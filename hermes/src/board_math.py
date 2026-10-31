"""Board arithmetic the answer-check judges share (plan 31.10, WP-0; frozen — a change needs every owner's consent).

One copy of the static exchange and of "where can this piece go", so the game-record checks (P1), the scene judge
(P3B), the board rules (P3D) and the facts (P8) count the same way:

  see(board, move)               the static exchange of a capture, in pawns, for the side making it
  capture_is_free(board, move)   the capture wins the piece it takes and loses nothing back
  legal_moves_of(board, sq)      the legal moves of the piece on sq (for its own side, whoever is to move)
  reach(board, sq)               the squares the piece on sq attacks
  safe_squares(board, sq)        the squares the piece on sq can go to without losing material by static exchange

``see`` is the function that was ``claim_rules.see`` (moved here; claim_rules re-imports it, byte for byte).
"""
from __future__ import annotations

from typing import Optional

import chess

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def see(board: chess.Board, move: chess.Move) -> int:
    """The static exchange count of the capture *move* (in pawns): what its side wins on that square when both sides
    keep taking there with their cheapest piece while it pays."""
    t = move.to_square
    if board.is_en_passant(move):
        first = 1
    else:
        v = board.piece_at(t)
        first = VALUE[v.piece_type] if v else 0
    b = board.copy(stack=False)
    mover = b.piece_at(move.from_square)
    gains = [first]
    on_square = VALUE[mover.piece_type]
    b.push(move)
    side = b.turn
    while True:
        attackers = [s for s in b.attackers(side, t)
                     if chess.Move(s, t) in b.legal_moves or (b.piece_type_at(s) == chess.PAWN and chess.square_rank(t) in (0, 7))]
        if not attackers:
            break
        s = min(attackers, key=lambda x: VALUE[b.piece_type_at(x)])
        gains.append(on_square - gains[-1])
        on_square = VALUE[b.piece_type_at(s)]
        mv = next((m for m in b.legal_moves if m.from_square == s and m.to_square == t), None)
        if mv is None:
            break
        b.push(mv)
        side = b.turn
    for i in range(len(gains) - 1, 0, -1):
        gains[i - 1] = -max(-gains[i - 1], gains[i])
    return gains[0]


def captured_value(board: chess.Board, move: chess.Move) -> int:
    """The value of what *move* takes (1 for en passant, 0 for a quiet move)."""
    if board.is_en_passant(move):
        return 1
    p = board.piece_at(move.to_square)
    return VALUE[p.piece_type] if p else 0


def capture_is_free(board_before: chess.Board, move: chess.Move) -> bool:
    """True when *move* captures and the static exchange is the captured piece's value: nothing is lost back
    («белые забирают фигуру бесплатно» after 4.exf6 is false — gxf6 or Qxf6 takes the pawn back)."""
    if not board_before.is_capture(move):
        return False
    return see(board_before, move) >= captured_value(board_before, move)


def _as_side(board: chess.Board, color: chess.Color) -> Optional[chess.Board]:
    """*board* with *color* to move (en passant dropped when the turn changes), or None when that position is not
    legal (the other king would be in check)."""
    if board.turn == color:
        return board
    b = board.copy(stack=False)
    b.turn = color
    b.ep_square = None
    return b if b.is_valid() else None


def legal_moves_of(board: chess.Board, sq: int) -> list[chess.Move]:
    """The legal moves of the piece on *sq*, for its own side whoever is to move ([] for an empty square or when the
    position with that side to move is not legal)."""
    p = board.piece_at(sq)
    if p is None:
        return []
    b = _as_side(board, p.color)
    if b is None:
        return []
    return [m for m in b.legal_moves if m.from_square == sq]


def reach(board: chess.Board, sq: int) -> chess.SquareSet:
    """The squares the piece on *sq* attacks (empty for an empty square)."""
    if board.piece_at(sq) is None:
        return chess.SquareSet()
    return board.attacks(sq)


def move_loss(board: chess.Board, move: chess.Move) -> int:
    """What the mover loses by static exchange on the arrival square after *move* (≥ 0; what it takes is counted
    against it): 0 when the piece is safe there or wins at least as much as it can lose."""
    gain = captured_value(board, move)
    b = board.copy(stack=False)
    b.push(move)
    t = move.to_square
    worst = 0
    for m in b.legal_moves:
        if m.to_square == t and b.is_capture(m):
            worst = max(worst, see(b, m))
    return max(0, worst - gain)


def safe_squares(board: chess.Board, sq: int) -> list[int]:
    """The squares the piece on *sq* can move to without losing material by static exchange there, in square order
    (promotions counted once). [] for a trapped piece."""
    out = []
    for m in legal_moves_of(board, sq):
        if m.to_square in out:
            continue
        b = _as_side(board, board.piece_at(sq).color)
        if b is not None and move_loss(b, m) == 0:
            out.append(m.to_square)
    return sorted(out)
