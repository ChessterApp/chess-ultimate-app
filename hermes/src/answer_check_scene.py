"""The position a line written in the answer reaches, and what the answer says next about it (prod 29.10).

A coach line is told half in notation, half in words: «Kd6 — и белый король заходит через d5», «лучший ход — b3:
ты отгоняешь слона, а если он отступит на a6, то с боку грозит bxc4», «после Ke5 белые играют a6, и ты обязан идти
Kd6. Теперь замри: пешка на a7, ты на d6». The checker followed only the notation, and leniently (a move legal in any
position of the turn, for either side), so what came after such a line was never judged in the position the line
reached: Kd5 next to the black king on d6, bxc4 with c4 empty after ...Ba6, a pawn «on a7» after a6 (production
check 29.10: r-zugzwang, castle-00, square-no).

Here the line is walked strictly — each move, in notation or in words, by the side to move — from a position given to
the turn (the board, a position a tool put on the screen, a game's) or from the line of the sentence before. Then:
  * a move that goes straight on with the line (no «или», «вместо», «иначе», «сейчас», no «если» before it, no move
    number from another point) and is impossible there for either side is wrong — the issue says why and what is
    legal there;
  * «пешка на a7, ты на d6», «конь стоит на d4» said of the position the line reached is wrong when no such piece
    stands there — in that position, anywhere along the line, or on a position given to the turn.
What is not followed is not judged: a move that fits no position (src/answer_check._san_issues has those), a branch
(«или», «вместо», a numbered move from another point), a move one side makes twice (a plan told one side at a time:
«Ke5, Kd6, Kc7»), a pronoun with nothing to name, two pieces that could make the move, a denial, a question, a move
marked «?». The first move of a line is never judged here: only what follows a move the line has made.
Review 30.10: a line with a square after its last read move («а на Be7 — e3») is not gone on with; «конь на f3»
a move away is the next move or a plan, not where the line stands; a line told as someone's belief is not the
coach's; a sentence not shown leaves the line as it was.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

SQ = r"[a-h][1-8]"
_B = r"(?<![а-яёa-z])"
_E = r"(?![а-яёa-z])"

_TYPE = {"король": chess.KING, "ферзь": chess.QUEEN, "ладья": chess.ROOK, "слон": chess.BISHOP, "конь": chess.KNIGHT,
         "пешка": chess.PAWN, "king": chess.KING, "queen": chess.QUEEN, "rook": chess.ROOK, "bishop": chess.BISHOP,
         "knight": chess.KNIGHT, "pawn": chess.PAWN}
_NAME = {chess.KING: "king", chess.QUEEN: "queen", chess.ROOK: "rook", chess.BISHOP: "bishop", chess.KNIGHT: "knight",
         chess.PAWN: "pawn"}

# «белый король заходит через d5», «он отступит на a6», «пешка идёт на a7», "the white king goes to d5": a move told
# in words, third person, present or future — the line going on. Imperatives and infinitives («поставь ладью на g1»,
# «может уйти на a6») are advice or a possibility, not the line told (src/move_words.py reads those).
_RU_GO = (r"ид[её]т|пойд[её]т|заходит|зайд[её]т|проходит|пройд[её]т|прорывается|прорв[её]тся|вторгается|вторгнется|"
          r"отступает|отступит|отходит|отойд[её]т|уходит|уйд[её]т|вста[её]т|встанет|становится|переходит|перейд[её]т|"
          r"прыгает|прыгнет|возвращается|вернется|бежит|побежит|выходит|выйдет|шагает|шагнет|подходит|подойд[её]т|"
          r"продвигается|продвинется|направляется|двигается|двинется")
_EN_GO = (r"goes|moves|steps|retreats|comes|walks|marches|heads|jumps|enters|penetrates|advances|returns|drops|"
          r"swings|will\s+go|will\s+move|will\s+step|will\s+retreat")
_WORD_MOVE = re.compile(
    _B + r"(?:(?P<side>бел(?:ый|ая)|ч[её]рн(?:ый|ая)|тво[йя]|мо[йя])\s+)?(?P<piece>король|ферзь|ладья|слон|конь|пешка|он|она)"
         rf"(?:\s+(?:с|из)\s+(?P<frm>{SQ}))?"
         r"(?:\s+(?!не\s)[а-я]+){0,2}?\s+(?:" + _RU_GO + r")\s+(?P<prep>на|в|через)\s+(?:пол[ея]\s+)?"
         rf"(?P<to>{SQ})(?![0-9])(?!\s?[-–—]\s?{SQ})"
    r"|(?<![a-z])(?:the\s+)?(?:(?P<en_side>white|black)\s+)?(?P<en_piece>king|queen|rook|bishop|knight|pawn|it)"
    rf"(?:\s+(?:on|from)\s+(?P<en_frm>{SQ}))?"
    r"(?:\s+(?!not\s)[a-z]+)?\s+(?:" + _EN_GO + r")\s+(?P<en_prep>to|into|onto|on|via|through)\s+"
    rf"(?P<en_to>{SQ})(?![0-9])(?!\s?[-–—]\s?{SQ})")  # not a route: «идёт на f2–e3–e4»

# The piece a pronoun («он», «она», "it") stands for: the last piece named before it, of its gender.
_MASC = {"корол": chess.KING, "ферз": chess.QUEEN, "слон": chess.BISHOP, "кон": chess.KNIGHT}
_FEM = {"ладь": chess.ROOK, "пешк": chess.PAWN}
_ANTECEDENT = re.compile(_B + r"(?P<w>корол[ьяюеи]\w*|ферз[ьяюеи]\w*|слон\w{0,3}|кон(?:ь|я|ю|ем|е|и|ей|ям)|"
                         r"ладь[яиюе]\w*|пешк[аиуеоы]\w*|king|queen|rook|bishop|knight|pawn)" + _E)

# A bare «a6» is a square unless a cue says it is played: «лучший ход — b3», «белые играют a6», «ответ — Kd6».
_PLAY_CUE = re.compile(_B + r"(?:ход|ходом|ответ|играют|играет|играешь|сыграют|сыграет|сыграешь|сыграй|играй|ответят|"
                            r"ответит|отвечают|отвечает|ответишь|пойдут|следует|plays?|played|replies|answers?|"
                            r"push(?:es)?)[\s*_`]*[—–:-]?[\s*_`]*$")
_LINE_GAP = re.compile(r"[\s,]*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s*)?")

# Between two moves: a word that starts another branch («или Nc3», «вместо этого», «(1...Kf6 …»), or goes back to the
# board as it is («а сейчас»): the walk stops — what follows may start anywhere.
_ALTERNATIVE = re.compile(_B + r"(?:или|либо|вместо|иначе|альтернатив\w*|другой\s+вариант|в\s+другом|сейчас|на\s+доске|"
                               r"в\s+партии|в\s+исходной|or|instead|otherwise|alternatively|rather|now|currently)" + _E
                          + r"|[(;]")
_SIDE_BEFORE = re.compile(r"(?<![а-яёa-z])(бел(?:ые|ым)|ч[её]рн(?:ые|ым)|white|black)(?:\s+[а-яёa-z]+)?[\s:—–-]*$")
# A condition («а если он отступит на a6»): the next move is followed when it fits the line, never judged itself.
_CONDITION = re.compile(_B + r"(?:если|когда|в\s+случае|бы|if|when|in\s+case|would|could)" + _E)
# Right before a move: «и тогда dxc4», «затем Bg5», "then Bg5" — the line's next move.
_THEN_BEFORE = re.compile(_B + r"(?:тогда|затем|потом|после\s+чего|then|after\s+that)[\s,:—–-]*$")
# The sentence goes on with the line of the one before.
_CONTINUES = re.compile(r"^\W*(?:(?:и|а|и\s+вот|and)\s+)?(?:тогда|затем|потом|далее|дальше|после\s+этого|после\s+чего|"
                        r"then|next|after\s+that|and\s+then)" + _E)
# …or names the position the line reached: «Теперь замри: пешка на a7, ты на d6».
_POINTS_AT_LINE = re.compile(r"^\W*(?:(?:и|а|and)\s+)?(?:теперь|в\s+итоге|в\s+результате|после\s+этого|получается|итак|"
                             r"тогда|at\s+this\s+point|then|as\s+a\s+result)" + _E)
_NOW = re.compile(_B + r"(?:сейчас|на\s+доске|в\s+этой\s+позиции|в\s+партии|right\s+now|on\s+the\s+board|currently)" + _E)
_HYPOTHETICAL = re.compile(_B + r"(?:если|бы|представь\w*|допустим|пусть|вообрази\w*|скажем|if|would|imagine|suppose|say)" + _E)
# A sentence that denies a move («не может зайти на d5», «Kd5 невозможен»): it tells the truth, it is not the line.
_DENIED_MOVE = re.compile(
    r"нельзя|невозможн|не\s+може|не\s+сможет|не\s+получит|не\s+проходит|не\s+пройд|не\s+зайд|не\s+пуст|не\s+да[её]т|"
    r"не\s+даст|нелегальн|не\s+по\s+правилам|illegal|not\s+legal|can'?t|cannot|impossible|isn'?t\s+possible|not\s+allowed")
# A line told as someone's belief or as a mistake, in order to refute it («Многие думают: Kd6 — и белый король
# заходит на d5, но…», «Ошибка новичка — считать, что после Kd6…», «Ты пишешь: …»): not the coach's line (review
# 30.10; the words of src/answer_check._NOT_TOLD for a claim not told as true, «подумай»/«посчитай» left out).
_BELIEF = re.compile(
    _B + r"(?:(?:по)?счита(?:ют|ет|ешь|л\w*|ть)|(?:по)?дума(?:ют|ет|ешь|л\w*|ть)|пишешь|написал\w*|говоришь|сказал\w*|"
         r"предлагаешь|предложил\w*|спрашиваешь|кажется|будто|якобы|по-твоему|уверен\w*|неправда|неверно|ошибк\w*|"
         r"ошибочн\w*|заблужд\w*|многие|новичк\w*|thinks?|thought|believes?|mistake\w*|wrong\w*|you\s+wrote|you\s+say|"
         r"many\s+players|beginners?)" + _E)
# A square after the walk's last move that it did not read («Сыграй Bg5, а на Be7 — e3.», «и затем d3: …», «конь
# перебирается … на g3»): the line went on unread, so where it got to is not known — the next sentence does not go
# on with it and no «piece on square» is judged against it (review 30.10). A square naming a piece or a point
# («пешка e3», «конь f6 связан», «пункт f7», «удар по f7») is not a move, nor a piece said to be where the line has
# put it («а конь на f6 уже не даёт…»).
_SQ_IN = re.compile(rf"(?<![a-z0-9])({SQ})(?![0-9])")
_NAMES_SQUARE = re.compile(r"(?:(?:пешк|кон|слон|ладь|ферз|корол|пункт|пол|клетк|square|pawn|knight|bishop|rook|queen|"
                           r"king)[а-яёa-z]*|(?:^|\s)по)\s+$")
_PIECE_ON = re.compile(r"(?P<w>пешк|кон|слон|ладь|ферз|корол)[а-яё]*\s+(?:(?:уже|теперь|стоит|находится)\s+){0,2}на\s+$")
_STEM_TYPE = {"пешк": chess.PAWN, "кон": chess.KNIGHT, "слон": chess.BISHOP, "ладь": chess.ROOK, "ферз": chess.QUEEN,
              "корол": chess.KING}


def _unread_move(text: str, board: Optional[chess.Board] = None) -> bool:
    if re.search(r"[0oо]-[0oо]", text):
        return True
    for m in _SQ_IN.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        if _NAMES_SQUARE.search(before[-14:]):
            continue
        on = _PIECE_ON.search(before)
        if on is not None and board is not None \
                and board.piece_type_at(chess.parse_square(m.group(1))) == _STEM_TYPE[on["w"]]:
            continue
        return True
    return False


# «пешка на a7, ты на d6», «конь стоит на d4», «чёрный король на e6»: where a piece stands, told plainly — a list or
# a stand verb, the square closing the clause. Not «конь на f3 атакует…» (a claim of its own, judged elsewhere).
_CLOSES = r"(?=\s*(?:[,.;:!?)—–]|$)|\s+(?:и|а|and)\s)"
_STANDS = re.compile(
    _B + r"(?:(?P<side>бел(?:ый|ая)|ч[её]рн(?:ый|ая)|тво[йя]|мо[йя])\s+)?(?P<piece>пешка|конь|слон|ладья|ферзь|король|ты)"
         r"\s+(?:(?:уже|теперь|тогда|по-прежнему|стоит|стоишь|находится|находишься)\s+){0,2}на\s+"
         rf"(?P<sq>{SQ})(?![0-9]){_CLOSES}"
    r"|(?<![a-z])(?:the\s+|your\s+|my\s+)?(?:(?P<en_side>white|black)\s+)?(?P<en_piece>king|queen|rook|bishop|knight|pawn)"
    rf"\s+(?:is|stands|sits)\s+(?:now\s+|still\s+)?on\s+(?P<en_sq>{SQ})(?![0-9]){_CLOSES}"
    rf"|(?<![a-z])you(?:'re|\s+are)\s+(?:now\s+)?on\s+(?P<you_sq>{SQ})(?![0-9]){_CLOSES}")

# Before «piece on square»: a goal or a plan, not the position reached («цель — конь на g5», «идеальная расстановка
# белых: пешка на d4, …», «а потом конь на f3», "the plan is simple: the knight is on g5"; review 30.10).
_PLAN = re.compile(_B + r"(?:цел[ьиюей]|план\w*|иде[яюиейа]\w*|расстановк\w*|напрашива\w*|хоч\w*|хотят|стрем\w*|"
                        r"нужн\w*|надо|долж\w*|будет|будут|потом|затем|дальше|далее|следующ\w*|задач\w*|мечта\w*|"
                        r"goal\w*|plan\w*|idea\w*|aim\w*|setup|wants?|next|later|will|should|need\w*|target\w*)" + _E)
# …and what makes it a position held still, not a move: «Теперь замри: пешка на a7, ты на d6».
_STILL = re.compile(_B + r"(?:замр\w*|стоп|останов\w*|картина|расклад|freeze|stop)" + _E)
_STAND_VERB = re.compile(_B + r"(?:уже|по-прежнему|стоит|стоишь|находится|находишься)" + _E)


def _one_move_to(board: chess.Board, ptype: int, color: Optional[bool], sq: int) -> bool:
    """A *ptype* of *color* (either, None) gets to *sq* in one move of its side from *board* — pseudo-legal, leniently."""
    for c in ((color,) if color is not None else (chess.WHITE, chess.BLACK)):
        b = board.copy(stack=False)
        b.turn = c
        for mv in b.generate_pseudo_legal_moves(to_mask=chess.BB_SQUARES[sq]):
            if b.piece_type_at(mv.from_square) == ptype or mv.promotion == ptype:
                return True
    return False


# Sentences inside one text (the voice check gets a whole utterance): «…Kd6. Теперь замри: …» — not after a move
# number («1. Nf3», «12... Kd6»).
_SENTENCE_END = re.compile(r"[.!?…]+\s+(?=[*_«\"(]*[А-ЯЁA-Z])")
_MOVE_NUMBER_END = re.compile(r"(?:^|[^a-zа-я0-9])\d{1,3}$", re.IGNORECASE)


class _Walk:
    """A line followed strictly from a given position: the boards along it and its moves."""

    def __init__(self, start: chess.Board):
        self.start = start.copy(stack=False)
        self.board = start.copy(stack=False)
        self.boards = [self.board.copy(stack=False)]
        self.moves: list = []
        self.branched = False
        # Other given positions the first move fitted as well (the start position on the board and a lesson's on the
        # screen): a move impossible on this line but possible on the same line from one of them is not judged.
        self.alts: list = []

    def push(self, move: chess.Move) -> None:
        self.board.push(move)
        self.moves.append(move)
        self.boards.append(self.board.copy(stack=False))

    def label(self) -> str:
        return self.start.variation_san(self.moves)

    def copy(self) -> "_Walk":
        """The line to go on with in a new sentence: the one before stays as it was if this sentence is not shown."""
        out = _Walk(self.start)
        out.board = self.board.copy(stack=False)
        out.boards = list(self.boards)
        out.moves = list(self.moves)
        out.branched = self.branched
        out.alts = self.alts
        return out

    def possible_from_another_start(self, attempt) -> bool:
        sans = []
        b = self.start.copy(stack=False)
        for mv in self.moves:
            sans.append(b.san(mv))
            b.push(mv)
        for alt in self.alts:
            b = alt.copy(stack=False)
            try:
                for san in sans:
                    b.push_san(san)
            except ValueError:
                continue
            if attempt(b) is not None:
                return True
        return False


def _side_word(word: Optional[str]) -> Optional[bool]:
    w = (word or "").lower()
    if w.startswith(("бел", "white")):
        return chess.WHITE
    if w.startswith(("чёрн", "черн", "black")):
        return chess.BLACK
    return None


def _as_mover(board: chess.Board, color: bool) -> Optional[chess.Board]:
    """*board* with *color* to move (a copy when that is not so), None when that position is not a legal one."""
    if board.turn == color:
        return board
    b = board.copy(stack=False)
    b.turn = color
    b.ep_square = None
    return b if b.is_valid() else None


# «4.a8», «a8=Ф» (the Cyrillic piece not read): a pawn's move to the last rank written without the piece is its
# promotion — to a queen, as _word_moves takes it (review 30.10: «4.a8 — и у белых новый ферзь» was cut).
_BARE_PROMOTION = re.compile(r"^[a-h](?:x[a-h])?[18][+#]?$")


def _parse(board: Optional[chess.Board], san: str) -> Optional[chess.Move]:
    if board is None:
        return None
    try:
        return board.parse_san(san)
    except ValueError:
        pass
    if _BARE_PROMOTION.match(san):
        try:
            return board.parse_san(san.rstrip("+#") + "=Q")
        except ValueError:
            return None
    return None


def _ambiguous(board: chess.Board, san: str) -> bool:
    try:
        board.parse_san(san)
    except chess.AmbiguousMoveError:
        return True
    except ValueError:
        return False
    return False


def _word_moves(board: chess.Board, color: bool, ptype: int, to: int, frm: Optional[int] = None) -> list:
    b = _as_mover(board, color)
    if b is None:
        return []
    return [mv for mv in b.legal_moves if mv.to_square == to and b.piece_type_at(mv.from_square) == ptype
            and (frm is None or mv.from_square == frm) and mv.promotion in (None, chess.QUEEN)]


def _reaches(board: chess.Board, color: bool, ptype: int, to: int, capture: Optional[bool] = None) -> bool:
    """Some *ptype* of *color* gets to *to* by its move pattern, whatever stands in the way: the move is one move of
    that side's, not a route («король идёт на f5» from h1) — a pawn by a step, a double step or a capture."""
    from src.answer_check import _geometry_move, _pawn_reaches

    for sq in board.pieces(ptype, color):
        if ptype == chess.PAWN:
            if (capture is not True and _pawn_reaches(color, sq, to, False)) \
                    or (capture is not False and _pawn_reaches(color, sq, to, True)):
                return True
        elif _geometry_move(ptype, sq, to):
            return True
    return False


