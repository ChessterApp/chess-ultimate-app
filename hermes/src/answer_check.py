"""Checks a coach answer, sentence by sentence, against the board.

The text coach runs without reasoning (fast), and without it the model writes
chess it has not checked. On production (2026-09-30) it said a knight «с f3
прыгает на d5» (a knight cannot), that a knight on c7 would attack the queen
d8 (it does not), recaptured «...Nxe5» with no black knight in reach, and gave
the moves of the quiet Italian as the Fried Liver. Each of these is decidable
from the board, so the server checks every finished sentence before it is
shown (see coach_chat), and a wrong one is not shown: the rest of the answer
is rewritten from there.

What is checked — only what can be decided without guessing, so that a right
sentence is never stopped:

  * a piece moving from a square to a square (Russian and English wording,
    «конь с f3 на d5», «Nf3-d5»): can that piece move that way at all;
  * a piece attacking squares («конь на c7 бьёт a8 и d8»): does it, by its
    move pattern (lines are not checked for blockers — hypotheticals are fine);
  * written moves (Nf6, 5...Na5, 3.Nxe5): legal in a position of this turn —
    the board, the opening line, a line written earlier in the answer — or at
    least reachable by such a piece of that side; plain squares are not moves;
  * an opening named next to moves from 1.: are they that opening's book line.

Negated claims («ладью он не достаёт») are skipped: they deny, they do not claim.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

import chess

logger = logging.getLogger(__name__)

SQ = r"[a-h][1-8]"
_SQ_RE = re.compile(rf"(?<![a-z0-9]){SQ}(?![0-9])")

# Russian piece nouns, every case, matched as whole words on lowercased text
# with ё → е. Stems alone would catch «конец», «королевский», «контроль».
_RU_PIECES = [
    (chess.KNIGHT, r"кон(?:ь|я|ю|е|и|ем|ей|ям|ями|ях)"),
    (chess.BISHOP, r"слон(?:а|у|ом|е|ы|ов|ам|ами|ах)?"),
    (chess.ROOK, r"лад(?:ья|ьи|ье|ью|ьей|ей|ьям|ьями|ьях)"),
    (chess.QUEEN, r"ферз(?:ь|я|ю|ем|е|и|ей)"),
    (chess.KING, r"корол(?:ь|я|ю|ем|е)"),
    (chess.PAWN, r"пеш(?:ка|ки|ке|ку|кой|ек|кам|ками|ках)"),
]
_EN_PIECES = [
    (chess.KNIGHT, r"knights?"), (chess.BISHOP, r"bishops?"), (chess.ROOK, r"rooks?"),
    (chess.QUEEN, r"queens?"), (chess.KING, r"kings?"), (chess.PAWN, r"pawns?"),
]
_W = r"(?<![а-яa-z])"
_E = r"(?![а-яa-z])"
_PIECE_WORD = re.compile(_W + "(?:" + "|".join(p for _, p in _RU_PIECES + _EN_PIECES) + ")" + _E)

_STOP = r"[^.!?;:\n—–()|]"  # a claim stays inside one clause (a table cell too)
# Between a piece and its verb a dash is Russian grammar («конём на c7 — вот он
# бил бы…»), not a new clause.
_STOP_MID = r"[^.!?;:,\n()|]"
# Inside a move claim a comma starts another clause («конь с b1 пока плох, но
# после перевода на g3…» is not a jump b1-g3).
_STOP_MOVE = r"[^.!?;:,\n—–()|]"

# «конь с f3 прыгает на d5», «слон уходит с c5 на a7», «knight from f3 to d5». The words between are one optional
# stretch of clause text (its characters include spaces): «(\s+X+?){0,2}?» meant the same strings but let a run of
# piece words split between the repeats in polynomially many ways — 5.5 s on «конь »×200 (review 30.10, wiring).
_MOVE_CLAIMS = []
for _ptype, _pat in _RU_PIECES:
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid1>(?:\s+{_STOP_MOVE}+?)??)\s+(?:с|со|из)\s+(?:пол[яе]\s+)?(?P<a>{SQ})"
        rf"(?P<mid2>(?:\s+{_STOP_MOVE}+?)??)\s+на\s+(?P<b>{SQ})(?![0-9])")))
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"\s+(?:с\s+)?(?P<a>{SQ})\s*[-–]\s*(?P<b>{SQ})(?![0-9])")))
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid1>(?:\s+{_STOP_MOVE}+?)??)\s+на\s+(?P<b>{SQ})"
        rf"(?P<mid2>(?:\s+{_STOP_MOVE}+?)??)\s+(?:с|со)\s+(?:пол[яе]\s+)?(?P<a>{SQ})(?![0-9])")))
for _ptype, _pat in _EN_PIECES:
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid1>(?:\s+{_STOP_MOVE}+?)??)\s+(?:from|on)\s+(?P<a>{SQ})"
        rf"(?P<mid2>(?:\s+{_STOP_MOVE}+?)??)\s+(?:to|onto)\s+(?P<b>{SQ})(?![0-9])")))

# «конь на c7 бьёт a8 и d8», «слон c4 держит f7», «the knight on f7 attacks d8 and h8».
# The attacker is the subject: nominative («конь») or instrumental («конём на
# c7 — вот он бил бы…»); «связывает пешку f7 и смотрит на h7» is the queen's claim.
_RU_SUBJECTS = [
    (chess.KNIGHT, r"конь|кони|кон[её]м"),
    (chess.BISHOP, r"слон|слоны|слоном"),
    (chess.ROOK, r"ладья|ладьи|ладь[её]й"),
    (chess.QUEEN, r"ферзь|ферз[её]м"),
    (chess.KING, r"король|корол[её]м"),
    (chess.PAWN, r"пешка|пешкой"),
]
# A hypothetical is a claim too: «ладья с g1 будет бить ферзя на h4», "your
# rook sits on g1 hitting the queen on h4" (production, 2026-10-01 — a rook
# does not hit h4 from g1). Future and participle forms, and the piece's
# square after a placement verb («встаёт на g1», "lands on g1"), count.
_RU_VERBS = (r"(?<![а-я])(?:бь[её]т|бьют|бил[аи]?\s+бы|атакует|атакуют|атаковал\w*|нападает|нападают|напал[аи]?|"
             r"угрожает|угрожают|держит|держат|смотрит|смотрят|давит|давят|целится|целятся|"
             r"бер[её]т|забирает|возьм[её]т|забер[её]т|съест|съедает|"
             r"защищает|защищают|контролирует|контролируют|вилк\w*|"
             r"буд(?:ет|ут)\s+(?:бить|атаковать|нападать|угрожать|держать|смотреть|давить|защищать|контролировать)|"
             r"удар(?:ит|ят)|напад[её]т|нападут|простреливает|простреливают|обстреливает|обстреливают|"
             r"бьющ\w+|нападающ\w+|атакующ\w+|нацел\w+|с\s+(?:нападением|темпом|атакой|ударом)\s+на)(?![а-я])")
_EN_VERBS = (r"(?<![a-z])(?:attacks|attack|hits|hit|forks|targets|eyes|threatens|pins|covers|guards|watches|"
             r"attacking|hitting|forking|targeting|eyeing|threatening|pinning|covering|guarding|watching|"
             r"defending|protecting|controlling|aiming\s+at|pointing\s+at|looking\s+at|bearing\s+down\s+on|"
             r"x-?raying|(?:would|will|can|could)\s+(?:attack|hit|fork|target|eye|threaten|pin|cover|guard)|"
             r"is\s+attacking|is\s+hitting|defends|protects|controls)(?![a-z])")
# «её держит только конь c6»: the subject comes after the verb — not this
# piece's claim. Russian only: its nominative tells the subject from the
# object; in English "attacks the queen on d8" names the target.
_INVERTED = re.compile(r"^\s*(?:[^\s,]+\s+){0,2}?(?:конь|слон|ладья|ферзь|король|пешка)(?![а-яa-z])")
# «ладья встаёт на g1 …», "the rook lands on g1 …": the piece's square after a placement verb.
_RU_PLACED = (r"(?:(?:вста[её]т|встанет|встанут|ид[её]т|пойд[её]т|переходит|перейд[её]т|прыгает|прыгнет|"
              r"попада[её]т|попад[её]т|окажется|оказывается|становится|стоит|стоящ\w*|будет|уже|теперь|сейчас|"
              # the game told in the past: «конь вышел на c3 и напал на пешку e5» (prod text game 28.10)
              r"вышел|вышла|встал|встала|пош[её]л|пошла|переш[её]л|перешла|прыгнул|прыгнула|отош[её]л|отошла|"
              r"двинулся|двинулась|оказался|оказалась)\s+)?")
_EN_PLACED = (r"(?:(?:sits|stands|lands|goes|comes|moves|arrives|jumps|hops|drops|swings|is|gets|"
              r"sitting|standing|landing|ends\s+up|will\s+be|would\s+be)\s+)?")
# «на g1, бьющая h4», "on g1, which attacks h4": the comma of a participle or
# relative clause stays inside the claim; any other comma ends it.
_COMMA_CLAUSE = r"(?:,(?=\s*(?:котор\w+|что|which|that|who|[а-яa-z]+(?:ющ|ящ|ащ|ущ|ing)\w*)(?![а-яa-z])))?"
_ATTACK_CLAIMS = []
for _ptype, _pat in _RU_SUBJECTS:
    _ATTACK_CLAIMS.append((_ptype, re.compile(
        # (Not «с d5»: «конь с g8 сразу бьёт в e4» is the knight that leaves g8.)
        _W + "(?:" + _pat + ")" + _E + rf"\s+{_RU_PLACED}(?:на\s+)?(?P<a>{SQ})(?![0-9]){_COMMA_CLAUSE}(?P<mid>{_STOP_MID}{{0,40}}?)"
        # «бьёт сразу две фигуры: короля на e8 и ладью на a8» — a colon after a count opens the list of targets
        rf"(?P<verb>{_RU_VERBS})(?P<targets>(?:{_STOP}{{0,30}}?(?:сразу|обе|оба|две|два|двух|три|фигур\w*|цел\w*){_STOP}{{0,20}}:\s*)?{_STOP}{{0,90}})")))
for _ptype, _pat in _EN_PIECES:
    _ATTACK_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"\s+{_EN_PLACED}(?:(?:on|to|at|onto|from)\s+)?(?P<a>{SQ})(?![0-9]){_COMMA_CLAUSE}(?P<mid>{_STOP_MID}{{0,40}}?)"
        rf"(?P<verb>{_EN_VERBS})(?P<targets>{_STOP}{{0,90}})")))
    # "the b3 queen guards it", "your c5-knight hits e4"
    _ATTACK_CLAIMS.append((_ptype, re.compile(
        rf"(?<![a-z0-9])(?P<a>{SQ})[- ](?:" + _pat + ")" + _E + rf"{_COMMA_CLAUSE}(?P<mid>{_STOP_MID}{{0,40}}?)"
        rf"(?P<verb>{_EN_VERBS})(?P<targets>{_STOP}{{0,90}})")))
# (C) «он сам нападает: бьёт ладью d5», "it attacks d5": the subject is the piece the sentence is about
_NAMED_PIECE = re.compile(_W + "(?P<piece>" + "|".join(p for _, p in _RU_PIECES + _EN_PIECES) + ")" + _E
                          + rf"\s+(?:на\s+|on\s+|с\s+|from\s+)?(?P<a>{SQ})(?![0-9])", re.IGNORECASE)
_PRONOUN_SUBJECT = re.compile(
    _W + r"(?P<pron>он|она|it|he|she)\s+(?:сам\w*\s+|же\s+|also\s+|now\s+|still\s+|itself\s+)?(?:нападает\s*:\s*|атакует\s*:\s*)?"
    rf"(?P<verb>{_RU_VERBS}|{_EN_VERBS})(?P<targets>{_STOP}{{0,90}})", re.IGNORECASE)
# «Rg1 нападает на ферзя h4», "Rg1 attacks the queen on h4": a written move as
# the subject — the piece on its destination square.
_SAN_SUBJECT = re.compile(
    rf"(?<![A-Za-z0-9])(?P<piece>[KQRBN])[a-h]?[1-8]?x?(?P<a>{SQ})[+#]?(?![0-9A-Za-z])(?P<mid>{_STOP_MID}{{0,12}}?)"
    rf"(?P<verb>{_RU_VERBS}|{_EN_VERBS})(?P<targets>{_STOP}{{0,90}})")
# «Если сыграть Rg1, ладья нападает на ферзя h4», "after Rg1 the rook attacks
# the queen on h4": a piece named without a square after a written move of that
# piece is the piece on the move's destination square (stand, 2026-10-04: the
# direct «ладья на g1 нападает…» was caught, this phrasing was not).
_BARE_SUBJECT = []
for _ptype, _pat in _RU_SUBJECTS:
    _BARE_SUBJECT.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid>{_STOP_MID}{{0,24}}?)\s(?P<verb>{_RU_VERBS})(?P<targets>{_STOP}{{0,90}})",
        re.IGNORECASE)))
for _ptype, _pat in _EN_PIECES:
    _BARE_SUBJECT.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid>{_STOP_MID}{{0,24}}?)\s(?P<verb>{_EN_VERBS})(?P<targets>{_STOP}{{0,90}})",
        re.IGNORECASE)))
# Where the targets of a claim end: another clause starts, or another piece
# becomes the subject («конь на f6 смотрит на e4, конь на c6 — на d4»).
_TARGETS_END = re.compile(
    r",?\s+(?:но|а|поэтому|чтобы|потому|если|когда|пока|затем|потом|после|хотя|but|so|because|if|when|while|"
    r"after|then|which|that|who|whose)\s|\s+котор\w*\s|,\s+and\s"
    r"|,\s*(?:(?:а|и|and)\s+)?(?:конь|слон|ладья|ферзь|король|пешка|the\s+(?:knight|bishop|rook|queen|king|pawn))"
    r"(?![а-яa-z])"
    r"|,\s*[KQRBN]?[a-h]?x?[a-h][1-8]\s+(?!(?:и|and|или|or)\s)[а-яa-z]", re.IGNORECASE)
# A denial right before a claim («не бьёт», "doesn't attack"): one rule for the checker (src/claim_scope.py).
_NEGATION = re.compile(r"(?:^|[\s*_«\"(])(?:не|ни|нет|никак|нельзя|never|not|n't|cannot|can't)[*_]*\s*(?:\w+\s+)?$"
                       r"|[a-z]+n'?t\s*$", re.IGNORECASE)  # "doesn't attack", "won't hit", «не просто бьёт»
# «Лe4 сыграть нельзя», «ладья так не ходит»: the sentence denies a move — its
# moves are the student's idea being refuted, not the coach's claims.
_DENIES = re.compile(
    r"нельзя|невозможн|не\s+може|не\s+могу|не\s+ход[иья]|не\s+получит|не\s+проходит|не\s+проход[яи]т|не\s+работает|"
    r"не\s+годится|нелегальн|не\s+по\s+правилам|хода\s+нет|нет\s+хода|нет\s+такого\s+хода|no\s+such\s+move|not\s+a\s+(?:legal\s+)?move|"
    r"illegal|not\s+legal|can'?t|cannot|impossible|isn'?t\s+possible|doesn'?t\s+work|does\s+not\s+work", re.IGNORECASE)
# «Ke3–e5», «Nb1–d2–f1–g3», «...d7-d5»: a move written from-to (a chain of hops).
_LONG = re.compile(
    r"(?<![A-Za-z0-9])(?:(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?|(?P<bdots>\.\.\.|…))?"
    r"(?P<piece>[KQRBN])?(?P<chain>[a-h][1-8](?:[-–][a-h][1-8])+)(?![0-9])")

# Written moves. Russian piece letters (Кf6, Сc4, Крg1) are read as SAN too.
_RU_SAN = re.compile(r"(?<![А-Яа-яA-Za-z])(Кр|К|С|Л|Ф)(?=x?[a-h][1-8])")
_RU_TO_SAN = {"Кр": "K", "К": "N", "С": "B", "Л": "R", "Ф": "Q"}
_FIGURINES = str.maketrans({"♔": "K", "♚": "K", "♕": "Q", "♛": "Q", "♖": "R", "♜": "R",
                            "♗": "B", "♝": "B", "♘": "N", "♞": "N"})


# Russian notation typed in Cyrillic throughout: «Се3», «Кс3», «Фа4», «Кре1», «С:е3» (the client's
# question «Что если я пойду Се3?» named no move — production 2026-10-07). The file letters а, с, е
# after a piece letter become a, c, e and «:» a capture; the length of the text is kept.
# Every Cyrillic file the student or the coach types (а б в с ц д е э ф г х), «х» as a capture too:
# the coach's «Сб5», «Кхе5» went unchecked (inventory 2026-10-15). The table is src/move_text.FILES.
_CYR_PIECE_FILE = re.compile(r"(?<![А-Яа-яЁёA-Za-z])(Кр|[КСЛФKQRBN])([x:×х]?)([абвсцдеэфгх])(?=[1-8](?![0-9]))")
_CYR_FILE = {k: v for k, v in __import__("src.move_text", fromlist=["FILES"]).FILES.items() if not k.isascii()}


def _cyrillic_files(text: str) -> str:
    text = _CYR_PIECE_FILE.sub(lambda m: m.group(1) + ("x" if m.group(2) else "") + _CYR_FILE[m.group(3)], text)
    return re.sub(r"(?<![А-Яа-яЁёA-Za-z])(Кр|[КСЛФKQRBN]):(?=[a-h][1-8](?![0-9]))", lambda m: m.group(1) + "x", text)


def _to_san(text: str) -> tuple[str, set]:
    """*text* with figurines and Russian piece letters as SAN letters, and the
    positions (in the result) where a Cyrillic «К» became N — models write «Кh1»
    for the king too, so there a king move is accepted as well."""
    text = _cyrillic_files((text or "").translate(_FIGURINES))
    out, cyr_k, last = [], set(), 0
    for m in _RU_SAN.finditer(text):
        out.append(text[last:m.start()])
        if m.group(1) == "К":
            cyr_k.add(sum(len(x) for x in out))
        out.append(_RU_TO_SAN[m.group(1)])
        last = m.end()
    out.append(text[last:])
    return "".join(out), cyr_k
_MOVE = re.compile(
    r"(?<![A-Za-z0-9.])(?:(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?|(?P<bdots>\.\.\.|…))?"
    r"(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?"
    r"|O-O-O|O-O)(?P<check>[+#]?)(?![A-Za-z0-9])")
# «Qxg7 — мат», "Qxg7 is checkmate" (not «мат в 3 хода», "mate in 3"): read as Qxg7#.
_MATE_WORD = re.compile(
    r"(?<![A-Za-z0-9])(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)"
    r"(?:\+|#)?(?P<rest>\s*(?:[—–-]|:|,)?\s*(?:это\s+|и\s+это\s+|is\s+|that'?s\s+|it'?s\s+|будет\s+|will\s+be\s+|"
    r"would\s+be\s+)?)(?:мат|checkmate|mate)(?!\s+(?:в|in|через|за)\s)(?![а-яa-z])", re.IGNORECASE)
_NAMES = {chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook",
          chess.QUEEN: "queen", chess.KING: "king", chess.PAWN: "pawn"}


def _geometry_move(ptype: int, a: int, b: int) -> bool:
    """Can a piece of *ptype* move a → b on an empty board (either colour)?"""
    if a == b:
        return False
    dx = abs(chess.square_file(a) - chess.square_file(b))
    dy = abs(chess.square_rank(a) - chess.square_rank(b))
    if ptype == chess.KNIGHT:
        return {dx, dy} == {1, 2}
    if ptype == chess.BISHOP:
        return dx == dy
    if ptype == chess.ROOK:
        return dx == 0 or dy == 0
    if ptype == chess.QUEEN:
        return dx == dy or dx == 0 or dy == 0
    if ptype == chess.KING:
        castling = chess.square_name(a) in ("e1", "e8") and dy == 0 and dx == 2
        return max(dx, dy) == 1 or castling
    if ptype == chess.PAWN:
        return (dx == 0 and 1 <= dy <= 2) or (dx == 1 and dy == 1)
    return False


def _geometry_attack(ptype: int, a: int, b: int) -> bool:
    """Does a piece of *ptype* on a attack b by its pattern (blockers ignored)?"""
    if ptype == chess.PAWN:
        dx = abs(chess.square_file(a) - chess.square_file(b))
        dy = abs(chess.square_rank(a) - chess.square_rank(b))
        return dx == 1 and dy == 1
    if ptype == chess.KING:
        return a != b and max(abs(chess.square_file(a) - chess.square_file(b)),
                              abs(chess.square_rank(a) - chess.square_rank(b))) == 1
    return _geometry_move(ptype, a, b)


def _clause_targets(text: str) -> list[str]:
    cut = _TARGETS_END.search(text)
    if cut:
        text = text[: cut.start()]
    return _SQ_RE.findall(text)


_FEN_IN_TEXT = re.compile(r"[rnbqkpRNBQKP1-8]{1,8}(?:/[rnbqkpRNBQKP1-8]{1,8}){7} [wb] [KQkq-]{1,4} [a-h1-8-]{1,2}(?: \d+ \d+)?")


@dataclass
class CheckContext:
    """The positions of this turn a written move may belong to, and the moves
    the student wrote (the coach may repeat those to refute them)."""

    boards: list = field(default_factory=list)
    quoted: set = field(default_factory=set)
    # Keys of the positions given to the turn (the board, lines, tool results),
    # as opposed to those derived by following moves written in the answer.
    given: set = field(default_factory=set)
    # The position in front of the student now (the first FEN given): claims
    # about material, hanging pieces and whose piece stands where are about it.
    current: Optional[chess.Board] = None
    # The student's colour when known (a game against the coach): «твой конь».
    student_color: Optional[bool] = None
    # The language the answer must be in ('ru', 'kk', 'kz', 'en'), when known.
    language: Optional[str] = None
    # The engine's evaluation of the position on the screen, in pawns from
    # White's side (±100 a forced mate), when the turn has one: «у белых лучше»
    # against −2.0 is not shown (2026-10-05).
    engine_eval: Optional[float] = None
    # The endgame tablebase's verdict for that position ('draw', 'White wins',
    # 'Black wins'), and the engine's forced mate (moves, + for the side to
    # move) — src/answer_check_rules.py judges «это выигрыш», «мат в два» by them.
    tablebase: Optional[str] = None
    engine_mate: Optional[int] = None
    # A game against the coach on the board: the moves the engine made in it (src/server.py). The coach
    # plays only through the engine — «я ответил Кc6» names one of them or is not shown (2026-10-12).
    game_engine_moves: Optional[list] = None
    # …and the game's whole record: the turn's own moves written in an answer («7.Bb5, слон напал на …») tell what is on
    # the board now, not a line to imagine — the claims after them are checked on the board (prod text game 28.10).
    game_moves: Optional[list] = None
    # The student's message: «можно мне рокироваться?» makes «нет, нельзя» a claim about this board.
    question: str = ""
    question_raw: str = ""
    # The square the previous sentence was about («a4 isn't hanging. It's
    # attacked by…»): what "it" means when a sentence opens with it. The
    # object the sentence's claims were about, else its first square.
    topic: Optional[str] = None
    _object: Optional[str] = None
    # The piece the sentence is about (type, square): «конь на c5 не связан — он сам бьёт d5».
    _subject: Optional[tuple] = None
    # The position after the last move the answer wrote (this sentence or the one before), and that
    # move: «Первый ход — Rxh6+. Король обязан отойти…» is about the board after Rxh6+ (2026-10-08).
    scene: Optional[chess.Board] = None
    scene_san: str = ""
    scene_age: int = 0
    # The scene before this sentence's moves, and this sentence's moves in order with the board after
    # each: a claim before «Kxh7» in «…поэтому он обязан её взять: Kxh7» is about the board before it.
    scene_before: Optional[tuple] = None
    scene_trail: list = field(default_factory=list)
    # The line the answer wrote, walked strictly from a given position (moves in words too) — what the next moves
    # and «пешка на a7, ты на d6» are judged in (src/answer_check_scene.py; prod 29.10).
    line_scene: Optional[dict] = None
    passed_keys: set = field(default_factory=set)
    # Positions only named in a tool's text (a lesson's diagram, a list of tasks): a move legal only there is not
    # an answer about the student's board (production 08.10: «Первый ход чёрных — Qxg2+» passed on a diagram).
    text_keys: set = field(default_factory=set)
    shown_keys: set = field(default_factory=set)
    # Positions given as a position (a FEN: the board, a tool's board, the student's idea), the positions a line
    # passes through, and the ends of the lines (what a loaded game or line shows): in a game on the board, the
    # game's earlier positions are its history — «теперь у чёрных на пешку больше» is about the board now, not
    # about a move ago (prod game 29.10: Black was two pawns up after 6...Nxe4, one after 5...exd4).
    state_keys: set = field(default_factory=set)
    line_keys: set = field(default_factory=set)
    line_ends: set = field(default_factory=set)
    # The captures made along a line, by the key of its end: (colour, square). «Ты взял пешку d5, чёрные забрали
    # обратно» told about 4.cxd5 is history, not a capture still to make (review 30.10).
    line_captures: dict = field(default_factory=dict)
    # The verified solution of the puzzle on the board, in SAN from its start, when a puzzle is there: a sentence
    # that gives «the solution» or «the mate» with another move is not shown (prod 23.10: «Qf3+ Kg1 и Qh1#» for
    # a puzzle solved by Nh3#).
    puzzle_solution: Optional[list] = None
    # The outcomes a sentence promises at the end of a line it writes («…Qxd5+, и ты забираешь ферзя»), under the
    # sentence, for the engine stage (src/line_verdict.py; prod 29.10), and the end of the last line written.
    line_claims: dict = field(default_factory=dict)
    _line_end: Optional[tuple] = None
    _line_advice: bool = False  # …and whether that sentence recommended it («Лучший ход здесь 4.Nxd4.»)
    # The moves of the lines and games given to the turn, as (the position's key, the move's UCI): «Здесь ты играешь
    # Qxd5+» in a review tells the game's own next move, not advice (review 30.10).
    line_next: set = field(default_factory=set)
    # Outcome claims at the end of a line written in a sentence («после Kd5 a6 Kc6 — ничья») whose position the
    # tablebase has not been asked about yet: the engine stage asks it (src/endgame_claims.pop_pending, 30.10).
    outcome_pending: dict = field(default_factory=dict)
    # ECO codes a tool's result names (identify_opening, get_opening_stats): the coach repeating one says what the
    # tool said (src/answer_check_openings.py, prod check 29.10).
    text_codes: set = field(default_factory=set)
    # Every line and game the turn has, as (its first position, its moves in SAN): what was played on the way to
    # the board — «здесь белые пошли 6.Сс4» on the board after 5...a6, «после размена на e4» after 2.exd5 Qxd5
    # (prod 29.10) are judged against it (src/answer_check_facts.py).
    line_records: list = field(default_factory=list)
    # A tool put another position on the board during this answer (src/server.py): the board the answer
    # talks about may no longer be the one the turn began on.
    board_moved: bool = False
    # The positions of the session's other boards (an earlier game, an earlier lesson's diagram), set by the server
    # when the turn begins; a tool that puts one up again this turn takes it back out. In a game on the board advice
    # is about the game, not about them (replay 30.10: an earlier Sicilian made «увести ферзя с d8 на c7 или b6»
    # «legal somewhere» in st2).
    other_board_keys: set = field(default_factory=set)
    # Claims that a reply is forced, by sentence, for the engine stage to judge (src/answer_check_rules.
    # forced_reply_claim → src/hypothetical.verify_forced_reply; prod 29.10, «обязаны ответить dxe5»).
    forced_claims: dict = field(default_factory=dict)
    # The end of the line the sentences before wrote, the student's own quoted moves included («после Nxe5 Bxd1
    # белые дают шах»; the scene skips quoted moves): (board, its last move, sentences ago). A forced reply claimed
    # in the next sentence may be about it (src/answer_check_rules._readings; review 30.10).
    forced_line: Optional[tuple] = None
    # The relation checker (src/answer_check_relations.py, plan 30.10): what a sentence leaves for the next one to
    # refer to (antecedents, the end of a told line) — immutable values only, so check_sentence's shallow copy is a
    # full snapshot; the claims recorded in shadow mode as (sentence, issues), never shown; its counters (calls,
    # claims, flags, errors, ms); and the lines that solve the task on the board (SAN lists from the current
    # position: the puzzle's solution, the engine's line for «какой здесь первый ход») — the boards after their
    # first moves are what an answer about an unnamed solution move describes.
    relation_state: dict = field(default_factory=dict)
    relation_shadow: list = field(default_factory=list)
    relation_stats: dict = field(default_factory=dict)
    solution_lines: list = field(default_factory=list)
    # Where the answer is shown: 'text' (the coach), 'voice', 'lesson' (the /learn tutor — the relation checker does
    # not run there, Асан 19.10: the lesson tutor is the team's), 'game' (a move comment — recorded, never cut, until
    # its flags are reviewed). src/answer_check_relations.mode reads it.
    relation_surface: str = "text"
    MAX_BOARDS = 400

    @classmethod
    def from_fens(cls, fens: Iterable[Optional[str]] = (), lines: Iterable[str] = (),
                  question: str = "", student_color: Optional[bool] = None) -> "CheckContext":
        ctx = cls()
        ctx.student_color = student_color
        ctx.question = (question or "").replace("ё", "е").lower()
        ctx.question_raw = question or ""
        ctx.add(chess.STARTING_FEN)
        for fen in fens:
            ctx.add(fen)
            if ctx.current is None and fen:
                try:
                    key = cls._key(chess.Board(fen))
                    ctx.current = next((b for b in ctx.boards if cls._key(b) == key), None)
                except ValueError:
                    pass
        for pgn in lines:
            ctx.add_line(pgn)
        converted, _ = _to_san(question or "")
        ctx.quoted = {m["san"] for m in _MOVE.finditer(converted)}
        start = re.search(r"(?<![0-9])1\s?\.\s?(?=[KQRBNa-hO])", converted)
        if start:
            ctx.add_line(converted[start.start():])  # «Как называется дебют 1.e4 e5 …?»
        return ctx

    def add_text(self, text: str) -> None:
        """Positions a tool result carries (a topic example, a puzzle, a game)."""
        for fen in _FEN_IN_TEXT.findall(text or ""):
            self.add(fen, shown=False)
            try:
                self.text_keys.add(self._key(chess.Board(fen)))  # named in a tool's text, maybe never on the board
            except ValueError:
                pass
        for pgn in re.findall(r'"pgn"\s*:\s*"([^"]{8,})"', text or ""):
            self.add_line(pgn.replace("\\n", " "))
        self.text_codes.update(re.findall(r"(?<![A-Za-z0-9])[A-E]\d\d(?![0-9A-Za-z])", text or ""))

    @staticmethod
    def _key(board: chess.Board) -> str:
        return board.board_fen() + (" w" if board.turn else " b")

    def is_given(self, board: chess.Board) -> bool:
        return self._key(board) in self.given

    def add(self, fen: Optional[str], derived: bool = False, shown: bool = True, line: bool = False) -> None:
        if not fen:
            return
        try:
            board = chess.Board(fen)
        except ValueError:
            return
        key = self._key(board)
        if not derived:
            self.given.add(key)
            (self.line_keys if line else self.state_keys).add(key)
            self.other_board_keys.discard(key)
        if shown:
            self.shown_keys.add(key)
        if len(self.boards) >= self.MAX_BOARDS:
            return
        if all(self._key(b) != key for b in self.boards):
            self.boards.append(board)

    def add_line(self, pgn: str) -> None:
        self.game_lines = getattr(self, "game_lines", 0) + 1  # a game or a line the turn has (none: its history is unknown)
        from src.openings_book import _split_moves

        board = chess.Board()
        header = re.search(r'\[FEN "([^"]+)"\]', pgn or "")
        if header:
            try:
                board = chess.Board(header.group(1))
            except ValueError:
                return
        pgn = re.sub(r"\[[^\]]*\]", " ", pgn or "")
        pgn = re.sub(r"\{[^}]*\}", " ", pgn)
        self.add(board.fen(), line=True)
        captures = set()
        record: list = []
        self.line_records.append((board.copy(stack=False), record))
        for san in _split_moves(pgn):
            # A position on the way through a game or a line, not its end: a line told without move numbers is not
            # started from there (src/answer_check_scene.py).
            self.passed_keys.add(self._key(board))
            try:
                move = board.parse_san(san)
            except ValueError:
                break
            self.line_next.add((self._key(board), move.uci()))
            if board.is_capture(move):
                captures.add((board.turn, move.to_square))
            board.push(move)
            record.append(san)
            self.add(board.fen(), line=True)
        self.line_ends.add(self._key(board))
        self.line_captures.setdefault(self._key(board), set()).update(captures)


_GROUP = re.compile(r"(?:пешки|пешек|пешкам|пешками|пешках|кони|коней|конями|слоны|слонов|слонами|"
                    r"ладьи|ладей|ладьями|ферзи|ферзей|pawns|knights|bishops|rooks)(?![а-яa-z])")


def _move_issues(text: str) -> list[str]:
    if _DENIES.search(text):
        return []
    issues = []
    for ptype, rx in _MOVE_CLAIMS:
        for m in rx.finditer(text):
            if _GROUP.match(m.group(0)):
                continue  # «пешки f7–g7–h7» names a group of pawns
            if ptype == chess.PAWN and m["a"][1] == m["b"][1]:
                continue  # pawns never move sideways: «пешкой e5–b5» is a chain
            between = (m.groupdict().get("mid1") or "") + (m.groupdict().get("mid2") or "")
            if _PIECE_WORD.search(between) or _SQ_RE.search(between):
                continue  # another piece or square in between: not one claim
            a, b = chess.parse_square(m["a"]), chess.parse_square(m["b"])
            if not _geometry_move(ptype, a, b):
                issues.append(f"a {_NAMES[ptype]} cannot move from {m['a']} to {m['b']}")
    return issues


# A sentence about what could be, not what is: a line of play, a condition, a future form, or a move written
# before the claim. The word list is the checker's one (src/claim_scope.py).
from src.claim_scope import CONDITIONAL as _HYPO  # noqa: E402


def _just_played(ctx: Optional["CheckContext"]) -> Optional[set]:
    """The turn's own moves of a game on the board — the student's last and the engine's reply."""
    moves = getattr(ctx, "game_moves", None) if ctx is not None else None
    return {m.rstrip("+#") for m in moves[-2:]} if moves else None


def _is_hypothetical(text: str, original: str, upto: int, whole: bool = False, played: Optional[set] = None) -> bool:
    """A marker or a written move BEFORE the claim; what follows it («у чёрных
    лишняя пешка, и после Rg1 Nxa4…») does not excuse the claim itself — a
    claim about the position after those moves holds on the derived boards.
    *whole*: the whole sentence counts («твой конь на c5 — если бы он туда
    попал — доминировал бы»), for claims about whose piece stands where."""
    if _HYPO.search(text if whole else text[:upto]):
        return True
    converted, _ = _to_san(original[:upto])
    return any(m["san"] for m in _MOVE.finditer(converted)
               if (m["num"] or m["bdots"] or m["san"][0] in "KQRBN") and m["san"].rstrip("+#") not in (played or ()))


# Verbs that say a piece reaches a square now — blockers count; «смотрит»,
# "eyes", "x-rays" look through pieces and are not checked for them.
_HARD_VERB = re.compile(r"бь[её]т|бьют|атаку|напада|напал|угрожа|держ|защища|контролир|вилк|"
                        r"attack|hit|fork|target|threaten|defend|protect|control|cover|guard|pin", re.IGNORECASE)
