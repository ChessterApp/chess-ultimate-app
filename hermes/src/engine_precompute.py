"""The board's positions analysed while the student thinks (plan 31.10 P7b, next1031/speed §3.3).

The coach's first word waited for the engine line (median 1.72 s in the replay), a question in a live game for its
note (1.34 s), a game review for its scan (1.9 s for 40 plies, 13.5 s for the whole `game-load` turn of 29.10 with
the model's own depth-16 call on the final position). Each of those positions is known the moment the board
changes. Here every board save (src/sessions.on_board_change) starts a job that searches them in the background
of the engine pool (src/engine_pool.PRIORITY_BACKGROUND: one process at most, stopped the moment an answer needs
it), with exactly the requests the turn will make, so the turn reads the analysis cache:

  live game, the student to move   the text turn's live-game note (its search and the threat search), then the
                                   depth-12 eval the student's next move is annotated against
  finished or loaded game          every move at depth 12 in order (the review scan), the final position's engine
                                   lines (as above: the review turn's line and the tool's depth 16), and the
                                   positions before the biggest moments as the tool asks them (depth 16, 3 lines)
  any other position               the text turn's engine line with its two threat searches, then depth 16 with
                                   3 lines (the site's prewarm, the voice note, the analyze_position tool)
  after a turn's engine line       the positions after the moves a coach recommends here (the line's top moves, the
                                   book's, castling, checks, captures, pawn moves), as the answer check's
                                   recommended-move check asks them (COACH_MOVE_VERIFY_MOVETIME_MS); the forced-reply
                                   confirm after the best move and the captures and checks among them; then every
                                   other legal move, further back
  the student's idea moves         the forced-reply confirm of the positions after them, ahead of the candidates

Each board has a change counter: a new save cancels the board's old job (its waiting searches are dropped, a running
one is stopped); the jobs for a turn's answer check are replaced by the next turn's. Nothing new reaches the model: a cached line is what a search at the turn would have found, and the
guards that keep a live game's best move from the coach act when a result is read, not when it is computed.
``COACH_PRECOMPUTE=0`` (or ``STOCKFISH_POOL=0``) switches it off.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from collections import OrderedDict
from typing import Callable, Optional

import chess
import chess.pgn

from src import engine_pool

logger = logging.getLogger(__name__)

# Positions before the biggest moments of a review analysed as the tool asks for them.
REVIEW_MOMENTS = 3
# The positions after the engine line's top moves the answer check is likely to ask about.
LINE_TOP_MOVES = 3
# How long the line step waits for its threat search beside it.
THREAT_WAIT_S = 5.0
# A stopped background search is asked again after this pause (the answer that needed the process goes first).
RETRY_PAUSE_S = 0.05
MAX_RETRIES = 50

_lock = threading.Condition()
_pending: "OrderedDict[str, _Task]" = OrderedDict()
_gen: dict = {}
_running: dict = {}  # key → [the job at work, its steps at work]
STATS = {"jobs": 0, "steps": 0, "cancelled": 0, "failed": 0}


# The background's own order (src/engine_pool: any priority from PRIORITY_BACKGROUND on is background, a smaller
# number first, and a waiting search stops a running one further back):
LEVEL_CHECK = engine_pool.PRIORITY_BACKGROUND        # the positions the turn's recommended-move check will ask for
LEVEL_CONFIRM = engine_pool.PRIORITY_BACKGROUND + 1  # the forced-reply check's confirming searches
LEVEL_BOARD = engine_pool.PRIORITY_BACKGROUND + 2    # a board's own positions


class _Task:
    __slots__ = ("key", "job", "steps", "gen", "queued_at", "level", "busy")

    def __init__(self, key: str, job: engine_pool.Job, steps: list, gen: int, level: int = LEVEL_BOARD):
        self.key, self.job, self.steps, self.gen = key, job, steps, gen
        self.queued_at = time.monotonic()
        self.level = level
        self.busy = 0  # steps at work (a short step may run beside another of its task: PARALLEL_STEPS)


def enabled() -> bool:
    """COACH_PRECOMPUTE and the pool on, and the local engine in use: with ENGINE_API_URL set the searches go to the
    site's engine server, which must not get the background's searches on top of the turns' (the team's call)."""
    try:
        from src import config
        from src.tools import stockfish

        return bool(config.COACH_PRECOMPUTE) and stockfish.pool_on() and not stockfish.ENGINE_API_URL
    except Exception:  # noqa: BLE001
        return False


# ── what to compute ──────────────────────────────────────────────────────────────────────────────────────────────
def _note_movetime() -> int:
    from src import config

    return config.COACH_ENGINE_NOTE_MOVETIME_MS


def _live_movetime() -> int:
    # The text turn's live-game note: half the engine line's time (src/server.coach_chat).
    return max(200, _note_movetime() // 2)


def _null_fen(board: chess.Board) -> Optional[str]:
    """The position with the side to move passing (the threat search's position), as position_facts._threat builds
    it; None when it cannot pass."""
    if board.is_check():
        return None
    null = board.copy(stack=False)
    null.push(chess.Move.null())
    if null.is_check() or not null.is_valid():
        return None
    return null.fen()


def _threat(fen: Optional[str]):
    from src.position_facts import THREAT_MOVETIME_MS
    from src.tools.stockfish import analyze_timed

    if not fen:
        return {}
    return analyze_timed(fen, THREAT_MOVETIME_MS, multipv=1, min_depth=10)


def _line_steps(fen: str) -> list:
    """The engine line of a position, as each consumer asks it: the text turn's (src/voice_engine_note.engine_note
    for COACH_ENGINE_NOTE_MOVETIME_MS, 3 lines) with its two threat searches (the opponent's threat now, and after the
    best move), then depth 16 with 3 lines — the site's prewarm, the voice note and the analyze_position tool (served
    by the timed search already when that one went as deep)."""
    from src.tools.stockfish import DEFAULT_DEPTH, DEFAULT_MULTIPV, analyze_cached, analyze_timed

    board = chess.Board(fen)

    def _text_line():
        return analyze_timed(fen, _note_movetime(), multipv=DEFAULT_MULTIPV)

    def _line_with_threats():
        # The line with both threat searches beside it, as the turn's engine_note runs them: the threat now on the
        # second process from the start (a short background search may take it while no answer waits), the threat
        # after the best move from the line's best move so far — all three end with the line, ~1.5 s after the save
        # instead of 2.1 s (review-wiring 01.11). The steps after it read them from the cache (or search again what
        # an answer stopped).
        from src.voice_engine_note import _at_caller_priority, _threat_pool, line_search

        now = _null_fen(board)
        side = _threat_pool.submit(_at_caller_priority(_threat), now) if now else None
        try:
            return line_search(board, fen, _note_movetime(), speculate=True)
        finally:
            if side is not None:
                try:
                    side.result(timeout=THREAT_WAIT_S)
                except Exception:  # noqa: BLE001 — the step after it asks again
                    pass

    def _after_best():
        res = _text_line()  # in the cache by now: the line the turn will read, and its best move
        if "error" in res or not res.get("lines"):
            return res
        try:
            best = chess.Move.from_uci((res["lines"][0].get("pv") or "").split()[0])
        except (IndexError, ValueError):
            return {}
        if best not in board.legal_moves:
            return {}
        after = board.copy(stack=False)
        after.push(best)
        return _threat(_null_fen(after))

    return [("line", _line_with_threats),
            ("threat", lambda: _threat(_null_fen(board))),
            ("threat_after_best", _after_best),
            ("line_depth", lambda: analyze_cached(fen, depth=DEFAULT_DEPTH, multipv=DEFAULT_MULTIPV))]


def _live_steps(fen: str) -> list:
    """A live game with the student to move: the text turn's live-game note (src/hypothetical.live_game_note: its
    search and the threat search), then the eval the student's next move is annotated against."""
    from src.game_engine import EVAL_DEPTH
    from src.hypothetical import MIN_DEPTH
    from src.tools.stockfish import analyze_exact, analyze_timed

    board = chess.Board(fen)

    def _candidates():
        # The coach's hint in a game names a move too: the check's positions after the likely ones.
        res = analyze_timed(fen, _live_movetime(), multipv=1, min_depth=MIN_DEPTH)
        best = []
        try:
            move = chess.Move.from_uci(((res.get("lines") or [{}])[0].get("pv") or "").split()[0])
            if move in board.legal_moves:
                best = [{"moves": [board.san(move)]}]
        except (IndexError, ValueError):
            pass
        steps, confirm = _after_move_steps(board, {"lines": best})
        return steps + confirm

    return [("live_note", lambda: analyze_timed(fen, _live_movetime(), multipv=1, min_depth=MIN_DEPTH)),
            ("threat", lambda: _threat(_null_fen(board))),
            ("eval", lambda: analyze_exact(fen, EVAL_DEPTH, 1)),
            ("plan", _candidates)]


