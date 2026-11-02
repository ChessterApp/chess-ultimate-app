"""A line the coach writes and the outcome it promises, judged by the engine (prod check 29.10).

«Берёшь коня на d5 с шахом: Qxd5+ … ты забираешь ферзя, и партия фактически решена» (8...Qxd5 and White has
given the queen for a knight), «если сыграть Nd4, можно нарваться на Nxe5, и там уже начинается опасная для
чёрных игра» (the Blackburne trap told backwards: 4.Nxe5? Qg5! and Black is better): the coach played a line in
its head and told where it ends. The board said nothing against it — every move was legal — so the sentences
went out. The board knows the line and the engine knows where it ends: an outcome the engine clearly contradicts
is not shown, and the rewrite gets the engine's evaluation (and, outside a live game, its continuation). A number
told for the change («на пешку хуже, чем было») is held against the engine's swing the same way — though not
«почти на четыре пешки хуже» for 6.b3? (prod 29.10): the engine says −6.5, but the line loses a whole bishop, and
a coach counting material is not clearly wrong.

Two steps, as for the coach's recommendation (src/hypothetical.verify_recommendation):
- line_claims(text, ctx) — synchronous, python-chess only. src/answer_check.check_sentence calls it for each
  sentence while the gate holds it, so the line of the sentence before is the right one; the claims wait in
  ctx.line_claims under the sentence.
- verify_claims(claims, …) — the engine, in the async verification stage of src/server.py (a thread of
  _engine_pool, within the turn's budget). Never raises; None when nothing is clearly wrong.

What is judged, and what is not (a wrongly cut sentence takes correct teaching with it):
- only a line of written moves, each legal from a position given to the turn (the board, a line or a game the
  turn has, what a tool put up) — never one only named in a tool's text, never a derived board but the line's
  own continuation; a line that fits two different given positions is not guessed;
- only an outcome told for a named side after the line («…, и белые выигрывают ферзя», «опасная для чёрных
  игра», «ты забираешь ферзя») — not before it, not denied, not the student's belief («думаешь, что…»), not a
  question, not a sentence that names the price itself («забирают коня, но…»);
- only a clear contradiction: the side the outcome favours stands at least CLEAR_PAWNS worse at the end of the
  line, or worse at the end with its own move in the line a mistake of at least MISTAKE_PAWNS (the trap told
  backwards). Thresholds and why: see below.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import chess

logger = logging.getLogger(__name__)

# The side an outcome favours stands this much worse at the end of the line: a clear contradiction, far beyond
# the noise of a 300 ms search (a few tenths). It is the engine's line for a mistake in src/hypothetical.py too
# (MISTAKE); «у белых лучше» on the board as it stands is cut at −0.6 (src/answer_check._eval_issues), but the end
# of a written line is searched shorter and the line may be told loosely. In the corpora (8950 + 1004 sentences
# and the 131 answers of 29.10) the outcomes that hold stood at 0.0 or better for their side; the wrong ones at
# −6.4 (mate2-no) and −0.8 (op-show-italian, by the mistake rule below).
CLEAR_PAWNS = 1.5
# …or worse at the end (by WORSE_PAWNS at least) with its own move in the line a mistake of MISTAKE_PAWNS: the
# line relies on a blunder by the side it is said to favour (3...Nd4 4.Nxe5?: +1.3 → −0.6 for White).
MISTAKE_PAWNS = 1.5
WORSE_PAWNS = 0.4
# «на N пешек хуже»: the number is wrong when it is off the engine's swing by max(SWING_ABS, SWING_REL × the
# larger), off the material swing by a pawn or more (a coach counting material is not contradicted), and not
# between the two.
SWING_ABS = 1.5
SWING_REL = 0.3
MAX_PLIES = 8
MAX_CLAIMS = 2
MATE_PAWNS = 100.0

_W = r"(?<![а-яёa-z])"
_E = r"(?![а-яёa-z])"

# The side an outcome is told for. «ты», «у тебя», a verb of the second person: the student.
_SIDE = (r"(?P<side>белые|белых|белым|ч[её]рные|ч[её]рных|ч[её]рным|white|black|ты|тебя|тебе|you|"
         r"соперник|соперника|сопернику|противник|противника|противнику|(?:your\s+)?opponent)")
# What is won or lost: the game, a piece, material — not a pawn, a tempo or the centre (a pawn grab that loses
# is still a pawn won: «забирают пешку, но ферзь попадает в ловушку» says something true).
_STAKE = (r"(?:(?:сразу|ещ[её]|целого|целую|целый|лишн\w+|чист\w+|в\s+итоге|обратно)\s+)*"
          r"(?:ферзя|ладью|фигуру|коня|слона|качество|материал|партию|игру|the\s+queen|a\s+rook|the\s+rook|a\s+piece|"
          r"a\s+knight|a\s+bishop|the\s+exchange|material|the\s+game)")
_END = r"(?=\s*(?:[.,;:!—–)]|$|\s(?:и|а|and)\s))"
# Verbs of the outcome. (verb, favours its subject?)
_GOOD = (r"(?:выигрыва(?:ет|ют|ешь)|выиграе(?:т|шь)|выиграют|забира(?:ет|ют|ешь)|забер(?:[её]т|[её]шь|ут)|"
         r"wins?|picks?\s+up)\s+" + _STAKE
         + r"|(?:выигрыва(?:ет|ют|ешь)|выиграе(?:т|шь)|выиграют|побежда(?:ет|ют|ешь)|wins?|is\s+winning|are\s+winning)" + _END
         + r"|(?:оста[её]т(?:ся|есь)|оста[её]шься|останет(?:ся|есь)|останешься|останутся)\s+с\s+лишн\w+\s+(?:ферз\w+|ладь\w+|фигур\w+|кон\w+|слон\w+)"
         + r"|(?:ставит|ставят|ставишь|поставит|поставят|поставишь)\s+мат|матует|(?:mates|checkmates)" + _E
         + r"|(?:получа(?:ет|ют|ешь)|получит|получат|получишь)\s+(?:решающ\w+|подавляющ\w+|выигранн\w+|выигрышн\w+|огромн\w+)\s+"
           r"(?:перевес|преимуществ\w*|позици\w+|атак\w*)")
# («отдаёт ферзя» is not here: a sacrifice is given on purpose — «белые отдают ферзя и через ход ставят мат»)
_BAD = (r"(?:теря(?:ет|ют|ешь)|потеря(?:ет|ют|ешь)|loses?)\s+" + _STAKE
        + r"|(?:проигрыва(?:ет|ют|ешь)|проиграе(?:т|шь)|проиграют|loses?|is\s+lost|are\s+lost)" + _END
        + r"|(?:получа(?:ет|ют|ешь)|получит|получат|получишь)\s+мат|(?:gets?|is)\s+(?:check)?mated")
# «белые стоят лучше», «ты стоишь лучше» — but «белым лучше сдаться», «тебе лучше сыграть Ng4», «ты лучше подумай о
# защите» are advice, not an evaluation (review 30.10): the side in the nominative, «ты» only with «стоишь», and no
# infinitive right after.
_NOMINATIVE = (r"(?P<side>белые|ч[её]рные|white|black|соперник|противник|(?:your\s+)?opponent|"
               r"ты(?=\s+(?:уже\s+|тогда\s+|там\s+)?стоишь\s)|you(?=\s+(?:are|stand)\s))")
_NO_INFINITIVE = r"(?!\s+(?:(?:сразу|всего|уже|просто|не|бы|же)\s+)*(?!почти)[а-яё]+(?:ть|ться|ти|чь)(?![а-яё]))"
_SECOND = (r"выигрываешь|выиграешь|забираешь|заберешь|заберёшь|оста[её]шься|останешься|ставишь|поставишь|побеждаешь|"
           r"получаешь|получишь|теряешь|потеряешь|проигрываешь|проиграешь")
_CLAIMS = [
    # «белые выигрывают ферзя», «у тебя … забираешь ферзя», "White wins a piece"
    (re.compile(_W + rf"(?:у\s+)?{_SIDE}\s+(?:(?!не\s|ни\s|not\s|no\s)[а-яёa-z']+\s+){{0,3}}?(?P<v>{_GOOD})", re.IGNORECASE), True),
    (re.compile(_W + rf"(?:у\s+)?{_SIDE}\s+(?:(?!не\s|ни\s|not\s|no\s)[а-яёa-z']+\s+){{0,3}}?(?P<v>{_BAD})", re.IGNORECASE), False),
    # «…, после чего забираешь ферзя»: the verb alone names the student
    (re.compile(_W + rf"(?P<v>(?=(?:{_SECOND}){_E})(?:{_GOOD}))", re.IGNORECASE), True),
    (re.compile(_W + rf"(?P<v>(?=(?:{_SECOND}){_E})(?:{_BAD}))", re.IGNORECASE), False),
    # «у белых решающий перевес», «чёрные стоят лучше»
    (re.compile(_W + rf"у\s+{_SIDE}\s+(?:уже\s+|сразу\s+|тогда\s+|там\s+)?(?P<v>(?:решающ\w+|подавляющ\w+|явн\w+|большой|огромн\w+|"
                r"серь[её]зн\w+|заметн\w+|сильн\w+|ощутим\w+|чист\w+|лишн\w+)\s+(?:перевес|преимуществ\w*|фигур\w*|ферз\w*|ладь\w*)"
                r"|(?:перевес|преимуществ\w*)" + _E + ")", re.IGNORECASE), True),
    (re.compile(_W + rf"{_NOMINATIVE}\s+(?:уже\s+|тогда\s+|там\s+)?(?:сто(?:ят|ит|ишь)\s+)?(?:заметно\s+|явно\s+|намного\s+|гораздо\s+|"
                r"значительно\s+|clearly\s+|much\s+)?(?P<v>лучше|better)" + _E + _NO_INFINITIVE, re.IGNORECASE), True),
    (re.compile(_W + rf"{_NOMINATIVE}\s+(?:уже\s+|тогда\s+|там\s+)?(?:сто(?:ят|ит|ишь)\s+)?(?:заметно\s+|явно\s+|намного\s+|гораздо\s+|"
                r"значительно\s+|clearly\s+|much\s+)?(?P<v>хуже|worse)" + _E + _NO_INFINITIVE, re.IGNORECASE), False),
    # «опасная для чёрных игра», «чёрные в беде», "dangerous for Black"
    (re.compile(_W + rf"(?P<v>опасн\w+|неприятн\w+|тяж[её]л\w+|плох\w+|dangerous|bad|trouble)\s+(?:\w+\s+)?(?:для|for)\s+{_SIDE}{_E}",
                re.IGNORECASE), False),
    (re.compile(_W + rf"{_SIDE}\s+(?:уже\s+|тогда\s+|там\s+|сразу\s+)?(?P<v>в\s+беде|в\s+опасности|под\s+разгромом|in\s+trouble)",
                re.IGNORECASE), False),
]
# «Qxd5+ выигрывает ферзя», «…Nxe5 теряет коня», "Nf7 wins the queen": the move itself is the subject — the outcome
# is for the side that makes it.
_MOVE_SUBJECT = re.compile(r"(?<![A-Za-z0-9])(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)"
                           r"[+#]?[!?]*[*_]*\s+(?:(?:сразу|просто|тут\s+же|немедленно|immediately|simply)\s+)?"
                           rf"(?P<v>{_GOOD}|{_BAD})")
_MOVE_SUBJECT_BAD = re.compile(rf"(?:{_BAD})$")
# The student's belief or a quote, not the coach's claim: «думаешь, что выигрываешь ферзя».
# …or what someone says or is sure of, a myth (review 30.10: «Ты говоришь, что…», «Многие новички уверены, что…»,
# «Это миф, что…», «никто не скажет, что белые стоят лучше» were judged as the coach's own claims).
_BELIEF = re.compile(_W + r"(?:дума\w*|кажет\w*|казал\w*|счита\w*|ожида\w*|наде\w*|рассчитыва\w*|по-тво\w+|якобы|будто|"
                     r"хоч\w*|хотел\w*|мечта\w*|пишешь|спрашива\w*|говор\w*|скаж\w*|сказа\w*|утвержда\w*|уверен\w*|"
                     r"предлага\w*|по\s+тво\w+\s+слов\w*|тво\w+\s+иде\w+|миф\w*|заблужд\w*|легенд\w*|"
                     r"think|thought|hope|expect|seems?|believe|says?|said|claims?|sure|myth)" + _E, re.IGNORECASE)
# The price named in the same sentence after the outcome: «забирают коня, но получают мат», «…забирают коня, и белые
# ставят мат» — told, not hidden.
_PRICE = re.compile(_W + r"(?:но|однако|зато|правда|хотя|ценой|мат(?:а|ом|у)?|матует|ловуш\w*|отыгрыва\w*|but|however|though|yet|"
                    r"at\s+the\s+cost|mates?|checkmate|trap\w*)" + _E, re.IGNORECASE)
# A condition between the line and the outcome: «Qxd5+, и если король отойдёт, ты забираешь ферзя» is about a reply
# the line does not write; the engine would judge another one.
# …or right after the outcome in its clause: «неприятная для белых позиция, если не знать ловушек» (review 30.10).
_CONDITION = re.compile(_W + r"(?:если|когда|в\s+случае|коли|if|when|unless|in\s+case)" + _E, re.IGNORECASE)
# «…, после чего ты забираешь ферзя», «в ответ», «в итоге»: what follows is the end of the line before.
_FOLLOWS = re.compile(_W + r"(?:после\s+(?:чего|этого|того)|в\s+ответ|тогда|затем|дальше|далее|потом|в\s+итоге|в\s+результате|"
                      r"then|after\s+that|afterwards|as\s+a\s+result)" + _E, re.IGNORECASE)
# «Поэтому дальше спокойно развиваешься…», «Вместо этого…»: the plan instead of the line before, not its end.
_INSTEAD = re.compile(r"^\W*(?:поэтому|так\s+что|вместо\s+(?:этого|него|того)|instead|so)" + _E, re.IGNORECASE)
# Alternatives between two written moves («Nf6 или Bc5», «не Nd4, а Nf6»): not one line.
# «…у белых нет ферзя, а после 8.Nc3…», «…; правильно 8.Nc3» start another branch too (review 30.10).
_ALTERNATIVE = re.compile(_W + r"(?:или|либо|вместо|а\s+не|не|а\s+(?:после|на|вот|если)|правильн\w*|лучше|сильнее|or|instead|"
                          r"rather|not|whereas|correct\w*|better)" + _E + r"|;", re.IGNORECASE)
# «на почти четыре пешки хуже», «хуже на две пешки», "two pawns worse"
_SWING_NUM = r"(?P<n>пешку|pawn|\d+(?:[.,]\d+)?|одну|одна|полторы|две|два|три|четыре|пять|шесть|семь|восемь|девять|one|two|three|four|five|six|seven|eight|nine|half\s+a)"
_SWING = [
    re.compile(_W + rf"на\s+(?:почти\s+|примерно\s+|около\s+|целых\s+|целую\s+|ровно\s+|всего\s+|уже\s+)*{_SWING_NUM}(?:\s+пешк\w*)?\s+(?P<dir>хуже|лучше)" + _E,
               re.IGNORECASE),
    re.compile(_W + rf"(?P<dir>хуже|лучше)\s+(?:почти\s+|примерно\s+|около\s+|целых\s+|уже\s+)*на\s+(?:почти\s+|примерно\s+|около\s+|целых\s+)*"
               rf"{_SWING_NUM}\s+пешк\w*", re.IGNORECASE),
    re.compile(_W + rf"(?:almost\s+|about\s+|roughly\s+|nearly\s+)?{_SWING_NUM}\s+pawns?\s+(?P<dir>worse|better)" + _E, re.IGNORECASE),
]
# The change against the position before: «…хуже, чем было», «по сравнению с …», "than before".
# Only against the position before — not «лучше, чем у чёрных», «хуже, чем Nc3» (two sides, two moves; review 30.10).
_AGAINST_BEFORE = re.compile(r"\s*,?\s*(?:чем\s+(?:было|был[аио]?|до(?![а-яё])|раньше|прежде|сейчас|в\s+начале|в\s+исходн\w+|на\s+доске)|"
                             r"than\s+(?:before|it\s+was|now|at\s+the\s+start))" + _E, re.IGNORECASE)
_COMPARED = re.compile(_W + r"(?:(?:по\s+сравнению|в\s+сравнении)\s+с\s+(?:тем|исходн\w+|прежн\w+|начальн\w+|позици\w+\s+до|"
                       r"момент\w+\s+до)|compared\s+(?:to|with)\s+(?:before|the\s+(?:start|position\s+before)))" + _E, re.IGNORECASE)
_NUMBERS = {"пешку": 1, "pawn": 1, "одну": 1, "одна": 1, "one": 1, "полторы": 1.5, "half a": 0.5, "две": 2, "два": 2, "two": 2, "три": 3, "three": 3,
            "четыре": 4, "four": 4, "пять": 5, "five": 5, "шесть": 6, "six": 6, "семь": 7, "seven": 7, "восемь": 8,
            "eight": 8, "девять": 9, "nine": 9}


_COLOUR_WORD = {chess.WHITE: re.compile(_W + r"(?:бел\w+|white)" + _E, re.IGNORECASE),
                chess.BLACK: re.compile(_W + r"(?:ч[её]рн\w+|black)" + _E, re.IGNORECASE)}


def _side_of(word: str, ctx, line_on_current: bool, sentence: str = "") -> Optional[bool]:
    w = (word or "").lower().replace("ё", "е")
    if w.startswith(("бел", "white")):
        return chess.WHITE
    if w.startswith(("черн", "black")):
        return chess.BLACK
    # «ты» is the student: their colour in a game; outside one the side to move on the board on the screen — only
    # for a line played from that board (the coach of an opening line may speak to either side), and not when the
    # sentence names that colour itself («Если белые сыграют Qxf7+, ты теряешь ферзя»: the student is Black there).
    # Nor when the question or the sentence tells the other side's move or the student's own last one («Что если он
    # возьмёт ферзём на d5?», «Он может взять Qxd5+, но тогда ты забираешь ферзя»: the student is Black; review 30.10).
    student = ctx.student_color
    if student is None:
        if not line_on_current or ctx.current is None or _COLOUR_WORD[ctx.current.turn].search(sentence):
            return None
        from src.answer_check import student_side

        student = student_side(ctx, sentence)
        if student is None:
            return None
    if w in ("ты", "тебя", "тебе", "you", "") or not w:
        return student
    return not student  # соперник, противник, opponent


def _tokens(converted: str) -> list:
    """The written moves of a sentence as a line may hold them: a piece move, a capture, a numbered move, castling —
    and a bare pawn move only right after one of those («1.e4 e5», «Nf3 d5»): alone «e4» is a square."""
    from src.answer_check import _MOVE

    out, last_end = [], -1
    for m in _MOVE.finditer(converted):
        san = m["san"]
        bare = not (m["num"] or m["bdots"] or san[0] in "KQRBNO" or "x" in san)
        if bare and not (last_end >= 0 and re.fullmatch(r"[\s,]*(?:\d{1,3}\s?\.{1,3}\s*)?", converted[last_end:m.start()])):
            last_end = -1
            continue
        out.append(m)
        last_end = m.end()
    return out


def _play(board: chess.Board, tokens: list) -> Optional[list]:
    b = board.copy(stack=False)
    moves = []
    for m in tokens:
        dots = m["dots"] or m["bdots"]
        if (dots in ("...", "…") and b.turn != chess.BLACK) or (m["num"] and dots == "." and b.turn != chess.WHITE):
            return None
        try:
            mv = b.parse_san(m["san"] + (m["check"] or ""))
        except ValueError:
            try:
                mv = b.parse_san(m["san"])
            except ValueError:
                return None
        moves.append(mv)
        b.push(mv)
    return moves


def _numbered_here(board: chess.Board, first) -> bool:
    """«8.Qxd5+» starts at move 8 (a puzzle numbered from 1 starts anywhere)."""
    return not first["num"] or first["num"] == "1" or int(first["num"]) == board.fullmove_number


def _start(ctx, tokens: list) -> Optional[tuple]:
    """(the board the line starts from, its moves, whether that is the board on the screen) — the board on the
    screen first, then the one other position given to the turn where the whole line is legal; None when no
    position or more than one fits."""
    if not tokens:
        return None
    if ctx.current is not None and _numbered_here(ctx.current, tokens[0]):
        moves = _play(ctx.current, tokens)
        if moves:
            return ctx.current, moves, True
    found = []
    for board in ctx.boards:
        key = ctx._key(board)
        if not ctx.is_given(board) or (key in ctx.text_keys and key not in ctx.shown_keys):
            continue  # a derived board never starts a line; a lesson's diagram only named in a tool's text neither
        if ctx.current is not None and board.board_fen() == chess.STARTING_BOARD_FEN \
                and ctx.current.board_fen() != chess.STARTING_BOARD_FEN and not tokens[0]["num"]:
            continue  # the start position stands in for an unknown one
        moves = _play(board, tokens) if _numbered_here(board, tokens[0]) else None
        if moves:
            found.append((board, moves))
        if len(found) > 1:
            return None
    if len(found) == 1:
        return found[0][0], found[0][1], False
    return None


def _end_of(line: tuple) -> chess.Board:
    b = line[0].copy(stack=False)
    for mv in line[1]:
        b.push(mv)
    return b


# A move told in words before the written line («Если они берут — ты бьёшь ладью слоном на f7, …, а ты играешь Лe1 и
# забираешь материал»: Re1 comes after three moves, not on the board as it stands — corpus 30.10).
_THEY_MOVE = re.compile(_W + r"(?:они|он|она|белые|ч[её]рные|соперник|противник|they|he|white|black)\s+(?:[а-яёa-z]+\s+){0,2}?"
                        r"(?:бер[её]т|берут|возьм[её]т|возьмут|бь[её]т|бьют|побь[её]т|побьют|забира\w+|забер\w+|ид[её]т|идут|пойд[её]т|"
                        r"уход\w+|уйд[её]т|отход\w+|отступ\w+|игра(?:ет|ют)|сыгра(?:ет|ют)|отвеча(?:ет|ют)|ответ(?:ит|ят)|"
                        r"закрыва\w+|закро\w+|takes?|captures?|plays?|replies|answers?|goes|retreats?)" + _E, re.IGNORECASE)


def _starts_here(converted: str, first) -> bool:
    """The written line starts where its first move stands: nothing before it in the sentence tells another move —
    no other square named before the move's own clause, no «они берут»."""
    earlier = converted[: first.start()]
    cut = max(earlier.rfind(c) for c in ",;:—–(")
    earlier = earlier[: max(cut, 0)]
    own = set(re.findall(r"[a-h][1-8]", first["san"]))
    if any(sq not in own for sq in re.findall(r"(?<![a-z0-9])[a-h][1-8](?![0-9])", earlier.lower())):
        return False
    return not _THEY_MOVE.search(earlier)