from src.claim_scope import FUTURE_VERB as _FUTURE_VERB  # noqa: E402
# An attack on the enemy (not «держит», «контролирует»: one's own piece may be held, a square controlled).
_ENEMY_VERB = re.compile(r"бь[её]т|бьют|атаку|напада|напал|угрожа|attack|hits|threaten|fork", re.IGNORECASE)
_TARGET_PIECE_WORD = (r"(?:пешк[уиа]|кон[яь]|слон[аы]?|ладь[юя]|ферз[яь]|корол[яь]|pawn|knight|bishop|rook|queen|king)")


class _WithSquare:
    """A claim match whose subject square comes from elsewhere (a written move)."""

    def __init__(self, m, a: str):
        self._m, self._a = m, a

    def __getitem__(self, key):
        return self._a if key == "a" else self._m[key]

    def start(self, group=None):
        return self._m.start(group) if group else self._m.start()

    def groupdict(self):
        return {**self._m.groupdict(), "a": self._a}


def _subject_board(ctx: "CheckContext", ptype: int, a: int, derived_ok: bool = False) -> Optional[chess.Board]:
    """The position the claim is about: the board on the screen when the piece
    stands there; with *derived_ok* (the subject is a written move) also the
    position that move leads to."""
    if ctx.current is not None and (pc := ctx.current.piece_at(a)) is not None and pc.piece_type == ptype:
        return ctx.current
    if not derived_ok:
        return None
    return next((b for b in ctx.boards if not ctx.is_given(b)
                 and (pc := b.piece_at(a)) is not None and pc.piece_type == ptype), None)


# «нападает на ферзя», "attacks the queen", «бьёт коня»: the object right after
# the verb, named by kind in the object case — not «бьют ферзём» (the
# instrument), not «держит удар королём», not «всю диагональ до короля».
_TARGET_PIECE = re.compile(
    r"^\s*(?:(?:на|по|за|the|your|my|their|his|her|an?|тво\w+|ваш\w+|ч[её]рн\w+|бел\w+|black|white|enemy|"
    r"вражеск\w+|неприятельск\w+)\s+){0,3}(?P<p>ферзя|коня|слона|ладью|короля|пешку|knight|bishop|rook|queen|king|pawn)(?![а-яa-z])",
    re.IGNORECASE)


def _typed_targets(targets: str, board: chess.Board, color: chess.Color, defends: bool = False) -> list[str]:
    """The square of the one enemy piece of the kind the claim names as its
    object — one's own for a defence («король e6 держит коня»: the black knight,
    not White's b1 one, 2026-10-08); nothing when there are several, none, or the
    object is not a piece."""
    m = _TARGET_PIECE.match(targets.replace("ё", "е"))
    if not m:
        return []
    ptype = _piece_type(m["p"].lower())
    if ptype is None:
        return []
    squares = list(board.pieces(ptype, color if defends else not color))
    return [chess.square_name(squares[0])] if len(squares) == 1 else []


def _ep_victim(board: chess.Board, a: int) -> Optional[int]:
    """The pawn the pawn on *a* takes en passant now, or None."""
    if board.ep_square is None or board.piece_type_at(a) != chess.PAWN:
        return None
    if any(board.is_en_passant(mv) and mv.from_square == a for mv in board.legal_moves):
        return board.ep_square + (-8 if board.turn == chess.WHITE else 8)
    return None


def _own_targets(ptype: int, a: int, targets: list, m, boards: list) -> Optional[str]:
    """«слон вышел на b5 и напал на твою пешку c6» — c6 held the bishop's OWN pawn (prod text game 28.10): an attack
    on a piece named as a piece («пешку c6», not «поле c6») that is of the attacker's own side in every position."""
    if not targets or not boards or not _ENEMY_VERB.search(m["verb"]) or _FUTURE_VERB.search(m["verb"]):
        return None
    own = []
    for t in targets:
        named = re.search("(?P<w>" + _TARGET_PIECE_WORD + rf")\s+(?:на\s+)?{t}(?![0-9])", m["targets"], re.IGNORECASE)
        kind = _piece_type(named["w"].lower()) if named else None
        # the piece named must be the one standing there: «твоего слона g5» over a pawn on g5 is about another
        # position (after 8.Bxg5) — not this board's claim
        if kind is not None and all((tp := b.piece_at(chess.parse_square(t))) is not None and tp.piece_type == kind
                                    and (me := b.piece_at(a)) is not None and tp.color == me.color for b in boards):
            own.append(t)
    if own:
        return f"the {_NAMES[ptype]} on {chess.square_name(a)} does not attack {', '.join(own)}: its own side's piece stands there"
    return None


def _attack_issue(ptype: int, m, text: str, ctx: Optional["CheckContext"] = None,
                  original: Optional[str] = None, about_now: bool = False) -> Optional[str]:
    """*about_now*: the subject's square is the position the claim is about
    (a written move's destination), so blockers count even after «если» or a
    written move — those positions are among the boards of the turn."""
    mid = m["mid"] or ""
    if _PIECE_WORD.search(mid) or _SQ_RE.search(mid):
        return None  # «конь на d5 и слон на c4 бьют f7»: whose attack?
    if _NEGATION.search(text[: m.start("verb")]):
        return None  # «ладью он не достаёт», «does not attack»
    if m["targets"].lstrip().startswith(","):
        return None  # «ладья d1 атакует, твои пешки g7/f7/h7 ещё стоят»
    if re.match(r"\s*by\s", m["targets"]):
        return None  # "the knight on d5 is hit by the bishop on c4": the passive names the attacker
    if _INVERTED.match(m["targets"]):
        return None  # «пешка e5 висит, её держит только конь c6»
    if re.search(r"(?:nothing|nobody|no\s+one|ничто|никто|ничего|никого)\s*$", mid):
        return None  # "the pawn on a4 is attacked but nothing defends a6": not the pawn's claim
    if re.search(r"(?:under|под)\s*$", mid):
        return None  # "the f2 pawn is under attack from the queen on h4": the pawn is the one attacked
    a = chess.parse_square(m["a"])
    targets = [t for t in _clause_targets(m["targets"]) if t != m["a"] and not _negated_target(m["targets"], t)]
    now = about_now or not _is_hypothetical(text, original if original is not None else text, m.start(),
                                            played=_just_played(ctx))
    # (Only for a piece named in words by its square: a written move as the subject already stands where it went.)
    went = None if about_now else _moved_in_sentence(original if original is not None else text, ptype, a, ctx)
    if went is not None:
        # «cxd4: пешка c5 бьёт пешку d4 и нападает на ферзя c3» — the pawn named by the square it left in
        # this very sentence: its capture is no attack claim, the rest is judged from where it went
        # (the lesson tutor's true sentence was cut, 2026-10-08).
        dest, after = went
        targets = [t for t in targets if t != chess.square_name(dest)]
        wrong = [t for t in targets if not _geometry_attack(ptype, dest, chess.parse_square(t))]
        if wrong:
            return f"a {_NAMES[ptype]} on {chess.square_name(dest)} does not attack {', '.join(wrong)}"
        own = _own_targets(ptype, dest, targets, m, [after]) if now else None
        if own:
            return own
        blocked = [t for t in targets if chess.parse_square(t) not in after.attacks(dest)]
        return f"a {_NAMES[ptype]} on {chess.square_name(dest)} does not reach {', '.join(blocked)}: a piece is in the way" \
            if blocked and now and _HARD_VERB.search(m["verb"]) else None
    if not targets and ctx is not None and re.match(r"\s*(?:it|её|ее|его)(?![а-яa-z])", m["targets"]):
        # "your queen on c3 defends it": the pronoun is the square the sentence is about
        referent = _pronoun_square(text, m.start("targets"), ctx)
        if referent and referent != m["a"]:
            targets = [referent]
            ctx._object = referent
    elif not targets and ctx is not None and now:
        # «ладья на g1 нападает на ферзя»: the one enemy queen of the position the claim is about
        board = _subject_board(ctx, ptype, a, derived_ok=about_now)
        if board is not None:
            defends = bool(re.search(r"держ|защищ|прикрыв|охраня|подстрах|defend|protect|guard|cover", m["verb"], re.IGNORECASE))
            targets = [t for t in _typed_targets(m["targets"], board, board.piece_at(a).color, defends) if t != m["a"]]
    # «Пешка e5 бьёт пешку d5 … и встаёт на d6» right after d7-d5: en passant takes d5.
    cur = ctx.current if ctx is not None else None
    if ptype == chess.PAWN and cur is not None and _ep_victim(cur, a) is not None:
        victim = chess.square_name(_ep_victim(cur, a))
        targets = [t for t in targets if t != victim]
    wrong = [t for t in targets if not _geometry_attack(ptype, a, chess.parse_square(t))]
    if wrong:
        return f"a {_NAMES[ptype]} on {m['a']} does not attack {', '.join(wrong)}"
    # «слон вышел на b5 и напал на твою пешку c6» — c6 held the bishop's OWN pawn (prod text game 28.10): an attack on
    # a piece named as a piece («пешку c6», not «поле c6») that is of the attacker's own side in every position.
    if ctx is not None and now:
        own = _own_targets(ptype, a, targets, m, [b for b in ctx.boards if (pc := b.piece_at(a)) is not None and pc.piece_type == ptype])
        if own:
            return own
    # The pattern fits; does the piece that really stands there reach the
    # square, or is something in the way? Only for what is said about now (or
    # about the position a written move leads to, which is on the boards).
    if ctx is not None and targets and _HARD_VERB.search(m["verb"]) and not _FUTURE_VERB.search(m["verb"]) and now:
        standing = [b for b in ctx.boards if (pc := b.piece_at(a)) is not None and pc.piece_type == ptype]
        if standing:
            blocked = [t for t in targets if not any(chess.parse_square(t) in b.attacks(a) for b in standing)]
            if blocked:
                return f"a {_NAMES[ptype]} on {m['a']} does not reach {', '.join(blocked)}: a piece is in the way"
    return None


from src.claim_scope import DENIAL as _NEGATED_WORD  # noqa: E402


def _negated_target(targets: str, square: str) -> bool:
    """«бьёт только по первой горизонтали, до h4 ей не достать»: the square sits
    in a clause (between commas) that denies something — not a claimed target."""
    at = re.search(rf"(?<![a-z0-9]){square}(?![0-9])", targets)
    if not at:
        return False
    # The clause is cut at commas and at conjunctions: «защищает пешку e5 и
    # ничего не подставляет» denies nothing about e5.
    start = max(targets.rfind(",", 0, at.start()) + 1,
                max((m.end() for m in _CONJ.finditer(targets, 0, at.start())), default=0))
    after = _CONJ.search(targets, at.end())
    end = targets.find(",", at.end())
    stops = [x for x in (end if end >= 0 else None, after.start() if after else None) if x is not None]
    clause = targets[start: min(stops) if stops else len(targets)]
    return bool(_NEGATED_WORD.search(clause))


_CONJ = re.compile(r"\s(?:и|а|но|или|and|but|or|yet)\s", re.IGNORECASE)


def _moved_in_sentence(text: str, ptype: int, a: int, ctx: Optional["CheckContext"]) -> Optional[tuple]:
    """(destination, board after) when this sentence's line moves the *ptype* piece standing on *a*."""
    if ctx is None:
        return None
    for _san, after, move in getattr(ctx, "scene_trail", []) or []:
        if move.from_square == a and after.piece_type_at(move.to_square) == ptype:
            return move.to_square, after
    return None


# «пешка h2 под боем ладьи h8, и конь f3 держит её»: the object pronoun after a defence/attack verb is the piece named
# last before it with the pronoun's gender (её — пешка, ладья; его — конь, слон, ферзь, король). Replaced by that
# piece's square so the claim is judged (prod long run 26.10: the knight on f3 does not defend h2).
_OBJ_PRONOUN = re.compile(r"(?<![а-яa-z])(?P<verb>держит|держат|защищает|защищают|прикрывает|прикрывают|охраняет|бь[её]т|атакует|нападает\s+на)\s+"
                          r"(?P<pron>е[её]|его)(?![а-яa-z])", re.IGNORECASE)
_PIECE_SQ_BEFORE = re.compile(rf"(?<![а-яa-z])(?P<piece>пешк\w*|ладь\w*|лад\w*|кон\w*|слон\w*|ферз\w*|корол\w*)\s+(?:на\s+)?(?P<sq>{SQ})(?![0-9])",
                              re.IGNORECASE)


def _resolve_object_pronouns(text: str) -> str:
    out, last = [], 0
    for m in _OBJ_PRONOUN.finditer(text):
        fem = m["pron"].lower() in ("её", "ее")
        named = [n for n in _PIECE_SQ_BEFORE.finditer(text[: m.start()])
                 if (n["piece"].lower().startswith(("пешк", "лад"))) == fem]
        if not named:
            continue
        # the piece the sentence is about: a nominative («пешка h2 под боем ладьи h8 … держит её» — the pawn, not the
        # rook in the genitive), else an accusative object, else the last one named
        nominative = [n for n in named if n["piece"].lower() in ("пешка", "ладья", "конь", "слон", "ферзь", "король")]
        accusative = [n for n in named if n["piece"].lower() in ("пешку", "ладью", "коня", "слона", "ферзя", "короля")]
        pick = (nominative or accusative or named)[-1]
        out.append(text[last: m.start("pron")] + pick["sq"].lower())
        last = m.end("pron")
    return "".join(out) + text[last:] if out else text


def _attack_issues(text: str, original: Optional[str] = None, ctx: Optional["CheckContext"] = None) -> list[str]:
    """*text* is lowercased for the piece words; *original* keeps the case of
    written moves (Rg1, Лг1) for the subject scan."""
    issues = []
    text = _resolve_object_pronouns(text)
    for ptype, rx in _ATTACK_CLAIMS:
        for m in rx.finditer(text):
            if ctx is not None:
                ctx._subject = (ptype, m["a"])
            issue = _attack_issue(ptype, m, text, ctx, original)
            if issue:
                issues.append(issue)
    if ctx is not None:
        # «он сам нападает: бьёт ладью d5» — the pronoun is the piece named last before it.
        for m in _PRONOUN_SUBJECT.finditer(text):
            named = list(_NAMED_PIECE.finditer(text[: m.start()]))
            # «Конь забирает пешку h7 с шахом: он бьёт f8 и f6» — «он» is the knight, not the pawn: a Russian
            # pronoun agrees in gender (конь, слон, ферзь, король — он; пешка, ладья — она), and a piece in the
            # accusative is what was taken, not who acts (a true sentence was cut on production, 2026-10-08).
            pron = (m.group("pron") or "").lower()
            if pron in ("он", "она"):
                fem = pron == "она"
                named = [n for n in named if (re.match(r"(?:пешк|лад)", n["piece"].lower()) is not None) == fem
                         and not re.fullmatch(r"(?:коня|слона|ферзя|короля|пешку|ладью)", n["piece"].lower())]
            if not named or _NEGATION.search(text[m.start(): m.start("verb")]):
                continue
            last = named[-1]
            ptype = _piece_type(last["piece"])
            if ptype is None:
                continue
            a_name = last["a"]
            moved = re.findall(rf"(?:на|to|onto)\s+({SQ})(?![0-9])", text[last.end(): m.start()])
            if moved:
                a_name = moved[-1]  # «увести ладью с d5 на f5: она бьёт по f6» — the rook is on f5 now
            a = chess.parse_square(a_name)
            targets = [t for t in _clause_targets(m["targets"]) if t != a_name]
            wrong = [t for t in targets if not _geometry_attack(ptype, a, chess.parse_square(t))]
            if wrong:
                issues.append(f"a {_NAMES[ptype]} on {a_name} does not attack {', '.join(wrong)}")
    # A written move as the subject (Лg1 read as Rg1; a Cyrillic «К» is skipped —
    # a king or a knight, the model writes both).
    converted, cyr_k = _to_san(original if original is not None else text)
    for m in _SAN_SUBJECT.finditer(converted):
        if m.start("piece") in cyr_k:
            continue
        ptype = chess.PIECE_SYMBOLS.index(m["piece"].lower())
        issue = _attack_issue(ptype, m, converted, ctx, converted, about_now=True)
        if issue and issue not in issues:
            issues.append(issue)
    # «Если сыграть Rg1, ладья нападает на ферзя h4»: the rook is the one that
    # just went to g1 — the written move before it names its square.
    for ptype, rx in _BARE_SUBJECT:
        if ptype == chess.PAWN:
            continue  # «угроза d5 — пешка наступает и бьёт коня c6»: a pawn is named for a plan square, not the last written move
        for m in rx.finditer(converted):
            mid = m["mid"] or ""
            if _SQ_RE.search(mid.lower()) or _PIECE_WORD.search(mid.lower()):
                continue  # «ладья на g1 нападает…» is the squared claim above; «ладья и слон бьют…» is not one piece's
            dest = _move_before(converted, m.start(), ptype)
            if dest is None:
                continue
            if re.search(rf"(?<![a-z0-9]){dest}(?![0-9])", (m["targets"] or "").lower()):
                # «Qxg6+ — ферзь бьёт коня на g6»: the capture the move makes, not an attack
                # from g6 (production 2026-10-07: read as «the queen attacks the e7 knight»).
                continue
            issue = _attack_issue(ptype, _WithSquare(m, dest), converted, ctx, converted, about_now=True)
            if issue and issue not in issues:
                issues.append(issue)
    return issues


# «после Rg1 ладья перейдёт на g3», "after Rg1 the rook is ready to swing to g3":
# the piece a written move just placed is said to go on to a square. Judged
# narrowly (production, 2026-10-05: the rook on g1 «swings to g3» through the
# king on g2): not a move of that piece at all, or its own KING in the way —
# a pawn or a piece in the way may be a plan to move it first, and is let be.
_PLAN_MOVE = []
for _ptype, _pat in _RU_SUBJECTS:
    if _ptype == chess.PAWN:
        continue
    _PLAN_MOVE.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + r"(?P<mid>(?:\s+(?!на\s|к\s)[а-яa-z]+){0,4}?)\s+"
        r"(?:перейд[её]т|перейти|пойд[её]т|пойти|встанет|встать|ид[её]т|идти|прыгнет|прыгнуть|отойд[её]т|отойти|"
        r"уйд[её]т|уйти|перевести|переведи|переводится|готова?\s+(?:перейти|пойти|встать|прыгнуть))"
        rf"\s+(?:на|к)\s+(?P<to>{SQ})(?![0-9])", re.IGNORECASE)))
for _ptype, _pat in _EN_PIECES:
    if _ptype == chess.PAWN:
        continue
    _PLAN_MOVE.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + r"(?P<mid>(?:\s+(?!to\s|on\s|onto\s)[a-z]+){0,4}?)\s+"
        r"(?:swings?|goes?|moves?|jumps?|comes?|lands?|drops?|slides?|hops?|heads?|can\s+go|will\s+go|is\s+ready\s+to\s+(?:swing|go|move|jump))"
        rf"\s+(?:over\s+|back\s+)?(?:to|on|onto)\s+(?P<to>{SQ})(?![0-9])", re.IGNORECASE)))


def _plan_move_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    issues = []
    converted, _ = _to_san(original)
    for ptype, rx in _PLAN_MOVE:
        for m in rx.finditer(converted):
            if _SQ_RE.search((m["mid"] or "").lower()) or _PIECE_WORD.search((m["mid"] or "").lower()):
                continue
            frm = _move_before(converted, m.start(), ptype)
            if frm is None:
                continue
            a, b = chess.parse_square(frm), chess.parse_square(m["to"])
            if a == b or ptype in (chess.KNIGHT, chess.KING):
                continue  # «Nbd2–f1–g3 — конь идёт на g3», «5...Na5 instead of 5...Nxd5 — your knight goes to a5»: the written move is not this knight's
            if not _geometry_move(ptype, a, b):
                issues.append(f"a {_NAMES[ptype]} on {frm} cannot go to {m['to']}")
                continue
            standing = [bd for bd in ctx.boards if not ctx.is_given(bd)
                        and (pc := bd.piece_at(a)) is not None and pc.piece_type == ptype]
            if not standing:
                continue
            for bd in standing:
                own = bd.piece_at(a).color
                blockers = [sq for sq in chess.SquareSet.between(a, b) if bd.piece_at(sq) is not None]
                king = next((sq for sq in blockers if (pc := bd.piece_at(sq)).piece_type == chess.KING and pc.color == own), None)
                if king is not None and all(bd.piece_at(sq) is not None for sq in [king]):
                    issues.append(f"a {_NAMES[ptype]} on {frm} cannot go to {m['to']}: its own king on "
                                  f"{chess.square_name(king)} is in the way")
                    break
    return issues


def _move_before(converted: str, upto: int, ptype: int) -> Optional[str]:
    """The destination of the last move of a *ptype* piece written before *upto*
    («Rg1», «1.e4», «...Nf6»); None when no such move is written."""
    dest = None
    for m in _MOVE.finditer(converted[:upto]):
        san = m["san"]
        if san.startswith("O-O"):
            continue
        if san[0] in "KQRBN":
            moved = chess.PIECE_SYMBOLS.index(san[0].lower())
        elif m["num"] or m["bdots"] or "x" in san:
            moved = chess.PAWN
        else:
            continue  # a bare «e4» is a square
        if moved == ptype:
            dest = re.findall(SQ, san)[-1]
    return dest


# «Тогда Bxd8…», «онда Сxd8…», "then Bxd8": the sentence goes on with the line of
# the one before — its moves are not judged on the board on the screen.
_CONTINUES = re.compile(r"^\W*(?:(?:и|а|и\s+вот|and)\s+)?(?:тогда|затем|потом|далее|дальше|после\s+этого|онда|сонда|"
                        r"содан\s+кейін|then|next|after\s+that|and\s+then)(?![а-яa-z])", re.IGNORECASE)


def _blocked_capture(ctx: "CheckContext", ptype: int, colors: list, dest: int) -> Optional[str]:
    """Why a written capture on *dest* fails on the positions given to the turn:
    every piece of that kind that could take there has a piece in its way. None
    when some position lets it through (then the move fails for another reason —
    a pin, a check — and the generic message stands), or when nothing of that
    kind aims at *dest*, or there is nothing to take (a plan, judged leniently)."""
    why = None
    for board in ctx.boards:
        if not ctx.is_given(board) or (board is not ctx.current and board.board_fen() == chess.STARTING_BOARD_FEN):
            continue
        for color in colors:
            target = board.piece_at(dest)
            if target is None or target.color == color:
                continue
            movers = [sq for sq in board.pieces(ptype, color) if _geometry_move(ptype, sq, dest)]
            if not movers:
                continue
            if ptype in (chess.KNIGHT, chess.KING):
                return None  # nothing can stand in its way: another reason
            for sq in movers:
                blockers = [b for b in chess.SquareSet.between(sq, dest) if board.piece_at(b) is not None]
                if not blockers:
                    return None
            if why is None:
                sq = movers[0]
                b = next(b for b in chess.SquareSet.between(sq, dest) if board.piece_at(b) is not None)
                why = (f"the {chess.piece_name(board.piece_type_at(b))} on {chess.square_name(b)} is in the way "
                       f"of the {_NAMES[ptype]} on {chess.square_name(sq)}")
    return why


def _pawn_reaches(color: chess.Color, sq: int, dest: int, capture: bool) -> bool:
    forward = 1 if color == chess.WHITE else -1
    df = chess.square_file(dest) - chess.square_file(sq)
    dr = (chess.square_rank(dest) - chess.square_rank(sq)) * forward
    return abs(df) == 1 and dr == 1 if capture else df == 0 and dr in (1, 2)


def _reachable(boards: list, ptype: int, colors: list, dest: int, steps: int, capture: bool) -> bool:
    """Some piece of *ptype* and one of *colors* in some position stands on
    *dest* (the move was just played) or gets there in *steps* moves by its
    pattern — a capture or a check is a claim about now (one step), a quiet
    move may be a plan («...a6 и ...Ba7»: two)."""
    for board in boards:
        for color in colors:
            for sq in board.pieces(ptype, color):
                if sq == dest:
                    return True
                if ptype == chess.PAWN:
                    if _pawn_reaches(color, sq, dest, capture) or (not capture and _pawn_reaches(color, sq, dest, True)):
                        return True
                    continue
                if _geometry_move(ptype, sq, dest):
                    return True
                if steps > 1 and any(_geometry_move(ptype, sq, mid) and _geometry_move(ptype, mid, dest)
                                     for mid in chess.SQUARES):
                    return True
    return False


def _long_issues(text: str, ctx: CheckContext) -> tuple[list[str], str]:
    """From-to moves («Ke3–e5», «Nb1–d2–f1–g3», «...d7-d5»): each hop must be a
    move of that piece. Returns the issues and *text* with these moves blanked
    (the SAN scan must not read «Ke3» of «Ke3–e5» as a king going to e3)."""
    issues = []
    for m in _LONG.finditer(text):
        squares = re.findall(SQ, m["chain"])
        piece = m["piece"]
        explicit = bool(m["num"] or m["bdots"])
        if not piece and not explicit:
            continue  # «c2–c3», «диагональ a2–g8»: plain squares, not a written move
        ptype = chess.PIECE_SYMBOLS.index(piece.lower()) if piece else chess.PAWN
        for a, b in zip(squares, squares[1:]):
            if ptype == chess.KING and _geometry_move(chess.KNIGHT, chess.parse_square(a), chess.parse_square(b)):
                continue  # a Latin K for the Russian К (конь)
            if not _geometry_move(ptype, chess.parse_square(a), chess.parse_square(b)):
                issues.append(f"{m.group(0).strip()}: a {_NAMES[ptype]} cannot move from {a} to {b}")
                break
        # The first hop, where it is a legal move, continues a written line.
        for board in list(ctx.boards):
            try:
                move = chess.Move.from_uci(squares[0] + squares[1])
            except ValueError:
                break
            for color in (chess.WHITE, chess.BLACK):
                trial = board.copy(stack=False)
                trial.turn = color
                if move in trial.legal_moves:
                    trial.push(move)
                    ctx.add(trial.fen(), derived=True)
                    break
    blanked = _LONG.sub(lambda m: " " * len(m.group(0)) if (m["piece"] or m["num"] or m["bdots"]) else m.group(0), text)
    return issues, blanked


def _move_denied(text: str) -> bool:
    """A written move the sentence refutes: «Лe4 сыграть нельзя», «нельзя Rxh4», «хода Qxg7 нет».
    The denial sits next to the move — «Ra5+! — шах, после которого белый король не может удержать
    пешку» denies something of the king, and its false «+» was let through (production 2026-10-07)."""
    converted, _ = _to_san(text)
    for m in _MOVE.finditer(converted):
        before = converted[max(0, m.start() - 28): m.start()]
        after = converted[m.end(): m.end() + 40]
        after = re.split(r"[.;!?]|\s[—–-]\s|,\s*(?:а|но|и|потому|после|чтобы|так\s+как|but|and|after)\s", after)[0]
        if _DENIES.search(after) or re.search(r"(?:нельзя|невозможн\w*|не\s+(?:можешь|может|сможешь|получится)|"
                                              r"can'?t|cannot)\s+(?:сыграть|играть|сделать|ход\w*|play|go\s+for)?\s*$", before, re.IGNORECASE):
            return True
    return False


def _recapture_issues(text: str, ctx: CheckContext) -> list[str]:
    """«чёрные бьют Bxe3, ты берёшь fxe3» with no pawn on f2 — a pawn taking back on the square
    the move before it captured on, where no such pawn stands (the client's game, 2026-10-07)."""
    converted, _ = _to_san(text)
    moves = list(_MOVE.finditer(converted))
    issues = []
    for first, second in zip(moves, moves[1:]):
        san1, san2 = first["san"], second["san"]
        if "x" not in san1 or not re.fullmatch(r"[a-h]x[a-h][1-8]", san2) or san2[-2:] != san1[-2:]:
            continue
        if first["num"] or first["bdots"] or second["num"] or second["bdots"]:
            continue  # a written line («17. Bxd5 cxd5») is followed by the line check
        missing = None
        for board in [b for b in ctx.boards if ctx.is_given(b) and (ctx.current is None or b.board_fen() != chess.STARTING_BOARD_FEN or ctx.current.board_fen() == chess.STARTING_BOARD_FEN)]:
            for color in (chess.WHITE, chess.BLACK):
                trial = board.copy(stack=False)
                trial.turn = color
                try:
                    move = trial.parse_san(san1)
                except ValueError:
                    continue
                if not trial.is_capture(move):
                    continue
                trial.push(move)
                try:
                    trial.parse_san(san2)
                    return []  # a position of the turn where that pawn stands: a line from there
                except ValueError:
                    dest = chess.parse_square(san2[-2:])
                    rank = chess.square_rank(dest) + (-1 if trial.turn == chess.WHITE else 1)
                    if 0 <= rank <= 7:
                        missing = chess.square_name(chess.square(chess.FILE_NAMES.index(san2[0]), rank))
        if missing:
            issues.append(f"{san2} is impossible after {san1}: there is no pawn on {missing} to take back on {san2[-2:]}")
    return issues


# «Партия шла так: 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.Nc3?…» about a position given without its game
# (production 2026-10-07): the moves that led here are not known, and the model made them up.
_HISTORY = re.compile(
    r"(?:(?:партия|игра)\s+(?:шла|развивалась|складывалась|началась)\s+(?:так|следующим\s+образом|вот\s+так)"
    r"|(?:до\s+этого|перед\s+этим)\s+(?:было|сыграли|сыграно)|the\s+game\s+(?:went|started|began)(?:\s+like\s+this)?)"
    r"[^.!?]{0,20}?\d{1,3}\s?\.", re.IGNORECASE)
INVENTED_HISTORY = "no game is loaded: the moves that led to this position are not known — do not invent them"


def _history_issues(text: str, ctx: CheckContext) -> list[str]:
    if getattr(ctx, "game_lines", 0) or not _HISTORY.search(text):
        return []
    return [INVENTED_HISTORY]


def _san_issues(text: str, ctx: CheckContext) -> list[str]:
    """Written moves that fit no position of the turn and no piece that could make them."""
    denied = bool(_DENIES.search(text))
    if denied and _move_denied(text):
        return []  # «Лe4 сыграть нельзя»: the move is being refuted
    issues = _san_issues_all(text, ctx)
    if denied:
        # A denial elsewhere («почему нельзя просто Kxf4?» — a question, a refutation further
        # on): a move is not called impossible, only a «+»/«#» it does not give.
        issues = [i for i in issues if i.endswith(("gives no check", "is not checkmate"))]
    return issues


def _parses(board: chess.Board, san: str) -> bool:
    try:
        board.parse_san(san)
        return True
    except ValueError:
        return False


def _san_issues_all(text: str, ctx: CheckContext) -> list[str]:
    converted, cyr_k = _to_san(text)
    converted = _MATE_WORD.sub(lambda mm: mm.group("san") + "#" + mm.group("rest"), converted)
    issues, converted = _long_issues(converted, ctx)
    in_line_until = -1  # a bare pawn move right after a played move is part of the line
    # The position after the previous move of this sentence: a written line is
    # followed from there first, so «1.e4 e5 2.Nf3 … 7.Qf3+» ends in the right
    # position (and its «+» is judged there), not in whichever position of the
    # turn happens to allow each move.
    prev: Optional[chess.Board] = None
    # Whether the chain of moves that leads to *prev* is to be trusted for a
    # «+» / «#»: it began on a position given to the turn, or at move 1 on the
    # start position. A chain begun on the start position standing in for an
    # unknown one («…13.Qe4 Rxf2 14.dxe5 Bg5+»), or re-begun mid-line, is not.
    prev_trusted = False
    for m in _MOVE.finditer(converted):
        san, num, dots = m["san"], m["num"], m["dots"] or m["bdots"]
        numbered = bool(num or m["bdots"])
        is_piece = san[0] in "KQRBN"
        continues_line = in_line_until >= 0 and not converted[in_line_until:m.start()].strip()
        if not numbered and not is_piece and not continues_line and "x" not in san:
            continue  # «e4» without a number is a square, not a move
        # «bxa6» without a number: followed where it is legal so the line goes on from it
        # («… bxa6. Тогда … Bc6#»), never judged impossible itself (a plan, another position).
        bare_capture = not numbered and not is_piece and not continues_line
        if num and not is_piece and re.fullmatch(r"[\s*_#>`-]*", converted[:m.start()]) \
                and re.match(r"\d{1,3}\.\s", converted[m.start():]) \
                and not re.search(r"\d{1,3}\.\s?[KQRBNa-hO]", converted[m.end():m.end() + 40]):
            continue  # «1. f7 пешкасы…»: a numbered list item, not 1.f7 («* **1. d4 Nf6 2. c4» is a line)
        if san.startswith("O-O") or san in ctx.quoted:
            continue
        list_item = bool(num) and dots == "." and re.fullmatch(r"[\s*_#>`-]*", converted[:m.start()]) \
            and re.match(r"\d{1,3}\.\s", converted[m.start():])
        if dots in ("...", "…"):
            colors = [chess.BLACK]
        elif num and dots == "." and not list_item:
            colors = [chess.WHITE]
        else:
            colors = [chess.WHITE, chess.BLACK]
        full = san + (m["check"] or "")
        # «Правильно было 5. Nxd4» about the game on the board: the move numbered N starts a line at move N of
        # that game, not wherever such a move happens to be legal (4.Nxd4 was, 5.Nxd4 was not — stand,
        # 2026-10-13). Only for a line's first move, with the game's position at that move given to the turn.
        if num and prev is None and not list_item and dots in (".", "...", "…") and getattr(ctx, "game_lines", 0):
            want = chess.WHITE if dots == "." else chess.BLACK
            at_n = [b for b in ctx.boards if b.fullmove_number == int(num) and b.turn == want and ctx.is_given(b)]
            if at_n and not any(_parses(b, full) for b in at_n):
                issues.append(f"{num}{dots}{full} is not possible at move {num} of the game "
                              f"(position {at_n[0].fen()})")
                continue
        legal_somewhere = False
        # «Rxd6#» parses as a legal move whether or not it mates: the suffix is
        # judged where the move is really meant — the line's own continuation
        # or a position of the turn (not the start position that stands in for
        # unknown ones), and a capture only where it captures.
        suffix_judged = suffix_ok = False
        fallback = ctx.boards[0] if ctx.boards and (ctx.current is None or ctx.current.board_fen() != ctx.boards[0].board_fen()) else None
        # The line's own continuation first, then the boards of the turn (the one
        # on the screen before the rest), the start position standing in for an
        # unknown one last — «4...d5 5.exd5» used to start from the start
        # position, where 4...d5 is legal too, and 5.exd5 then found no pawn.
        boards = list(ctx.boards)
        ordered = ([ctx.current] if ctx.current is not None and ctx.current in boards else []) \
            + [b for b in boards if b is not fallback and b is not ctx.current] + ([fallback] if fallback is not None else [])
        # A board where it is that side's move comes before one where the side is changed to fit: «15.Bxd7+ …
        # 16.Qb8+» is the game's 16th move, not White moving twice after 15.Bxd7+ (2026-10-08).
        candidates = ([(prev, [prev.turn])] if prev is not None and prev.turn in colors else []) \
            + [(b, [c for c in colors if c == b.turn]) for b in ordered] \
            + [(b, [c for c in colors if c != b.turn]) for b in ordered]
        for board, board_colors in candidates:
            if board is prev:
                trusted = prev_trusted
            else:
                trusted = (board is not fallback and ctx.is_given(board)) \
                    or (board is fallback and num == "1" and dots == "." and not list_item)
            for color in board_colors:
                trial = board.copy(stack=False)
                trial.turn = color
                try:
                    move = trial.parse_san(full)
                except ValueError:
                    continue
                if m["check"] and not suffix_ok and ("x" not in san or trial.is_capture(move)):
                    gives = trial.gives_check(move)
                    after = trial.copy(stack=False)
                    after.push(move)
                    holds = after.is_checkmate() if m["check"] == "#" else gives
                    if trusted:
                        suffix_judged = True
                        suffix_ok = holds
                    elif holds:
                        # The answer's own line («Qa6+ … bxa6 … Bc6#») reaches a position where
                        # it mates: that clears it, though a derived position never condemns
                        # (production 2026-10-07: «следует Bc6# — мат» was cut on the board as it stands).
                        suffix_ok = True
                if not legal_somewhere:
                    legal_somewhere = True
                    scene_san = trial.san(move)
                    trial.push(move)
                    prev, prev_trusted = trial, trusted
                    ctx.add(trial.fen(), derived=True)  # a line written in the answer goes on from here
                    ctx.scene, ctx.scene_san, ctx.scene_age = trial.copy(stack=False), scene_san, 0
                    ctx.scene_trail.append((scene_san, ctx.scene, move))
                if suffix_ok or not m["check"]:
                    break
            if legal_somewhere and (suffix_ok or not m["check"]):
                break
        in_line_until = m.end() if legal_somewhere else -1
        if not legal_somewhere:
            prev, prev_trusted = None, False
        if legal_somewhere:
            if suffix_judged and not suffix_ok and not bare_capture:
                label = (f"{num}{dots}" if num else (dots or "")) + full
                issues.append(f"{label} is not checkmate" if m["check"] == "#" else f"{label} gives no check")
            continue
        if bare_capture:
            continue
        ptype = chess.PIECE_SYMBOLS.index(san[0].lower()) if is_piece else chess.PAWN
        dest = chess.parse_square(re.findall(SQ, san)[-1])
        capture = "x" in san or bool(m["check"])
        # «Возьми ферзя ладьёй: Rxh4» with the h2 pawn between (stand, 2026-10-04):
        # a capture written for the board on the screen, by a piece that is there
        # but cannot get through, is impossible — not a plan from another position.
        if is_piece and "x" in san and prev is None and ctx.current is not None and not list_item \
                and not _is_hypothetical(text, text, m.start()) and not _CONTINUES.match(text):
            blocked = _blocked_capture(ctx, ptype, colors, dest)
            if blocked:
                issues.append(f"{full} is not possible here: {blocked}")
                continue
        # Reachable by such a piece in some position of the turn: lenient on purpose —
        # plans («...d6, ...Na5») and lines from positions not on the board are common.
        if _reachable(ctx.boards, ptype, colors, dest, 1 if capture else 2, capture):
            continue
        if ptype == chess.KING and _reachable(ctx.boards, chess.KNIGHT, colors, dest, 1, capture):
            continue  # «Kc6» with a Latin K for the Russian К (конь)
        san_at = m.start("san")
        if san_at in cyr_k and _reachable(ctx.boards, chess.KING, colors, dest, 2, capture):
            continue  # «Кh1» written for the king
        side = {1: "white", 0: "black"}.get(colors[0]) if len(colors) == 1 else "any"
        label = (f"{num}{dots}" if num else (dots or "")) + full
        issues.append(f"{label} is impossible: no {side} {_NAMES[ptype]} can "
                      f"{'capture on' if capture else 'reach'} {chess.square_name(dest)} in the positions of this turn")
    return issues


