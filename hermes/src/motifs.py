"""Does a position show the motif it is an example of — a fork, a pin, a skewer, a discovered attack?

«Покажи пример вилки» put the first diagram of the site's lesson «Двойной шах» on the board — a king,
a queen and a king, no fork anywhere — and the coach explained a fork that was not there (prod,
2026-10-13). An example position for a tactical motif shows it now or after one move of the side to
move (a lesson's diagram is often the position before the blow); a position that shows neither is
not an example of it, whatever lesson it came from.
"""

from __future__ import annotations

import re
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


def _sliders(board: chess.Board, color: chess.Color, piece: Optional[int] = None) -> chess.SquareSet:
    """The squares of *color*'s sliders — only of type *piece* when one is asked («связка слоном»)."""
    return chess.SquareSet([sq for pt in SLIDERS if piece is None or pt == piece for sq in board.pieces(pt, color)])


def _pins(board: chess.Board, color: chess.Color, piece: Optional[int] = None) -> bool:
    """A slider of *color* pins an enemy piece to the king or to a piece worth more behind it."""
    for sq in _sliders(board, color, piece):
        for front, back in _ray_pair(board, sq):
            fv, bv = VALUE[board.piece_type_at(front)], VALUE[board.piece_type_at(back)]
            if board.piece_type_at(front) != chess.KING and bv > fv and board.piece_type_at(back) != chess.PAWN:
                return True
    return False


def _skewers(board: chess.Board, color: chess.Color, piece: Optional[int] = None) -> bool:
    """A slider of *color* attacks a valuable piece with a lesser (non-pawn) piece behind it."""
    for sq in _sliders(board, color, piece):
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


def shows_motif(fen: str, slug: str, piece: Optional[int] = None) -> Optional[bool]:
    """True when the position shows the motif now or after one move of the side to move, False when it
    does not, None when *slug* is not a motif checked here (or the FEN is broken). *piece*: the motif
    made by that piece only — «вилка конём» is not shown by a rook's double attack (prod 29.10)."""
    if slug not in MOTIFS:
        return None
    try:
        board = chess.Board(fen)
    except (ValueError, IndexError):
        return None
    us = board.turn

    def by(b: chess.Board, sq: int) -> bool:
        return piece is None or b.piece_type_at(sq) == piece

    if slug == "fork":
        if any(_forks(board, sq) for sq in chess.SQUARES if board.piece_at(sq) and by(board, sq)):
            return True
        for mv in board.legal_moves:
            after = board.copy(stack=False)
            after.push(mv)
            if by(after, mv.to_square) and _forks(after, mv.to_square):
                return True
        return False
    if slug in ("pin", "skewer"):
        test = _pins if slug == "pin" else _skewers
        if test(board, us, piece) or test(board, not us, piece):
            return True
        for mv in board.legal_moves:
            after = board.copy(stack=False)
            after.push(mv)
            if test(after, us, piece):
                return True
        return False
    return any(_discovers(board, mv) for mv in board.legal_moves if piece is None or board.piece_type_at(mv.from_square) == piece)


# The piece a motif is asked with: «вилка конём», «пример вилки пешкой», «коневая вилка», «связка слоном»,
# "knight fork", "a fork with the queen". Production 29.10 (d3-example): «Покажи на доске пример вилки конём»
# put up the lesson's double attack by a rook — the example search did not know the piece was asked.
_MOTIF_RX = {
    "fork": r"вилк\w*|двойн\w+\s+удар\w*|forks?|double\s+attacks?",
    "pin": r"связк\w*|pins?",
    "skewer": r"сквозн\w+\s+(?:удар|атак)\w*|рентген\w*|skewers?",
    "discovered-attack": r"вскрыт\w+\s+(?:шах|нападени|атак)\w*|discovered\s+(?:attacks?|checks?)",
}
# The forms that name the piece MAKING the motif: the instrumental («вилка конём», «связка слоном»), the
# adjective («коневая вилка», "knight fork") and "with/by the knight". Not the targets: «королевская вилка» is a
# fork OF the king and queen (by a knight, usually), "pin the knight" / "fork the king and rook" name what is hit
# (review 30.10) — so no adjective for the king, and an English piece only before the motif or after with/by.
_BY_PIECE = ((chess.KNIGHT, r"кон[её]м", r"конев\w+|конск\w+", r"knight"),
             (chess.PAWN, r"пешкой", r"пешечн\w+", r"pawn"),
             (chess.BISHOP, r"слоном", r"слонов\w+", r"bishop"),
             (chess.ROOK, r"ладь[её]й", r"ладейн\w+", r"rook"),
             (chess.QUEEN, r"ферз[её]м", r"ферзев\w+", r"queen"),
             (chess.KING, r"корол[её]м", None, None))
# A pin or a skewer is made by a slider: «связка конём» names no motif that exists — nothing to look for.
_MAKERS = {"pin": SLIDERS, "skewer": SLIDERS}


def motif_pieces(text: str) -> Optional[tuple]:
    """(motif slug, the piece types named as making it) when *text* asks for a motif made by a named piece —
    every piece named counts («чем вилка конём отличается от вилки пешкой?»: a knight and a pawn) — else None."""
    low = (text or "").lower().replace("ё", "е")
    for slug, motif in _MOTIF_RX.items():
        found = set()
        for piece, instr, adj, en in _BY_PIECE:
            if piece not in _MAKERS.get(slug, (piece,)):
                continue
            by = rf"(?<![а-яa-z])(?:{motif})\s+(?:с\s+)?{instr}(?![а-яa-z])"
            if en:
                by += (rf"|(?<![а-яa-z])(?:{motif})\s+(?:by|with|using)\s+(?:(?:a|the|your|my)\s+)?{en}(?![a-z])"
                       rf"|(?<![а-яa-z])(?:{adj}|{en}(?:'s)?)\s+(?:{motif})(?![а-яa-z])")
            if re.search(by, low):
                found.add(piece)
        if found:
            return slug, frozenset(found)
    return None


def motif_piece(text: str) -> Optional[tuple]:
    """(motif slug, piece type) when *text* asks for a motif made by one named piece, else None."""
    asked = motif_pieces(text)
    return (asked[0], next(iter(asked[1]))) if asked and len(asked[1]) == 1 else None
