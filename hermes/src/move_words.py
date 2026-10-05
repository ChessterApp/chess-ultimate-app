"""Moves written in words, as moves on a board.

«Поставить ладью на g1», «взять на h4 ладьёй», «конём на f5», "rook to g1",
"take the queen with the rook": the student (and the coach) name moves this
way as often as in notation. Resolved on the board on the screen, so the
legality block, the engine's look at the student's idea and the check of the
coach's recommendation all see the same move (2026-10-04).
"""

from __future__ import annotations

import re
from typing import Optional

import chess

SQ = r"[a-h][1-8]"

# Object and instrument cases: «ладью» (put the rook), «ладьёй» (with the rook).
_RU_PIECE = (r"(?P<piece>ладью|ладь[её]й|ладьи|коня|кон[её]м|слона|слоном|ферзя|ферз[её]м|короля|корол[её]м|"
             r"пешку|пешкой|пешки)")
_EN_PIECE = r"(?P<piece>rook|knight|bishop|queen|king|pawn)"
_RU_TARGET = r"(?P<target>ферзя|коня|слона|ладью|короля|пешку)"
_EN_TARGET = r"(?P<target>queen|knight|bishop|rook|king|pawn)"
_RU_TAKE = (r"(?:взять|бить|побить|съесть|забрать|срубить|брать|рубить|забирать|беру|бью|бер[её]м|бь[её]м|возьму|"
            r"возьм[её]м|взял\w*|побил\w*|съел\w*|забрал\w*|рубану\w*|меняю\w*|разменять)")
_EN_TAKE = r"(?:take|takes|took|taking|capture|captures|grab|grabs|win|wins)"
_EN_PUT = r"(?:put|place|move|bring|play|swing|drop|develop|retreat|shift|put\s+back)"

_B = r"(?<![а-яa-z])"
_E = r"(?![а-яa-z])"

_PATTERNS = [
    # «ладью на g1», «коня с f3 на d5», «ладьёй на h4», «пешку на e5»
    re.compile(_B + _RU_PIECE + rf"\s+(?:(?:с\s+)?(?:пол[яе]\s+)?(?P<frm>{SQ})\s+)?(?:на|в)\s+(?:пол[ея]\s+)?(?P<to>{SQ})(?![0-9])"),
    # «взять на h4 ладьёй», «бью на e5 конём», «побить h4 ладьёй»
    re.compile(_B + _RU_TAKE + rf"\s+(?:на\s+)?(?P<to>{SQ})(?![0-9])\s+" + _RU_PIECE + _E),
    # «ладьёй взять на h4», «конём бью e5»
    re.compile(_B + _RU_PIECE + r"\s+" + _RU_TAKE + rf"\s+(?:на\s+)?(?P<to>{SQ})(?![0-9])"),
    # «взять ферзя ладьёй», «забрать коня слоном»
    re.compile(_B + _RU_TAKE + r"\s+(?:ч[её]рн\w+\s+|бел\w+\s+|его\s+|их\s+|вражеск\w+\s+)?" + _RU_TARGET + r"\s+" + _RU_PIECE + _E),
    # «ладьёй взять ферзя»
    re.compile(_B + _RU_PIECE + r"\s+" + _RU_TAKE + r"\s+(?:ч[её]рн\w+\s+|бел\w+\s+|его\s+|их\s+)?" + _RU_TARGET + _E),
    # "put the rook on g1", "move the knight to d5", "rook to g1"
    re.compile(_B + rf"(?:{_EN_PUT}\s+)?(?:the\s+|my\s+|your\s+|a\s+)?" + _EN_PIECE
               + rf"\s+(?:(?:from\s+|on\s+)?(?P<frm>{SQ})\s+)?(?:to|on|onto)\s+(?P<to>{SQ})(?![0-9])"),
    # "take on h4 with the rook", "capture h4 with the rook"
    re.compile(_B + _EN_TAKE + rf"\s+(?:on\s+)?(?P<to>{SQ})(?![0-9])\s+with\s+(?:the\s+|my\s+|your\s+)?" + _EN_PIECE + _E),
    # "rook takes h4", "rook takes on h4"
    re.compile(_B + _EN_PIECE + rf"\s+{_EN_TAKE}\s+(?:on\s+)?(?P<to>{SQ})(?![0-9])"),
    # "take the queen with the rook"
    re.compile(_B + _EN_TAKE + r"\s+(?:the\s+|his\s+|her\s+|their\s+|black'?s\s+|white'?s\s+)?" + _EN_TARGET
               + r"\s+with\s+(?:the\s+|my\s+|your\s+)?" + _EN_PIECE + _E),
    # "rook takes the queen"
    re.compile(_B + _EN_PIECE + rf"\s+{_EN_TAKE}\s+(?:the\s+|his\s+|her\s+|their\s+)?" + _EN_TARGET + _E),
]