_IDENTITY = re.compile(r"(?<![а-яa-z])(?:это|перед\s+нами|у\s+нас|называется|называют|сыгран\w*|разыгр\w*|получил\w*|this\s+is"
                       r"|it'?s\s+(?:the|a)|is\s+called|we\s+have|бұл)(?![а-яa-z])", re.IGNORECASE)
_NAME_HEDGE = re.compile(r"(?<![а-яa-z])(?:не|нет|похож\w*|напомина\w*|отлич\w*|если|бы|вместо|переход\w*|перешл\w*|перейд\w*|станет"
                         r"|начинал\w*|могл\w*|может|бывает|как\s+в|could|would|transpos\w*|unlike|like|not|instead|if)(?![а-яa-z])",
                         re.IGNORECASE)


_ON_THE_BOARD = re.compile(r"на\s+доске|эт(?:а|ой|у)\s+позици|в\s+этой\s+позиции|(?<![а-яa-z])(?:здесь|тут)(?![а-яa-z])"
                           r"|this\s+position|on\s+the\s+board|(?<![a-z])here(?![a-z])", re.IGNORECASE)
_ASKS_BOARD_NAME = re.compile(r"как\s+называ|что\s+(?:это\s+)?за\s+(?:дебют|защит|вариант|систем)|какой\s+(?:это\s+)?(?:дебют|вариант)"
                              r"|какая\s+(?:это\s+)?(?:защита|система)|what\s+(?:opening|defen[cs]e|variation)|which\s+opening"
                              r"|қандай\s+дебют", re.IGNORECASE)


_LINE_IN_GENERAL = re.compile(r"(?:^|[^а-яё])(?:играют|отвечают|ставят|выбирают|берут|^\W*(?:или|либо|а\s+если))(?![а-яё])")
# any past-tense verb («защитили», «поставили», «двинули», «сделал»): the game is being told, not the line in general
_PAST_VERB = re.compile(r"(?<![а-яё])[а-яё]{3,}(?:ил|ал|ял|ел|ул|ыл)(?:и|а|о|ся|ись|ась)?(?![а-яё])")
_PLAYED_HERE = re.compile(r"(?<![а-яё])(?:сыграл\w*|ответил\w*|взял\w*|пош[её]л\w*|пошли|выбрал\w*|разыграл\w*|получил\w*|сложил\w*|"
                          r"у\s+нас|у\s+тебя|у\s+меня|в\s+нашей|в\s+(?:этой\s+)?партии|на\s+доске)(?![а-яё])")


def _opening_identity_issues(text: str, ctx: Optional[CheckContext]) -> list[str]:
    """«Это защита Каро-Канн, вариант Атака Панова» on the Advance Variation (stand theory run 28.10), «Это дебют
    четырёх коней» after 1.e3 e5 2.Nc3 (stand text game): the opening the answer says is on the board must be the
    ECO book's opening of the board — by the game's moves, or by the position."""
    if ctx is None or not _IDENTITY.search(text):
        return []
    from src.openings_book import _FAMILIES_RE, _NAMED_RE, _split_moves, get_book, named_openings

    # About the board only: a game, the board named in the sentence, or the student asking the board's opening — «это
    # называется жареная печень» may be the line explained in words while the student's own position stays.
    in_game = bool(getattr(ctx, "game_moves", None))
    q = (ctx.question_raw or ctx.question or "")
    asks_board = bool(_ASKS_BOARD_NAME.search(q)) and not named_openings(q)
    if not (in_game or asks_board or _ON_THE_BOARD.search(text)):
        return []
    if re.search(r"(?<![0-9])1\s?\.\s?(?:[KQRBNКФЛС]?[a-h]?x?[a-h][1-8]|O-O)", text):
        return []  # a line written from move 1 is judged by its own moves (_opening_issues)

    lowered = text.lower().replace("ё", "е").replace("’", "'")
    found = []
    for rx, name in _NAMED_RE + _FAMILIES_RE:
        m = rx.search(lowered)
        if m and not any(name == n for n, _ in found):
            found.append((name, m.start()))
    if not found:
        return []
    book = get_book()
    truth = None
    moves = getattr(ctx, "game_moves", None)
    if moves:
        truth = book.identify(list(moves))
        truth = (truth["eco"], truth["name"], truth.get("book_line") or "") if truth else None
    if truth is None and ctx.current is not None:
        hit = book.by_position(ctx.current.fen())
        truth = (hit["eco"], hit["name"], hit.get("line") or hit.get("book_line") or "") if hit else None
    if truth is None:
        return []
    eco, real, real_line = truth
    converted, _ = _to_san(text)
    said_moves = [(x.group("san").rstrip("+#"), x.start()) for x in _MOVE.finditer(converted)]
    # …said of the line in general before it is named («чаще всего играют e6, это называется …», «или c6, это …»), not
    # as played here («чёрные сыграли a6») nor after the name («Это вариант Найдорфа, типичный ход a6»)
    # — and never when the board's own name is asked or claimed («Это …», «Перед нами …», «У нас …»)
    general = (bool(_LINE_IN_GENERAL.search(lowered)) and not _PLAYED_HERE.search(lowered) and not _PAST_VERB.search(lowered)
               and not asks_board
               and not re.match(r"\W*(?:это|перед\s+нами|здесь|тут)(?![а-яё])", lowered)
               and not re.search(r"перед\s+нами|мы\s+(?:раз)?игра\w*|(?:сейчас|теперь)\s+это|это\s+и\s+есть|"
                                 r"(?:тво|наш|мо)\w*\s+(?:позици|дебют|парти|вариант)", lowered))
    real_moves = _split_moves(real_line) if real_line else ()
    out = []
    for name, at in found:
        if _NAME_HEDGE.search(lowered[max(0, at - 40):at]):
            continue  # «не путай с атакой Панова», «похоже на венскую», «если бы … Винавер»
        if real == name or real.startswith(name.split(":")[0] if ":" not in name else name):
            continue  # the family of the real line, or the real line itself
        variation = name.split(":", 1)[-1].strip().lower()
        if variation in real.lower() or real.split(":", 1)[-1].strip().lower() in lowered:
            continue  # «Accelerated London System» names the real line, «London System» is part of it
        entry = book.exact(name) or next(iter(book.by_name(name)), None)
        if entry is None:
            continue
        line = _split_moves(entry[2])
        played = tuple(moves or ()) or real_moves
        unplayed = set(line) - set(played)
        if general and any(mv in unplayed and pos < at for mv, pos in said_moves):
            # «Чаще всего чёрные играют e6 — это отказанный ферзевый гамбит» over a game of 2...dxc4 (prod Live 29.10):
            # the move named is the line's, not the game's — the sentence describes that line
            continue
        if played and (tuple(played[:len(line)]) == line or tuple(line[:len(played)]) == tuple(played)):
            continue  # the named line is on the way to, or the way from, the board's
        if ":" not in name and real.split(":")[0] == name:
            continue
        out.append(f"the opening on the board is the {real} ({eco}) by the ECO book, not the {name}")
    return out


# The game told move by move (stand text games 28.10): «3...Кf6 — конь вышел и прикрыл f7», «слон с f8 поднялся на e7 и
# прикрыл f7», «d6 перекрыла дорогу слону c8», «чёрные атакуют её ходом е6» — each false, none checked before.
_GONE = (r"(?:вышел|вышла|пош[её]л|пошла|встал|встала|поднялся|поднялась|отош[её]л|отошла|отступил|отступила|вернулся|"
         r"вернулась|уш[её]л|ушла|двинулся|двинулась|прыгнул|прыгнула|переш[её]л|перешла)")
_MOVED_CLAIM = re.compile(
    # «конь с g8 встал на f6», and the move told the 29.10 way, «конь с g8 на f6 вышел в центр и сразу напал на d4»
    rf"(?<![а-яё])(?P<piece>конь|слон|ладья|ферзь|пешка|король)\s+(?:с\s+(?P<frm>{SQ})\s+)?"
    rf"(?:{_GONE}(?:\s+с\s+{SQ})?(?:\s+(?:на|в)\s+(?P<to>{SQ}))?|(?(frm)на\s+(?P<to2>{SQ})\s+{_GONE}|(?!)))"
    # one more clause of the same piece on the way («, вышел в центр и …») — no wider: «, а ты … напал» is another subject
    rf"(?:,\s*(?:вышел|вышла|пош[её]л|пошла|двинул\w*)(?:\s+(?:в\s+центр|вперёд|вперед|в\s+игру))?)?(?:(?!(?:конь|слон|ладья|ферзь|пешка|король)(?![а-яё])|на\s+[a-h][1-8])[^.!?;:]){{0,12}}?"
    r"\s*(?:\s+и\s+|\s*—\s*|,\s*)(?:сразу\s+|тоже\s+|заодно\s+|уже\s+)?"
    r"(?P<verb>прикрыл\w*|защитил\w*|подкрепил\w*|поддержал\w*|укрепил\w*|напал\w*(?:\s+на)?|атаковал\w*|атакует|бь[её]т|держит|нацелил\w*(?:\s+на)?|смотрит\s+на|давит\s+на)\s+"
    r"(?:тво\w+\s+|мо\w+\s+|сво\w+\s+|его\s+|е[её]\s+)?(?:поле\s+|пункт\s+|пешк\w+\s+|кон\w+\s+|слон\w*\s+|ладь\w+\s+|ферз\w+\s+|корол\w+\s+)?"
    rf"(?:на\s+)?(?P<target>{SQ})(?![0-9])", re.IGNORECASE)
_BLOCK_ACTIVE = re.compile(
    rf"(?<![a-z0-9])(?P<b>{SQ})\s+(?:сразу\s+|тоже\s+|ещ[её]\s+)?(?:перекрыл\w*|закрыл\w*|запер\w*|перекрывает|закрывает|запирает)\s+"
    r"(?:дорогу\s+|путь\s+|диагональ\s+|линию\s+)?(?:сво\w+\s+|тво\w+\s+|мо\w+\s+)?(?P<pw>слон\w*|ладь\w+|ферз\w+)\s+(?:на\s+)?"
    rf"(?P<p>{SQ})(?![0-9])", re.IGNORECASE)
_BLOCK_PASSIVE = re.compile(
    rf"(?P<pw>слон|ладья|ферзь)\s+(?:на\s+)?(?P<p>{SQ})\s+(?:сейчас\s+|вс[её]\s+ещ[её]\s+|пока\s+)?(?:заперт\w*|закрыт\w*|перекрыт\w*)\s+"
    rf"(?:сво\w+\s+)?(?:пешк\w+|кон\w+|слон\w+|фигур\w+)\s+(?:на\s+)?(?P<b>{SQ})(?![0-9])", re.IGNORECASE)
_BY_OBJ = rf"(?:её|ее|его|(?:(?:пешк\w+|кон\w+|слон\w*|ладь\w+|ферз\w+)\s+(?:на\s+)?)?{SQ})"
_BY_VERB = r"(?:атаку\w+|напада\w+|бь[её]т|бьют)"
_BY_MOVE = re.compile(
    rf"(?:{_BY_VERB}\s+(?P<obj>{_BY_OBJ})|(?P<obj2>{_BY_OBJ})\s+(?:сразу\s+|тут\s+же\s+|уже\s+)?{_BY_VERB})\s+"
    r"ходом\s+(?P<mv>[^\s,.;!?]+)", re.IGNORECASE)
_SLIDER = {"слон": chess.BISHOP, "ладь": chess.ROOK, "ферз": chess.QUEEN}
_MOVER = {"конь": chess.KNIGHT, "слон": chess.BISHOP, "ладья": chess.ROOK, "ферзь": chess.QUEEN, "пешка": chess.PAWN,
          "король": chess.KING}


def _xray(board: chess.Board, a: int, t: int, battery: bool = True) -> chess.SquareSet:
    """What the piece on *a* attacks once its own pieces between it and *t* are gone: a battery («ладья за ферзём
    поддержала d4»), or for a look (*battery* False) any own piece but a pawn — «слон g7 смотрит на d4» through the
    knight f6 that can step away, not «слон d6 смотрит на h2» through its own pawn e5."""
    piece = board.piece_at(a)
    clear = board.copy(stack=False)
    diagonal = chess.square_file(a) != chess.square_file(t) and chess.square_rank(a) != chess.square_rank(t)
    movers = (chess.BISHOP, chess.QUEEN) if diagonal else (chess.ROOK, chess.QUEEN)
    for sq in chess.SquareSet(chess.between(a, t)):
        own = clear.piece_at(sq)
        if own is None:
            continue
        if piece is None or own.color != piece.color or (own.piece_type not in movers if battery else own.piece_type == chess.PAWN):
            return chess.SquareSet()  # a pawn or a knight in the way blocks the line
        clear.remove_piece_at(sq)
    return clear.attacks(a)


def _told_move_issues(text: str, original: str, ctx: Optional[CheckContext]) -> list[str]:
    if ctx is None or not ctx.boards:
        return []
    issues = []
    played = _just_played(ctx)
    for m in _MOVED_CLAIM.finditer(text):
        if _is_hypothetical(text, original, m.start(), played=played):
            continue
        ptype = _MOVER[m["piece"].lower()]
        sq = m["to"] or m["to2"]
        if not sq:  # «3...Кf6 — конь вышел и прикрыл f7»: the square of the move written before it
            converted, _ = _to_san(original[:m.start()])
            letter = {chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}.get(ptype)
            hits = [x["san"] for x in _MOVE.finditer(converted)
                    if (x["san"][0] == letter if letter else x["san"][0] in "abcdefgh")]
            sq = re.findall(SQ, hits[-1])[-1] if hits else None
        if not sq or sq == m["target"]:
            continue
        a, t = chess.parse_square(sq), chess.parse_square(m["target"])
        standing = [b for b in ctx.boards if (pc := b.piece_at(a)) is not None and pc.piece_type == ptype]
        if not standing:
            continue
        if m["verb"].lower().startswith("прикрыл") and re.search(r"корол\w*\s+(?:на\s+)?[a-h][1-8]\s*$", m.group(0).lower()):
            continue  # «прикрыл короля e8 (от шаха)»: stood in the way of a check — not an attack on the king's square
        supports = re.match(r"(?:подкреп|поддерж|укреп|смотрит|нацелил|давит)", m["verb"].lower())
        if supports and not re.match(r"(?:смотрит|нацелил|давит)", m["verb"].lower()) and re.search(r"(?:кон|слон|ладь|ферз|корол)\w*\s+(?:на\s+)?[a-h][1-8]\s*$", m.group(0).lower()):
            continue  # «поддержал слона c4 (в атаке на f7)»: joined its attack, not defends it
        if supports and re.match(r"(?:подкреп|поддерж|укреп)", m["verb"].lower()) \
                and re.match(r"\s*(?:в|во)\s+(?:атак|борьб|наступлени|прорыв)", text[m.end():m.end() + 20]):
            continue  # «поддержал пешку e4 в атаке на f5»: joined the push, not defends the pawn
        looks = bool(supports) and bool(re.match(r"(?:смотрит|нацелил|давит)", m["verb"].lower()))
        if not any(t in b.attacks(a) or (supports and t in _xray(b, a, t, battery=not looks)) for b in standing):
            reach = "does not attack" if not _geometry_attack(ptype, a, t) else "does not reach"
            issues.append(f"a {_NAMES[ptype]} on {sq} {reach} {m['target']}")
    for rx in (_BLOCK_ACTIVE, _BLOCK_PASSIVE):
        for m in rx.finditer(text):
            if _NEGATION.search(text[max(0, m.start() - 25):m.start()]):
                continue
            ptype = next(v for k, v in _SLIDER.items() if m["pw"].lower().startswith(k))
            p, b = chess.parse_square(m["p"]), chess.parse_square(m["b"])
            if p != b and not _geometry_move(ptype, p, b):
                issues.append(f"{m['b']} is not on any line of the {_NAMES[ptype]} on {m['p']}: it blocks nothing for it")
    for m in _BY_MOVE.finditer(text):
        obj = m["obj"] or m["obj2"]
        sqs = re.findall(SQ, obj or "")
        target = sqs[-1] if sqs else _pronoun_square(text, m.start(), ctx)
        if not target:
            continue
        san, _ = _to_san(m["mv"])
        mv_m = _MOVE.search(san)
        if not mv_m:
            continue
        legal_somewhere, attacks = False, False
        for board in ctx.boards:
            try:
                move = board.parse_san(mv_m["san"])
            except ValueError:
                continue
            legal_somewhere = True
            after = board.copy(stack=False)
            after.push(move)
            if chess.parse_square(target) in after.attacks(move.to_square):
                attacks = True
                break
        if legal_somewhere and not attacks:
            issues.append(f"after {mv_m['san']} the piece that moved does not attack {target}")
    return issues


def _opening_issues(text: str) -> list[str]:
    """Moves from 1. next to an opening name must be that opening's line."""
    from src.openings_book import get_book, named_openings, _split_moves

    names = named_openings(text)
    if not names:
        return []
    converted, _ = _to_san(text)
    start = re.search(r"(?<![0-9])1\s?\.\s?(?=[KQRBNa-hO])", converted)
    if not start:
        return []
    board, played = chess.Board(), []
    for m in _MOVE.finditer(converted, start.start()):
        try:
            board.push_san(m["san"] + (m["check"] or ""))
        except ValueError:
            break
        played.append(m["san"] + (m["check"] or ""))
    if len(played) < 4:
        return []
    book = get_book()
    # A named line decides when one is mentioned: «жареная печень — это
    # итальянская партия: 1.e4 … 5.d3 d6» is about the Fried Liver, and the
    # Italian around it does not excuse the moves.
    specific = [n for n, is_named in names if is_named]
    judged = specific or [n for n, _ in names]
    wrong = None
    for name in judged:
        verdict = _fits(book, name, played)
        if verdict is None or verdict:
            return []
        wrong = wrong or name
    real = book.identify(played)
    real_name = real["name"] if real else "another line"
    return [f"the moves {' '.join(played[:10])} are not the {wrong} — they are the {real_name}"]


def _keys_along(moves) -> list[str]:
    board, keys = chess.Board(), []
    for san in moves:
        try:
            board.push_san(san)
        except ValueError:
            break
        keys.append(board.board_fen() + (" w" if board.turn else " b"))
    return keys


def _fits(book, name: str, played: list[str]) -> Optional[bool]:
    """Do *played* moves belong to the opening *name*? None when the book cannot tell.

    Positions are compared, not move orders: 1.e4 e5 2.Qh5 Nc6 3.Bc4 is the
    Scholar's Mate position too.
    """
    from src.openings_book import _split_moves

    entry = book.exact(name) or next(iter(book.by_name(name)), None)
    if entry is None:
        return None
    line = [s.rstrip("+#") for s in _split_moves(entry[2])]
    seq = [s.rstrip("+#") for s in played]
    k = min(len(line), len(seq))
    if line[:k] == seq[:k]:
        return True
    seq_keys = _keys_along(seq)
    line_keys = _keys_along(line)
    if line_keys and line_keys[-1] in seq_keys:
        return True  # the named position is reached, by another order
    # Every position of the opening's lines (the line and the lines named after
    # it: its variations, a trap's defences).
    own = re.split(r"[:,]", name)[-1].strip()
    related = set()
    for other in book.entries:
        if other[1].startswith(name) or (own and own in other[1] and own != other[1].split(":")[0].strip()
                                         or other[1] == name):
            related.update(_keys_along(_split_moves(other[2])))
    if seq_keys and seq_keys[-1] in related:
        return True  # ends inside the opening, whatever the order
    deepest = max((i for i, key in enumerate(seq_keys) if key in related), default=-1)
    if len(seq_keys) - 1 - deepest >= 3 and deepest < len(line_keys) - 1:
        return False  # leaves the opening early and goes on elsewhere
    return None


# ── Facts about the position (2026-10-02) ────────────────────────────────────
#
# What the game tester's coach wrote and the board denied: "Black is up two
# pawns" (a knight for a pawn), "your bishop on e1" (a rook), «пешка a4 висит»
# (defended), «конь связан» (not pinned). Each is decidable on the positions of
# the turn; a claim is wrong only when no position of the turn bears it out,
# and a sentence about a line of play («после», "if", a move before the claim)
# is left alone where the position after the move is not known.

_B2 = r"(?<![а-яa-z])"
_PIECE_ANY = "(?:" + "|".join(p for _, p in _RU_PIECES + _EN_PIECES) + ")"
_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def _piece_type(word: str) -> Optional[int]:
    word = word.lower().replace("ё", "е")
    for ptype, pat in _RU_PIECES + _EN_PIECES:
        if re.fullmatch(pat, word):
            return ptype
    return None


# A word or two between the square and the verb («ладья e1 при этом связана»),
# never a piece name — that would be another piece's claim.
_GAP = r"(?:(?!(?:конь|слон|ладья|ферзь|король|пешка|knight|bishop|rook|queen|king|pawn|и|а|но|или|and|but|or)(?![а-яa-z]))[а-яa-z]+\s+){0,2}?"
_HANGING = re.compile(
    _B2 + rf"(?:(?P<p1>{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<a>{SQ})(?![0-9])\s+(?:у\s+\w+\s+)?"
    rf"(?:сейчас\s+|уже\s+|просто\s+|is\s+|are\s+|now\s+|still\s+|currently\s+|completely\s+|totally\s+|совсем\s+|совершенно\s+)*{_GAP}"
    r"(?P<v>ничем\s+не\s+защищ\w+|не\s+защищ\w+|(?:ничем|никем)\s+не\s+прикрыт(?:ый|ая|ое|ые|а|о|ы)?(?![а-яё])(?!\s*[,—–-]?\s*(?:кроме|помимо|если\s+не\s+считать|только|лишь|разве|за\s+исключени\w*|но\s|пешк\w*|от\s|со\s+сторон\w*|с\s+фланг\w*|с\s+тыла|спереди|сзади|сбоку|по\s+(?:диагонал|вертикал|горизонтал|лини)\w*))|без\s+защиты|беззащит\w+|висит|повис\w*|под\s+боем|под\s+ударом|атакован\w*|защищ[ёе]н\w*|"
    r"not\s+defended|not\s+protected|undefended|unprotected|hanging|en\s+prise|loose|under\s+attack|attacked|defended|protected|covered|guarded)"
    rf"|(?P<v2>висит|повис\w*|hangs|hanging)\s+(?:is\s+)?(?:the\s+)?(?P<p2>{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<b>{SQ})(?![0-9])"
    rf"|(?P<v3>ничто\s+не\s+защищает|никто\s+не\s+защищает|nothing\s+(?:defends|protects|covers|guards))\s+"
    rf"(?:(?:the\s+)?(?:{_PIECE_ANY}\s+)?(?:на\s+|on\s+)?(?P<c>{SQ})(?![0-9])|(?P<pron>it|её|ее|его)(?![а-яa-z])))", re.IGNORECASE)
_HANGING_KIND = (("ничем не защищ", "undefended"), ("не защищ", "undefended"), ("не прикрыт", "undefended"),
                 ("без защиты", "undefended"),
                 ("беззащит", "undefended"), ("not defended", "undefended"), ("not protected", "undefended"),
                 ("undefended", "undefended"), ("unprotected", "undefended"), ("nothing", "undefended"),
                 ("ничто", "undefended"), ("никто", "undefended"), ("вис", "hanging"), ("повис", "hanging"),
                 ("hang", "hanging"), ("en prise", "hanging"), ("loose", "hanging"), ("под боем", "hanging"),
                 ("под ударом", "hanging"), ("атакован", "hanging"), ("under attack", "hanging"), ("attacked", "hanging"),
                 ("защищ", "defended"),
                 ("defended", "defended"), ("protected", "defended"), ("covered", "defended"), ("guarded", "defended"))


def _hanging_kind(verb: str) -> str:
    verb = re.sub(r"\s+", " ", verb.lower())
    for key, kind in _HANGING_KIND:
        if key in verb:
            return kind
    return "hanging"


_EXCEPT = re.compile(r"\s*,?\s*(?:кроме|помимо|except|other\s+than|apart\s+from|but\s+(?:the|your|my|a))(?![а-яa-z])", re.IGNORECASE)


# «Ладья c1 забирает ферзя», «брать пешкой b7xc6» with no rook on c1 and no pawn on b7 (production lesson
# answers, 07.10): a piece named by the square it stands on, which no position of the turn — the board, a
# tool's position, a game, a line the answer wrote, the student's idea — has there.
_GHOST = re.compile(
    # «ферзь b6 у тебя висит» (prod 23.10): a word or two about whose it is, or when, between the square and the verb
    _B2 + rf"(?:(?P<w4>конь|слон|ладья|ферзь|король|пешка)\s+(?P<sq4>{SQ})(?![0-9])\s+(?:сама\s+|сам\s+|только\s+что\s+|уже\s+)?"
    r"(?:взял[аи]?|побил[аи]?|съел[аи]?|забрал[аи]?|срубил[аи]?)(?![а-яa-z])"
    rf"|(?P<w5>конь|слон|ладья|ферзь|король|пешка)\s+на\s+(?P<sq5>{SQ})(?![0-9])\s+(?:сейчас\s+|уже\s+|по-прежнему\s+)?"
    r"(?:стоит|висит|связан\w*|защищает|прикрывает|держит)(?![а-яa-z])"
    rf"|(?P<w>конь|слон|ладья|ферзь|король|пешка)\s+(?P<sq>{SQ})(?![0-9])\s+"
    r"(?:(?:сейчас|уже|сама|сам|теперь|пока|тоже|по-прежнему|всё\s+ещё|все\s+еще|у\s+(?:тебя|вас|меня|него|не[её]|них)|"
    r"тво[йяёе]\w*|ваш\w*|мо[йяёе]\w*)\s+){0,2}"
    r"(?:бь[её]т|забирает|берёт|берет|защищает|атакует|нападает|держит|стоит|висит|давит|смотрит|прикрывает|связан\w*)(?![а-яa-z])"
    rf"|(?P<w2>{_PIECE_ANY})\s+(?P<sq2>{SQ})\s?[x×:]\s?{SQ}"
    # «свою e3-пешку» with a bishop on e3 (production 08.10)
    rf"|(?<![a-z0-9])(?P<sq3>{SQ})-(?P<w3>{_PIECE_ANY}))", re.IGNORECASE)


def _ghost_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None or ctx.current.board_fen() == chess.STARTING_BOARD_FEN:
        return []  # an opening talked about from the first move: its positions are not all on the boards
    if re.search(r"(?<![а-яa-z])(?:партии|партия|партию|game|played)(?![а-яa-z])", text):
        return []  # a game named in the words may be one the turn does not have
    for m in _GHOST.finditer(text):
        word, sq_name = next(((m[w], m[q]) for w, q in (("w", "sq"), ("w2", "sq2"), ("w3", "sq3"), ("w4", "sq4"), ("w5", "sq5"))
                              if m[w]), (None, None))
        if word is None:
            continue
        if _NEGATION.search(text[max(0, m.start() - 12):m.start()]):
            continue
        ptype = _piece_type(word)
        if ptype is None:
            continue
        sq = chess.parse_square(sq_name.lower())
        if any((pc := b.piece_at(sq)) is not None and pc.piece_type == ptype for b in _turn_boards(ctx)):
            continue
        there = ctx.current.piece_at(sq)
        here = f"there is a {_NAMES[there.piece_type]} there" if there else "nothing stands there"
        return [f"there is no {_NAMES[ptype]} on {sq_name.lower()} in this position ({here})"]
    return []


# «давит на коня c6», «забираешь коня на e2», «напал на коня f3 и ещё на пешку e2», «и на слона на c4 тоже
# нападает», "attacks the knight on c6": the OBJECT of an attack, a capture, a threat or a defence, named by its
# kind and square. Two facts of the board about it (prod 19.10 and Alexander's phone 24.10):
#   * a piece of that kind stands there on a board of the turn (the start position does not count — every turn
#     carries it for opening lines, and «пешку на e2» found its pawn there);
#   * for an attack or a threat about the board as it is: SOMETHING attacks that square — whoever the subject is
#     (a pronoun, the piece of the sentence before, nobody): «напал на слона c4» with no black piece touching c4.
# Russian object cases (коня, ладью, пешке) never name the actor, so the verb may stand anywhere in the clause;
# an English noun is read only right after the verb. «поставить коня на c6» is a destination: not these verbs.
_RU_OBJ = r"коня|слона|ладью|ферзя|короля|пешку|коню|слону|ладье|ферзю|королю|пешке"
_OBJ_ADJ = (r"(?:(?:сво\w+|его|их|е[её]|тво\w+|ваш\w+|мо\w+|ч[её]рн\w+|бел\w+|вражеск\w+|неприятельск\w+|"
            r"незащищ[её]нн\w+|беззащитн\w+|связанн\w+|лишн\w+|этого|эту|того|ту|этому|этой|тому|той|одного|одну|"
            r"the|your|my|his|her|their|that|this|black|white|enemy|loose|hanging|undefended|unprotected)\s+){0,2}")
_RU_OBJECT = re.compile(_B2 + r"(?:(?:на|по|за)\s+)?" + _OBJ_ADJ + rf"(?P<w>{_RU_OBJ})\s+(?:на\s+)?(?P<sq>{SQ})(?![0-9])")
_EN_OBJECT = re.compile(
    r"(?<![a-z])(?:attack\w*|hit\w*|tak\w+|captur\w+|win\w*|target\w*|threaten\w*|pin\w*|fork\w*|grab\w*|defend\w*|"
    r"protect\w*|guard\w*)\s+" + _OBJ_ADJ + rf"(?P<w>knight|bishop|rook|queen|king|pawn)\s+on\s+(?P<sq>{SQ})(?![0-9])",
    re.IGNORECASE)
# The verbs a clause needs for its objects to be claims: of attack/threat (checked for an attacker), of capture,
# defence, loss or exchange (checked for the piece only). Finite forms: «напади», «атакуй», «напасть» are plans.
_ATTACK_FINITE = (r"бь[её]т|бьют|бь[её]шь|бь[её]те|напал\w*|напада(?:ет|ют|ешь|ете)|напад[её]т|нападут|атаку(?:ет|ют|ешь|ете)|"
                  r"атаковал\w*|угрожа(?:ет|ют|ешь|ете)|угроз\w+|давит|давят|давишь|нацел\w+|"
                  r"attacks|attacking|threatens|threatening|hits|hitting|targets|targeting")
_OTHER_FINITE = (r"забира\w+|забер[её]\w*|бер[её]\w+|взять|взял\w*|съесть|съеда\w+|съел\w*|держит|держишь|держат|"
                 r"защища\w+|прикрыва\w+|связыва\w+|связал\w*|связать|выигрыва\w+|выиграть|теря\w+|потеря\w+|"
                 r"отда[её]\w+|отдать|разменя\w+|меня\w+|takes?|taking|captur\w+|wins?|defends?|protects?|guards?")
_CAPTURE_VERB = re.compile(_B2 + r"(?:забира\w+|забер[её]\w*|бер[её]\w+|взять|взял\w*|съесть|съеда\w+|съел\w*|выигрыва\w+|выиграть|takes?|taking|captur\w+|wins?)" + _E, re.IGNORECASE)
_ATTACK_IN_CLAUSE = re.compile(_B2 + "(?:" + _ATTACK_FINITE + ")" + _E, re.IGNORECASE)
_OBJECT_VERB_IN_CLAUSE = re.compile(_B2 + "(?:" + _ATTACK_FINITE + "|" + _OTHER_FINITE + ")" + _E, re.IGNORECASE)
_CLAUSE_SPLIT = re.compile(r"[;—–]|,\s*(?:а|но|однако|зато|хотя|поэтому|так\s+что|while|but|so|yet)\s", re.IGNORECASE)


def _clauses(text: str) -> list[str]:
    return [c for c in _CLAUSE_SPLIT.split(text) if c and c.strip()]


