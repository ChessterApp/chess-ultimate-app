"""Which side the student plays — decided once per turn by the server, from what it knows exactly (06.11).

The old bug: a question that tells the opponent's move — «Они сыграли f5. Брать?», «Белые поставили коня на d5»,
"They played f5", «Олар f5 жүрді» — made the student the side that had just moved. The server read every move «already
played» as the student's own (src/server: «Я сыграл Qb6. Это мат?»), so the answer check cut «Твой конь b5 нападает на
c7» as Black's knight and the rewrite was told the wrong side (shipped1104/fp t25, t46, t28). The side was decided in
four places, each with its own guess; now it is decided here, and the one decision goes to the model (a turn-context
block, the rewrite's side note) and to the answer check (CheckContext.student_color).

What decides, strongest first:

1. **A game against the coach on the board** — its ``student_color`` (live or finished). **A database game on the
   board** (a master game) is nobody's: no word of the student's gives a side of it — «они сыграли Ba4», «я бы сыграл
   d4», «как играть за белых в этой партии?» (review 06.11).
2. **The student says their side** — «я играю чёрными», «я за белых», «у меня белые», «что делать чёрными?»,
   "I'm Black", "I play as White", "what should I play as Black?", «мен ақпен ойнаймын», «қаралар үшін не істеу
   керек?». A colour as an object is no side: «Я белых поймал?», «Я белым отдал пешку», «қаралар үшін қауіп бар ма?».
3. **The student tells who made a move** — «я сыграл Qb6», «я пошёл конём», "I played Nb5", «мен e4 жүрдім» (the
   student made it) or «они сыграли f5», «соперник взял на c5», "they replied f5", «олар f5 жүрді», «қарсылас …» (the
   opponent made it). The move's colour is read off the board, never guessed: in the board's record (the PGN on the
   screen) or by the piece that stands on the square after a move told as done; by who can play it now for a move
   to come. «Он/она», "he/she" and a colour as the subject («Белые сыграли …», "White played …") are not counted
   and block an earlier «я» («Я думаю, белые сыграли Ba4 зря»): «он» is often a piece, and «почему белые сыграли
   Bxf7?» is asked about master games the student is not playing. A subject counts only as the subject of a move
   verb in its own clause («я сыграл», «если я возьму», "they replied", «олар … жүрді»): «я боюсь Ng5», "how can I
   stop Ng5?", «что угрожает сопернику после Nf3?», «движок советует Nf3» tell no mover (review 06.11). «Сыграл Qb6.
   Это мат?» — a singular past verb opening its clause with no subject — is the student's own move, as Russian drops
   the «я». A move told only by its square («я взял на c6») is the colour of every arrival there that the clause fits
   (a capture, «слоном», «коня») — after 4.Bxc6 dxc6 it is either side's, so none (review 06.11).
4. Otherwise **the side to move** on the board — a guess (``exact`` False): the checks keep their own reading of
   the sentence then (src/answer_check.student_side), and the model is not told a side it was not told.

Signals that disagree (the student says Black, the move told says White) leave the side unknown.

COACH_STUDENT_SIDE (off | shadow | on, default shadow; ``applied``): in shadow the decision is logged every turn but
reaches the checks and the model only where the server pinned the side before (a game; a move of the question
«already played» on the board — the 2026-10-08 rule), so it can correct that pin with the pin's own move or a side
the student said («Они сыграли f5», t25) or drop it («Белые поставили коня на d5», t46) but never pins a new class of
questions. Where nothing is told about the move («Qxf7 — это мат?») the pin stays in every mode. ``on`` uses the
decision everywhere. A master game on the board (src/answer_check_db.note_board_game, also one loaded mid-turn) is
nobody's in both.

The board's orientation is not a signal: the site flips its board locally and never tells the server, and a study
board is created «white» by default — it says nothing about the student.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import chess

@dataclass(frozen=True)
class StudentSide:
    """The decision: ``color`` (chess.WHITE / chess.BLACK / None), ``source`` and the words of the message that
    decided it."""

    color: Optional[bool]
    # game, said, own_move, their_move (exact); master_game, other_mover, conflict (the move «already played» is
    # known not to be the student's, or the signals disagree: no side); side_to_move, none (nothing told); legacy
    # (the 04.11 pin, ``applied``)
    source: str
    evidence: str = ""
    # The moves of the board's record that decided it (own_move / their_move / other_mover): SAN, or «@c6» for a
    # square told alone — ``applied`` lets them correct the 04.11 pin only when they are the move that set it.
    moves: tuple = ()

    @property
    def exact(self) -> bool:
        """Known, not guessed: the game, or the student's own words."""
        return self.color is not None and self.source in ("game", "said", "own_move", "their_move", "legacy")

    @property
    def name(self) -> str:
        return "" if self.color is None else ("White" if self.color else "Black")

    def why(self) -> str:
        """Why the server knows it, in a few words (for the model and the rewrite)."""
        if self.source == "game":
            return "the game against the coach on the board"
        if self.source == "said":
            return f"the student said so: «{self.evidence}»"
        if self.source == "own_move":
            return f"the student told their own move: «{self.evidence}»"
        if self.source == "their_move":
            return f"the student told the opponent's move: «{self.evidence}»"
        if self.source == "side_to_move":
            return "the side to move on the board"
        if self.source == "legacy":
            return "the side that just made the move the student asked about"
        return ""

    def note(self, board: Optional[chess.Board] = None) -> str:
        """The turn-context block for the model; "" unless the side is known exactly (in a game the game block says
        it already)."""
        if not self.exact or self.source in ("game", "legacy"):
            return ""
        name, other = ("White", "Black") if self.color else ("Black", "White")
        lines = [
            "## The student's side (decided by the server — do not guess another)",
            f"The student plays {name} ({self.why()}). «ты», «твой», «у тебя», \"you\", \"your\", «сен», «сенің» mean "
            f"{name}; {other} is the opponent («соперник», «они», \"they\", «қарсылас»). Talk from {name}'s side and "
            f"advise only {name}'s moves.",
        ]
        if board is not None and board.turn != self.color:
            lines.append(f"On the board it is {other}'s (the opponent's) move now, not the student's.")
        return "\n".join(lines)