def _ply(m, previous: Optional[int]) -> Optional[int]:
    """The half-move a written move is numbered as («8.Nc3» → 14, «8...Qxd5» → 15), else the one after *previous*."""
    if m["num"]:
        return 2 * (int(m["num"]) - 1) + (1 if (m["dots"] or "") in ("...", "…") else 0)
    return None if previous is None else previous + 1


def _segments(converted: str, tokens: list) -> list:
    """The written moves split where the text offers an alternative («Nf6 или Bc5») or a move's number does not
    follow the move before («8.Qxd5+ Qxd5 9.Bxd5+ Kxd5 …, а после 8.Nc3 …»: two branches, not 10.Nc3; review 30.10)."""
    out, cur, ply = [], [], None
    for m in tokens:
        here = _ply(m, ply)
        if cur and (_ALTERNATIVE.search(converted[cur[-1].end():m.start()])
                    or (m["num"] and ply is not None and here != ply + 1)):
            out.append(cur)
            cur = []
        cur.append(m)
        ply = here
    if cur:
        out.append(cur)
    return out


def line_claims(text: str, ctx) -> list:
    """The outcomes *text* (one sentence) promises at the end of a line it writes, for verify_claims. Also keeps
    the line on *ctx* for the sentence after it («Тогда белые выигрывают ферзя»)."""
    from src.answer_check import _CONTINUES, _DENIES, _FAILS, _RECOMMENDS, _to_san

    if ctx is None or not (text or "").strip():
        return []
    previous = getattr(ctx, "_line_end", None)  # (start board, moves, on the screen's board) of the sentence before
    ctx._line_end = None
    converted, _ = _to_san(text.replace("ё", "е"))
    low = converted.lower()
    tokens = _tokens(converted)
    # «Тогда …», «…, после чего ты забираешь ферзя» in a sentence with no moves of its own: the line before goes on
    # — not «Поэтому дальше спокойно развиваешься…», the plan instead of it.
    follows = previous is not None and not _INSTEAD.match(low) \
        and bool(_CONTINUES.match(converted) or (not tokens and _FOLLOWS.search(low)))
    previous_advice = getattr(ctx, "_line_advice", False)
    lines = []  # (end offset in the text, start board, moves, on the screen's board)
    segments = _segments(converted, tokens)
    for seg in segments:
        if not _starts_here(converted, seg[0]):
            continue
        found = _start(ctx, seg)
        if found is None and follows:
            end = _end_of(previous)
            moves = _play(end, seg)
            if moves:
                found = (previous[0], list(previous[1]) + moves, previous[2])
        if found is None:
            continue
        board, moves, on_current = found
        extra = len(moves) - len(seg)
        for i, m in enumerate(seg):
            lines.append((m.end(), board, moves[: extra + i + 1], on_current))
    if lines:
        ctx._line_end = lines[-1][1:]
        ctx._line_advice = bool(_RECOMMENDS.search(low))
    elif follows and not tokens:
        ctx._line_end = previous  # still the line before
    # A line the sentence refutes («Брать 8.Qxd5+ нельзя: после 8...Qxd5 белые остаются без ферзя») is not the one
    # the next sentence goes on with: «Поэтому дальше … у тебя перевес» is about the plan instead (review 30.10).
    if _FAILS.search(low) or _DENIES.search(converted):
        ctx._line_end = None
    if "?" in text or len(segments) > 1:
        return []  # a question; alternatives («Qd3 или Qxd5+ — и белые выигрывают фигуру»): which line is meant is not known
    claims = []
    for rx, good in _CLAIMS:
        for m in rx.finditer(low):
            at = m.start("v")
            before = [ln for ln in lines if ln[0] <= m.start()]
            line = before[-1] if before else None
            if line is None and follows and not tokens and (_CONTINUES.match(converted) or _FOLLOWS.search(low[:m.start()])):
                line = (0,) + tuple(previous)
            if line is None:
                continue
            if not _claimed(low, converted, at, m.end()) or _CONDITION.search(low[line[0]:m.start()]) \
                    or _CONDITION.search(_clause_after(low, m.end())):
                continue
            side_word = m.groupdict().get("side") or ""
            color = _side_of(side_word, ctx, line[3], low)
            if color is None:
                continue
            favoured = color if good else not color
            claims.append({"kind": "line", "board": line[1], "moves": line[2], "side": favoured,
                           "words": converted[m.start():m.end()].strip()[:80], "stake": _stake(m.group("v"))})
    for m in _MOVE_SUBJECT.finditer(converted):
        before = [ln for ln in lines if ln[0] <= m.start("v")]
        if not before or not _claimed(low, converted, m.start("v"), m.end()):
            continue
        line = before[-1]
        if _CONDITION.search(low[line[0]:m.start()]) or _CONDITION.search(_clause_after(low, m.end())):
            continue
        mover = line[1].turn if len(line[2]) % 2 == 1 else not line[1].turn
        good = not _MOVE_SUBJECT_BAD.match(m.group("v"))
        claims.append({"kind": "line", "board": line[1], "moves": line[2], "side": mover if good else not mover,
                       "words": m.group(0).strip()[:80], "stake": _stake(m.group("v"))})
    for rx in _SWING:
        for m in rx.finditer(low):
            from src.claim_scope import denied_before

            if denied_before(low, m.start(), 24):
                continue
            if not _AGAINST_BEFORE.match(low, m.end()) and not _COMPARED.search(low):
                continue  # «белые стоят на пешку лучше» is the evaluation, not the change a move made
            n = m["n"].lower().replace(",", ".")
            pawns = float(n) if re.fullmatch(r"\d+(?:\.\d+)?", n) else _NUMBERS.get(n)
            if not pawns:
                continue
            ref = _swing_reference(lines, previous, previous_advice, ctx, low)
            if ref is None:
                continue
            board, moves = ref
            worse = m["dir"].lower() in ("хуже", "worse")
            claims.append({"kind": "swing", "board": board, "moves": moves, "side": board.turn,
                           "pawns": -pawns if worse else pawns, "words": converted[m.start():m.end()].strip()[:80]})
    for c in claims:
        if c["kind"] == "swing":
            _name_trade(c, low, ctx)
    if not tokens and not follows and previous is None:
        claims.extend(_piece_claims(low, converted, ctx))
    # One verdict per line end is enough: the first claims of the sentence.
    out, seen = [], set()
    for c in claims:
        key = (c["kind"], c["board"].fen(), tuple(c["moves"]), c["side"], c.get("piece"))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out[:MAX_CLAIMS]