# «Конь забирает пешку h7 с шахом, и это вилка: он бьёт короля f8 и коня f6»: from the clause that tells a move or a
# capture on, the sentence is about the position after it — those clauses are not judged against the board as it is.
_NARRATED_MOVE = re.compile(
    _B2 + r"(?:забира\w+|забер[её]\w*|бер[её]т|бер[её]шь|берут|взял\w*|съеда\w+|съел\w*|ид[её]т|пойд[её]т|прыга\w+|прыгн\w+|"
    r"вста[её]т|встан\w+|перевод\w+|отступ\w+|уход\w+|уйд[её]т|играет|сыграет|ходит|сходит|рокиру\w+|"
    r"takes|captures|goes|jumps|lands|moves|retreats|castles)" + _E, re.IGNORECASE)


def _clauses_about_now(text: str) -> list[str]:
    out = []
    for clause in _clauses(text):
        if _NARRATED_MOVE.search(clause):
            break
        out.append(clause)
    return out


def _turn_boards(ctx: CheckContext) -> list:
    """The boards of the turn a named piece may stand on — without the bare start position unless it is
    the position in front of the student."""
    if ctx.current is not None and ctx.current.board_fen() == chess.STARTING_BOARD_FEN:
        return ctx.boards
    return [b for b in ctx.boards if b.board_fen() != chess.STARTING_BOARD_FEN]


def _objects(clause: str):
    for m in _RU_OBJECT.finditer(clause):
        yield m
    for m in _EN_OBJECT.finditer(clause):
        yield m


# A clause that denies («никто не атакует», «не защищает») claims nothing; a clause whose SUBJECT piece is not on
# the board («удар конём на f7: конь на f7 бьёт ферзя d8», "your rook on g1 hits the queen on h4") tells a line
# the turn may not have — its objects are judged elsewhere, not against this board.
_CLAUSE_NEG = re.compile(r"(?<![а-яa-z])(?:не|нет|ни|никто|ничто|никем|ничем|нельзя|not|n't|no|nobody|nothing|never|"
                         r"neither)(?![а-яa-z])", re.IGNORECASE)
_EN_OBJECT_BEFORE = re.compile(
    r"(?:attack\w*|hit\w*|tak\w+|captur\w+|win\w*|target\w*|threaten\w*|pin\w*|fork\w*|grab\w*|defend\w*|protect\w*|"
    r"guard\w*)\s+(?:(?:the|your|my|his|her|their|that|this|black|white|enemy|loose|hanging|undefended|unprotected)\s+){0,2}$",
    re.IGNORECASE)
_CLAUSE_SUBJECT = re.compile(
    _B2 + rf"(?:(?P<ru>конь|слон|ладья|ферзь|король|пешка)\s+(?:на\s+)?(?P<a>{SQ})"
    rf"|(?P<en>knight|bishop|rook|queen|king|pawn)\s+(?:on|at)\s+(?P<b>{SQ}))(?![0-9])", re.IGNORECASE)


def _clause_judged_here(clause: str, ctx: CheckContext) -> bool:
    if _CLAUSE_NEG.search(clause):
        return False
    for m in _CLAUSE_SUBJECT.finditer(clause):
        if m["en"] and _EN_OBJECT_BEFORE.search(clause[: m.start()]):
            continue  # "attacks the knight on c6": the object, not the subject
        ptype = _piece_type((m["ru"] or m["en"]).lower())
        sq = chess.parse_square((m["a"] or m["b"]).lower())
        piece = ctx.current.piece_at(sq) if ctx.current is not None else None
        if piece is None or (ptype is not None and piece.piece_type != ptype):
            return False
    return True


def _object_ghost_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None or ctx.current.board_fen() == chess.STARTING_BOARD_FEN:
        return []
    if re.search(r"(?<![а-яa-z])(?:партии|партия|партию|game|played)(?![а-яa-z])", text):
        return []
    boards = _turn_boards(ctx)
    for clause in _clauses_about_now(text):
        if not _OBJECT_VERB_IN_CLAUSE.search(clause) or not _clause_judged_here(clause, ctx):
            continue
        for m in _objects(clause):
            if _NEGATION.search(clause[max(0, m.start() - 12):m.start()]):
                continue
            ptype = _piece_type(m["w"])
            if ptype is None:
                continue
            sq = chess.parse_square(m["sq"].lower())
            if any((pc := b.piece_at(sq)) is not None and pc.piece_type == ptype for b in boards):
                continue
            there = ctx.current.piece_at(sq)
            if there is not None and there.piece_type in _actors(clause):
                continue  # «конь забирает пешку h7» with the knight now on h7: the capture just made, told
            if there is None and _CAPTURE_VERB.search(clause) and not _ATTACK_IN_CLAUSE.search(clause):
                continue  # «конь забирает пешку h7» with h7 empty: a capture of a line, not a claim about now
            here = f"a {_NAMES[there.piece_type]} stands there" if there else "the square is empty"
            return [f"there is no {_NAMES[ptype]} on {m['sq'].lower()} in this position ({here})"]
    return []


_ACTOR = re.compile(_B2 + r"(?P<p>конь|кон[её]м|слон|слоном|ладья|ладь[её]й|ферзь|ферз[её]м|король|корол[её]м|пешка|пешкой|"
                    r"knight|bishop|rook|queen|king|pawn)" + _E, re.IGNORECASE)


def _actors(clause: str) -> set:
    """The kinds of piece named as acting in *clause* (nominative or instrumental; an English noun not right
    after an object verb)."""
    out = set()
    for m in _ACTOR.finditer(clause):
        if m["p"].isascii() and _EN_OBJECT_BEFORE.search(clause[: m.start()]):
            continue
        ptype = _piece_type(m["p"].lower())
        if ptype is not None:
            out.add(ptype)
    return out


def _attacked_after_asked_move(ctx: CheckContext, sq: int, color: bool) -> bool:
    """The piece of *color* on *sq* is attacked after a move the question names, played by the other side: the answer
    to «А если сначала b3?» tells what b3 does — «ты нападаешь на слона c4» — on the board the idea leads to, as the
    retreat rule reads «он уйдёт на a6, b5…» there (src/answer_check_rules._chase_boards)."""
    if not ctx.question:
        return False
    from src.answer_check_rules import _MOVE_LOW, _parse_lowered

    mover = ctx.current.copy(stack=False)
    mover.turn = not color
    mover.ep_square = None
    for m in _MOVE_LOW.finditer(ctx.question):
        try:
            move = _parse_lowered(mover, m.group(0))
        except Exception:  # noqa: BLE001
            move = None
        if move is None:
            continue
        after = mover.copy(stack=False)
        after.push(move)
        if after.color_at(sq) == color and after.attackers(not color, sq):
            return True
    return False


def _unattacked_object_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    if _DENIES.search(text):
        return []
    for clause in _clauses_about_now(text):
        if not _ATTACK_IN_CLAUSE.search(clause) or not _clause_judged_here(clause, ctx):
            continue
        for m in _objects(clause):
            if _NEGATION.search(clause[max(0, m.start() - 12):m.start()]):
                continue
            at = text.find(clause)
            upto = (at if at >= 0 else 0) + m.start()
            if _is_hypothetical(text, original, upto):
                continue  # «после Nb5 конь нападёт на пешку c7»: a line, judged on the derived boards elsewhere
            if _SAN_IN_TEXT.search(_to_san(original[:upto])[0]):
                continue  # «cxd4: пешка c5 … нападает на ферзя c3»: after the move written before it
            ptype = _piece_type(m["w"])
            if ptype is None:
                continue
            sq = chess.parse_square(m["sq"].lower())
            piece = ctx.current.piece_at(sq)
            if piece is None or piece.piece_type != ptype:
                continue  # a ghost: _object_ghost_issues says so
            if ctx.current.attackers(not piece.color, sq):
                continue
            if _attacked_after_asked_move(ctx, sq, piece.color):
                continue  # «А если b3?» — «ты нападаешь на слона c4»: the asked move's attack (row d1-b3, review 30.10)
            if piece.piece_type == chess.PAWN and any(
                    ctx.current.is_en_passant(mv) and mv.to_square + (-8 if ctx.current.turn == chess.WHITE else 8) == sq
                    for mv in ctx.current.legal_moves):
                continue  # the pawn that just passed: taken en passant
            return [f"the {_NAMES[ptype]} on {m['sq'].lower()} is not attacked by anything in this position"]
    return []


# «решение: Qf3+ Kg1 и Qh1#», «ферзь на h1 ставит мат», "the solution is Qh1#": a move given as the puzzle's solution
# or its mate must be the puzzle's own. Only when the sentence is about the solution or claims the mate — a hint or a
# «what if» is left alone.
_SOLUTION_WORD = re.compile(r"(?<![а-яa-z])(?:решени[еяю]|ответ|solution|answer)(?![а-яa-z])", re.IGNORECASE)
# «ферзь на h1 ставит мат», «конь h3 — мат», "the queen on h1 mates": the mating move in words.
_PIECE_SQUARE_MATES = re.compile(
    r"(?<![а-яa-z])(?P<piece>конь|кон[её]м|слон|слоном|ладья|ладь[её]й|ферзь|ферз[её]м|король|корол[её]м|пешка|пешкой|"
    r"knight|bishop|rook|queen|king|pawn)\s+(?:на\s+|on\s+|to\s+)?(?P<sq>[a-h][1-8])(?![0-9])\s*(?:[—–-]|,)?\s*"
    r"(?:и\s+)?(?:это\s+)?(?:ставит\s+мат|да[её]т\s+мат|объявляет\s+мат|мат(?![а-я])|mates|is\s+mate|gives\s+mate|checkmates?)",
    re.IGNORECASE)
_SAN_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?")


def _norm_san(san: str) -> str:
    return san.replace("+", "").replace("#", "").replace("x", "")


def _solution_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    solution = [s for s in (ctx.puzzle_solution or []) if s]
    if not solution:
        return []
    converted, _ = _to_san(original)
    moves = [m.group(0) for m in _SAN_IN_TEXT.finditer(converted)]
    if not moves:
        return []
    allowed = {_norm_san(s) for s in solution}
    if _DENIES.search(text) or _NEGATION.search(text[:40]):
        return []
    # (a) the mating move: «X#», «X — мат», «X ставит мат», «ферзь на h1 ставит мат»
    mates = [m.group("san") for m in _MATE_WORD.finditer(converted)] + [m[:-1] for m in moves if m.endswith("#")]
    for m in _PIECE_SQUARE_MATES.finditer(text):
        ptype = _piece_type(m["piece"])
        if ptype is not None:
            mates.append(chess.piece_symbol(ptype).upper().replace("P", "") + m["sq"].lower())
    last = _norm_san(solution[-1])
    for san in mates:
        if _norm_san(san) != last and _norm_san(san) not in allowed:
            return [f"the puzzle's solution ends with {solution[-1]}, not {san}: say the puzzle's own line"]
    # (b) «решение: …» — every move of the line must be the puzzle's
    if _SOLUTION_WORD.search(text) and not _is_hypothetical(text, original, 0, whole=True):
        wrong = [m for m in moves if _norm_san(m) not in allowed]
        if wrong:
            return [f"the puzzle's solution is {' '.join(solution)}; {wrong[0]} is not in it"]
    return []


# «e5xd5», «e5:d5»: a capture written from square to square — the piece standing on the first square must
# be able to take that way (a pawn takes one square diagonally forward: «обычным взятием — e5xd5» with
# the pawns on e5 and d5 side by side, production 19.10).
_CAPTURE_CHAIN = re.compile(rf"(?<![A-Za-z0-9])(?P<a>{SQ})\s?[x×:]\s?(?P<b>{SQ})(?![0-9])")


def _capture_chain_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    for m in _CAPTURE_CHAIN.finditer(text):
        a, b = chess.parse_square(m["a"].lower()), chess.parse_square(m["b"].lower())
        standing = [bd for bd in ctx.boards if bd.piece_at(a) is not None]
        if not standing:
            continue  # a plan on a position the turn does not have: not judged
        ok = False
        for bd in standing:
            piece = bd.piece_at(a)
            if piece.piece_type == chess.PAWN:
                forward = 1 if piece.color == chess.WHITE else -1
                if (abs(chess.square_file(a) - chess.square_file(b)) == 1
                        and chess.square_rank(b) - chess.square_rank(a) == forward):
                    ok = True
            elif _geometry_move(piece.piece_type, a, b):
                ok = True
        if not ok:
            piece = ctx.current.piece_at(a) or standing[0].piece_at(a)
            what = _NAMES[piece.piece_type]
            why = " (a pawn takes one square diagonally forward)" if piece.piece_type == chess.PAWN else ""
            issues.append(f"{m['a']}x{m['b']}: a {what} on {m['a'].lower()} cannot capture on {m['b'].lower()}{why}")
    return issues


def _hanging_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []  # no real position of the turn to judge by
    issues = []
    for m in _HANGING.finditer(text):
        sq_name = m["a"] or m["b"] or m["c"]
        if not sq_name and m.groupdict().get("pron"):
            sq_name = _pronoun_square(text, m.start(), ctx)  # "the pawn on a4 is hanging and nothing defends it"
            if not sq_name:
                continue
        ctx._object = sq_name
        verb = m["v"] or m["v2"] or m["v3"]
        kind = _hanging_kind(verb)
        if kind == "undefended" and _EXCEPT.match(text, m.end()):
            continue  # «никто не защищает, кроме ферзя», "nothing defends f2 except the king": a defender is named
        if "прикрыт" in verb.lower() and (re.match(r"(?:корол|king)", (m["p1"] or "").lower())
                                          or re.search(r"между|смотрит|лини[яюи]|вертикал|диагонал|горизонтал|рентген", text, re.I)):
            continue  # «король ничем не прикрыт» is about its shelter, not about pieces next to it
        if kind == "hanging" and re.match(r"\s+(?:в\s+воздухе|in\s+the\s+air|без\s+дела)", text[m.end():]):
            continue  # «ладья висит в воздухе и ничего не делает»: idle, not en prise (replay, 2026-10-05)
        if kind != "undefended" and _NEGATION.search(text[: m.start(verb and ("v" if m["v"] else "v2" if m["v2"] else "v3"))]):
            continue  # «не висит», "is not hanging"
        if _is_hypothetical(text, original, m.start()):
            continue
        sq = chess.parse_square(sq_name)
        named = _piece_type(m["p1"] or m["p2"] or "") if (m["p1"] or m["p2"]) else None
        seen = False
        for board in ctx.boards:
            piece = board.piece_at(sq)
            if piece is None or (named is not None and piece.piece_type != named):
                continue  # «Слон на c4 ничем не защищён» is not about the rook a written Rxc4 put there
            seen = True
            defenders = board.attackers(piece.color, sq)
            attackers = board.attackers(not piece.color, sq)
            if kind == "hanging" and attackers:
                break  # «висит» is said of an attacked piece, defended or not
            if kind == "undefended" and not defenders:
                break
            if kind == "defended" and defenders:
                break
        else:
            if seen and ctx.current is not None and (piece := ctx.current.piece_at(sq)) is not None:
                defenders = [chess.square_name(d) for d in ctx.current.attackers(piece.color, sq)]
                name = _NAMES[piece.piece_type]
                if kind == "defended":
                    issues.append(f"the {name} on {sq_name} is not defended by anything")
                elif kind == "undefended":
                    issues.append(f"the {name} on {sq_name} is defended (by {', '.join(defenders)}), not undefended")
                else:
                    issues.append(f"the {name} on {sq_name} is not attacked, so it is not hanging")
    return issues


def _pinned_any(board: chess.Board, sq: int) -> bool:
    """Pinned to the king, or to a more valuable piece behind it on the line."""
    piece = board.piece_at(sq)
    if piece is None:
        return False
    if board.is_pinned(piece.color, sq):
        return True
    for a in board.attackers(not piece.color, sq):
        attacker = board.piece_at(a)
        if attacker is None or attacker.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        df = (chess.square_file(sq) > chess.square_file(a)) - (chess.square_file(sq) < chess.square_file(a))
        dr = (chess.square_rank(sq) > chess.square_rank(a)) - (chess.square_rank(sq) < chess.square_rank(a))
        f, r = chess.square_file(sq) + df, chess.square_rank(sq) + dr
        while 0 <= f < 8 and 0 <= r < 8:
            behind = board.piece_at(chess.square(f, r))
            if behind is not None:
                if behind.color == piece.color and (behind.piece_type == chess.KING
                                                    or _VALUE[behind.piece_type] > _VALUE[piece.piece_type]):
                    return True
                break
            f, r = f + df, r + dr
    return False


_PINNED = re.compile(
    _B2 + rf"(?:(?P<p1>{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<a>{SQ})(?![0-9])\s+(?:is\s+|are\s+|сейчас\s+|уже\s+|now\s+)*{_GAP}"
    r"(?P<v>связан\w*|под\s+связкой|прикован\w*|pinned)"
    rf"|(?P<v2>связывает|связывают|связал\w*|pins|pinning)\s+(?:the\s+|your\s+|тво\w+\s+|ваш\w+\s+|ч[её]рн\w+\s+|бел\w+\s+|black\s+|white\s+)?"
    rf"(?:{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<b>{SQ})(?![0-9]))", re.IGNORECASE)


def _pin_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    for m in _PINNED.finditer(text):
        sq_name = m["a"] or m["b"]
        if _NEGATION.search(text[: m.start("v" if m["v"] else "v2")]):
            continue  # «не связан», "is not pinned"
        if _is_hypothetical(text, original, m.start()):
            continue
        sq = chess.parse_square(sq_name)
        if ctx.current is not None and ctx.current.piece_at(sq) is not None:
            ctx._subject = (ctx.current.piece_at(sq).piece_type, sq_name)
        boards = [b for b in ctx.boards if b.piece_at(sq) is not None]
        if boards and not any(_pinned_any(b, sq) for b in boards):
            piece = (ctx.current.piece_at(sq) if ctx.current is not None else None) or boards[0].piece_at(sq)
            issues.append(f"the {_NAMES[piece.piece_type]} on {sq_name} is not pinned")
    return issues


_SIDE = (r"(?P<side>белые|белых|ч[её]рные|ч[её]рных|white|black|ты|тебя|вы|вас|you|соперник|соперника|противник|"
         r"противника|opponent|engine|движок|я|меня|me|i|них|него|не[её]|они|им|ему|ей|them|they|he|she)")
_SIDE_NAMED = re.compile(r"(?<![а-яa-z])(белые|белых|белым|ч[её]рные|ч[её]рных|ч[её]рным|white|black|ты|тебя|тебе|вы|вас|вам|you|"
                         r"соперник|соперника|сопернику|противник|противника|opponent|engine|движок|я|меня|мне|me|i)(?![а-яa-z])",
                         re.IGNORECASE)
_PRONOUN_SIDES = {"них", "него", "нее", "они", "им", "ему", "ей", "them", "they", "he", "she"}
_UNIT = (r"(?P<unit>пешк\w*|pawns?|фигур\w*|pieces?|кон[ьяе]м?|knights?|слон\w*|bishops?|ладь\w+|rooks?|"
         r"ферз\w*|queens?|качеств\w*|exchange)")
_NUM = r"(?P<n>одн[ауи]|одной|одним|одна|две|двух|двумя|пар[ау]|три|тр[её]х|четыре|an?\s+couple\s+of|couple\s+of|a|an|one|two|three|four|\d)"
_MATERIAL = [re.compile(_B2 + rx, re.IGNORECASE) for rx in (
    # «чёрные на две пешки впереди», «у белых на пешку больше», «ты фигурой меньше»
    rf"(?:у\s+)?{_SIDE}\s+(?:уже\s+|сейчас\s+|по\s+материалу\s+)?(?:на\s+)?(?:{_NUM}\s+)?{_UNIT}\s+"
    r"(?P<dir>больше|впереди|меньше|позади)",
    # «у белых лишняя пешка», «чёрные без фигуры», «чёрные … остаются с лишней ладьёй»
    rf"(?:у\s+)?{_SIDE}\s+(?:[^,.;:!?]{{0,40}}?\s)?(?:с\s+)?(?P<dir>лишн\w+|без)\s+(?:{_NUM}\s+)?{_UNIT}",
    # "black is up two pawns", "you are down a piece"
    rf"{_SIDE}(?:\s+(?:is|are|am)|'s|'re|'m)?\s*(?:already\s+|now\s+|simply\s+|currently\s+)?"
    rf"(?P<dir>up|down|ahead\s+by|behind\s+by)\s+(?:{_NUM}\s+)?{_UNIT}",
    # "black is two pawns up", "white is a piece down"
    rf"{_SIDE}(?:\s+(?:is|are|am)|'s|'re|'m)?\s*(?:already\s+|now\s+)?(?:{_NUM}\s+)?{_UNIT}\s+(?P<dir>up|down|ahead|behind)",
    # "white has an extra pawn"
    rf"{_SIDE}(?:\s+(?:has|have)|'s|'ve)\s+(?:an?\s+)?(?P<dir>extra|spare)\s+{_UNIT}",
)]
_MATERIAL_EQUAL = re.compile(
    _B2 + r"(?:материал\w*\s+(?:пока\s+|сейчас\s+)?рав\w+|равн\w+\s+материал\w*|материальн\w+\s+равенств\w+|"
    # «лишней пешки ни у кого нет» (prod 29.10, can-kg-accept): equality said as a denial of an extra pawn
    r"лишн\w+\s+(?:пешк|фигур)\w*\s+ни\s+у\s+кого\s+нет|ни\s+у\s+кого\s+нет\s+лишн\w+\s+(?:пешк|фигур)\w*|"
    r"material\s+is\s+(?:still\s+)?(?:equal|even|level|balanced)|(?:equal|even|level)\s+material)", re.IGNORECASE)
_MORE = {"больше", "впереди", "лишн", "up", "ahead", "extra", "spare"}


def _num(word: Optional[str]) -> int:
    if not word:
        return 1
    word = word.lower().replace("ё", "е")
    if word.isdigit():
        return int(word)
    if word.startswith(("дв", "two", "пар")) or "couple" in word:
        return 2
    if word.startswith(("тр", "three")):
        return 3
    if word.startswith(("четыр", "four")):
        return 4
    return 1


def _unit(word: str) -> tuple[str, int]:
    """(kind, points): pawn / minor / knight / bishop / rook / queen / exchange."""
    w = word.lower().replace("ё", "е")
    if w.startswith(("пешк", "pawn")):
        return "pawn", 1
    if w.startswith(("фигур", "piece")):
        return "minor", 3
    if w.startswith(("кон", "knight")):
        return "knight", 3
    if w.startswith(("слон", "bishop")):
        return "bishop", 3
    if w.startswith(("лад", "rook")):
        return "rook", 5
    if w.startswith(("ферз", "queen")):
        return "queen", 9
    return "exchange", 2


def _side_color(word: str, ctx: CheckContext, before: str = "") -> Optional[bool]:
    """The colour a side word names. «у них», "they": the side named before it.
    «ты», "you" outside a game: the side to move — the coach talks to the
    student as the side to move (prompt v11)."""
    w = word.lower().replace("ё", "е")
    if w in _PRONOUN_SIDES:
        named = _SIDE_NAMED.findall(before)
        if not named:
            return None
        w = named[-1].lower().replace("ё", "е")
    if w.startswith(("бел", "white")):
        return chess.WHITE
    if w.startswith(("черн", "black")):
        return chess.BLACK
    student = ctx.student_color
    if student is None:
        if ctx.current is None:
            return None
        student = ctx.current.turn
    if w in ("ты", "тебя", "тебе", "вы", "вас", "вам", "you"):
        return student
    return not student  # соперник, движок, я (the coach plays the engine's side)


def _counts(board: chess.Board, color: bool) -> dict:
    out = {pt: len(board.pieces(pt, color)) for pt in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)}
    out["minors"] = out[chess.KNIGHT] + out[chess.BISHOP]
    out["nonpawn"] = sum(out[pt] * _VALUE[pt] for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN))
    return out