# ── 2. the student says their side ─────────────────────────────────────────────────────────────────────────────

_W_RU, _B_RU = r"бел(?:ые|ых|ыми|ым)", r"черн(?:ые|ых|ыми|ым)"
_SAID_RU = re.compile(
    r"(?<![а-я])(?:"
    # «я играю чёрными», «играю за белых», «я сейчас играю белыми», «мы играем за чёрных»
    rf"(?:я\s+|мы\s+)?(?:сейчас\s+|тут\s+|здесь\s+)?(?:игра(?:ю|ем)|сыгра(?:ю|ем)|выступа(?:ю|ем))\s+(?:сейчас\s+)?(?:за\s+)?(?P<c1>{_W_RU}|{_B_RU})"
    # «я за белых», «я белыми», «я — чёрные», «я играл(а) белыми»: «за + genitive», the instrumental (not of pieces:
    # «я белыми пешками атакую») or the nominative ending its clause. A bare genitive or dative is an object —
    # «Я белых поймал?», «Я белым отдал пешку», «Я чёрных не боюсь» (review 06.11)
    r"|я\s+(?:[—–-]\s+)?(?:сам\w*\s+)?(?:игра(?:л|ла|ли)\s+)?"
    r"(?P<c2>за\s+(?:белых|черных)|(?:белыми|черными)(?!\s+(?:пешк|пешек|фигур|слон|кон|ладь|ладей|ферз|корол))"
    r"|(?:белые|черные)(?=\s*(?:[.,;:!?)—–]|$)))"
    # «у меня белые», «мои — чёрные», «мой цвет белые», «моя сторона — чёрные»
    # — the phrase ends at the colour: «у меня белые поля слабые», «мои белые слоны» say nothing of the side
    rf"|(?:у\s+меня|мои(?:\s+фигуры)?|мой\s+цвет|моя\s+сторона)\s+(?:[—–:-]\s+)?(?:сейчас\s+)?(?P<c3>{_W_RU}|{_B_RU})"
    r"(?![а-я]|\s*-|\s+(?:пол[еяю]\w*|клет\w*|квадрат\w*|диагонал\w*|слон\w*|кон[ьяюе]\w*|ладь\w*|ладей|ферз\w*|"
    r"корол\w*|пешк\w*|пешек|фигур\w*\s+(?:слаб|сильн|плох|хорош|стоят|активн|пассивн)\w*))"
    # «что делать чёрными?», «как играть за белых», «чем ходить белыми», «что мне сыграть за чёрных» — the
    # instrumental or «за + genitive» only: «как атаковать чёрных?» names the side attacked, not the student's
    rf"|(?:делать|играть|ходить|сыграть|пойти|отвечать|защищаться|атаковать|продолжать)\s+(?:мне\s+|теперь\s+|здесь\s+|тут\s+|дальше\s+)?"
    r"(?P<c4>за\s+(?:белых|черных)|белыми|черными)"
    ")(?![а-я])",
    re.IGNORECASE)
# The colour ends the phrase: "I have black's knight pinned", "I have the white-squared bishop", "I'm white-washing"
# say nothing of the student's side.
_EN_COLOUR_END = r"(?![a-z'’-]|\s+(?:squares?|squared|bishops?|knights?|rooks?|queens?|kings?|pawns?|diagonals?)(?![a-z]))"
_SAID_EN = re.compile(
    r"(?<![a-z])(?:"
    rf"i(?:'m|\s+am)\s+(?:playing\s+)?(?:as\s+|with\s+)?(?:the\s+)?(?P<c1>white|black){_EN_COLOUR_END}"
    rf"|i\s+(?:play|played|was\s+playing|have)\s+(?:as\s+|with\s+)?(?:the\s+)?(?P<c2>white|black){_EN_COLOUR_END}"
    rf"|my\s+(?:side|colou?r|pieces)\s+(?:is|are)\s+(?:the\s+)?(?P<c3>white|black){_EN_COLOUR_END}"
    # "what should I play as Black?", "how do I defend as White", "how to play with Black" — the student playing:
    # "What's the best move for Black here?" asks about a side, often the opponent's reply
    r"|(?:(?:i|we)\s+(?:\w+\s+)?|how\s+to\s+)(?:play|defend|attack|continue)\s+(?:here\s+|now\s+|next\s+|on\s+)?"
    rf"(?:as|with)\s+(?:the\s+)?(?P<c4>white|black){_EN_COLOUR_END}"
    r")(?![a-z])",
    re.IGNORECASE)