def _pinned_or_check(board: chess.Board, color: bool, pieces: list, to: int) -> Optional[str]:
    """The move is one of the piece's own but leaves its king in check: a pin, or a check it does not answer."""
    b = _as_mover(board, color)
    if b is None:
        return None
    # Only a move of the piece's own that is not legal: a pseudo-legal move that is legal (a promotion read without
    # its piece) has no pin or check to tell — the reason is then not this one (review 30.10: «4.a8» was said to
    # «leave the white king in check» with no check anywhere).
    pseudo = [mv for mv in b.generate_pseudo_legal_moves() if mv.to_square == to and mv.from_square in pieces
              and b.piece_type_at(mv.from_square) != chess.KING and not b.is_legal(mv)]
    if not pseudo:
        return None
    frm = pseudo[0].from_square
    side = "white" if color == chess.WHITE else "black"
    if b.is_pinned(color, frm):
        ray = b.pin(color, frm)
        pinner = next((s for s in ray if b.piece_at(s) is not None and b.color_at(s) != color), None)
        if pinner is not None:
            return (f"the {_NAME[b.piece_type_at(frm)]} on {chess.square_name(frm)} is pinned to the {side} king by the "
                    f"{_NAME[b.piece_type_at(pinner)]} on {chess.square_name(pinner)}")
    if b.is_check():
        return f"the {side} king is in check, and that move does not answer it"
    return f"it would leave the {side} king in check" if b.is_into_check(pseudo[0]) else None


