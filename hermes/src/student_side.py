"""Which side the student plays — decided once per turn by the server, from what it knows exactly (06.11).

The old bug: a question that tells the opponent's move — «Они сыграли f5. Брать?», «Белые поставили коня на d5»,
"They played f5", «Олар f5 жүрді» — made the student the side that had just moved. The server read every move «already
played» as the student's own (src/server: «Я сыграл Qb6. Это мат?»), so the answer check cut «Твой конь b5 нападает на
c7» as Black's knight and the rewrite was told the wrong side (shipped1104/fp t25, t46, t28). The side was decided in
four places, each with its own guess; now it is decided here, and the one decision goes to the model (a turn-context
block, the rewrite's side note) and to the answer check (CheckContext.student_color).

What decides, strongest first:

1. **A game against the coach on the board** — its ``student_color`` (live or finished).
2. **The student says their side** — «я играю чёрными», «я за белых», «у меня белые», «что делать чёрными?»,
   "I'm Black", "I play as White", "what should I play as Black?", «мен ақпен ойнаймын», «қаралар үшін».
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
   the «я». «Они» about the database game on the board (a master game) is no opponent of the student's.
4. Otherwise **the side to move** on the board — a guess (``exact`` False): the checks keep their own reading of
   the sentence then (src/answer_check.student_side), and the model is not told a side it was not told.

Signals that disagree (the student says Black, the move told says White) leave the side unknown.

COACH_STUDENT_SIDE (off | shadow | on, default shadow; ``applied``): in shadow the decision is logged every turn but
reaches the checks and the model only where the server pinned the side before (a game; a move of the question
«already played» on the board — the 2026-10-08 rule), so it can correct that pin («Они сыграли f5», t25) or drop it
(«Белые поставили коня на d5», t46) but never pins a new class of questions. ``on`` uses it everywhere.

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
    """The decision: ``color`` (chess.WHITE / chess.BLACK / None), ``source`` (game, said, own_move, their_move,
    side_to_move, conflict, none) and the words of the message that decided it."""

    color: Optional[bool]
    source: str  # game, said, own_move, their_move, side_to_move, conflict, none; legacy (COACH_STUDENT_SIDE=off)
    evidence: str = ""

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
    # «я за белых», «я белыми», «я — чёрные», «я играл(а) белыми»
    rf"|я\s+(?:[—–-]\s+)?(?:сам\w*\s+)?(?:игра(?:л|ла|ли)\s+)?(?:за\s+)?(?P<c2>{_W_RU}|{_B_RU})(?![а-я])"
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
    # «қаралар үшін не істеу керек?»
    rf"|(?P<c3>ақтар|қаралар)\s+үшін"
    ")(?![а-яәғқңөұүһі])",
    re.IGNORECASE)
_NEGATED = re.compile(r"(?:(?<![а-яa-z])не|not|n't|never|емес)\s*$", re.IGNORECASE)


def _said(low: str) -> tuple[Optional[bool], str]:
    found: list[tuple[bool, str]] = []
    for rx in (_SAID_RU, _SAID_EN, _SAID_KK):
        for m in rx.finditer(low):
            word = next(g for g in m.groups() if g)
            if _NEGATED.search(low[max(0, m.start() - 8): m.start()]) or re.search(r"(?<![а-яa-z])(?:не|not)\s", m.group(0)):
                continue
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
    r"|(?:^|[.,;:!?—–]\s*|(?<![а-яәғқңөұүһі])(?:ал|бірақ|сосын|содан\s+кейін)\s+)мен(?=\s)",
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


def _record_colors(pgn: Optional[str]) -> dict[str, list[bool]]:
    """The moves of the board's record by SAN (without +/#) and by the square they land on («@f4»): the colour of
    each time it was played, last last."""
    out: dict[str, list[bool]] = {}
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
            out.setdefault("@" + chess.square_name(mv.to_square), []).append(board.turn)
            board.push(mv)
    except Exception:  # noqa: BLE001 — a record that does not read is no evidence
        return {}
    return out


def _mover(board: chess.Board, san: str, done: bool, record: dict[str, list[bool]],
           square_only: bool = False) -> Optional[bool]:
    """The colour that makes (or made) the move *san* — from the board and its record, or None when it cannot
    be told. *done*: the move is told as already made («сыграли», "played"). *square_only*: only the square is named
    («взяли на f4», "took on f4") — whatever piece went there, not the pawn move «f4» (shipped1104 t09: 3.f4 was
    White's, 4...exf4 Black's)."""
    key = san.rstrip("+#")
    target = re.findall(r"[a-h][1-8]", key)
    if square_only:
        if not done or not target:
            return None
        colors = record.get("@" + target[-1]) or []
        if colors:
            return colors[-1]
        piece = board.piece_at(chess.parse_square(target[-1]))
        return piece.color if piece is not None else None
    if done:
        colors = record.get(key) or []
        if colors:
            return colors[-1]  # the game on the screen says who played it
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
    """('first' | 'third', done) — the subject of the move that follows *head* (its sentence up to the move) when it
    is the subject of a move verb in the move's own clause; *tail* is the text right after the move. None when the
    nearest subject is someone else (a colour, «он»), when nothing plays the move («я боюсь Ng5», "how can I stop
    Ng5?"), or when it is denied («я не играл f5»)."""
    cands = []
    for rx, kind in ((_FIRST, "first"), (_FIRST_NOUN, "noun"), (_THIRD, "third"), (_OTHER_SUBJECT, "other")):
        cands += [(m.start(), m.end(), kind) for m in rx.finditer(head)]
    if not cands:
        return None
    start, end, kind = max(cands, key=lambda c: (c[0], c[1]))
    span = head[end:]
    if kind == "other" or (kind != "noun" and _BOUNDARY.search(span)):
        return None  # someone else's move («белые сыграли»), or the subject's clause ended before the move
    if _NOT_DONE.search(span):
        return None  # «я не играл f5», "they didn't play f5"
    if kind == "noun":  # «мой последний ход Qb6», "my last move was Qb6" — made
        return "first", bool(_PAST.search(span) or re.search(r"послед|last", head[start:end]))
    # The verb right after the subject (at most three words between), or right after the move («олар f5 жүрді»,
    # «они f5 сыграли»).
    words = [w.strip(".,!?«»\"'") for w in span.split()][:4] or [w.strip(".,!?«»\"'") for w in tail.split()][:2]
    for word in words:
        if _PAST.fullmatch(word):
            return kind, True
        if _PLAY.fullmatch(word):
            return kind, False
    if not span.split() and _PAST.match(tail.strip()):
        return kind, True  # «жауап берді»
    return None


def _implicit_first(head: str) -> bool:
    """«Сыграл Qb6. Это мат?», «Пошёл ферзём на b6»: the move's clause opens with a singular past verb and has no
    subject — the student's own move with the «я» dropped."""
    if _FIRST.search(head) or _THIRD.search(head) or _OTHER_SUBJECT.search(head) or _FIRST_NOUN.search(head):
        return False
    m = None
    for m in _IMPLICIT_FIRST.finditer(head):
        pass
    if m is None:
        return False
    rest = head[m.end():]
    return not (_BOUNDARY.search(rest) or _NOT_DONE.search(rest) or re.search(r"(?<![а-я])бы(?![а-я])", rest))


def _told_moves(message: str, board: chess.Board, pgn: Optional[str],
                master_game: bool = False) -> list[tuple[bool, str, str]]:
    """(student colour, source, words) for every move the message tells with its subject."""
    from src.answer_check import _MOVE, _to_san
    from src.move_text import normalize

    record = _record_colors(pgn)
    out: list[tuple[bool, str, str]] = []
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
            mover = _mover(board, san, done, record, square_only)
            if mover is None:
                continue
            words = s.strip()[:80]
            if kind == "first":
                out.append((mover, "own_move", words))
            else:
                out.append((not mover, "their_move", words))
    return out


def decide(message: str, fen: Optional[str], *, pgn: Optional[str] = None,
           game_state: Optional[dict] = None, master_game: bool = False) -> StudentSide:
    """The student's side this turn (see the module docstring). *fen* is the board on the screen, *pgn* its record,
    *game_state* the state of a game against the coach on it, *master_game* a database game on the board."""
    color = (game_state or {}).get("student_color")
    if color in ("white", "black"):
        return StudentSide(chess.WHITE if color == "white" else chess.BLACK, "game")
    board = None
    if fen:
        try:
            board = chess.Board(fen)
        except ValueError:
            board = None
    low = (message or "").lower().replace("ё", "е")
    said, said_words = _said(low)
    told: list[tuple[bool, str, str]] = []
    if board is not None and message:
        try:
            told = _told_moves(message, board, pgn, master_game)
        except Exception:  # noqa: BLE001 — a move that does not read is no evidence
            told = []
    colors = {c for c, _, _ in told} | ({said} if said is not None else set())
    if len(colors) > 1:
        return StudentSide(None, "conflict", said_words or told[0][2])
    if said is not None:
        return StudentSide(said, "said", said_words)
    if told:
        return StudentSide(told[0][0], told[0][1], told[0][2])
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


def applied(side: StudentSide, legacy: Optional[bool], how: Optional[str] = None) -> StudentSide:
    """What the checks and the model get this turn under COACH_STUDENT_SIDE (*how*, default the config): ``on`` the
    decision; ``shadow`` the decision only where the 04.11 server pinned a side (*legacy* not None) or a game decides
    — it can correct or drop that pin, never add one; ``off`` the 04.11 pin itself."""
    how = how or mode()
    if side.source == "game" or how == "on":
        return side
    if legacy is None:
        return StudentSide(None, "none")
    if how == "off":
        return StudentSide(legacy, "legacy")
    return side if side.exact else StudentSide(None, "none")


def log_payload(side: StudentSide, used: StudentSide, legacy: Optional[bool], how: Optional[str] = None) -> dict:
    """The student_side event: the decision, what was applied and the 04.11 pin — for grading shadow before ``on``."""
    def name(color: Optional[bool]) -> Optional[str]:
        return None if color is None else ("white" if color else "black")

    return {"mode": how or mode(), "decided": name(side.color), "source": side.source, "exact": side.exact,
            "evidence": side.evidence[:80], "applied": name(check_color(used)), "legacy": name(legacy)}