_W_KK, _B_KK = r"ақ(?:тар|пен|тармен|қа|тарға)?", r"қара(?:лар|мен|лармен|ға|ларға)?"
_SAID_KK = re.compile(
    r"(?<![а-яәғқңөұүһі])(?:"
    # «мен ақпен ойнаймын», «қаралармен ойнап жатырмын», «ақ тастармен ойнаймын»
    rf"(?:мен\s+)?(?P<c1>{_W_KK}|{_B_KK})(?:\s+тас(?:тар)?(?:мен|пен)?)?\s+ойна(?:ймын|п\s+жатырмын|дым|ймыз)"
    # «менде ақтар», «менің түсім — қара»
    rf"|(?:менде|менің\s+түсім)\s+(?:[—–:-]\s+)?(?P<c2>{_W_KK}|{_B_KK})"
    # «қаралар үшін не істеу керек?», «ақтар үшін қалай ойнаймын?» — playing for the side: «қаралар үшін қауіп бар ма?»
    # («is there danger for Black?») asks about a side, as "for Black" does (review 06.11)
    r"|(?P<c3>ақтар|қаралар)\s+үшін\s+(?:\S+\s+){0,2}?(?:істе|ойна|жүр)[а-яәғқңөұүһі]*"
    ")(?![а-яәғқңөұүһі])",
    re.IGNORECASE)
_NEGATED = re.compile(r"(?:(?<![а-яa-z])не|not|n't|never|емес)\s*$", re.IGNORECASE)


def _said(low: str) -> tuple[Optional[bool], str]:
    found: list[tuple[bool, str]] = []
    for rx in (_SAID_RU, _SAID_EN, _SAID_KK):
        for m in rx.finditer(low):
            word = next(g for g in m.groups() if g)
            if _NEGATED.search(low[max(0, m.start() - 8): m.start()]) or (
                    rx is not _SAID_KK and re.search(r"(?<![а-яa-z])(?:не|not)\s", m.group(0))):
                continue  # Kazakh «не» is «what»: «қаралар үшін не істеу керек?»
            word = re.sub(r"^за\s+", "", word)
            color = chess.WHITE if word.startswith(("бел", "white", "ақ")) else chess.BLACK
            found.append((color, m.group(0).strip()))
    colors = {c for c, _ in found}
    if len(colors) != 1:
        return None, ""
    return found[0]


# ── 3. the student tells who made a move ───────────────────────────────────────────────────────────────────────

# The student as the subject: «я», "I", «мен» (at the start of its clause: «мен» is also «and/with» in Kazakh).
_FIRST = re.compile(
    r"(?<![а-яa-zәғқңөұүһі'])(?:я|i)(?![а-яa-zәғқңөұүһі'])"
    r"|(?:^|[.,;:!?—–]\s*|(?<![а-яәғқңөұүһі])(?:ал|бірақ|сосын|содан\s+кейін)\s+)мен(?=\s)"
    # the student's own piece as the subject: «мой конь пошёл на d5», "my knight went to d5"
    r"|(?<![а-яa-z])(?:(?:мой|моя)\s+(?:пешка|конь|слон|ладья|ферзь|король)|my\s+(?:pawn|knight|bishop|rook|queen|king))"
    r"(?![а-яa-z])",
    re.IGNORECASE)
# The student's move named as a noun — no verb needed: «мой ход», "my move", «менің жүрісім».
_FIRST_NOUN = re.compile(
    r"(?<![а-яa-zәғқңөұүһі'])(?:мой\s+(?:последний\s+)?ход|моим\s+ходом|my\s+(?:last\s+)?move|менің\s+жүрісім)"
    r"(?![а-яa-zәғқңөұүһі'])",
    re.IGNORECASE)
# The opponent as the subject, in the nominative: «они», «(мой) соперник», "they", "my opponent", «олар», «қарсылас».
# Not «сопернику/соперника» (an object: «что угрожает сопернику после Nf3?») and not the engine, the bot or the
# computer — they recommend moves, they are not the student's opponent here («движок советует Nf3», review 06.11).
_THIRD = re.compile(
    r"(?<![а-яa-zәғқңөұүһі])(?:они|соперник(?:и)?|противник(?:и)?|оппонент(?:ы)?|they|(?:my\s+|the\s+)?opponents?|"
    r"олар|қарсылас(?:ым|ың|тар)?)(?![а-яa-zәғқңөұүһі])",
    re.IGNORECASE)
# Subjects that are neither the student nor their opponent, nearer the move than an «я» before them: a colour
# («Я думаю, белые сыграли Ba4 зря» — a master game) or «он/она», "he/she" (a piece as often as a player).
_OTHER_SUBJECT = re.compile(
    r"(?<![а-яa-zәғқңөұүһі])(?:белые|черные|white|black|ақтар|қаралар|он|она|he|she)(?![а-яa-zәғқңөұүһі'’-])",
    re.IGNORECASE)