def _material_holds(board: chess.Board, color: bool, kind: str, points: int, n: int, more: bool,
                    balance: bool = True) -> bool:
    """*balance*: «на пешку больше», "up a pawn" — the whole balance; otherwise
    («лишняя пешка», "an extra knight") only that count."""
    mine, theirs = _counts(board, color), _counts(board, not color)
    sign = 1 if more else -1
    dp = (mine[chess.PAWN] - theirs[chess.PAWN]) * sign
    dnp = (mine["nonpawn"] - theirs["nonpawn"]) * sign
    if not balance:
        if kind == "pawn":
            return dp >= n
        if kind == "minor":
            return (mine["minors"] - theirs["minors"]) * sign >= n
        if kind == "exchange":
            return (mine[chess.ROOK] - theirs[chess.ROOK]) * sign >= 1 and (mine["minors"] - theirs["minors"]) * sign <= -1
        pt = {"knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK, "queen": chess.QUEEN}[kind]
        return (mine[pt] - theirs[pt]) * sign >= n
    if kind == "pawn":
        return dp == n and abs(dnp) <= 1
    if kind == "exchange":
        return (mine[chess.ROOK] - theirs[chess.ROOK]) * sign == 1 and (mine["minors"] - theirs["minors"]) * sign == -1 \
            and abs(dp) <= 2
    want = points * n
    if kind == "knight" and (mine[chess.KNIGHT] - theirs[chess.KNIGHT]) * sign < 1:
        return False
    if kind == "bishop" and (mine[chess.BISHOP] - theirs[chess.BISHOP]) * sign < 1:
        return False
    if kind == "rook" and (mine[chess.ROOK] - theirs[chess.ROOK]) * sign < 1:
        return False
    if kind == "queen" and (mine[chess.QUEEN] - theirs[chess.QUEEN]) * sign < 1:
        return False
    return abs(dnp - want) <= 1 and abs(dp) <= 2


def _imbalance(board: chess.Board) -> str:
    """«White: +pawn; Black: +knight» — what each side has that the other does not."""
    w, b = _counts(board, chess.WHITE), _counts(board, chess.BLACK)
    extra = {chess.WHITE: [], chess.BLACK: []}
    for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
        d = w[pt] - b[pt]
        if d:
            extra[chess.WHITE if d > 0 else chess.BLACK].append(f"{abs(d)} {_NAMES[pt]}{'s' if abs(d) > 1 else ''}")
    if not extra[chess.WHITE] and not extra[chess.BLACK]:
        return "material is equal"
    parts = [f"{'White' if c else 'Black'} has an extra {', '.join(extra[c])}" for c in (chess.WHITE, chess.BLACK) if extra[c]]
    return "; ".join(parts)


# «у белых лучше», «перевес у чёрных», «ты выигрываешь», «позиция равная», "White is
# winning", "the position is balanced": a verdict the engine contradicts (2026-10-05).
_EVAL_WORDS = (r"(?P<w>лучше|хуже|перевес\w*|преимуществ\w*|выигрыва\w+|выигран\w*|выиграл\w*|проигрыва\w+|проигран\w*|"
               r"проиграл\w*|better|worse|winning|won|lost|losing|ahead|behind|crushing|dominating)")
_EVAL_CLAIMS = [
    re.compile(_B2 + rf"(?:у\s+)?{_SIDE}\s+(?:(?!не\s|not\s)[а-яa-z']+\s+){{0,3}}?{_EVAL_WORDS}(?![а-яa-z])", re.IGNORECASE),
    re.compile(_B2 + rf"(?P<w>перевес\w*|преимуществ\w*|advantage)\s+(?:сейчас\s+|явно\s+|уже\s+|clearly\s+)?"
               rf"(?:у|на\s+стороне|is\s+with|belongs\s+to|is)\s+{_SIDE}(?![а-яa-z])", re.IGNORECASE),
    re.compile(_B2 + r"(?:позици\w+|position|game)\s+(?:is\s+|сейчас\s+|пока\s+|примерно\s+|roughly\s+|about\s+|basically\s+|"
               r"still\s+|в\s+целом\s+|here\s+){0,3}(?P<eq>равн\w+|равенств\w*|сбалансирован\w+|equal|balanced|level|even)(?![а-яa-z])",
               re.IGNORECASE),
]


def _fmt_eval(ev: float) -> str:
    if abs(ev) >= 99.5:
        return "a forced mate for " + ("White" if ev > 0 else "Black")
    return f"{ev:+.1f} for White"


def _eval_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.engine_eval is None or ctx.current is None:
        return []
    ev = ctx.engine_eval
    issues = []
    for rx in _EVAL_CLAIMS:
        for m in rx.finditer(text):
            if _is_hypothetical(text, original, m.start()):
                continue
            gd = m.groupdict()
            key = "eq" if gd.get("eq") else "w"
            if _NEGATION.search(text[max(0, m.start() - 20): m.start(key)]):
                continue  # «не лучше», "not winning"
            if gd.get("eq"):
                if abs(ev) >= 1.5:
                    issues.append(f"the engine evaluates the position at {_fmt_eval(ev)} — not equal")
                continue
            color = _side_color(m["side"], ctx, text[: m.start()])
            if color is None:
                continue
            e = ev if color == chess.WHITE else -ev
            name = "White" if color == chess.WHITE else "Black"
            w = gd["w"].lower().replace("ё", "е")
            if w.startswith(("лучше", "перевес", "преимуществ", "better", "ahead", "advantage")):
                if e <= -0.6:
                    issues.append(f"the engine evaluates the position at {_fmt_eval(ev)}: {name} is worse, not better")
            elif w.startswith(("хуже", "worse", "behind")):
                if e >= 0.6:
                    issues.append(f"the engine evaluates the position at {_fmt_eval(ev)}: {name} is better, not worse")
            elif w.startswith(("выигр", "winning", "won", "crushing", "dominating")):
                if e < 1.0:
                    issues.append(f"the engine evaluates the position at {_fmt_eval(ev)}: {name} is not winning")
            elif w.startswith(("проигр", "lost", "losing")):
                if e > -1.0:
                    issues.append(f"the engine evaluates the position at {_fmt_eval(ev)}: {name} is not lost")
    return issues


_FUTURE_FILL = _FUTURE_VERB  # «останешься с лишней пешкой»: the same future forms (src/claim_scope.py)


# «был», "had": the sentence tells the material of a past moment, not of the board now.
_PAST_BE = re.compile(_B2 + r"(?:был|была|было|были|had|was|were)" + _E, re.IGNORECASE)


def _is_past(ctx: CheckContext, board: chess.Board) -> bool:
    """In a game on the board: *board* is one of the game's (or a line's) positions before the board now. A FEN
    the turn was given counts too when the game passed through it — the client sends the board before the typed
    move (CoachChat: fen = the board when the student typed «0-0»; the pre-step then plays 6.O-O Nxe4), and it is
    the game's history, not a position given as such (review 30.10, prod st3)."""
    key = ctx._key(board)
    if key not in ctx.line_keys or key in ctx.line_ends or board is ctx.current:
        return False
    # outside a game, a position given as such stays one even when a line passes through it (unchanged)
    return key not in ctx.state_keys or (bool(ctx.game_moves) and ctx.current is not None
                                         and board.ply() < ctx.current.ply())


def _now_boards(ctx: CheckContext) -> list:
    """The boards a claim about the material now may be about. In a game on the board, the game's earlier
    positions are its history (a move ago Black was one pawn up, now two — prod game 29.10): the board now, the
    positions given as such (a tool's board, the student's idea) and those the answer's own moves lead to."""
    boards = ctx.boards[1:] or ctx.boards
    if not ctx.game_moves or ctx.current is None:
        return boards
    ply = ctx.current.ply()
    # …and a position the answer's moves reach from one of those (a move named in words — «ответили Nxe4» — is
    # followed where it first parses, a move before it in the game): earlier in the game than the board now.
    now = [b for b in boards if not _is_past(ctx, b) and (ctx.is_given(b) or b.ply() >= ply)]
    return now if any(b is ctx.current for b in now) else [ctx.current] + now


# «ты отдал пешку e5, но забрал f4», «белые взяли на d4»: a capture told as done.
_TOOK_ON = re.compile(
    _B2 + rf"(?:забрал\w*|взял\w*|съел\w*|выиграл\w*|took|captured|grabbed)\s+(?:(?:обратно|назад|back)\s+)?"
    rf"(?:(?:пешк\w+|кон\w+|слон\w*|ладь\w+|ферз\w+|pawn|knight|bishop|rook|queen)\s+)?(?:(?:на|on)\s+)?(?P<sq>{SQ})(?![0-9])",
    re.IGNORECASE)
# «чёрные забрали обратно», «отыграли», «разменялись», "took back": the sentence tells an exchange already over —
# the capture it names is history, the board now shows its end (review 30.10: QGD 4.cxd5 exd5, Scotch 3...exd4 4.Nxd4).
_RECAPTURE = re.compile(_B2 + r"(?:обратно|назад|отыгра\w*|отбил\w*|размен\w*|back|recaptur\w*|traded|exchanged)" + _E,
                        re.IGNORECASE)


def _told_capture(text: str, ctx: CheckContext) -> Optional[tuple]:
    """(SAN, the boards after it) when the sentence tells as done a capture the side to move has still to make —
    «Материал пока равный — ты отдал пешку e5, но забрал f4» on the board before 2...exf4 (prod 29.10,
    can-kg-accept): the material the sentence counts is the board after that capture, not the board before it.
    One capture told, legal now for the side to move (a side named before it is that side), not just played, not
    made already on that square in the game or line that leads to the board, no recapture told with it — and with
    no such history, only the capture the student asks about («Стоит ли брать пешку f4?»): «Ты забрал пешку на e5»
    on a bare FEN may be the move just made (review 30.10)."""
    board = ctx.current
    hits = list(_TOOK_ON.finditer(text))
    if board is None or len(hits) != 1 or _RECAPTURE.search(text):
        return None
    m = hits[0]
    # «пока равный», «пока что»: "so far", not "while" — the one sense of «пока» that is not a condition
    if _HYPO.search(re.sub(r"(?<![а-я])пока(?=\s+(?:что|ещ[её]|рав\w+))", "", text[: m.start()])) or _FUTURE_VERB.search(text):
        return None  # «если ты заберёшь f4…»: a line, judged elsewhere
    named = _SIDE_NAMED.findall(text[: m.start()])
    if named and _side_color(named[-1], ctx) != board.turn:
        return None
    sq = chess.parse_square(m["sq"].lower())
    played = _just_played(ctx) or set()
    if any(re.search(rf"{m['sq'].lower()}(?:=[QRBN])?$", p) for p in played):
        return None  # the capture of the move just played: the board already shows it
    history = ctx.line_captures.get(ctx._key(board))
    if history is not None and (board.turn, sq) in history:
        return None  # «Ты забрал пешку c6» about 3.dxc6, two moves ago: made, not to come (review 30.10)
    if history is None:
        from src.move_text import spoken_squares  # «брать пешку эф четыре?» asked aloud

        if not re.search(rf"(?<![a-z]){m['sq'].lower()}(?![0-9])", spoken_squares(ctx.question_raw or "").lower()):
            return None  # no record of how the board came about and the student did not ask about that capture
    moves = [mv for mv in board.legal_moves if mv.to_square == sq and board.is_capture(mv)]
    if not moves:
        return None
    after = []
    for mv in moves:
        b = board.copy(stack=False)
        b.push(mv)
        after.append(b)
    return board.san(moves[0]), after


def _material_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    told = _told_capture(text, ctx)
    if told:
        boards, where, shown = told[1], told[1][0], f"after {told[0]} (the capture this sentence tells as made): "
    else:
        boards, where, shown = ctx.boards[1:] or ctx.boards, ctx.current, ""
        if ctx.game_moves and not _PAST_BE.search(text):
            boards = _now_boards(ctx)  # a game: the material now, not a move ago (prod 29.10)
    for rx in _MATERIAL:
        for m in rx.finditer(text):
            if _is_hypothetical(text, original, m.start()):
                continue
            if _FUTURE_FILL.search(text[m.start("side"): m.start("dir")]):
                continue  # «ты останешься без фигуры»: what will be, not what is (replay, 2026-10-05)
            color = _side_color(m["side"], ctx, text[: m.start()])
            if color is None:
                continue
            kind, points = _unit(m["unit"])
            n = _num(m.groupdict().get("n"))
            direction = m["dir"].lower().replace("ё", "е")
            more = any(direction.startswith(w) for w in _MORE)
            balance = not direction.startswith(("лишн", "без", "extra", "spare"))
            if not any(_material_holds(b, color, kind, points, n, more, balance) for b in boards):
                issues.append(f"material {shown}{_imbalance(where)} (not: {m.group(0).strip()})" if shown
                              else f"material: {_imbalance(where)} (not: {m.group(0).strip()})")
    for m in _MATERIAL_EQUAL.finditer(text):
        if _is_hypothetical(text, original, m.start()):
            continue
        if _NEGATION.search(text[: m.start()]):
            continue  # «материал не равен»
        if not any(_counts(b, chess.WHITE)["nonpawn"] + _counts(b, chess.WHITE)[chess.PAWN]
                   == _counts(b, chess.BLACK)["nonpawn"] + _counts(b, chess.BLACK)[chess.PAWN]
                   for b in boards):
            issues.append(f"material {shown}{_imbalance(where)} (not equal)" if shown
                          else f"material: {_imbalance(where)} (not equal)")
    return issues


# «твой конь на c5» (the student's), «слон на e1» (a rook stands there).
_OWN_PIECE = re.compile(
    _B2 + rf"(?P<own>тво[йяеию]\w*|ваш\w*|your|мо[йяеию]\w*|наш\w*|my|our)\s+(?:(?:белый|белая|ч[её]рный|ч[её]рная|white|black)\s+)?"
    rf"(?:(?P<piece>{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<a>{SQ})|(?P<a2>{SQ})[- ](?P<piece2>pawn|knight|bishop|rook|queen|king))(?![0-9])",
    re.IGNORECASE)


# «А слон чёрных на c4 уже смотрит на f7» with a white bishop on c4 (production 08.10): a piece named by its
# side — an adjective (белый, чёрный, white), a genitive (белых, чёрных) or the opponent's.
_SIDE_ADJ = (r"(?:белый|белая|белого|белой|белую|белым|белом|ч[её]рный|ч[её]рная|ч[её]рного|ч[её]рной|ч[её]рную|"
             r"ч[её]рным|ч[её]рном|white|black)")
_SIDE_PIECE = re.compile(
    _B2 + rf"(?:(?P<adj>{_SIDE_ADJ})\s+(?P<p1>{_PIECE_ANY})|(?P<p2>{_PIECE_ANY})\s+(?P<gen>белых|ч[её]рных|соперника|противника))"
    rf"\s+(?:на\s+|on\s+)?(?P<a>{SQ})(?![0-9])", re.IGNORECASE)


# «После Се3 чёрные просто бьют Сxc5» — Bxc5 is White's (production 08.10, the client's own question): a move
# given to a side that cannot make it on any position of the turn while the other side can.
_SIDE_PLAYS = re.compile(
    _B2 + r"(?P<side>белые|белым|ч[её]рные|ч[её]рным|white|black)\s+(?:[а-яёa-z]+\s+){0,2}?"
    r"(?:бьют|берут|забирают|играют|сыграют|отвечают|ответят|идут|пойдут|ходят|делают|жертвуют|plays?|takes?|answers?|replies?|captures?)"
    r"\s+(?:[а-яёa-z]+\s+){0,1}?[*_]*(?P<mv>(?:\d{1,3}\s?\.{1,3}\s?|\.\.\.|…)?(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8]|O-O(?:-O)?)[+#]?)",
    re.IGNORECASE)


def _side_move_issues(original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    converted, _ = _to_san(original)
    for m in _SIDE_PLAYS.finditer(converted):
        side = chess.WHITE if m["side"].lower().startswith(("бел", "white")) else chess.BLACK
        mv = re.sub(r"^\d{1,3}\s?\.{1,3}\s?|^\.\.\.|^…", "", m["mv"])
        # The moves written before it in the sentence lead somewhere too («После Кxe5 чёрные играют Кxe5»;
        # a Cyrillic К may be a knight or a king, and the line check leaves it out).
        boards = list(ctx.boards)
        for prior in _MOVE.finditer(converted[: m.start("mv")]):
            for cand in {prior["san"], "N" + prior["san"][1:] if prior["san"][0] == "K" else prior["san"]}:
                for b in list(boards):
                    for color in (chess.WHITE, chess.BLACK):
                        t = b.copy(stack=False)
                        t.turn = color
                        try:
                            pm = t.parse_san(cand)
                        except ValueError:
                            continue
                        if "x" in cand and not t.is_capture(pm):
                            continue  # python-chess reads «Bxc5» onto an empty c5 too
                        t.push(pm)
                        boards.append(t)
                if len(boards) > 300:
                    break

        def legal_for(color: int) -> bool:
            for b in boards:
                t = b.copy(stack=False)
                if t.turn != color:
                    t.turn, t.ep_square = color, None
                    if not t.is_valid():
                        continue
                try:
                    played = t.parse_san(mv)
                except ValueError:
                    continue
                if "x" in mv and not t.is_capture(played):
                    continue
                return True
            return False
        if not legal_for(side) and legal_for(not side):
            return [f"{mv.rstrip('+#')} is a {'Black' if side else 'White'} move here: "
                    f"{'White' if side else 'Black'} cannot play it"]
    return []


def _side_piece_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    for m in _SIDE_PIECE.finditer(text):
        if _is_hypothetical(text, original, m.start(), whole=True):
            continue
        word = (m["adj"] or m["gen"]).lower().replace("ё", "е")
        if word.startswith(("сопер", "против")):
            student = ctx.student_color if ctx.student_color is not None else ctx.current.turn
            color = not student
        else:
            color = chess.WHITE if word.startswith(("бел", "white")) else chess.BLACK
        ptype = _piece_type(m["p1"] or m["p2"])
        if ptype is None:
            continue
        sq = chess.parse_square(m["a"].lower())
        if any((pc := b.piece_at(sq)) is not None and pc.piece_type == ptype and pc.color == color for b in ctx.boards):
            continue
        there = ctx.current.piece_at(sq)
        if there is not None and there.piece_type == ptype:
            return [f"the {_NAMES[ptype]} on {m['a'].lower()} is {'White' if there.color else 'Black'}'s, not "
                    f"{'White' if color else 'Black'}'s"]
    return []


def _presence_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    # Outside a game «твой» is the side to move: the coach talks to the student
    # as the side to move (prompt v11), and "your b3 queen" was a pawn (stand, 2026-10-04).
    student = ctx.student_color if ctx.student_color is not None else ctx.current.turn
    for m in _OWN_PIECE.finditer(text):
        if _is_hypothetical(text, original, m.start(), whole=True):
            continue
        ptype = _piece_type(m["piece"] or m["piece2"])
        if ptype is None:
            continue
        own = m["own"].lower().replace("ё", "е")
        # «наш король», "our rook": the coach talking with the student as "we" (voice, 2026-10-06).
        color = student if own.startswith(("тво", "ваш", "your", "наш", "our")) else not student
        if re.search(r"(?:пол[еяю]|клетк\w*)\s+(?:превращени\w+\s+)?$|promotion\s+square\s+(?:of\s+)?$", text[max(0, m.start() - 30):m.start()]):
            continue  # «поле превращения твоей пешки на h8» names a square, not a pawn there
        sq = chess.parse_square(m["a"] or m["a2"])
        if any((pc := b.piece_at(sq)) is not None and pc.piece_type == ptype and pc.color == color for b in ctx.boards):
            continue
        there = ctx.current.piece_at(sq)
        whose = "the student's" if color == student else "the coach's"
        sq_name = m["a"] or m["a2"]
        # Say what IS there: a correction told only «no pawn of yours on d5» put
        # «your knight on d5» in its place — the knight was the opponent's (voice, 2026-10-06).
        side = f"the student is {'White' if student else 'Black'}"
        if there is not None and there.piece_type == ptype:
            issues.append(f"the {_NAMES[ptype]} on {sq_name} is {'White' if there.color else 'Black'}'s, not {whose} ({side})")
        elif there is not None:
            issues.append(f"there is no {_NAMES[ptype]} of {whose} on {sq_name}: the {'white' if there.color else 'black'} "
                          f"{_NAMES[there.piece_type]} stands there ({side})")
        else:
            issues.append(f"there is no {_NAMES[ptype]} of {whose} on {sq_name}: the square is empty ({side})")
    # No check of «конь на f7» without an owner: the coach names pieces of lines
    # it explains («удар конём на f7: конь на f7 бьёт ферзя d8») that are on no
    # board of the turn.
    return issues


# «бьёшь его ладьёй с f5»: the piece of that kind must stand on that square.
_INSTRUMENT = re.compile(
    _B2 + rf"(?P<piece>ладь[её]й|кон[её]м|слоном|ферз[её]м|пешкой|корол[её]м|with\s+(?:the|your|my)\s+(?:rook|knight|bishop|queen|pawn|king)"
    # «убрать коня с d3», «отвести слона с c4», "move the knight from d3" — the piece leaves that square (2026-10-08)
    rf"|(?<=убрать\s)(?:коня|слона|ладью|ферзя|пешку|короля)|(?<=увести\s)(?:коня|слона|ладью|ферзя|пешку|короля)"
    rf"|(?<=отвести\s)(?:коня|слона|ладью|ферзя|пешку|короля)|(?<=перевести\s)(?:коня|слона|ладью|ферзя|пешку|короля)"
    rf"|(?<=move\sthe\s)(?:rook|knight|bishop|queen|pawn|king))"
    rf"\s+(?:с|со|from)\s+(?P<a>{SQ})(?![0-9])", re.IGNORECASE)
_INSTRUMENT_TYPE = {"лад": chess.ROOK, "кон": chess.KNIGHT, "сло": chess.BISHOP, "фер": chess.QUEEN, "пеш": chess.PAWN,
                    "кор": chess.KING, "roo": chess.ROOK, "kni": chess.KNIGHT, "bis": chess.BISHOP, "que": chess.QUEEN,
                    "paw": chess.PAWN, "kin": chess.KING}


def _instrument_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    for m in _INSTRUMENT.finditer(text):
        if _is_hypothetical(text, original, m.start(), whole=True):
            continue
        word = m["piece"].lower().replace("ё", "е").split()[-1]
        ptype = _INSTRUMENT_TYPE.get(word[:3])
        if ptype is None:
            continue
        sq = chess.parse_square(m["a"])
        if any((pc := b.piece_at(sq)) is not None and pc.piece_type == ptype for b in ctx.boards):
            continue
        issues.append(f"there is no {_NAMES[ptype]} on {m['a']}")
    return issues


# "the pawn on a4 is attacked by the b6 pawn", «ладью на d5 атакуют конь c5 и пешка d6»:
# the attackers come after the object — each must reach it.
_OBJECT_FIRST = re.compile(
    _B2 + rf"(?:(?:the\s+|your\s+|my\s+|his\s+|her\s+|их\s+|тво[йяею]\w*\s+|ваш\w*\s+|мо[йяею]\w*\s+)?"
    rf"(?:(?P<obj_piece>{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<obj>{SQ})|(?P<obj2>{SQ})[- ](?:pawn|knight|bishop|rook|queen|king))|(?P<it>it|её|ее|его))(?![0-9])"
    # «её тоже бьёт эта же пешка f3», «e5 пока держат только пешка d7 и конь g8» (stand text games 28.10)
    r"(?:'s|'re)?\s+(?:сейчас\s+|уже\s+|пока\s+|тоже\s+|также\s+|ещ[её]\s+|по-прежнему\s+|всё\s+ещ[её]\s+|is\s+|are\s+|"
    r"was\s+|were\s+|gets\s+|now\s+|still\s+|also\s+)*"
    r"(?P<verb>атакуют|атакует|бьют|бь[её]т|держат|держит|защищают|защищает|прикрывают|прикрывает|"
    r"attacked|hit|defended|protected|covered|guarded|pinned|threatened)\s+"
    r"(?:сразу\s+|только\s+|only\s+|just\s+)?(?:(?:две|три|two|three)\s+)?(?:ч[её]рн\w+\s+|бел\w+\s+|black\s+|white\s+)?(?:фигур\w*\s*[—–-]?\s*|pieces?\s*[—–:-]?\s*)?"
    r"(?:by\s+)?(?P<subjects>(?:(?:the\s+|your\s+|my\s+|a\s+|(?:эт|т)(?:а|от|о)\s+же\s+|тво[йя]\s+|мо[йя]\s+)?(?:(?:конь|слон|ладья|ферзь|король|пешка|knight|bishop|rook|queen|king|pawn)\s+(?:на\s+|on\s+|from\s+|с\s+)?[a-h][1-8]|[a-h][1-8][- ](?:pawn|knight|bishop|rook|queen|king))"
    r"(?:\s*(?:,|и|and|или|or)\s*)?)+)", re.IGNORECASE)
_SUBJECT = re.compile(rf"(?:(?P<piece>конь|слон|ладья|ферзь|король|пешка|knight|bishop|rook|queen|king|pawn)\s+(?:на\s+|on\s+|from\s+|с\s+)?(?P<a>{SQ})"
                      rf"|(?P<a2>{SQ})[- ](?P<piece2>pawn|knight|bishop|rook|queen|king))", re.IGNORECASE)


_OPENS_WITH_PRONOUN = re.compile(r"^\W*(?:(?:но|а|и|вот|and|but|so|yet)\s+)?(?:it|its|it's|он|она|оно|её|ее|его|ей|ему)(?![а-яa-z])",
                                 re.IGNORECASE)


_PASSIVE = re.compile(r"атакован\w*|защищ[её]н\w*|прикрыт\w*|бь[её]тся|под\s+боем|attacked|defended|protected|covered|guarded|"
                      r"\bhit\b|by\s+the|висит|hanging", re.IGNORECASE)


def _pronoun_square(text: str, upto: int, ctx: CheckContext) -> Optional[str]:
    """What "it" / «её» at *upto* stands for.

    The clause the pronoun is in is skipped («но её защищает конь c3»: c3 is
    the subject of that clause). In the clause before it, a passive one («пешка
    f7 атакована слоном c4», "it's attacked by the b6 pawn") is about its first
    square, an active one («конь f6 напал на пешку e4») about its last; a clause
    that opens with a pronoun, or no clause with a square at all, means the
    previous sentence's square."""
    clauses = re.split(r"[,;:—–()]|\s[-]\s|(?<![а-яa-z])(?:because|since|потому\s+что|так\s+как|ведь|поскольку)(?![а-яa-z])",
                       text[:upto])
    for clause in reversed(clauses[:-1]):
        squares = _SQ_RE.findall(clause)
        if not squares:
            continue
        if _OPENS_WITH_PRONOUN.match(clause):
            return ctx.topic
        if re.search(r"(?<![а-яa-z])(?:it|её|ее|его)(?![а-яa-z])", clause, re.IGNORECASE):
            continue  # "the knight on c5 is eyeing it": about the same thing as the clause before
        return squares[0] if _PASSIVE.search(clause) else squares[-1]
    if _OPENS_WITH_PRONOUN.match(text) and ctx.topic:
        return ctx.topic
    squares = _SQ_RE.findall(clauses[-1]) if clauses else []
    if squares and not _PASSIVE.search(clauses[-1]):
        return squares[0]  # "the pawn on a4 is hanging and nothing defends it"
    if squares:
        return squares[0]
    return ctx.topic


def _object_first_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    issues = []
    for m in _OBJECT_FIRST.finditer(text):
        if _NEGATION.search(text[: m.start("verb")]):
            continue
        if _is_hypothetical(text, original, m.start()):
            continue
        obj = m["obj"] or m["obj2"]
        if not obj:
            obj = _pronoun_square(text, m.start(), ctx)
            if not obj:
                continue
        ctx._object = obj
        target = chess.parse_square(obj)
        if re.match(r"держ|hold", m["verb"], re.IGNORECASE) and any(
                (pc := b.piece_at(target)) is not None and pc.piece_type == chess.KING for b in ctx.boards):
            continue  # «короля a8 держат пешка b6 и король c8»: a king held is a king hemmed in, not a square attacked
        for sm in _SUBJECT.finditer(m["subjects"]):
            word = (sm["piece"] or sm["piece2"]).lower()
            ptype = _piece_type(word) or _INSTRUMENT_TYPE.get(word[:3])
            if ptype is None:
                continue
            a = chess.parse_square(sm["a"] or sm["a2"])
            if a == target:
                continue
            if not _geometry_attack(ptype, a, target):
                issues.append(f"a {_NAMES[ptype]} on {chess.square_name(a)} does not attack {obj}")
                continue
            standing = [b for b in ctx.boards if (pc := b.piece_at(a)) is not None and pc.piece_type == ptype]
            if standing and not any(target in b.attacks(a) for b in standing):
                issues.append(f"a {_NAMES[ptype]} on {chess.square_name(a)} does not reach {obj}: a piece is in the way")
    return issues


# «ферзь h4 под ударом ладьи», «пешка e4 атакована конём», "the queen on h4 is
# attacked by the rook", "f7 is under attack from the bishop": the attacker named
# by its kind only — some piece of that kind must really hit the square.
_OBJECT_TYPED = re.compile(
    _B2 + rf"(?:(?:the\s+|your\s+|my\s+|тво\w*\s+|ваш\w*\s+|мо\w*\s+|ч[её]рн\w*\s+|бел\w*\s+|black\s+|white\s+)?"
    rf"(?:{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<obj>{SQ})|(?P<obj2>{SQ})[- ](?:pawn|knight|bishop|rook|queen|king)|(?P<obj3>{SQ}))(?![0-9])"
    r"\s+(?:сейчас\s+|уже\s+|теперь\s+|is\s+|are\s+|now\s+|будет\s+|окажется\s+|оказывается\s+|попада[её]т\s+|"
    r"will\s+be\s+|would\s+be\s+|ends\s+up\s+|comes\s+)*"
    r"(?P<verb>под\s+(?:ударом|боем|прицелом|атакой)|атакован\w*|бь[её]тся|is\s+attacked|gets\s+attacked|attacked|"
    r"under\s+attack|under\s+fire|hit)\s+"
    r"(?:от\s+|со\s+стороны\s+|by\s+|from\s+)?(?:the\s+|your\s+|my\s+|an?\s+|тво\w*\s+|ваш\w*\s+|мо\w*\s+|ч[её]рн\w*\s+|"
    r"бел\w*\s+|black\s+|white\s+|enemy\s+|вражеск\w*\s+|неприятельск\w*\s+)?"
    rf"(?P<att>{_PIECE_ANY})(?![а-яa-z])(?!\s*(?:на\s+|on\s+|from\s+|с\s+|со\s+)?{SQ})", re.IGNORECASE)


def _object_typed_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []  # no real position of the turn to judge by
    issues = []
    for m in _OBJECT_TYPED.finditer(text):
        if _NEGATION.search(text[: m.start("verb")]):
            continue
        obj = m["obj"] or m["obj2"] or m["obj3"]
        ptype = _piece_type(m["att"].lower())
        if ptype is None:
            continue
        sq = chess.parse_square(obj)
        standing = [b for b in ctx.boards if b.piece_at(sq) is not None]
        if _is_hypothetical(text, original, m.start()):
            # «после Rg1 ферзь h4 под ударом ладьи»: judged on the positions the
            # sentence's moves lead to, never on the board as it is now
            standing = [b for b in standing if not ctx.is_given(b)]
        if not standing:
            continue
        if any(any(b.piece_type_at(a) == ptype for a in b.attackers(not b.piece_at(sq).color, sq)) for b in standing):
            continue
        ctx._object = obj
        issues.append(f"no {_NAMES[ptype]} attacks {obj}")
    return issues


# «ничто не атакует пешку a4», "nothing is attacking it", «пешка a4 не под боем»,
# "the a4 pawn is not attacked": a claim that nothing hits the
# square (stand, 2026-10-04: "Your a4 pawn is fine — nothing is attacking it"
# with the knight on c5 hitting it). A named attacker («не атакована ферзём»,
# "not attacked by the queen") is another claim and is left alone.
_NOT_ATTACKED = re.compile(
    _B2 + r"(?:(?:никто|ничто|ничего|nothing|nobody|no\s+one|no\s+piece)\s+(?:не\s+|is\s+|isn't\s+|currently\s+)?"
    r"(?:атакует|бь[её]т|нападает|угрожает|attacks|attacking|hits|hitting|threatens|threatening|targets|targeting)\s+"
    r"(?:на\s+)?(?:(?:тво\w+|ваш\w+|мо\w+|ч[её]рн\w+|бел\w+|the|your|my)\s+)?"
    rf"(?:(?P<p1>{_PIECE_ANY})\s+(?:на\s+|on\s+)?)?(?:(?P<a>{SQ})|(?P<it1>it|её|ее|его))(?![0-9a-zа-я])"
    r"(?!\s*(?:a\s+second\s+time|twice|again|any\s*more|ещ[её]\s+раз|второй\s+раз|дважды|больше|кроме|except|but)(?![а-яa-z]))"
    rf"|(?:(?P<p2>{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<b>{SQ})|(?P<b2>{SQ})[- ](?P<p3>pawn|knight|bishop|rook|queen|king)|(?P<it2>it|она|он))(?![0-9])"
    r"\s+(?:сейчас\s+|пока\s+|уже\s+|is\s+|'s\s+|are\s+|now\s+|currently\s+|still\s+|совсем\s+|совершенно\s+|полностью\s+|perfectly\s+|completely\s+)*"
    r"(?P<neg>не\s+(?:атакован\w*|под\s+(?:боем|ударом|угрозой))|никем\s+не\s+атакован\w*|"
    r"(?:is\s+)?not\s+(?:attacked|under\s+attack|under\s+threat|threatened)|isn't\s+(?:attacked|under\s+attack|threatened))"
    r"(?![а-яa-z])(?!\s*(?:by|from|от|со\s+стороны)(?![а-яa-z])))", re.IGNORECASE)


# «никто не защищает a4», "nothing defends a4", "nothing of yours defends the rook":
# a claim that the square has no defender (production, 2026-10-04: "Right now
# nothing defends a4" with the pawn on b3 defending it).
_NOT_DEFENDED = re.compile(
    _B2 + r"(?:никто|ничто|ничего|nothing|nobody|no\s+one|no\s+piece)(?:\s+of\s+(?:yours|mine|theirs|white'?s|black'?s))?"
    r"\s+(?:не\s+|is\s+|isn't\s+|currently\s+|really\s+)?"
    r"(?:защищает|прикрывает|держит|охраняет|defends|defending|protects|protecting|guards|guarding|covers|covering)\s+"
    r"(?:на\s+)?(?:(?:тво\w+|ваш\w+|мо\w+|ч[её]рн\w+|бел\w+|the|your|my|that|this)\s+)?"
    rf"(?:(?P<p1>{_PIECE_ANY})\s+(?:на\s+|on\s+)?)?(?:(?P<a>{SQ})|(?P<it>it|её|ее|его))(?![0-9a-zа-я])"
    r"(?!\s*,?\s*(?:a\s+second\s+time|twice|again|any\s*more|ещ[её]\s+раз|второй\s+раз|дважды|больше|кроме|помимо|except|but|other\s+than|apart\s+from)(?![а-яa-z]))"
    # «пешку a4 никто не защищает»: the object first
    rf"|(?P<p2>{_PIECE_ANY})\s+(?:на\s+)?(?P<b>{SQ})(?![0-9])\s+(?:сейчас\s+|пока\s+|уже\s+|теперь\s+)?(?:никто|ничто|ничего)\s+не\s+"
    r"(?:защищает|прикрывает|держит|охраняет)(?![а-я])(?!\s*,?\s*(?:кроме|помимо|больше)(?![а-я]))",
    re.IGNORECASE)


def _same_kind(word: Optional[str], piece: chess.Piece) -> bool:
    """No piece named, or the named kind is what stands on the square."""
    if not word:
        return True
    kind = _piece_type(word.lower())
    return kind is None or kind == piece.piece_type


def _not_defended_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    for m in _NOT_DEFENDED.finditer(text):
        if _is_hypothetical(text, original, m.start()):
            continue
        sq_name = m["a"] or m["b"] or (_pronoun_square(text, m.start("it"), ctx) if m["it"] else None)
        if not sq_name or (m["it"] and sq_name not in _SQ_RE.findall(text)):
            continue  # "nobody guards it" about a square the sentence never names (the question's Rxd6): not judged
        sq = chess.parse_square(sq_name)
        piece = ctx.current.piece_at(sq)
        if piece is None or not _same_kind(m["p1"] or m["p2"], piece):
            continue  # "the rook on d6" with a pawn on d6: about another position (after Rxd6)
        defenders = ctx.current.attackers(piece.color, sq)
        if not defenders:
            continue
        ctx._object = sq_name
        who = ", ".join(_piece_name_at(ctx.current, d) for d in defenders)
        issues.append(f"the {_NAMES[piece.piece_type]} on {sq_name} IS defended — by {who}")
    return issues


def _not_attacked_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    for m in _NOT_ATTACKED.finditer(text):
        if _is_hypothetical(text, original, m.start()):
            continue
        sq_name = m["a"] or m["b"] or m["b2"]
        if not sq_name:
            sq_name = _pronoun_square(text, m.start("it1") if m["it1"] else m.start(), ctx)
            if not sq_name or sq_name not in _SQ_RE.findall(text):
                continue  # the pronoun's square must be named in this sentence
        sq = chess.parse_square(sq_name)
        piece = ctx.current.piece_at(sq)
        if piece is None or not _same_kind(m["p1"] or m["p2"] or m["p3"], piece):
            continue
        attackers = ctx.current.attackers(not piece.color, sq)
        if not attackers:
            continue
        ctx._object = sq_name
        who = ", ".join(_piece_name_at(ctx.current, a) for a in attackers)
        issues.append(f"the {_NAMES[piece.piece_type]} on {sq_name} IS attacked — by {who}")
    return issues


def _piece_name_at(board: chess.Board, sq: int) -> str:
    p = board.piece_at(sq)
    return f"the {_NAMES[p.piece_type]} on {chess.square_name(sq)}" if p else chess.square_name(sq)


# "c2 defends it", «d6 защищает её»: a bare square as the subject is the piece standing there.
_SQUARE_SUBJECT = re.compile(
    _B2 + rf"(?<!on )(?<!на )(?<!from )(?<!с )(?<!со )(?<!to )(?<!the )(?P<a>{SQ})\s+(?P<verb>defends|protects|covers|guards|attacks|hits|защищает|прикрывает|держит|атакует|бь[её]т)\s+"
    rf"(?:the\s+)?(?:(?P<pw>{_PIECE_ANY})\s+(?:on\s+|на\s+)?)?(?:(?P<b>{SQ})|(?P<it>it|её|ее|его))(?![0-9])", re.IGNORECASE)
# «a3 держит пешка b2»: a piece word in the nominative after the verb is its subject — the pawn on b2
# holds a3 (Russian word order; the lesson tutor's true sentence was cut, 2026-10-08).
_NOMINATIVE_PIECE = re.compile(r"(?:пешка|конь|слон|ладья|ферзь|король)", re.IGNORECASE)


def _square_subject_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    for m in _SQUARE_SUBJECT.finditer(text):
        if _NEGATION.search(text[: m.start("verb")]) or _is_hypothetical(text, original, m.start()):
            continue
        target_name = m["b"] or _pronoun_square(text, m.start(), ctx)
        if not target_name:
            continue
        ctx._object = target_name
        a, target = chess.parse_square(m["a"]), chess.parse_square(target_name)
        if m["b"] and m["pw"] and _NOMINATIVE_PIECE.fullmatch(m["pw"]):
            a, target = target, a  # the subject stands after the verb
        if a == target:
            continue
        piece = ctx.current.piece_at(a)
        if piece is None:
            continue  # an empty square now: a line of play, not judged
        if target == _ep_victim(ctx.current, a):
            continue  # «e5 бьёт пешку d5» on the move after d7-d5: en passant
        if target not in ctx.current.attacks(a):
            issues.append(f"the {_NAMES[piece.piece_type]} on {chess.square_name(a)} does not reach "
                          f"{chess.square_name(target)}")
    return issues


# «Qxg7 легален», "you can play Qxg7", «обе легальны» about the moves the student asked about.
_LEGAL_CLAIM = re.compile(
    r"(?P<san>(?<![A-Za-z0-9])[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?\s*(?:[—–-]\s*)?(?:ход\s+)?"
    r"(?:легален|легальн\w*|возможен|возможн\w*|допустим\w*|разреш[её]н\w*|is\s+legal|is\s+(?:a\s+)?legal\s+move|is\s+possible|is\s+allowed|works)"
    r"|(?:можно|можешь|можете|you\s+can|you\s+could|you\s+may|it'?s\s+legal\s+to)\s+(?:сыграть\s+|играть\s+|play\s+)?"
    r"(?P<san2>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)", re.IGNORECASE)
_BOTH_LEGAL = re.compile(r"(?<![а-яa-z])(?:об[ае]|оба\s+хода|both(?:\s+moves)?(?:\s+are)?)\s+(?:хода\s+)?(?:легальн\w*|возможн\w*|допустим\w*|legal|possible|allowed)",
                         re.IGNORECASE)


def _legality_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    """A move the coach calls legal must be legal on the board now (for the side
    to move, or at least for the other side)."""
    if ctx.current is None:
        return []
    claimed = []
    converted, _ = _to_san(original)
    for m in _LEGAL_CLAIM.finditer(converted):
        if _NEGATION.search(converted[: m.start()]):
            continue
        claimed.append(m["san"] or m["san2"])
    if _BOTH_LEGAL.search(text):
        claimed += sorted(ctx.quoted)
    issues = []
    for san in dict.fromkeys(claimed):
        if san.startswith("O-O"):
            continue
        legal = False
        for color in (ctx.current.turn, not ctx.current.turn):
            trial = ctx.current.copy(stack=False)
            trial.turn = color
            try:
                trial.parse_san(san)
                legal = True
                break
            except ValueError:
                continue
        if not legal:
            issues.append(f"{san} is not a legal move here")
    return issues


def _fact_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    denial = _DENIES.search(text)
    if denial:
        # «Ферзь b6 у тебя висит под боем коня f7, так что медлить нельзя» (prod 23.10): the denial is a later
        # clause; the clauses before it are still claims about the board — the ghost checks read them.
        head = text[: denial.start()]
        cut = max(head.rfind(","), head.rfind("—"), head.rfind("–"), head.rfind(";"), head.rfind(":"))
        before = head[:cut] if cut > 0 else ""
        return (_legality_issues(text, original, ctx)
                + (_ghost_issues(before, ctx) + _object_ghost_issues(before, ctx) if before.strip() else []))
    return (_hanging_issues(text, original, ctx) + _pin_issues(text, original, ctx)
            + _material_issues(text, original, ctx) + _presence_issues(text, original, ctx)
            + _instrument_issues(text, original, ctx) + _object_first_issues(text, original, ctx)
            + _square_subject_issues(text, original, ctx) + _legality_issues(text, original, ctx)
            + _object_typed_issues(text, original, ctx) + _not_attacked_issues(text, original, ctx)
            + _not_defended_issues(text, original, ctx) + _eval_issues(text, original, ctx)
            + _side_piece_issues(text, original, ctx) + _side_move_issues(original, ctx)
            + (_ghost_issues(text, ctx) if not _is_hypothetical(text, original, 0, whole=True) else [])
            + _object_ghost_issues(text, ctx) + _capture_chain_issues(text, ctx) + _solution_issues(text, original, ctx)
            + _unattacked_object_issues(text, original, ctx))


# A sentence in the wrong language: the model answered a Russian question in
# English after a long English tool result (and once in Chinese, 2026-09-29).
# Only a clear case counts — URLs, FENs, moves and names of openings are not
# language — so a Russian sentence with an English title in it is left alone.
_NOT_LANGUAGE = re.compile(
    r"https?://\S+|www\.\S+|[rnbqkpRNBQKP1-8]{1,8}(?:/[rnbqkpRNBQKP1-8]{1,8}){7}(?:\s+[wb]\s+\S+\s+\S+(?:\s+\d+\s+\d+)?)?"
    r"|(?<![A-Za-z])(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8]|O-O(?:-O)?)[+#!?]*(?![A-Za-z])"
    r"|`[^`]*`")
MIN_LANGUAGE_LETTERS = 30
# Letters of neither alphabet (Chinese, Arabic, Hindi…): a whole lesson answer came in Chinese on
# the local stand (DeepSeek, 2026-10-08) and the check, counting only Latin and Cyrillic, saw nothing.
MIN_OTHER_SCRIPT = 4


def _other_script(text: str) -> int:
    """Letters neither Latin (accents included: «Réti», «Grünfeld») nor Cyrillic."""
    def other(ch: str) -> bool:
        if not ch.isalpha() or "a" <= ch.lower() <= "z" or "а" <= ch.lower() <= "я" or ch.lower() in "ёәғқңөұүһі":
            return False
        base = unicodedata.normalize("NFD", ch)[0].lower()
        return not ("a" <= base <= "z" or "а" <= base <= "я") and ch.lower() not in "ßøæœłđı"
    return sum(1 for ch in text if other(ch))


def looks_wrong_script(text: str, language: Optional[str]) -> bool:
    """*text* (the start of a sentence) is mostly in the wrong script already —
    too short to be sure, enough to hold it back until it is."""
    if not language:
        return False
    stripped = _NOT_LANGUAGE.sub(" ", text or "")
    cyrillic = sum(1 for ch in stripped if "а" <= ch.lower() <= "я" or ch.lower() in "ёәғқңөұүһі")
    latin = sum(1 for ch in stripped if "a" <= ch.lower() <= "z")
    if _other_script(stripped) >= MIN_OTHER_SCRIPT:
        return True
    if language == "en":
        return cyrillic >= 8 and cyrillic > 2 * latin
    return latin >= 8 and latin > 2 * cyrillic


_EN_FUNCTION = re.compile(r"(?<![A-Za-z'])(?:I'?ll|I'?m|I\s+will|let\s+me|let'?s|here'?s|the|this|that|is|are|you|your|we|it'?s|"
                          r"and|with|for|of|to|at|on|look|pull|show|check)(?![A-Za-z'])", re.IGNORECASE)


def language_issue(sentence: str, language: Optional[str]) -> Optional[str]:
    """*sentence* is clearly not in *language* (a locale code), or None."""
    if not language:
        return None
    text = _NOT_LANGUAGE.sub(" ", sentence or "")
    cyrillic = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch.lower() in "ёәғқңөұүһі")
    latin = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    if _other_script(text) >= MIN_OTHER_SCRIPT:
        name = {"ru": "Russian", "kk": "Kazakh", "kz": "Kazakh", "en": "English"}.get(language, language)
        return f"this sentence is not in {name}; the whole answer must be in {name}"
    if language == "en":
        if cyrillic >= MIN_LANGUAGE_LETTERS and cyrillic > 2 * latin:
            return "this sentence is not in English; the whole answer must be in English"
        return None
    if latin >= MIN_LANGUAGE_LETTERS and latin > 2 * cyrillic:
        name = {"ru": "Russian", "kk": "Kazakh", "kz": "Kazakh"}.get(language, language)
        return f"this sentence is in English; the whole answer must be in {name}"
    # A short English sentence: «I'll pull up the game.» opened a Russian answer (2026-10-08). Names
    # and glosses («(Fried Liver Attack)», «DrNykterstein (Lichess)») have no English function words.
    if cyrillic == 0 and latin >= 8 and len(_EN_FUNCTION.findall(text)) >= 2:
        name = {"ru": "Russian", "kk": "Kazakh", "kz": "Kazakh"}.get(language, language)
        return f"this sentence is in English; the whole answer must be in {name}"
    return None


# A generic English chess word inside a Russian or Kazakh sentence: «у White появляется…»,
# «Блэк вынужден взять», «вничью instant» (production 2026-10-07). Opening names and
# notation are not words of this list; a replacement would break the grammar — rewritten.
_FOREIGN_WORD = re.compile(
    r"(?<![A-Za-z'(])(?:White|Black|white|black|instant|instantly|checkmate|stalemate|tempo|Блэк|Уайт)"
    r"(?![A-Za-zА-Яа-яЁё)]|'s\s+(?:Gambit|Indian))")  # «ловушка Блэкберна» is a name; «(tempo)» a gloss


# The chess words of a Russian or Kazakh answer, one table (prod 09.10–29.10: «епископ», «королева», «рыцарь»,
# «opposition», «queen выгоняет на край», «нет pawns», «en passant», «на d-файле»): the word the model used, and
# the word the language has — (pattern, Russian, Kazakh). A word of the table in a sentence is not shown; the
# words chess_terms() can swap in place (the same gender, so the sentence still agrees) never reach the check in
# the text coach, the others are rewritten (королева → ферзь changes the gender), and the voice coach says the
# sentence again with the right word.
_TERM_TABLE = [
    # (pattern, Russian, Kazakh, the stem of the right word: with it in the sentence the other one is explained)
    (r"епископ\w*", "слон", "піл", r"слон|піл"),
    (r"королев(?:а|ы|е|у|ой|ою|ам|ами|ах)", "ферзь", "уәзір", r"ферз|уәзір"),  # not «королевский», not «Королёв»
    (r"рыцар(?:ь|я|ю|ем|е|и|ей|ям|ями|ях)", "конь", "ат", r"кон[ьяюеё]|ат(?:ты|қа|ы)?(?![\w-])"),
    (r"башн(?:я|и|е|ю|ей|ею|ям|ями|ях|ен)", "ладья", "тура", r"лад[ьеи]|тура"),
    (r"эндгейм\w*", "эндшпиль", "эндшпиль", r"эндшпил"),
    (r"миттельгейм\w*", "миттельшпиль", "миттельшпиль", r"миттельшпил"),
    # «открытый файл», not the verb «открыть файл PGN» (review 30.10)
    (r"[a-h]-?файл\w*|вертикальн\w+\s+файл\w*|(?:полу)?открыт(?:ый|ой|ая|ом|ую|ых|ые|ым|ыми|ого|ому)\s+файл\w*",
     "вертикаль", "тік", r"вертикал|тік"),
    # English words in a Russian or Kazakh sentence: «queen выгоняет на край», «нет pawns», «только immediately»;
    # with the right word right next to them they are glossed: «оппозиция, или opposition» (review 30.10) — next to
    # them only: «мат ставит именно ферзь, … — queen выгоняет на край» (prod 29.10) has both and is wrong
    (r"queens?", "ферзь", "уәзір", r"ферз|уәзір"), (r"kings?", "король", "патша", r"корол|патша"),
    (r"rooks?", "ладья", "тура", r"лад[ьеи]|тура"), (r"bishops?", "слон", "піл", r"слон|піл"),
    (r"knights?", "конь", "ат", r"кон[ьяюеё]|ат(?:ты|қа|ы)?(?![\w-])"), (r"pawns?", "пешка", "сарбаз", r"пешк|сарбаз"),
    (r"opposition", "оппозиция", "оппозиция", r"оппозиц"), (r"zugzwang", "цугцванг", "цугцванг", r"цугцванг"),
    (r"fianchetto", "фианкетто", "фианкетто", r"фианкетто"),
    (r"en\s+passant", "взятие на проходе", "өтпелі алу", r"на\s+проходе|өтпелі"),
    (r"endgame", "эндшпиль", "эндшпиль", r"эндшпил"), (r"middlegame", "миттельшпиль", "миттельшпиль", r"миттельшпил"),
    (r"skewer", "сквозной удар", "рентген", r"сквозн|рентген"), (r"outpost", "форпост", "форпост", r"форпост"),
    (r"immediately", "сразу", "бірден", r"сразу|бірден"),
]
_TERM_WORD = re.compile(r"(?<![\w'-])(?:" + "|".join(f"(?P<t{i}>{row[0]})" for i, row in enumerate(_TERM_TABLE))
                        + r")(?![\w-]|'s\s)", re.IGNORECASE)
# Not words of the sentence: links and paths («chesster.io/learn/chess-basics/the-king-move-right»), a gloss in
# brackets («оппозиция (opposition)»), a quoted name («сериал «Ход королевы»»); a title in capitals — of a book,
# a course or an opening («Silman's Complete Endgame Course», «King and Pawn Endgames», «Two Knights Defense») —
# and the series «Ход королевы» unquoted (review 30.10).
_NOT_TERMS = re.compile(r"\S*[/\\]\S*|\b[\w-]+\.(?:io|com|org|ru|kz|net)\b\S*|\([^()]{0,80}\)|«[^«»]{0,80}»|\"[^\"]{0,80}\"|“[^”]{0,80}”"
                        r"|(?<![A-Za-z'])[A-Z][A-Za-z']*(?:\s+(?:(?:and|of|the|for|in|on|to|&)\s+)*[A-Z][A-Za-z']*)+"
                        r"|Ход\s+королев\w*")
# A word named as a word of another language: «по-английски opposition», «немецкое слово zugzwang», «от
# итальянского fianchetto», «ферзь queen деп аталады» — the English words of the sentence are glossed.
_GLOSSED = re.compile(r"(?<![\w-])(?:по-английски|по-немецки|по-французски|по-итальянски|английск\w*|немецк\w*|"
                      r"итальянск\w*|французск\w*|латинск\w*|называ\w*|зовут|термин\w*|ағылшын\w*|аталады|in\s+english)(?![\w-])",
                      re.IGNORECASE)


def _term_row(word: str) -> Optional[int]:
    """The row of _TERM_TABLE the word belongs to, or None."""
    m = _TERM_WORD.fullmatch(word or "")
    return int(next(k for k, v in m.groupdict().items() if v)[1:]) if m else None


def _term_rows(text: str) -> set:
    """The rows of _TERM_TABLE whose words are in *text* — the student's question, in any form of the word."""
    return {int(next(k for k, v in m.groupdict().items() if v)[1:]) for m in _TERM_WORD.finditer(text or "")}


def _term_explained(row: int, sentence: str, asked: set, at: Optional[tuple] = None) -> bool:
    """The word of *row* (at *at* in *sentence*) is the student's own («королева» asked, «королевой» answered), or
    the right word is in the sentence («ферзь (его ещё зовут королевой)», «Ладью часто называют башней»), or an
    English word is named as English («по-английски queen») or stands right by the right word: explained, not used."""
    pat, _ru, _kk, stem = _TERM_TABLE[row]
    if row in asked:
        return True
    english = pat[:1].isalpha()
    if english and _GLOSSED.search(sentence):
        return True
    where = sentence
    if english:
        if at is None:
            return False
        where = sentence[max(0, at[0] - 25):at[1] + 25]
    return bool(stem and re.search(r"(?<![\w-])(?:" + stem + ")", where, re.IGNORECASE))


def _term_issue(sentence: str, language: str, question: str = "") -> Optional[str]:
    """A word of _TERM_TABLE in a Russian or Kazakh sentence, as an issue, or None."""
    text = _NOT_TERMS.sub(lambda mm: " " * len(mm.group(0)), _NOT_LANGUAGE.sub(lambda mm: " " * len(mm.group(0)), sentence))
    asked = _term_rows(question)
    for m in _TERM_WORD.finditer(text):
        i = int(next(k for k, v in m.groupdict().items() if v)[1:])
        _pat, ru, kk, _stem = _TERM_TABLE[i]
        word = m.group(0)
        if _term_explained(i, sentence, asked, m.span()):
            continue
        right = kk if language in ("kk", "kz") else ru
        name = {"ru": "Russian", "kk": "Kazakh", "kz": "Kazakh"}[language]
        return f"«{word}» is not the {name} chess word: say {right}"
    return None


def foreign_word_issue(sentence: str, language: Optional[str], question: str = "") -> Optional[str]:
    """An English chess word, or a word of another register («епископ», «королева»), in a sentence that is
    otherwise in *language* (ru/kk), or None."""
    if language not in ("ru", "kk", "kz") or not sentence:
        return None
    cyrillic = sum(1 for ch in sentence if "а" <= ch.lower() <= "я" or ch.lower() in "ёәғқңөұүһі")
    if cyrillic < MIN_LANGUAGE_LETTERS:
        # A short sentence still has its words: «Епископ на c4 сильный.» (the table's words are not English names)
        return _term_issue(sentence, language, question) if cyrillic >= 10 else None
    m = _FOREIGN_WORD.search(_NOT_LANGUAGE.sub(lambda mm: " " * len(mm.group(0)), sentence))
    name = {"ru": "Russian", "kk": "Kazakh", "kz": "Kazakh"}[language]
    if m:
        return f"«{m.group(0)}» is an English word in a {name} sentence: say it in {name} (белые, чёрные, сразу, мат, пат, темп)"
    return _term_issue(sentence, language, question)


_TOPIC_TARGET = re.compile(
    rf"(?:бь[её]т|бьют|атакует|атакуют|нападает|нападают|защищает|защищают|прикрывает|прикрывают|держит|держат|"
    rf"attacks|hits|defends|protects|covers|guards|eyes|eyeing|attacking|hitting|defending)\s+"
    rf"(?:на\s+|по\s+|в\s+|the\s+|your\s+|my\s+)?(?:{_PIECE_ANY}\s+)?(?:на\s+|on\s+)?({SQ})(?![0-9])", re.IGNORECASE)


# «Сыграй Rg1», «лучше Rg1», «можно поставить ладью на g1», "play Rg1", "you
# should put the rook on g1": the coach recommends a move. Its quality is the
# engine's to judge (src/server.py verifies it before the sentence is shown).
_PROPOSES = re.compile(
    # «Спокойнее всего уйти слоном — например, сыграть Bb5» (prod 09.10: Bb5 hangs the bishop) — not «если сыграть …»
    r"(?<![а-яa-z])(?:(?<!если\s)(?<!если\sбы\s)(?:например,?\s+)?сыграть|спокойнее(?:\s+всего)?|сыграй(?:те)?|играй(?:те)?|поставь(?:те)?|ставь(?:те)?|пойди(?:те)?|ходи(?:те)?|бей(?:те)?|"
    r"бери(?:те)?|возьми(?:те)?|забирай(?:те)?|сыграем|берём|берем|ставим|идём|идем|"
    r"лучше(?:\s+всего)?|сильнее(?:\s+всего)?|правильно|точнее|надо|нужно|стоит|можно|рекомендую|советую|предлагаю|"
    r"попробуй(?:те)?|я\s+бы\s+(?:сыграл\w*|поставил\w*|пошл\w+|взял\w*|отв[её]л\w*|ув[её]л\w*)|хороший\s+ход|лучший\s+ход|сильный\s+ход|"
    r"отвести|отведи(?:те)?|увести|уведи(?:те)?|перевести|переведи(?:те)?|разменять|разменяй(?:те)?|"
    r"самое\s+(?:упорное|точное|сильное|над[её]жное|простое|естественное)|единственн\w+\s+(?:ход|шанс|защита|спасение)|"
    r"самый\s+\w+\s+ход|ход\s+(?:здесь|тут|сейчас)\s*[—–:-]|"
    r"(?:мой|наш)\s+совет\s*[—–:-]?|совет\w*\s*[—–:]|рекомендаци\w+\s*[—–:]|напрашивается|просится|"
    r"my\s+(?:advice|suggestion|pick|choice)\s*[—–:-]?|i\s+suggest|i'?d\s+suggest|i'?d\s+recommend|the\s+move\s+to\s+play|go\s+with|"
    r"верный\s+ход|правильный\s+ход|идея\s*[—–:-]|план\s*[—–:-]|решение\s*[—–:-]|"
    r"play|try|go\s+for|put|place|take|grab|capture|push|advance|best\s+is|the\s+best\s+(?:move|is)|i'?d\s+(?:play|go|put|take)|"
    r"i\s+would\s+(?:play|go|put|take)|you\s+(?:should|could|can|want\s+to|need\s+to|have\s+to)|consider|"
    r"recommend|suggest|strong(?:est)?\s+(?:is|move)|the\s+(?:right|correct|key|good|natural|only)\s+move|"
    r"the\s+move\s+(?:is|here\s+is))(?![а-яa-z])", re.IGNORECASE)
# Where the recommended move must sit: in the same clause, before any «если»/«после»
# (those start a hypothetical, not the recommendation) and before «но»/«а не»/«вместо».
_PROPOSAL_END = re.compile(
    r"\.(?!\s?(?:[KQRBNO]|[a-h][1-8x]))|[;!?\n]|"
    r",\s*(?:но|а|если|когда|после|пока|потому|вместо|but|if|when|after|instead|rather|because)(?![а-яa-z])|"
    r"\s(?:если|после|когда|вместо|а\s+не|но\s+не|if|after|when|instead\s+of|rather\s+than|not)(?![а-яa-z])",
    re.IGNORECASE)


# «Ход Rg1 — как раз самый сильный», "Rg1 is the best move here": the move
# comes first, the praise after it.
_PRAISED = re.compile(
    r"\s*(?:[—–-]|:|,)?\s*(?:это\s+|здесь\s+|тут\s+|сейчас\s+|как\s+раз\s+|is\s+|here\s+is\s+|would\s+be\s+|looks\s+)*"
    r"(?:самый\s+|the\s+|a\s+|very\s+|really\s+)?(?:сильн\w+|лучш\w+|точн\w+|правильн\w+|верн\w+|хорош\w+|отличн\w+|"
    r"единственн\w+|над[её]жн\w+|best|strongest|right|correct|good|excellent|only|natural)\b", re.IGNORECASE)


# «а вот если конь прыгнет на f7 — он бьёт и ладью, и ферзя», "Nf7 forks the queen
# and the rook": a move shown with what it wins is the coach's advice, whatever
# the grammar (production, 2026-10-05: Nxf7 hung the queen on h5 to the g6 pawn).
_PRAISE = re.compile(
    r"бь[её]т|бьют|напада|атаку|выигрыва|забира|вилк|с\s+темпом|с\s+шахом|(?<![а-я])мат(?![а-я])|сильн|отличн|хорош|лучш|решает|"
    r"forks?|attacks?|hits|wins|picks\s+up|with\s+tempo|with\s+check|(?<![a-z])mates?(?![a-z])|strong|great|excellent|good",
    re.IGNORECASE)


def written_line_after(sentence: str, san: str) -> list[str]:
    """The moves written right after *san* in *sentence* («после Nf7 Kxf7 Qxc5 …»
    → ['Nxf7', 'Kxf7', 'Qxc5']), the first being *san* itself; [] when it stands alone."""
    converted, _ = _to_san(sentence or "")
    key = san.replace("x", "").rstrip("+#")
    moves = list(_MOVE.finditer(converted))
    for i, m in enumerate(moves):
        if m["san"].replace("x", "") != key:
            continue
        line = [m["san"] + (m["check"] or "")]
        last_end = m.end()
        for nxt in moves[i + 1:]:
            gap = converted[last_end: nxt.start()]
            if not re.fullmatch(r"[\s,]*(?:\d{1,3}\s?\.{1,3}\s*)?", gap):
                break
            line.append(nxt["san"] + (nxt["check"] or ""))
            last_end = nxt.end()
        return line if len(line) > 1 else []
    return []


# «закрыть калитку пешкой: g6», «пешку на e4», "the pawn to e4", "push g6": a pawn told
# to go to the square (production, 2026-10-06: «самое надёжное — пешкой: g6» hung the rook to Qxe5+)
_PAWN_MOVE_WORDS = re.compile(
    r"(?:пешк\w*\s*(?:на|в|[:—–-])\s*|пешкой\s+(?:на\s+)?|pawn\s+(?:to|on|onto)\s+|push(?:ing)?\s+(?:the\s+pawn\s+(?:to\s+)?)?|"
    r"(?:толкн\w+|продвин\w+|двин\w+)\s+(?:пешку\s+)?(?:на\s+)?)$", re.IGNORECASE)  # not «пешка e5 висит»: that names a square


# Words that look at a move rather than recommend it, when the move is the one the student asked about
# («А если я сыграю Be7+?» — «Сыграем **Be7+** и посмотрим…»): on the lesson page (2026-10-08) such a
# sentence was cut as bad advice, and with it the explanation of why the student's idea fails.
_EXPLORES = re.compile(r"сыграем|берём|берем|ставим|идём|идем|можно|попробуй(?:те)?|попробуем|давай(?:те)?|let'?s",
                       re.IGNORECASE)


# A recommendation in so many words: the student's own idea is advice only with one of these.
_RECOMMENDS = re.compile(
    r"(?<![а-яa-z])(?:сыграй(?:те)?|играй(?:те)?|поставь(?:те)?|бей(?:те)?|бери(?:те)?|возьми(?:те)?|лучше|сильнее|"
    r"правильно|надо|нужно|стоит|рекомендую|советую|предлагаю|хорош\w*\s+ход|лучш\w*\s+ход|сильн\w*\s+ход|"
    r"отличн\w*|верн\w*\s+ход|play|go\s+for|recommend|best|good\s+move|strong)(?![а-яa-z])", re.IGNORECASE)


# «Берёшь коня на d5 с шахом: Qxd5+.», «Играешь Nf3 — и конь защищает…»: the coach tells the student's move in the
# present, the second person, at the start of the sentence — advice as much as «сыграй Qxd5+» (prod 29.10: Qxd5+
# lost the queen to 8...Qxd5 and went out unchecked). Not after «тогда», «после …», «если …» (a step of a line), not
# in a question, and not when the sentence says the move fails («берёшь на d5 — и теряешь ферзя»).
_YOU_PLAY = re.compile(
    r"^[\s*_>#«\"-]*(?:(?:и|а|здесь|тут|сейчас|теперь|сначала|поэтому|так\s+что|вот)\s+)?(?:ты\s+)?"
    r"(?:просто\s+|спокойно\s+|сразу\s+|смело\s+|сам\s+)?"
    r"(?:берешь|бьешь|играешь|ставишь|идешь|забираешь|уводишь|отводишь|жертвуешь|переводишь|выводишь|двигаешь|продвигаешь|"
    r"толкаешь|отдаешь|разменива\w*ешь|прыгаешь|ходишь)(?![а-я])", re.IGNORECASE)
# (review 30.10: «…и ферзя у тебя больше нет», «ты остаёшься без ферзя», «почему так не играют» say it fails too)
_FAILS = re.compile(r"(?<![а-яa-z])(?:теря\w*|потеря\w*|проигр\w*|ошиб\w*|зева\w*|зевок|подстав\w*|ловуш\w*|плох\w*|нельзя|"
                    r"опасн\w*|не\s+стоит|не\s+надо|не\s+нужно|не\s+проход\w*|не\s+работа\w*|так\s+не\s+игра\w*|больше\s+нет|"
                    r"оста[её]шься\s+без|остаются\s+без|минус|пропада\w*|hangs?|loses?|blunder\w*|mistake\w*|trap\w*)(?![а-яa-z])",
                    re.IGNORECASE)
# …nor when it goes on to the opponent's answer («Берёшь Qxd5+, а он просто отвечает Qxd5», «…но чёрный ферзь бьёт
# обратно»): the sentence tells a line, and the line's outcome is the engine's to judge (src/line_verdict.py), not
# the first move as advice (review 30.10: four correct refutations of Qxd5+ were cut as «Qxd5+ is a mistake»).
_REPLY = re.compile(r"(?<![а-яa-z])(?:отвеча\w*|ответ(?:ит|ят|ом)|в\s+ответ|(?:бь[её]т|бьют|бер[её]т|берут|забира\w+)\s+обратно|"
                    r"replies|answers|recaptures?|takes\s+back)"
                    r"(?![а-яa-z])", re.IGNORECASE)
# A move told for the other side in the third person («Что если он возьмёт ферзём на d5?», «Если соперник сыграет
# Qxd5+…», «чёрные отвечают Qxd5»), or the student's own last move told («Я пошёл королём на e6»): outside a game
# the student is then not known to be the side to move (review 30.10: a Black student's «ты забираешь ферзя» was
# read as White's).
_THIRD_MOVE = re.compile(
    r"(?<![а-яa-z])(?:он|она|они|соперник\w*|противник\w*|оппонент\w*|белые|черные|he|she|they|(?:my\s+|the\s+|your\s+)?opponent|"
    r"white|black)\s+(?:[а-яa-z]+\s+){0,2}?"
    r"(?:бер[её]т|берут|возьм\w+|взять|бь[её]т|бьют|побь\w+|побить|сыгра\w+|игра(?:ет|ют)|пойд\w+|пойти|ид[её]т|идут|ход(?:ит|ят)|"
    r"жертву\w+|пожертв\w+|отвеча\w+|ответ(?:ит|ят|ить)|забира\w+|забер\w+|забрать|уход\w+|уйд\w+|уйти|отступ\w+|"
    r"takes?|captures?|plays?|replies|answers?|goes|moves?)(?![а-яa-z])", re.IGNORECASE)
_I_MOVED = re.compile(r"(?<![а-яa-z])я\s+(?:[а-яa-z]+\s+)?(?:пош[её]л|сходил|сыграл\w*|взял\w*|побил\w*|поставил\w*|отош[её]л|"
                      r"уш[её]л|отступил\w*|сделал\w*\s+ход|i\s+(?:played|moved|took))(?![а-яa-z])", re.IGNORECASE)


def student_side(ctx: Optional[CheckContext], sentence: str = "") -> Optional[bool]:
    """The student's colour: known in a game; outside one the side to move on the board on the screen — unless the
    question or *sentence* tells a move of the other side or the student's own last move (then not known)."""
    if ctx is None:
        return None
    if ctx.student_color is not None:
        return ctx.student_color
    if ctx.current is None:
        return None
    for told in (ctx.question or "", (sentence or "").lower().replace("ё", "е")):
        if _THIRD_MOVE.search(told) or _I_MOVED.search(told):
            return None
    return ctx.current.turn


def _tells_line(rest: str) -> bool:
    """More than one written move after the student's move told in the second person («Здесь ты играешь Qxd5+, и
    после Qxd5 партия переворачивается»): the opponent's answer is told too — a line, not advice."""
    converted, _ = _to_san(rest)
    moves = [m for m in _MOVE.finditer(converted)
             if m["san"][0] in "KQRBNO" or m["num"] or m["bdots"] or "x" in m["san"]]
    return len(moves) > 1


def _review_asked(ctx: CheckContext) -> bool:
    """«Разбери мою партию, где я ошибся?»: «здесь ты играешь Qxd5+» tells the student's own game."""
    from src.intent import _REVIEW

    return bool(_REVIEW.search(ctx.question_raw or ctx.question or ""))


def proposed_move(sentence: str, ctx: Optional[CheckContext]) -> Optional[tuple]:
    """The move the coach recommends to the side to move on the board on the
    screen: (board, move, san), or None. In notation («Rg1», «Лg1») or in words
    («поставь ладью на g1»). A sentence that refutes a move («Rg1 сыграть
    нельзя»), or says not to play it, recommends nothing. The move the student
    asked about («А если Be7+?») is looked at, not advised — «Ход Be7+ даёт шах:
    слон бьёт по королю» describes it — unless the sentence recommends it in so
    many words («Be7+ — хороший ход», «лучше Be7+»)."""
    found = _proposed_move(sentence, ctx)
    if found and ctx.quoted and not _RECOMMENDS.search(sentence.replace("ё", "е")):
        bare = found[2].rstrip("+#").replace("x", "")
        if bare in {q.rstrip("+#").replace("x", "") for q in ctx.quoted}:
            return None
    return found


def _proposed_move(sentence: str, ctx: Optional[CheckContext]) -> Optional[tuple]:
    if ctx is None or ctx.current is None or not sentence:
        return None
    text = sentence.replace("ё", "е")
    if _DENIES.search(text):
        return None
    # «Первый ход — **Bxh4**», «Здесь решает Nf6+!»: the answer to a task is advice too — the engine never
    # saw these (production 07.10: Bxh4?? and Nf6+?? given as lesson solutions went out unchecked).
    converted_all, _ = _to_san(text)
    for mv in _MOVE.finditer(converted_all):
        if not _ANNOUNCED.search(converted_all[max(0, mv.start() - 45):mv.start()]):
            continue
        try:
            move = ctx.current.parse_san(mv["san"] + (mv["check"] or ""))
        except ValueError:
            break
        return ctx.current, move, ctx.current.san(move)
    starts = list(_PROPOSES.finditer(text))
    you_play = _YOU_PLAY.match(text)
    if you_play and "?" not in text and not _FAILS.search(text) and not _REPLY.search(text) \
            and student_side(ctx, text) == ctx.current.turn and not _tells_line(text[you_play.end():]) \
            and not _review_asked(ctx):
        starts.insert(0, you_play)
    for m in starts:
        if _NEGATION.search(text[max(0, m.start() - 24): m.start()]):
            continue  # «не стоит играть Rg1», "don't play Rg1"
        clause = text[m.end():]
        end = _PROPOSAL_END.search(clause)
        if end:
            clause = clause[: end.start()]
        clause = clause[:90]
        converted, _ = _to_san(clause)
        for mv in _MOVE.finditer(converted):
            san = mv["san"]
            if san[0] not in "KQRBNO" and not mv["num"] and not mv["bdots"] and "x" not in san \
                    and not _PAWN_MOVE_WORDS.search(converted[max(0, mv.start() - 24): mv.start()]) \
                    and not re.fullmatch(r"[\s—–:\-]*(?:здесь\s+|сейчас\s+|here\s+|now\s+)?", converted[: mv.start()]):
                continue  # «e4» is a square («пешка e5 висит») unless a pawn is told to go there («пешкой: g6», "pawn to e4») or it is the move itself («лучше d4»)
            if _EXPLORES.fullmatch(m.group(0).strip()) and san.replace("x", "") in {q.replace("x", "") for q in ctx.quoted}:
                continue  # «Сыграем Be7+ и посмотрим», «можно Be7+»: the student's own idea looked at, not advice
            try:
                move = ctx.current.parse_san(san + (mv["check"] or ""))
            except ValueError:
                continue
            if m is you_play and (ctx._key(ctx.current), move.uci()) in ctx.line_next:
                break  # the game's or the line's own next move, told in the present: narration, not advice
            return ctx.current, move, ctx.current.san(move)
        try:
            from src.move_words import prose_moves

            for pm in prose_moves(clause, ctx.current):
                if pm["move"] is not None:
                    if m is you_play and (ctx._key(ctx.current), pm["move"].uci()) in ctx.line_next:
                        break
                    return ctx.current, pm["move"], pm["san"]
        except Exception:  # noqa: BLE001 — words are a bonus on top of notation
            logger.debug("prose move parse failed", exc_info=True)
    converted, _ = _to_san(text)
    for mv in _MOVE.finditer(converted):
        san = mv["san"]
        if san[0] not in "KQRBNO" and not mv["num"] and not mv["bdots"] and "x" not in san:
            continue
        # «**Kxb3!** — единственный ход» (production 09.10, a losing king move): a move marked «!» or «!!» is
        # the coach's choice too.
        exclaimed = re.match(r"[*_]*!{1,2}(?![?])", converted[mv.end():])
        if not (_PRAISED.match(converted, mv.end()) or exclaimed) or _NEGATION.search(converted[max(0, mv.start() - 24): mv.start()]):
            continue
        try:
            move = ctx.current.parse_san(san + (mv["check"] or ""))
        except ValueError:
            continue
        return ctx.current, move, ctx.current.san(move)
    # A move with what it wins after it, in notation or in words («если конь прыгнет
    # на f7 — он бьёт ладью и ферзя»): the coach's idea, checked like advice.
    candidates = []
    for mv in _MOVE.finditer(converted):
        san = mv["san"]
        if san[0] in "KQRBNO" or mv["num"] or mv["bdots"] or "x" in san \
                or _PAWN_MOVE_WORDS.search(converted[max(0, mv.start() - 24): mv.start()]):
            candidates.append((mv.end(), san + (mv["check"] or ""), None, mv.start()))
    try:
        from src.move_words import prose_moves

        for pm in prose_moves(text, ctx.current):
            if pm["move"] is not None:
                at = text.lower().replace("ё", "е").find(pm["words"].lower())
                candidates.append((at + len(pm["words"]) if at >= 0 else 0, pm["san"], pm["move"], max(at, 0)))
    except Exception:  # noqa: BLE001
        logger.debug("prose move parse failed", exc_info=True)
    # Written moves before a candidate make it a step of a line («после ...Nxg6 следует Bf7+ —
    # и мат»), judged in that line, not advice on this board (production 2026-10-07).
    written_before = [mv.end() for mv in _MOVE.finditer(converted)
                      if mv["num"] or mv["bdots"] or mv["san"][0] in "KQRBN" or "x" in mv["san"]]
    for end, san, move, start in sorted(candidates, key=lambda c: c[0]):
        if any(e <= start for e in written_before):
            continue
        if ctx.student_color is not None and ctx.current.turn == ctx.student_color \
                and _COACH_OWN_PIECE.search(text[max(0, start - 30): start] + " " + converted[max(0, start - 30): start]):
            continue  # «моя пешка на f6 забирает твоего слона» in a game: the engine's pawn told, not advice (prod Live 29.10)
        tail = text[end: end + 90]
        cut = re.search(r"[.;!?\n]|\s(?:но|а\s+не|однако|but|however)(?![а-яa-z])", tail)
        tail = tail[: cut.start()] if cut else tail
        if not _PRAISE.search(tail) or _NEGATED_WORD.search(tail[: _PRAISE.search(tail).start()]):
            continue
        if move is None:
            try:
                move = ctx.current.parse_san(san)
            except ValueError:
                continue
        if san.replace("x", "") in {q.replace("x", "") for q in ctx.quoted} and not _PRAISE.search(tail):
            continue
        return ctx.current, move, ctx.current.san(move)
    return None


# «Моя пешка на f6…», «мой конь c6…»: in a game against the coach, the coach's own (the engine's) piece.
_COACH_OWN_PIECE = re.compile(r"(?<![а-яё])мо(?:й|я|е|ё|и)\s+(?:пешк\w*|кон\w*|слон\w*|ладь\w*|ферз\w*|корол\w*)\s+(?:на\s+|с\s+)?$",
                              re.IGNORECASE)


# The move named as the answer to the task: «Первый ход — **...Rxf3!**», «Здесь решает 1...Qh1+!», "The key
# move is Nf6+". On production 07.10 four of 187 lesson puzzles were answered from a diagram of the lesson's
# text — another position, often for the other side («1...Ba6!» with White to move) — and the check, which
# reads a bare capture or a numbered move as a step of some line, let them through.
_ANNOUNCED = re.compile(
    r"(?:(?<![а-яa-z])(?:перв\w*\s+ход\w*|решает|решающ\w+\s+ход|решени\w*|лучш\w+\s+ход\w*|ключев\w+\s+ход\w*|"
    r"(?:спасает|выигрывает|держит|решает)\s+(?:здесь\s+|тут\s+)?(?:только\s+|лишь\s+)?(?:один|единственн\w+)\s+ход|"
    r"только\s+один\s+ход|единственн\w+\s+(?:ход|спасение|защита)|"
    r"начина\w*\s+с|начн\w*\s+с)(?:\s+(?:здесь|тут|в\s+задаче|в\s+этой\s+позиции|бел\w*|ч[её]рн\w*|за\s+\w+|for\s+\w+)){0,2}|"
    r"\b(?:first|key|winning|best)\s+move(?:\s+is)?|\bthe\s+solution(?:\s+is)?)\s*(?:[—–:-]|это|is)?\s*[*_]*\s*$",
    re.IGNORECASE)


def _announced_move_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    converted, _ = _to_san(text)
    for mv in _MOVE.finditer(converted):
        if not _ANNOUNCED.search(converted[max(0, mv.start() - 45):mv.start()]):
            continue
        san = mv["san"]
        if san[0] not in "KQRBNO" and "x" not in san and not mv["num"] and not mv["bdots"]:
            return []  # «первый ход — e4» may be a square of a plan; only clear moves are judged
        black = bool(mv["bdots"] or (mv["dots"] in ("...", "…")))
        white = bool(mv["num"] and mv["dots"] == ".")
        for board in ctx.boards:
            # A position of the turn the student sees or the answer reaches: the board, what a tool put on it, a
            # game, a line the answer wrote — not one only named in a tool's text (a lesson's diagram).
            if (black and board.turn != chess.BLACK) or (white and board.turn != chess.WHITE):
                continue
            key = ctx._key(board)
            if key in ctx.text_keys and key not in ctx.shown_keys and ctx.is_given(board):
                continue
            if board.board_fen() == chess.STARTING_BOARD_FEN and ctx.current.board_fen() != chess.STARTING_BOARD_FEN:
                continue  # «Первый ход здесь 1.e4» on a mating puzzle (production 09.10): the start stands in for nothing here
            try:
                board.parse_san(san)
                return []
            except ValueError:
                continue
        side = "White" if ctx.current.turn == chess.WHITE else "Black"
        label = (mv["num"] or "") + (mv["dots"] or mv["bdots"] or "") + san
        return [f"{label} is not a move of the position on the board ({side} to move there): the answer must name a "
                f"legal move of that position, not one from another diagram"]
    return []


ECHO_ISSUE = "this sentence repeats the student's question word for word; it is not an answer"


def _echoes_question(sentence: str, ctx: CheckContext) -> bool:
    """«Покажи на доске оперную партию Морфи…» as the answer's first line (production 08.10)."""
    norm = lambda t: re.sub(r"[^а-яёa-z0-9]+", " ", (t or "").lower()).strip()
    s = norm(sentence)
    if len(s) < 20:
        return False
    return any(norm(q) == s for q in re.split(r"(?<=[.!?])\s+", ctx.question_raw or "") if q)


# The coach says it made a move: «я ответил Кc6», «отвечаю e5», «мой ход — d5», "I play Nf6".
_COACH_MOVE = re.compile(
    r"(?:(?<![\w-])я\s+(?:тоже\s+|сразу\s+|просто\s+)?(?:отвечаю|ответил[аи]?|играю|сыграл[аи]?|пош[её]л|пойду|иду|хожу|с?делаю\s+ход)"
    r"|(?:^|[.!—–:]\s*)(?:отвечаю|ответил[аи]?|хожу|иду|пойду|сыграю|ставлю|беру|бью)(?![а-я])"
    r"|(?<![\w-])мой\s+(?:первый\s+|следующий\s+|очередной\s+|последний\s+|предыдущий\s+)?(?:ответ|ход)"
    r"(?:\s+был)?\s*(?:[—–:-]|это|будет)?"
    # the engine's opening move told (prod Live run 28.10: «Мой первый ход — пешка на е4» when it opened 1.Nf3)
    # («начну с того, что…» is not a move: «с» counts only right before one)
    # (the past only with «я» / «движок»: «белые начали с e4» in an example is not the game's move)
    r"|(?<![\w-])(?:(?:я|движок|компьютер)\s+(?:начал[аи]?|открыл[аи]?)|(?:я\s+)?(?:начинаю|начну|открываю))"
    r"(?:\s+партию)?\s+(?:ходом|с\s+хода"
    r"|с(?=\s+(?:(?:пешк|кон|слон|лад|ферз|корол)\w*\s+(?:на\s+)?)?[a-h][1-8](?!\w)))"
    r"|(?<![\w-])i\s+(?:play|played|answer|answered|reply|replied|open(?:ed)?\s+with|start(?:ed)?\s+with)"
    r"|(?<![\w-])my\s+(?:first\s+|next\s+|last\s+|previous\s+)?(?:reply|move|answer)\s+(?:is|was)?)"
    r"(?![^.!?]*\bбы\b)(?P<rest>[^.!?;]{0,40})",
    re.IGNORECASE,
)


# «2...Nc6», «3.d4»: the move number before a move. The claims below read up to the first dot, so «Мой последний ход
# был 2...Nc6» (the student's move) came through as «2» once the coach got the moves numbered (stand run 28.10).
_MOVE_NUMBER = re.compile(r"(?<![\w.])\d{1,3}\s?(?:\.\.\.|…|\.)\s?(?=[KQRBNOКФЛСa-h])")


# «Мой ответ: 4.e4» when the game's record has 3.e4 (prod text game 28.10: three numbers in a row one too high).
_NUMBERED_CLAIM = re.compile(
    r"(?:(?<![\w-])мой\s+(?:\w+\s+)?(?:ответ|ход)(?:\s+был)?|(?<![\w-])я\s+(?:ответил[аи]?|сыграл[аи]?|пош[её]л|отвечаю|играю|хожу)"
    r"|(?<![\w-])my\s+(?:\w+\s+)?(?:reply|move|answer)\s+(?:is|was)|(?<![\w-])i\s+(?:played|answered|replied))"
    r"\s*[—–:-]?\s*(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?"
    r"(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?|O-O-O|O-O)",
    re.IGNORECASE)


# «Принято, твой ход d4» for the engine's 2.d4 (stand voice run 28.10): a move called the student's must be theirs.
_YOUR_MOVE = re.compile(
    r"(?<![\w-])(?:тво[йя]|ваш)\s+(?:последн\w+\s+|предыдущ\w+\s+)?ход(?:\s+был)?\s*[—–:-]?\s*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?"
    r"(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?|O-O-O|O-O)"
    r"(?=[\s.,!?;:)—–-]|$)", re.IGNORECASE)


def _students_move_issues(text: str, ctx: "CheckContext") -> list[str]:
    moves = getattr(ctx, "game_moves", None)
    if not moves or ctx.student_color is None:
        return []
    first = 0 if ctx.student_color == chess.WHITE else 1
    student = [m.rstrip("+#") for i, m in enumerate(moves) if i % 2 == first]
    engine = [m.rstrip("+#") for i, m in enumerate(moves) if i % 2 != first]
    out = []
    for m in _YOUR_MOVE.finditer(text):
        san = m.group("san")
        if san in engine[-2:] and (not student or san != student[-1]):
            out.append(f"{san} was the engine's (your) move, not the student's"
                       + (f" — the student's last move was {student[-1]}" if student else "")
                       + ": never give the student a move the engine made")
    return out


def _move_number_issues(text: str, played: list, student_color) -> list[str]:
    """The number the coach gives its own move must be the move's number in the game (a game from the start)."""
    if student_color is None:
        return []
    engine_white = student_color == chess.BLACK
    out = []
    for m in _NUMBERED_CLAIM.finditer(text):
        san = m.group("san")
        idx = next((i for i in range(len(played) - 1, -1, -1) if played[i].rstrip("+#") == san), None)
        if idx is None:
            continue  # not the engine's move at all: the rule below says so
        num, black_dots = int(m.group("num")), m.group("dots") in ("...", "…")
        if num != idx + 1 or black_dots == engine_white:
            right = f"{idx + 1}{'.' if engine_white else '...'}{san}"
            out.append(f"in this game your move {san} was {right}, not {m.group('num')}{m.group('dots')}{san}: "
                       "number the game's moves as its record does")
    return out


# «Моя пешка на e7 забрала ферзя» when the pawn only attacked it (prod Live run 29.10: the queen was taken a move
# later), «я забрал твоего коня»: a capture the coach says it made must be one the engine made in this game.
_INSTR = r"(?:пешкой|кон[её]м|слоном|ладь[её]й|ферз[её]м|корол[её]м)"
_COACH_TOOK = re.compile(
    r"(?:(?<![а-яё])мо(?:й|я|е|ё)\s+(?P<piece>пешк\w*|кон\w*|слон\w*|ладь\w*|ферз\w*|корол\w*)(?:\s+(?:на|с)\s+[a-h][1-8])?"
    r"|(?<![а-яё])я)\s+(?:только\s+что\s+|уже\s+|сразу\s+|просто\s+|тоже\s+)?"
    rf"(?:забрал\w*|побил\w*|взял\w*|съел\w*|сбил\w*)\s+(?:(?P<inst>{_INSTR})\s+)?(?:тво\w+\s+|ваш\w+\s+)?"
    # the taken piece in the accusative only («взял конём пешку»: конём is the taker)
    r"(?P<target>пешку|пешки|коня|коней|слона|слонов|ладью|ладьи|ферзя)(?:\s+на\s+(?P<tsq>[a-h][1-8]))?"
    rf"(?:\s+(?P<inst2>{_INSTR}))?(?![а-яё])", re.IGNORECASE)
# Not this game's capture: a wish or a purpose («чтобы я взял»), a question, the student's words quoted, another game.
_NOT_TOLD = re.compile(r"(?<![а-яё])(?:если|бы|чтобы|можешь|могу|может|хотел\w*|пишешь|спрашиваешь|говоришь|сказал\w*|решил\w*|"
                       r"счита\w*|(?:по)?дума\w*|показал\w*|кажется|будто|якобы|неправда|неверно|написал\w*|имеешь\s+в\s+виду|прошл\w*|предыдущ\w*|вчера|раньше|откат\w*|отменил\w*|вернул\w*|"
                       r"похож\w*|друг\w+\s+парти\w*|т(?:ой|ую|ом)\s+парти\w*|перв\w+\s+парти\w*|представ\w*|допуст\w*|предполож\w*|"
                       r"вообраз\w*|по-твоему|уверен\w*|ход\s+назад|друг\w+\s+игр\w*|позапрошл\w*|тогда|в\s+тот\s+момент|на\s+тот\s+момент|"
                       r"до\s+этого|перед\s+этим|спросил\w*|утвержда\w*|например|в\s+вариант\w*|обратно|отмен\w*|переигра\w*|вернуть|"
                       r"говорил\w*|по\s+тво\w+\s+слов\w*|жалу\w*|возмущ\w*|переход\w*|верси\w*|стар\w+\s+парти\w*|рестарт\w*|бросил\w*|"
                       r"сесси\w*|начали\s+(?:нов\w*|заново)|т(?:ой|ую|ом)\s+игр\w*|перв\w+\s+игр\w*|старой)(?![а-яё])",
                       re.IGNORECASE)
# «взял коня в связку», «взял пешку под защиту / на прицел»: a pin, a defence, a target — not a capture
_TOOK_IDIOM = re.compile(r"(?:\s+[a-h][1-8])?\s*,?\s*(?:в|во|под|на)\s+(?:связк|защит|прицел|обстрел|заметк|наблюден|оборот|контрол|вилк|"
                         r"тиск|клещ|атак|удар|бо[йея]|давлени|мушк|рентген|прикрыти|охран|опек|присмотр|расч[её]т)", re.IGNORECASE)
_TOOK_TYPE = (("пешк", chess.PAWN), ("кон", chess.KNIGHT), ("слон", chess.BISHOP), ("ладь", chess.ROOK),
              ("ферз", chess.QUEEN), ("корол", chess.KING))


def _took_type(word: str) -> Optional[int]:
    word = (word or "").lower()
    return next((t for k, t in _TOOK_TYPE if word.startswith(k)), None)


def _coach_capture_issues(text: str, ctx: CheckContext) -> list[str]:
    moves = getattr(ctx, "game_moves", None)
    if not moves or ctx.student_color is None or "?" in text or "«" in text or '"' in text:
        return []
    claims = [m for m in _COACH_TOOK.finditer(text) if not _NOT_TOLD.search(text[max(0, m.start() - 40):])
              and not _TOOK_IDIOM.match(text, m.end())
              and not re.search(r"(?<![а-яё])(?:в|во|под|на)\s+(?:связк|прицел|обстрел|вилк|контрол|давлени|мушк|удар|тиск|клещ|"
                                r"прикрыти|охран|опек|присмотр|расч[её]т|рентген)",
                                text[m.end():m.end() + 40], re.IGNORECASE)]
    if not claims:
        return []
    board, taken = chess.Board(), []
    try:
        for san in moves:
            move = board.parse_san(san)
            if board.turn != ctx.student_color and board.is_capture(move):
                squares = {chess.square_name(move.to_square)}
                if board.is_en_passant(move):
                    victim = chess.PAWN
                    squares.add(chess.square_name(move.to_square + (-8 if board.turn == chess.WHITE else 8)))
                else:
                    victim = board.piece_type_at(move.to_square)
                takers = {board.piece_type_at(move.from_square)} | ({move.promotion} if move.promotion else set())
                taken.append((takers, victim, squares))
            board.push(move)
    except ValueError:
        return []  # a game from another start: not judged
    out = []
    for m in claims:
        piece = _took_type(m["piece"]) or _took_type(m["inst"]) or _took_type(m["inst2"])
        target = _took_type(m["target"])
        if target is None:
            continue
        if not any((piece is None or piece in takers) and t == target and (not m["tsq"] or m["tsq"] in sqs)
                   for takers, t, sqs in taken):
            what = f"{_NAMES[target]}" + (f" on {m['tsq']}" if m["tsq"] else "") + (f" with a {_NAMES[piece]}" if piece else "")
            out.append(f"in this game the engine never captured a {what}: never say you took what the game did not record")
    return out


def _coach_move_issues(text: str, ctx: CheckContext) -> list[str]:
    """In a game, a move the coach says it made must be one the engine made."""
    played = ctx.game_engine_moves
    if played is None:
        return []
    out = _move_number_issues(text, played, ctx.student_color) + _students_move_issues(text, ctx) + _coach_capture_issues(text, ctx)
    text = _MOVE_NUMBER.sub("", text)
    norm = {m.rstrip("+#") for m in played}
    for m in _COACH_MOVE.finditer(text):
        sans, _ = _to_san(m.group("rest"))
        named = [x.group("san").rstrip("+#") for x in _MOVE.finditer(sans)]
        mover = _spoken_mover(m.group("rest"))  # «беру ферзём на c6» is not Bxc6
        if named and not any(_same_move(n, p) and (mover is None or _piece_of(p) == mover) for n in named for p in norm):
            last = played[-1] if played else None
            out.append(f"in this game the engine plays your moves and it did not play {named[0]}"
                       + (f" (its last move was {last})" if last else "")
                       + ": never say you made a move the game did not record")
    if played and not out:
        last = played[-1].rstrip("+#")
        for wrong in _last_move_issues(text, last):
            out.append(f"in this game the engine plays your moves and its last move was {last}, not {wrong}: "
                       "never announce a move the game did not play")
    return out

# The move itself first: «3.d3», «Bc4», «Кf6», «конь на f6», «пешка d6» — not «конь с g8…», «защита e5».
_MOVE_FIRST = re.compile(r"\s*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?(?:[KQRBNКФЛС][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8]|O-O|0-0|"
                         r"(?:конь|слон|ладья|ферзь|пешка|король|knight|bishop|rook|queen|pawn|king|the\s+\w+)\s+(?:на\s+|to\s+)?[a-h][1-8])(?![\w-])",
                         re.IGNORECASE)


# Two claims checked against the engine's LAST move (Alexander 27.10), on top of the rule above:
# «Мой ответ — конь на f6» (an announcement: a dash, a colon, «это», «будет» right after «мой ответ / мой ход»)…
# («Мой последний ход — Bc4 от белых» when it was 3.d3: prod text game 29.10 — the last move is the game's last one.)
# («Мой ход был Кc6» may recap an earlier move: «был» only with «последний».)
_MY_REPLY = re.compile(r"(?<![\w-])(?:мой\s+(?:первый\s+|следующий\s+)?(?:ответ|ход)|мой\s+последний\s+(?:ответ|ход)(?:\s+был)?"
                       r"|my\s+(?:first\s+|next\s+)?(?:reply|move|answer)|my\s+last\s+(?:reply|move|answer)(?:\s+was)?)"
                       r"\s*(?:[—–:]|-\s|это\s|будет\s|is\s|(?<=был)\s|(?<=was)\s)"
                       # «Мой последний ход был ответом на твоего слона b5 — a6»: the move answered is not the move made
                       r"(?!\s*(?:ответ\w*|против|в\s+ответ|защит\w*\s+от|an?\s+answer|a\s+reply|against|не|вовсе\s+не|not)(?![а-яёa-z]))"
                        r"(?P<rest>[^.!?;,]{0,30})", re.IGNORECASE)
# …and «Я забираю его слоном» (a capture by a named piece, no square).
_TAKES_WITH = re.compile(r"(?<![\w-])(?:я\s+)?(?:забираю|беру|бью|съедаю)\s+(?:(?:его|е[её]|их|эт[уо]\w*|пешку|коня|слона|ладью|ферзя)\s+)?"
                         r"(?P<sq1>на\s+[a-h][1-8]\s+)?"
                         r"(?P<piece>слоном|кон[её]м|ладь[её]й|ферз[её]м|корол[её]м|пешкой)(?![а-я])(?P<rest>[^.!?;]{0,30})", re.IGNORECASE)
_NOMINATIVE = {"конь": "N", "слон": "B", "ладья": "R", "ферзь": "Q", "король": "K", "пешка": "P",
               "knight": "N", "bishop": "B", "rook": "R", "queen": "Q", "king": "K", "pawn": "P"}
_INSTRUMENTAL = {"слоном": "B", "конем": "N", "ладьей": "R", "ферзем": "Q", "королем": "K", "пешкой": "P"}


def _spoken_mover(rest: str) -> Optional[str]:
    """The piece that moved, as speech names it: «…слоном», or «конь на f6» right before the square."""
    low = rest.lower().replace("ё", "е")
    found = list(re.finditer(r"(?<![а-я])(слоном|конем|ладьей|ферзем|королем|пешкой)(?![а-я])", low))
    if found:
        # the one nearest the square («отвечаю на твой ход слоном пешкой a6» — the pawn moved)
        square = re.search(r"[a-h][1-8]", low)
        before = [f for f in found if square and f.start() < square.start()]
        return _INSTRUMENTAL[(before[-1] if before else found[0]).group(1)]
    m = re.match(r"\s*([а-яa-z]+)\s+(?:на\s+|to\s+)?[a-h][1-8]", low)
    return _NOMINATIVE.get(m.group(1)) if m else None


def _piece_of(san: str) -> str:
    return "K" if san.startswith("O") else (san[0] if san[:1] in ("K", "Q", "R", "B", "N") else "P")


_LINE_BEFORE = re.compile(r"(?<![а-яa-z])(?:если|в случае|когда|if|when)(?![а-яa-z])|(?<![а-я])ты\s+[а-я]+(?:ешь|ишь)(?![а-я])")


def _in_a_line(text: str, at: int) -> bool:
    """«если ты возьмёшь…, я заберу», «ты берёшь на c6 — я забираю пешкой»: a line, not the move just made."""
    return bool(_LINE_BEFORE.search(re.split(r"[.!?]", text[:at])[-1].lower().replace("ё", "е")))


# …and castling said in words (28.10): «Я рокируюсь», «Мой ход — длинная рокировка», "I castle kingside".
_SIDE_RU = r"(?:(?P<{0}>коротк\w*|длинн\w*)\s+)?"
_SIDE_EN = r"(?:\s+(?P<{0}>kingside|queenside|short|long))?"
_MY_CASTLING = re.compile(
    r"(?<![\w-])(?:"
    r"я\s+(?:тоже\s+|сразу\s+|просто\s+|сейчас\s+|теперь\s+)?(?:рокируюсь|делаю\s+" + _SIDE_RU.format("s1") + r"рокировку)"
    r"(?:\s+(?:в|на)\s+(?P<s5>длинн\w*|коротк\w*|ферзев\w*|королев\w*)\s+(?:сторон|фланг)\w*)?"
    r"|мой\s+(?:ход|ответ)\s*(?:[—–:]|-\s|это\s|будет\s)\s*" + _SIDE_RU.format("s2") + r"рокировка"
    r"|i\s+(?:now\s+)?castle(?![a-z])" + _SIDE_EN.format("s3")
    + r"|my\s+(?:move|reply|answer)\s+(?:is\s+|:\s*)(?:to\s+)?castl\w*" + _SIDE_EN.format("s4")
    + r")(?![а-яa-z])",
    re.IGNORECASE)
# Not the move just made: later, usually, if, in such openings, a wish (the clause around the claim).
_NOT_NOW = re.compile(r"(?<![а-яa-z])(?:скоро|потом|позже|позднее|затем|дальше|следом|следующ\w*|обычно|всегда|часто|никогда|"
                      r"рано|бы|если|когда|как\s+правило|схем\w*|дебют\w*|партиях|таких|later|soon|next|then|usually|"
                      r"always|often|never|early|would|could|should|if|when|unless|most|games|openings?|systems?|such|"
                      # a plan, not the move just made: «после Nf3 я рокируюсь», «только после того, как разовью коня»,
                      # «сначала…», «хочу», «в ближайшее время», "after", "before", "once", "going to" (review 28.10)
                      r"после|до|перед|только|сначала|как\s+только|хочу|хотел\w*|планир\w*|собира\w*|ближайш\w*|"
                      r"after|before|once|first|plan\w*|want\w*|going|until)(?![а-яa-z])",
                      re.IGNORECASE)


def _castling_issues(text: str, last: str) -> list[str]:
    out = []
    for m in _MY_CASTLING.finditer(text):
        if _in_a_line(text, m.start()):
            continue
        before = re.split(r"[.!?;,]", text[:m.start()])[-1]
        after = re.match(r"[^.!?;]*[.!?;]?", text[m.end():]).group(0)
        if _NOT_NOW.search(before + " " + after) or after.rstrip().endswith("?"):
            continue
        side = next((g for g in m.group("s1", "s2", "s3", "s4", "s5") if g), "").lower()
        want = ("O-O-O",) if side.startswith(("длин", "ферз", "queen", "long")) else ("O-O",) if side else ("O-O", "O-O-O")
        if last not in want:
            out.append(want[0] if side else "castling")
    return out


def _last_move_issues(text: str, last: str) -> list[str]:
    text = _MOVE_NUMBER.sub("", text)
    out = _castling_issues(text, last)
    for m in _MY_REPLY.finditer(text):
        if _in_a_line(text, m.start()):
            continue
        # «e7–e5», «e5:d4» — no spaces: «d6: e5 теперь под защитой», «Nf6 — e4 под ударом» explain the move
        rest = re.sub(r"([KQRBNКФЛС]?)[a-h][1-8][–—:]([a-h][1-8])", r"\1\2", m.group("rest"))
        if re.search(r"последн|last", m.group(0), re.IGNORECASE) and (not _MOVE_FIRST.match(rest) or _NOT_TOLD.search(text)
                                                                      or "?" in text or "«" in text):
            continue  # «Мой последний ход — конь с g8 на f6», «… — защита пешки e5»: a recap, not a move named (review 29.10)
        sans, _ = _to_san(rest)
        named = [x.group("san").rstrip("+#") for x in _MOVE.finditer(sans)]
        if not named:
            continue
        lead = re.match(r"\s*([а-яa-z]+)\s+(?:на\s+|to\s+)?[a-h][1-8]", rest.lower().replace("ё", "е"))
        piece = _NOMINATIVE.get(lead.group(1)) if lead else None
        if not (_same_move(named[0], last) and (piece is None or _piece_of(last) == piece)):
            out.append(named[0])
    for m in _TAKES_WITH.finditer(text):
        if _in_a_line(text, m.start()):
            continue
        piece = _INSTRUMENTAL[m.group("piece").lower().replace("ё", "е")]
        square = re.search(r"[a-h][1-8]", (m.group("sq1") or "") + m.group("rest"))
        took = "x" in last and _piece_of(last) == piece and (square is None or last.endswith(square.group(0)))
        if not took:
            out.append(f"a capture with that piece ({piece})" + (f" on {square.group(0)}" if square else ""))
    return out


def _same_move(named: str, played: str) -> bool:
    """*named* (as read from speech) is *played*: the same SAN, or the same target square when speech lost the piece
    («конём f6» reads as «f6») or the piece agrees."""
    named, played = named.rstrip("+#"), played.rstrip("+#")
    if named == played:
        return True
    if played in ("O-O", "O-O-O"):
        # the king's own step of a castling: «король на g8, рокировка» when the engine played O-O (28.10)
        squares = ("g1", "g8") if played == "O-O" else ("c1", "c8")
        return named.lstrip("K") in squares and named[:1] in ("K", "g", "c")
    to_n, to_p = re.findall(r"[a-h][1-8]", named), re.findall(r"[a-h][1-8]", played)
    if not to_n or not to_p or to_n[-1] != to_p[-1]:
        return False
    piece_n = named[0] if named[0] in "KQRBN" else None
    piece_p = played[0] if played[0] in "KQRBN" else None
    return piece_n is None or piece_n == piece_p


# What stands on the board now, named as a whole: «Здесь позиция «король против короля»», «На доске король и
# пешка против короля», «там пустая доска, только два короля», «здесь уже эндшпиль». Judged only when the sentence
# ties it to the board as it is (a now-word before it) — «Ладья против короля — всегда выигрыш» is a rule, «разберём
# эндшпиль ладья против короля?» an offer (prod 29.10: «ладью с королём против короля пора бы уже дожать» on the
# start position was about the student's study plan, not the board — no now-word, not judged). «Это» is not a
# now-word: «Это позиция Филидора: ладья и пешка против ладьи», «Это эндшпиль, который обязан знать каждый» name
# the topic asked (review 30.10).
# Each piece word ends at a word end and the joints are whole words: «корольикороль…» cannot be split in
# exponentially many ways (review 30.10: 6.6 s on 165 characters before).
_COMP_PIECE = (r"(?:корол\w*|ферз\w*|лад(?:ья|ьи|ью|ьей|ьёй|ье|ей|ьям|ьями)|слон\w*|кон(?:ь|я|ем|ём|ю|е|и|ей|ям|ями)|"
               r"пеш(?:ка|ки|ку|кой|ке|ек|кам|ками))(?![а-яёa-z0-9])")
_COMP_NUM = r"(?:одн\w*|один|дв(?:а|е|ух|умя)|тр(?:и|ех|ёх|емя|ёмя)|четыр\w*|\d)"
_COMP_SIDE = (rf"(?:(?:{_COMP_NUM}\s+)?(?:гол[оы]\w+\s+|одинок\w+\s+|лишн\w+\s+)?{_COMP_PIECE}"
              rf"(?:(?:\s+(?:и|с|со|плюс)\s+|\s*\+\s*)(?:{_COMP_NUM}\s+)?{_COMP_PIECE})*)")
_COMP_ANCHOR = r"(?:здесь|тут|на\s+доске|в\s+этой\s+позиции|перед\s+нами|сейчас|позиция[^.!?;:]{0,12}:|там)"
# The sides named are the whole board only with a king among them («ладья против короля», «король и пешка против
# короля») or a word that says so («только», «чистый», «голый»): «конь против слона», «ладья против слона — ты
# выиграл качество» is the imbalance with the rest equal and cancelled out, not the whole board (review 30.10).
_COMP_WHOLE = re.compile(r"корол|гол[оы]\w|одинок", re.IGNORECASE)
_COMP_STRICT = re.compile(_B2 + r"(?:только|лишь|чист\w*)" + _E, re.IGNORECASE)
# Another moment or another game: «в той партии в конце остались только два короля», «был эндшпиль» (review 30.10).
_COMP_ELSEWHERE = re.compile(
    _B2 + r"(?:был|была|было|были|остал(?:ись|ось|ся|ась)|получил(?:ись|ось|ся|ась)|возник\w*|(?:в|из)\s+(?:\w+\s+)?"
    r"парти(?:и|ях|й)|had|was|were|in\s+(?:that|the|this|his|her|their)\s+game)" + _E, re.IGNORECASE)
_COMPOSITION = re.compile(
    _B2 + _COMP_ANCHOR + r"(?![а-яa-z])[^.!?;:]{0,40}?[«\"]?(?P<a>" + _COMP_SIDE + r")\s+против\s+(?P<b>" + _COMP_SIDE + r")[»\"]?" + _E,
    re.IGNORECASE)
# «Доска пустая, все фигуры на местах» (a new game: no moves yet) is an idiom — only kings named as all there is count.
_ONLY_KINGS = re.compile(_B2 + r"(?:только\s+(?:два\s+)?корол(?:я|и|ей)|одни\s+корол(?:и|ей))" + _E, re.IGNORECASE)
_ONLY_KINGS_ANCHOR = re.compile(_B2 + r"(?:на\s+доске|доск\w*|здесь|тут|там|сейчас)" + _E, re.IGNORECASE)
_ENDGAME_NOW = re.compile(
    _B2 + r"(?:здесь|тут|на\s+доске|сейчас)\s+(?:уже\s+|у\s+нас\s+|у\s+тебя\s+)?(?:чист\w+\s+)?эндшпил(?:ь|я)" + _E,
    re.IGNORECASE)
_COMP_TYPE = (("корол", chess.KING), ("ферз", chess.QUEEN), ("лад", chess.ROOK), ("слон", chess.BISHOP),
              ("кон", chess.KNIGHT), ("пеш", chess.PAWN))


def _comp_side(words: str) -> Optional[dict]:
    """«король и пешка» → {PAWN: 1} (kings left out), with "strict" when the side is bare («голый», «только»)."""
    out: dict = {}
    for m in re.finditer(rf"(?:(?P<n>{_COMP_NUM})\s+)?(?:гол[оы]\w+\s+|одинок\w+\s+|лишн\w+\s+)?(?P<p>{_COMP_PIECE})", words, re.IGNORECASE):
        pt = next(t for stem, t in _COMP_TYPE if m["p"].lower().startswith(stem))
        if pt != chess.KING:
            out[pt] = out.get(pt, 0) + _num(m["n"]) if m["n"] else out.get(pt, 0) + 1
    return out


def _side_fits(board: chess.Board, color: bool, want: dict, strict_pawns: bool) -> bool:
    for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
        if len(board.pieces(pt, color)) != want.get(pt, 0):
            return False
    pawns = len(board.pieces(chess.PAWN, color))
    if chess.PAWN in want:
        return pawns == want[chess.PAWN] or (pawns >= 1 and want[chess.PAWN] == 1 and not strict_pawns)
    return pawns == 0 or not strict_pawns


def _composition(board: chess.Board) -> str:
    def side(color: bool) -> str:
        parts = ["K"] + [f"{len(board.pieces(pt, color))}{chess.piece_symbol(pt).upper()}"
                         if len(board.pieces(pt, color)) > 1 else chess.piece_symbol(pt).upper()
                         for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT) if board.pieces(pt, color)]
        pawns = len(board.pieces(chess.PAWN, color))
        return " ".join(parts) + (f" + {pawns} pawn{'s' if pawns > 1 else ''}" if pawns else "")
    return f"White {side(chess.WHITE)}, Black {side(chess.BLACK)}"