def _why_not(board: chess.Board, color: bool, ptype: int, to: int, capture: bool, walk: "_Walk",
             hint: str = "") -> str:
    """Why no *ptype* of *color* can go to *to* on *board*, and what such a piece can do there instead. *hint*: the
    file or rank a SAN names its piece by («bxc4»: the b-pawn)."""
    side, other = ("white", "black") if color == chess.WHITE else ("black", "white")
    name, sq = _NAME[ptype], chess.square_name(to)
    pieces = [s for s in board.pieces(ptype, color) if not hint or hint in chess.square_name(s)]
    there = board.piece_at(to)
    if not pieces:
        why = f"there is no such {side} {name} there"
    elif there is not None and there.color == color:
        why = f"{sq} is taken by the {side} {_NAME[there.piece_type]}"
    elif capture and there is None and not (ptype == chess.PAWN and board.ep_square == to):
        why = f"{sq} is empty — there is nothing to take there"
        left = next((i for i, mv in enumerate(walk.moves) if mv.from_square == to), None)
        if left is not None:
            moved = walk.boards[left + 1].piece_at(walk.moves[left].to_square)
            if moved is not None:
                why += f" (the {_NAME[moved.piece_type]} has gone from {sq} to {chess.square_name(walk.moves[left].to_square)})"
    elif _pinned_or_check(board, color, pieces, to):
        why = _pinned_or_check(board, color, pieces, to)
    elif ptype == chess.KING and board.is_attacked_by(not color, to):
        att = sorted(board.attackers(not color, to))
        kings = [a for a in att if board.piece_type_at(a) == chess.KING]
        a = kings[0] if kings else att[0]
        why = (f"{sq} is next to the {other} king on {chess.square_name(a)}" if kings
               else f"{sq} is attacked by the {other} {_NAME[board.piece_type_at(a)]} on {chess.square_name(a)}")
    else:
        why = f"no {side} {name} can go to {sq} from where it stands ({', '.join(chess.square_name(s) for s in pieces)})"
        if ptype in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            from src.answer_check import _geometry_move

            for s in pieces:
                if _geometry_move(ptype, s, to):
                    block = next((b for b in chess.SquareSet.between(s, to) if board.piece_at(b) is not None), None)
                    if block is not None:
                        why = (f"the {_NAME[board.piece_type_at(block)]} on {chess.square_name(block)} stands between "
                               f"the {name} on {chess.square_name(s)} and {sq}")
                        break
    b = _as_mover(board, color)
    legal = sorted({b.san(mv) for mv in b.legal_moves if mv.from_square in pieces}) if b is not None else []
    if legal:
        what = f"the {side} {name}" if len(pieces) == 1 else f"the {side} {name}s"
        why += f"; legal moves of {what} there: {', '.join(legal[:8])}"
    return why