def _claimed(low: str, text: str, at: int, end: int) -> bool:
    """The outcome at *at* is the coach's own claim: not denied, not the student's belief or a quote, and not one
    whose price the sentence names after it."""
    from src.claim_scope import denied_before

    return not (denied_before(low, at, 30) or _BELIEF.search(low[:at]) or _PRICE.search(low[end:])
                or "«" in text[:at] or '"' in text[:at])


def _swing_reference(lines: list, previous, previous_advice: bool, ctx, low: str) -> Optional[tuple]:
    """The move the number is about: this sentence's line, the line of the sentence before, or the one move the
    student asked about («А если b3?» — «…это почти на четыре пешки хуже»), played on the board on the screen.

    A sentence without a line of its own is judged only when the move it is about is not in doubt (review 30.10:
    «Правильно здесь 4.Nxd4 … . А взятие пешки конём — это почти на две пешки хуже, чем было» is about 4.Nxe5, not
    the line before): not after the coach's recommendation, not when the student asked about another move, not
    when the sentence names a square the move does not touch («из-за ответа ферзём на g5», «взять на e5»)."""
    if lines:
        return lines[-1][1], lines[-1][2]
    quoted = []
    if ctx.current is not None:
        for q in sorted(ctx.quoted or ()):
            try:
                quoted.append(ctx.current.parse_san(q))
            except ValueError:
                continue
    if previous is not None:
        board, moves = previous[0], list(previous[1])
        if previous_advice or (quoted and (board is not ctx.current or moves[0] not in quoted)):
            return None
    elif len(quoted) == 1:
        board, moves = ctx.current, quoted
    else:
        return None
    touched = {chess.square_name(sq) for mv in moves for sq in (mv.from_square, mv.to_square)}
    if any(sq not in touched for sq in re.findall(r"(?<![a-z0-9])[a-h][1-8](?![0-9])", low)):
        return None
    return board, moves