def _composition_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    """«На доске король и пешка против короля», «там пустая доска, только два короля», «здесь уже эндшпиль»: the
    material named as the whole of the board now, against every position given to the turn (the board, what a tool
    put up). A rule, an offer, a question, a denial or a line is not judged, nor another moment or game, a named
    position («позиция Филидора»), or the composition or the endgame the student asked about — the topic, not the
    board («Расскажи про эндшпиль ферзь против ладьи»)."""
    if ctx.current is None or "?" in text or _is_hypothetical(text, original, 0, whole=True) \
            or _COMP_ELSEWHERE.search(text) or re.search(r"позици\w*\s+[А-ЯЁA-Z]", original) \
            or re.search(r"(?<![а-я])(?:против|эндшпил\w*)(?![а-я])", ctx.question or ""):
        return []
    given = [b for b in ctx.boards if ctx.is_given(b) and not _is_past(ctx, b)]
    given = [b for b in given if b is not ctx.boards[0] or b is ctx.current] or [ctx.current]
    issues = []
    # «Это два короля, король со слоном против короля, король с конём против короля…»: a list of cases (the rule
    # of the sentence before), not the board — one «против» or none judged.
    for m in (_COMPOSITION.finditer(text) if len(re.findall(r"(?<![а-я])против(?![а-я])", text)) == 1 else ()):
        if _NEGATED_WORD.search(text[m.start(): m.start("a")]) or _NEGATION.search(text[: m.start()]):
            continue
        if re.search(r"(?<![а-яa-z])(?:как|похож\w*|напомина\w*|вроде|типа|тем[аеуы]|урок\w*|при[её]м\w*|техник\w*|метод\w*|"
                     r"правил\w*|задач\w*|пример\w*|like)(?![а-яa-z])", text[m.start(): m.start("a")], re.IGNORECASE):
            continue  # «это техника «ладья против короля»»: a topic named, not the board described
        if not _COMP_WHOLE.search(m["a"] + " " + m["b"]) and not _COMP_STRICT.search(text[m.start(): m.end()]):
            continue  # «здесь конь против слона»: the imbalance, the rest equal — not the board as a whole
        a, b = _comp_side(m["a"]), _comp_side(m["b"])
        strict = bool(re.search(r"чист\w*|гол[оы]\w*|одинок\w*|только|лишь", text, re.IGNORECASE)) \
            or chess.PAWN in a or chess.PAWN in b
        if not any(_side_fits(bd, c, a, strict) and _side_fits(bd, not c, b, strict)
                   for bd in given for c in (chess.WHITE, chess.BLACK)):
            issues.append(f"the board shows {_composition(ctx.current)} — not «{m['a']} против {m['b']}»")
    m = _ONLY_KINGS.search(text)
    if m and _ONLY_KINGS_ANCHOR.search(text) and not _NEGATION.search(text[: m.start()]) \
            and not any(len(bd.piece_map()) == 2 for bd in given):
        issues.append(f"the board holds more than the two kings: {_composition(ctx.current)}")
    m = _ENDGAME_NOW.search(text)
    if m and not _NEGATION.search(text[: m.start()]) \
            and all(len(bd.piece_map()) - len(bd.pieces(chess.PAWN, True)) - len(bd.pieces(chess.PAWN, False)) - 2 >= 12
                    for bd in given):
        issues.append(f"this is not an endgame: {_composition(ctx.current)}")
    return issues


