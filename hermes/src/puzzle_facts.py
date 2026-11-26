"""What each move of a puzzle's solution does on the board — the coach explains a solution from these (26.11).

«Почему Сxg4?» in a warm-up puzzle (1...Bd7+ 2.Ke4 Bxg4) was answered «белый король не может ответить взятием,
потому что поле g4 защищено пешкой h6» — a pawn on h6 covers g5; the king on e4 simply stands two files away
(tester 26.11; the stand answered «дело не в материале… ты забираешь пешку» of a move that wins a bishop). The
puzzle's block gave the model the solution as bare notation and the final position, so the reason was told from the
look of the board. The server knows the reason exactly: what a move takes, what guarded that piece when the puzzle
began and what guards it when it is taken, what can take back, where a checked king may go. It says so here, for
every move of the solution, on the position that move is played in.
"""

from __future__ import annotations

import logging
from typing import Optional

import chess

logger = logging.getLogger(__name__)

MAX_PLIES = 10  # a longer solution is told by its first moves; the block says how many it left out


def _piece(board: chess.Board, sq: int) -> str:
    p = board.piece_at(sq)
    return f"the {'white' if p.color else 'black'} {chess.piece_name(p.piece_type)} on {chess.square_name(sq)}"


def _names(board: chess.Board, squares) -> str:
    return ", ".join(_piece(board, s) for s in squares)


def _label(board: chess.Board, san: str) -> str:
    return f"{board.fullmove_number}{'.' if board.turn == chess.WHITE else '...'}{san}"


def _parse(board: chess.Board, token: str) -> Optional[chess.Move]:
    try:
        return board.parse_san(token)
    except ValueError:
        try:
            move = chess.Move.from_uci(token)
        except ValueError:
            return None
        return move if move in board.legal_moves else None


def _guard_story(start: chess.Board, board: chess.Board, move: chess.Move) -> str:
    """Why the piece *move* takes could be taken: what guarded it when the puzzle began, and what guards it now."""
    dest = move.to_square
    victim = board.piece_at(dest)
    if victim is None:
        return ""
    now = sorted(board.attackers(victim.color, dest))
    was = start.piece_at(dest)
    if was is None or was.piece_type != victim.piece_type or was.color != victim.color:
        return ""  # it came to this square during the solution: the moves before tell how
    then = sorted(start.attackers(victim.color, dest))
    if then and not now:
        return (f"when the puzzle began {_piece(board, dest)} was guarded by {_names(start, then)}; by this move "
                "nothing guards it any more — the earlier moves of the solution took its guard away")
    if not then and not now:
        return f"nothing guarded {_piece(board, dest)}, from the start of the puzzle to this move"
    return ""


def move_facts(start: chess.Board, board: chess.Board, move: chess.Move) -> str:
    """One move of the solution, on *board* (before it): the move in words and what it does there."""
    from src.game_mode import move_words
    from src.hypothetical import moved_piece_facts

    after = board.copy(stack=False)
    after.push(move)
    told = [move_words(board, move)]
    if after.is_checkmate():
        told.append("this is checkmate")
        return "; ".join(told)
    if board.is_capture(move) and not board.is_en_passant(move):
        story = _guard_story(start, board, move)
        if story:
            told.append(story)
    for fact in moved_piece_facts(board, after, move):
        if fact.startswith("it takes ") or " gives check" in fact or fact.endswith("attacks nothing"):
            continue  # in the move's words already; «attacks nothing» is no reason
        if fact.endswith("is not attacked") and board.is_capture(move):
            continue  # said as «nothing can take it back»
        told.append(fact)
    return "; ".join(told)


def solution_facts(fen: str, solution: list) -> list[str]:
    """«1...Bd7+ — bishop from c6 to d7, check; …» for every move of *solution* from *fen*; [] when the line cannot
    be played."""
    try:
        start = chess.Board(fen)
    except ValueError:
        return []
    board = start.copy(stack=False)
    solver = start.turn
    out: list[str] = []
    for i, token in enumerate(solution or []):
        if i >= MAX_PLIES:
            out.append(f"(…and {len(solution) - MAX_PLIES} more moves of the solution, not told here)")
            break
        move = _parse(board, str(token))
        if move is None:
            return out
        san = board.san(move)
        try:
            who = "the solver's move" if board.turn == solver else "the reply"
            out.append(f"{_label(board, san)} ({who}) — {move_facts(start, board, move)}.")
        except Exception:  # noqa: BLE001 — one move's facts never lose the rest
            logger.debug("puzzle facts: %s failed", san, exc_info=True)
            out.append(f"{_label(board, san)}.")
        board.push(move)
    return out


RULE = (
    "Explain WHY a move of the solution works only from these lines: what it takes, what guarded that piece and no "
    "longer does, what can or cannot take back, where the checked king may go. Never name a defender, an attacker "
    "or a reason they do not give (a pawn guards only the two squares diagonally ahead of it; a king only the "
    "squares next to it)."
)