def _legal_on_given(ctx, san: Optional[str], ptype: int, to: int, color: Optional[bool],
                    number: Optional[tuple] = None) -> bool:
    """The move is legal in some position given to the turn (for the side named, else either): the sentence may have
    gone back to the board as it is. Not the start position standing in for unknown ones (every context has it: any
    first move of a pawn or a knight would pass), and for a numbered move («9.dxc4») only a position at that move
    (*number*: side, move number) — review 30.10: «… 6.e5 d5 7.Nc3» passed on the start position, «8.Be3 Ba6
    9.dxc4» on the board at move 8."""
    for board in getattr(ctx, "boards", []):
        if not ctx.is_given(board):
            continue
        if board is not ctx.current and board.board_fen() == chess.STARTING_BOARD_FEN:
            continue
        if number is not None and (board.turn != number[0] or board.fullmove_number != number[1]):
            continue
        for c in ((color,) if color is not None else (chess.WHITE, chess.BLACK)):
            if san is not None:
                if _parse(_as_mover(board, c), san) is not None:
                    return True
            elif _word_moves(board, c, ptype, to):
                return True
    return False


def _antecedent(low: str, at: int, pronoun: str) -> Optional[int]:
    table = _MASC if pronoun == "он" else _FEM if pronoun == "она" else None
    for m in reversed(list(_ANTECEDENT.finditer(low[:at]))):
        w = m["w"]
        if table is None:  # "it"
            if w in _TYPE:
                return _TYPE[w]
            continue
        for stem, ptype in table.items():
            if w.startswith(stem):
                return ptype
    return None