# The motif a sentence presents as made by the moving piece: «ладья идёт на d4 — и сразу бьёт по двум», «вилка», a pin.
_PRESENTS_MOTIF = {
    "fork": re.compile(r"(?<![а-яa-z])(?:вилк\w*|двойн\w+\s+удар\w*|(?:бь[её]т|бьют|напада\w+|атаку\w+)\s+(?:сразу\s+)?"
                       r"(?:по\s+|на\s+)?(?:двум|две|двух|обе|оба|обоих)|forks?|double\s+attacks?|attacks?\s+(?:both|two))(?![а-яa-z])",
                       re.IGNORECASE),
    "pin": re.compile(r"(?<![а-яa-z])(?:связк\w*|связыва\w*|связал\w*|pins?|pinned|pinning)(?![а-яa-z])", re.IGNORECASE),
}
# The piece that MAKES the blow: the subject of a moving or striking verb («ладья идёт на d4», «конь с d5 может
# атаковать», «ладья d4 — двойной удар»), not every piece the sentence names — «ладья на a8 и король на e8
# оказались под вилкой», «король и ладья — цели для вилки конём» name the targets (review 30.10).
_MOVER_PIECE = r"(конь|слон|ладья|ферзь|король|пешка|knight|bishop|rook|queen|king|pawn)"
_MOVER_VERB = (r"(?:ид[её]т|пойд[её]т|пош[её]л|пошла|прыга\w*|прыгн\w*|скачет|поскачет|переход\w*|перейд[её]т|переш[её]л|"
               r"перешла|вста[её]т|встанет|встал\w*|становится|станет|ставит|поставит|поставил\w*|дела[её]т|сдела[её]т|"
               r"сделал\w*|бь[её]т|ударит|ударил\w*|напада\w*|напад[её]т|напал\w*|атаку\w*|атаковал\w*|бер[её]т|"
               r"возьм[её]т|взял\w*|забира\w*|забер[её]т|забрал\w*|объявля\w*|объявит|объявил\w*|да[её]т|дал|дала|"
               r"шаху\w*|связыва\w*|свяж[её]т|связал\w*|ходит|уходит|выходит|выйд[её]т|выш[её]л|вышла|появля\w*|"
               r"может|сможет|мог|могла|играет|goes|jumps|moves|attacks|forks|pins|hits|lands|comes|takes|captures|"
               r"checks|can|will|could)")
_MOTIF_MOVER = re.compile(
    r"(?<![а-яa-z])" + _MOVER_PIECE + r"(?:\s+(?:белых|черных|чёрных|соперника|противника))?"
    r"(?:\s+(?:(?:с|со|из|на|on|from)\s+)?[a-h][1-8](?![0-9]))?(?:\s+(?:белых|черных|чёрных))?\s*,?\s+"
    r"(?:(?:тут\s+же|сразу|теперь|уже|затем|потом|then|now|immediately)\s+)?(?:" + _MOVER_VERB + r"(?![а-яa-z])"
    r"|[—–-]\s*(?=вилк|двойн|связк|сквозн|fork|double|pin))", re.IGNORECASE)
_MOVER_TYPE = {"конь": chess.KNIGHT, "слон": chess.BISHOP, "ладья": chess.ROOK, "ферзь": chess.QUEEN, "король": chess.KING,
               "пешка": chess.PAWN, "knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK,
               "queen": chess.QUEEN, "king": chess.KING, "pawn": chess.PAWN}
_CONTRAST = re.compile(r"(?<![а-яa-z])(?:не|нет|а\s+не|в\s+отличие|вместо|тоже|также|как\s+и|not|unlike|instead|also)(?![а-яa-z])",
                       re.IGNORECASE)


