"""Tool 5: analyze_position — Stockfish engine analysis."""

import contextlib
import json
import os
import shutil
import logging
import re
import subprocess
import threading
import time
from collections import OrderedDict

import chess

from tools.registry import registry

logger = logging.getLogger(__name__)

# STOCKFISH_PATH env overrides the Debian default (macOS/brew installs it elsewhere).
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish") or "/usr/games/stockfish"
# Depth 20 costs ~6 s per position on the coach host and the model calls the engine
# 2-5 times per turn (bench 2026-09-23); depth 16 is ~2 s with the same top move in
# coaching positions. STOCKFISH_DEPTH overrides without a deploy.
DEFAULT_DEPTH = int(os.environ.get("STOCKFISH_DEPTH", "16"))
# The models pass `depth` explicitly (the old schema text said "default 20", and
# the voice bench of 2026-09-24 caught Gemini Live asking for 20 → 5 s of
# silence), so the default alone does not bound the cost — the ceiling does.
MAX_DEPTH = max(DEFAULT_DEPTH, int(os.environ.get("STOCKFISH_MAX_DEPTH", str(DEFAULT_DEPTH))))
# Depth alone does not bound the time: a sharp middlegame at depth 16 with three
# lines took 24 s in a game review on the bench of 2026-09-28. The search stops
# at the depth or after this many milliseconds, whichever comes first (0 = no cap).
MAX_MS = int(os.environ.get("STOCKFISH_MAX_MS", "3000"))
# 06.11: MAX_MS bounds the searches that have no clock of their own (the model's analyze_position call). A search that
# judges — one to a fixed depth from an empty hash, kept in the exact store (the move check, the forced-reply confirm,
# the precompute's searches for them, the game's evals) — is bounded by its caller's deadline (*max_ms*), else by
# this: the longest a check waits for one such search (src/hypothetical.FORCED_CONFIRM_MAX_MS). Capped at MAX_MS, the
# move check's depth-16 search after «сыграй конём на e4» (650k nodes) stopped short on the bench host in 3 runs of 3
# and the bad move went out unjudged although the check had 6 s (shipped1104/REPORT.md, V-eng-02).
EXACT_MAX_MS = int(os.environ.get("STOCKFISH_EXACT_MAX_MS", "8000"))
DEFAULT_MULTIPV = 3
MAX_MULTIPV = 5
TIMEOUT_SECONDS = 30

ANALYZE_SCHEMA = {
    "name": "analyze_position",
    "description": "Analyze a chess position using Stockfish. Provide a FEN string and get evaluation, best move, and top lines.",
    "parameters": {
        "type": "object",
        "properties": {
            "fen": {"type": "string", "description": "FEN string of the position to analyze."},
            "depth": {"type": "integer", "description": f"Search depth; leave unset (default {DEFAULT_DEPTH}, max {MAX_DEPTH})."},
            "multipv": {"type": "integer", "description": f"Number of principal variations (default {DEFAULT_MULTIPV}, max {MAX_MULTIPV})."},
        },
        "required": ["fen"],
    },
}


def _validate_fen(fen: str) -> bool:
    """Validate a FEN string using python-chess."""
    try:
        board = chess.Board(fen)
        return board.is_valid()
    except (ValueError, IndexError):
        return False


def _parse_info_line(line: str) -> dict | None:
    """Parse a Stockfish info line into a structured dict."""
    if not line.startswith("info"):
        return None

    result = {}

    # Extract multipv
    m = re.search(r"multipv (\d+)", line)
    if m:
        result["multipv"] = int(m.group(1))

    # Extract depth
    m = re.search(r" depth (\d+)", line)
    if m:
        result["depth"] = int(m.group(1))

    # Extract score
    m = re.search(r"score cp (-?\d+)", line)
    if m:
        result["score"] = int(m.group(1)) / 100.0
    else:
        m = re.search(r"score mate (-?\d+)", line)
        if m:
            mate_in = int(m.group(1))
            result["score"] = 10000 * (1 if mate_in > 0 else -1)
            result["mate_in"] = mate_in

    # Extract PV (principal variation)
    m = re.search(r" pv (.+)", line)
    if m:
        result["pv"] = m.group(1).strip()

    return result if result else None


