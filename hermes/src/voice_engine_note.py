"""The voice coach's [Engine] line — Stockfish's top moves for the board, ahead of the question.

Gemini Live has to call analyze_position and wait for it before it can say
anything concrete about the position (voice bench 2026-09-24: ~5 s to the
substantive answer, 7 s of silence on the old model). The browser asks for this
line whenever the board changes and feeds it into the live session, so "what is
the best move here?" is answered from context straight away. The analysis goes
through the same cache as the tool, so a later analyze_position call for this
position is free too.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import chess

from src.fen_repair import repair_fen
from src.position_facts import THREAT_MOVETIME_MS, dynamic_facts, static_facts
from src.tools.stockfish import DEFAULT_DEPTH, DEFAULT_MULTIPV, analyze_cached, analyze_timed

PV_PLIES = 4
MATE_PLIES = 11  # a forced mate up to mate in 6 is written to the end

# Stepping through a game fires one request per move; never run more than a
# couple of engines for it at once (each request is a Stockfish process).
_slots = threading.BoundedSemaphore(2)
# The opponent's-threat search runs beside the main analysis (it does not need
# the best move), so the facts add one short search to the line, not two.
_threat_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="threat")


def _threat_analysis(fen: str) -> dict:
    return analyze_timed(fen, THREAT_MOVETIME_MS, multipv=1, min_depth=10)


def _at_caller_priority(fn, at_least: Optional[int] = None):
    """*fn* to run on another thread at the calling thread's engine-pool priority and job (src/engine_pool): the
    threat searches of a line computed in advance stay background work, those of a held check stay in front.
    *at_least*: no further forward than this level (a guess runs as background work: any answer stops it)."""
    try:
        from src import engine_pool

        level, job = engine_pool.current_priority(), engine_pool.current_job()
        if at_least is not None:
            level = max(level, at_least)
    except Exception:  # noqa: BLE001
        return fn

    def run(*args, **kwargs):
        with engine_pool.priority(level, job):
            return fn(*args, **kwargs)

    return run


def _null_fen_after(board: chess.Board, uci: Optional[str]) -> Optional[str]:
    """The position after *uci* with the other side passing — the position position_facts._threat searches for the
    threat after the best move — or None (illegal, a check or a mate after it, no pass possible)."""
    try:
        move = chess.Move.from_uci(uci or "")
    except ValueError:
        return None
    if move not in board.legal_moves:
        return None
    after = board.copy(stack=False)
    after.push(move)
    if after.is_check() or after.is_game_over():
        return None
    null = after.copy(stack=False)
    null.push(chess.Move.null())
    if null.is_check() or not null.is_valid():
        return None
    return null.fen()


# The threat after the best move needs the best move: it was searched after the line (1.5 s + 0.3 s). On the pool it
# starts from the line's two best moves so far (its first two lines), SPECULATE_MOVES × THREAT_MOVETIME_MS +
# SPECULATE_LEAD_MS before the line ends, on a process no other search wants — the same search
# (src/position_facts._threat, through the analysis cache), so dynamic_facts reads it when the line's final best is
# one of them, and searches it after the line as before when it is not (review-wiring 01.11). Under load (no free
# process, a search waiting) nothing is guessed: the pool's time goes to the turns.
SPECULATE_LEAD_MS = 150
SPECULATE_MIN_DEPTH = 8
SPECULATE_MOVES = 2


class _AfterBestThreat:
    def __init__(self, board: chess.Board, movetime_ms: int):
        self.board = board
        self.best: Optional[str] = None
        self.tops: dict = {}  # multipv → its first move, at the latest depth
        self.fired: Optional[list] = None
        self._lock = threading.Lock()
        self._delay = (movetime_ms - SPECULATE_MOVES * THREAT_MOVETIME_MS - SPECULATE_LEAD_MS) / 1000.0
        from src.engine_pool import PRIORITY_BACKGROUND

        # a guess: background work (an answer that needs the process stops it, and the threat is searched after the
        # line as before); the turn's own search of the same position joins it and promotes it (stockfish._merged)
        self._run = _at_caller_priority(_threat_analysis, at_least=PRIORITY_BACKGROUND)
        self._timer: Optional[threading.Timer] = None
        self._closed = False

    @classmethod
    def start(cls, board: chess.Board, movetime_ms: Optional[int]) -> "Optional[_AfterBestThreat]":
        """A speculator for a timed line on the pool (None otherwise: the process-per-search path stays as it was)."""
        from src.tools.stockfish import pool_on

        if not movetime_ms or movetime_ms < SPECULATE_MOVES * THREAT_MOVETIME_MS + SPECULATE_LEAD_MS + 300 \
                or not pool_on():
            return None
        return cls(board, movetime_ms)

    def on_line(self, line: str) -> None:
        """An output line of the line's search: the best move of the latest depth (the first line, multipv 1). The
        first line starts the clock — the search may have waited for a process."""
        if self._timer is None:
            with self._lock:
                if self._timer is None and not self._closed:
                    self._timer = threading.Timer(max(0.0, self._delay), self.fire)
                    self._timer.daemon = True
                    self._timer.start()
        if not line.startswith("info ") or " pv " not in line:
            return
        parts = line.split()
        try:
            depth = int(parts[parts.index("depth") + 1])
            mpv = int(parts[parts.index("multipv") + 1]) if "multipv" in parts else 1
            move = parts[parts.index("pv") + 1]
        except (ValueError, IndexError):
            return
        if depth >= SPECULATE_MIN_DEPTH and "upperbound" not in parts and "lowerbound" not in parts:
            if mpv == 1:
                self.best = move
            if mpv <= SPECULATE_MOVES:
                self.tops[mpv] = move

    def fire(self) -> None:
        with self._lock:
            if self.fired is not None or self.best is None or self._closed:
                return
            moves = [self.best] + [m for k, m in sorted(self.tops.items()) if m != self.best]
            self.fired = moves[:SPECULATE_MOVES]
        try:
            from src import engine_pool

            if not engine_pool.has_spare():
                return  # every process is wanted: no guessing on a busy pool
        except Exception:  # noqa: BLE001
            return
        for uci in self.fired:
            fen = _null_fen_after(self.board, uci)
            if fen:
                _threat_pool.submit(self._run, fen)

    def done(self) -> None:
        with self._lock:
            self._closed = True
            if self._timer is not None:
                self._timer.cancel()


def _passed_fen(board: chess.Board) -> Optional[str]:
    """The position with the side to move passing, or None when it cannot pass (check)."""
    if board.is_check():
        return None
    passed = board.copy(stack=False)
    passed.push(chess.Move.null())
    return passed.fen() if passed.is_valid() and not passed.is_check() else None


def _san_line(board: chess.Board, pv: str, plies: int = PV_PLIES) -> list[str]:
    """First *plies* moves of a UCI principal variation, in SAN; stops at the first bad move."""
    b = board.copy(stack=False)
    out: list[str] = []
    for uci in pv.split()[:plies]:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in b.legal_moves:
            break
        out.append(b.san(move))
        b.push(move)
    return out


def _white_eval(line: dict, turn: chess.Color) -> str:
    """Line score as White sees it: '+0.35', '-1.20', 'mate in 3 for Black'."""
    sign = 1 if turn == chess.WHITE else -1
    mate = line.get("mate_in")
    if mate is not None:
        winner = "White" if mate * sign > 0 else "Black"
        return f"mate in {abs(mate)} for {winner}"
    return f"{line.get('score', 0.0) * sign:+.2f}"


def _game_over_note(board: chess.Board, fen: str) -> Optional[str]:
    if board.is_checkmate():
        winner = "Black" if board.turn == chess.WHITE else "White"
        return f"[Engine] {fen} — checkmate, {winner} has won."
    if board.is_stalemate():
        return f"[Engine] {fen} — stalemate, the game is a draw."
    if board.is_insufficient_material():
        return f"[Engine] {fen} — insufficient material, the game is a draw."
    return None


def _tablebase_result(board: chess.Board) -> Optional[str]:
    """'draw' / 'White wins' / 'Black wins' from the Lichess tablebase, or None."""
    try:
        from src.board_rules import tablebase, tablebase_white_result

        raw = tablebase(board)
        return tablebase_white_result(board, raw) if raw else None
    except Exception:  # noqa: BLE001 — a bonus on top of the engine
        return None


def line_search(board: chess.Board, fen: str, movetime_ms: int, speculate: bool = True) -> dict:
    """The turn's timed engine line (DEFAULT_MULTIPV lines), with the threat search after its best move started
    beside it on the pool (_AfterBestThreat) when *speculate*."""
    spec = _AfterBestThreat.start(board, movetime_ms) if speculate else None
    if spec is None:
        return analyze_timed(fen, movetime_ms, multipv=DEFAULT_MULTIPV)
    from src.tools.stockfish import progress

    try:
        with progress(spec.on_line):
            return analyze_timed(fen, movetime_ms, multipv=DEFAULT_MULTIPV)
    finally:
        spec.done()


def engine_note(fen: str, depth: int = DEFAULT_DEPTH, movetime_ms: Optional[int] = None,
                explicit_rules: bool = False) -> Optional[dict]:
    """Return {fen, note, best, lines} for a legal position, or None when it cannot be analysed.

    With *movetime_ms* the engine searches for that long instead of to *depth*
    (the text turn waits for the line, so it must be ready on time).
    *explicit_rules*: the coach's own note (voice and text turn) — castling with the squares that decide it and the
    pawn and queen moves of the side to move (src/board_rules.rule_facts, voice 02.11); off for the lesson tutor
    and the hidden board, whose facts stay as they were.
    """
    fen = repair_fen(fen)
    try:
        board = chess.Board(fen)
    except (ValueError, IndexError):
        return None
    if not board.is_valid():
        return None

    over = _game_over_note(board, fen)
    if over:
        return {"fen": fen, "note": over, "best": None, "lines": []}

    # The endgame tablebase (≤ 7 pieces) is exact where Stockfish without
    # tables shows +1.13 for a dead draw (production, 2026-10-06). Asked beside
    # the engine, not before it: in front of the search its ~0.4 s pushed the
    # text turn's note past its wait, and the turn went without any facts
    # (production 2026-10-07: «Да, это выигрыш» on a tablebase draw).
    tb_future = _threat_pool.submit(_tablebase_result, board.copy(stack=False)) if len(board.piece_map()) <= 7 else None

    with_facts = os.environ.get("COACH_ENGINE_FACTS", "1").strip().lower() not in ("0", "false", "no", "off")
    passed_fen = _passed_fen(board) if with_facts else None
    prefetch = _threat_pool.submit(_at_caller_priority(_threat_analysis), passed_fen) if passed_fen else None
    with _slots:
        if movetime_ms:
            result = line_search(board, fen, movetime_ms, speculate=with_facts)
        else:
            result = analyze_cached(fen, depth=depth, multipv=DEFAULT_MULTIPV)
    if "error" in result or not result.get("lines"):
        return None

    lines = []
    for raw in result["lines"]:
        # A forced mate is shown to the end: «Rxh6+ gxh6 dxc5+ Ne5» stopped short of the mate in 3, and the
        # lesson answers made up how it ends (production 07.10: «король уходит на h8», «мат даёт Rh7»).
        mate = raw.get("mate_in")
        plies = min(MATE_PLIES, 2 * abs(mate) - (1 if mate > 0 else 0)) if mate else PV_PLIES
        san = _san_line(board, raw.get("pv", ""), max(PV_PLIES, plies))
        if san:
            lines.append({"moves": san, "eval": _white_eval(raw, board.turn), "depth": raw.get("depth")})
    if not lines:
        return None

    side = "White" if board.turn == chess.WHITE else "Black"
    best = lines[0]
    parts = [
        f"[Engine] {fen} — {side} to move. "
        f"Best: {best['moves'][0]} ({best['eval']}; line {' '.join(best['moves'])})."
    ]
    if len(lines) > 1:
        parts.append("Also: " + ", ".join(f"{ln['moves'][0]} ({ln['eval']})" for ln in lines[1:]) + ".")
    parts.append(f"Evaluations are from White's side, Stockfish depth {best['depth'] or depth}.")
    opening = _opening(fen)
    if opening:
        parts.append(opening)
    book_moves = _book_moves(fen)
    if book_moves:
        parts.append(book_moves)

    # COACH_ENGINE_FACTS=0 leaves the line as moves and evaluations only.
    facts = _facts(board, result["lines"][0], prefetch, lines=result["lines"], explicit=explicit_rules) if with_facts else []
    typed: Optional[list] = None  # None: no line facts collected (COACH_ENGINE_FACTS=0) — the block falls back
    if with_facts:
        # The typed facts this line vets (src/turn_facts, plan 31.10 P8): the safe squares of an attacked piece that
        # start one of these lines, what one more attacker wins. Not in this note (the voice and lesson lines stay as
        # they were): the coach's engine block renders them from this note's "typed_facts" — this turn's own, not
        # the last ones any session collected for the position (review-wiring 01.11).
        from src import turn_facts

        typed = turn_facts.collect(board, result["lines"], kinds=turn_facts.ENGINE_KINDS)
    if facts:
        parts.append("Facts (verified on the board and by the engine): " + "; ".join(facts) + ".")
    if with_facts:
        top_pv = (result["lines"][0].get("pv") or "").split()
        mate = result["lines"][0].get("mate_in")
        try:
            from src.position_facts import explain_line

            told = explain_line(board, top_pv, MATE_PLIES if mate and mate > 0 else PV_PLIES + 1)
        except Exception:  # noqa: BLE001 — the explanation is a bonus on top of the line
            told = None
        if told:
            parts.append(f"The best line, move by move (verified): {told}.")
    mate_in = result["lines"][0].get("mate_in")
    tb = None
    if tb_future is not None:
        try:
            tb = tb_future.result(timeout=0.5)  # the lookup ran during the search; a slow one is left out
        except Exception:  # noqa: BLE001 — a bonus on top of the engine
            tb = None
    return {"fen": fen, "note": " ".join(parts), "best": best["moves"][0], "lines": lines, "facts": facts,
            "tablebase": tb, "mate_in": mate_in, "typed_facts": typed}


def _opening(fen: str) -> Optional[str]:
    """'Opening (ECO book): C60 Ruy Lopez — испанская партия.' when the book names this position."""
    try:
        from src.openings_book import get_book

        found = get_book().by_position(fen)
    except Exception:  # noqa: BLE001 — the name is a bonus on top of the moves
        return None
    if not found:
        return None
    ru = f" — {found['name_ru']}" if found.get("name_ru") else ""
    return f"Opening (ECO book): {found['eco']} {found['name']}{ru}."


def _book_moves(fen: str, limit: int = 5) -> Optional[str]:
    """The book's moves from the position with the variation each one leads to — for «2.c3 — это вариант…» from
    the book, not from memory: on 29.10 (prod check) the coach called 2.c3 «атака в стиле Алёхина» (the Alapin
    Variation). The moves shown are the ones the book works out furthest, but the book names lines and counts no
    games: the Evans Gambit has 51 named sub-lines after 3...Bc5 and 4.d3 five, 2.d4 after 1.c4 Nf6 gathers the
    whole Indian theory by transposition. So the line gives no numbers and no order of popularity, and says so
    (review 30.10: «call only the first one the main move» had the model call the Evans the usual move)."""
    try:
        from src.openings_book import get_book

        board = chess.Board(fen)
        book = get_book()
        conts = book.continuations(board)
        here = book.by_position(fen)
    except Exception:  # noqa: BLE001 — the moves are a bonus on top of the name
        return None
    if not conts:
        return None
    own = (here or {}).get("name")
    num = f"{board.fullmove_number}." if board.turn == chess.WHITE else f"{board.fullmove_number}..."
    told = []
    for c in sorted(conts[:limit], key=lambda c: c["san"]):
        named = f" — {c['name']} ({c['eco']})" if c.get("name") and c["name"] != own else ""
        told.append(f"{num}{c['san']}{named}")
    return ("Book moves here (ECO book: the variation each move leads to — give a move this name, never one from "
            "memory; the book names lines and counts no games, so it says nothing of which move is main or usual): "
            + "; ".join(told) + ".")


def _facts(board: chess.Board, top: dict, prefetch, lines: Optional[list] = None, explicit: bool = False) -> list[str]:
    """What hangs, what is pinned, what the best move and the opponent threaten.

    *lines* are all the engine's lines of the turn (default: *top* alone): a fork is told only when its move starts
    one of them within 1.0 of the best (src/position_facts.vetted_forks) — «a fork is available now: Qxd5+» was
    told on mate2-no, where 8...Qxd5 takes the queen back (plan 31.10 P8), so the label "verified on the board and
    by the engine" now holds for the forks too.

    Never fails the line: a broken fact search just leaves the facts out.
    """
    lines = list(lines) if lines is not None else ([top] if top else None)
    try:
        if prefetch is not None:
            prefetch.result(timeout=THREAT_MOVETIME_MS / 1000.0 + 2.0)  # warms the cache
        best_uci = (top.get("pv") or "").split()[0] if top.get("pv") else None
        score = top.get("score") or 0.0
        if top.get("mate_in") is not None:
            score = 10000.0 if top["mate_in"] > 0 else -10000.0
        return (_rules(board, explicit) + static_facts(board, lines, explicit=explicit)
                + dynamic_facts(board, best_uci, float(score), _threat_analysis, explicit=explicit))
    except Exception:  # noqa: BLE001 — the facts are a bonus on top of the moves
        return (_rules(board, explicit) + static_facts(board, lines, explicit=explicit)) if board.is_valid() else []


def _rules(board: chess.Board, explicit: bool = False) -> list[str]:
    """Castling, en passant, the tablebase, textbook endings, pawn structure (src/board_rules.py); *explicit*: the
    deciding castling squares and the side to move's pawn and queen moves too."""
    try:
        from src.board_rules import rule_facts

        return rule_facts(board, explicit=explicit)
    except Exception:  # noqa: BLE001
        return []