def _clause_after(low: str, end: int) -> str:
    """The rest of the outcome's clause: up to the end of the sentence or a «;»."""
    return re.split(r"[.;!?]", low[end:], maxsplit=1)[0]


_STAKES = (("ферз", (chess.QUEEN,)), ("ладь", (chess.ROOK,)), ("качеств", (chess.ROOK,)), ("кон", (chess.KNIGHT,)),
           ("слон", (chess.BISHOP,)), ("фигур", (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)),
           ("материал", (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)), ("queen", (chess.QUEEN,)),
           ("rook", (chess.ROOK,)), ("exchange", (chess.ROOK,)), ("knight", (chess.KNIGHT,)), ("bishop", (chess.BISHOP,)),
           ("piece", (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)),
           ("material", (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)))


def _stake(verb: str) -> Optional[tuple]:
    """The pieces an outcome is about («выигрывают ферзя», «забирает фигуру»), or None for the game, an evaluation,
    a mate: a material outcome is a statement about material (see _verify_line)."""
    v = (verb or "").lower().replace("ё", "е")
    if re.search(r"мат(?![а-яё])|матует|mates|партию|игру|the\s+game", v):
        return None
    for word, kinds in _STAKES:
        if word in v:
            return kinds
    return None


# ── an outcome tied to a piece: «решает ферзь» (plan 31.10, P4 C2, detector piece_decides) ──────────────────────
#
# «Нет, мата в два хода тут нет — но … король чёрных застрял в центре на e6, и решает ферзь.» (mate2-no, prod 29.10):
# no line is written, yet the sentence promises an outcome for a piece on the board now — and no queen move wins
# there (the queen's best, Qg3, is −3; the engine's move is the quiet 8.Nc3, +1). What the sentence promises is
# that piece's best move: one search restricted to its legal moves (searchmoves) against the engine's best.
#
# Judged only when the board is not in doubt and the claim is the coach's own, about now: no written move in the
# sentence and no line in the one before (that is the line's end, judged by _verify_line), no condition, no
# general statement («в таких позициях обычно решает конь»), no future or past, no question, not denied, not a
# belief, one piece type named (not «слон и ферзь решают»), no adjective but the owner's (not «лишний конь»), the
# piece's side to move. A pawn or the king is never the subject: «лишняя пешка решает партию», «решает активный
# король» tell material or activity, not a move.
_PIECE_NOM = {"ферзь": chess.QUEEN, "ферзи": chess.QUEEN, "ладья": chess.ROOK, "ладьи": chess.ROOK,
              "конь": chess.KNIGHT, "кони": chess.KNIGHT, "слон": chess.BISHOP, "слоны": chess.BISHOP,
              "queen": chess.QUEEN, "rook": chess.ROOK, "knight": chess.KNIGHT, "bishop": chess.BISHOP}
_PIECE_INS = {"ферзем": chess.QUEEN, "ладьей": chess.ROOK, "конем": chess.KNIGHT, "слоном": chess.BISHOP}
_PIECE_WORD = r"(?P<piece>ферз[ьи]|ладь[яи]|кон[ьи]|слоны?|queen|rook|knight|bishop)"
# The owner told next to the piece: «белый ферзь», «ферзь белых», «твой конь», «their queen».
_OWNER_BEFORE = (r"(?:(?P<own>бел(?:ый|ая|ые)|ч[её]рн(?:ый|ая|ые)|тво(?:й|я|и)|сво(?:й|я|и)|мо(?:й|я|и)|его|ее|её|их|"
                 r"white's|black's|your|my|their|his|her)\s+)?")
_OWNER_AFTER = r"(?:\s+(?P<own2>белых|ч[её]рных|соперника|противника))?"
_ON_SQUARE = r"(?:\s+(?:на\s+|on\s+)?(?P<sq>[a-h][1-8])(?![0-9a-z]))?"
_DECIDES_OBJ = r"(?:\s+(?:вс[её]|дело|исход(?:\s+партии)?|партию|игру|the\s+game|it|matters))?"
_PIECE_END = r"(?=\s*(?:[.,;:!—–)]|$))"
_FILLER = r"(?:(?:и|а|но|тут|здесь|теперь|сейчас|уже|сразу|именно|вс[её]|просто|and|here|now)\s+)"
_DECIDES_VERB = re.compile(r"реша|выигрывает|decide|decisive|wins", re.IGNORECASE)
_DECIDES = [
    # «… и решает ферзь», «всё решает белый ферзь на f3», «у белых решает ферзь», "here the queen decides"
    re.compile(_W + rf"(?:у\s+(?P<at>белых|ч[её]рных|тебя|соперника|противника)\s+)?{_FILLER}{{0,3}}(?P<v>реша(?:ет|ют)|выигрывает)\s+"
               rf"(?:(?:вс[её]|дело|исход(?:\s+партии)?|партию|игру|тут|здесь|сейчас|теперь|сразу)\s+){{0,2}}"
               + _OWNER_BEFORE + _PIECE_WORD + _ON_SQUARE + _OWNER_AFTER + _PIECE_END, re.IGNORECASE),
    # «ферзь решает», «конь на d5 решает исход партии», "the queen decides the game"
    re.compile(_W + r"(?:the\s+)?" + _OWNER_BEFORE + _PIECE_WORD + _ON_SQUARE + _OWNER_AFTER + r"\s+" + _FILLER + r"{0,2}"
               r"(?P<v>реша(?:ет|ют)|выигрывает|decides?|is\s+decisive|wins)" + _DECIDES_OBJ + _PIECE_END, re.IGNORECASE),
    # «белые решают ферзём», «решаешь конём»
    re.compile(_W + r"(?:(?P<subj>белые|ч[её]рные|ты)\s+)?" + _FILLER + r"{0,2}(?P<v>реша(?:ют|ешь|ет))\s+"
               r"(?:(?:вс[её]|дело|исход|партию|игру|тут|здесь|сразу)\s+){0,2}(?P<ins>ферзем|ладьей|конем|слоном)"
               + _ON_SQUARE + _PIECE_END, re.IGNORECASE),
]
# Not the board now, or not a claim: a condition, a general statement, an example offered, another time (a line's
# end, the future, a famous game), a possibility («может решить»), a subjunctive.
_NOT_NOW = re.compile(_W + r"(?:если|когда|коли|пока|где|куда|бы|б|может|могут|мог\w*|обычно|часто|нередко|чаще|редко|"
                      r"как\s+правило|всегда|иногда|бывает|нередк\w+|в\s+(?:таких|подобных|этих|похожих|некоторых)|"
                      r"в\s+(?:эндшпил\w*|миттельшпил\w*|дебют\w*|целом|принципе|теории|итоге|конце|результате)|вообще|"
                      r"пример\w*|задач\w*|урок\w*|хочешь|давай|представь\w*|допустим|в\s+партии|в\s+той|в\s+игре|"
                      r"после|потом|затем|дальше|далее|позже|скоро|будет|станет|in\s+such|usually|often|always|"
                      r"sometimes|if|when|would|could|might|after|later|then|example)" + _E, re.IGNORECASE)