# A piece as the subject of a move told as done — «Пешка пошла на g5. Куда отступать конём?» (shipped1104/fp t12),
# "The knight went to d5": a report of a move, as «белые сыграли …» is, not the student's own «я сыграл» (the 04.11
# pin cut «…защищают её конь c3» there as the opponent's). The Russian nominative is the subject wherever it stands
# («пошла пешка на g5»; «мой/моя …» is the student's, _FIRST); an English noun only opening its clause ("I moved the
# pawn to g5" has it as the object). A move to come with a piece as its subject («ферзь бьёт f7 — мат?») tells no one.
_PIECE_SUBJECT = re.compile(
    r"(?<![а-яa-zәғқңөұүһі])(?<!мой\s)(?<!моя\s)(?:пешка|конь|слон|ладья|ферзь|король)(?![а-яa-zәғқңөұүһі])"
    r"|(?:^|(?<=[.,;:!?—–]))\s*(?:the\s+|a\s+)?(?:pawn|knight|bishop|rook|queen|king)(?![a-z])",
    re.IGNORECASE)
# A move told as done: «сыграли», «пошёл», «взяли», "played", "replied", «жүрді», «алды».
_PAST = re.compile(
    r"(?<![а-яa-zәғқңөұүһі])(?:сыграл\w*|сходил\w*|пош[её]л|пошли|пошла|взял\w*|побил\w*|съел\w*|забрал\w*|поставил\w*|"
    r"ответил\w*|отош[её]л|отошли|уш[её]л|ушли|двинул\w*|толкнул\w*|продвинул\w*|вывел\w*|сделал\w*|рокировал\w*|"
    r"played|moved|took|captured|replied|answered|responded|went|pushed|castled|put|"
    r"жүрді\w*|ойнады\w*|алды\w*|қойды\w*|жеді\w*|жауап\s+берді\w*)(?![а-яa-zәғқңөұүһі])",
    re.IGNORECASE)
# A move to come played by its subject: «сыграю», «если они возьмут», «пойти», "play", "takes", «жүрсем».
_PLAY = re.compile(
    r"(?<![а-яa-zәғқңөұүһі])(?:сыгра(?:ю|ем|ет|ют|ешь|ть)|игра(?:ю|ем|ет|ют|ть)|пойд(?:у|ем|ет|ут|ешь)|пойти|"
    r"хожу|ход(?:им|ит|ят|ить)|схож(?:у)|сход(?:им|ит|ят|ить)|возьм(?:у|ем|ет|ут|ешь)|взять|бер(?:у|ем|ет|ут)|"
    r"побь(?:ю|ем|ет|ют)|побить|бить|бь(?:ю|ем|ет|ют)|съе(?:м|ст|дят|сть)|забер(?:у|ем|ет|ут)|забрать|"
    r"постав(?:лю|им|ит|ят|ить)|ответ(?:ят|ит|им|ить)|отвеча(?:ю|ем|ет|ют|ть)|двин(?:у|ем|ет|ут|уть)|"
    r"толкн(?:у|ем|ет|ут|уть)|рокиру(?:юсь|ются|ется|емся)|рокироваться|пожертву(?:ю|ем|ет|ют)|пожертвовать|"
    r"отступ(?:лю|им|ит|ят|ить)|уйд(?:у|ем|ет|ут)|уйти|"
    r"play|plays|playing|take|takes|taking|capture|captures|push|pushes|castle|castles|go|goes|reply|replies|"
    r"answer|answers|respond|responds|sacrifice|sacrifices|retreat|retreats|"
    r"жүр(?:семіз|сем|се|емін|ейін|еді|сін)|ойна(?:сам|са|ймын|йды)|ал(?:сам|са|амын|айын|ады)|қой(?:сам|са|амын|ады)|"
    r"же(?:сем|се|ймін|йді))(?![а-яa-zәғқңөұүһі])",
    re.IGNORECASE)
# Between the subject and its verb at most three words («я только что сыграл», "I want to play", «мой соперник в
# ответ взял»); a clause boundary between the subject and the move ends the subject's clause.
_BOUNDARY = re.compile(r"[,;:—–()]|(?<![а-яa-z])(?:почему|зачем|потому|но|однако|why|because|but|however)(?![а-яa-z])",
                       re.IGNORECASE)
# «Сыграл Qb6. Это мат?», «Пошёл ферзём на b6»: a singular past verb opening its clause, no subject — Russian drops
# the «я» of the student's own move (2026-10-08: «твой ферзь на b6» was called the opponent's).
_IMPLICIT_FIRST = re.compile(
    r"(?:^|[.,;:!?—–]\s*|(?<![а-я])(?:а|и|потом|тогда|вот|ну|сначала|затем|я\s+же)\s+)(?:только\s+что\s+|сейчас\s+|уже\s+)?"
    r"(?:сыграл|сыграла|сходил|сходила|пош[её]л|пошла|взял|взяла|побил|побила|съел|съела|забрал|забрала|поставил|"
    r"поставила|ответил|ответила|отош[её]л|отошла|двинул|двинула|толкнул|толкнула|вывел|вывела|сделал|сделала|"
    r"рокировался|рокировалась)(?![а-я])",
    re.IGNORECASE)
# A Kazakh verb in the first person after the move: «f5 жүрдім», «e4 ойнадым», «атты қойдым», «пілді алдым» — a Kazakh
# verb stem: «четвёртым», «простым» and other Russian instrumentals end the same way (review 06.11).
_KK_FIRST_VERB = re.compile(
    r"^\s*(?:\S+\s+){0,2}?(?:жүр|ойна|қой|ал|же|ұт|бер|ауыстыр|шығар|сал|кет|бар|рокировка\s+жаса)(?:дым|дім|тым|тім)"
    r"(?![а-яәғқңөұүһі])",
    re.IGNORECASE)
