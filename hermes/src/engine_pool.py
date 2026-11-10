"""Persistent Stockfish processes for every analysis search (plan 31.10 P7a, next1031/speed §3.1).

Before this, each search started its own Stockfish process: 282 processes for the 173 replayed answers, 116–158 ms
of start-up on every search (18 % of all engine time), and no bound on how many ran at once on a 2-vCPU host
(6–10 processes, 1–1.6 GB at peak). Here a fixed set of processes (``STOCKFISH_POOL_SIZE``, one thread and
``STOCKFISH_HASH_MB`` each) serves every search through one priority queue:

  0  a sentence the answer check holds, the voice check (PRIORITY_CHECK)
  1  the turn's engine line, a live-game note, a voice note, the review scan (PRIORITY_LINE, the default)
  2  the model's tool calls (PRIORITY_TOOL)
  3  work done in advance while the student thinks (PRIORITY_BACKGROUND, src/engine_precompute.py); any larger
     number is background too, further back (the precompute: 3 the positions the turn's check will ask for, 4 the
     forced-reply confirms, 5 a board's own positions)

Background searches use at most one process, and only when no other search waits — a short one (≤
SHORT_BACKGROUND_MS: a threat search, the position after a move) may take a second free process while nothing
answer-time waits; a search that arrives while every process is busy stops a running background search at once (its
partial result is dropped, the precompute asks again later), so an answer waits for at most one stop. A background
search waiting for the background's process stops a running one further back the same way.

An answer-time search starts from an empty hash (``ucinewgame``): a search to a fixed depth then gives the same
lines a fresh process gives, every time (the forced-reply check's rule, src/hypothetical.py). A background run over
one game's moves keeps the hash from move to move (``clear_hash=False``, the same process when it is free: *job*).

The API is synchronous and thread-safe: the server already runs engine work on its own threads. A process that dies
mid-search is restarted and the search tried once more; one that does not answer ``stop`` within a second is
killed and restarted; idle processes are pinged every 30 s and replaced after ``STOCKFISH_RECYCLE_SEARCHES``
searches. A binary that cannot start marks the pool down: searches fail at once with the error today's path gives,
and the pool tries again after 60 s. ``STOCKFISH_POOL=0`` keeps today's process per search (src/tools/stockfish.py).
"""

from __future__ import annotations

import atexit
import contextlib
import itertools
import logging
import queue
import re
import subprocess
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

PRIORITY_CHECK = 0
PRIORITY_LINE = 1
PRIORITY_TOOL = 2
PRIORITY_BACKGROUND = 3

# Background searches never take more than this many processes — except a short one (a threat search, the position
# after a move, ≤ SHORT_BACKGROUND_MS), which may take another free process while no answer-time search waits: the
# board's engine line and its threat searches then end together, ~1.5 s after the save instead of 2.1 s
# (review-wiring 01.11: an engine line asked 2 s after the save waited for the last threat search). An answer that
# arrives meanwhile stops one of them (a stop is answered at once).
MAX_BACKGROUND = 1
SHORT_BACKGROUND_MS = 400
PING_INTERVAL_S = 30.0
DOWN_RETRY_S = 60.0
START_TIMEOUT_S = 10.0
READY_TIMEOUT_S = 5.0
STOP_GRACE_S = 1.0
# A timed search that has not answered this long after its movetime is asked to stop (a healthy process answers
# ``stop`` at once: the result is used); one that does not answer within STOP_GRACE_S more is replaced.
READ_SLACK_S = 0.5
# A search with a caller's deadline is read until DEADLINE_SLACK_S / 2 past it, then stopped and given the other half.
DEADLINE_SLACK_S = 0.4
# A search given less than this is not started (the same floor as src/tools/stockfish.analyze_position).
MIN_SEARCH_MS = 100
# The weight of the newest answer-time search in the moving average of the wait for a process (answer_wait_ms).
ANSWER_WAIT_ALPHA = 0.1

_EOF = object()


class EngineDied(Exception):
    """The process exited (or its pipe broke) during a command."""


class EngineTimeout(Exception):
    """No answer within the read deadline, and none after ``stop`` either."""


# ── the caller's priority and job, for code that calls the analysis functions without passing them ──────────────
_local = threading.local()


