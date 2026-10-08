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
_threat_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="threat")


def _threat_analysis(fen: str) -> dict:
    return analyze_timed(fen, THREAT_MOVETIME_MS, multipv=1, min_depth=10)


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


def engine_note(fen: str, depth: int = DEFAULT_DEPTH, movetime_ms: Optional[int] = None) -> Optional[dict]:
    """Return {fen, note, best, lines} for a legal position, or None when it cannot be analysed.

    With *movetime_ms* the engine searches for that long instead of to *depth*
    (the text turn waits for the line, so it must be ready on time).
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
    prefetch = _threat_pool.submit(_threat_analysis, passed_fen) if passed_fen else None
    with _slots:
        if movetime_ms:
            result = analyze_timed(fen, movetime_ms, multipv=DEFAULT_MULTIPV)
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

    # COACH_ENGINE_FACTS=0 leaves the line as moves and evaluations only.
    facts = _facts(board, result["lines"][0], prefetch) if with_facts else []
    if facts:
        parts.append("Facts (verified on the board and by the engine): " + "; ".join(facts) + ".")
    mate_in = result["lines"][0].get("mate_in")
    tb = None
    if tb_future is not None:
        try:
            tb = tb_future.result(timeout=0.5)  # the lookup ran during the search; a slow one is left out
        except Exception:  # noqa: BLE001 — a bonus on top of the engine
            tb = None
    return {"fen": fen, "note": " ".join(parts), "best": best["moves"][0], "lines": lines, "facts": facts,
            "tablebase": tb, "mate_in": mate_in}


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


def _facts(board: chess.Board, top: dict, prefetch) -> list[str]:
    """What hangs, what is pinned, what the best move and the opponent threaten.

    Never fails the line: a broken fact search just leaves the facts out.
    """
    try:
        if prefetch is not None:
            prefetch.result(timeout=THREAT_MOVETIME_MS / 1000.0 + 2.0)  # warms the cache
        best_uci = (top.get("pv") or "").split()[0] if top.get("pv") else None
        score = top.get("score") or 0.0
        if top.get("mate_in") is not None:
            score = 10000.0 if top["mate_in"] > 0 else -10000.0
        return _rules(board) + static_facts(board) + dynamic_facts(board, best_uci, float(score), _threat_analysis)
    except Exception:  # noqa: BLE001 — the facts are a bonus on top of the moves
        return (_rules(board) + static_facts(board)) if board.is_valid() else []


def _rules(board: chess.Board) -> list[str]:
    """Castling, en passant, the tablebase, textbook endings, pawn structure (src/board_rules.py)."""
    try:
        from src.board_rules import rule_facts

        return rule_facts(board)
    except Exception:  # noqa: BLE001
        return []