_NOT_DONE = re.compile(r"(?<![а-яa-z])(?:не|not|didn'?t|never|емес)(?![а-яa-z])", re.IGNORECASE)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?\n]*")


def _record_colors(pgn: Optional[str]) -> dict[str, list]:
    """The moves of the board's record by SAN (without +/#): the colour of each time it was played, last last; and
    by the square they land on («@f4»): (colour, piece type that moved, piece type taken or None) of each arrival."""
    out: dict[str, list] = {}
    if not pgn:
        return out
    try:
        import io

        import chess.pgn

        game = chess.pgn.read_game(io.StringIO(pgn))
        if game is None:
            return out
        board = game.board()
        for mv in game.mainline_moves():
            san = board.san(mv).rstrip("+#")
            out.setdefault(san, []).append(board.turn)
            taken = board.piece_type_at(mv.to_square)
            if taken is None and board.is_en_passant(mv):
                taken = chess.PAWN
            out.setdefault("@" + chess.square_name(mv.to_square), []).append(
                (board.turn, board.piece_type_at(mv.from_square), taken))
            board.push(mv)
    except Exception:  # noqa: BLE001 — a record that does not read is no evidence
        return {}
    return out


# What the clause of a square told alone says of the move (review 06.11: «я взял на c6» after 4.Bxc6 dxc6 is either
# side's — both arrived on c6): the piece that moved («слоном», "with the bishop", «пілмен»), the piece taken («взял
# коня», "took the knight", «атты алдым») and whether it was a capture at all («взяли на f4» is 4...exf4, not 3.f4).
_PIECE_RU = {"пешк": chess.PAWN, "кон": chess.KNIGHT, "слон": chess.BISHOP, "ладь": chess.ROOK, "ферз": chess.QUEEN,
             "корол": chess.KING}
_PIECE_EN = {"pawn": chess.PAWN, "knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK,
             "queen": chess.QUEEN, "king": chess.KING}
_PIECE_KK = {"пешка": chess.PAWN, "сарбаз": chess.PAWN, "ат": chess.KNIGHT, "піл": chess.BISHOP, "тура": chess.ROOK,
             "ферз": chess.QUEEN, "уәзір": chess.QUEEN, "патша": chess.KING, "корол": chess.KING}
_BY_PIECE = re.compile(
    r"(?<![а-яa-zәғқңөұүһі])(?:(?P<ru>пешкой|конем|слоном|ладьей|ладьею|ферзем|королем)"
    r"|with\s+(?:the\s+|my\s+|a\s+|his\s+|her\s+|their\s+)?(?P<en>pawn|knight|bishop|rook|queen|king)"
    r"|(?:my|the|his|her|their)\s+(?P<en2>pawn|knight|bishop|rook|queen|king)\s+(?:took|captured|went|moved|jumped)"
    r"|(?P<kk>пешка|сарбаз|ат|піл|тура|ферзь?|ферзі|уәзір|патша|король?)(?:мен|пен|бен))(?![а-яa-zәғқңөұүһі])",
    re.IGNORECASE)
_PIECE_OBJ = re.compile(
    r"(?<![а-яa-zәғқңөұүһі])(?:(?P<ru>пешку|коня|слона|ладью|ферзя|короля)"
    r"|(?:took|takes|take|taking|captured|captures|capture|capturing)\s+(?:the\s+|my\s+|a\s+|his\s+|her\s+|their\s+)?"
    r"(?P<en>pawn|knight|bishop|rook|queen|king)"
    r"|(?P<kk>пешканы|сарбазды|атты|пілді|тураны|ферзьді|ферзіні|уәзірді|патшаны|корольді))(?![а-яa-zәғқңөұүһі])",
    re.IGNORECASE)
_CAPTURE_VERB = re.compile(
    r"(?<![а-яa-zәғқңөұүһі])(?:взя\w*|возьм\w*|забра\w*|забер\w*|поби\w*|побь\w*|съе[лвдмсш]\w*|разменя\w*|бить|бью\w*|"
    r"бье\w*|бил\w*|took|take|takes|taking|captur\w*|exchang\w*|traded|"
    r"алды\w*|алдым|алса\w*|алам\w*|алай\w*|алып|жеді\w*|жедім|жесе\w*|жеп)(?![а-яa-zәғқңөұүһі])",
    re.IGNORECASE)


def _piece_of(word: str, table: dict) -> Optional[int]:
    return next((t for stem, t in table.items() if word.startswith(stem)), None)


def _square_clause(clause: str) -> tuple[bool, Optional[int], Optional[int]]:
    """(a capture, the piece type that moved, the piece type taken) as the clause of a square told alone says them."""
    capture = bool(_CAPTURE_VERB.search(clause))
    moved = taken = None
    for m in _BY_PIECE.finditer(clause):
        word = (m["ru"] or m["en"] or m["en2"] or m["kk"] or "").lower()
        moved = _piece_of(word, _PIECE_RU) or _piece_of(word, _PIECE_EN) or _piece_of(word, _PIECE_KK)
    for m in _PIECE_OBJ.finditer(clause):
        word = (m["ru"] or m["en"] or m["kk"] or "").lower()
        ptype = _piece_of(word, _PIECE_RU) or _piece_of(word, _PIECE_EN) or _piece_of(word, _PIECE_KK)
        if m["en"] or capture:
            taken = ptype  # «взял коня», "took the knight": the piece taken
        elif moved is None:
            moved = ptype  # «поставил коня на c6»: the piece that went there
    return capture or taken is not None, moved, taken