@contextlib.contextmanager
def priority(level: int, job: "Optional[Job]" = None):
    """Searches started in this thread inside the block run at *level* (and belong to *job*)."""
    old = (getattr(_local, "priority", None), getattr(_local, "job", None))
    _local.priority = level
    if job is not None:
        _local.job = job
    try:
        yield
    finally:
        _local.priority, _local.job = old


def current_priority() -> int:
    p = getattr(_local, "priority", None)
    return PRIORITY_LINE if p is None else p


def current_job() -> "Optional[Job]":
    return getattr(_local, "job", None)


def at_priority(level: int, fn, *args, **kwargs):
    """*fn(*args, **kwargs)* with its searches at *level* — for submitting a function to an executor."""
    with priority(level):
        return fn(*args, **kwargs)


class Job:
    """A group of background searches that one board change asked for; ``cancel`` drops the rest of it.

    A job made with a *parent* (one search the precompute runs for its job, src/tools/stockfish._merged) is cancelled
    with it; ``promote`` raises it for good (*boost*), so a search promoted before it reached the queue still enters
    the queue at the level it was promoted to."""

    _ids = itertools.count(1)

    def __init__(self, label: str = "", parent: "Optional[Job]" = None):
        self.id = next(self._ids)
        self.label = label
        self.parent = parent
        self.boost: Optional[int] = None
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled or (self.parent is not None and self.parent.cancelled)

    @cancelled.setter
    def cancelled(self, value: bool) -> None:
        self._cancelled = bool(value)

    def belongs_to(self, other: "Optional[Job]") -> bool:
        return other is not None and (self is other or (self.parent is not None and self.parent.belongs_to(other)))

    def __repr__(self) -> str:  # pragma: no cover — logs only
        return f"Job({self.id}, {self.label!r}, cancelled={self.cancelled})"