def _game_positions(pgn: str) -> Optional[list]:
    try:
        game = chess.pgn.read_game(io.StringIO(pgn or ""))
    except Exception:  # noqa: BLE001
        return None
    if game is None:
        return None
    board = game.board()
    out = [board.copy(stack=False)]
    for move in game.mainline_moves():
        board.push(move)
        out.append(board.copy(stack=False))
    return out if len(out) > 1 else None


def _review_steps(pgn: str) -> list:
    """A game's review: the scan of every move, the final position as the tool asks, the biggest moments."""
    from src.tools.stockfish import DEFAULT_DEPTH, DEFAULT_MULTIPV, analyze_cached

    positions = _game_positions(pgn)
    if not positions:
        return []

    def _scan():
        from src.tools.critical_moments import _scan_pooled

        return _scan_pooled(positions, halves=1)  # in game order, the hash kept from move to move

    final = positions[-1]
    steps = [("scan", _scan)]
    if not final.is_game_over():
        steps += _line_steps(final.fen())

    def _moments():
        from src.tools.critical_moments import find_critical_moments

        found = find_critical_moments(pgn)  # every position is in the cache now: no search
        for m in (found.get("critical_moments") or [])[:REVIEW_MOMENTS]:
            fen = m.get("fen_before")
            if fen:
                analyze_cached(fen, depth=DEFAULT_DEPTH, multipv=DEFAULT_MULTIPV)
        return found

    steps.append(("moments", _moments))
    return steps


