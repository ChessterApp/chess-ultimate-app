"""The voice coach's [Engine] line — Stockfish's top moves for the board, ahead of the question.

Gemini Live has to call analyze_position and wait for it before it can say
anything concrete about the position (voice bench 2026-09-24: ~5 s to the
substantive answer, 7 s of silence on the old model). The browser asks for this
line whenever the board changes and feeds it into the live session, so "what is
the best move here?" is answered from context straight away. The analysis goes
through the same cache as the tool, so a later analyze_position call for this
position is free too.
"""

import threading
from typing import Optional

import chess

from src.tools.stockfish import DEFAULT_DEPTH, DEFAULT_MULTIPV, analyze_cached

PV_PLIES = 4

# Stepping through a game fires one request per move; never run more than a
# couple of engines for it at once (each request is a Stockfish process).
_slots = threading.BoundedSemaphore(2)


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


def engine_note(fen: str, depth: int = DEFAULT_DEPTH) -> Optional[dict]:
    """Return {fen, note, best, lines} for a legal position, or None when it cannot be analysed."""
    try:
        board = chess.Board(fen)
    except (ValueError, IndexError):
        return None
    if not board.is_valid():
        return None

    over = _game_over_note(board, fen)
    if over:
        return {"fen": fen, "note": over, "best": None, "lines": []}

    with _slots:
        result = analyze_cached(fen, depth=depth, multipv=DEFAULT_MULTIPV)
    if "error" in result or not result.get("lines"):
        return None

    lines = []
    for raw in result["lines"]:
        san = _san_line(board, raw.get("pv", ""))
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
    return {"fen": fen, "note": " ".join(parts), "best": best["moves"][0], "lines": lines}