_ADVERB_OR_FUNCTION = frozenset("и а но тут здесь теперь сейчас уже сразу именно всё все просто да же вот ведь and here now so "
                                "the у".split())
_COLOUR_TO_MOVE = {chess.WHITE: re.compile(_W + r"бел(?:ых|ым|ыми|ого|ой|ому|ом)" + _E + r"|white's|for\s+white", re.IGNORECASE),
                   chess.BLACK: re.compile(_W + r"ч[её]рн(?:ых|ым|ыми|ого|ой|ому|ом)" + _E + r"|black's|for\s+black",
                                           re.IGNORECASE)}
# Two pieces joined («слон h6 и ферзь g5 решают», «решает ферзь вместе с ладьёй»): not one piece's move.
_ANY_PIECE = r"(?:ферз\w*|ладь\w*|кон[ьяюеи]\w*|слон\w*|пешк\w*|корол\w*|queens?|rooks?|knights?|bishops?|pawns?|kings?)"
_JOINED_BEFORE = re.compile(_W + _ANY_PIECE + r"(?:\s+(?:на\s+)?[a-h][1-8])?\s*(?:,|и|and|или|or|с|with)\s+(?:\w+\s+)?$", re.IGNORECASE)
_JOINED_AFTER = re.compile(r"\s*(?:,\s*|\s)(?:и|and|или|or|а\s+также|вместе\s+с|с|with)\s+(?:\w+\s+)?" + _ANY_PIECE, re.IGNORECASE)
_AT_SIDE = re.compile(_W + r"у\s+(белых|ч[её]рных|тебя|соперника|противника)" + _E, re.IGNORECASE)
_SECOND_PERSON = re.compile(_W + r"(?:ты|тебя|тебе|тобой|тво\w+|сво\w+|you|your)" + _E, re.IGNORECASE)


def _owner(word: str, ctx, sentence: str) -> Optional[bool]:
    """The colour an owner word names, None when it names none («его» outside a game)."""
    from src.answer_check import student_side

    w = (word or "").lower().replace("ё", "е")
    if w.startswith(("бел", "white")):
        return chess.WHITE
    if w.startswith(("черн", "black")):
        return chess.BLACK
    student = student_side(ctx, sentence)
    if student is None:
        return None
    if w.startswith(("тво", "сво", "тебя", "ты", "your")):
        return student
    if w.startswith(("мо", "my", "его", "ее", "их", "соперн", "против", "their", "his", "her")):
        return None if ctx.student_color is None else (not student)
    return None


def _scene_board(ctx) -> Optional[chess.Board]:
    """The one board a claim about «now» may mean: the board on the screen, when the turn shows no other state
    (the start position standing in for an unknown one aside) and no written line the sentence may be about."""
    cur = getattr(ctx, "current", None)
    if cur is None:
        return None
    if getattr(ctx, "scene", None) is not None and getattr(ctx, "scene_age", 0) < 2:
        return None  # a move the answer just wrote: «Теперь решает ферзь» is about the board after it
    if getattr(ctx, "quoted", None):
        return None  # «А если b3?» — the answer may be about the board after the student's move
    others = set()
    for key in getattr(ctx, "state_keys", set()):
        if key == ctx._key(cur) or key in getattr(ctx, "text_keys", set()):
            continue
        if key.split(" ")[0] == chess.STARTING_BOARD_FEN and cur.board_fen() != chess.STARTING_BOARD_FEN:
            continue  # the start position stands in for an unknown one
        others.add(key)
    return None if others else cur


# The claim read by its parts (review 01.11: «Всё решает ход ферзя», «Ферзём ты выигрываешь сразу», «Решающий удар
# наносит ферзь», «Ферзь в одиночку решает всё», «Ферзь у белых решает» were missed — the patterns above take one word
# order and one case). In one clause (split at «;:—()» and at «, и / а / но …»): an outcome predicate, one piece as
# its actor in any case and order — the subject («решает ферзь»), the instrument («ферзём ты выигрываешь»), the
# actor of an action noun («ход ферзя», «атака ферзём», «ферзевая атака») or «решающее слово за ферзём» —, and
# nothing else but the owner, the piece's square, the game as the object («партию», «всё», «исход»), a place («в
# центре», «на короля e6»: a target) and adverbs. Any other word, a denial, a hedge, a second piece or a pawn or king
# as an actor leaves the clause unjudged: unjudged is fine, a false cut is not.
# the outcome predicate as a lemma class (review-miss2 01.11): the present and the future of «решать / выигрывать /
# побеждать / решить / выиграть / победить», «приносит / обеспечивает победу», «решающий удар / ход / фигура»,
# «решение за X», «козырь», «(всё) кончается X-ом»
_PV_DECIDE = re.compile(r"^(?:реша(?:ет|ют|ешь|ете)|выигрыва(?:ет|ют|ешь|ете)|побежда(?:ет|ют|ешь|ете)|"
                        r"реш(?:ит|ат|ишь|ите)|выигра(?:ет|ют|ешь|ете)|побед(?:ит|ят|ишь|ите))$")
_PV_DECIDE_INF = re.compile(r"^(?:выиграть|решить|победить)$")  # with «можно»: «выиграть здесь можно ферзём»
_PV_BRING = re.compile(r"^(?:принос(?:ит|ят|ишь|ите)|принес(?:ет|ут)|обеспечива(?:ет|ют)|обеспечит|обеспечат)$")
_PV_BRING_OBJ = frozenset("победу выигрыш успех".split())
_PV_DECISIVE = re.compile(r"^решающ(?:ий|ее|ую|им|ая|его|ей)$")
_PV_DECISIVE_NOUN = frozenset("удар слово ход".split())
_PV_DECISIVE_PIECE = frozenset("фигура фигурой силой сила".split())  # «ферзь — решающая фигура»: no verb needed
_PV_TRUMP = re.compile(r"^(?:козыр[ьяем]|козырем)$")
_PV_END = re.compile(r"^(?:конча(?:ет|ют)ся|заканчива(?:ет|ют)ся|заверша(?:ет|ют)ся)$")
_PV_DECISIVE_VERB = frozenset("наносит наносят делает делают принадлежит остается за у".split())
_PV_NOM = {"ферзь": chess.QUEEN, "ферзи": chess.QUEEN, "ладья": chess.ROOK, "ладьи": chess.ROOK, "конь": chess.KNIGHT,
           "кони": chess.KNIGHT, "слон": chess.BISHOP, "слоны": chess.BISHOP}
_PV_INS = {"ферзем": chess.QUEEN, "ладьей": chess.ROOK, "конем": chess.KNIGHT, "слоном": chess.BISHOP,
           "ферзями": chess.QUEEN, "ладьями": chess.ROOK, "конями": chess.KNIGHT, "слонами": chess.BISHOP}
_PV_GEN = {"ферзя": chess.QUEEN, "ладьи": chess.ROOK, "коня": chess.KNIGHT, "слона": chess.BISHOP}
_PV_ADJ = ((re.compile(r"^ферзев\w+$"), chess.QUEEN), (re.compile(r"^ладейн\w+$"), chess.ROOK))
_PV_ACTION = re.compile(r"^(?:ход|хода|ходом|удар|удара|ударом|атак[аиуой]|атакой|вторжени[ея]|рейд|маневр|жертв[аы]|шах|шахи|"
                        r"прорыв|нападени[ея]|налет)$")
_PV_PIECE_FAMILY = re.compile(r"^(?:ферз\w*|ладь\w*|ладей|кон[ьяюеи]\w*|коней|слон\w*|пешк\w*|пешек|корол\w*|фигур\w*)$")
_PV_PREP = frozenset("в во на у к ко по против за от без для с со под над перед из через при о об про около возле".split())
_PV_OBJECT = frozenset("все дело исход исхода партии партию игру игры матч судьбу встречу".split())
_PV_OWNER = re.compile(r"^(?:бел(?:ый|ая|ые|ых|ого|ым)|черн(?:ый|ая|ые|ых|ого|ым)|тво(?:й|я|и|его|им)|сво(?:й|я|и)|"
                       r"мо(?:й|я|и)|его|ее|их|соперника|противника|ты|вы)$")
_PV_FUNCTION = frozenset("и а же ведь вот да тут здесь теперь сейчас уже сразу именно просто один одна одни сам сама "
                         "одиночку вмиг тотчас немедленно лично главный главная главное это он она позиции этой "
                         "можно".split())
_PV_HEDGE = frozenset("почти возможно наверное наверно вероятно пожалуй видимо кажется скорее может могут вряд едва "
                      "иногда часто обычно потом позже скоро рано поздно когда-нибудь якобы будто ли бы".split())
_PV_DENY = frozenset("не нет ни ничего никак никогда нельзя".split())
_PV_CLAUSE = re.compile(r"[.;:!?()«»\"—–]|,\s*(?=(?:и|а|но|однако|зато|хотя|потому|так|поскольку|если|когда|пока|чтобы|что|"
                        r"где|ведь|ибо)(?![а-яё]))|\s(?=(?:но|а|однако|зато)\s)")