def _tokens(sentence: str):
    """The text in SAN letters, lower-cased, and its moves in order: (start, end, kind, data) — *kind* 'san' (data:
    san, number, dots) or 'word' (data: the match)."""
    from src.answer_check import _MATE_WORD, _MOVE, _to_san

    converted, cyr_k = _to_san(sentence)
    if _MATE_WORD.search(converted):
        cyr_k = set()  # the positions move once «#» is written in; «Кh1» for the king is then not looked for
        converted = _MATE_WORD.sub(lambda mm: mm.group("san") + "#" + mm.group("rest"), converted)
    low = converted.lower()
    out = []
    last_end = -1
    for m in _MOVE.finditer(converted):
        san = m["san"]
        if not (m["num"] or m["bdots"]) and san[0] not in "KQRBNO" and "x" not in san:
            follows = last_end >= 0 and _LINE_GAP.fullmatch(converted[last_end:m.start()])
            if not (follows or _PLAY_CUE.search(low[max(0, m.start() - 30):m.start()])):
                continue  # «e4» without a number is a square, not a move
        # «Кh1»: the Russian К is a knight, but models write it for the king too (src/answer_check._san_issues_all)
        alt = "K" + san[1:] if m.start("san") in cyr_k else None
        out.append((m.start(), m.end(), "san", (san + (m["check"] or ""), m["num"], m["dots"] or m["bdots"], alt)))
        last_end = m.end()
    for m in _WORD_MOVE.finditer(low):
        if not any(s < m.end() and m.start() < e for s, e, _k, _d in out):
            out.append((m.start(), m.end(), "word", m))
    out.sort(key=lambda t: t[0])
    return converted, low, out