def analyze_position(
    fen: str,
    depth: int = DEFAULT_DEPTH,
    multipv: int = DEFAULT_MULTIPV,
    stockfish_path: str = STOCKFISH_PATH,
    timeout: int = TIMEOUT_SECONDS,
    movetime_ms: int | None = None,
    max_ms: int | None = None,
    searchmoves: tuple | list | None = None,
    cap_ms: int | None = None,
) -> dict:
    """Run Stockfish analysis on a FEN position — to *depth*, or for *movetime_ms* when given.

    *max_ms* bounds a search to *depth* in time, the engine server and the local fallback together: a search
    stopped short of the depth returns its lines as deep as they got (the caller decides whether that says
    anything), and no time is left → an error. The caller's *max_ms* is the search's whole bound: STOCKFISH_MAX_MS
    does not cut it shorter (06.11). Without *max_ms* a depth search is capped at *cap_ms*, else at MAX_MS — the cap
    of the search itself, not of the wait for a process.

    *searchmoves* (UCI strings; plan 31.10): the search looks only at these moves of the side to move («решает ферзь»:
    the queen's best). The engine server has no such option, so a restricted search is always local."""
    from src.fen_repair import repair_fen

    fen = repair_fen(fen)
    if not _validate_fen(fen):
        return {"error": f"Invalid FEN: {fen}"}
    import time

    deadline = time.monotonic() + max_ms / 1000.0 if max_ms and not movetime_ms else None

    # The site's own engine server (engine.chesster.io) when ENGINE_API_URL is set:
    # no Stockfish process on the coach host, its cache and pool instead. Any
    # failure falls back to the local engine, so the turn never waits in vain.
    sm = _searchmoves(searchmoves)
    if ENGINE_API_URL and not sm:
        try:
            remote = _analyze_remote(fen, depth, multipv, movetime_ms, wait_s=max_ms / 1000.0 if deadline else None)
            if remote and remote.get("lines"):
                return remote
        except Exception as exc:  # noqa: BLE001
            logger.warning("engine server %s failed (%s); using the local engine", ENGINE_API_URL, exc)
    cap = None
    if deadline is not None:
        cap = int((deadline - time.monotonic()) * 1000)
        if cap < 100:
            return {"error": "no time left for the search"}
    # The search's own cap: none when the caller brought a deadline (the pool sets the time left once a process is
    # free; the process-per-search path gets *cap*), else *cap_ms* or the analysis cap.
    own_cap = 0 if deadline is not None else (cap_ms if cap_ms is not None else MAX_MS)
    if pool_on():
        # A persistent process (src/engine_pool.py): the time cap is set once a process is free, so waiting for
        # one counts against *max_ms* as the start of a new process did.
        # The flight's own time bound — what a check that joins it weighs against a search of its own (exact_join).
        budget_s = max_ms / 1000.0 if deadline is not None else (own_cap / 1000.0 if own_cap > 0 else None)
        flight = None if movetime_ms else _exact_begin(fen, depth, multipv, sm, budget_s)
        result = {"error": "search failed"}
        try:
            if flight is not None and flight.job is not None:
                from src import engine_pool

                with engine_pool.priority(engine_pool.current_priority(), flight.job):
                    result = _analyze_pooled(fen, depth, multipv, timeout, movetime_ms, deadline, sm, own_cap)
            else:
                result = _analyze_pooled(fen, depth, multipv, timeout, movetime_ms, deadline, sm, own_cap)
            _exact_put(fen, depth, multipv, sm, movetime_ms, result)  # `ucinewgame` first: an empty hash
            return result
        finally:
            if flight is not None:
                _exact_end(fen, depth, multipv, sm, flight, result)
    with _running_lock:
        global _running
        _running += 1
    try:
        cap = cap if cap is not None else own_cap
        if sm:
            result = _analyze_position(fen, depth, multipv, stockfish_path, timeout, movetime_ms, cap, searchmoves=sm)
        else:
            result = _analyze_position(fen, depth, multipv, stockfish_path, timeout, movetime_ms, cap)
        return result
    finally:
        with _running_lock:
            _running -= 1


ENGINE_API_URL = os.environ.get("ENGINE_API_URL", "").strip().rstrip("/")
ENGINE_API_TOKEN = os.environ.get("ENGINE_API_TOKEN", "").strip()
ENGINE_API_MAX_MULTIPV = 4
ENGINE_API_MAX_MOVETIME_S = 2.0