def _outcome_parts(clause: str):
    """(piece type, owner word, square, actor's offset in *clause*) of the outcome claim *clause* makes, or None."""
    toks = [(m.group(0), m.start()) for m in re.finditer(r"[a-h][1-8](?![0-9a-z])|[а-я]+(?:-[а-я]+)?|[a-z']+", clause)]
    if not toks:
        return None
    words = [t for t, _ in toks]
    if any(w in _PV_DENY or w in _PV_HEDGE for w in words):
        return None
    used = [False] * len(words)
    # the predicate
    preds = []
    for i, w in enumerate(words):
        if _PV_DECIDE.match(w):
            preds.append((i, [i]))
        elif _PV_DECIDE_INF.match(w) and "можно" in words:
            preds.append((i, [i, words.index("можно")]))
        elif _PV_TRUMP.match(w) or _PV_END.match(w):
            preds.append((i, [i]))
        elif w == "решение" and i + 1 < len(words) and words[i + 1] == "за":
            preds.append((i, [i, i + 1]))
        elif _PV_DECISIVE.match(w) and i + 1 < len(words) and words[i + 1] in _PV_DECISIVE_PIECE:
            preds.append((i, [i, i + 1]))
        elif _PV_DECISIVE.match(w) and (i + 1 == len(words) or words[i + 1] not in _PV_DECISIVE_NOUN) and \
                any(_PV_ACTION.match(x) for x in words[:i]):
            preds.append((i, [i]))  # «ферзевый удар здесь решающий»: the adjective as the predicate
        elif _PV_BRING.match(w):
            obj = [j for j, x in enumerate(words) if x in _PV_BRING_OBJ]
            if obj:
                preds.append((i, [i, obj[0]]))
        elif _PV_DECISIVE.match(w) and i + 1 < len(words) and words[i + 1] in _PV_DECISIVE_NOUN:
            span = [i, i + 1]
            verb = [j for j, x in enumerate(words) if x in _PV_DECISIVE_VERB and j not in span]
            if not verb:
                continue
            preds.append((i, span + verb[:1]))
    if not preds:
        return None
    pi, pspan = preds[0]
    for _, extra in preds[1:]:
        pspan = pspan + extra  # «главный козырь — ферзь, он и решает»: one claim said twice
    for j in pspan:
        used[j] = True
    second_person = words[pi].endswith(("ешь", "ете"))
    # the actor
    actors = []
    for i, w in enumerate(words):
        if used[i]:
            continue
        prev = words[i - 1] if i else ""
        if w in _PV_NOM and prev not in _PV_PREP:
            if w == "ладьи" and prev and _PV_ACTION.match(prev):
                actors.append((i, chess.ROOK, [i - 1, i]))
            else:
                actors.append((i, _PV_NOM[w], [i]))
        elif w in _PV_INS:
            if prev and _PV_ACTION.match(prev):
                actors.append((i, _PV_INS[w], [i - 1, i]))
            elif prev == "за" and (words[pi].startswith("решающ") or words[pi] == "решение"):
                actors.append((i, _PV_INS[w], [i - 1, i]))  # «решающее слово за ферзём», «решение за ферзём»
            elif prev in _PV_PREP:
                return None  # «вместе с ладьёй», «за конём»: another role
            else:
                actors.append((i, _PV_INS[w], [i]))  # «ферзём ты выигрываешь», «белые решают ладьёй»
        elif w in _PV_GEN and prev and _PV_ACTION.match(prev):
            actors.append((i, _PV_GEN[w], [i - 1, i]))  # «ход ферзя»
        elif w in _PV_GEN and i >= 2 and words[i - 2] == "за" and prev == "счет":
            actors.append((i, _PV_GEN[w], [i - 2, i - 1, i]))  # «выигрывают за счёт ферзя»
        else:
            for rx, pt in _PV_ADJ:
                if rx.match(w) and i + 1 < len(words) and _PV_ACTION.match(words[i + 1]):
                    actors.append((i, pt, [i, i + 1]))  # «ферзевая атака»
    if len({pt for _, pt, _ in actors}) != 1:
        return None
    ai, ptype, _ = actors[0]
    for _, _, span in actors:
        for j in span:
            used[j] = True
    # the owner and the square, next to the actor
    own, sq = "", None
    a_last = max(j for _, _, span in actors for j in span)
    k = a_last + 1
    if k < len(words) and words[k] == "на" and k + 1 < len(words) and re.match(r"^[a-h][1-8]$", words[k + 1]):
        sq, used[k], used[k + 1] = words[k + 1], True, True
    elif k < len(words) and re.match(r"^[a-h][1-8]$", words[k]):
        sq, used[k] = words[k], True
    # a place: «в центре», «на королевском фланге», «на короля e6» (a target), «у белых» (the owner) — up to three
    # words, no other actor among them; an owner word inside a target is the target's, not the actor's
    i = 0
    while i < len(words):
        w = words[i]
        if used[i] or w not in _PV_PREP:
            i += 1
            continue
        j = i + 1
        while j < len(words) and j <= i + 3 and not used[j] and not _PV_DECIDE.match(words[j]):
            if _PV_PIECE_FAMILY.match(words[j]) and w not in ("на", "против", "по"):
                return None  # «с ладьёй», «у ферзя»: another piece in another role
            if w == "у" and j == i + 1 and _PV_OWNER.match(words[j]):
                own = own or words[j]  # «ферзь у белых решает»
            j += 1
            if j < len(words) and (words[j] in _PV_PREP or words[j] in _PV_FUNCTION or (
                    _PV_OWNER.match(words[j]) and not (re.match(r"^(?:\w+ых|соперника|противника)$", words[j])
                                                       and _PV_PIECE_FAMILY.match(words[j - 1])))):
                break  # «на короля чёрных»: the target's owner; «в центре белые решают»: the subject's
        for x in range(i, j):
            used[x] = True
        i = j
    for i, w in enumerate(words):
        if used[i]:
            continue
        if _PV_OWNER.match(w):
            if w in ("ты", "вы") and not second_person:
                return None
            own = own or w
            used[i] = True
    if second_person and not own:
        own = "ты"
    # every other word: the game as the object, an adverb, a function word
    for i, w in enumerate(words):
        if used[i]:
            continue
        if _PV_PIECE_FAMILY.match(w):
            return None  # a second piece, a pawn or the king as a subject: not one piece's move
        if w in _PV_OBJECT or w in _PV_FUNCTION or w in _ADVERB_OR_FUNCTION or re.match(r"^[a-h][1-8]$", w):
            continue
        if len(w) >= 5 and w.endswith(("о", "ски")) and w not in _PV_HEDGE:
            continue  # an adverb of manner: «быстро», «мгновенно», «конечно»
        return None  # a word the claim does not explain: «решает задачу», «выигрывает пешку», «лишний конь»
    return ptype, own, sq, toks[ai][1]


_OUTCOME_CUE = re.compile(r"реш|выигр|побед|принос|принес|обеспечи|козыр|конча|заканчива|заверша")


def _piece_claims(low: str, converted: str, ctx) -> list:
    """«решает ферзь»: the claims that a piece of the side to move decides the game on the board now."""
    from src import config
    from src.claim_scope import denied_before, denied_in

    if "?" in low or not (_DECIDES_VERB.search(low) or _OUTCOME_CUE.search(low)):
        return []  # the cheap test first: this runs on every sentence without a written move
    mode = config.detector_mode("piece_decides", ctx)
    if mode == "off":
        return []
    found = []  # (piece type, owner word, square, offset of the piece, offset of the claim, end, the rx or None)
    for rx in _DECIDES:
        for m in rx.finditer(low):
            at = m.start("v")
            start = m.start()
            clause_from = max(low.rfind(c, 0, start) for c in ";:—–(")
            clause = low[clause_from + 1: m.end()]
            if denied_before(low, at, 30) or denied_in(clause) or _BELIEF.search(low[:at]) or "«" in converted[:at] \
                    or '"' in converted[:at] or _NOT_NOW.search(low):
                continue
            gd = m.groupdict()
            word = (gd.get("piece") or "").replace("ё", "е")
            ptype = _PIECE_NOM.get(word) or _PIECE_INS.get((gd.get("ins") or "").replace("ё", "е"))
            if ptype is None:
                continue
            # The words before the piece: an adjective other than the owner's («лишний конь», «второй ферзь») or
            # another piece joined by «и» («слон h6 и ферзь g5 решают») — not one piece's move.
            head = low[max(0, start - 40): start].split()
            if rx is _DECIDES[1] and head and not gd.get("own"):
                prev = re.sub(r"[^\wё]", "", head[-1])
                if prev and prev not in _ADVERB_OR_FUNCTION and not head[-1].endswith((",", ":", ";", "—")):
                    continue
            at_piece = m.start("piece") if gd.get("piece") else m.start("ins")
            if _JOINED_BEFORE.search(low[:at_piece]) or _JOINED_AFTER.match(low, m.end()):
                continue
            own = gd.get("own") or gd.get("own2") or gd.get("at") or gd.get("subj") or ""
            if not own:
                # «У чёрных в защите решает ферзь»: the owner told earlier in the clause.
                at_side = _AT_SIDE.findall(low[clause_from + 1: at])
                own = at_side[-1] if at_side else ""
            found.append((ptype, own, gd.get("sq"), at_piece, m.start(), m.end()))
    if not found and not _NOT_NOW.search(low) and "«" not in converted and '"' not in converted:
        norm = low.replace("ё", "е")
        for text_ in (norm, re.sub(r"\s[—–]\s", "   ", norm)):  # a dash may be the copula: «Ферзь — решающая фигура»
            bounds = [0] + [m.end() for m in _PV_CLAUSE.finditer(text_)] + [len(text_)]
            for a, b in zip(bounds, bounds[1:]):
                parts = _outcome_parts(text_[a:b])
                if parts is None or _BELIEF.search(text_[:a + parts[3]]):
                    continue
                ptype, own, sq, at_piece = parts
                if not own:
                    at_side = _AT_SIDE.findall(text_[a:b])
                    own = at_side[-1] if at_side else ""
                found.append((ptype, own, sq, a + at_piece, a, b))
            if found:
                break
    out = []
    for ptype, own, sq_name, _at_piece, start, end in found:
        board = _scene_board(ctx)
        if board is None:
            continue
        side = _owner(own, ctx, low) if own else board.turn
        if side is None or side != board.turn:
            continue  # the other side's piece is a threat, not a move now; an owner not known is not guessed
        if not own:
            # Unowned: the side to move's — unless the sentence names that side as the victim («король белых
            # в опасности, решает ферзь») or speaks to a student who is not to move.
            if _COLOUR_TO_MOVE[side].search(low):
                continue
            from src.answer_check import student_side

            student = student_side(ctx, low)
            if _SECOND_PERSON.search(low) and student is not None and student != side:
                continue
        square = chess.parse_square(sq_name) if sq_name else None
        if square is not None:
            p = board.piece_at(square)
            if p is None or p.piece_type != ptype or p.color != side:
                continue  # a piece not there is another check's error
            squares = [square]
        else:
            squares = list(board.pieces(ptype, side))
        if not squares or not any(mv.from_square in squares for mv in board.legal_moves):
            continue  # no such piece, or it cannot move: what the sentence means is not a move of it
        out.append({"kind": "piece_decides", "board": board, "moves": [], "side": side, "piece": ptype,
                    "squares": tuple(squares), "words": converted[start:end].strip(" ,")[:80], "mode": mode})
    return out[:1]