def _given_starts(ctx, numbered: bool = False) -> list:
    """The positions a line may start from: the board on the screen first, then the others given to the turn and
    shown (a position a tool put on the screen, the end of a game or a line) — not the start position standing in
    for unknown ones, not a position only named in a tool's text (a lesson's diagram: its line is another
    position's), not a position on the way through a game unless the move's number says so («12.Nf3»)."""
    out = [ctx.current]
    passed = getattr(ctx, "passed_keys", set())
    for b in ctx.boards:
        if b is ctx.current or not ctx.is_given(b) or b.board_fen() == chess.STARTING_BOARD_FEN:
            continue
        key = ctx._key(b)
        if key in getattr(ctx, "shown_keys", set()) and (numbered or key not in passed):
            out.append(b)
    return out


def age_scene(ctx) -> None:
    """A new sentence: the line of the one before is one sentence older."""
    scene = getattr(ctx, "line_scene", None)
    if scene is not None:
        scene["age"] = scene.get("age", 0) + 1


def scene_issues(sentence: str, ctx) -> list[str]:
    """Moves after a written line that are impossible where the line got to, and pieces said to stand where it put
    none. Keeps the line in *ctx.line_scene* for the next sentence."""
    if ctx is None or getattr(ctx, "current", None) is None:
        return []
    issues: list[str] = []
    text = sentence.replace("ё", "е")
    cuts = [m.end() for m in _SENTENCE_END.finditer(text) if not _MOVE_NUMBER_END.search(text[:m.start()])]
    parts = [p for p in (text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])) if p.strip()]
    for i, part in enumerate(parts):
        if i:
            age_scene(ctx)
        issues += _one_sentence(part, ctx)
    return issues


def _side_of(word: Optional[str], ctx) -> Optional[bool]:
    """The side a word names: «белый», «чёрная», "white"; «твой»/«мой» when the student's colour is known."""
    w = (word or "").lower()
    if w.startswith(("тво", "мо")):
        student = getattr(ctx, "student_color", None)
        return None if student is None else (not student if w.startswith("мо") else student)
    return _side_word(w)


