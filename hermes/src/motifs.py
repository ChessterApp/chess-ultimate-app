"""Does a position show the motif it is an example of — a fork, a pin, a skewer, a discovered attack?

«Покажи пример вилки» put the first diagram of the site's lesson «Двойной шах» on the board — a king,
a queen and a king, no fork anywhere — and the coach explained a fork that was not there (prod,
2026-10-13). An example position for a tactical motif shows it now or after one move of the side to
move (a lesson's diagram is often the position before the blow); a position that shows neither is
not an example of it, whatever lesson it came from.
"""

from __future__ import annotations

from typing import Optional

import chess

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
SLIDERS = (chess.BISHOP, chess.ROOK, chess.QUEEN)


def _threatens_mate(board: chess.Board, color: chess.Color) -> bool:
    """*color* would mate in one if it were its move."""
    test = board.copy(stack=False)
    if test.turn != color:
        if test.is_check():
            return False
        test.push(chess.Move.null())
    for mv in test.legal_moves:
        test.push(mv)
        mate = test.is_checkmate()
        test.pop()
        if mate:
            return True
    return False


def _forks(board: chess.Board, sq: int) -> bool:
    """The piece on *sq* attacks two targets: the king, a piece worth more, or a piece left undefended —
    or one of them while its side threatens mate (the site's «двойной удар с нападением на мат»)."""
    piece = board.piece_at(sq)
    if piece is None:
        return False
    targets = 0
    for t in board.attacks(sq):
        victim = board.piece_at(t)
        if victim is None or victim.color == piece.color or victim.piece_type == chess.PAWN:
            continue
        if (victim.piece_type == chess.KING or VALUE[victim.piece_type] > VALUE[piece.piece_type]
                or not board.is_attacked_by(victim.color, t)):
            targets += 1
    return targets >= 2 or (targets == 1 and _threatens_mate(board, piece.color))


def _ray_pair(board: chess.Board, sq: int) -> list[tuple[int, int]]:
    """(first, second) enemy pieces one behind the other on the lines of the slider on *sq*."""
    piece = board.piece_at(sq)
    if piece is None or piece.piece_type not in SLIDERS:
        return []
    dirs = []
    if piece.piece_type in (chess.ROOK, chess.QUEEN):
        dirs += [(0, 1), (0, -1), (1, 0), (-1, 0)]
    if piece.piece_type in (chess.BISHOP, chess.QUEEN):
        dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    out = []
    for df, dr in dirs:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        seen = []
        while len(seen) < 2:
            f, r = f + df, r + dr
            if not (0 <= f < 8 and 0 <= r < 8):
                break
            s = chess.square(f, r)
            p = board.piece_at(s)
            if p is None:
                continue
            if p.color == piece.color:
                break
            seen.append(s)
        if len(seen) == 2:
            out.append((seen[0], seen[1]))
    return out


def _pins(board: chess.Board, color: chess.Color) -> bool:
    """A slider of *color* pins an enemy piece to the king or to a piece worth more behind it."""
    for sq in board.pieces(chess.BISHOP, color) | board.pieces(chess.ROOK, color) | board.pieces(chess.QUEEN, color):
        for front, back in _ray_pair(board, sq):
            fv, bv = VALUE[board.piece_type_at(front)], VALUE[board.piece_type_at(back)]
            if board.piece_type_at(front) != chess.KING and bv > fv and board.piece_type_at(back) != chess.PAWN:
                return True
    return False


def _skewers(board: chess.Board, color: chess.Color) -> bool:
    """A slider of *color* attacks a valuable piece with a lesser (non-pawn) piece behind it."""
    for sq in board.pieces(chess.BISHOP, color) | board.pieces(chess.ROOK, color) | board.pieces(chess.QUEEN, color):
        for front, back in _ray_pair(board, sq):
            fp, bp = board.piece_type_at(front), board.piece_type_at(back)
            if fp in (chess.KING, chess.QUEEN, chess.ROOK) and bp != chess.PAWN and VALUE[fp] > VALUE[bp]:
                return True
    return False


def _discovers(board: chess.Board, move: chess.Move) -> bool:
    """After *move*, a piece other than the one moved checks the king or attacks the queen or a rook."""
    mover = board.turn
    after = board.copy(stack=False)
    after.push(move)
    if len(after.checkers()) >= 2:
        return True
    for sq in after.pieces(chess.BISHOP, mover) | after.pieces(chess.ROOK, mover) | after.pieces(chess.QUEEN, mover):
        if sq == move.to_square:
            continue
        for t in after.attacks(sq):
            victim = after.piece_at(t)
            if victim is None or victim.color == mover or victim.piece_type not in (chess.KING, chess.QUEEN, chess.ROOK):
                continue
            if t not in board.attacks(sq):
                return True
    return False


MOTIFS = ("fork", "pin", "skewer", "discovered-attack")


def shows_motif(fen: str, slug: str) -> Optional[bool]:
    """True when the position shows the motif now or after one move of the side to move, False when it
    does not, None when *slug* is not a motif checked here (or the FEN is broken)."""
    if slug not in MOTIFS:
        return None
    try:
        board = chess.Board(fen)
    except (ValueError, IndexError):
        return None
    us = board.turn
    if slug == "fork":
        if any(_forks(board, sq) for sq in chess.SQUARES if board.piece_at(sq)):
            return True
        for mv in board.legal_moves:
            after = board.copy(stack=False)
            after.push(mv)
            if _forks(after, mv.to_square):
                return True
        return False
    if slug in ("pin", "skewer"):
        test = _pins if slug == "pin" else _skewers
        if test(board, us) or test(board, not us):
            return True
        for mv in board.legal_moves:
            after = board.copy(stack=False)
            after.push(mv)
            if test(after, us):
                return True
        return False
    return any(_discovers(board, mv) for mv in board.legal_moves)
