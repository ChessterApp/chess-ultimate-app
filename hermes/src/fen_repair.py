"""A FEN with impossible castling or en-passant flags, made consistent (2026-10-08).

16 of the site's 187 lesson puzzles carry castling rights their position can
no longer have («… w Qkq», the white king already on g1). python-chess calls
such a board invalid, so the engine tool answered «Invalid FEN» (production,
07.10: 12 of 58 analyze_position calls, 6 of 20 check_moves), and the engine
line, the board facts and the «а если…» notes of the turn quietly switched off.

The pieces and the side to move are never touched — only flags the position
itself rules out are dropped. A FEN that cannot be read, or that is wrong in
any other way (a side not to move in check, a pawn on the first rank), stays
as it is: that is not ours to guess.
"""

from __future__ import annotations

import chess

_REPAIRABLE = chess.STATUS_BAD_CASTLING_RIGHTS | chess.STATUS_INVALID_EP_SQUARE


def repair_fen(fen):
    """*fen* with castling rights and the en-passant square its position allows."""
    if not isinstance(fen, str) or not fen.strip():
        return fen
    try:
        board = chess.Board(fen)
    except ValueError:
        return fen
    status = board.status()
    if not status & _REPAIRABLE:
        return fen
    if status & chess.STATUS_BAD_CASTLING_RIGHTS:
        board.castling_rights = board.clean_castling_rights()
    if status & chess.STATUS_INVALID_EP_SQUARE:
        board.ep_square = None
    return board.fen(en_passant="fen")