def _plan(kind: str, fen: str, pgn: str, state: Optional[dict]) -> list:
    try:
        board = chess.Board(fen)
    except (ValueError, TypeError):
        return []
    if not board.is_valid():
        return []
    if kind == "game" and state:
        if state.get("status") == "playing":
            student = chess.WHITE if state.get("student_color") == "white" else chess.BLACK
            if board.turn == student and not board.is_game_over():
                return _live_steps(fen)
            return []  # the engine's reply is on its way: the next save is the student's position
        return _review_steps(pgn) if pgn else []
    if pgn and kind in ("game", "master_game"):
        steps = _review_steps(pgn)
        # The position shown, when it is not the final one: its engine line goes first.
        positions = _game_positions(pgn)
        if positions and positions[-1].board_fen() != board.board_fen() and not board.is_game_over():
            steps = _line_steps(fen) + steps
        return steps
    if board.is_game_over():
        return []
    return _line_steps(fen)


# ── the job queue ────────────────────────────────────────────────────────────────────────────────────────────────
# Tasks run one step at a time: a step is one position's searches. Tasks go by level (LEVEL_CHECK, LEVEL_CONFIRM,
# LEVEL_BOARD), the level is the steps' priority in the pool, and a waiting step stops a running one further back
# (the board's 3 s depth-16 search gives way to the positions the check is about to ask for). Two workers take
# steps, so a step the turn joined (and promoted, src/tools/stockfish._merged) does not hold the rest back. The pool
# still runs at most one background search at a time (src/engine_pool.MAX_BACKGROUND).
WORKERS = 2


def _submit(key: str, steps: list, label: str, replace: bool = True,
            level: int = LEVEL_BOARD) -> Optional[engine_pool.Job]:
    if not steps:
        return None
    with _lock:
        if replace:
            _cancel_locked(key)
        gen = _gen.get(key, 0)
        job = engine_pool.Job(label)
        task = _Task(key, job, list(steps), gen, level)
        _pending[key] = task
        _pending.move_to_end(key)
        STATS["jobs"] += 1
        _ensure_workers()
        _lock.notify_all()
    return job


def _cancel_locked(key: str) -> None:
    _gen[key] = _gen.get(key, 0) + 1
    old = _pending.pop(key, None)
    if old is not None:
        old.job.cancelled = True
        STATS["cancelled"] += 1
        engine_pool.cancel(old.job)  # its step at work, if any, is stopped


_workers: list = []