class _Worker:
    """One Stockfish process, its reader thread and the line queue the reader fills."""

    _ids = itertools.count(1)

    def __init__(self, path: str, hash_mb: int):
        self.id = next(self._ids)
        self.path = path
        self.hash_mb = hash_mb
        self.proc: Optional[subprocess.Popen] = None
        self.lines: "queue.Queue" = queue.Queue()
        self._wlock = threading.Lock()
        self.searches = 0
        self.last_used = time.monotonic()
        self.last_job: Optional[int] = None
        self.stop_sent = False
        self.want_stop = False
        self.searching = False

    # ── process ──────────────────────────────────────────────────────────────────────────────────────────────
    def start(self) -> None:
        self.proc = subprocess.Popen([self.path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.lines = queue.Queue()
        proc, lines = self.proc, self.lines
        threading.Thread(target=self._read, args=(proc, lines), daemon=True,
                         name=f"stockfish-reader-{self.id}").start()
        self.send("uci\n")
        self.read_until("uciok", time.monotonic() + START_TIMEOUT_S)
        self.send(f"setoption name Threads value 1\nsetoption name Hash value {self.hash_mb}\nisready\n")
        self.read_until("readyok", time.monotonic() + START_TIMEOUT_S)
        self.searches = 0
        self.last_used = time.monotonic()
        self.last_job = None

    @staticmethod
    def _read(proc, lines) -> None:
        try:
            for line in proc.stdout:
                lines.put(line.strip())
        except (ValueError, OSError):
            pass
        lines.put(_EOF)

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def send(self, text: str) -> None:
        with self._wlock:
            try:
                self.proc.stdin.write(text)
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError, AttributeError) as exc:
                raise EngineDied(str(exc)) from exc

    def stop(self) -> None:
        """Ask this search to end now (from any thread): sent at once when it runs, right after its ``go`` when it
        is about to start; harmless when nothing runs."""
        with self._wlock:
            self.want_stop = True
            if not self.searching or self.stop_sent:
                return
            self.stop_sent = True
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError, AttributeError):
                pass

    def read_until(self, prefix: str, deadline: float, out: Optional[list] = None, on_line=None) -> list:
        out = [] if out is None else out
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise EngineTimeout(prefix)
            try:
                line = self.lines.get(timeout=left)
            except queue.Empty:
                raise EngineTimeout(prefix) from None
            if line is _EOF:
                raise EngineDied(f"engine exited while waiting for {prefix}")
            out.append(line)
            if on_line is not None:
                try:
                    on_line(line)  # the caller watches the search as it goes (src/tools/stockfish.progress)
                except Exception:  # noqa: BLE001 — a watcher never breaks the search
                    on_line = None
            if line.startswith(prefix):
                return out

    def kill(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            pass

    def quit(self) -> None:
        proc = self.proc
        if proc is None:
            return
        try:
            self.send("quit\n")
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            self.kill()
        self.proc = None

    def restart(self) -> None:
        self.kill()
        self.start()

    # ── one search ───────────────────────────────────────────────────────────────────────────────────────────
    def run(self, fen: str, go: str, multipv: int, clear_hash: bool, read_timeout: float, on_line=None,
            stop_grace: float = STOP_GRACE_S) -> tuple:
        """(the engine's output up to ``bestmove``, whether ``stop`` cut the search short)."""
        # Anything left from an earlier command (a ping's readyok) is not this search's.
        while True:
            try:
                left = self.lines.get_nowait()
            except queue.Empty:
                break
            if left is _EOF:
                raise EngineDied("engine exited")
        self.stop_sent = False
        self.send(("ucinewgame\n" if clear_hash else "") + f"setoption name MultiPV value {multipv}\n"
                  f"position fen {fen}\nisready\n")
        self.read_until("readyok", time.monotonic() + READY_TIMEOUT_S)
        try:
            with self._wlock:
                try:
                    self.proc.stdin.write(f"go {go}\n")
                    if self.want_stop:  # stopped before it started (a waiting answer, a cancelled job)
                        self.proc.stdin.write("stop\n")
                        self.stop_sent = True
                    self.proc.stdin.flush()
                except (BrokenPipeError, OSError, ValueError, AttributeError) as exc:
                    raise EngineDied(str(exc)) from exc
                self.searching = True
            out: list = []
            try:
                self.read_until("bestmove", time.monotonic() + read_timeout, out, on_line)
            except EngineTimeout:
                # Late: stop it. A process that answers the stop gave a complete (if cut) search, like a movetime
                # one — the caller gets it; one that does not answer is hung (EngineTimeout: it is replaced).
                self.stop()
                try:
                    self.read_until("bestmove", time.monotonic() + stop_grace, out)
                except EngineTimeout:
                    raise EngineTimeout("bestmove") from None
            return out, self.stop_sent or self.want_stop
        finally:
            with self._wlock:
                self.searching = False

    def ping(self) -> bool:
        try:
            self.send("isready\n")
            self.read_until("readyok", time.monotonic() + 2.0)
            return True
        except (EngineDied, EngineTimeout):
            return False


class _Waiter:
    __slots__ = ("priority", "seq", "job", "short")

    def __init__(self, priority: int, seq: int, job: Optional[Job], short: bool = False):
        self.priority, self.seq, self.job, self.short = priority, seq, job, short

    def key(self) -> tuple:
        return (self.priority, self.seq)


def _is_short(go: str) -> bool:
    """A search bounded by a short movetime and no depth (a threat search, a move's check)."""
    m = re.search(r"\bmovetime (\d+)", go)
    return bool(m) and int(m.group(1)) <= SHORT_BACKGROUND_MS and not re.search(r"\bdepth\b", go)


def _with_time_cap(go: str, left_ms: int) -> str:
    """*go* bounded to *left_ms*: a depth search gets (or keeps a shorter) ``movetime``."""
    if not re.search(r"\bdepth\b", go):
        return go
    m = re.search(r"\bmovetime (\d+)", go)
    if m:
        if int(m.group(1)) <= left_ms:
            return go
        return go[:m.start(1)] + str(left_ms) + go[m.end(1):]
    head, sep, tail = go.partition(" searchmoves ")
    return f"{head} movetime {left_ms}" + (sep + tail if sep else "")


def _read_timeout(spec: str, timeout: Optional[float], deadline: Optional[float]) -> float:
    """How long a search's output is read before it is asked to stop: the caller's *timeout*, else the movetime plus
    READ_SLACK_S (30 s for a search with no time bound) — never past the caller's *deadline* (plus the slack)."""
    m = re.search(r"\bmovetime (\d+)", spec)
    limit = timeout if timeout is not None else (int(m.group(1)) / 1000.0 + READ_SLACK_S if m else 30.0)
    if deadline is not None:
        limit = min(limit, max(0.0, deadline - time.monotonic()) + DEADLINE_SLACK_S / 2)
    return max(0.05, limit)


class EnginePool:
    def __init__(self, path: str, size: int = 2, hash_mb: int = 32, recycle: int = 5000):
        self.path = path
        self.size = max(1, int(size))
        self.hash_mb = hash_mb
        self.recycle = max(1, int(recycle))
        self._cv = threading.Condition()
        self._workers: list[_Worker] = []
        self._free: list[_Worker] = []
        self._busy: dict[int, tuple] = {}  # worker id → (worker, priority, job)
        self._waiters: list[_Waiter] = []
        self._seq = itertools.count()
        self._started = False
        self._closed = False
        self._down_at: Optional[float] = None
        self._down_error: Optional[str] = None
        self._starting = False
        self._maint: Optional[threading.Thread] = None
        self._replacing: set = set()
        self.stats = {"searches": 0, "restarts": 0, "retries": 0, "preempted": 0, "cancelled": 0,
                      "recycled": 0, "timeouts": 0, "no_time": 0, "started": 0}
        # How long an answer-time search waits for a process now (ms, a moving average): what a search asked now
        # should expect before it starts (src/tools/critical_moments.scan_estimate_ms, 10.11 load test).
        self.answer_wait_ms = 0.0

    # ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────
    def start(self) -> bool:
        """Start the processes (at warm-up, or on the first search). False when the binary cannot start."""
        with self._cv:
            if self._started and not self._closed:
                return True
            if self._starting:
                while self._starting:
                    self._cv.wait(1.0)
                return self._started
            if self._down_at is not None and time.monotonic() - self._down_at < DOWN_RETRY_S:
                return False
            self._starting = True
        workers, errors = [], []

        def _one():
            w = _Worker(self.path, self.hash_mb)
            try:
                w.start()
                workers.append(w)
            except (OSError, EngineDied, EngineTimeout) as exc:
                w.kill()
                errors.append(exc)

        threads = [threading.Thread(target=_one, daemon=True) for _ in range(self.size)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with self._cv:
            self._starting = False
            if workers:
                self._workers = list(workers)
                self._free = list(workers)
                self._started, self._closed = True, False
                self._down_at = self._down_error = None
                self.stats["started"] += len(workers)
                if self._maint is None or not self._maint.is_alive():
                    self._maint = threading.Thread(target=self._maintain, daemon=True, name="stockfish-pool")
                    self._maint.start()
            else:
                self._down_at = time.monotonic()
                exc = errors[0] if errors else None
                self._down_error = (f"Stockfish not found at {self.path}." if isinstance(exc, FileNotFoundError)
                                    else f"Stockfish could not start ({exc}).")
                logger.warning("engine pool down: %s", self._down_error)
            self._cv.notify_all()
            return bool(workers)

    def close(self) -> None:
        with self._cv:
            self._closed = True
            self._started = False
            workers, self._workers, self._free = self._workers, [], []
            self._cv.notify_all()
        for th in list(self._replacing):
            th.join(timeout=5)
        for w in workers:
            w.quit()

    def status(self) -> dict:
        with self._cv:
            return {
                "on": True, "size": self.size, "processes": len(self._workers),
                "alive": sum(1 for w in self._workers if w.alive()),
                "busy": len(self._busy), "waiting": len(self._waiters),
                "background": sum(1 for _, p, _ in self._busy.values() if p >= PRIORITY_BACKGROUND),
                "down": self._down_error, "hash_mb": self.hash_mb, "answer_wait_ms": round(self.answer_wait_ms),
                **self.stats,
            }

    def running(self) -> int:
        """Answer-time searches at work plus those waiting for a process (the turn's load rule reads this). Work done
        in advance is not load: it gives way to any of them."""
        with self._cv:
            return (sum(1 for _, p, _ in self._busy.values() if p < PRIORITY_BACKGROUND)
                    + sum(1 for w in self._waiters if w.priority < PRIORITY_BACKGROUND))

    def has_spare(self) -> bool:
        """A process is free and no search waits for one."""
        with self._cv:
            return bool(self._free) and not self._waiters

    def pids(self) -> list:
        with self._cv:
            return [w.proc.pid for w in self._workers if w.proc is not None]

    # ── the queue ────────────────────────────────────────────────────────────────────────────────────────────
    def _head(self) -> Optional[_Waiter]:
        return min(self._waiters, key=_Waiter.key) if self._waiters else None

    def _background_busy(self) -> int:
        return sum(1 for _, p, _ in self._busy.values() if p >= PRIORITY_BACKGROUND)

    def _preempt(self, level: int) -> None:
        """A search at *level* waits and no process it may take is free: stop background searches further back than
        it — as many as there are searches at *level* or before waiting for one (minus the stops already on their
        way), the furthest back first."""
        need = sum(1 for wt in self._waiters if wt.priority <= level)
        running = [(p, w) for w, p, _ in list(self._busy.values()) if p >= PRIORITY_BACKGROUND and p > level]
        need -= sum(1 for _, w in running if w.want_stop)
        for p, w in sorted((x for x in running if not x[1].want_stop), key=lambda x: (-x[0], -x[1].id)):
            if need <= 0:
                return
            self.stats["preempted"] += 1
            w.stop()
            need -= 1

    def _background_may_take(self, me: "_Waiter") -> bool:
        """A background waiter at the head may take a free process: below MAX_BACKGROUND, or a short search while no
        answer-time search waits."""
        busy = self._background_busy()
        if busy < MAX_BACKGROUND:
            return True
        return me.short and busy < len(self._workers) and not any(
            wt.priority < PRIORITY_BACKGROUND for wt in self._waiters)

    def _acquire(self, prio: int, deadline: Optional[float], job: Optional[Job], short: bool = False):
        me = _Waiter(prio, next(self._seq), job, short)
        with self._cv:
            self._waiters.append(me)
            try:
                while True:
                    if self._closed or not self._started:
                        return None, "closed"
                    if job is not None and job.cancelled:
                        return None, "cancelled"
                    if job is not None and job.boost is not None and job.boost < me.priority:
                        me.priority = job.boost  # promoted before (or while) it queued
                    head = self._head()
                    if head is me and self._free and (me.priority < PRIORITY_BACKGROUND
                                                      or self._background_may_take(me)):
                        w = next((x for x in self._free if job is not None and x.last_job == job.id), self._free[0])
                        self._free.remove(w)
                        w.want_stop = w.stop_sent = False
                        self._busy[w.id] = (w, me.priority, job)
                        return w, None
                    if me.priority < PRIORITY_BACKGROUND and not self._free:
                        self._preempt(me.priority)
                    elif head is me and me.priority >= PRIORITY_BACKGROUND and (
                            not self._free or not self._background_may_take(me)):
                        self._preempt(me.priority)
                    wait = 1.0
                    if deadline is not None:
                        wait = deadline - time.monotonic()
                        if wait <= 0:
                            self.stats["no_time"] += 1
                            return None, "no time left for the search"
                        wait = min(wait, 1.0)
                    self._cv.wait(wait)
            finally:
                self._waiters.remove(me)
                self._cv.notify_all()

    def _release(self, w: _Worker, job: Optional[Job], broken: bool = False) -> None:
        with self._cv:
            self._busy.pop(w.id, None)
            w.last_used = time.monotonic()
            w.last_job = job.id if job is not None else None
            w.searches += 1
            retire = broken or not w.alive() or w.searches >= self.recycle
            if not retire and w in self._workers:
                self._free.append(w)
            self._cv.notify_all()
        if retire and not self._closed:
            if not broken and w.alive():
                self.stats["recycled"] += 1
            th = threading.Thread(target=self._replace, args=(w,), daemon=True, name="stockfish-restart")
            self._replacing.add(th)
            th.start()

    def _replace(self, w: _Worker) -> None:
        try:
            self._replace_one(w)
        finally:
            self._replacing.discard(threading.current_thread())

    def _replace_one(self, w: _Worker) -> None:
        if self._closed:
            w.kill()
            return
        try:
            w.restart()
            self.stats["restarts"] += 1
        except (OSError, EngineDied, EngineTimeout) as exc:
            logger.warning("engine pool: process %s did not restart (%s)", w.id, exc)
            w.kill()
            with self._cv:
                if w in self._workers:
                    self._workers.remove(w)
                if not self._workers:
                    self._started = False
                    self._down_at = time.monotonic()
                    self._down_error = f"Stockfish could not restart ({exc})."
                self._cv.notify_all()
            return
        with self._cv:
            if w in self._workers and not self._closed:
                self._free.append(w)
            else:
                w.quit()
            self._cv.notify_all()

    def _maintain(self) -> None:
        """Ping the processes idle for PING_INTERVAL_S; a silent one is replaced."""
        while True:
            time.sleep(min(PING_INTERVAL_S, 5.0))
            with self._cv:
                if self._closed:
                    return
                now = time.monotonic()
                idle = [w for w in self._free if now - w.last_used >= PING_INTERVAL_S]
                for w in idle:
                    self._free.remove(w)
                    self._busy[w.id] = (w, PRIORITY_BACKGROUND, None)
            for w in idle:
                ok = w.alive() and w.ping()
                with self._cv:
                    self._busy.pop(w.id, None)
                    w.last_used = time.monotonic()
                    if ok and w in self._workers:
                        self._free.append(w)
                    self._cv.notify_all()
                if not ok:
                    logger.warning("engine pool: process %s did not answer a ping; restarting", w.id)
                    self._replace(w)

    # ── one search ───────────────────────────────────────────────────────────────────────────────────────────
    def search(self, fen: str, *, go: str, multipv: int = 1, priority: Optional[int] = None,
               deadline: Optional[float] = None, clear_hash: bool = True, job: Optional[Job] = None,
               timeout: Optional[float] = None, on_line=None) -> dict:
        """Run ``go <go>`` on *fen*; {"output": [lines up to bestmove], "stopped": bool, "wait_ms": float}, or
        {"error": …}.

        *deadline* (time.monotonic()) bounds the wait for a process and, for a depth search, the search itself: its
        ``movetime`` is set from the time left once a process is free. *timeout* is the read limit (default: the
        movetime + READ_SLACK_S, or 30 s). A stopped background search (``stopped``) is incomplete: the caller drops
        it. *on_line(line)* sees each line of the engine's output as it comes (from the caller's thread).
        """
        prio = current_priority() if priority is None else priority
        job = current_job() if job is None else job
        if not self._started and not self.start():
            return {"error": self._down_error or "Stockfish is not available."}
        if job is not None and job.cancelled:
            return {"error": "cancelled"}
        t0 = time.monotonic()
        w, why = self._acquire(prio, deadline, job, short=_is_short(go))
        if w is None:
            if why == "closed" and not self._closed and self._down_error:
                why = self._down_error
            return {"error": why}
        wait_ms = (time.monotonic() - t0) * 1000.0
        if prio < PRIORITY_BACKGROUND:
            with self._cv:
                self.answer_wait_ms += ANSWER_WAIT_ALPHA * (wait_ms - self.answer_wait_ms)
        broken = False
        try:
            for attempt in (1, 2):
                # The time cap and the read limit from the time left now — on the retry after a crash too, which
                # must not run past the caller's deadline either (review-wiring 01.11).
                spec = go
                if deadline is not None:
                    left = int((deadline - time.monotonic()) * 1000)
                    if left < MIN_SEARCH_MS:
                        self.stats["no_time"] += 1
                        return {"error": "no time left for the search"}
                    spec = _with_time_cap(go, left)
                read_timeout = _read_timeout(spec, timeout, deadline)
                # A search with a deadline: a hung process costs the caller at most DEADLINE_SLACK_S past it, in all
                # (the read slack and the grace after ``stop`` come out of that; review-wiring2 01.11: 1.5 s before)
                grace = STOP_GRACE_S if deadline is None else DEADLINE_SLACK_S / 2
                try:
                    if job is not None and job.cancelled:
                        return {"error": "cancelled"}
                    out, stopped = w.run(fen, spec, multipv, clear_hash or attempt == 2, read_timeout, on_line, grace)
                    self.stats["searches"] += 1
                    if stopped and job is not None and job.cancelled:
                        self.stats["cancelled"] += 1
                    return {"output": out, "stopped": stopped and prio >= PRIORITY_BACKGROUND,
                            "wait_ms": wait_ms, "worker": w.id}
                except EngineTimeout:
                    self.stats["timeouts"] += 1
                    broken = True
                    return {"error": "Stockfish analysis timed out."}
                except EngineDied as exc:
                    logger.warning("engine pool: process %s died (%s)%s", w.id, exc,
                                   "; retrying once" if attempt == 1 else "")
                    try:
                        w.restart()
                        self.stats["restarts"] += 1
                    except (OSError, EngineDied, EngineTimeout) as exc2:
                        broken = True
                        return {"error": f"Stockfish could not restart ({exc2})."}
                    if attempt == 1:
                        self.stats["retries"] += 1
            broken = True
            return {"error": "Stockfish died during the search."}
        finally:
            self._release(w, job, broken=broken)

    def promote(self, job: Optional[Job], level: int) -> None:
        """An answer waits for *job*'s search of the same position (src/tools/stockfish._merged): that search now
        runs at *level* — it is no longer stopped for an answer, and it is not kept waiting behind one."""
        if job is None:
            return
        with self._cv:
            job.boost = level if job.boost is None else min(job.boost, level)
            for wid, (w, p, j) in list(self._busy.items()):
                if j is job and p > level:
                    self._busy[wid] = (w, level, j)
            for wt in self._waiters:
                if wt.job is job and wt.priority > level:
                    wt.priority = level
            self._cv.notify_all()

    def demote(self, job: Optional[Job], level: int) -> None:
        """The answer that promoted *job* stopped waiting for it (its own deadline came first): the search runs at
        *level* again (its own, a background one) — an answer may stop it, and it counts toward MAX_BACKGROUND.
        Promoted for good, a precompute search a check gave up on held a process unstoppable to its own cap
        (verify 06.11: STOCKFISH_EXACT_MAX_MS, 8 s, on a pool of two)."""
        if job is None:
            return
        with self._cv:
            job.boost = None
            for wid, (w, p, j) in list(self._busy.items()):
                if j is job and p < level:
                    self._busy[wid] = (w, level, j)
            for wt in self._waiters:
                if wt.job is job and wt.priority < level:
                    wt.priority = level
            self._cv.notify_all()

    def cancel(self, job: Optional[Job]) -> None:
        """Drop *job*: its waiting searches return at once, a running one gets ``stop``."""
        if job is None:
            return
        with self._cv:
            job.cancelled = True
            for w, _, j in self._busy.values():
                if j is not None and j.belongs_to(job):
                    w.stop()
            self._cv.notify_all()


# ── the server's pool ─────────────────────────────────────────────────────────────────────────────────────────
_pool: Optional[EnginePool] = None
_pool_lock = threading.Lock()


def enabled() -> bool:
    try:
        from src import config

        return bool(config.STOCKFISH_POOL)
    except Exception:  # noqa: BLE001
        return False


def get_pool() -> EnginePool:
    global _pool
    with _pool_lock:
        if _pool is None:
            from src import config
            from src.tools.stockfish import STOCKFISH_PATH

            _pool = EnginePool(STOCKFISH_PATH, config.STOCKFISH_POOL_SIZE, config.STOCKFISH_HASH_MB,
                               config.STOCKFISH_RECYCLE_SEARCHES)
        return _pool


def start() -> bool:
    """Start the server's processes now (warm-up); False when the pool is off or the binary cannot start."""
    return enabled() and get_pool().start()


def search(fen: str, *, go: str, multipv: int = 1, priority: Optional[int] = None, deadline: Optional[float] = None,
           clear_hash: bool = True, job: Optional[Job] = None, timeout: Optional[float] = None, on_line=None) -> dict:
    return get_pool().search(fen, go=go, multipv=multipv, priority=priority, deadline=deadline,
                             clear_hash=clear_hash, job=job, timeout=timeout, on_line=on_line)


def cancel(job: Optional[Job]) -> None:
    if _pool is not None:
        _pool.cancel(job)


def promote(job: Optional[Job], level: int) -> None:
    if _pool is not None:
        _pool.promote(job, level)


def demote(job: Optional[Job], level: int) -> None:
    if _pool is not None:
        _pool.demote(job, level)


def running() -> int:
    return _pool.running() if _pool is not None else 0


def answer_wait_ms() -> float:
    """The recent wait of an answer-time search for a process (ms, a moving average; 0 without a pool)."""
    return float(getattr(_pool, "answer_wait_ms", 0.0) or 0.0) if _pool is not None else 0.0


def has_spare() -> bool:
    """The server's pool has a free process and nothing waiting (work that is only a guess may run)."""
    return _pool is not None and _pool.has_spare()


def status() -> dict:
    if not enabled():
        return {"on": False}
    if _pool is None:
        return {"on": True, "processes": 0, "started": 0}
    return _pool.status()


def shutdown() -> None:
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.close()


def _set_pool_for_tests(pool: Optional[EnginePool]) -> Optional[EnginePool]:
    global _pool
    with _pool_lock:
        old, _pool = _pool, pool
    return old


atexit.register(shutdown)