def _one_sentence(text: str, ctx) -> list[str]:
    from src.answer_check import _LONG

    prev = getattr(ctx, "line_scene", None)
    fresh = prev if prev is not None and prev.get("age", 9) <= 1 and not prev["walk"].branched else None
    converted, low, tokens = _tokens(text)
    longs = [(m.start(), m.end()) for m in _LONG.finditer(converted) if m["piece"] or m["num"] or m["bdots"]]
    question = text.rstrip().endswith("?")
    denied = _DENIED_MOVE.search(low) is not None
    continues = bool(_CONTINUES.match(low))
    issues: list[str] = []
    walk: Optional[_Walk] = None
    made = 0  # moves the walk had before this sentence (a line of the sentence before, gone on with)
    last_end = 0

    for start, end, kind, data in tokens:
        if any(s <= start < e for s, e in longs):
            if walk is not None:
                walk.branched = True  # «d7-d6»: a move written from-to — followed elsewhere (src/answer_check._long_issues)
            break
        if walk is None and re.search(rf"(?<![a-z0-9]){SQ}[\s,]*$", low[max(0, start - 8):start]):
            break  # «e4 c5 Nf3 …»: the line began with moves not read as moves — where it starts is not known
        gap = low[last_end:start] if walk is not None else ""
        if walk is not None and (_ALTERNATIVE.search(gap) or re.search(rf"(?<![a-z0-9]){SQ}(?![0-9])", gap)
                                 or re.search(r"[0oо]-[0oо]", gap)):
            walk.branched = True  # another branch, the board as it is, a square or «0-0» between: a move not read
            break
        conditional = walk is not None and (_CONDITION.search(gap) is not None or len(gap) > 80)
        side, ptype, to, frm, capture = None, None, None, None, None
        if kind == "san":
            san, num, dots, alt = data
            want = None if not num else (chess.WHITE if dots == "." else chess.BLACK)
            # The side a move is told for: its number («2.Kd5»), or «белые играют …» right before it.
            said = _SIDE_BEFORE.search(low[max(last_end, start - 30):start])
            side = want if want is not None else (_side_word(said.group(1)) if said else None)
            capture = True if "x" in san else (False if san[0] in "abcdefgh" else None)
            to = chess.parse_square(re.findall(SQ, san)[-1]) if not san.startswith("O-O") else None
            ptype = (chess.PIECE_SYMBOLS.index(san[0].lower()) if san[0] in "KQRBN" else chess.PAWN) if to is not None else None

            def attempt(board, san=san, num=num, want=want, alt=alt, side=side):
                if want is not None and (board.turn != want or board.fullmove_number != int(num)):
                    return None  # a numbered move from another point of the game
                if side is not None and board.turn != side:
                    return None
                for written in (san, alt) if alt else (san,):
                    mv = _parse(board, written)
                    if mv is not None and "x" in written and not board.is_capture(mv):
                        mv = None  # «Bxe3» with nothing on e3 is not this move
                    if mv is not None:
                        return mv
                return None
        else:
            m = data
            word = m["piece"] or m["en_piece"]
            side = _side_of(m["side"] or m["en_side"], ctx)
            if (m["side"] or "").startswith(("тво", "мо")) and side is None:
                if walk is not None:
                    walk.branched = True  # «твой король» with the student's colour unknown: whose is not known
                break
            to = chess.parse_square(m["to"] or m["en_to"])
            frm_name = m["frm"] or m["en_frm"]
            frm = chess.parse_square(frm_name) if frm_name else None
            ptype = _antecedent(low, start, word) if word in ("он", "она", "it") else _TYPE.get(word)
            via = (m["prep"] or m["en_prep"]) in ("через", "via", "through")
            if ptype is None or (via and ptype != chess.KING):
                if walk is not None:
                    walk.branched = True  # «он» with nothing to name; a piece passing a square on its way
                break
            if walk is not None and walk.moves:
                last = walk.moves[-1]
                if last.to_square == to and walk.board.piece_type_at(to) == ptype:
                    last_end = end
                    continue  # «Rh7# — ладья заходит на h7»: the move just written, told in words

            def attempt(board, ptype=ptype, to=to, side=side, frm=frm):
                if side is not None and side != board.turn:
                    return None
                moves = _word_moves(board, board.turn, ptype, to, frm)
                return moves[0] if len(moves) == 1 else None

        if walk is None:
            # The first move: on the line of the sentence before when the sentence goes on with it, else on a
            # position given to the turn — the board on the screen first.
            use_prev = fresh is not None and not _NOW.search(low[:start])
            boards = ([fresh["walk"].board] if use_prev else []) + _given_starts(ctx, kind == "san" and bool(data[1]))
            if kind == "san" and data[1] == "1" and data[2] == ".":
                boards.append(chess.Board())  # «1.e4 e5 2.Nf3 …» from the first move
            found = [b for b in boards if attempt(b) is not None]
            if continues and not use_prev:
                break  # «Дальше идёт Rf3+» after moves not followed: the line goes on from a position not known
            if use_prev and (not found or found[0] is not fresh["walk"].board) and continues:
                walk, made = fresh["walk"].copy(), len(fresh["walk"].moves)  # «Тогда …»: the line goes on, whatever fits
            elif not found:
                break
            elif use_prev and found[0] is fresh["walk"].board:
                if len(found) > 1 and not continues:
                    break  # it fits the line before and a given position as well: which one is not known
                walk, made = fresh["walk"].copy(), len(fresh["walk"].moves)
            else:
                if len({b.fen() for b in found}) > 1 and found[0] is not ctx.current:
                    break  # legal in several positions given to the turn: which one is not known
                if any(attempt(b) is not None for b in ctx.boards if ctx._key(b) in getattr(ctx, "text_keys", set())
                       and ctx._key(b) != ctx._key(found[0])):
                    break  # it fits a position a tool named too (a lesson's diagram): the line may be that one's
                walk = _Walk(found[0])
                walk.alts = [b for b in found[1:] if b.fen() != found[0].fen()]
        mv = attempt(walk.board)
        if mv is not None:
            walk.push(mv)
            last_end = end
            continue

        # Not a move of the side to move where the line is: judged only when it cannot be anything else.
        walk.branched = True
        board, mover = walk.board, (side if side is not None else walk.board.turn)
        if to is None or conditional or question or denied or (len(walk.moves) <= made and not continues) \
                or re.match(r"[*_]*\?", converted[end:end + 4]) or _BELIEF.search(low[:start]):
            break  # «Kd5?»: a move the coach warns against is not his line; «многие думают: …» — not his either
        if kind == "san":
            if data[1] and (board.turn != want or board.fullmove_number != int(data[1])):
                break  # «2.Kc3» where the line is at another move: a branch, or one side's moves listed
            if data[0].rstrip("+#") in {q.rstrip("+#") for q in getattr(ctx, "quoted", set())} or _ambiguous(board, data[0]):
                break
            if data[0][0] == "K" and _parse(board, "N" + data[0][1:]) is not None or alt:
                break  # a Latin K for the Russian К (конь), a Russian К for the king: which piece is not known
        if side is not None and side != board.turn:
            break  # the other side's move: a plan told one side at a time
        if side is None and _reaches(board, not board.turn, ptype, to, capture):
            break  # the side that has just moved could mean it too («после Rf1 ладья перейдёт на f2»: a plan)
        if not _reaches(board, mover, ptype, to, capture):
            break  # no such piece gets there in one move: a route or a plan («король идёт на f5» from h1)
        if len(_word_moves(board, mover, ptype, to, frm)) > 1:
            break
        if walk.possible_from_another_start(attempt):
            break  # the same line from another position given to the turn goes on with it: the line may be that one's
        # The move is made on the board as it is: the sentence may have gone back to it — not when it is told as the
        # line's own next move, by its number («7.Nc3»), by the side named («Kd6 — и белые играют e4») or by «и
        # тогда» right before it («слон отступает на a6, и тогда dxc4»): those go on with the line (review 30.10).
        told_next = (side is not None and (kind == "word" or bool(_SIDE_BEFORE.search(low[max(last_end, start - 30):start])))
                     or _THEN_BEFORE.search(low[last_end:start]) is not None)
        if kind == "san" and data[1]:
            if _legal_on_given(ctx, data[0], ptype, to, side, (want, int(data[1]))):
                break
        elif not told_next and _legal_on_given(ctx, data[0] if kind == "san" else None, ptype, to, side):
            break
        if kind == "san":
            san = data[0]
            hint = ""
            if ptype == chess.PAWN and "x" in san:
                hint = san[0]
            elif ptype != chess.PAWN:
                hint = re.match(r"[KQRBN]([a-h1-8]?)(?=x?[a-h][1-8])", san).group(1)
            why = _why_not(board, mover, ptype, to, "x" in san, walk, hint)
            issues.append(f"after {walk.label()} (the line written here) {san} is impossible: {why}")
        else:
            why = _why_not(board, mover, ptype, to, False, walk)
            issues.append(f"after {walk.label()} (the line written here) the {'white' if mover else 'black'} "
                          f"{_NAME[ptype]} cannot go to {chess.square_name(to)}: {why}")
        break

    issues += _stands_issues(low, bool(tokens), walk, fresh, last_end, ctx)
    if walk is not None and not walk.branched and (_unread_move(low[last_end:], walk.board) or _BELIEF.search(low)):
        walk.branched = True  # moves after it not read, or someone else's line: the next sentence does not go on with it
    if walk is not None and walk.moves:
        ctx.line_scene = {"walk": walk, "age": 0}
    return issues