def _ensure_workers() -> None:
    global _workers
    _workers = [w for w in _workers if w.is_alive()]
    while len(_workers) < WORKERS:
        th = threading.Thread(target=_work, daemon=True, name=f"engine-precompute-{len(_workers) + 1}")
        th.start()
        _workers.append(th)


# Work nobody will read any more is dropped: a turn's check positions after CHECK_TTL_S (the answer is checked by
# then), a board's own positions after BOARD_TTL_S, and the oldest tasks beyond MAX_TASKS (many students at once).
CHECK_TTL_S = 30.0
BOARD_TTL_S = 120.0
MAX_TASKS = 24


def _expire_locked() -> None:
    now = time.monotonic()
    for key, task in list(_pending.items()):
        ttl = BOARD_TTL_S if task.level >= LEVEL_BOARD else CHECK_TTL_S
        if not task.busy and now - task.queued_at > ttl:
            _pending.pop(key, None)
            task.job.cancelled = True
            STATS["expired"] = STATS.get("expired", 0) + 1
    idle = [t for t in _pending.values() if not t.busy]
    for task in sorted(idle, key=lambda t: (-t.level, t.queued_at))[:max(0, len(_pending) - MAX_TASKS)]:
        _pending.pop(task.key, None)
        task.job.cancelled = True
        STATS["expired"] = STATS.get("expired", 0) + 1


# Steps that are one short search each (the position after a candidate move, 300 ms) run two of a task at a time:
# the pool lets a short background search take the second process while no answer waits (src/engine_pool), so the
# candidates are covered twice as fast in the time the model takes to answer (review-wiring 01.11).
PARALLEL_STEPS = ("after_move",)


def _startable(task: "_Task") -> bool:
    if not task.steps:
        return False
    if not task.busy:
        return True
    return task.busy < WORKERS and task.steps[0][0] in PARALLEL_STEPS


def _next_locked():
    """The next step to run: the lowest level first, then the oldest task; one step of a task at a time (two short
    ones). A step is not started while a task of a lower level still has steps: its next step would only stop this
    one."""
    _expire_locked()
    best = None
    ahead = min((t.level for t in _pending.values() if t.steps or t.busy), default=None)
    for key, task in _pending.items():
        if not _startable(task):
            continue
        if best is None or task.level < best.level:
            best = task
    if best is not None and ahead is not None and best.level > ahead:
        return None
    return best


def _work() -> None:
    while True:
        with _lock:
            task = _next_locked()
            while task is None:
                _lock.wait(30.0)
                task = _next_locked()
            task.busy += 1
            name, step = task.steps.pop(0)
            run = _running.get(task.key)
            if run is not None and run[0] is task.job:
                run[1] += 1
            else:
                _running[task.key] = [task.job, 1]
        try:
            more = _run_step(task, name, step)
        except Exception:  # noqa: BLE001 — background work never surfaces
            STATS["failed"] += 1
            logger.debug("precompute step failed", exc_info=True)
            more = None
        finally:
            with _lock:
                task.busy -= 1
                if more:
                    task.steps[:0] = more  # a plan's steps, right where the plan was
                run = _running.get(task.key)
                if run is not None and run[0] is task.job:
                    run[1] -= 1
                    if run[1] <= 0:
                        _running.pop(task.key, None)
                if (task.job.cancelled or (not task.steps and not task.busy)) and _pending.get(task.key) is task:
                    _pending.pop(task.key, None)
                _lock.notify_all()


def _run_step(task: _Task, name: str, step: Callable):
    """Run one step in the background of the pool; a step a waiting answer stopped is asked again. A plan step
    returns the steps it planned."""
    with engine_pool.priority(task.level, task.job):
        for _ in range(MAX_RETRIES):
            if task.job.cancelled:
                return None
            result = step()
            if name == "plan":
                return result
            if not _was_stopped(result) or task.job.cancelled:
                break
            time.sleep(RETRY_PAUSE_S)  # stopped for an answer: ask again once it has the process
        STATS["steps"] += 1
    return None


def _was_stopped(result) -> bool:
    """A step whose search a waiting answer stopped (its result was dropped): it is asked again."""
    if result is None:
        return True  # the scan gave nothing: one of its searches was stopped
    if isinstance(result, dict):
        err = str(result.get("error") or "")
        return "preempted" in err
    return False