def _mover(board: chess.Board, san: str, done: bool, record: dict[str, list],
           square_only: bool = False, clause: str = "") -> Optional[bool]:
    """The colour that makes (or made) the move *san* — from the board and its record, or None when it cannot
    be told. *done*: the move is told as already made («сыграли», "played"). *square_only*: only the square is named
    («взяли на f4», "took on f4") — whatever piece went there, not the pawn move «f4» (shipped1104 t09: 3.f4 was
    White's, 4...exf4 Black's); *clause* is the words around it, which may name the piece that moved or was taken."""
    key = san.rstrip("+#")
    target = re.findall(r"[a-h][1-8]", key)
    if square_only:
        if not done or not target:
            return None
        capture, moved, taken = _square_clause(clause)
        arrivals = record.get("@" + target[-1]) or []
        if arrivals:
            # Every arrival the clause fits; a colour only when they are all one side's — after 4.Bxc6 dxc6 «я взял
            # на c6» is either side's, «я взял слоном на c6» / «взял коня на c6» White's (review 06.11).
            fits = {c for c, mtype, ttype in arrivals
                    if (not capture or ttype is not None) and (moved is None or mtype == moved)
                    and (taken is None or ttype == taken)}
            return fits.pop() if len(fits) == 1 else None
        if record:
            return None  # the record has no arrival there: not this game's move
        piece = board.piece_at(chess.parse_square(target[-1]))
        if piece is None or (moved is not None and piece.piece_type != moved):
            return None
        return piece.color  # no record: the piece standing there made the last move to it
    if done:
        colors = set(record.get(key) or [])
        if colors:
            return colors.pop() if len(colors) == 1 else None  # the game on the screen says who played it
        if target and not key.startswith("O-O"):
            piece = board.piece_at(chess.parse_square(target[-1]))
            ptype = "PNBRQK".index(key[0]) + 1 if key[0] in "NBRQK" else chess.PAWN
            if piece is not None and piece.piece_type == ptype:
                return piece.color  # the piece stands where the move put it
        # Told as done but neither in the record nor on the board: a story about another game («почему они сыграли
        # Nf3?» about a master game) — who could play it here says nothing of who did (review 06.11).
        return None
    now = other = False
    try:
        board.parse_san(key)
        now = True
    except ValueError:
        pass
    flipped = board.copy(stack=False)
    flipped.turn = not board.turn
    flipped.ep_square = None
    try:
        flipped.parse_san(key)
        other = True
    except ValueError:
        pass
    if now != other:
        return board.turn if now else not board.turn
    return None  # a move to come that neither side (or both) can play now says nothing about who will


def _subject(head: str, tail: str) -> Optional[tuple[str, bool]]:
    """('first' | 'third' | 'other', done) — the subject of the move that follows *head* (its sentence up to the move)
    when it is the subject of a move verb in the move's own clause; *tail* is the text right after the move. 'other'
    is someone neither the student nor their opponent — a colour, «он» («белые сыграли Nd5», «он пошёл на d5») — or
    the student denying the move («я не сыграл f5»): the move is not told as the student's. None when nothing plays
    the move («я боюсь Ng5», "how can I stop Ng5?") or the subject's clause ended before it."""
    cands = []
    for rx, kind in ((_FIRST, "first"), (_FIRST_NOUN, "noun"), (_THIRD, "third"), (_OTHER_SUBJECT, "other"),
                     (_PIECE_SUBJECT, "piece")):
        cands += [(m.start(), m.end(), kind) for m in rx.finditer(head)]
    if not cands:
        return None
    start, end, kind = max(cands, key=lambda c: (c[0], c[1]))
    span = head[end:]
    if kind != "noun" and _BOUNDARY.search(span):
        return None  # the subject's clause ended before the move
    if kind == "noun":  # «мой последний ход Qb6», "my last move was Qb6" — made
        if _NOT_DONE.search(span):
            return None
        return "first", bool(_PAST.search(span) or re.search(r"послед|last", head[start:end]))
    # The verb right after the subject (at most three words between), or right after the move («олар f5 жүрді»,
    # «они f5 сыграли»).
    done = None
    words = [w.strip(".,!?«»\"'") for w in span.split()][:4] or [w.strip(".,!?«»\"'") for w in tail.split()][:2]
    for word in words:
        if _PAST.fullmatch(word):
            done = True
            break
        if _PLAY.fullmatch(word):
            done = False
            break
    if done is None and not span.split() and _PAST.match(tail.strip()):
        done = True  # «жауап берді»
    if done is None:
        return None
    if kind == "piece":
        return ("other", True) if done and not _NOT_DONE.search(span) else None
    if _NOT_DONE.search(span):
        # «я не сыграл f5»: not the student's move; "they didn't play f5" tells no mover
        return ("other", done) if kind == "first" else None
    return kind, done