def _analyze_remote(fen: str, depth: int, multipv: int, movetime_ms: int | None,
                    wait_s: float | None = None) -> dict | None:
    """POST /analyze on the engine server, in the shape analyze_position returns.

    The server answers from White's side with SAN lines; here the score is for
    the side to move and the pv is UCI, as the local parser gives them.
    """
    import httpx
    import chess

    body: dict = {"fen": fen, "multipv": max(1, min(int(multipv or 1), ENGINE_API_MAX_MULTIPV))}
    if movetime_ms:
        body["movetime"] = min(movetime_ms / 1000.0, ENGINE_API_MAX_MOVETIME_S)
    else:
        body["depth"] = max(1, min(int(depth or DEFAULT_DEPTH), 30))
    wait = (body.get("movetime") or 4.0) + 3.0
    if wait_s is not None:
        wait = min(wait, max(0.1, wait_s))  # a search bounded in time: not a second more on the network
    headers = {"X-Engine-Token": ENGINE_API_TOKEN} if ENGINE_API_TOKEN else {}
    resp = httpx.post(f"{ENGINE_API_URL}/analyze", json=body, headers=headers, timeout=wait)
    resp.raise_for_status()
    data = resp.json() or {}
    board = chess.Board(fen)
    sign = 1 if board.turn == chess.WHITE else -1
    raw_lines = data.get("lines") or [data]
    lines = []
    for i, ln in enumerate(raw_lines[: body["multipv"]]):
        ev = ln.get("evaluation") or data.get("evaluation") or {}
        b = board.copy(stack=False)
        uci = []
        for san in ln.get("pv") or []:
            try:
                mv = b.parse_san(san)
            except ValueError:
                break
            uci.append(mv.uci())
            b.push(mv)
        if not uci and ln.get("bestMove"):
            uci = [ln["bestMove"]]
        entry = {"multipv": i + 1, "depth": ln.get("depth") or data.get("depth"), "pv": " ".join(uci)}
        value = ev.get("value", 0) or 0
        if ev.get("type") == "mate":
            mate = int(value) * sign
            entry["mate_in"] = mate
            entry["score"] = 10000 * (1 if mate > 0 else -1)
        else:
            entry["score"] = float(value) / 100.0 * sign
        lines.append(entry)
    return {"lines": lines, "depth": data.get("depth"), "remote": True} if lines else None


_running = 0
_running_lock = __import__("threading").Lock()


def engines_running() -> int:
    """Stockfish processes at work right now — the turn shortens its searches
    when several students ask at once (local stand, 8 turns at once, 2026-10-05:
    every engine line missed its 2.5 s wait and the answers went out without facts).

    With the pool (plan 31.10 P7a): searches at work plus searches waiting for a process."""
    with _running_lock:
        n = _running
    if pool_on():
        from src import engine_pool

        n += engine_pool.running()
    return n


def pool_on() -> bool:
    """STOCKFISH_POOL (src/config.py), read at call time so a test or an operator can switch it."""
    try:
        from src import config

        return bool(config.STOCKFISH_POOL)
    except Exception:  # noqa: BLE001
        return False


def _go_spec(depth: int, movetime_ms: int | None, searchmoves=(), cap_ms: int | None = None) -> str:
    """The `go` arguments the process-per-search path sends: a depth search capped at *cap_ms* (default MAX_MS; 0 =
    no cap of its own — a caller's deadline then sets it on the pool)."""
    restrict = f" searchmoves {' '.join(searchmoves)}" if searchmoves else ""
    cap = MAX_MS if cap_ms is None else cap_ms
    if movetime_ms:
        return f"movetime {movetime_ms}{restrict}"
    if cap > 0:
        return f"depth {depth} movetime {cap}{restrict}"
    return f"depth {depth}{restrict}"


# A watcher of the search the calling thread is about to start on the pool (progress()): it sees the engine's output
# lines as they come — src/voice_engine_note.engine_note starts the threat search after the best move from the
# line's best move so far, beside the line, instead of after it (review-wiring 01.11: 1.81 s → ~1.5 s).
_progress = threading.local()


@contextlib.contextmanager
def progress(on_line):
    """Searches this thread starts on the pool inside the block report each output line to *on_line(line)*."""
    old = getattr(_progress, "fn", None)
    _progress.fn = on_line
    try:
        yield
    finally:
        _progress.fn = old