_TYPES = {"лад": chess.ROOK, "кон": chess.KNIGHT, "сло": chess.BISHOP, "фер": chess.QUEEN, "кор": chess.KING,
          "пеш": chess.PAWN, "roo": chess.ROOK, "kni": chess.KNIGHT, "bis": chess.BISHOP, "que": chess.QUEEN,
          "kin": chess.KING, "paw": chess.PAWN}
_LETTER = {chess.ROOK: "R", chess.KNIGHT: "N", chess.BISHOP: "B", chess.QUEEN: "Q", chess.KING: "K", chess.PAWN: ""}
_NAMES = {chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook",
          chess.QUEEN: "queen", chess.KING: "king", chess.PAWN: "pawn"}


def _ptype(word: str) -> Optional[int]:
    return _TYPES.get(word.lower().replace("ё", "е")[:3])


def prose_moves(text: str, board: chess.Board) -> list[dict]:
    """Moves named in words in *text*, for the side to move on *board*.

    Each item: ``san`` (the move as the board writes it, or the best label when
    it is not a legal move), ``move`` (a chess.Move, or None), ``note`` (why
    there is no move: ambiguous, no such piece, nothing to take), ``words``
    (the phrase). Order of appearance, one item per move.
    """
    low = (text or "").replace("ё", "е").replace("Ё", "Е").lower()
    out: list[dict] = []
    seen: set[str] = set()
    for rx in _PATTERNS:
        for m in rx.finditer(low):
            ptype = _ptype(m["piece"])
            if ptype is None:
                continue
            groups = m.groupdict()
            to_name, target = groups.get("to"), groups.get("target")
            frm = groups.get("frm")
            if target:
                ttype = _ptype(target)
                squares = list(board.pieces(ttype, not board.turn)) if ttype is not None else []
                if len(squares) != 1:
                    label = f"{_LETTER[ptype]}x{_NAMES.get(ttype, '?')}"
                    note = (f"there is no {'black' if board.turn else 'white'} {_NAMES.get(ttype, 'piece')} to take"
                            if not squares else f"more than one {_NAMES.get(ttype, 'piece')} could be meant")
                    _add(out, seen, label, None, note, m.group(0))
                    continue
                to_name = chess.square_name(squares[0])
            to = chess.parse_square(to_name)
            from_sq = chess.parse_square(frm) if frm else None
            capture = bool(target) or rx.pattern.find("TAKE") >= 0 or any(
                w in rx.pattern for w in ("взять", "take"))
            san, move, note = resolve(board, ptype, to, from_sq=from_sq, capture=capture)
            _add(out, seen, san, move, note, m.group(0))
    return out


def _add(out: list, seen: set, san: str, move: Optional[chess.Move], note: Optional[str], words: str) -> None:
    key = move.uci() if move is not None else san
    if key in seen:
        return
    seen.add(key)
    out.append({"san": san, "move": move, "note": note, "words": words.strip()})


def resolve(board: chess.Board, ptype: int, to: int, from_sq: Optional[int] = None,
            capture: bool = False) -> tuple[str, Optional[chess.Move], Optional[str]]:
    """The legal move of a *ptype* piece to *to* (from *from_sq* when given).

    Returns (san, move, None) for one legal move; (label, None, why) when
    there are several candidates or none. A promotion resolves to a queen.
    """
    candidates = [
        mv for mv in board.legal_moves
        if mv.to_square == to and board.piece_type_at(mv.from_square) == ptype
        and (from_sq is None or mv.from_square == from_sq)
        and (mv.promotion in (None, chess.QUEEN))
    ]
    if len(candidates) == 1:
        return board.san(candidates[0]), candidates[0], None
    letter = _LETTER[ptype]
    target = board.piece_at(to)
    x = "x" if (capture or (target is not None and target.color != board.turn)) else ""
    label = f"{letter}{x}{chess.square_name(to)}" if (letter or not x) else f"x{chess.square_name(to)}"
    if len(candidates) > 1:
        sans = ", ".join(board.san(mv) for mv in candidates)
        return label, None, f"ambiguous — more than one {_NAMES[ptype]} can go to {chess.square_name(to)} ({sans})"
    return label, None, None