def _implicit_first(head: str) -> bool:
    """«Сыграл Qb6. Это мат?», «Пошёл ферзём на b6»: the move's clause opens with a singular past verb and has no
    subject — the student's own move with the «я» dropped."""
    if (_FIRST.search(head) or _THIRD.search(head) or _OTHER_SUBJECT.search(head) or _FIRST_NOUN.search(head)
            or _PIECE_SUBJECT.search(head)):
        return False  # «Пошла пешка на g5»: the verb has its subject
    m = None
    for m in _IMPLICIT_FIRST.finditer(head):
        pass
    if m is None:
        return False
    rest = head[m.end():]
    return not (_BOUNDARY.search(rest) or _NOT_DONE.search(rest) or re.search(r"(?<![а-я])бы(?![а-я])", rest))


def _told_moves(message: str, board: chess.Board, pgn: Optional[str],
                master_game: bool = False) -> list[tuple[Optional[bool], str, str, str]]:
    """(student colour, source, words, move) for every move the message tells with its subject: own_move,
    their_move, or other_mover (colour None) for a move told as someone else's («белые сыграли Nd5») or denied.
    *move* is its SAN, or «@c6» for a square told alone."""
    from src.answer_check import _MOVE, _to_san
    from src.move_text import normalize

    record = _record_colors(pgn)
    out: list[tuple[Optional[bool], str, str, str]] = []
    text = normalize(message)
    text = re.sub(r"(?<![0-9A-Za-z-])0-0-0(?![0-9-])", "O-O-O", text)
    text = re.sub(r"(?<![0-9A-Za-z-])0-0(?![0-9-])", "O-O", text)
    for sent in _SENTENCE.finditer(text):
        s = sent.group(0)
        converted, _ = _to_san(s)
        moves = [(m.start(), m.end(), m["san"] + (m["check"] or "")) for m in _MOVE.finditer(converted)]
        # A move told in words («поставили коня на d5», «взяли моего слона на c5»): the question reader resolves it
        # on the board; only a move told as done and standing there now says whose it was (the reader resolves
        # words for the side to move, so a legal reading tells nothing about the mover).
        try:
            from src.prompt_builder import question_moves

            for item in question_moves(s, board.fen()):
                if item.get("source") != "san" and str(item.get("verdict") or "").startswith("already played"):
                    at = s.lower().find((item.get("words") or "").lower()) if item.get("words") else -1
                    moves.append((max(at, 0), max(at, 0) + len(item.get("words") or ""), item["san"]))
        except Exception:  # noqa: BLE001 — notation alone still tells
            pass
        low = converted.lower().replace("ё", "е")
        for start, end, san in moves:
            head = low[:start]
            tail = low[end: end + 30]
            subject = _subject(head, tail)
            if subject is None and _KK_FIRST_VERB.match(tail):
                subject = ("first", True)  # «e4 жүрдім»: the verb after the move says «I»
            if subject is None and _implicit_first(head):
                subject = ("first", True)  # «Сыграл Qb6. Это мат?»: the dropped «я»
            if subject is None:
                continue
            kind, done = subject
            if kind == "third" and master_game:
                continue  # «почему они сыграли Bxf7?» about the database game on the board — not the student's opponent
            # «взяли на f4», "took on f4", «f4-ке»: a square the move went to, not the pawn move «f4»
            square_only = bool(re.fullmatch(r"[a-h][1-8]", san)) and bool(
                re.search(r"(?<![а-яa-z])(?:на|в|on|to|at|onto)\s+$", head) or re.match(r"[-‐]?(?:ке|ка|ге|ға|те|та)(?![а-яәғқңөұүһі])", tail))
            key = ("@" + san) if square_only else san.rstrip("+#")
            words = s.strip()[:80]
            if kind == "other":
                out.append((None, "other_mover", words, key))
                continue
            # The clause around a square told alone («я пошёл слоном на c6 и взял коня») names the pieces.
            clause = re.split(r"[,;:—–()]", head)[-1] + " " + re.split(r"[,;:—–()]", low[end:])[0]
            mover = _mover(board, san, done, record, square_only, clause)
            if mover is None:
                continue
            if kind == "first":
                out.append((mover, "own_move", words, key))
            else:
                out.append((not mover, "their_move", words, key))
    return out


def decide(message: str, fen: Optional[str], *, pgn: Optional[str] = None,
           game_state: Optional[dict] = None, master_game: bool = False) -> StudentSide:
    """The student's side this turn (see the module docstring). *fen* is the board on the screen, *pgn* its record,
    *game_state* the state of a game against the coach on it, *master_game* a database game on the board."""
    color = (game_state or {}).get("student_color")
    if color in ("white", "black"):
        return StudentSide(chess.WHITE if color == "white" else chess.BLACK, "game")
    if master_game:
        # A master game on the board is nobody's: «они сыграли Ba4», «я бы сыграл d4», «как играть за белых в этой
        # партии?» tell no side of the student's (review 06.11) — the rewrite says so (master_game_side_note).
        return StudentSide(None, "master_game")
    board = None
    if fen:
        try:
            board = chess.Board(fen)
        except ValueError:
            board = None
    low = (message or "").lower().replace("ё", "е")
    said, said_words = _said(low)
    found: list[tuple[Optional[bool], str, str, str]] = []
    if board is not None and message:
        try:
            found = _told_moves(message, board, pgn, master_game)
        except Exception:  # noqa: BLE001 — a move that does not read is no evidence
            found = []
    told = [t for t in found if t[0] is not None]
    others = [t for t in found if t[0] is None]
    colors = {c for c, _, _, _ in told} | ({said} if said is not None else set())
    if len(colors) > 1:
        return StudentSide(None, "conflict", said_words or told[0][2], tuple(t[3] for t in told))
    if said is not None:
        return StudentSide(said, "said", said_words)
    if told:
        return StudentSide(told[0][0], told[0][1], told[0][2], tuple(t[3] for t in told))
    if others:
        # «Белые поставили коня на d5», «я не сыграл f5»: the move is told as not the student's — no side, and the
        # 04.11 pin «the student made the move just played» is dropped for it (``applied``)
        return StudentSide(None, "other_mover", others[0][2], tuple(t[3] for t in others))
    if board is not None:
        return StudentSide(board.turn, "side_to_move")
    return StudentSide(None, "none")