def _asked_motif_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    """The student asked for a motif made by a named piece («пример вилки конём») and the sentence presents the
    example's blow by another piece as that motif (prod 29.10, d3-example: «ладья идёт на d4 — и сразу бьёт по
    двум…» for «вилка конём»). A sentence that contrasts or denies («это не вилка конём, а…») is left alone, and
    so is one that names the asked motif itself («цели для вилки конём»); every piece the student named counts
    («чем вилка конём отличается от вилки пешкой?»)."""
    from src.motifs import motif_pieces

    asked = motif_pieces(ctx.question)
    if not asked or asked[0] not in _PRESENTS_MOTIF or "?" in text:
        return []
    m = _PRESENTS_MOTIF[asked[0]].search(text)
    if not m or _CONTRAST.search(text) or _is_hypothetical(text, original, 0, whole=True):
        return []
    told = motif_pieces(text)
    if told and told[0] == asked[0] and told[1] & asked[1]:
        return []
    converted, _ = _to_san(original)
    movers = {_MOVER_TYPE[x.group(1).lower()] for x in _MOTIF_MOVER.finditer(text[: m.end()])}
    movers |= {chess.PIECE_SYMBOLS.index(x["san"][0].lower()) for x in _MOVE.finditer(converted) if x["san"][0] in "KQRBN"}
    if not movers or movers & asked[1]:
        return []
    want = " or ".join(sorted(chess.piece_name(p) for p in asked[1]))
    named = " or ".join(sorted(chess.piece_name(p) for p in movers))
    return [f"the student asked for a {asked[0]} made by a {want}; this sentence presents a "
            f"blow by a {named} — that is not the {want} {asked[0]} asked for: say so plainly"]


_WS_RUN = re.compile(r"\s{2,}")
_EMPHASIS = re.compile(r"\*{1,3}|(?<![A-Za-zА-Яа-яЁё0-9])__|__(?![A-Za-zА-Яа-яЁё0-9])")


def check_sentence(sentence: str, ctx: Optional[CheckContext] = None, *, spoken: bool = False) -> list[str]:
    """The reasons *sentence* is wrong on the board; [] when nothing checkable is wrong. *spoken*: the sentence was
    already said (the voice check replaying the answer so far) — what it named stays the antecedent of the next
    sentence's «он/она» even when it has issues, since the listener heard it."""
    ctx = ctx or CheckContext.from_fens()
    # A sentence with issues is not shown, and its rewrite is checked on the same context (src/server.py: fix_gate
    # shares check_ctx): the line it wrote must not be the one the rewrite's «Тогда …» goes on with (review 30.10).
    # Every record of «the line the sentence before wrote» goes back: the scene's walk, the line the engine judges a
    # promised outcome at (line_verdict), and the line a forced reply may follow — «В итоге ты выигрываешь фигуру»
    # after a hidden «после 4.Nxe5 Nxe5 …» is not about that line (review 30.10, interplay).
    line_before = ctx.line_scene
    age_before = line_before.get("age", 0) if line_before is not None else 0
    kept = (ctx._line_end, ctx._line_advice, ctx.forced_line)
    # …and what the relation checker remembered for the next sentence (its antecedents, the line it told): a
    # sentence not shown leaves nothing for «он», «тогда» of the next one to refer to (plan 30.10).
    relation_kept = dict(ctx.relation_state)
    issues = _check_sentence(sentence, ctx)
    if issues:
        ctx.line_scene = line_before
        if line_before is not None:
            line_before["age"] = age_before
        ctx._line_end, ctx._line_advice, ctx.forced_line = kept
        if not spoken:
            ctx.relation_state = relation_kept
    return issues


def _check_sentence(sentence: str, ctx: CheckContext) -> list[str]:
    if sentence.strip():
        ctx.scene_age += 1  # the scene a move of this sentence sets is age 0; the explanation after it still sees it
        ctx.scene_before = (ctx.scene, ctx.scene_san, ctx.scene_age) if ctx.scene is not None else None
        ctx.scene_trail = []
        from src.answer_check_scene import age_scene

        age_scene(ctx)
    # The line the sentence before ended with: a sentence left out here (meta, an echo, another language) ends it.
    previous_line, ctx._line_end = ctx._line_end, None
    if is_meta(sentence):
        return [META_ISSUE]
    if _echoes_question(sentence, ctx):
        return [ECHO_ISSUE]
    wrong_language = language_issue(sentence, ctx.language) or foreign_word_issue(sentence, ctx.language, ctx.question_raw)
    if wrong_language:
        return [wrong_language]
    # Markdown emphasis is not a word of the claim: «Пешка на a2 **не атакована**», «**Слон c4** висит», «если **ладья**
    # под боем» went through every check the bold split (09.10, the castling rule; 30.10 for all of them).
    text = _EMPHASIS.sub("", sentence).replace("ё", "е")
    # A run of whitespace is one gap between words: the patterns that allow a few words between a piece and its
    # claim backtrack polynomially on a long run of spaces (review 30.10: «Пешка» + 50 spaces + «на e4.» held the
    # event loop for 2.8 s, 590 spaces for over 10 s — a browser-sent voice/check body reaches here too).
    text = _WS_RUN.sub(lambda m: "\n" if "\n" in m.group(0) else " ", text)
    # Speech transcripts write files in Cyrillic lookalikes: «слон на е2», «пешка с4» (voice, 2026-10-06).
    # …and transliterated ones: «конь на ф3», «ферзь на б6», «пешка г4», «ладья х1» (2026-10-08).
    text = re.sub(r"(?<![а-яА-Яa-zA-Z])([асебдфгхАСЕБДФГХ])(?=[1-8](?![0-9]))",
                  lambda m: {"а": "a", "с": "c", "е": "e", "б": "b", "д": "d", "ф": "f", "г": "g", "х": "h"}[m.group(1).lower()], text)
    lowered = text.lower()
    # Written moves first: the positions they lead to join the boards of the
    # turn, and the claims after them («Rg1, ладья нападает на ферзя») are judged there.
    san_issues = _history_issues(text, ctx) + _san_issues(text, ctx) + _recapture_issues(text, ctx)
    from src.answer_check_openings import opening_book_issues
    from src.answer_check_rules import rules_issues

    issues = (_move_issues(lowered) + _attack_issues(lowered, text, ctx) + san_issues
              + _opening_issues(text) + _opening_identity_issues(text, ctx) + _told_move_issues(lowered, text, ctx)
              + _fact_issues(lowered, text, ctx)
              + _plan_move_issues(lowered, text, ctx)
              + rules_issues(lowered, ctx) + _coach_move_issues(text, ctx) + _scene_issues(text, ctx)
              + _asked_motif_issues(lowered, text, ctx) + _composition_issues(lowered, text, ctx)
              # ECO codes, variations named after a person, «usually X» — by the ECO book (prod check 29.10)
              + opening_book_issues(text, ctx))
    from src.answer_check_facts import record_fact_issues

    issues += record_fact_issues(lowered, text, ctx)
    # Who attacks, defends, pins, holds what — each claim judged on the board it is about (src/answer_check_relations.py,
    # off | shadow | on by COACH_RELATION_CHECK; fail-open). After the facts, so this sentence's scene_trail is filled.
    from src.answer_check_relations import relation_issues

    issues += relation_issues(text, ctx, issues)
    if not san_issues:
        issues += _announced_move_issues(text, ctx)
    if ctx.current is not None and sentence.strip():
        # A forced reply claimed: the board it is about is known only now (this sentence's scene); the engine
        # judges it later, off the event loop (src/server.py, the async stage).
        from src.answer_check_rules import forced_reply_claim, line_end

        try:
            claim = forced_reply_claim(text, ctx) if not issues and len(ctx.forced_claims) < 40 else None
        except Exception:  # noqa: BLE001 — a broken pattern must never block an answer
            claim = None
        if claim:
            ctx.forced_claims[sentence] = claim
        try:
            ended = line_end(text, ctx)
        except Exception:  # noqa: BLE001
            ended = None
        if ended:
            ctx.forced_line = (ended[0], ended[1], 1)
        elif ctx.forced_line:
            ctx.forced_line = (ctx.forced_line[0], ctx.forced_line[1], ctx.forced_line[2] + 1)
    squares = _SQ_RE.findall(lowered)
    if ctx._object:
        ctx.topic = ctx._object
    elif squares and not _OPENS_WITH_PRONOUN.match(lowered):
        # «Твой конь с f3 бьёт e5 — пешка выглядит висящей»: about e5, the thing
        # hit, not f3 — the target of the last attack or defence verb, else the first square.
        hit = _TOPIC_TARGET.findall(lowered)
        ctx.topic = hit[-1] if hit else squares[0]
    ctx._object = None
    ctx._subject = None
    # A line written with its outcome: the engine judges the outcome before the sentence is shown (src/server.py).
    try:
        from src.line_verdict import line_claims

        ctx._line_end = previous_line
        claims = line_claims(text, ctx)
        if claims and not issues:
            ctx.line_claims[sentence] = claims
    except Exception:  # noqa: BLE001 — the check must never break a turn
        logger.debug("line claims failed", exc_info=True)
    return list(dict.fromkeys(issues))


def _scene_issues(text: str, ctx: CheckContext) -> list[str]:
    """The moves and the «piece on square» told after a written line, in the position the line reached
    (src/answer_check_scene.py: «Kd6 — и белый король заходит через d5», prod 29.10)."""
    from src.answer_check_scene import scene_issues

    try:
        return scene_issues(text, ctx)
    except Exception:  # noqa: BLE001 — a broken walk must never block an answer
        logger.debug("scene check failed", exc_info=True)
        return []


# The coach's private planning written out as the answer. On production
# (2026-09-30, «планы белых в испанской») DeepSeek without reasoning put its
# whole deliberation in the text: «Студент спрашивает о планах… Нужно ответить
# по-русски, коротко, с ходами из блока… Стоит ли вызывать get_topic?». Tool
# names, the words of the instructions (the block, the facts, the playbook,
# the rule), and the student in the third person never belong in a reply.
_META_RE = re.compile(
    r"\b(?:get_[a-z_]+|board_control|analyze_position|check_moves|find_critical_moments|search_master_games|"
    r"identify_opening|compare_variations|set_fen|load_pgn|draw_arrows|highlight_squares|playbook|"
    r"system prompt|tool[- ]?call|function[- ]?call)\b"
    r"|(?<![а-яa-z])(?:студент|ученик)\s+(?:спрашивает|просит|хочет|задал)"
    r"|(?<![а-яa-z])(?:нужно|надо|стоит ли|могу ли|должен|должна)\s+(?:ответить|отвечать|вызывать|вызвать|"
    r"упоминать|назвать|использовать|сказать про|дать)"
    r"|(?<![а-яa-z])(?:из|в|по)\s+блок[аеу]?(?![а-я])|(?<![а-яa-z])блок\s+(?:движка|дебюта|фактов|уже)"
    r"|(?<![а-яa-z])(?:инструкци[яию]|факт[ыа]\s+из|только факты|engine[- ]verified|не проверено)"
    # «Правило: отвечать по-русски» opening the sentence is an instruction; «здесь работает правило: …» is teaching (2026-10-07)
    r"|^[\s*_>#-]*правило\s*:"
    # thinking aloud in the answer: «… отойти на gxf6... нет, стоп: …» (2026-10-06)
    r"|(?:\.\.\.|…)\s*(?:нет|стоп|хм|подожди|wait|no)[,!.:\s]+(?:стоп|не\s+так|wait|that'?s\s+wrong)?"
    r"|(?<![а-яa-z])нет,\s+стоп\b|\bwait,\s+no\b"
    # «Инструмент подобрал мне не тот материал» (production, 2026-10-06): the tools are not the student's business.
    r"|(?<![а-яa-z])инструмент\w*\s+(?:мне\s+)?(?:подобрал|вернул|выдал|дал|показал|не\s+наш[её]л|ошиб\w*|сломал\w*|"
    r"недоступ\w*|не\s+сработал|не\s+работает)|\bthe\s+tool\s+(?:returned|gave|picked|failed|didn'?t)"
    r"|(?<![а-яa-z])(?:the student (?:asks|wants|is asking)|i (?:should|need to|must|'ll) (?:answer|reply|mention|"
    r"call|use|avoid|stick)|according to the (?:block|instructions|facts)|from the (?:engine|opening) block)",
    re.IGNORECASE)

META_ISSUE = "this is the coach's private planning (tools, instructions, the student in the third person), not an answer"


def is_meta(text: str) -> bool:
    """*text* narrates the coach's instructions or tools instead of answering."""
    return bool(_META_RE.search((text or "").replace("ё", "е")))


# Where a chess claim can begin: a piece word, a square, a move number, a
# figurine, castling. Text before that in a sentence claims nothing checkable.
_CLAIM_START = re.compile(
    r"[a-h][1-8]|\d|[♔-♟]|O-O|" + _W + r"(?:" + "|".join(p for _, p in _RU_PIECES + _EN_PIECES) + r")" + _E
    # material and the result are claims too: «ты выигрываешь — у тебя лишняя ладья» (production, 2026-10-05:
    # the start went out before the check found the rook was the opponent's)
    + r"|" + _W + r"(?:лишн\w*|без|впереди|материал\w*|выигрыва\w*|проигрыва\w*|выиграл\w*|проиграл\w*|мат\b|"
    r"extra|material|winning|losing|ahead|behind|up\s+an?\b|down\s+an?\b|mate|"
    # a side's name opens most claims about material and the result ("Black is a pawn up"):
    # the words before it streamed, the rewrite restated them — «Right now Black is a No — …» (2026-10-06)
    r"white|black|белые|белых|ч[её]рные|ч[её]рных|"
    # …and the outcome of an ending: «Нет, не догонит.» went out whole before its check (prod 29.10, the square)
    r"догон\w*|догнать|успе(?:ет|ешь|ют|вает|ваешь|вают)|проход(?:ит|ят)|пройд[её]т|ничь\w*|удерж\w*|спас\w*|"
    r"catch\w*|queens)" + _E,
    re.IGNORECASE)


# A piece letter written in Cyrillic by sound or by look: «Нf6+», «Рh8+», «Вf5» (production
# lesson sweep 2026-10-07). Russian notation has no such letters (it is К, Л, С, Ф), so they
# are the Latin N, R, B the rest of the answer uses.
_LOOKALIKE_PIECE = re.compile(r"(?<![А-Яа-яЁёA-Za-z])([НРВ])(?=[x:×]?[a-h][1-8](?![0-9]))")
_LOOKALIKE_MAP = {"Н": "N", "Р": "R", "В": "B"}


_RU_PROMO = re.compile(r"(?<=[a-h][18])=?([ФЛСК])(?![а-яё])")
_RU_PROMO_MAP = {"Ф": "=Q", "Л": "=R", "С": "=B", "К": "=N"}


def normalize_notation(text: str) -> str:
    """«Нf6+» → «Nf6+», «Рh8+» → «Rh8+», «Вf5» → «Bf5»; Russian letters typed as Latin ones —
    «Cc4» → «Bc4», «Kf7+ (конь с g5…)» → «Nf7+», «1.e4 e5 2.Kf3» → «2.Nf3»."""
    if not text:
        return text
    text = _LOOKALIKE_PIECE.sub(lambda m: _LOOKALIKE_MAP[m.group(1)], text)
    text = _RU_PROMO.sub(lambda m: _RU_PROMO_MAP[m.group(1)], text)  # «b8=Ф» → «b8=Q» (prod 09.10)
    text = _LATIN_C.sub("B", text)
    text = _KNIGHT_AS_K.sub("N", text)
    return _LINE_START.sub(lambda m: _fix_line_letters(m.group(0)), text) if "K" in text else text


# Russian notation typed with Latin letters (production 2026-10-07, 5 of 187 lesson answers): С (слон)
# as a Latin C, which no notation has, and К (конь) as a Latin K, which is the king: «Первый ход —
# **Kxf2** (конь берёт пешку f2 с шахом)», «Kc7+ — конь врывается», «1.e3, 2.Kc3, 3.Cc4».
_LATIN_C = re.compile(r"(?<![A-Za-zА-Яа-яЁё0-9])C(?=[x:×]?[a-h][1-8](?![0-9]))")
# A K glossed as a knight in brackets: «Kf7+ (конь с g5 на f7)». Only the gloss counts — «после Kxf2 конь
# f6 прыгает на g4» is the king taking and then another piece.
_KNIGHT_AS_K = re.compile(r"(?<![A-Za-zА-Яа-яЁё0-9])K(?=x?[a-h][1-8][+#!?]*\**\s*\(\s*кон[ьяеёю])")
_LINE_START = re.compile(r"(?<![0-9])1\s?\.\s?(?:[KQRBNa-hO][^.!?\n]*(?:\.\s?\S[^.!?\n]*)*)")


def _fix_line_letters(line: str) -> str:
    """A line from the first move with a K that only a knight can play: «1.e4 e5 2.Kf3» → «2.Nf3».

    Only once two moves of it have been read from the initial position: «1.Kc3 Kb8 2.Qg7» is an
    endgame line from the board, and its Kc3 is the king."""
    board = chess.Board()
    out, last = [], 0
    for m in re.finditer(r"(?<![A-Za-z])([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)([+#!?]*)", line):
        san = m.group(1)
        try:
            board.push_san(san)
            continue
        except ValueError:
            pass
        if san.startswith("K") and len(board.move_stack) >= 2:
            try:
                board.push_san("N" + san[1:])
                out.append(line[last:m.start()] + "N")
                last = m.start() + 1
                continue
            except ValueError:
                pass
        break  # the line leaves this board: nothing further to read
    return "".join(out) + line[last:]


MIN_RELEASED_CHARS = 20  # a claim-free start shorter than this waits for its sentence
# A start that announces the move it is about to name («Первый ход — », "The key move: "):
# held with that move — when the move is cut, «Первый ход — Сначала отдаём ферзя…» dangled
# (production 2026-10-07, three of 187 lesson puzzles).
_ANNOUNCES_MOVE = re.compile(
    r"(?<![а-яa-z])(?:ход\w*|move|решени\w*|solution|сыгра\w*|играй|play|начн\w*\s+с|начина\w*\s+с|"
    r"лучше\s+всего|start\s+with)(?![а-яa-z])[^.!?]{0,40}[:—–-]\s*$", re.IGNORECASE)


# Whether the claim-free start of a sentence streams before the sentence is checked. Off: a cut
# sentence left its shown start dangling — «Сначала нужно было поставить чёрную Однако…», «не пускай
# белого Тогда…», «ваш У короля…» (about one answer in ten on the production runs of 06–07.10).
# The quick reaction already gives the student the first words. COACH_STREAM_SENTENCE_STARTS=1 — back.
# «Покажу на доске.», «Сейчас поставлю позицию на доску», "I'll show it on the board": the coach promises a board
# action — a sentence that is that promise and nothing more (no square, no move, no offer or question). Kept only
# when the board changes in the turn (SentenceGate(hold_promises=True)); prod 29.10 (rule-promote): «Покажу на
# доске.» and the board stayed as it was. «Хочешь, покажу на доске?» is an offer, not a promise.
_SHOW_PROMISE = re.compile(
    r"^\W*(?:(?:сейчас|тогда|давай|итак|вот|ну|а|и|so|now|ok|okay)\s*,?\s+)?(?:я\s+)?(?:сейчас\s+)?"
    r"(?:(?:покажу|поставлю|выставлю|расставлю|нарисую|отмечу)(?![а-я])[^.!?]{0,60}?(?<![а-я])(?:на\s+доск\w*|доску)(?![а-я])"
    r"|(?:i'?ll|i\s+will|let\s+me)\s+(?:show|set\s+up|put|draw|mark)(?![a-z])[^.!?]{0,60}?(?<![a-z])board(?![a-z])"
    r"|(?:тақтада|тақтаға)\s+(?:\S+\s+){0,3}?(?:көрсет|қой)\w*)",
    re.IGNORECASE)
_PROMISE_OFFER = re.compile(r"(?<![а-яa-z])(?:хочешь|хотите|хочет|если|можем|могу|можно|могли|if|want|would|could|can|"
                            r"қаласаң|қаласаңыз)(?![а-яa-z])|\?", re.IGNORECASE)
PROMISE_ISSUE = "the coach promised to show this on the board, but nothing was put on the board this turn"


def promises_board(sentence: str) -> bool:
    """*sentence* is only a promise to show something on the board («Покажу на доске, как это выглядит.»)."""
    text = (sentence or "").strip()
    return bool(text) and len(text.split()) <= 14 and bool(_SHOW_PROMISE.search(text)) \
        and not _PROMISE_OFFER.search(text) and not _SQ_RE.search(text.lower())


RELEASE_STARTS = os.environ.get("COACH_STREAM_SENTENCE_STARTS", "0").strip().lower() not in ("0", "false", "no", "off", "")
# «Be3, блокируя... нет, точнее защищая f1»: a self-correction after an ellipsis is the model thinking aloud.
_SELF_CORRECTION = re.compile(r"^\W*(?:нет|стоп|хм|то\s+есть|точнее|вернее|wait|no)(?:[,—:\s]|$)", re.IGNORECASE)


# A word that leans on the sentence before it: when that sentence was left out, «Затем выводи короля…»
# opened what was left of the answer (lucena, the newest code, 2026-10-08).
_LEANS_BACK = re.compile(
    r"^(\s*(?:[>#-]+\s*)?)([*_]{0,2})(?:затем|потом|после\s+этого|дальше|далее|следом|кроме\s+того|также|тоже|then|"
    # «Зато есть сильный ход…», «Дело в том, что…», «Но ничья наступает…» — the answer began mid-thought
    # once its first sentence was left out (prod curriculum and stand, 2026-10-13).
    r"но|зато|однако|тем\s+не\s+менее|при\s+этом|а\s+вот|так\s+что|дело\s+в\s+том,?\s+что|"
    r"after\s+that|next|also|besides|but|however|still|yet)(?![а-яёa-z])([*_]{0,2})[\s,—–-]*", re.IGNORECASE)


def strip_leaning_start(text: str) -> str:
    """*text* without a first word that refers to a sentence the student never saw."""
    m = _LEANS_BACK.match(text or "")
    if not m or len(text) - m.end() < 12:
        return text
    rest = text[m.end():]
    mark = "" if m.group(3) else m.group(2)  # «**Затем** выводи» loses its bold, «**Затем выводи…**» keeps it
    return m.group(1) + mark + rest[:1].upper() + rest[1:]


class SentenceGate:
    """Holds streamed text until its sentence is complete and checked.

    Only the part of a sentence from where a claim can begin is held: the words
    before the first piece name, square or move number go out as they arrive,
    so a plain opening («Хороший вопрос — тут у тебя есть выбор.») streams as
    before and the first word is not delayed by the check. ``feed`` returns
    (text, issues, sentence): *text* to show unless *issues*, *sentence* the
    whole sentence the check ran on. Disabled, text passes straight through.
    """

    MAX_HOLD = 600  # characters without a sentence end: check and release anyway

    def __init__(self, ctx: Optional[CheckContext] = None, enabled: bool = True, release_starts: Optional[bool] = None,
                 hold_promises: bool = False):
        self.ctx = ctx or CheckContext.from_fens()
        self.enabled = enabled
        self.release_starts = RELEASE_STARTS if release_starts is None else release_starts
        # «Покажу на доске.» (promises_board) waits for a board action of the turn — the model writes the promise
        # before the tool call that keeps it — and so does every sentence after it, to keep their order; a turn
        # that ends with the board untouched leaves the promise out (flush: PROMISE_ISSUE). The text coach only:
        # spoken words cannot wait (prod 29.10, rule-promote).
        self.hold_promises = hold_promises
        self._board_changed = False
        self._held: list = []
        self._buf = ""
        self._released = ""  # the start of the current sentence, already out
        # The last sentence shown: DeepSeek sometimes writes a sentence twice in a
        # row («Хороший вопрос — давай проверим… Хороший вопрос — давай проверим…»,
        # production 2026-10-06); the repeat is dropped.
        self._prev = ""

    @staticmethod
    def _same(a: str, b: str) -> bool:
        norm = lambda x: re.sub(r"\s+", " ", x).strip().lower()  # noqa: E731
        return bool(norm(a)) and norm(a) == norm(b)

    def board_changed(self) -> None:
        """A board action of the turn went out: a held promise is kept, it and what follows go out with the next text."""
        self._board_changed = True

    def _hold(self, pairs: list) -> list:
        if not self.hold_promises or not self.enabled:
            return pairs
        out = []
        if self._board_changed and self._held:
            out, self._held = self._held, []
        for pair in pairs:
            if self._held or (not self._board_changed and not pair[1] and promises_board(pair[2])):
                self._held.append(pair)
            else:
                out.append(pair)
        return out

    def feed(self, text: str) -> list[tuple[str, list[str], str]]:
        return self._hold(self._feed(text))

    def _feed(self, text: str) -> list[tuple[str, list[str], str]]:
        if not self.enabled:
            return [(text, [], text)] if text else []
        self._buf += text
        out: list[tuple[str, list[str], str]] = []
        sentences, self._buf = _split_sentences(self._buf)
        if len(self._buf) > self.MAX_HOLD:
            sentences.append(self._buf)
            self._buf = ""
        for sentence in sentences:
            sentence = chess_terms(normalize_notation(sentence), self.ctx.language, self.ctx.question_raw)  # «рыцарь» → «конь»
            full = self._released + sentence
            self._released = ""
            if len(full.strip()) >= 12 and self._same(full, self._prev):
                continue  # the model repeated its last sentence word for word
            prev_end = self._prev.rstrip()
            if full.strip():
                self._prev = full
            if prev_end.endswith(("...", "…")) and _SELF_CORRECTION.match(full):
                out.append((sentence, [META_ISSUE], full))
                continue
            out.append((sentence, check_sentence(full, self.ctx), full))
        # The language is judged before anything of an unfinished sentence goes
        # out: a sentence in the wrong language has no piece or square in it,
        # so the claim-free start below would release it whole unchecked (the
        # tester's "ok and a skewer?" came back in English past the gate,
        # 2026-10-04). Held until there are enough letters to tell; stopped
        # at once when they are the wrong script.
        if self.ctx.language and self._buf:
            pending = self._released + self._buf
            wrong = language_issue(pending, self.ctx.language)
            if wrong:
                out.append((self._buf, [wrong], pending))
                self._buf = ""
                self._released = ""
                return out
            if looks_wrong_script(pending, self.ctx.language):
                return out  # suspicious start: held until there is enough to judge
        if not self.release_starts:
            return out  # the whole sentence goes out once it is checked
        # The claim-free start of the unfinished sentence goes out now — unless
        # the sentence so far reads like the coach's planning: that is held
        # whole and checked (a released «Студент спрашивает» cannot be recalled).
        safe = "" if is_meta(self._released + self._buf) else self._safe_prefix(self._buf)
        start_so_far = re.sub(r"\s+", " ", self._released + safe).strip().lower()
        if safe and len(start_so_far) >= 6 and re.sub(r"\s+", " ", self._prev).strip().lower().startswith(start_so_far):
            safe = ""  # it may be the last sentence again: held until it is whole
        if safe and len(self._released) + len(safe) < MIN_RELEASED_CHARS \
                and not re.search(r"[:,;—–-]\s*$", self._released + safe):
            safe = ""  # «А вот твоя » would dangle after a cut; «Смотри сюда: » reads on into any rewrite
        if safe and _ANNOUNCES_MOVE.search(self._released + safe):
            safe = ""  # «Первый ход — » goes out with its move or not at all
        if safe and self.hold_promises and _SHOW_PROMISE.search(self._released + safe):
            safe = ""  # «Покажу на доске» is judged whole, with the board action of the turn
        if safe:
            self._released += safe
            self._buf = self._buf[len(safe):]
            out.append((safe, [], safe))
        return out

    @staticmethod
    def _safe_prefix(buf: str) -> str:
        """The start of *buf* that no claim can be part of: whole words before the
        first piece name, square, digit or figurine (a word may be cut mid-delta)."""
        m = _CLAIM_START.search(buf)
        limit = m.start() if m else len(buf)
        # Back to the start of the word the claim begins in, and never a partial word.
        cut = buf.rfind(" ", 0, limit) + 1 if m else buf.rfind(" ") + 1
        cut = max(cut, buf.rfind("\n", 0, limit) + 1)
        return buf[:cut]

    def flush(self) -> list[tuple[str, list[str], str]]:
        rest, self._buf = chess_terms(normalize_notation(self._buf), self.ctx.language, self.ctx.question_raw), ""
        full, self._released = self._released + rest, ""
        pairs = self._hold([(rest, check_sentence(full, self.ctx) if self.enabled else [], full)] if rest else [])
        held, self._held = self._held, []
        # The turn is over: a promise still held was not kept — it is marked, the rest goes out in order.
        return pairs + [(t, [PROMISE_ISSUE] if not i and promises_board(f) else i, f) for t, i, f in held]


def _split_sentences(buf: str) -> tuple[list[str], str]:
    """Complete sentences of *buf* (with their trailing spaces) and the unfinished rest.

    A sentence ends at a newline, or at . ! ? … followed by a space — except
    after a move number («1. e4», «5... Na5»). Punctuation at the very end
    waits for the next text: it may be «1.» of a move.
    """
    out: list[str] = []
    start = i = 0
    n = len(buf)
    while i < n:
        ch = buf[i]
        if ch == "\n":
            j = i + 1
            while j < n and buf[j] == "\n":
                j += 1
            out.append(buf[start:j])
            start = i = j
            continue
        if ch in ".!?…":
            j = i
            while j < n and buf[j] in ".!?…":
                j += 1
            if j >= n:
                break  # decide when more text comes
            if buf[j] in " \t\n":
                k = i
                while k > start and buf[k - 1].isalnum():
                    k -= 1
                if not buf[k:i].isdigit():
                    while j < n and buf[j] in " \t":
                        j += 1
                    out.append(buf[start:j])
                    start = i = j
                    continue
            i = j
            continue
        i += 1
    return out, buf[start:]


def fix_messages(turn_message: str, shown: str, wrong: str, issues: list[str], language_note: str,
                 student_note: str = "") -> list[dict]:
    """The one tool-free call that writes the rest of an answer after a wrong sentence.

    It gets what the coach's turn got (the question, the board, the engine and
    opening blocks), what the student has already seen, the rejected sentence
    and why it is wrong — and continues from there.
    """
    system = (
        "You are a chess coach finishing your reply to a student. The beginning of the reply is "
        "already on the student's screen — it may end in the middle of a sentence, and then your "
        "text must complete that very sentence so it reads naturally. The next part of your draft "
        "was checked on the board and is WRONG; it was not shown. Write the rest of the reply: "
        "continue right after the shown text, make the point the wrong sentence tried to make — "
        "correctly — and finish "
        "the thought in 2–4 short sentences, the way a coach talks. Do not mention a mistake, a "
        "draft or a check. Do not repeat what is already shown. Name only moves, squares and "
        "attacks you can read in the verified context (the engine block, the opening block, the "
        "facts, tool results); when unsure, explain the idea in words without moves. No engine "
        "names, no numbers, no [[marks]]."
    )
    user = (
        f"{turn_message}\n\n"
        f"## Already shown to the student\n{shown.strip() or '(nothing yet — write the whole answer)'}\n\n"
        f"## The sentence of the draft that is WRONG (its start may already be shown; the rest was not)\n"
        f"{wrong.strip()}\n"
        f"Why it is wrong (checked on the board): {'; '.join(issues)}.\n"
        + (f"{student_note}\n" if student_note else "") +
        f"\n{language_note}\nContinue the reply now."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# DeepSeek's own tool-call markup (DSML) sometimes reaches the text through the
# provider: on production (2026-09-30) an answer began «id" string="false">3686097Нашёл —».
_DSML = r"[｜|]\s*DSML\s*[｜|]"
_LEAKS = re.compile(
    rf"<\s*{_DSML}\s*parameter[^>]*>[^<]{{0,200}}<\s*/\s*{_DSML}\s*parameter\s*>"   # a whole parameter
    rf"|<\s*/?\s*{_DSML}[^>]*>"                                                        # any other DSML tag
    r"|(?:<[^>\n]{0,40})?\b[\w-]{0,40}\"\s*string=\"(?:true|false)\"\s*>[A-Za-z0-9_.:/-]{0,60}"
    r"(?:<\s*/[^>\n]{0,40}>)?"                                                         # a cut-off fragment
    r"|(?<![\w])[\w-]{0,40}=\"(?:true|false)\"\s*>[A-Za-z0-9_.:/-]{0,60}"                # «="true">Nepomniachtchi» (2026-10-13)
    r"|<\s*/?\s*(?:function_calls|invoke|parameter)\b[^>\n]{0,80}>"
    r"|(?m:^[ \t]*(?:parameter\s+)?name=\"[^\n]{0,60}$)", re.IGNORECASE)                    # a stray « name="» line


# «епископ» is the bishop of a church, not of the board: «У белых епископ и конь» (prod, 2026-10-09, 2026-10-13).
# Masculine for masculine, so the words around it still agree — and «рыцарь» → «конь», «башня» → «ладья»,
# «эндгейм» → «эндшпиль» the same way (30.10, _TERM_TABLE). «королева» → «ферзь» changes the gender: rewritten.
_BISHOP_FORMS = {"епископ": "слон", "епископа": "слона", "епископу": "слону", "епископом": "слоном",
                 "епископе": "слоне", "епископы": "слоны", "епископов": "слонов", "епископам": "слонам",
                 "епископами": "слонами", "епископах": "слонах"}
_SWAP_FORMS = {**_BISHOP_FORMS,
               "рыцарь": "конь", "рыцаря": "коня", "рыцарю": "коню", "рыцарем": "конём", "рыцаре": "коне",
               "рыцари": "кони", "рыцарей": "коней", "рыцарям": "коням", "рыцарями": "конями", "рыцарях": "конях",
               "башня": "ладья", "башни": "ладьи", "башне": "ладье", "башню": "ладью", "башней": "ладьёй",
               "башнею": "ладьёю", "башен": "ладей", "башням": "ладьям", "башнями": "ладьями", "башнях": "ладьях",
               "эндгейм": "эндшпиль", "эндгейма": "эндшпиля", "эндгейму": "эндшпилю", "эндгеймом": "эндшпилем",
               "эндгейме": "эндшпиле", "эндгеймы": "эндшпили", "эндгеймов": "эндшпилей", "эндгеймам": "эндшпилям",
               "эндгеймами": "эндшпилями", "эндгеймах": "эндшпилях"}
_BISHOP_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted(_BISHOP_FORMS, key=len, reverse=True)) + r")(?![\w-])",
                        re.IGNORECASE)
_SWAP_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted(_SWAP_FORMS, key=len, reverse=True)) + r")(?![\w-])",
                      re.IGNORECASE)


def chess_terms(text: str, language: Optional[str] = None, question: str = "") -> str:
    """*text* with the Russian chess words where the model used others («епископ» → «слон», «рыцарь» → «конь»).
    Only «епископ» outside Russian: in Kazakh «тура» is the rook, and the rest is rewritten (foreign_word_issue).
    A word the sentence explains stays (_term_explained, the same as the check): «Ладью часто называют башней»
    became «…называют ладьёй» (review 30.10)."""
    if not text:
        return text
    rx, forms = (_SWAP_RE, _SWAP_FORMS) if language == "ru" else (_BISHOP_RE, _BISHOP_FORMS)
    if not rx.search(text):
        return text
    asked = _term_rows(question)

    def swap_in(sentence: str) -> str:
        def swap(m: "re.Match") -> str:
            row = _term_row(m.group(1))
            if row is not None and _term_explained(row, sentence, asked):
                return m.group(1)
            word = forms[m.group(1).lower()]
            return word.capitalize() if m.group(1)[0].isupper() else word

        return rx.sub(swap, sentence)

    return "".join(swap_in(part) for part in re.split(r"(?<=[.!?…])(\s+)", text))


def strip_leaks(text: str) -> str:
    """*text* without tool-call markup the model wrote as text."""
    return _LEAKS.sub("", text) if text else text