# ── a named trade's swing: «отдают слона за пешку — это почти на четыре пешки хуже» (C8, trade_swing_named) ──────
#
# _verify_swing lets a figure pass when it lies between the material the line loses (along the engine's
# continuation) and the engine's swing: a coach counting material is not contradicted. When the sentence names the
# trade itself, the coach's count is that trade's (bishop for a pawn: 2), and a figure that is neither that count
# nor the engine's swing (pawn-b3-bare: 4 against 2 and 6.5) is wrong. Off until Асан agrees to change the
# tolerance he approved (COACH_TRADE_SWING_NAMED; plan 31.10 §7).
_TRADE_VALUE = {"ферз": 9, "ладь": 5, "качеств": 2, "кон": 3, "слон": 3, "фигур": 3, "пешк": 1, "queen": 9, "rook": 5,
                "exchange": 2, "knight": 3, "bishop": 3, "piece": 3, "pawn": 1}
_COUNT = {"одну": 1, "одного": 1, "две": 2, "два": 2, "двух": 2, "три": 3, "трех": 3, "трёх": 3, "2": 2, "3": 3,
          "two": 2, "three": 3, "a": 1, "an": 1}
_UNIT = (r"(?:(?:одну|одного|две|два|двух|три|тр[её]х|[23]|two|three|a|an)\s+)?"
         r"(?:ферз[яейи]\w*|ладь[юиейя]\w*|качеств\w*|кон[яейи]\w*|слон\w*|фигур\w*|пешк\w*|queens?|rooks?|"
         r"the\s+exchange|knights?|bishops?|pieces?|pawns?)")
_TRADE = re.compile(_W + r"(?:отда\w*|отдад\w*|разменива\w*|меня\w*|разменя\w*|теря\w*|потеря\w*|gives?|giving|gave|trades?|"
                    r"swaps?|loses?|losing)\s+(?:(?:сво\w+|тво\w+|целого|целую|целый|сразу|за\s+бесценок|up|away)\s+)*"
                    rf"(?P<given>{_UNIT}(?:\s+(?:и|and)\s+{_UNIT})?)\s+(?:за|на|for)\s+"
                    rf"(?P<got>{_UNIT}(?:\s+(?:и|and)\s+{_UNIT})?)" + _E, re.IGNORECASE)


def _units(words: str) -> Optional[int]:
    """The material value of «слона», «две пешки», «пешку и слона» (P1 N3 B3 R5 Q9, the exchange 2)."""
    total = 0
    for part in re.split(r"\s+(?:и|and)\s+", words.strip()):
        bits = part.split()
        n = _COUNT.get(bits[0], None) if len(bits) > 1 else None
        if n is not None:
            bits = bits[1:]
        name = " ".join(bits)
        v = next((val for stem, val in _TRADE_VALUE.items() if name.startswith(stem) or name.startswith("the " + stem)),
                 None)
        if v is None:
            return None
        total += v * (n or 1)
    return total


def _name_trade(claim: dict, low: str, ctx) -> None:
    """Keep on a swing claim the trade its sentence names before the figure (claim["named"], the pawns the giver
    loses), when trade_swing_named is not off."""
    from src import config

    mode = config.detector_mode("trade_swing_named", ctx)
    if mode == "off":
        return
    at = low.find((claim.get("words") or "").lower()[:20])
    for m in _TRADE.finditer(low[: at if at > 0 else len(low)]):
        given, got = _units(m["given"]), _units(m["got"])
        if given is not None and got is not None and given > got:
            claim["named"] = given - got
            claim["named_words"] = m.group(0).strip()[:60]
            claim["named_mode"] = mode


# ── the engine ──────────────────────────────────────────────────────────────


def _eval(board: chess.Board, movetime_ms: int) -> Optional[tuple]:
    """(White's score in pawns, the engine's line as SAN) for *board*, or None."""
    from src import hypothetical
    from src.hypothetical import MIN_DEPTH, _san_line, _white_pawns

    if board.is_checkmate():
        return (-MATE_PAWNS if board.turn == chess.WHITE else MATE_PAWNS), []
    if board.is_game_over():
        return 0.0, []
    # K3 02.11: at the engine stage's fixed depth (src/hypothetical.VERIFY_DEPTH, the exact store), not a timed look or
    # whatever the analysis cache held — op-show-italian's «опасная для чёрных» was cut or shown by what earlier turns
    # had searched (verify1102: caught in a full replay, missed alone, on the same tree)
    import time

    line = hypothetical._look(board.fen(), movetime_ms, time.monotonic() + hypothetical.VERIFY_MAX_MS / 1000.0)
    if not line:
        return None
    return _white_pawns(line, board.turn), _san_line(board, line.get("pv", ""), MAX_PLIES)


def _material(board: chess.Board, color: bool) -> int:
    from src.hypothetical import _VALUE

    return sum(_VALUE[p.piece_type] * (1 if p.color == color else -1) for p in board.piece_map().values())


def _line_text(board: chess.Board, moves: list) -> tuple[str, chess.Board]:
    from src.hypothetical import _numbered

    b = board.copy(stack=False)
    sans = []
    for mv in moves:
        sans.append(b.san(mv))
        b.push(mv)
    return _numbered(board, sans), b


def _name(color: bool) -> str:
    return "White" if color == chess.WHITE else "Black"


def _took(board: chess.Board, moves: list, side: bool, kinds: tuple) -> bool:
    """Does *side* capture a piece of *kinds* in the line?"""
    b = board.copy(stack=False)
    for mv in moves:
        if b.turn == side and b.piece_type_at(mv.to_square) in kinds:
            return True
        b.push(mv)
    return False


def _verify_line(claim: dict, movetime_ms: int, reveal: bool) -> Optional[str]:
    from src.hypothetical import _fmt, _numbered

    board, moves, side = claim["board"], claim["moves"], claim["side"]
    # A material outcome is a statement about material (review 30.10, Legal's mate: «…5.Nxe5 Bxd1 — чёрные выигрывают
    # ферзя.» «Но после 6.Bxf7+ Ke7 7.Nd5# белые ставят мат.»): true when the line itself takes that piece, whatever
    # the price told in the next sentence.
    stake = claim.get("stake")
    if stake and _took(board, moves, side, stake):
        return None
    line, end = _line_text(board, moves)
    got = _eval(end, movetime_ms)
    if got is None:
        return None
    white, pv = got
    mine = white if side == chess.WHITE else -white
    if stake and mine <= -(MATE_PAWNS - 0.5):
        # …and a mate against the side is the price of the grab (the Blackburne trap: «7.Be2 белые уже выигрывают
        # ладью.» «Однако следует 7...Nf3#»), often told in the sentence after; not the material contradicted.
        return None
    said = f"«{claim['words']}»"
    cont = f" (it goes on {_numbered(end, pv[:4])})" if reveal and pv and abs(white) < MATE_PAWNS - 0.5 else ""
    where = f"after {line}"
    if mine <= -CLEAR_PAWNS:
        return (f"{said} is wrong: {where} the engine evaluates the position at {_fmt(white)}{cont} — "
                f"{_name(side)} stands worse there, not better; say what really happens in this line or leave it out")
    if mine > -WORSE_PAWNS:
        return None
    # The trap told backwards: the line relies on a mistake by the side it is said to favour.
    last = max((i for i in range(len(moves)) if (board.turn == side) == (i % 2 == 0)), default=None)
    if last is None:
        return None
    before = board.copy(stack=False)
    for mv in moves[:last]:
        before.push(mv)
    got_before = _eval(before, movetime_ms)
    if got_before is None:
        return None
    if got_before[1] and got_before[1][0] == before.san(moves[last]):
        # The engine's own choice there is no mistake: the «loss» is the noise of two short searches (review 30.10:
        # at 150 ms, 3...Nd4 4.Nxe5 Qg5 came out as Black's mistake, +0.7 → −0.9 for Black, with Qg5 the engine's move).
        return None
    mover_before = got_before[0] if side == chess.WHITE else -got_before[0]
    after_board = before.copy(stack=False)
    after_board.push(moves[last])
    if last == len(moves) - 1:
        mover_after = mine
    else:
        got_after = _eval(after_board, movetime_ms)
        if got_after is None:
            return None
        mover_after = got_after[0] if side == chess.WHITE else -got_after[0]
    loss = mover_before - mover_after
    if loss < MISTAKE_PAWNS:
        return None
    mistake = _numbered(before, [before.san(moves[last])])
    return (f"{said} is wrong: {mistake} is {_name(side)}'s mistake in this line (the engine: about {loss:.1f} pawns "
            f"given away), and {where} the position is {_fmt(white)}{cont} — {_name(not side)} stands better; "
            f"say what really happens in this line or leave it out")


