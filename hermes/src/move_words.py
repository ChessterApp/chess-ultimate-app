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
            r"возьм[её]м|взял\w*|побил\w*|съел\w*|забрал\w*|рубану\w*|меняю\w*|разменять|"
            # the coach's imperatives: «бей ферзём по h3», «возьми конём на f7» (production, 2026-10-06)
            r"бей|бейте|возьми|возьмите|забери|заберите|съешь|съешьте|руби|рубите|бери|берите)")
_EN_TAKE = r"(?:take|takes|took|taking|capture|captures|grab|grabs|win|wins)"
_EN_PUT = (r"(?:put|place|move|bring|play|swing|drop|develop|retreat|shift|put\s+back|putting|placing|moving|bringing|"
           r"playing|pushing|sending|send)")

_B = r"(?<![а-яa-z])"
_E = r"(?![а-яa-z])"

# «сыграть ферзь b6», «а если ферзь b6?», «хочу конь f3»: speech recognition keeps the
# nominative and often drops «на» (production voice, 2026-10-07 — the [Idea] note
# and the check of «тогда пат» never saw Qb6). Only after a cue to play, and not when
# that piece already stands there: «ферзь b6 атакует…» is a piece on b6.
_SPOKEN = re.compile(
    _B + r"(?:сыграть|сыграю|сыграем|сыграй|играть|играю|пойти|пойду|пойд[её]м|хочу|если|давай|ходом|ход)"
    r"\s+(?:[а-яё]+\s+)?(?P<piece>ладья|конь|слон|ферзь|король|пешка)\s+(?:на\s+)?(?P<to>" + SQ + r")(?![0-9])"
    r"(?!\s*[-–—]?\s*[a-h][1-8](?![0-9]))")
# «пойти ферзём d1», «сходи конём f3»: the instrument said with the square, «на» dropped by the transcription
# (voice 02.11) — after a verb of moving only; the instrument names the piece that moves, never one standing there.
_SPOKEN_WITH = re.compile(
    _B + r"(?:сыграть|сыграй|сыграем|сыграешь|пойти|пойди|пойд[её]м|пойд[её]шь|сходить|сходи|сходим|сходишь|ходи|иди|"
    r"двинуть|двинь|двинем|двинешь|ход|ходом)"
    r"\s+(?P<piece>ладь[её]й|кон[её]м|слоном|ферз[её]м|корол[её]м|пешкой)\s+(?P<to>" + SQ + r")(?![0-9])"
    r"(?!\s*[-–—]?\s*[a-h][1-8](?![0-9]))")  # «ладьёй a8-a5»: a8 is where it stands

_RU_INSTR = r"(?P<piece>ладь[её]й|кон[её]м|слоном|ферз[её]м|корол[её]м|пешкой)"
_RU_OBJ = r"(?:ч[её]рн\w+\s+|бел\w+\s+|его\s+|их\s+|вражеск\w+\s+)?(?:ферзя|коня|слона|ладью|короля|пешку)"