def _stands_issues(low: str, has_moves: bool, walk: Optional[_Walk], fresh, last_end: int, ctx) -> list[str]:
    """«пешка на a7, ты на d6» about the position the line reached: some board of the line or of the turn has such a
    piece there."""
    if low.rstrip().endswith("?"):
        return []
    if has_moves:
        if walk is None or walk.branched or not walk.moves:
            return []
        scope_from = last_end  # after this sentence's own line: the clauses right after its last move
    else:
        if fresh is None or not _POINTS_AT_LINE.match(low) or _NOW.search(low):
            return []
        walk, scope_from = fresh["walk"], 0
    out = []
    gap, prev_end = "", scope_from
    for m in _STANDS.finditer(low, scope_from):
        gap += low[prev_end:m.start()] + " "  # the text between the line and this clause, other clauses left out
        prev_end = m.end()
        if _HYPOTHETICAL.search(gap) or _ALTERNATIVE.search(gap) or _unread_move(gap, walk.board):
            break  # imagined, another branch, or a move the walk did not read: not the position it reached
        if _PLAN.search(low[:m.start()]) or _BELIEF.search(low[:m.start()]):
            break  # a goal or a plan («цель — конь на g5», «идеальная расстановка: …»), someone else's belief
        if re.search(r"(?:^|\s)(?:не|ни|not)\s+$", low[max(0, m.start() - 6):m.start()]):
            continue
        word = m["piece"] or m["en_piece"] or ("ты" if m["you_sq"] else None)
        sq_name = m["sq"] or m["en_sq"] or m["you_sq"]
        side_w = m["side"] or m["en_side"] or ""
        color = _side_word(side_w)
        if word == "ты" or side_w.startswith(("тво", "мо")):
            student = getattr(ctx, "student_color", None)
            color = None if student is None else (not student if side_w.startswith("мо") else student)
        ptype = chess.KING if word == "ты" else _TYPE.get(word)
        if ptype is None:
            continue
        sq = chess.parse_square(sq_name)
        # «Тогда конь на f3, а слон на c4», «Теперь ферзь на f7 — мат»: a piece named on a square it gets to in one
        # move from where the line is is the next move told the Russian way, not where the line stands — judged
        # only when told as standing («стоит», «уже», "is on") or the position is held still («Теперь замри: …»).
        still = _STILL.search(low[:m.start()]) or _STAND_VERB.search(m.group(0)) or m["en_piece"] or m["you_sq"]
        if not still and _one_move_to(walk.board, ptype, color, sq):
            continue
        boards = list(walk.boards) + _given_starts(ctx, numbered=True)
        if any((pc := b.piece_at(sq)) is not None and pc.piece_type == ptype and (color is None or pc.color == color)
               for b in boards):
            continue
        end = walk.board
        where = [chess.square_name(s) for s in (end.pieces(ptype, color) if color is not None
                                                 else end.pieces(ptype, chess.WHITE) | end.pieces(ptype, chess.BLACK))]
        kind = ("" if color is None else ("white " if color else "black ")) + _NAME[ptype]
        there = (f"the {kind} stands on {where[0]}" if len(where) == 1 else
                 f"the {kind}s stand on {', '.join(where)}" if where else f"there is no {kind} at all")
        out.append(f"after {walk.label()} (the line written) there is no {kind} on {sq_name}: {there} — the line does "
                   f"not reach the position named; give the moves that lead there or describe the position it reaches")
    return out