def _analyze_pooled(fen, depth, multipv, timeout, movetime_ms, deadline=None, searchmoves=(), cap_ms=None) -> dict:
    """analyze_position on the pool: the same `go`, the same parsing, the same result as a new process gives."""
    from src import engine_pool

    out = engine_pool.search(fen, go=_go_spec(depth, movetime_ms, searchmoves, cap_ms), multipv=multipv,
                             deadline=deadline, clear_hash=True,
                             timeout=None if movetime_ms or timeout == TIMEOUT_SECONDS else timeout,
                             on_line=getattr(_progress, "fn", None))
    if "error" in out:
        return {"error": out["error"]}
    if out.get("stopped"):
        # A background search an answer needed the process for (or a board that changed): incomplete, never cached.
        return {"error": "search stopped (preempted)"}
    return _build_result(out["output"], depth, movetime_ms, capped=deadline is not None or (MAX_MS if cap_ms is None else cap_ms) > 0)


def _searchmoves(searchmoves) -> tuple:
    """*searchmoves* as a sorted tuple of valid UCI strings (() for none): one spelling for the cache key and the
    `go` command."""
    if not searchmoves:
        return ()
    out = set()
    for m in searchmoves:
        u = str(m).strip()
        if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", u):
            out.add(u)
    return tuple(sorted(out))