def check_color(side: StudentSide) -> Optional[bool]:
    """What the answer check gets as CheckContext.student_color: the side when known exactly, else None (the check
    then reads «ты» as the side to move, or not at all when the sentence tells the other side's move)."""
    return side.color if side.exact else None


def mode() -> str:
    """COACH_STUDENT_SIDE: off | shadow | on (read at call time)."""
    from src import config

    value = str(getattr(config, "COACH_STUDENT_SIDE", "shadow") or "shadow").strip().lower()
    return value if value in ("off", "shadow", "on") else "shadow"


def legacy_color(named_moves: Optional[list], fen: Optional[str]) -> Optional[bool]:
    """The 04.11 pin (2026-10-08): a move of the question «already played» on the board made the student the side
    that just moved («Я сыграл Qb6. Это мат?») — None when no such move was named."""
    if not any(str(q.get("verdict") or "").startswith("already played") for q in named_moves or []):
        return None
    try:
        return not chess.Board(fen).turn
    except (ValueError, TypeError):
        return None


def legacy_moves(named_moves: Optional[list]) -> tuple:
    """The moves of the question «already played» on the board — the ones the 04.11 pin read as the student's."""
    return tuple(str(q.get("san") or "").rstrip("+#") for q in named_moves or []
                 if str(q.get("verdict") or "").startswith("already played") and q.get("san"))


def _same_move(told: tuple, pinned: Optional[tuple]) -> bool:
    """A move of the decision is one the 04.11 pin came from: the same SAN, or a move to the same square («они взяли
    на f4» and exf4). *pinned* None: not known — any move counts."""
    if pinned is None:
        return True

    def square(san: str) -> str:
        found = re.findall(r"[a-h][1-8]", san)
        return found[-1] if found else san

    return any(t.lstrip("@") == p or square(t) == square(p) for t in told for p in pinned)


def applied(side: StudentSide, legacy: Optional[bool], how: Optional[str] = None,
            pinned_moves: Optional[tuple] = None) -> StudentSide:
    """What the checks and the model get this turn under COACH_STUDENT_SIDE (*how*, default the config).

    *legacy* is the 04.11 pin (a move of the question «already played»: the student made it), *pinned_moves* the
    moves it came from (``legacy_moves``). A game decides in every mode; ``off`` is the 04.11 pin itself. Otherwise:

    - a master game on the board: no side (nobody's — not the pin either);
    - nothing told about the move («Qxf7 — это мат?», "Is Qxf7 mate?", «После Qxf7 это мат?»): the pin stays — the
      student asks about the move just played (2026-10-08), and the decision has nothing better (review 06.11);
    - the move of the pin told as someone else's («Белые поставили коня на d5», t46) or signals that disagree: dropped;
    - a side told exactly: ``on`` takes it; ``shadow`` takes it where the pin was — a side the student said, or the
      very move of the pin («Они сыграли f5», t25) — and drops the pin when another move disagrees with it, never
      flips it on another move's say-so («Я взял на c6, а потом Nxe5»), and never pins a question the 04.11 server
      left alone.
    """
    how = how or mode()
    if side.source == "game":
        return side
    if how == "off":
        return StudentSide(legacy, "legacy") if legacy is not None else StudentSide(None, "none")
    if side.source == "master_game":
        return side
    if legacy is None:
        return side if how == "on" else StudentSide(None, "none")
    pin = StudentSide(legacy, "legacy")
    if side.exact:
        if how == "on" or side.source == "said" or side.color == legacy or _same_move(side.moves, pinned_moves):
            return side
        return StudentSide(None, "none")
    if side.source == "other_mover":
        return side if _same_move(side.moves, pinned_moves) else pin
    if side.source == "conflict":
        return side
    return pin


def log_payload(side: StudentSide, used: StudentSide, legacy: Optional[bool], how: Optional[str] = None) -> dict:
    """The student_side event: the decision, what was applied and the 04.11 pin — for grading shadow before ``on``."""
    def name(color: Optional[bool]) -> Optional[str]:
        return None if color is None else ("white" if color else "black")

    return {"mode": how or mode(), "decided": name(side.color), "source": side.source, "exact": side.exact,
            "evidence": side.evidence[:80], "moves": list(side.moves), "applied": name(check_color(used)),
            "applied_source": used.source, "legacy": name(legacy)}