# ── the entry points ─────────────────────────────────────────────────────────────────────────────────────────────
def board_changed(session, board) -> None:
    """src/sessions listener: a board was saved — analyse its new position in the background."""
    if not enabled():
        return
    try:
        key = f"{getattr(session, 'id', '')}/{board.id}"
        state = board.game_state
        snap_state = dict(state) if isinstance(state, dict) else None
        if snap_state is not None and isinstance(snap_state.get("moves"), list):
            snap_state["moves"] = list(snap_state["moves"])
        kind, fen, pgn = board.kind, board.fen, board.pgn or ""
    except Exception:  # noqa: BLE001
        return
    # The jobs for the turn's answer check (#line, #ideas) stay: the check judges the board the turn began on,
    # whatever the coach's tools put up meanwhile; the next turn's line replaces them.
    with _lock:
        _cancel_locked(key)
        _cancel_locked(key + "#rest")  # the old board's least likely moves: the new board's positions go first
    # The plan reads the PGN: built on a worker thread, never on the request's.
    _submit(key, [("plan", lambda: _plan(kind, fen, pgn, snap_state))], f"board {key}", replace=False)


# How many positions after candidate moves are analysed for the recommended-move check per engine line, first (the
# rest of the legal moves follow further back, LEVEL_BOARD: a coach recommends a quiet developing move too — Qe2,
# Nf6, Be2 were checked at the turn in the replay of 01.11, 300 ms each).
CANDIDATE_MOVES = 12
# The positions after the best move and after the likely captures and checks among the candidates get the
# forced-reply check's confirming search («после Nxe5 чёрные обязаны ответить dxe5»: trap-legal held its sentence
# 1.4 s for it in the replay of 01.11).
CONFIRM_MOVES = 4


def _candidate_moves(board: chess.Board, note: dict) -> list:
    """The moves a coach recommends here, most likely first: the engine line's top moves, the ECO book's moves (an
    opening answer recommends «4.d4», «6.Qd2»), castling, checks, captures, then pawn moves (replay 31.10: of the
    recommendations the check searched with the line's top 3 moves alone, d4, Qd2, Nf6, Nd2, O-O, Qxd5+ and h6 were
    none of them)."""
    seen: list = []

    def add(move):
        if move is not None and move in board.legal_moves and move not in seen:
            seen.append(move)

    for line in (note.get("lines") or [])[:LINE_TOP_MOVES]:
        try:
            add(board.parse_san((line.get("moves") or [""])[0]))
        except ValueError:
            pass
    try:
        from src.openings_book import get_book

        for c in get_book().continuations(board):
            try:
                add(board.parse_san(c["san"]))
            except (ValueError, KeyError):
                pass
    except Exception:  # noqa: BLE001 — the book is a bonus
        pass
    legal = list(board.legal_moves)
    for move in legal:
        if board.is_castling(move):
            add(move)
    for move in legal:
        if board.gives_check(move):
            add(move)
    for move in legal:
        if board.is_capture(move):
            add(move)
    for move in legal:
        if board.piece_type_at(move.from_square) == chess.PAWN:
            add(move)  # «играй h6», «c4 и d4»
    return seen[:CANDIDATE_MOVES]


def _other_moves(board: chess.Board, first: list) -> list:
    """The legal moves not among *first*, the likelier first: minor pieces off their first rank, then the queen,
    the rooks, the other minor-piece moves, the king."""
    home = 0 if board.turn == chess.WHITE else 7

    def rank(move):
        piece = board.piece_type_at(move.from_square)
        if piece in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(move.from_square) == home:
            return 0
        return {chess.QUEEN: 1, chess.ROOK: 2, chess.KNIGHT: 3, chess.BISHOP: 3, chess.PAWN: 4}.get(piece, 5)

    return sorted((m for m in board.legal_moves if m not in first), key=lambda m: (rank(m), m.uci()))


