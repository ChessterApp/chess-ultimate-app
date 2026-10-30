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
    # One verdict per line end is enough: the first claims of the sentence.
    out, seen = [], set()
    for c in claims:
        key = (c["kind"], c["board"].fen(), tuple(c["moves"]), c["side"])
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


# ── the engine ──────────────────────────────────────────────────────────────


def _eval(board: chess.Board, movetime_ms: int) -> Optional[tuple]:
    """(White's score in pawns, the engine's line as SAN) for *board*, or None."""
    from src import hypothetical
    from src.hypothetical import MIN_DEPTH, _san_line, _white_pawns

    if board.is_checkmate():
        return (-MATE_PAWNS if board.turn == chess.WHITE else MATE_PAWNS), []
    if board.is_game_over():
        return 0.0, []
    res = hypothetical.analyze_timed(board.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH)  # the cache of the engine line
    line = (res.get("lines") or [None])[0] if "error" not in res else None
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
    if abs(said - material) < 1.0 or min(material, swing) <= said <= max(material, swing):
        # The coach counts the material the line loses («почти на четыре пешки» for a bishop, −3), or tells a figure
        # between that count and the engine's: not clearly wrong. (The count follows the engine's continuation, which
        # a short search under load may cut before or after a recapture: −2 or −3 for the same 6.b3? b5.)
        return None
    cont = f" (it goes on {_numbered(end, got_after[1][:4])})" if reveal and got_after[1] else ""
    return (f"«{claim['words']}» is wrong: after {line} the engine evaluates the position at {_fmt(got_after[0])}{cont} "
            f"against {_fmt(got_before[0])} before — about {abs(swing):.1f} pawns {'worse' if swing < 0 else 'better'} "
            f"for {_name(side)}, and in material {material:+d}; give the engine's figure or none")


def verify_claims(claims: list, movetime_ms: int = 300, reveal: bool = True) -> Optional[str]:
    """Why the first of *claims* (src/line_verdict.line_claims) the engine clearly contradicts is wrong, or None.
    *reveal* off (a live game) keeps the engine's continuation out. Never raises."""
    for claim in claims or []:
        try:
            why = (_verify_swing if claim.get("kind") == "swing" else _verify_line)(claim, movetime_ms, reveal)
        except Exception:  # noqa: BLE001 — a failed check never blocks the answer
            logger.debug("line verdict failed", exc_info=True)
            why = None
        if why:
            return why
    return None