_PATTERNS = [
    # «возьми конём ферзя на d8», «бей пешкой пешку на f2»: the instrument, then the piece taken with its square
    # (review-miss 03.11 — the accusative was read as the mover)
    re.compile(_B + _RU_TAKE + r"\s+(?:сво\w+\s+)?" + _RU_INSTR + r"\s+" + _RU_OBJ + rf"\s+(?:на\s+)?(?P<to>{SQ})(?![0-9])"),
    _SPOKEN,
    _SPOKEN_WITH,
    # «ладью на g1», «коня с f3 на d5», «ладьёй на h4», «пешку на e5»; «пешкой на d2 на d3» — the from-square said with
    # a second «на» (voice 02.11: read as the pawn going to d2)
    re.compile(_B + _RU_PIECE + rf"\s+(?:(?:(?:с\s+)?(?:пол[яе]\s+)?|на\s+(?=[a-h][1-8]\s+на\s+[a-h][1-8](?![0-9])))"
               rf"(?P<frm>{SQ})\s+)?(?:на|в|по)\s+(?:пол[ея]\s+)?(?P<to>{SQ})(?![0-9])"),
    # «ладьёй a8-a5», «коня g1-f3», «ладьёй a8a5» (squares said one after the other, voice): from-square and square
    # (review-miss 02.11 #12)
    re.compile(_B + _RU_PIECE + rf"\s+(?P<frm>{SQ})\s*[-–—]?\s*(?P<to>{SQ})(?![0-9])"),
    # «взять на h4 ладьёй», «бью на e5 конём», «побить h4 ладьёй»
    re.compile(_B + _RU_TAKE + rf"\s+(?:на\s+)?(?P<to>{SQ})(?![0-9])\s+" + _RU_PIECE + _E),
    # «ладьёй взять на h4», «конём бью e5»
    re.compile(_B + _RU_PIECE + r"\s+" + _RU_TAKE + rf"\s+(?:на\s+)?(?P<to>{SQ})(?![0-9])"),
    # «съесть пешку на h7 конём», «взять коня на f6 слоном» (the client's question, 2026-10-05)
    re.compile(_B + _RU_TAKE + r"\s+(?:ч[её]рн\w+\s+|бел\w+\s+|его\s+|их\s+)?(?:ферзя|коня|слона|ладью|короля|пешку)\s+(?:на\s+)?"
               rf"(?P<to>{SQ})(?![0-9])\s+(?:сво\w+\s+|мо\w+\s+)?" + _RU_PIECE + rf"(?:\s+(?P<frm2>{SQ}))?" + _E),
    # «взять ферзя ладьёй», «забрать коня слоном»
    re.compile(_B + _RU_TAKE + r"\s+(?:ч[её]рн\w+\s+|бел\w+\s+|его\s+|их\s+|вражеск\w+\s+)?" + _RU_TARGET + r"\s+" + _RU_PIECE + _E),
    # «конь прыгнет на f7», «ладья сначала идёт на g3», «слон отходит на c4»
    re.compile(_B + r"(?P<piece>ладья|конь|слон|ферзь|король|пешка)" + _E + r"(?:\s+(?!на\s|в\s)[а-яё]+){0,2}?\s+"
               r"(?:прыгает|прыгнет|прыгн[её]т|ид[её]т|пойд[её]т|вста[её]т|встанет|переходит|перейд[её]т|ходит|сходит|отходит|"
               r"отойд[её]т|уходит|уйд[её]т|выходит|выйдет|б[её]р[её]т|возьм[её]т|забирает|забер[её]т|бь[её]т|съест|попада[её]т|"
               r"попад[её]т|нападает|напад[её]т)"
               rf"\s+(?:на|в)\s+(?:пол[ея]\s+)?(?P<to>{SQ})(?![0-9])"),
    # «бей ферзём по h3», «возьми конём на f7»
    re.compile(_B + _RU_TAKE + r"\s+(?:сво\w+\s+)?" + _RU_PIECE + rf"\s+(?:по\s+|на\s+)?(?:пол[юея]\s+|пешке\s+|пешку\s+)?(?P<to>{SQ})(?![0-9])"),
    # «ладьёй взять ферзя»
    re.compile(_B + _RU_PIECE + r"\s+" + _RU_TAKE + r"\s+(?:ч[её]рн\w+\s+|бел\w+\s+|его\s+|их\s+)?" + _RU_TARGET + _E),
    # "put the rook on g1", "move the knight to d5", "rook to g1"
    re.compile(_B + rf"(?:{_EN_PUT}\s+)?(?:the\s+|my\s+|your\s+|a\s+)?" + _EN_PIECE
               + rf"\s+(?:(?:from\s+|on\s+)?(?P<frm>{SQ})\s+)?(?:to|on|onto)\s+(?P<to>{SQ})(?![0-9])"),
    # "the knight jumps to f7", "the rook then swings to g3", "the bishop retreats to c4"
    re.compile(_B + r"(?:the\s+|my\s+|your\s+)?" + _EN_PIECE + r"(?:\s+(?!to\s|on\s|onto\s)[a-z]+){0,2}?\s+"
               r"(?:jumps?|goes|moves|comes|lands|hops|swings|drops|retreats|steps|heads|takes|captures|hits|attacks)"
               rf"\s+(?:over\s+|back\s+)?(?:to|on|onto)\s+(?P<to>{SQ})(?![0-9])"),
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
    taken: list[tuple[int, int]] = []  # spans already read as a move: «пешку на h7» inside «съесть пешку на h7 конём»
    ordered = sorted(_PATTERNS, key=lambda rx: 0 if "target" in rx.groupindex or "TAKE" in rx.pattern or "взять" in rx.pattern else 1)
    for rx in ordered:
        for m in rx.finditer(low):
            if any(m.start() < e and m.end() > b for b, e in taken):
                continue
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
                    _add(out, seen, label, None, note, m.group(0), m.start())
                    taken.append((m.start(), m.end()))
                    continue
                to_name = chess.square_name(squares[0])
            to = chess.parse_square(to_name)
            if rx is _SPOKEN:
                there = board.piece_at(to)
                if there is not None and there.piece_type == ptype and there.color == board.turn:
                    continue  # «если ферзь b6 уйдёт» with the queen on b6: a piece, not a move
            frm = frm or groups.get("frm2")
            from_sq = chess.parse_square(frm) if frm else None
            capture = bool(target) or rx.pattern.find("TAKE") >= 0 or any(
                w in rx.pattern for w in ("взять", "take"))
            san, move, note = resolve(board, ptype, to, from_sq=from_sq, capture=capture)
            _add(out, seen, san, move, note, m.group(0), m.start(),
                 {"ptype": ptype, "to": to, "from": from_sq, "capture": capture,
                  "nominative": m["piece"] in ("ладья", "конь", "слон", "ферзь", "король", "пешка")
                  or bool(re.search(r"\bon\s+[a-h][1-8]$", m.group(0)) and not re.match(_EN_PUT, m.group(0)))})
            taken.append((m.start(), m.end()))
    out.sort(key=lambda item: item["at"])  # in order of appearance, whichever pattern read them
    return out


def _add(out: list, seen: set, san: str, move: Optional[chess.Move], note: Optional[str], words: str,
         at: int = 0, told: Optional[dict] = None) -> None:
    key = move.uci() if move is not None else san
    if key in seen:
        return
    seen.add(key)
    # *told*: what the words named — the piece kind, the target and from-square, a capture, the piece in the nominative
    # («ферзь на d1» may name a piece standing there; «ферзём на d1» names a move) — for a move that cannot be played
    # (src/answer_check._word_move_issues, voice 02.11).
    out.append({"san": san, "move": move, "note": note, "words": words.strip(), "at": at, **(told or {})})


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
    # «побить пешку d5 пешкой e5» right after d7-d5: the capture is en passant,
    # onto d6 (production, 2026-10-06: «нет, не можешь… есть exd6!»).
    if not candidates and ptype == chess.PAWN and board.ep_square is not None:
        victim = board.ep_square + (-8 if board.turn == chess.WHITE else 8)
        if to == victim:
            candidates = [mv for mv in board.legal_moves if board.is_en_passant(mv)
                          and (from_sq is None or mv.from_square == from_sq)]
            if len(candidates) == 1:
                return board.san(candidates[0]), candidates[0], "legal — en passant (the pawn lands on " \
                    + chess.square_name(board.ep_square) + "; only on this move)"
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


_COLOR = {chess.WHITE: "white", chess.BLACK: "black"}


def _named(board: chess.Board, sq: int) -> str:
    pc = board.piece_at(sq)
    return f"the {_COLOR[pc.color]} {chess.piece_name(pc.piece_type)} on {chess.square_name(sq)}"


def why_not(board: chess.Board, ptype: int, to: int, from_sq: Optional[int] = None,
            capture: bool = False) -> Optional[str]:
    """Why no *ptype* piece of the side to move on *board* (from *from_sq* when given) can go to *to*, told from the
    board: the piece already stands there, the square holds an own piece (or, for a pawn going straight, any piece),
    the way is blocked, there is no such piece, nothing to take, or the move would leave the king in check. None when
    such a move is legal (one or several) — voice 02.11: «пойти ферзём на d1» with the queen on d1, «пешкой на d3»
    with Black's bishop on d3."""
    color = board.turn
    side = _COLOR[color]
    name = _NAMES[ptype]
    target = chess.square_name(to)
    legal = [mv for mv in board.legal_moves if mv.to_square == to and board.piece_type_at(mv.from_square) == ptype
             and (from_sq is None or mv.from_square == from_sq)]
    if legal:
        return None
    if ptype == chess.PAWN and board.ep_square is not None and to == board.ep_square + (-8 if color else 8) \
            and any(board.is_en_passant(mv) and (from_sq is None or mv.from_square == from_sq) for mv in board.legal_moves):
        return None  # «побить пешку d5 пешкой e5»: en passant, onto d6 (resolve reads it so)
    there = board.piece_at(to)
    if from_sq is not None:
        pc = board.piece_at(from_sq)
        if pc is None or pc.color != color or pc.piece_type != ptype:
            what = "nothing" if pc is None else f"the {_COLOR[pc.color]} {chess.piece_name(pc.piece_type)}"
            return f"there is no {side} {name} on {chess.square_name(from_sq)} ({what} stands there)"
        if from_sq == to:
            return f"the {side} {name} already stands on {target}"
        movers = [from_sq]
    else:
        movers = list(board.pieces(ptype, color))
        if not movers:
            return f"{side.capitalize()} has no {name}"
    if there is not None and there.color == color:
        if there.piece_type == ptype and (from_sq is None or from_sq == to):
            return f"the {side} {name} already stands on {target}"
        return f"{target} is occupied by {side.capitalize()}'s own {chess.piece_name(there.piece_type)}"
    if capture and there is None and ptype != chess.PAWN:
        return f"there is nothing to take on {target}"
    if ptype == chess.KING and from_sq in (None, movers[0]) and abs(chess.square_file(movers[0]) - chess.square_file(to)) == 2 \
            and chess.square_rank(movers[0]) == chess.square_rank(to):
        return None  # «королём на g1» from e1 is castling told in words: the castling check's to judge
    pseudo = [mv for mv in board.pseudo_legal_moves if mv.to_square == to and mv.from_square in movers
              and board.piece_type_at(mv.from_square) == ptype]
    if pseudo:
        return _leaves_check(board, pseudo[0], name, side, target)
    if ptype == chess.PAWN:
        return _pawn_why(board, movers, to, capture, side, target)
    for sq in movers:
        if _reaches(ptype, sq, to):
            blockers = [b for b in chess.SquareSet.between(sq, to) if board.piece_at(b) is not None]
            if blockers:
                b = min(blockers, key=lambda x: chess.square_distance(x, sq))
                return f"the way of the {name} on {chess.square_name(sq)} to {target} is blocked by {_named(board, b)}"
    where = ", ".join(chess.square_name(sq) for sq in movers)
    stand = "s stand" if len(movers) > 1 else " stands"
    return f"no {side} {name} can reach {target} in one move (the {side} {name}{stand} on {where})"


def _leaves_check(board: chess.Board, mv: chess.Move, name: str, side: str, target: str) -> str:
    """Why the pseudo-legal *mv* is illegal: the king steps onto an attacked square, the king stays in check, or the
    piece is pinned."""
    color = board.turn
    if board.piece_type_at(mv.from_square) == chess.KING:
        after = board.copy(stack=False)
        after.remove_piece_at(mv.from_square)
        attackers = after.attackers(not color, mv.to_square)
        if attackers:
            return f"{target} is attacked by {_named(board, min(attackers))}: the king cannot go there"
        return f"the king cannot go to {target}: it would stay in check"
    checkers = board.checkers()
    if checkers:
        return f"the {side} king is in check from {_named(board, min(checkers))} and the {name} going to {target} does not answer it"
    if board.is_pinned(color, mv.from_square):
        mask = board.pin(color, mv.from_square)
        pinners = [sq for sq in chess.SquareSet(mask) if (pc := board.piece_at(sq)) is not None and pc.color != color]
        by = f" by {_named(board, pinners[0])}" if pinners else ""
        return f"the {name} on {chess.square_name(mv.from_square)} is pinned to the {side} king{by}"
    return f"the {name} going to {target} would leave the {side} king in check"


def _pawn_why(board: chess.Board, movers: list, to: int, capture: bool, side: str, target: str) -> str:
    color = board.turn
    step = 1 if color == chess.WHITE else -1
    start_rank = 1 if color == chess.WHITE else 6
    there = board.piece_at(to)
    same_file = [sq for sq in movers if chess.square_file(sq) == chess.square_file(to)
                 and (chess.square_rank(to) - chess.square_rank(sq) == step
                      or (chess.square_rank(sq) == start_rank and chess.square_rank(to) - chess.square_rank(sq) == 2 * step))]
    beside = [sq for sq in movers if abs(chess.square_file(sq) - chess.square_file(to)) == 1
              and chess.square_rank(to) - chess.square_rank(sq) == step]
    if same_file and not (capture and beside):
        sq = same_file[0]
        if there is not None:
            pc = board.piece_at(to)
            return (f"{target} is occupied by the {_COLOR[pc.color]} {chess.piece_name(pc.piece_type)}: a pawn cannot move "
                    f"straight onto an occupied square (it captures only diagonally)")
        mid = chess.square(chess.square_file(sq), chess.square_rank(sq) + step)
        if mid != to and board.piece_at(mid) is not None:
            return f"the pawn on {chess.square_name(sq)} is blocked by {_named(board, mid)}"
    if beside and there is None:
        return f"there is nothing to take on {target}: a pawn moves diagonally only to capture"
    pawns = ", ".join(chess.square_name(sq) for sq in movers)
    return f"no {side} pawn can reach {target} in one move (the {side} pawn{'s stand' if len(movers) > 1 else ' stands'} on {pawns})"


def _reaches(ptype: int, a: int, b: int) -> bool:
    """A *ptype* piece on *a* would move to *b* on an empty board."""
    if a == b:
        return False
    if ptype == chess.KNIGHT:
        return b in chess.SquareSet(chess.BB_KNIGHT_ATTACKS[a])
    if ptype == chess.KING:
        return b in chess.SquareSet(chess.BB_KING_ATTACKS[a])
    df = abs(chess.square_file(a) - chess.square_file(b))
    dr = abs(chess.square_rank(a) - chess.square_rank(b))
    straight, diagonal = df == 0 or dr == 0, df == dr
    return {chess.ROOK: straight, chess.BISHOP: diagonal, chess.QUEEN: straight or diagonal}.get(ptype, False)


# «push the d-pawn», «двинь d-пешку», «пешкой d вперёд»: a pawn named by its file, no square — it steps forward.
_FILE_PAWN = re.compile(
    _B + r"(?:(?:the\s+|your\s+|my\s+)?(?P<f1>[a-h])-?pawn(?:\s+(?:forward|up|ahead|one\s+square|two\s+squares))?"
    r"|(?P<f2>[a-h])-?пешк(?:у|ой)(?:\s+вперед)?|пешк(?:у|ой)\s+[«\"']?(?P<f3>[a-h])[»\"']?(?![a-z0-9])(?:\s+вперед)?)" + _E)


def file_pushes(text: str, board: chess.Board) -> list[dict]:
    """Pawns told to step forward by their file («push the d-pawn», «двинь d-пешку»), for the side to move: each item
    as prose_moves gives it, with ``file`` (0–7) and ``move`` the one legal push or None."""
    low = (text or "").replace("ё", "е").replace("Ё", "Е").lower()
    out = []
    for m in _FILE_PAWN.finditer(low):
        f = chess.FILE_NAMES.index(m["f1"] or m["f2"] or m["f3"])
        pushes = [mv for mv in board.legal_moves if board.piece_type_at(mv.from_square) == chess.PAWN
                  and chess.square_file(mv.from_square) == f and chess.square_file(mv.to_square) == f]
        out.append({"san": chess.FILE_NAMES[f] + "-pawn", "move": pushes[0] if len(pushes) == 1 else None,
                    "note": None if len(pushes) < 2 else "more than one push", "words": m.group(0).strip(),
                    "at": m.start(), "ptype": chess.PAWN, "file": f, "pushes": len(pushes)})
    return out


def why_no_push(board: chess.Board, f: int) -> Optional[str]:
    """Why no pawn of the side to move on file *f* can step forward; None when one can."""
    color = board.turn
    side = _COLOR[color]
    letter = chess.FILE_NAMES[f]
    pawns = [sq for sq in board.pieces(chess.PAWN, color) if chess.square_file(sq) == f]
    if not pawns:
        return f"{side.capitalize()} has no pawn on the {letter}-file"
    if any(board.piece_type_at(mv.from_square) == chess.PAWN and mv.from_square in pawns
           and chess.square_file(mv.to_square) == f for mv in board.legal_moves):
        return None
    sq = max(pawns) if color == chess.WHITE else min(pawns)
    ahead = sq + (8 if color == chess.WHITE else -8)
    if 0 <= ahead < 64 and board.piece_at(ahead) is not None:
        pc = board.piece_at(ahead)
        return f"the {letter}-pawn on {chess.square_name(sq)} cannot move: {chess.square_name(ahead)} in front of it is " \
               f"occupied by the {_COLOR[pc.color]} {chess.piece_name(pc.piece_type)}"
    if board.is_pinned(color, sq):
        return f"the {letter}-pawn on {chess.square_name(sq)} is pinned to the {side} king"
    return f"the {letter}-pawn on {chess.square_name(sq)} cannot move: it would leave the {side} king in check"