def _analyze_position(fen, depth, multipv, stockfish_path, timeout, movetime_ms, cap_ms=None, searchmoves=()) -> dict:
    try:
        proc = subprocess.Popen(
            [stockfish_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return {"error": f"Stockfish not found at {stockfish_path}."}

    try:
        proc.stdin.write("uci\n")
        # The pool's options (src/engine_pool.py): one thread (a fixed-depth search then gives the same lines every
        # run — the exact store's rule) and the same hash, so STOCKFISH_POOL=0 judges a move as the pool does.
        proc.stdin.write(f"setoption name Threads value 1\nsetoption name Hash value {_hash_mb()}\n")
        proc.stdin.write("isready\n")
        proc.stdin.write(f"setoption name MultiPV value {multipv}\n")
        proc.stdin.write(f"position fen {fen}\n")
        # The caller's cap (its deadline's time left, or its own cap) replaces MAX_MS; MAX_MS when it brings none.
        cap = cap_ms if cap_ms is not None else MAX_MS
        restrict = f" searchmoves {' '.join(searchmoves)}" if searchmoves else ""
        if movetime_ms:
            proc.stdin.write(f"go movetime {movetime_ms}{restrict}\n")
        elif cap > 0:
            proc.stdin.write(f"go depth {depth} movetime {cap}{restrict}\n")
        else:
            proc.stdin.write(f"go depth {depth}{restrict}\n")
        proc.stdin.flush()

        lines = []
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            lines.append(line)
            if line.startswith("bestmove"):
                break
        else:
            proc.kill()
            return {"error": "Stockfish analysis timed out."}

        proc.stdin.write("quit\n")
        proc.stdin.flush()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"error": "Stockfish analysis timed out."}
    except BrokenPipeError:
        pass  # Stockfish already exited

    return _build_result(lines, depth, movetime_ms, capped=cap > 0)


def _hash_mb() -> int:
    try:
        from src import config

        return int(config.STOCKFISH_HASH_MB)
    except Exception:  # noqa: BLE001
        return 16


def _build_result(lines: list, depth: int, movetime_ms: int | None, capped: bool | None = None) -> dict:
    """The analysis dict from Stockfish's output up to `bestmove` (one parser for the new-process and pool paths)."""
    # Parse info lines — keep only the deepest for each multipv
    best_lines: dict[int, dict] = {}
    for line in lines:
        parsed = _parse_info_line(line)
        if parsed and "multipv" in parsed and "pv" in parsed:
            pv_num = parsed["multipv"]
            if pv_num not in best_lines or parsed.get("depth", 0) >= best_lines[pv_num].get("depth", 0):
                best_lines[pv_num] = parsed

    # Parse bestmove
    best_move = ""
    for line in lines:
        if line.startswith("bestmove"):
            parts = line.split()
            if len(parts) >= 2:
                best_move = parts[1]

    # Build result
    evaluation = best_lines.get(1, {}).get("score", 0.0)
    result_lines = []
    for pv_num in sorted(best_lines.keys()):
        entry = best_lines[pv_num]
        line = {
            "pv": entry.get("pv", ""),
            "score": entry.get("score", 0.0),
            "depth": entry.get("depth", 0),
        }
        if "mate_in" in entry:
            line["mate_in"] = entry["mate_in"]
        result_lines.append(line)

    result = {
        "evaluation": evaluation,
        "best_move": best_move,
        "lines": result_lines,
    }
    # Stopped by the time cap short of the requested depth (a found mate also
    # ends early, but then the line is already decided).
    reached = result_lines[0]["depth"] if result_lines else 0
    capped = MAX_MS > 0 if capped is None else capped
    if not movetime_ms and capped and reached < depth and "mate_in" not in (result_lines[0] if result_lines else {}):
        result["time_capped"] = True
    return result


# Results shared by the analyze_position tool and the voice [Engine] line
# (src/voice_engine_note.py): the board is usually analysed the moment it
# changes, so the model's own call for the same position is answered from here.
_CACHE_MAX = 256
# With the pool (plan 31.10 P7a) the game evaluations, the review scan and the positions analysed in advance share
# this cache too: a 40-move game alone is 41 positions. An entry is a few hundred bytes.
_CACHE_MAX_POOL = 4096
# Position (clocks ignored) → the deepest analysis of it so far.
_cache: "OrderedDict[str, dict]" = OrderedDict()
_cache_lock = threading.Lock()


def clear_analysis_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _result_depth(result: dict) -> int:
    lines = result.get("lines") or []
    return int(lines[0].get("depth") or 0) if lines else 0


def _cache_key(fen: str, searchmoves=()) -> str:
    """Position (clocks ignored), and the moves a restricted search looked at: a search of the queen's moves only is
    never an answer for the whole position, nor the other way round (plan 31.10)."""
    key = " ".join(fen.split()[:4])
    sm = _searchmoves(searchmoves)
    return f"{key} searchmoves {' '.join(sm)}" if sm else key


def _cache_get(fen: str, depth: int, multipv: int, searchmoves=()) -> dict | None:
    """A cached analysis at least *depth* deep with at least *multipv* lines."""
    key = _cache_key(fen, searchmoves)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None or len(hit.get("lines", [])) < multipv:
            return None
        # A run the time cap stopped is as deep as this host gets in the budget;
        # searching again would spend the same seconds for the same answer.
        if _result_depth(hit) < depth and not hit.get("time_capped"):
            return None
        _cache.move_to_end(key)
        return {**hit, "lines": hit["lines"][:multipv]}


def _cache_put(fen: str, result: dict, searchmoves=()) -> None:
    """Keep *result* unless the cache already holds a deeper (or as deep and wider) run."""
    if "error" in result or not result.get("lines") or result.get("stopped"):
        return
    key = _cache_key(fen, searchmoves)
    with _cache_lock:
        old = _cache.get(key)
        if old is None or (_result_depth(result), len(result["lines"])) >= (_result_depth(old), len(old["lines"])):
            _cache[key] = result
        _cache.move_to_end(key)
        limit = _CACHE_MAX_POOL if pool_on() else _CACHE_MAX
        while len(_cache) > limit:
            _cache.popitem(last=False)


# ── the exact store (plan 31.10 P7a, speed §3.2) ─────────────────────────────────────────────────────────────────
# A search to a fixed depth that starts from an empty hash (a new process, or a pool process after `ucinewgame`)
# gives the same lines every time. Those results, and only those, are kept here by (position, depth, lines,
# restricted moves): the forced-reply confirm reads this store and no other, so the same sentence gets the same
# verdict in text and voice and in later turns — never a timed look that happened to reach the depth (trap-legal:
# 0.72 from the cache against 0.50 searched to depth 17, merge 30.10).
_EXACT_MAX = 2048
_exact: "OrderedDict[tuple, dict]" = OrderedDict()


def _exact_key(fen: str, depth: int, multipv: int, searchmoves=()) -> tuple:
    return (" ".join(fen.split()[:4]), int(depth), int(multipv), _searchmoves(searchmoves))


def _complete(result: dict, depth: int) -> bool:
    """Every line reached *depth* (or found a mate): the search ended at the depth, not at a time cap."""
    lines = result.get("lines") or []
    if "error" in result or result.get("time_capped") or result.get("remote") or not lines:
        return False
    return all(int(ln.get("depth") or 0) >= depth or ln.get("mate_in") is not None for ln in lines)


def _exact_put(fen: str, depth: int, multipv: int, searchmoves, movetime_ms, result: dict) -> None:
    if movetime_ms or not pool_on() or not _complete(result, depth):
        return
    key = _exact_key(fen, depth, multipv, searchmoves)
    with _cache_lock:
        _exact[key] = result
        _exact.move_to_end(key)
        while len(_exact) > _EXACT_MAX:
            _exact.popitem(last=False)


def exact_get(fen: str, depth: int, multipv: int, searchmoves=()) -> dict | None:
    """The exact result for (position, depth, lines), or None."""
    from src.fen_repair import repair_fen

    key = _exact_key(repair_fen(fen), depth, multipv, searchmoves)
    with _cache_lock:
        hit = _exact.get(key)
        if hit is not None:
            _exact.move_to_end(key)
        return hit


def analyze_exact(fen: str, depth: int, multipv: int, *, max_ms: int | None = None,
                  searchmoves: tuple | list | None = None) -> dict:
    """A search to *depth* with *multipv* lines from an empty hash — the same lines on every run.

    Served only from the exact store (never from a timed look or a search that kept its hash). A search bounded by
    *max_ms* that stops short of the depth is returned as it is (its lines say so) and is not kept."""
    sm = _searchmoves(searchmoves)
    hit = exact_get(fen, depth, multipv, sm) if pool_on() else None  # STOCKFISH_POOL=0: a search every time, as before
    if hit is not None:
        return hit
    # A search that judges: bounded by the caller's deadline, else by EXACT_MAX_MS — never by the analysis cap.
    kwargs = {"max_ms": max_ms} if max_ms else {"cap_ms": EXACT_MAX_MS}
    if sm:
        kwargs["searchmoves"] = sm
    return analyze_position(fen, depth=depth, multipv=multipv, **kwargs)  # kept in the store when complete


# Depth searches at work, by exact key: the forced-reply confirm joins one of the same position, depth and lines
# (the precompute's, src/engine_precompute.py; the voice check of a sentence the text check is confirming) rather
# than searching beside it — and gets the same complete result the store will keep.
_exact_flights: dict = {}


def _exact_begin(fen: str, depth: int, multipv: int, sm: tuple, budget_s: float | None = None):
    from src import engine_pool

    key = _exact_key(fen, depth, multipv, sm)
    with _inflight_lock:
        if key in _exact_flights:
            return None  # one at work already: this one runs beside it and is not the one joined
        prio = engine_pool.current_priority()
        background = prio >= engine_pool.PRIORITY_BACKGROUND
        flight = _Flight(multipv, None, engine_pool.Job("exact flight", parent=engine_pool.current_job())
                         if background else None, base=prio, budget_s=budget_s)
        _exact_flights[key] = flight
        return flight


def _exact_end(fen: str, depth: int, multipv: int, sm: tuple, flight, result: dict) -> None:
    key = _exact_key(fen, depth, multipv, sm)
    flight.result = result
    flight.event.set()
    with _inflight_lock:
        if _exact_flights.get(key) is flight:
            _exact_flights.pop(key, None)


def exact_join(fen: str, depth: int, multipv: int, wait_s: float, searchmoves=()) -> dict | None:
    """The complete result of a search to *depth* of this position already at work, waited for up to *wait_s*
    (the search is promoted to the caller's priority meanwhile); None when none is at work, it did not complete in
    time, or it is bounded tighter than the caller's own search would be.

    Verify 06.11: a search joined is one that can do at least what the caller's own search could — its own time
    bound (*budget_s*: its caller's deadline, or its cap) no shorter than *wait_s*; it started earlier from the same
    empty hash, so it then completes no later. A tighter one (the model's analyze_position call at the check's depth
    and lines, capped at STOCKFISH_MAX_MS; another check's search with less time) is not waited for: on a slow host it
    stops short, and the check, having waited for it, had too little time left for its own search (V-eng-02)."""
    from src import engine_pool
    from src.fen_repair import repair_fen

    if not pool_on() or wait_s <= 0:
        return None
    key = _exact_key(repair_fen(fen), depth, multipv, searchmoves)
    with _inflight_lock:
        flight = _exact_flights.get(key)
    if flight is None:
        return None
    if flight.budget_s is not None and flight.budget_s + _MERGE_SLACK_S < wait_s:
        return None  # runs beside it: the caller's own search has more time than this one
    if not _join_wait(flight, engine_pool.current_priority(), wait_s):
        return None
    res = flight.result or {}
    return res if _complete(res, depth) else None


def clear_exact_store() -> None:
    with _cache_lock:
        _exact.clear()


# ── one search per position at a time (plan 31.10 P7a) ──────────────────────────────────────────────────────────
# The site's prewarm (depth 16) and the turn's engine line (1500 ms) of the same board, or the voice and the text
# check of the same move, used to run side by side on a 2-vCPU host. A request now waits for a search of the same
# position already at work when that one ends no later than its own would and has as many lines; its result then
# serves the request by the cache's own rule, or the request searches after all.
_inflight: dict = {}
_inflight_lock = threading.Lock()
_MERGE_SLACK_S = 0.15


class _Flight:
    __slots__ = ("multipv", "ends_by", "event", "result", "job", "base", "budget_s", "joiners")

    def __init__(self, multipv: int, ends_by: float | None, job=None, base: int | None = None,
                 budget_s: float | None = None):
        self.multipv, self.ends_by, self.job = multipv, ends_by, job
        self.base = base          # the priority it runs at of its own (what a joiner that gives up restores)
        self.budget_s = budget_s  # its own time bound (exact flights), None = none
        self.joiners: list = []   # the priorities of the requests waiting for it now
        self.event = threading.Event()
        self.result: dict | None = None


def _join_wait(flight: _Flight, prio: int | None, wait: float | None) -> bool:
    """Wait for *flight* up to *wait*; it is promoted to *prio* (None: not promoted) while this request waits.

    A request that gives up undoes its promotion (verify 06.11): the search runs at its own priority again, or at the
    highest of the requests still waiting — a background search no answer waits for any more may be stopped by one."""
    from src import engine_pool

    if flight.job is None or prio is None:
        return flight.event.wait(wait)
    with _inflight_lock:
        flight.joiners.append(prio)
        engine_pool.promote(flight.job, prio)
    done = flight.event.wait(wait)
    with _inflight_lock:
        flight.joiners.remove(prio)
        if not done and not flight.event.is_set():
            base = engine_pool.PRIORITY_BACKGROUND if flight.base is None else flight.base
            engine_pool.demote(flight.job, base)
            if flight.joiners:
                engine_pool.promote(flight.job, min(flight.joiners))
    return done


def _satisfies(result: dict | None, depth: int, multipv: int) -> bool:
    """The cache's rule (_cache_get) for a result in hand."""
    if not result or "error" in result or len(result.get("lines") or []) < multipv:
        return False
    return _result_depth(result) >= depth or bool(result.get("time_capped"))


def _merged(fen: str, sm: tuple, need_depth: int, multipv: int, own_s: float | None, run) -> dict:
    """*run()* unless a search of this position at work already answers the request (pool only).

    A search the precompute started (src/engine_precompute.py) is joined too: it is then promoted to the joiner's
    priority, so it is no longer stopped for an answer — the turn that asks for the line the background is computing
    waits for that search instead of starting a second one beside it."""
    from src import engine_pool

    if not pool_on():
        return run()
    key = _cache_key(fen, sm)
    now = time.monotonic()
    own_end = now + own_s if own_s else None
    prio = engine_pool.current_priority()
    background = prio >= engine_pool.PRIORITY_BACKGROUND
    with _inflight_lock:
        flights = _inflight.get(key) or []
        join = next((f for f in flights if f.multipv >= multipv and (
            own_end is None or (f.ends_by is not None and f.ends_by <= own_end + _MERGE_SLACK_S))), None)
        mine = None
        if join is None:
            # A background search gets a job of its own (a child of the precompute's), so promoting it raises this
            # search alone, even before it has reached the pool's queue.
            mine = _Flight(multipv, own_end, engine_pool.Job("flight", parent=engine_pool.current_job())
                           if background else None, base=prio)
            _inflight.setdefault(key, []).append(mine)
    if join is not None:
        wait = None if join.ends_by is None else max(0.0, join.ends_by - time.monotonic()) + _MERGE_SLACK_S
        promote = join.job is not None and not background
        if promote:
            # Promoted, the search runs at this request's priority and started before it: it ends about when a
            # search of its own would, even after the queue it met (replay 31.10: a wait cut at its estimated end,
            # then a search of its own, cost three turns their engine line). Twice its own time at most.
            wait = 2 * (own_s or MAX_MS / 1000.0 or 3.0) + 0.3
        if _join_wait(join, prio if promote else None, wait) and _satisfies(join.result, need_depth, multipv):
            res = join.result
            return {**res, "lines": res["lines"][:multipv]}
        return run()
    try:
        if mine.job is not None:
            with engine_pool.priority(prio, mine.job):
                res = run()
        else:
            res = run()
        mine.result = res
        return res
    finally:
        mine.event.set()
        with _inflight_lock:
            flights = _inflight.get(key) or []
            if mine in flights:
                flights.remove(mine)
            if not flights:
                _inflight.pop(key, None)


def analyze_cached(fen: str, depth: int = DEFAULT_DEPTH, multipv: int = DEFAULT_MULTIPV,
                   searchmoves: tuple | list | None = None) -> dict:
    """analyze_position behind a small LRU keyed by position (clocks ignored) and *searchmoves*.

    A cached run at least as deep, with at least as many lines, serves the
    request. Errors are never cached.
    """
    sm = _searchmoves(searchmoves)
    hit = _cache_get(fen, depth, multipv, sm)
    if hit is not None:
        return hit

    def _run():
        hit2 = _cache_get(fen, depth, multipv, sm)  # a search that ended while this one looked
        if hit2 is not None:
            return hit2
        if sm:
            res = analyze_position(fen, depth=depth, multipv=multipv, searchmoves=sm)
        else:
            res = analyze_position(fen, depth=depth, multipv=multipv)
        _cache_put(fen, res, sm)
        return res

    if not pool_on():
        return _run()
    return _merged(fen, sm, depth, multipv, (MAX_MS / 1000.0) if MAX_MS > 0 else None, _run)


def analyze_timed(fen: str, movetime_ms: int, multipv: int = DEFAULT_MULTIPV, min_depth: int = 12,
                  searchmoves: tuple | list | None = None) -> dict:
    """Analysis bounded by time rather than depth, through the same cache.

    Depth then follows the host's speed and the result is ready on time — the
    text turn waits for it. A cached run at least *min_depth* deep serves it.
    *searchmoves* (UCI): only these moves are searched, cached under their own key (plan 31.10, P4's «решает ферзь»).
    """
    sm = _searchmoves(searchmoves)
    hit = _cache_get(fen, min_depth, multipv, sm)
    if hit is not None:
        return hit

    def _run():
        hit2 = _cache_get(fen, min_depth, multipv, sm)
        if hit2 is not None:
            return hit2
        if sm:
            res = analyze_position(fen, multipv=multipv, movetime_ms=movetime_ms, searchmoves=sm)
        else:
            res = analyze_position(fen, multipv=multipv, movetime_ms=movetime_ms)
        _cache_put(fen, res, sm)
        return res

    if not pool_on():
        return _run()
    return _merged(fen, sm, min_depth, multipv, movetime_ms / 1000.0, _run)


def _bounded_int(value, default: int, low: int, high: int) -> int:
    """Model-supplied int arg clamped to [low, high]; junk falls back to default."""
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _live_game_turn(fen: str, kwargs: dict) -> str | None:
    """See game_mode.game_turn: the session's shown game, its live position or one move on."""
    sid = kwargs.get("session_id")
    if not sid:
        return None
    from src.session_persistence import SessionLoadError

    try:
        from src.game_mode import game_turn
        from src.sessions import session_store

        return game_turn(session_store.get(sid, kwargs.get("user_id")), fen)
    except SessionLoadError:
        raise  # a game we could not load must not get Stockfish's best line (28.10)
    except Exception:  # noqa: BLE001 — the guard never breaks the analysis
        return None


def _handle_analyze_position(args: dict, **kwargs) -> str:
    from src import engine_pool

    with engine_pool.priority(engine_pool.PRIORITY_TOOL):  # the model's call waits behind checks and lines
        result = analyze_cached(
            fen=args.get("fen", ""),
            depth=_bounded_int(args.get("depth"), DEFAULT_DEPTH, 1, MAX_DEPTH),
            multipv=_bounded_int(args.get("multipv"), DEFAULT_MULTIPV, 1, MAX_MULTIPV),
        )
    # In a game the engine plays the coach's moves at the game's strength, not Stockfish's best: a line from here
    # handed the coach a reply to announce as its own while the engine played another (Alexander 27.10). The live
    # position keeps only the student's candidate moves; the position after the student's move keeps no move at all.
    turn = _live_game_turn(args.get("fen", ""), kwargs) if isinstance(result, dict) and result.get("lines") else None
    if turn:
        result = dict(result)
        if turn == "live":
            result["lines"] = [{**ln, "pv": ((ln.get("pv") or "").split() or [""])[0]} for ln in result["lines"]]
        else:
            result["lines"] = [{k: v for k, v in ln.items() if k != "pv"} for ln in result["lines"][:1]]
            result.pop("best_move", None)
        from src.game_mode import GAME_TOOL_NOTE

        result["game_note"] = GAME_TOOL_NOTE
    return json.dumps(result, indent=2)


registry.register(
    name="analyze_position",
    toolset="chess",
    schema=ANALYZE_SCHEMA,
    handler=_handle_analyze_position,
    description="Analyze a chess position with Stockfish engine.",
    emoji="🔬",
)