def _verify_swing(claim: dict, movetime_ms: int, reveal: bool) -> Optional[str]:
    from src.hypothetical import _fmt, _numbered

    board, moves, side = claim["board"], claim["moves"], claim["side"]
    line, end = _line_text(board, moves)
    got_before, got_after = _eval(board, movetime_ms), _eval(end, movetime_ms)
    if got_before is None or got_after is None:
        return None
    if max(abs(got_before[0]), abs(got_after[0])) >= MATE_PAWNS - 0.5:
        return None
    sign = 1 if side == chess.WHITE else -1
    swing = (got_after[0] - got_before[0]) * sign
    said = claim["pawns"]
    if abs(said - swing) < max(SWING_ABS, SWING_REL * max(abs(said), abs(swing))):
        return None
    # The material the line and the engine's continuation after it change, for the side that moved first.
    b = end.copy(stack=False)
    for san in got_after[1]:
        try:
            b.push_san(san)
        except ValueError:
            break
    material = _material(b, side) - _material(board, side)
    named = claim.get("named")
    if named:
        # The trade the sentence names is the coach's own count (C8): the figure must be that count or the engine's
        # swing — not «between» them (pawn-b3-bare: «слона за пешку — почти на четыре пешки хуже», 2 vs 4 vs 6.5).
        count = -named if said < 0 else named
        named_why = None
        if abs(said - count) >= 1.0 and abs(said - material) >= 1.0:
            cont = f" (it goes on {_numbered(end, got_after[1][:4])})" if reveal and got_after[1] else ""
            named_why = (f"«{claim['words']}» is wrong: the trade the sentence names («{claim.get('named_words', '')}») "
                         f"is {named} pawn{'s' if named != 1 else ''} of material, and after {line} the engine evaluates "
                         f"the position at {_fmt(got_after[0])}{cont} against {_fmt(got_before[0])} before — about "
                         f"{abs(swing):.1f} pawns {'worse' if swing < 0 else 'better'} for {_name(side)}; give the "
                         f"trade's count or the engine's figure, not another")
        if claim.get("named_mode") != "shadow":
            return named_why
        if named_why:
            from src.answer_check import record_shadow

            record_shadow(None, "trade_swing_named", [named_why])
    if abs(said - material) < 1.0 or min(material, swing) <= said <= max(material, swing):
        # The coach counts the material the line loses («почти на четыре пешки» for a bishop, −3), or tells a figure
        # between that count and the engine's: not clearly wrong. (The count follows the engine's continuation, which
        # a short search under load may cut before or after a recapture: −2 or −3 for the same 6.b3? b5.)
        return None
    cont = f" (it goes on {_numbered(end, got_after[1][:4])})" if reveal and got_after[1] else ""
    return (f"«{claim['words']}» is wrong: after {line} the engine evaluates the position at {_fmt(got_after[0])}{cont} "
            f"against {_fmt(got_before[0])} before — about {abs(swing):.1f} pawns {'worse' if swing < 0 else 'better'} "
            f"for {_name(side)}, and in material {material:+d}; give the engine's figure or none")


# «решает ферзь» holds when the piece's best move leaves its side at least DECIDES_PAWNS up and no more than
# BEHIND_PAWNS below the engine's best (both capped at DECISIVE_PAWNS: a piece that wins a rook decides even where
# another move mates), or when the piece moves among its side's first PV_OWN_MOVES moves of the engine's winning
# line (it decides there after a check by another piece: «Nf6+, и решает ферзь»).
DECIDES_PAWNS = 1.5
BEHIND_PAWNS = 1.0
DECISIVE_PAWNS = 5.0
PV_OWN_MOVES = 3
_PIECE_EN = {chess.QUEEN: "queen", chess.ROOK: "rook", chess.KNIGHT: "knight", chess.BISHOP: "bishop"}


def _first_line(res: dict) -> Optional[dict]:
    return (res.get("lines") or [None])[0] if isinstance(res, dict) and "error" not in res else None


def _moves_in_pv(board: chess.Board, pv: str, squares: tuple, side: bool) -> bool:
    """Does the piece on one of *squares* move among *side*'s first PV_OWN_MOVES moves of *pv* (UCI)?"""
    b = board.copy(stack=False)
    tracked, own = set(squares), 0
    for uci in (pv or "").split():
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            return False
        if mv not in b.legal_moves:
            return False
        if b.turn == side:
            if mv.from_square in tracked:
                return True
            own += 1
            if own >= PV_OWN_MOVES:
                return False
        else:
            tracked.discard(mv.to_square)  # captured
        b.push(mv)
    return False


def _verify_piece(claim: dict, movetime_ms: int, reveal: bool) -> Optional[str]:
    from src import hypothetical
    from src.hypothetical import MIN_DEPTH, _fmt, _numbered, _white_pawns

    board, side, squares = claim["board"], claim["side"], tuple(claim["squares"])
    if board.turn != side:
        return None
    mine_moves = [m for m in board.legal_moves if m.from_square in squares]
    if not mine_moves:
        return None
    best = _first_line(hypothetical.analyze_timed(board.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH))
    best_white = _white_pawns(best, board.turn)
    if best is None or best_white is None or not best.get("pv"):
        return None
    best_move = chess.Move.from_uci(best["pv"].split()[0])
    if best_move in mine_moves:
        piece, piece_white = best, best_white
    else:
        piece = _first_line(hypothetical.analyze_timed(board.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH,
                                                       searchmoves=[m.uci() for m in mine_moves]))
        piece_white = _white_pawns(piece, board.turn)
        if piece is None or piece_white is None or not piece.get("pv"):
            return None
    piece_move = chess.Move.from_uci(piece["pv"].split()[0])
    if piece_move not in mine_moves:
        return None  # the restricted search did not keep to the piece: no verdict
    sign = 1 if side == chess.WHITE else -1
    b_mine, p_mine = best_white * sign, piece_white * sign
    capped_b, capped_p = min(b_mine, DECISIVE_PAWNS), min(p_mine, DECISIVE_PAWNS)
    if capped_p >= DECIDES_PAWNS and capped_b - capped_p <= BEHIND_PAWNS:
        return None
    if b_mine >= DECIDES_PAWNS and _moves_in_pv(board, best["pv"], squares, side):
        return None
    name = _PIECE_EN.get(claim["piece"], "piece")
    said = f"«{claim['words']}»"
    if b_mine < DECIDES_PAWNS:
        why = f"no move decides the game here: even the engine's best keeps it at {_fmt(best_white)}"
    else:
        why = f"the {name} does not decide it: another piece's move is clearly stronger"
    if not reveal:
        # A live game: no move named, the student is still to find it.
        return (f"{said} is wrong: the {name}'s best move here leaves the position at {_fmt(piece_white)}, and "
                f"{why.split(':')[0]}; do not promise that the {name} decides — say what the position really "
                f"offers without naming the engine's move")
    return (f"{said} is wrong: the {name}'s best move here is {_numbered(board, [board.san(piece_move)])} "
            f"({_fmt(piece_white)}), and the engine's move is {_numbered(board, [board.san(best_move)])} "
            f"({_fmt(best_white)}) — {why}; say what the engine says or leave the claim out")


_VERIFY = {"swing": _verify_swing, "piece_decides": _verify_piece}
_DETECTOR_OF = {"piece_decides": "piece_decides"}


def verify_claims(claims: list, movetime_ms: int = 300, reveal: bool = True) -> Optional[str]:
    """Why the first of *claims* (src/line_verdict.line_claims) the engine clearly contradicts is wrong, or None.
    *reveal* off (a live game) keeps the engine's continuation out. Never raises. A claim of a detector in shadow
    (plan 31.10 §1.3) is judged and logged, never returned."""
    for claim in claims or []:
        try:
            why = _VERIFY.get(claim.get("kind"), _verify_line)(claim, movetime_ms, reveal)
        except Exception:  # noqa: BLE001 — a failed check never blocks the answer
            logger.debug("line verdict failed", exc_info=True)
            why = None
        if why and claim.get("mode") == "shadow":
            # the turn's check (src/answer_check.shadow_into, set by the engine stage) gets the record: the
            # detector_shadow event, as for the sync detectors
            from src.answer_check import record_shadow

            record_shadow(None, _DETECTOR_OF.get(claim.get("kind"), claim.get("kind")), [why])
            continue
        if why:
            return why
    return None