def _after_move_steps(board: chess.Board, note: dict, rest: Optional[list] = None) -> tuple:
    """(the positions after the candidate moves, as the recommended-move check asks them; the forced-reply confirm
    of the positions after the best one and after the captures and checks among them). *rest*, when given, gets the
    same step for every other legal move (src/engine_precompute: further back)."""
    from src import config
    from src.hypothetical import MIN_DEPTH
    from src.tools.stockfish import analyze_timed

    movetime = config.COACH_MOVE_VERIFY_MOVETIME_MS

    def step(move):
        after = board.copy(stack=False)
        after.push(move)
        if after.is_game_over():
            return None, None
        f = after.fen()
        return ("after_move", lambda f=f: analyze_timed(f, movetime, multipv=1, min_depth=MIN_DEPTH)), f

    steps, confirm_fens = [], []
    candidates = _candidate_moves(board, note)
    for i, move in enumerate(candidates):
        s, f = step(move)
        if s is None:
            continue
        steps.append(s)
        # «после <лучший ход> чёрные обязаны ответить …», «после Nxe5 … обязаны взять»
        if (i == 0 or board.is_capture(move) or board.gives_check(move)) and len(confirm_fens) < CONFIRM_MOVES:
            confirm_fens.append(f)
    if rest is not None:
        for move in _other_moves(board, candidates):
            s, _ = step(move)
            if s is not None:
                rest.append(s)
    return steps, _confirm_steps(confirm_fens)


def after_engine_line(session_id: str, board_id: str, fen: str, note: Optional[dict]) -> None:
    """A turn's engine line is ready: the positions after the moves a coach recommends here, as the recommended-move
    check asks them, and the forced-reply confirm after the best move (further back: a forced reply is rarer)."""
    if not enabled() or not note or not fen:
        return
    try:
        board = chess.Board(fen)
    except ValueError:
        return
    key = f"{session_id}/{board_id}"

    def _plan():
        rest: list = []
        steps, confirm = _after_move_steps(board, note, rest)
        _submit(key + "#confirm", confirm, f"confirm {fen}", level=LEVEL_CONFIRM)
        _submit(key + "#rest", rest, f"rest {fen}", level=LEVEL_BOARD)
        return steps

    _submit(key + "#line", [("plan", _plan)], f"line {fen}", level=LEVEL_CHECK)


def _confirm_steps(fens: list) -> list:
    """The forced-reply check's confirming search (src/hypothetical: depth FORCED_CONFIRM_DEPTH, 3 lines, from an
    empty hash) of the positions after moves the turn already knows: «после Nxe5 чёрные обязаны ответить dxe5» is then
    judged on the same complete search on every run, not on whether a 1 s search reached the depth under load."""
    from src.hypothetical import FORCED_CONFIRM_DEPTH
    from src.tools.stockfish import analyze_exact

    def _confirm(f):
        res = analyze_exact(f, FORCED_CONFIRM_DEPTH, 3)
        # A complete depth-17 look is also the deepest answer the analysis cache has for the check's timed look
        # (600 ms, 3 lines) of the same position: both stages of the check then read one search.
        if not res.get("error") and not res.get("time_capped"):
            _cache_put(f, res)
        return res

    from src.tools.stockfish import _cache_put

    return [("confirm", lambda f=f: _confirm(f)) for f in fens if f and not chess.Board(f).is_game_over()]


def after_ideas(session_id: str, board_id: str, idea_fens: list) -> None:
    """The student's idea moves were played on the board (src/hypothetical.hypothetical_notes): the positions after
    them get the forced-reply check's confirming search in advance (an answer about the idea names its reply)."""
    if not enabled() or not idea_fens:
        return
    steps = _confirm_steps([f for f in idea_fens[:3] if isinstance(f, str)])
    # At the level of the check's own positions, and ahead of them (older): the student named these moves, so the
    # answer is about them, and a forced-reply confirm costs the held sentence 0.8–1.4 s (a recommended move's check
    # 0.3 s). Further back, the candidates' searches stopped it again and again (replay 01.11, trap-legal: «можно
    # сыграть Nxe5?» — the confirm after 5.Nxe5 was stopped six times and the turn searched it itself, 1.6 s).
    _submit(f"{session_id}/{board_id}#ideas", steps, "ideas", level=LEVEL_CHECK)


def idle(timeout: float = 30.0) -> bool:
    """Wait until no job is queued or at work (tests, benches). True when idle."""
    end = time.monotonic() + timeout
    with _lock:
        while _pending or _running:
            left = end - time.monotonic()
            if left <= 0:
                return False
            _lock.wait(min(left, 0.1))
    return True


def install() -> None:
    """Register the board listener (the server does this once at import)."""
    from src.sessions import on_board_change

    on_board_change(board_changed)
