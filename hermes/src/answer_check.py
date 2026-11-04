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

import functools
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

import chess

# The checks build many patterns inline (re.search(W + r"…", …)); past re's 512-entry cache they were compiled again
# on the hot path — the relation p99 tail (review-wiring2 01.11: about 900 compilations on one corpus run). A larger
# cache keeps every one of them compiled once per process.
if getattr(re, "_MAXCACHE", 4096) < 4096:
    re._MAXCACHE = 4096

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
_TARGETS_END_V1031 = re.compile(
    r",?\s+(?:но|а|поэтому|чтобы|потому|если|когда|пока|затем|потом|после|хотя|but|so|because|if|when|while|"
    r"after|then|which|that|who|whose)\s|\s+котор\w*\s|,\s+and\s"
    r"|,\s*(?:(?:а|и|and)\s+)?(?:конь|слон|ладья|ферзь|король|пешка|the\s+(?:knight|bishop|rook|queen|king|pawn))"
    r"(?![а-яa-z])"
    r"|,\s*[KQRBN]?[a-h]?x?[a-h][1-8]\s+(?!(?:и|and|или|or)\s)[а-яa-z]", re.IGNORECASE)  # the /learn tutor's, kept as is
_TARGETS_END = re.compile(
    r",?\s+(?:но|а|поэтому|чтобы|потому|если|когда|пока|затем|потом|после|хотя|ведь|поскольку|так\s+как|but|so|"
    r"because|since|if|when|while|after|then|which|that|who|whose)\s|\s+котор\w*\s|,\s+and\s"
    r"|,\s*(?:(?:а|и|and)\s+)?(?:конь|слон|ладья|ферзь|король|пешка|the\s+(?:knight|bishop|rook|queen|king|pawn))"
    r"(?![а-яa-z])"
    r"|,\s*[KQRBN]?[a-h]?x?[a-h][1-8]\s+(?!(?:и|and|или|or)\s)[а-яa-z]"
    # fix1102 K5 — a clause of its own with another subject or another square (VERDICT §6.3, «X нападает на Y, её
    # защищают Z и W» — the defenders were read as X's targets, ~20 true sentences cut on both trees):
    #  * an object pronoun with a verb of its own: «, её защищают конь c3 и пешка d2», «, и его держит слон e7»;
    r"|,?\s*(?:(?:и|а|но)\s+)?(?:е[её]|его|их)\s+(?:(?:тоже|также|уже|пока|же|только|сейчас|надёжно|надежно)\s+)*"
    r"(?:защища|прикрыва|держ|охраня|подстраховыва|поддержива|бь|атаку|напада|контролиру|стереж)\w*(?![а-яa-z])"
    #  * the verb first, the object pronoun after it: «, защищает её только ферзь d4»;
    #    (or a square: the object pronoun after a verb is replaced by its antecedent's square before this reads it)
    r"|,\s*(?:(?:и|а|но)\s+)?(?:защища|прикрыва|держ|охраня)\w*\s+(?:е[её]|его|их|[a-h][1-8])(?![а-яa-z0-9])"
    #  * a participle or a gerund opens a clause about something else: «, защищённую слоном c1», «, оставляя слону c8
    #    дорогу на f5», "…, leaving d4 weak" (an attack gerund — "hitting", "attacking" — goes on with the same piece);
    r"|,\s*(?:защищ[её]нн|прикрыт|охраняем)\w*"
    r"|,\s*[а-я]+(?:ая|яя|уя|юя|ав|яв|ив|ув|вши|ясь|аясь)\s"
    r"|,\s*(?!(?:attack|hitt|threaten|fork|target|pinn|eye|x-?ray|aim)ing)[a-z]+ing\s"
    #  * the piece moves on — what follows is judged from a square the claim does not name: «бьёт d5, встаёт на d6 и
    #    нападает на c7» (en passant: the pawn attacks from d6, not from e5).
    r"|(?:,\s*|\s+)(?:(?:и|а|then|and)\s+)?(?:вста[её]т|встанет|ид[её]т|пойд[её]т|уходит|уйд[её]т|отходит|отойд[её]т|"
    r"отступает|переходит|перейд[её]т|прыгает|прыгнет|возвращается|вернётся|вернется|lands|goes|moves|retreats|jumps)"
    r"(?![а-яa-z])", re.IGNORECASE)
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
    for the king too, so there a king move is accepted as well. Memoised (every check converts the same sentence;
    review-wiring2 01.11): the set is a fresh copy each call."""
    conv, cyr_k = _to_san_cached(text or "")
    return conv, set(cyr_k)


@functools.lru_cache(maxsize=512)
def _to_san_cached(text: str) -> tuple:
    conv, cyr_k = _to_san_now(text)
    return conv, frozenset(cyr_k)


def _to_san_now(text: str) -> tuple[str, set]:
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


def _clause_targets(text: str, ctx=None) -> list[str]:
    cut = (_TARGETS_END_V1031 if _lesson(ctx) else _TARGETS_END).search(text)
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
    # Every move this sentence wrote and the walk followed, in order (san, board after, move): the scene's moves and
    # the moves read as a plan on the start position (start_scene sets no scene for them, yet they are written moves —
    # a name next to them may be about their line, src/answer_check_openings._told_trail).
    written_trail: list = field(default_factory=list)
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
    student_moved_now: bool = False  # the turn's pre-step played the student's move in the game (K3 02.11)
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
    # The facts the model was given this turn (src/turn_facts.Fact; plan 31.10, filled by P8's providers): a detector
    # may quote the one it relied on («(you were given: …)»). Empty until a provider fills it.
    facts: list = field(default_factory=list)
    # The issues of plan-31.10 detectors switched to shadow (COACH_DETECTORS_SHADOW, or a game move comment): logged,
    # never shown — [(detector name, sentence, issues)], one shape for every package (record_shadow).
    detector_shadow: list = field(default_factory=list)
    # The sentence _check_sentence is judging now (the sentence a shadow record names).
    sentence_now: str = ""
    # …and the one judged before it on this context (the answer so far): «Поле f2 под боем. Поэтому рокироваться нельзя»
    # gives its reason in the sentence before (src/castle_reason, review-miss 02.11), «Соперник угрожает …» names who
    # moves in the next one (word_move).
    sentence_before: str = ""
    # The moves of the side to move the sentence before told — recommended, offered, named in words or notation
    # (_told_moves): «Сыграй конём на d5. Конь атакует слона e3» is about the board after Nd5 (review-fp 03.11).
    told_before: list = field(default_factory=list)
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


def _fail_open(fn, *args) -> list:
    """*fn*(*args*), or [] when it raises: a broken new detector never blocks an answer (plan 31.10)."""
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001
        logger.debug("%s failed", getattr(fn, "__name__", "detector"), exc_info=True)
        return []


# The check a shadow record belongs to when its detector judges away from the CheckContext — the engine stage's
# verify_claims, the tablebase's judge_pending, run on a worker thread (shadow_into): (ctx, the sentence held).
import contextlib as _contextlib  # noqa: E402
import contextvars as _contextvars  # noqa: E402

_SHADOW_SINK: "_contextvars.ContextVar[Optional[tuple]]" = _contextvars.ContextVar("detector_shadow_sink", default=None)


@_contextlib.contextmanager
def shadow_into(ctx, sentence: Optional[str] = None):
    """Shadow records made inside the block without a context (record_shadow(None, …)) go to *ctx*, naming
    *sentence*: the engine stage's detectors are graded from the same detector_shadow event as the sync ones."""
    token = _SHADOW_SINK.set((ctx, sentence) if ctx is not None else None)
    try:
        yield
    finally:
        _SHADOW_SINK.reset(token)


def record_shadow(ctx, name: str, issues, text: Optional[str] = None) -> None:
    """One shadow record for every plan-31.10 detector: (name, sentence, issues) on ctx.detector_shadow, and logged —
    never shown or cut. *text* defaults to the sentence being judged (ctx.sentence_now). *ctx* None: the check the
    caller runs for (shadow_into); with none it is only logged, as before. Fail-open."""
    try:
        issues = [issues] if isinstance(issues, str) else list(issues or [])
        if ctx is None:
            sink = _SHADOW_SINK.get()
            if sink is not None:
                ctx = sink[0]
                if text is None:
                    text = sink[1]
    except Exception:  # noqa: BLE001
        return
    if not issues:
        return
    if ctx is None:
        try:
            logger.info("detector %s (shadow): %r -> %s", name, " ".join((text or "").split())[:300], "; ".join(issues)[:300])
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        if text is None:
            text = getattr(ctx, "sentence_now", "") or ""
        logger.info("detector %s (shadow): %r -> %s", name, " ".join(text.split())[:300], "; ".join(issues)[:300])
        sink = getattr(ctx, "detector_shadow", None)
        if sink is None:
            sink = []
            ctx.detector_shadow = sink
        sink.append((name, text, issues))
    except Exception:  # noqa: BLE001
        pass


def shadow_event_payload(ctx, limit: int = 12) -> Optional[dict]:
    """The payload of the turn's ``detector_shadow`` event (src/server.py), or None when no shadow detector flagged
    anything: the first *limit* records as {detector, sentence, issues} and the total. Plan §7: a shadow detector is
    switched on only after ≥ 20 graded prod flags at ≥ 90 % precision — this is what gets graded."""
    rows = [r for r in list(getattr(ctx, "detector_shadow", None) or []) if isinstance(r, (tuple, list)) and len(r) >= 3]
    if not rows:
        return None
    return {"records": [{"detector": str(r[0]), "sentence": " ".join(str(r[1] or "").split())[:300],
                         "issues": [str(i)[:300] for i in list(r[2] or [])[:4]]} for r in rows[:limit]],
            "total": len(rows)}


def _switch_mode(name: str, ctx=None) -> str:
    """src/config.detector_mode, 'off' when the switch cannot be read."""
    try:
        from src.config import detector_mode

        return detector_mode(name, ctx)
    except Exception:  # noqa: BLE001
        return "off"


def _detector(name: str, ctx: Optional["CheckContext"], issues: list) -> list:
    """The issues of the plan-31.10 detector *name* as its switch says (src/config.detector_mode): 'on' returns
    them, 'shadow' records them in ctx.detector_shadow and logs them (never shown), 'off' drops them."""
    if not issues:
        return []
    try:
        from src.config import detector_mode

        mode = detector_mode(name, ctx)
    except Exception:  # noqa: BLE001 — a switch that cannot be read is a switched-off detector (fail-open)
        logger.debug("detector switch %s failed", name, exc_info=True)
        return []
    if mode == "on":
        return list(issues)
    if mode == "shadow" and ctx is not None:
        record_shadow(ctx, name, issues)
    return []


# «Позиция после 1.d4 e5 … 6.exd8=R+: …», «…5.fxe7, и после твоих ошибок белые впереди»: the game's own record up to
# the board now told before a claim. «после» right before the moves, and «после твоих ошибок / этого / всех разменов»
# after them, then mean "now" (plan 31.10 M1 recap_scope).
_RECAP_AFTER = re.compile(r"(?<![а-я])после\s+(?=\d{1,3}\s?\.)", re.IGNORECASE)
_RECAP_SINCE = re.compile(r"(?<![а-я])после\s+(?:тво\w+|ваш\w+|эт\w+|всех|всего)(?:\s+[а-я]+)?", re.IGNORECASE)


def _recap_now(original: str, upto: int, ctx: Optional["CheckContext"]) -> bool:
    """The written moves before *upto* are the game's own record and end at the board now (src/game_record.recap_end;
    a recap that ends a ply early, or an invented line, is not)."""
    moves = getattr(ctx, "game_moves", None) if ctx is not None else None
    if not moves or ctx.current is None:
        return False
    try:
        from src.config import detector_mode

        if detector_mode("recap_scope", ctx) == "off":
            return False  # off is main: the record is not read at all
        from src.game_record import recap_end

        return recap_end(ctx, original[:upto]) == len(moves)
    except Exception:  # noqa: BLE001 — a broken recap reader leaves the claim as main reads it (fail-open, F8)
        logger.debug("recap_scope failed", exc_info=True)
        return False


def _is_hypothetical(text: str, original: str, upto: int, whole: bool = False, played: Optional[set] = None,
                     ctx: Optional["CheckContext"] = None) -> bool:
    """A marker or a written move BEFORE the claim; what follows it («у чёрных
    лишняя пешка, и после Rg1 Nxa4…») does not excuse the claim itself — a
    claim about the position after those moves holds on the derived boards.
    *whole*: the whole sentence counts («твой конь на c5 — если бы он туда
    попал — доминировал бы»), for claims about whose piece stands where.
    *ctx*: in a game, written moves that retell the game's own record up to the board now are no line to imagine
    (plan 31.10 M1): the claim after them is about the board now."""
    if not whole and ctx is not None and _fail_open(_recap_now, original, upto, ctx):  # [] when it raises
        head = _RECAP_AFTER.sub("", text[:upto])
        first = re.search(r"\d{1,3}\s?\.", head)
        if first:
            head = head[: first.start()] + _RECAP_SINCE.sub("", head[first.start():])
        if _HYPO.search(head):
            return True
        if _HYPO.search(text[:upto]) is None and not any(
                m["san"] for m in _MOVE.finditer(_to_san(original[:upto])[0])
                if (m["num"] or m["bdots"] or m["san"][0] in "KQRBN") and m["san"].rstrip("+#") not in (played or ())):
            return False  # nothing made it a line before either: no switch to consult
        from src.config import detector_mode

        mode = detector_mode("recap_scope", ctx)
        if mode == "on":
            return False
        if mode == "shadow":
            record_shadow(ctx, "recap_scope", [f"recap to now read as the board now: {text[:upto][-80:]}"])
        return True
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


# fix1102 K5: a pin names two pieces — the one pinned and the one behind it («pins the knight on f6 to the queen on d8»,
# «держит коня f6 в связке с ферзём d8», "pins the f2 pawn to the king on g1"). The piece behind is reached THROUGH
# the pinned one by definition: it is no blocked line, and its own geometry (on the line) is still judged.
_PIN_WORD = re.compile(r"(?<![a-z])pin\w*|связ\w*|связк\w*", re.IGNORECASE)
_PIN_BEHIND = re.compile(
    r"(?<![а-яa-z])(?:to|against|with|к|ко|с|со)\s+(?:(?:the|its|his|her|their|own|your|my|сво\w+|тво\w+|ваш\w+|"
    r"ч[её]рн\w+|бел\w+|black|white|enemy)\s+){0,2}(?:(?:king|queen|rook|bishop|knight|корол\w*|ферз\w*|ладь\w*|"
    rf"слон\w*|кон\w*)\s+)?(?:on\s+|на\s+)?(?P<sq>{SQ})(?![0-9])", re.IGNORECASE)


def _pin_behind(m) -> set:
    """The squares a pin claim names as the piece behind the pinned one (none when the claim is no pin)."""
    if not (_PIN_WORD.search(m["verb"]) or _PIN_WORD.search(m["targets"])):
        return set()
    return {x["sq"].lower() for x in _PIN_BEHIND.finditer(m["targets"])}


def _through_one(board: chess.Board, a: int, t: int) -> bool:
    """*t* is on a line from *a* with exactly one piece between them (an x-ray through the pinned piece)."""
    between = chess.SquareSet(chess.between(a, t))
    return bool(between) and len(between & board.occupied) == 1


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
    targets = [t for t in _clause_targets(m["targets"], ctx) if t != m["a"] and not _negated_target(m["targets"], t)]
    if ctx is not None and ctx.current is not None and not _lesson(ctx) and targets and re.match(r"держ|hold", m["verb"], re.IGNORECASE):
        from src.board_rules import pawn_held_back

        if all(pawn_held_back(ctx.current, a, chess.parse_square(t)) for t in targets):
            return None  # «пешка c6 держит твою пешку d4»: the pawn held back — d5 is under c6 (review-fp 03.11, E3)
    now = about_now or not _is_hypothetical(text, original if original is not None else text, m.start(),
                                            played=_just_played(ctx), ctx=ctx)
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
        behind = set() if _lesson(ctx) else _pin_behind(m)
        blocked = [t for t in targets if chess.parse_square(t) not in after.attacks(dest)
                   and not (t in behind and _through_one(after, dest, chess.parse_square(t)))]
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
            behind = set() if _lesson(ctx) else _pin_behind(m)
            blocked = [t for t in targets if not any(chess.parse_square(t) in b.attacks(a)
                                                     or (t in behind and _through_one(b, a, chess.parse_square(t)))
                                                     for b in standing)]
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
        if move.to_square == a and after.piece_type_at(a) == ptype:
            return None  # «ферзь идёт на g5 и атакует коня e5: … Qxg2»: named where it went, judged there (K3 02.11)
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
            targets = [t for t in _clause_targets(m["targets"], ctx) if t != a_name]
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
    the move before it captured on, where no such pawn stands (the client's game, 2026-10-07).

    The pair is judged where its line stands (F5 01.11): the moves written right before it in the same run
    («Nxd4 Nxd4 exd4» — the run, not its last two moves: 3...Nxd4 4.Nxd4 exd4 is legal) are played first, from a
    position of the turn or the one after the move the question is about («А почему не Nxd4?» — «после Nxd4 exd4»);
    a run that plays from none of them is not judged here (the line check reads lines)."""
    if _main_reading(ctx):
        return _recapture_issues_v1031(text, ctx)
    converted, _ = _to_san(text)
    moves = list(_MOVE.finditer(converted))
    if not any("x" in a["san"] and re.fullmatch(r"[a-h]x[a-h][1-8]", b["san"]) and a["san"][-2:] == b["san"][-2:]
               for a, b in zip(moves, moves[1:])):
        return []  # no capture taken back by a pawn: nothing to judge (the anchors below cost a key per board)
    anchors = [b for b in ctx.boards if ctx.is_given(b) and (ctx.current is None or b.board_fen() != chess.STARTING_BOARD_FEN
                                                            or ctx.current.board_fen() == chess.STARTING_BOARD_FEN)]
    # …and the position after the student's asked move, on the board on the screen: the line the answer tells from there
    if ctx.current is not None:
        for q in sorted(ctx.quoted):
            try:
                idea = ctx.current.copy(stack=False)
                idea.push_san(q)
                anchors.append(idea)
            except ValueError:
                continue
    issues = []
    for k in range(1, len(moves)):
        first, second = moves[k - 1], moves[k]
        san1, san2 = first["san"], second["san"]
        if "x" not in san1 or not re.fullmatch(r"[a-h]x[a-h][1-8]", san2) or san2[-2:] != san1[-2:]:
            continue
        if san1 == san2 and re.search(r"[A-Za-zА-Яа-яЁё]", converted[first.end(): second.start()]):
            # fix1102 K5: «лучший ответ — exf4, то есть принять гамбит: exf4», «(2.d4 exd4), но ты сыграл не exd4»: the
            # same move named again after words is that move restated, not a pawn taking back on its square
            continue
        # the moves written right before the pair, in one run with it («Nxd4 Nxd4 exd4»)
        j = k - 1
        while j > 0 and re.fullmatch(r"[\s,]*(?:\d{1,3}\s?\.{1,3}\s*)?", converted[moves[j - 1].end(): moves[j].start()]):
            j -= 1
        run = moves[j: k + 1]
        i = len(run) - 1
        if any(x["num"] or x["bdots"] for x in run):
            continue  # a written line («17. Bxd5 cxd5») is followed by the line check
        missing, played = None, False
        # An exchange told from its middle («коню некуда возвращаться: после Nxd4 exd4 белые играют Qxd4» — the
        # first capture on d4 left unwritten, or told in words): the position after a capture on that square by
        # the side to move is where it stands too.
        sq1 = chess.parse_square(san1[-2:])
        middle = []
        if ctx.current is not None:
            for mv in ctx.current.legal_moves:
                if mv.to_square == sq1 and ctx.current.is_capture(mv):
                    after = ctx.current.copy(stack=False)
                    after.push(mv)
                    middle.append(after)
        for board in anchors + middle:
            for color in (board.turn, not board.turn):
                trial = board.copy(stack=False)
                trial.turn = color
                try:
                    for x in run[: i - 1]:
                        trial.push_san(x["san"] + (x["check"] or ""))
                    move = trial.parse_san(san1)
                except ValueError:
                    continue
                if not trial.is_capture(move):
                    continue
                trial.push(move)
                played = True
                try:
                    trial.parse_san(san2)
                    missing = None
                    break
                except ValueError:
                    dest = chess.parse_square(san2[-2:])
                    rank = chess.square_rank(dest) + (-1 if trial.turn == chess.WHITE else 1)
                    if 0 <= rank <= 7:
                        missing = chess.square_name(chess.square(chess.FILE_NAMES.index(san2[0]), rank))
            else:
                continue
            break  # a position where the pawn stands: a line from there
        else:
            if played and missing:
                issues.append(f"{san2} is impossible after {san1}: there is no pawn on {missing} to take back on {san2[-2:]}")
            continue
    return issues


def _recapture_issues_v1031(text: str, ctx: CheckContext) -> list[str]:
    """The recapture check of 31.10, kept exactly for the /learn lesson tutor (the team's, Асан 19.10)."""
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


def _gap_from_words(board: chess.Board, words: str, nxt: str) -> Optional[tuple]:
    """(san, move, board after) for the one move *words* tell for the side to move on *board* («ферзь идёт на g5», or a
    written move the walk skips, such as castling), when exactly one move told there lets the written move *nxt* follow
    it; else None (K3 02.11)."""
    if not words.strip():
        return None
    try:
        from src.move_words import prose_moves

        found = {}
        told = [pm.get("move") for pm in prose_moves(words, board)]
        for w in _MOVE.finditer(words):  # a written move the walk does not play («12.Ba2 O-O-O 13.Bd2»: castling)
            try:
                told.append(board.parse_san(w["san"] + (w["check"] or "")))
            except ValueError:
                pass
        for mv in told:
            if mv is None or mv not in board.legal_moves:
                continue
            after = board.copy(stack=False)
            after.push(mv)
            if _parses(after, nxt):
                found[mv.uci()] = (board.san(mv), mv, after)
        return next(iter(found.values())) if len(found) == 1 else None
    except Exception:  # noqa: BLE001 — words are a bonus on top of notation
        logger.debug("gap from words failed", exc_info=True)
        return None


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
    prev_ghost = False  # *prev* comes from the start position standing in for a known board (plan 31.10 H)
    prev_flipped = False  # the line reached *prev* with a move made on a board whose side to move was changed to fit
    from src.config import detector_mode

    start_scene = ctx.current is not None and ctx.current.board_fen() != chess.STARTING_BOARD_FEN \
        and detector_mode("start_scene", ctx) == "on"
    prev_end = -1  # where the move that led to *prev* ends in *converted*
    # K3 02.11: the line skipped a ply its words did not let us play («После 4.Nxe5 ферзь идёт куда-то… 5.Nxf7 Qxg2»):
    # the boards its later moves are played on are guesses, so none of them is judged impossible or not to check.
    line_unknown = False
    # K3 02.11: a written move of this sentence fit no board («если чёрные сыграют Bxd1, то Bxf7+ Ke7 Nd5#» with the
    # board after the student's Nxe5 not given): the moves after it belong to the line it began, not to a board of the
    # turn — a «+»/«#» or a blocked capture is not judged on one.
    unplaced = last_unplaced = False
    lesson = _lesson(ctx)
    for m in _MOVE.finditer(converted):
        unplaced, last_unplaced = unplaced or last_unplaced, False
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
        if san in ctx.quoted and not san.startswith("O-O") and not _main_reading(ctx):
            # The student's own move repeated: never judged, but followed when it is a move of the line here, so the
            # moves after it are read after it (not on the board as it stands, the side to move changed to fit).
            qcolors = [chess.BLACK] if dots in ("...", "…") else [chess.WHITE] if num and dots == "." else [chess.WHITE, chess.BLACK]
            followed = None
            for board in ([prev] if prev is not None else []) + ([ctx.current] if ctx.current is not None else []):
                if board.turn in qcolors and _parses(board, san + (m["check"] or "")):
                    followed = board
                    break
            if followed is not None:
                trial = followed.copy(stack=False)
                move = trial.parse_san(san + (m["check"] or ""))
                trial.push(move)
                prev_trusted = prev_trusted if followed is prev else ctx.is_given(followed)
                prev_flipped = followed is prev and prev_flipped
                prev, prev_ghost = trial, False
                prev_end = in_line_until = m.end()
                ctx.add(trial.fen(), derived=True)
            continue
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
        # K3 02.11 (trap-blackburne live): a numbered move one ply past the line's board («После 4.Nxe5 ферзь идёт на g5
        # …: 5.Nxf7 Qxg2») — the ply between is told in words. Played when the words name exactly one move after which
        # this one is legal; otherwise the line's board is unknown from here on.
        if not lesson and prev is not None and num and not list_item and len(colors) == 1 and colors[0] != prev.turn \
                and int(num) == prev.fullmove_number + (1 if prev.turn == chess.BLACK else 0):
            filled = _gap_from_words(prev, converted[max(prev_end, 0):m.start()], full)
            if filled is not None:
                gap_san, gap_move, prev = filled
                ctx.add(prev.fen(), derived=True)
                ctx.scene_trail.append((gap_san, prev.copy(stack=False), gap_move))
                ctx.written_trail.append((gap_san, prev.copy(stack=False), gap_move))
            else:
                line_unknown = True
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
        start_scene_off = start_scene and fallback is not None and fallback.board_fen() == chess.STARTING_BOARD_FEN
        # The line's own continuation first, then the boards of the turn (the one
        # on the screen before the rest), the start position standing in for an
        # unknown one last — «4...d5 5.exd5» used to start from the start
        # position, where 4...d5 is legal too, and 5.exd5 then found no pawn.
        boards = list(ctx.boards)
        ordered = ([ctx.current] if ctx.current is not None and ctx.current in boards else []) \
            + [b for b in boards if b is not fallback and b is not ctx.current] + ([fallback] if fallback is not None else [])
        # A board where it is that side's move comes before one where the side is changed to fit: «15.Bxd7+ …
        # 16.Qb8+» is the game's 16th move, not White moving twice after 15.Bxd7+ (2026-10-08).
        ghost_now = False
        # A move numbered as the next ply of the line it continues («3...Nxd4 4.d5») is that line's move: illegal
        # there, it is not re-anchored on a board where the other side is made to move (4.d5 on the board now with
        # White to move, the pawn still on d4 — review-miss 01.11, wrong-board path 3). It stays a plan the lenient
        # checks below may still accept; it sets no scene. (F2's patch; F5 adds: not after a line that reached its board
        # with the side changed, and not on the lesson surface, which keeps 31.10's walk.)
        next_ply = prev is not None and bool(num) and not list_item and colors == [prev.turn] \
            and int(num) == prev.fullmove_number and not prev_flipped and not _main_reading(ctx)
        line_prev, line_trusted = prev, prev_trusted
        # K3 02.11 (op-show-italian live): the next move of a line being followed is played on that line's board; when it
        # does not fit there, no other board of the turn is its board — its «+»/«#» is not judged there.
        line_bound = not lesson and prev is not None and (continues_line or next_ply)
        candidates = ([(prev, [prev.turn])] if prev is not None and prev.turn in colors else []) \
            + [(b, [c for c in colors if c == b.turn]) for b in ordered] \
            + ([] if next_ply else [(b, [c for c in colors if c != b.turn]) for b in ordered])
        for board, board_colors in candidates:
            if board is prev:
                trusted = prev_trusted
            else:
                trusted = ((board is not fallback and ctx.is_given(board))
                           or (board is fallback and num == "1" and dots == "." and not list_item)) \
                    and not line_bound and not unplaced
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
                if not legal_somewhere and start_scene_off and not trusted \
                        and (board is fallback or (board is prev and prev_ghost)):
                    # Plan 31.10 H (start_scene): the real board is known and is not the start position — a move
                    # legal only on the start position standing in for an unknown one (and the moves after it) is
                    # a plan, not a line the later claims are about: it is followed (its boards stay among the
                    # turn's, for the lenient "some board allows it" checks), but it sets no scene (prod plan-kid
                    # 29.10: «...f5» read on the start position, then «бить на e4» judged there).
                    legal_somewhere = True
                    plan_san = trial.san(move)
                    trial.push(move)
                    ctx.written_trail.append((plan_san, trial.copy(stack=False), move))
                    prev, prev_trusted, ghost_now = trial, False, True
                    prev_end = m.end()
                    ctx.add(trial.fen(), derived=True)
                    break
                if not legal_somewhere:
                    legal_somewhere = True
                    scene_san = trial.san(move)
                    trial.push(move)
                    prev_flipped = color != board.turn or (board is prev and prev_flipped)
                    prev, prev_trusted, ghost_now = trial, trusted, False
                    prev_end = m.end()
                    ctx.add(trial.fen(), derived=True)  # a line written in the answer goes on from here
                    ctx.scene, ctx.scene_san, ctx.scene_age = trial.copy(stack=False), scene_san, 0
                    ctx.scene_trail.append((scene_san, ctx.scene, move))
                    ctx.written_trail.append((scene_san, ctx.scene, move))
                if suffix_ok or not m["check"]:
                    break
            if legal_somewhere and (suffix_ok or not m["check"]):
                break
        in_line_until = m.end() if legal_somewhere else -1
        prev_ghost = ghost_now
        if not legal_somewhere:
            prev, prev_trusted, prev_ghost = None, False, False
            last_unplaced = not lesson  # the moves after this one (K3 02.11)
        if line_unknown:
            continue  # K3 02.11: after a ply the words skipped, the line's board is a guess — nothing judged on it
        if legal_somewhere:
            if suffix_judged and not suffix_ok and not bare_capture:
                label = (f"{num}{dots}" if num else (dots or "")) + full
                issues.append(f"{label} is not checkmate" if m["check"] == "#" else f"{label} gives no check")
            continue
        if bare_capture:
            continue
        if next_ply and line_trusted and not (re.fullmatch(r"[a-h](?:x[a-h])?[18]", san) and _parses(line_prev, full + "=Q")):
            # F5 (01.11): the line began on a board of the turn with its own side to move and every move so far was legal
            # there: its next move, legal nowhere after it, is impossible — not a plan of some other position («После
            # 3...Nxd4 4.d5 конь c6 под ударом»: the d-pawn is gone). «4.a8» without its piece is a promotion.
            issues.append(f"{num}{dots}{full} is impossible after the moves before it in this line "
                          f"(position {line_prev.fen()})")
            continue
        ptype = chess.PIECE_SYMBOLS.index(san[0].lower()) if is_piece else chess.PAWN
        dest = chess.parse_square(re.findall(SQ, san)[-1])
        capture = "x" in san or bool(m["check"])
        # «Возьми ферзя ладьёй: Rxh4» with the h2 pawn between (stand, 2026-10-04):
        # a capture written for the board on the screen, by a piece that is there
        # but cannot get through, is impossible — not a plan from another position.
        if is_piece and "x" in san and prev is None and ctx.current is not None and not list_item and not unplaced \
                and not _is_hypothetical(text, text, m.start(), ctx=ctx) and not _CONTINUES.match(text):
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
        side = {1: "white ", 0: "black "}.get(colors[0], "") if len(colors) == 1 else ""
        either = "" if side else " of either side"
        label = (f"{num}{dots}" if num else (dots or "")) + full
        issues.append(f"{label} is impossible: no {side}{_NAMES[ptype]}{either} can "
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


# «вариант четырёх коней», «система с g3», "the Four Knights Variation": the words right before an opening name that make
# it the title of a variation inside another opening, not the opening itself.
_VARIATION_WORD = re.compile(r"(?<![а-яa-z])(?:вариант\w*|систем\w*|ветк\w*|variation|line|system)\s+(?:[а-яa-z]+\s+)?$")
_NAME_SUFFIX = re.compile(r"\s+(?:game|opening|defen[cs]e|gambit|attack|system|variation|counterattack)$", re.IGNORECASE)


def _names_variation_of(name: str, real: str) -> bool:
    """The core of the book name *name* («Four Knights» of the Four Knights Game) is the title of a variation of the
    board's own line *real* («English Opening: King's English Variation, Four Knights Variation»)."""
    core = _NAME_SUFFIX.sub("", name.split(":", 1)[0].strip()).strip().lower()
    if not core or ":" not in real:
        return False
    parts = [p.strip().lower() for p in re.split(r"[:,]", real.split(":", 1)[1])]
    return any(p == core or p.startswith(core + " ") for p in parts)


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
    position = ctx.current
    if moves:
        try:
            position = chess.Board()
            for san in moves:
                position.push_san(san)
        except ValueError:
            position = ctx.current
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
        if _VARIATION_WORD.search(lowered[max(0, at - 30):at]) and _names_variation_of(name, real):
            continue  # «английское начало, вариант четырёх коней»: the English's Four Knights Variation (A28), not the
            # Four Knights Game (K7 02.11, fresh-fp a20#0) — a line called a variation is matched to the real line's variations
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
        if position is not None and any(e[1] == name or e[1].startswith((name + ",", name + ":"))
                                        for e in book.lineage(position)[0]):
            continue  # the board is on that line by another move order (1.e4 c5 2.Nf3 d6 … 5...e6 is the Scheveningen; fix 01.11)
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
        if _is_hypothetical(text, original, m.start(), played=played, ctx=ctx):
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


# The attacker named right after «под ударом / атакован»: a bare square («под ударом b3») or a move («под ударом Nd5»).
_ATTACKER_AFTER = re.compile(r"\s+(?:(?:пешки|пешкой|by)\s+)?(?:(?:ход\w*|move)\s+)?(?:(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8])"
                             r"|(?P<sq>[a-h][1-8]))(?![0-9a-z])", re.IGNORECASE)
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
        if any((pc := b.piece_at(sq)) is not None and pc.piece_type == ptype for b in _turn_boards(ctx, text)):
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
_FUTURE_ATTACK = re.compile(r"напад[её]т|нападут", re.IGNORECASE)
_ATTACK_IN_CLAUSE = re.compile(_B2 + "(?:" + _ATTACK_FINITE + ")" + _E, re.IGNORECASE)
_OBJECT_VERB_IN_CLAUSE = re.compile(_B2 + "(?:" + _ATTACK_FINITE + "|" + _OTHER_FINITE + ")" + _E, re.IGNORECASE)
_CLAUSE_SPLIT = re.compile(r"[;—–]|,\s*(?:а|но|однако|зато|хотя|поэтому|так\s+что|while|but|so|yet)\s", re.IGNORECASE)


def _clauses(text: str) -> list[str]:
    return [c for c in _CLAUSE_SPLIT.split(text) if c and c.strip()]


# fix1102 K5: an object after a gerund in its clause is the gerund's — «Пешка d4 нападает на e5, открывая слону c1
# дорогу на g5»: «слону c1» is no object of «нападает» (the bishop was judged as attacked). Only such objects are left
# unjudged; the clause itself is not split (its negations and relative clauses still count).
_GERUND_BEFORE = re.compile(r",\s*[а-яё]+(?:ая|яя|уя|юя|ав|яв|ив|ув|вши|ясь|аясь)\s[^,]*$", re.IGNORECASE)


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


def _turn_boards(ctx: CheckContext, text: str = "") -> list:
    """The boards of the turn a named piece may stand on — without the bare start position unless it is
    the position in front of the student, or the sentence names it («в начальной позиции», review fp2 01.11)."""
    if ctx.current is not None and ctx.current.board_fen() == chess.STARTING_BOARD_FEN:
        return ctx.boards
    out = [b for b in ctx.boards if b.board_fen() != chess.STARTING_BOARD_FEN]
    if text:
        try:
            from src.claim_scene import _START_CUE

            if _START_CUE.search(text.replace("ё", "е")):
                out.append(chess.Board())
        except Exception:  # noqa: BLE001
            pass
    return out


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


def _subject_in_force_here(before: str, ctx: CheckContext) -> bool:
    """The subject a clause goes on with — the last piece named on its square as a subject before it in the sentence
    («Конь на e8 бьёт с шахом короля, а заодно нападает на ферзя g7») — stands on the board now (or none is named).
    A clause with a subject of its own is judged by _clause_judged_here; this one covers the clause that has none."""
    last = None
    for m in _CLAUSE_SUBJECT.finditer(before):
        if m["en"] and _EN_OBJECT_BEFORE.search(before[: m.start()]):
            continue
        last = m
    if last is None or ctx.current is None:
        return True
    ptype = _piece_type((last["ru"] or last["en"]).lower())
    piece = ctx.current.piece_at(chess.parse_square((last["a"] or last["b"]).lower()))
    return piece is not None and (ptype is None or piece.piece_type == ptype)


def _object_ghost_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None or ctx.current.board_fen() == chess.STARTING_BOARD_FEN:
        return []
    if re.search(r"(?<![а-яa-z])(?:партии|партия|партию|game|played)(?![а-яa-z])", text):
        return []
    boards = _turn_boards(ctx, text)
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
    lesson = _lesson(ctx)
    for clause in _clauses_about_now(text):
        if not _ATTACK_IN_CLAUSE.search(clause) or not _clause_judged_here(clause, ctx):
            continue
        if not lesson and all(_FUTURE_ATTACK.fullmatch(v.group(0)) for v in _ATTACK_IN_CLAUSE.finditer(clause)):
            # fix1102 K5: «Оттуда она нападёт на пешку e4», «Ферзь нападёт на пешку e5»: a perfective future tells the
            # attack after a move the clause does not write — not the board as it is (fresh-fp e03#1, f04#1)
            continue
        for m in _objects(clause):
            if _NEGATION.search(clause[max(0, m.start() - 12):m.start()]):
                continue
            if not lesson and _GERUND_BEFORE.search(clause[:m.start()]):
                continue
            at = text.find(clause)
            upto = (at if at >= 0 else 0) + m.start()
            if _is_hypothetical(text, original, upto, ctx=ctx):
                continue  # «после Nb5 конь нападёт на пешку c7»: a line, judged on the derived boards elsewhere
            if _SAN_IN_TEXT.search(_to_san(original[:upto])[0]) or _PROMOTION_IN_TEXT.search(_to_san(original[:upto])[0]):
                continue  # «cxd4: пешка c5 … нападает на ферзя c3»: after the move written before it
            if not _subject_in_force_here(text[:upto], ctx):
                continue  # «Конь на e8 бьёт с шахом…, а заодно нападает на ферзя g7»: the subject the clause goes on with
                          # is not on this board (K3 02.11, underpromo live)
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
# A written promotion («e8=N+») is a move too, whatever its file: what the sentence says after it is about the board
# after it (K3 02.11, underpromo live: «e8=N+ даёт шах и нападает на ферзя g7» judged on the board before it).
_PROMOTION_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])[a-h](?:x[a-h])?[18]=[QRBN][+#]?")


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
    if _SOLUTION_WORD.search(text) and not _is_hypothetical(text, original, 0, whole=True, ctx=ctx):
        wrong = [m for m in moves if _norm_san(m) not in allowed]
        if wrong:
            return [f"the puzzle's solution is {' '.join(solution)}; {wrong[0]} is not in it"]
    return []


# «e5xd5», «e5:d5»: a capture written from square to square — the piece standing on the first square must
# be able to take that way (a pawn takes one square diagonally forward: «обычным взятием — e5xd5» with
# the pawns on e5 and d5 side by side, production 19.10).
# (fix1102 K5: «начать с 2...e6: e6 — пешка d5 получает поддержку» was read as «e6xe6». A colon is a capture only
# written tight, «e5:d4» — with a space after it, it is punctuation; and no piece captures onto its own square.)
_CAPTURE_CHAIN_V1031 = re.compile(rf"(?<![A-Za-z0-9])(?P<a>{SQ})\s?[x×:]\s?(?P<b>{SQ})(?![0-9])")  # the /learn tutor's
_CAPTURE_CHAIN = re.compile(rf"(?<![A-Za-z0-9])(?P<a>{SQ})(?:\s?[x×]\s?|:)(?P<b>{SQ})(?![0-9])")


def _capture_chain_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    lesson = _lesson(ctx)
    for m in (_CAPTURE_CHAIN_V1031 if lesson else _CAPTURE_CHAIN).finditer(text):
        a, b = chess.parse_square(m["a"].lower()), chess.parse_square(m["b"].lower())
        if a == b and not lesson:
            continue  # the same square named twice («e6: e6»), not a capture
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
        if kind == "hanging" and (am := _ATTACKER_AFTER.match(text, m.end())) and (
                am["san"] or ctx.current.piece_at(chess.parse_square(am["sq"].lower())) is None):
            continue  # «Слон c4 под ударом b3 уйдёт …» (review miss2 01.11): the attacker is a move to come, not the board now
        if kind == "hanging" and re.match(r"\s+(?:в\s+воздухе|in\s+the\s+air|без\s+дела)", text[m.end():]):
            continue  # «ладья висит в воздухе и ничего не делает»: idle, not en prise (replay, 2026-10-05)
        if kind != "undefended" and _NEGATION.search(text[: m.start(verb and ("v" if m["v"] else "v2" if m["v2"] else "v3"))]):
            continue  # «не висит», "is not hanging"
        if _is_hypothetical(text, original, m.start(), ctx=ctx):
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
            if seen and ctx.current is not None and (piece := ctx.current.piece_at(sq)) is not None \
                    and (named is None or piece.piece_type == named):
                defenders = [chess.square_name(d) for d in ctx.current.attackers(piece.color, sq)]
                name = _NAMES[piece.piece_type]
                if kind == "undefended" and not defenders:
                    continue  # undefended on the board now too: the claim holds here (live 02.11: «defended (by )»)
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
        if _is_hypothetical(text, original, m.start(), ctx=ctx):
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
_PLURAL_PRONOUNS = {"них", "они", "им", "them", "they"}
_EN_PRONOUNS = {"them", "they", "he", "she"}
# What a 3rd-person pronoun can stand for: never «ты», «я», «вы» (another person), and a Russian one agrees in number.
_THIRD_PERSON = {
    "plural": {"белые", "белых", "белым", "черные", "черных", "черным"},
    "singular": {"соперник", "соперника", "сопернику", "противник", "противника", "движок"},
    "en": {"white", "black", "opponent", "engine"},
}
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
# Plan 31.10 M2 (material_order), rebuilt as a grammar (fix 01.11 F4): a material claim is read from its parts, not from
# one word order — a LEAD PREDICATE (its meaning class: more / less; a balance, an extra unit, a count), the QUANTITY it
# names (a number, «всего/только», units in any case, «ладью и слона»), the SIDE it is about (the subject, «у X», the
# genitive after «перевес»; pronouns through _side_color), in either order and as a noun («перевес белых — одна
# фигура»). «белые впереди на целую ладью», «ты отстаёшь на ферзя», «у белых преимущество в ладью», «материально
# белые лучше на две пешки», «у чёрных одна лишняя пешка», «у белых лишняя ладья, но больше ничего» (prod st2 29.10:
# three wrong counts went out; review-miss 01.11: 6/16). A claim it cannot read safely (an evaluation in pawns, a flank
# majority, a process «выигрывают пешку») stays unjudged.
_MQ_NUM = (r"(?:одн(?:а|у|ой|им|ого|ому)|один|два|две|двух|двумя|пар[ауы]|три|тр[её]х|тремя|четыре|четыр[её]х|"
           r"пять|пяти|шесть|шести|семь|семи|восемь|восьми|\d{1,2})")
_MQ_UNIT = r"(?:пешк\w*|пешек|фигур\w*|кон(?:ь|я|ем|ю|е|и|ей|ям|ями)|слон\w*|ладь\w*|ладей|ферз\w*|качеств\w*)"
# a second unit of «на ладью и слона»: an oblique form only (not «…, и слон сильнее»)
_MQ_UNIT_OBL = (r"(?:пешк(?:у|и|ой|ами)|пешек|фигур(?:у|ы|ой|ами)?|кон(?:я|ем|ей|ям|ями)|слон(?:а|ом|ов|ами)|"
                r"ладь(?:ю|и|ей|ям|ями)|ладей|ферз(?:я|ем|ей|ями)|качеств(?:о|ом|а))")
_MQ_MOD = r"(?:всего|только|лишь|ровно|цел\w+)"
_MQ_ONE = rf"(?:(?:{_MQ_NUM}|{_MQ_MOD})\s+){{0,3}}"
# between two items of a list: «ферзя, слона и двух коней», «слона плюс пешку» (verify1102 B1: the reader stopped at
# the first item of «впереди на ферзя, слона и двух коней»)
_MQ_SEP = r"(?:\s*,\s*(?:(?:и|плюс)\s+)?|\s+(?:и|плюс|\+)\s+)"
_MQ = rf"(?P<q>{_MQ_ONE}{_MQ_UNIT}(?:{_MQ_SEP}{_MQ_ONE}{_MQ_UNIT_OBL})*)(?![а-я])"
# one more item after what a frame read (past the clause too): the list was not read whole — the claim is unjudged
_MQ_MORE = re.compile(rf"\s*(?:,\s*)?(?:(?:и|плюс|\+)\s+)?{_MQ_ONE}(?P<u>{_MQ_UNIT})(?![а-я])")
_MQ_NOM_SG = re.compile(r"(?:пешка|конь|слон|ладья|ферзь|фигура)$")
_MQ_FILL = r"(?:(?:уже|сейчас|теперь|пока|вс[её]\s+ещ[её]|по\s+материалу|материально|по\s+очкам|тебе|ему|им)\s+){0,3}"
_MAT_FRAMES = [(name, re.compile(_B2 + rx, re.IGNORECASE)) for name, rx in (
    # «впереди на ладью», «отстаёшь на ферзя», «ведут по материалу на одну ладью», «лучше на две пешки»
    ("after", r"(?P<pred>впереди|позади|отста\w+|вед[уеё]т|вед[её]шь|вед[её]те|в\s+плюсе|в\s+минусе|лучше|хуже|больше|меньше)"
              rf"\s+{_MQ_FILL}на\s+{_MQ}"),
    # «уступаешь по материалу целую ладью», «проигрываешь ладью по материалу» (a material word required, below)
    ("direct", rf"(?P<pred>уступа\w+|проигрыва\w+|выигрыва\w+)\s+{_MQ_FILL}(?:на\s+)?{_MQ}"),
    # «на пешку больше», «пешкой меньше», «на две пешки впереди»
    ("before", rf"(?:на\s+)?{_MQ}\s+{_MQ_FILL}(?P<pred>больше|меньше|впереди|позади)"),
    # «перевес белых — одна фигура», «у белых преимущество в ладью», «материальный перевес в две пешки»
    ("noun", r"(?P<pred>(?:материальн\w+\s+)?(?:перевес|преимуществ)\w*)\s+(?:(?:у|на\s+стороне)\s+)?"
             r"(?:(?P<gside>белых|ч[её]рных|тебя|вас|соперника|противника|них)\s+)?(?:по\s+материалу\s+)?"
             rf"(?:в\s+|[—–:=]\s*|-\s+|составляет\s+|равен\s+){_MQ}"),
    # «одна лишняя пешка», «лишняя ладья», «две лишние пешки»
    ("extra", rf"(?P<q>(?:(?:{_MQ_NUM}|всего|только|лишь)\s+){{0,2}})(?P<pred>лишн\w+)\s+"
              rf"(?P<u>{_MQ_UNIT}(?:{_MQ_SEP}(?:{_MQ_NUM}\s+)?{_MQ_UNIT})*)(?![а-я])"),
    # «пешка лишняя», «одна пешка лишняя»
    ("extra_after", rf"(?P<q>(?:(?:{_MQ_NUM}|всего|только|лишь)\s+){{0,2}})(?P<u>{_MQ_UNIT})\s+(?P<pred>лишн\w+)"),
    # «у белых больше пешек»: a count of one kind
    ("count", r"(?P<pred>больше|меньше)\s+(?P<u>пешек|коней|слонов|ладей|ферзей)(?![а-я])"),
)]
# The side a claim is about: the subject or «у X» in the clause before the predicate (not «от X», «чем у X»).
_MAT_SIDE = re.compile(r"(?<![а-яa-z])(?P<pre>(?:от|чем|за|против|для|с|по|к)\s+(?:у\s+)?)?(?:у\s+)?"
                       r"(?P<s>белые|белых|ч[её]рные|ч[её]рных|ты|тебя|вы|вас|соперник|соперника|противник|противника|"
                       r"они|них|я|меня)(?![а-яa-z])", re.IGNORECASE)
_MAT_CLAUSE_END = re.compile(r"[.!?;]|,\s*(?:но|а|зато|хотя|однако|и|причем|поэтому|так\s+что|тогда|пока)(?![а-я])|\s(?:но|а|зато)\s")
# Claims not read as the material now: a flank or centre majority, an evaluation in pawns, a question.
_MAT_NOT_TOTAL = re.compile(r"фланг|крыл|в\s+центре|на\s+(?:королевск|ферзев)|большинств|majority|"
                            r"оценк|движ[оеку]|stockfish|компьютер|эвал|позиционн|в\s+пешк(?:ах|ам)|\d[.,]\d", re.IGNORECASE)
_MAT_GAP = re.compile(r"(?:\s*[—–:,]?\s*(?:уже|сейчас|теперь|пока|вс[её]|ещ[её]|по\s+материалу|по\s+очкам|материально|тоже|"
                      r"также|снова|опять|явно|заметно|ощутимо|в\s+итоге|в\s+результате|фактически|реально|просто|сразу|"
                      r"даже|ведь|же|здесь|тут|на\s+доске|в\s+этой\s+позиции|after|по-прежнему|по\s+сути))*\s*[—–:,]?\s*",
                      re.IGNORECASE)
_MAT_AGAINST = re.compile(r"\s*(?:против|за|vs\.?|versus)\s+(?:[а-яё]+\s+)?(?:пешк|кон|слон|ладь|ферз|фигур|качеств)",
                          re.IGNORECASE)
# The sentence counts in points: «по материалу», «по очкам», «в пересчёте», a trade told («конь за пешку»), "in points".
_MAT_POINTS = re.compile(r"материал|очк|пересч[её]т|(?:кон[ья]|слон\w*|фигур\w*|ладь\w*|ферз\w*|качеств\w*)\s+за\s+(?:пешк|пару)|"
                         r"material|points?(?![a-z])", re.IGNORECASE)
_MAT_WORD = re.compile(r"материал|по\s+очкам", re.IGNORECASE)
_MAT_FUTURE = re.compile(r"стан(?:ет|ут|ешь|ем)|окаж|получ(?:ат|ит|ишь|им)|выйд|будет|будут|будешь", re.IGNORECASE)
_MAT_ONLY = re.compile(r"(?<![а-я])(?:всего|только|лишь|ровно)(?![а-я])")
_MAT_NOTHING_ELSE = re.compile(r"\s*,?\s*(?:но|и|а)?\s*(?:больше\s+ничего|ничего\s+больше|и\s+вс[её])(?![а-я])")


def _mat_clause(text: str, start: int, end: int) -> str:
    """The clause of *text* around [start, end): from the last clause boundary before it to the next one after it."""
    starts = [x.end() for x in _MAT_CLAUSE_END.finditer(text[:start])]
    tail = _MAT_CLAUSE_END.search(text, end)
    return text[starts[-1] if starts else 0: tail.start() if tail else len(text)]


def _mat_units(q: str) -> tuple[list, bool, bool]:
    """([(n, kind, points)], a number said, «всего/только» said) of a quantity «две пешки», «ладью и слона»."""
    units, n, said_num, only = [], None, False, False
    for w in re.findall(r"[а-яa-z0-9]+", (q or "").lower().replace("ё", "е")):
        if re.fullmatch(_MQ_NUM, w):
            n, said_num = _num(w), True
        elif re.fullmatch(r"всего|только|лишь|ровно", w):
            only = True
        elif re.fullmatch(_MQ_UNIT, w):
            kind, points = _unit(w)
            units.append((n or 1, kind, points))
            n = None
    return units, said_num, only


def _lead_holds(board: chess.Board, color: bool, units: list, more: bool, mode: str, in_points: bool = False) -> bool:
    """*mode* 'balance': the whole balance is that much («впереди на ладью», «на две пешки больше» — in pawns of points
    too); 'count': that many of the kind more («две лишние пешки»); 'atleast': at least that («лишняя пешка»);
    'kind': more of that kind («больше пешек»)."""
    if len(units) > 1:
        try:
            from src.game_record import material as _material_of

            diff = _material_of(board)["diff"] * (1 if color == chess.WHITE else -1) * (1 if more else -1)
        except Exception:  # noqa: BLE001 — a broken material count leaves the claim unjudged (fail-open, F8)
            logger.debug("material count failed", exc_info=True)
            return True
        if mode != "balance":  # «лишние слон, конь и пешка»: those extras at least, in points (more may go unnamed)
            return diff >= sum(n * p for n, _, p in units) - 1
        return abs(diff - sum(n * p for n, _, p in units)) <= 1
    n, kind, points = units[0]
    if mode == "balance":
        return _material_holds(board, color, kind, points, n, more, True, in_points)
    if mode == "atleast":
        return _material_holds(board, color, kind, points, n, more, False)
    mine, theirs = _counts(board, color), _counts(board, not color)
    sign = 1 if more else -1
    key = {"pawn": chess.PAWN, "knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK, "queen": chess.QUEEN,
           "minor": "minors"}.get(kind)
    if key is None:  # «качество»: a rook for a minor piece
        return _material_holds(board, color, kind, points, n, more, mode != "count")
    d = (mine[key] - theirs[key]) * sign
    return d == n if mode == "count" else d >= 1


def _material_claims(text: str, ctx: CheckContext) -> list[tuple]:
    """(side start, colour, units, more, mode, span, frame) for each material claim of *text* (lowercased) the grammar
    can read — see _MAT_FRAMES."""
    out, seen = [], set()
    for frame, rx in _MAT_FRAMES:
        for m in rx.finditer(text):
            pred = m["pred"].lower().replace("ё", "е")
            # the clause: from the last boundary before the claim to the next one after it
            head = text[: m.start()]
            starts = [x.end() for x in _MAT_CLAUSE_END.finditer(head)]
            c0 = starts[-1] if starts else 0
            tail = _MAT_CLAUSE_END.search(text, m.end())
            c1 = tail.start() if tail else len(text)
            clause = text[c0:c1]
            if "?" in text[m.end(): c1 + 1] or _MAT_NOT_TOTAL.search(clause):
                continue
            if (frame == "direct" or pred.startswith(("лучше", "хуже", "вед"))) and not _MAT_WORD.search(clause):
                continue  # «уступаешь пешку», «лучше на две пешки», «ведёт на ферзя»: not the balance by themselves
            if m.start("pred") in seen:
                continue
            if _MAT_AGAINST.match(text, m.end()) or (frame == "before" and _MAT_AGAINST.match(text, m.end("q"))):
                continue  # «преимущество в ладью против слона», «лишняя ладья за слона»: an imbalance, read elsewhere
            if frame == "before" and not re.match(r"на\s", m.group(0)) and \
                    not re.search(r"(?:ой|ей|[её]й|ем|[её]м|ом|ами|ями)$", m["q"]):
                continue  # «пешек меньше»: a count, not a lead («на пешку меньше», «пешкой меньше»)
            side_word, side_at = None, None
            if m.groupdict().get("gside"):
                side_word, side_at = m["gside"], m.start("gside")
            else:
                for s in _MAT_SIDE.finditer(text, c0, m.start("pred") if frame != "before" else m.start()):
                    if not s["pre"]:
                        side_word, side_at = s["s"], s.start("s")
            if side_word is None:
                continue
            color = _side_color(side_word, ctx, text[:side_at])
            if color is None:
                continue
            if not m.groupdict().get("gside"):
                # the side is the predicate's own subject: only filler words between them («у белых конь ведёт на
                # ферзя атаку», «белые давят больше на пешку» name no lead)
                gap_end = m.start() if frame in ("before", "extra", "extra_after") else m.start("pred")
                gap = text[side_at: gap_end]
                gap = gap[re.match(r"\w+", gap).end():] if re.match(r"\w+", gap) else gap
                if not _MAT_GAP.fullmatch(gap):
                    continue
            if _negated_before_pred(text, m.start("pred")) or _negated_before_pred(text, m.start()):
                continue
            if _FUTURE_FILL.search(text[side_at: m.end()]) or _MAT_FUTURE.search(text[side_at: m.end()]):
                continue
            if frame in ("extra", "extra_after", "count"):
                units, said_num, only = _mat_units((m.groupdict().get("q") or "") + " " + m["u"])
                only = only or bool(_MAT_NOTHING_ELSE.match(text, m.end()))
                mode = "kind" if frame == "count" else ("balance" if only else ("count" if said_num else "atleast"))
                more = True if frame != "count" else pred.startswith("больше")
            else:
                units, said_num, only = _mat_units(m["q"])
                mode = "balance"
                more = pred.startswith(("впереди", "вед", "в плюс", "лучше", "больше", "перевес", "преимуществ",
                                        "материальн", "выигрыва"))
            if not units:
                continue
            more_item = _MQ_MORE.match(text, m.end("u") if frame in ("extra", "extra_after", "count") else
                                       (m.end("q") if frame != "before" else m.end()))
            if more_item and frame != "before" and not (frame not in ("extra", "extra_after") and
                                                        _MQ_NOM_SG.search(more_item["u"])):
                continue  # «впереди на ферзя, слона, и двух коней»: a list read only in part is left unjudged
            if frame == "noun" and any(k == "bishop" and n == 2 for n, k, _ in units):
                continue  # «преимущество двух слонов»: the bishop pair, not the balance
            seen.add(m.start("pred"))
            out.append((side_at, color, units, more, mode, text[min(side_at, m.start()): m.end()].strip(), frame, m.end()))
    return out


def _mat_cond_after(text: str, end: int) -> bool:
    """The rest of the claim's clause after *end* names a condition («у чёрных на пешку больше после других ходов»,
    «… если он возьмёт»): the claim is about another board (verify1102 B1)."""
    from src.material_frames import conditional

    tail = _MAT_CLAUSE_END.search(text, end)
    return conditional(text[end: tail.start() if tail else len(text)])


def _negated_before_pred(text: str, at: int) -> bool:
    return bool(re.search(r"(?<![а-яa-z])(?:не|ни|нет)\s+(?:\w+\s+)?$", text[max(0, at - 16): at]))


# Equality, hedged or not: «материал равный», «по материалу равенство», «материал почти равный» (within 2 points).
_MATERIAL_EQUAL_ANY = re.compile(
    _B2 + r"(?:материал\w*\s+(?:(?P<h1>почти|примерно|практически|приблизительно|фактически|более-менее|плюс-минус|"
    r"формально|в\s+целом)\s+|пока\s+|сейчас\s+|вс[её]\s+ещ[её]\s+|по-прежнему\s+)*(?:рав\w+|одинаков\w*|поровну)|"
    r"по\s+материалу\s+(?:(?P<h2>почти|примерно|практически|приблизительно|фактически)\s+|пока\s+|сейчас\s+)*"
    r"(?:равенств\w*|поровну|равно)|материальн\w+\s+(?:равенств|равновеси)\w*|"
    r"material\s+is\s+(?:still\s+)?(?P<h3>roughly\s+|about\s+|almost\s+|nearly\s+)?(?:equal|even|level|balanced))",
    re.IGNORECASE)
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
    if w.startswith(("пешк", "пешек", "pawn")):
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
        # «им», «они», «у них» stand for a plural side (белые, чёрные); «ему», «у него» for a singular one (соперник,
        # движок): «Белые на пешку впереди, и движок даёт им …» — «им» are the White pieces, not the engine (K7 02.11)
        want = _THIRD_PERSON["en" if w in _EN_PRONOUNS else ("plural" if w in _PLURAL_PRONOUNS else "singular")]
        named = [n for n in _SIDE_NAMED.findall(before) if n.lower().replace("ё", "е") in want]
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
                    balance: bool = True, in_points: bool = False) -> bool:
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
        # «впереди на две пешки по материалу / по очкам», «… : конь за пешку»: the balance in pawns of points (a knight
        # for a pawn is +2) when the sentence counts in points (review-fp 01.11, Fried Liver); without that it is a count
        # of pawns (graded prod 06.10, «Black is up two pawns already» with a knight for a pawn: wrong)
        return (dp == n and abs(dnp) <= 1) or (in_points and dp + dnp == n)
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


# A unit as the object of «выиграть/проиграть»: «выиграли (у тебя) (целых) две пешки», «проиграл качество», "won a pawn".
_UNIT_OBJECT = re.compile(
    r"(?:\s+(?:у|для)\s+\w+)?(?:\s+(?:уже|ещё|еще|сразу|целых|целую|целого|всего|лишь|только|одну|одного|один|две|два|"
    r"три|четыре|пару|несколько|лишнюю|лишнего|лишний|ещё\s+одну|a|an|one|two|three|the|another|extra|back))*\s+"
    r"(?:пешк\w*|фигур\w*|кон[ьяе]\w*|слон\w*|ладь\w*|ферз\w*|качеств\w*|материал\w*|темп\w*|pawns?|pieces?|knights?|"
    r"bishops?|rooks?|queens?|exchange|material)(?![а-яa-z])", re.IGNORECASE)


def _fmt_eval(ev: float) -> str:
    if abs(ev) >= 99.5:
        return "a forced mate for " + ("White" if ev > 0 else "Black")
    return f"{ev:+.1f} for White"


# Who a verdict belongs to when the subject only hands it out: «движок даёт белым решающий перевес», «ты даёшь
# сопернику перевес», "the engine gives White a big edge" — the evaluator or the giver is the subject, the holder is the
# side in the dative (K7 02.11: fresh-fp d13#3, e09#1 were read as the engine's own side). A side in the dative between
# the subject and the verdict word is the holder; any other side there leaves the claim unjudged.
_HOLDER_DATIVE = {"белым", "черным", "тебе", "вам", "мне", "сопернику", "противнику", "им", "ему", "ей",
                  "white", "black", "you", "them", "him", "her", "me"}
_GAP_SIDE = re.compile(r"(?<![а-яa-z])(белые|белых|белым|черные|черных|черным|white|black|ты|тебя|тебе|вы|вас|вам|you|"
                       r"соперник\w*|противник\w*|opponent|engine|движок|движка|я|меня|мне|me|них|него|нее|они|им|ему|ей|"
                       r"them|they|him|her)(?![а-яa-z])", re.IGNORECASE)
# The engine (or "the evaluation") as the subject: it rates a position, it holds no side's verdict.
_EVALUATOR = re.compile(r"^(?:движок|engine)$|(?<![а-яa-z])(?:оценива\w*|оценил\w*|оценк\w*|счита\w*|показыва\w*|показал\w*|"
                        r"да[её]т|дают|видит|rates?|evaluates?|gives|shows|sees|says)(?![а-яa-z])", re.IGNORECASE)
_HOLDER_AFTER = re.compile(r"\s+(?:\w+\s+)?(?:для|в\s+пользу|for)\s+(?P<side>белых|ч[её]рных|тебя|вас|соперника|противника|"
                           r"white|black|you)(?![а-яa-z])", re.IGNORECASE)
# A move named before an engine's verdict: «a3 или ход королём проигрывают: движок даёт чёрным решающий перевес» — the
# verdict is that move's, on the board after it.
_MOVE_WORD = re.compile(r"(?<![а-яa-z])(?:ход\w*|move[sd]?)(?![а-яa-z])", re.IGNORECASE)


def _names_a_move(text: str, board: chess.Board) -> bool:
    if _MOVE_WORD.search(text):
        return True
    converted, _ = _to_san(text)
    for mm in _MOVE.finditer(converted):
        try:
            board.parse_san(mm["san"].rstrip("+#"))
            return True
        except ValueError:
            continue
    return False


def _verdict_holder(text: str, m, ctx: CheckContext) -> tuple:
    """(the colour the verdict of the _EVAL_CLAIMS[0] match *m* belongs to, whether an evaluator gave it) —
    (None, …) when the words do not say whose it is."""
    gap = text[m.end("side"): m.start("w")].replace("ё", "е")
    inner = list(_GAP_SIDE.finditer(gap))
    evaluator = bool(_EVALUATOR.search(m["side"].replace("ё", "е"))) or bool(_EVALUATOR.search(gap))
    if inner:
        last = inner[-1].group(1).lower()
        if last not in _HOLDER_DATIVE:
            return None, evaluator  # two sides before the verdict and none of them its holder in the dative
        return _side_color(last, ctx, text[: m.end("side") + inner[-1].start()]), True
    if evaluator:
        after = _HOLDER_AFTER.match(text, m.end("w"))
        return (_side_color(after["side"], ctx) if after else None), True
    return _side_color(m["side"], ctx, text[: m.start()]), False


def _eval_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.engine_eval is None or ctx.current is None:
        return []
    ev = ctx.engine_eval
    issues = []
    for rx in _EVAL_CLAIMS:
        for m in rx.finditer(text):
            if _is_hypothetical(text, original, m.start(), ctx=ctx):
                continue
            gd = m.groupdict()
            key = "eq" if gd.get("eq") else "w"
            if _NEGATION.search(text[max(0, m.start() - 20): m.start(key)]):
                continue  # «не лучше», "not winning"
            if gd.get("eq"):
                if abs(ev) >= 1.5:
                    issues.append(f"the engine evaluates the position at {_fmt_eval(ev)} — not equal")
                continue
            if "side" in gd and rx is _EVAL_CLAIMS[0]:
                color, evaluated = _verdict_holder(text, m, ctx)
                if evaluated and color is not None and _names_a_move(text[: m.start()], ctx.current):
                    continue  # the engine's verdict on the move the sentence names, not on the board now
            else:
                color = _side_color(m["side"], ctx, text[: m.start()])
            if color is None:
                continue
            e = ev if color == chess.WHITE else -ev
            name = "White" if color == chess.WHITE else "Black"
            w = gd["w"].lower().replace("ё", "е")
            if w.startswith(("выигр", "проигр", "won", "lost", "winning", "losing")) and \
                    _UNIT_OBJECT.match(text, m.end("w")):
                continue  # «Чёрные выиграли две пешки» (review miss2 01.11): a material gain or loss, not the evaluation
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


def _off_game_keys(ctx: CheckContext) -> set:
    """In a game on the board: the positions of the session's other games and lines (ctx.other_board_keys, and every
    position of a recorded line from the initial position after it leaves this game's moves) — never "the board now"
    of this game (review-miss 01.11: «Материал равный» in st3 was excused by the st2 game's final board)."""
    stamp = (len(getattr(ctx, "line_records", None) or ()), tuple(ctx.game_moves or ()),
             frozenset(getattr(ctx, "other_board_keys", None) or ()), ctx._key(ctx.current) if ctx.current is not None else "")
    cached = getattr(ctx, "_off_game_cache", None)
    if cached and cached[0] == stamp:
        return cached[1]
    off = _off_game_keys_now(ctx)
    try:
        ctx._off_game_cache = (stamp, off)
    except Exception:  # noqa: BLE001
        pass
    return off


def _off_game_keys_now(ctx: CheckContext) -> set:
    off = set(getattr(ctx, "other_board_keys", None) or ())
    moves = [str(m).rstrip("+#") for m in (ctx.game_moves or ())]
    board, path = chess.Board(), set()
    path.add(ctx._key(board))
    for san in moves:
        try:
            board.push_san(san)
        except ValueError:
            return off - {ctx._key(ctx.current)} if ctx.current is not None else off
        path.add(ctx._key(board))
    for start, rec in list(getattr(ctx, "line_records", None) or ()):
        if start.board_fen() != chess.STARTING_BOARD_FEN or start.turn != chess.WHITE:
            continue  # a line from a position: it may go on from this game
        sans = [str(x).rstrip("+#") for x in rec]
        k = min(len(sans), len(moves))
        if sans[:k] == moves[:k]:
            continue  # this game, a part of it, or a line that goes on from it
        b = start.copy(stack=False)
        for san in sans:
            try:
                b.push_san(san)
            except ValueError:
                break
            off.add(ctx._key(b))
    off -= path
    if ctx.current is not None:
        off.discard(ctx._key(ctx.current))
    return off


def _can_follow(now: chess.Board, board: chess.Board) -> bool:
    """*board* may come after *now* in play: no side has more pawns, and no more of a piece than *now* has plus the
    pawns it has promoted since — a position reached from another game's board (a move of the answer walked there)
    cannot."""
    for color in (chess.WHITE, chess.BLACK):
        promoted = len(now.pieces(chess.PAWN, color)) - len(board.pieces(chess.PAWN, color))
        if promoted < 0:
            return False
        extra = sum(max(0, len(board.pieces(pt, color)) - len(now.pieces(pt, color)))
                    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN))
        if extra > promoted:
            return False
    return True


def _now_boards(ctx: CheckContext) -> list:
    """The boards a claim about the material now may be about. In a game on the board, the game's earlier
    positions are its history (a move ago Black was one pawn up, now two — prod game 29.10): the board now, the
    positions given as such (a tool's board, the student's idea) and those the answer's own moves lead to — not the
    positions of the session's other games (_off_game_keys)."""
    boards = ctx.boards[1:] or ctx.boards
    if not ctx.game_moves or ctx.current is None:
        return boards
    off = _off_game_keys(ctx)
    boards = [b for b in boards if b is ctx.current or (ctx._key(b) not in off and _can_follow(ctx.current, b))]
    ply = ctx.current.ply()
    # …and a position the answer's moves reach from one of those (a move named in words — «ответили Nxe4» — is
    # followed where it first parses, a move before it in the game): earlier in the game than the board now.
    now = [b for b in boards if not _is_past(ctx, b) and (ctx.is_given(b) or b.ply() >= ply)]
    return now if any(b is ctx.current for b in now) else [ctx.current] + now


def _now_boards_v1029(ctx: CheckContext) -> list:
    """main's _now_boards (29.10, prod game st3#9), kept as it is for main's material reading (_material_issues_v1029):
    the board now, the positions given as such and those the answer's own moves lead to."""
    boards = ctx.boards[1:] or ctx.boards
    if not ctx.game_moves or ctx.current is None:
        return boards
    ply = ctx.current.ply()
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


# Every material pattern below needs one of these words: a sentence without any is not looked at further.
_MAT_ANY = re.compile(r"больше|меньше|впереди|позади|лишн|без|материал|перевес|преимуществ|отста|уступа|вед[уеё]|лучше|хуже|"
                      r"опережа|обгоня|сильнее|слабее|богаче|беднее|поровну|одинаков|паритет|сравня|баланс|разниц|"
                      r"выигрыва|проигрыва|плюс|минус|равн|равен|up|down|ahead|behind|extra|spare|material|equal|even|level|"
                      r"balanced", re.IGNORECASE)


def _material_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    """The material claims of the sentence against the board. material_order's switch wraps the new reading only
    (verify1102 B3): 'off' is main's reading of 29.10 exactly (_material_issues_v1029, its game-board fix of 29.10
    included), 'shadow' shows main's issues and records what the new reading says otherwise, 'on' is the new reading
    (_material_issues_new). A new reading that raises falls back to main's (fail-open to main, not to nothing)."""
    mode = _switch_mode("material_order", ctx)
    if mode == "off":
        return _material_issues_v1029(text, original, ctx)
    try:
        new = _material_issues_new(text, original, ctx)
    except Exception:  # noqa: BLE001
        logger.debug("material reading failed", exc_info=True)
        return _material_issues_v1029(text, original, ctx)
    if mode == "on":
        return new
    base = _material_issues_v1029(text, original, ctx)
    if new != base:
        record_shadow(ctx, "material_order", [i for i in new if i not in base]
                      or [f"main's issue not raised by the new reading: {i}" for i in base if i not in new])
    return base


def _material_issues_v1029(text: str, original: str, ctx: CheckContext) -> list[str]:
    """main's material reading (02bb40d0), kept verbatim: what material_order 'off' (and the lesson tutor) gets."""
    if ctx.current is None:
        return []
    issues = []
    told = _told_capture(text, ctx)
    if told:
        boards, where, shown = told[1], told[1][0], f"after {told[0]} (the capture this sentence tells as made): "
    else:
        boards, where, shown = ctx.boards[1:] or ctx.boards, ctx.current, ""
        if ctx.game_moves and not _PAST_BE.search(text):
            boards = _now_boards_v1029(ctx)  # a game: the material now, not a move ago (prod 29.10)
    for rx in _MATERIAL:
        for m in rx.finditer(text):
            if _is_hypothetical(text, original, m.start()):
                continue
            if _FUTURE_FILL.search(text[m.start("side"): m.start("dir")]):
                continue  # «ты останешься без фигуры»: what will be, not what is (replay, 2026-10-05)
            color = _side_color(m["side"], ctx, text[: m.start()])
            if color is None:
                continue
            kind, points = _unit(m["unit"])  # _UNIT here never reads «пешек»: main's _unit and this one agree
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


def _material_issues_new(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None or not _MAT_ANY.search(text):
        return []
    from src.material_frames import mask_idioms

    text = mask_idioms(text)  # «всё равно», «плюс ко всему», «лишний раз»: no material words (verify1102 B1)
    issues = []
    record = None
    told = _told_capture(text, ctx)
    if told:
        boards, where, shown = told[1], told[1][0], f"after {told[0]} (the capture this sentence tells as made): "
    else:
        boards, where, shown = ctx.boards[1:] or ctx.boards, ctx.current, ""
        if ctx.game_moves and not _PAST_BE.search(text) and not _OTHER_GAME.search(original):
            # a game: the material now, not a move ago (prod 29.10), nor another game's — fail-open to every board
            # (review-wiring2 01.11)
            boards = _fail_open(_now_boards, ctx) or boards
        elif ctx.game_moves and _PAST_BE.search(text):
            # «После 3...Nf6 у белых уже был лишний конь» (review-miss2 01.11): the past at a move of the game's record —
            # the board right after it, rebuilt from the record; another past is left as before
            past = _fail_open(_past_ply_board, original, ctx)
            if past:
                boards, where, shown = [past[0]], past[0], f"right after {past[1]} (the moment this sentence names): "
                record = {str(x).rstrip("+#") for x in ctx.game_moves}  # the record's moves are no line to imagine
                blank = lambda m_: " " * len(m_.group(0))  # noqa: E731 — the anchor is no condition («после» it names)
                text, original = _PAST_ANCHOR.sub(blank, text), _PAST_ANCHOR.sub(blank, original)

    def said(span: str) -> str:
        return f"material {shown}{_imbalance(where)}" if shown else f"material: {_imbalance(where)}"

    def in_points(issue: str) -> str:
        try:
            from src.game_record import material as _material_of

            diff = _material_of(where)["diff"]
        except Exception:  # noqa: BLE001 — the points are a bonus on the issue (fail-open, F8)
            diff = 0
        return issue.replace(" (not: ", f" — {'White' if diff > 0 else 'Black'} +{abs(diff)} in points (not: ", 1) \
            if diff else issue

    counts_points = bool(_MAT_POINTS.search(text))
    judged = set()  # the side words the fixed patterns judged: the grammar adds only what they miss or read looser
    ordered = []
    for rx in _MATERIAL:
        for m in rx.finditer(text):
            judged.add(m.start("side"))
            if _is_hypothetical(text, original, m.start(), played=record, ctx=ctx):
                continue
            if _FUTURE_FILL.search(text[m.start("side"): m.start("dir")]):
                continue  # «ты останешься без фигуры»: what will be, not what is (replay, 2026-10-05)
            if _MAT_NOT_TOTAL.search(_mat_clause(text, m.start(), m.end())):
                continue  # «на ферзевом фланге у белых на пешку больше»: a majority, not the balance
            if _mat_cond_after(text, m.end()):
                continue
            color = _side_color(m["side"], ctx, text[: m.start()])
            if color is None:
                continue
            kind, points = _unit(m["unit"])
            n = _num(m.groupdict().get("n"))
            direction = m["dir"].lower().replace("ё", "е")
            more = any(direction.startswith(w) for w in _MORE)
            balance = not direction.startswith(("лишн", "без", "extra", "spare"))
            if not any(_material_holds(b, color, kind, points, n, more, balance, counts_points) for b in boards):
                issues.append(f"{said(m.group(0))} (not: {m.group(0).strip()})")
    # the grammar (M2 material_order, rebuilt 01.11): every lead it reads that the patterns above did not judge, or
    # judged looser (an explicit count, «всего», «больше ничего»)
    try:
        claims = _material_claims(text, ctx)
    except Exception:  # noqa: BLE001 — fail-open: a broken reading never blocks an answer
        logger.debug("material grammar failed", exc_info=True)
        claims = []
    for at, color, units, more, mode, span, frame, end in claims:
        if at in judged and not (frame in ("extra", "extra_after") and mode in ("count", "balance")):
            continue  # the patterns above read this very claim (only a stricter count of an extra unit is added)
        if _is_hypothetical(text, original, at, played=record, ctx=ctx) or _mat_cond_after(text, end):
            continue
        try:
            holds = any(_lead_holds(b, color, units, more, mode, counts_points) for b in boards)
        except Exception:  # noqa: BLE001 — fail-open (review-wiring2 01.11)
            logger.debug("material lead failed", exc_info=True)
            holds = True
        if not holds:
            ordered.append(in_points(f"{said(span)} (not: {span})"))
    eq_old = {m.start() for m in _MATERIAL_EQUAL.finditer(text)}
    eq_new = []
    for m in _MATERIAL_EQUAL_ANY.finditer(text):
        if _is_hypothetical(text, original, m.start(), played=record, ctx=ctx):
            continue
        if "?" in text[m.end():] or _NEGATION.search(text[: m.start()]) \
                or re.match(r"\s*(?:нет|не\s|отсутству)", text[m.end():]) or _mat_cond_after(text, m.end()):
            continue  # «материал не равен», «материального равенства нет», «материал равный после размена»
        hedged = bool(m["h1"] or m["h2"] or m["h3"])
        if not any(abs(_counts(b, chess.WHITE)["nonpawn"] + _counts(b, chess.WHITE)[chess.PAWN]
                       - _counts(b, chess.BLACK)["nonpawn"] - _counts(b, chess.BLACK)[chess.PAWN]) <= (2 if hedged else 0)
                   for b in boards):
            issue = f"{said(m.group(0))} (not {'about ' if hedged else ''}equal)"
            (issues if m.start() in eq_old and not hedged else eq_new).append(issue)
    for m in _MATERIAL_EQUAL.finditer(text):  # the fixed forms the wider one does not read («лишней пешки ни у кого нет»)
        if any(x.start() <= m.start() < x.end() for x in _MATERIAL_EQUAL_ANY.finditer(text)):
            continue
        if _is_hypothetical(text, original, m.start(), played=record, ctx=ctx) or _NEGATION.search(text[: m.start()]) \
                or _mat_cond_after(text, m.end()):
            continue
        if not any(_counts(b, chess.WHITE)["nonpawn"] + _counts(b, chess.WHITE)[chess.PAWN]
                   == _counts(b, chess.BLACK)["nonpawn"] + _counts(b, chess.BLACK)[chess.PAWN] for b in boards):
            issues.append(f"{said(m.group(0))} (not equal)")
    # every other material claim of the sentence, read by its parts (src/material_frames, review-miss2 01.11)
    read_spans = [(m.start(), m.end()) for rx in _MATERIAL for m in rx.finditer(text)] + \
        [(m.start(), m.end()) for m in _MATERIAL_EQUAL_ANY.finditer(text)] + \
        [(m.start(), m.end()) for m in _MATERIAL_EQUAL.finditer(text)] + \
        [(at, at + len(span)) for at, _c, _u, _mo, _md, span, _f, _e in claims]
    eq_new += _fail_open(_material_frame_issues, text, original, ctx, boards, read_spans, said, record)
    return issues + ordered + eq_new


_PAST_ANCHOR = re.compile(r"(?<![а-яa-z])(?:после|after)\s+(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?"
                          r"(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?"
                          r"|O-O(?:-O)?)", re.IGNORECASE)


def _past_ply_board(original: str, ctx: CheckContext):
    """[(the board right after the numbered move «после N.X» of the game's record, its label)] — the past the sentence
    anchors there; [] when it names none or the move is not the record's at that number."""
    conv, _ = _to_san(original)
    found = list(_PAST_ANCHOR.finditer(conv))
    if len(found) != 1:
        return []
    m = found[0]
    ply = 2 * int(m["num"]) - (0 if m["dots"] in ("...", "…") else 1)
    moves = [str(x).rstrip("+#") for x in ctx.game_moves]
    if not (1 <= ply <= len(moves)) or moves[ply - 1] != m["san"].rstrip("+#"):
        return []
    # the line the anchor opens runs on («после 1.e4 e5 2.Nf3 …», «после 3.d4 cxd4»): its last move, each the record's
    label = f"{m['num']}{m['dots']}{m['san']}"
    pos = m.end()
    while True:
        nxt = re.match(r"[\s,]*(?:(?P<n>\d{1,3})\s?(?P<d>\.\.\.|…|\.)\s?)?(?P<s>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?"
                       r"|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?(?![\w])", conv[pos:])
        if not nxt or ply >= len(moves) or moves[ply] != nxt["s"].rstrip("+#"):
            if nxt and (ply >= len(moves) or moves[ply] != nxt["s"].rstrip("+#")):
                return []  # the line leaves the record: another line, not the game's past
            break
        ply += 1
        label = (f"{(ply - 1) // 2 + 1}{'.' if ply % 2 else '...'}") + nxt["s"]
        pos += nxt.end()
    m = {"num": None}
    board = chess.Board()
    try:
        for san in moves[:ply]:
            board.push_san(san)
    except ValueError:
        return []
    return [board, label]


def _material_frame_issues(text: str, original: str, ctx: CheckContext, boards: list, read_spans: list, said,
                           record=None) -> list:
    from src.capture_frames import resolve
    from src.game_record import material as _material_of
    from src.material_frames import read

    out = []
    last = (str(ctx.game_moves[-1]).rstrip("+#") if getattr(ctx, "game_moves", None) else None)
    diffs = None  # the balance of every board, computed once and only for a claim to judge
    for c in read(text):
        if any(a < c.end and c.at < b for a, b in read_spans):
            continue  # a pattern above read this clause
        anchored = len(boards) == 1 and boards[0] is not ctx.current and bool(_PAST_ANCHOR.search(_to_san(original)[0]))
        # a condition or a line before the claim itself, not only before its clause («после других ходов у чёрных …»)
        if _is_hypothetical(text, original, min(max(c.at, c.pos), max(0, len(text) - 1)), played=record, ctx=ctx) or \
                (_PAST_BE.search(text[c.at:c.end]) and not anchored):
            continue
        sans = [m["san"].rstrip("+#") for m in _MOVE.finditer(_to_san(text[c.at:c.end])[0])]
        if sans and (last is None or sans[-1] != last) and not anchored:
            continue  # «после 3.Nf3 материал …»: an earlier moment of the game or a line — another board
        if diffs is None:
            diffs = []
            for b in boards:
                try:
                    diffs.append(_material_of(b)["diff"])
                except Exception:  # noqa: BLE001
                    return []
        if not diffs:
            continue
        if c.kind == "equal":
            if c.unit:
                key = {"пешек": chess.PAWN, "коней": chess.KNIGHT, "слонов": chess.BISHOP, "ладей": chess.ROOK,
                       "ферзей": chess.QUEEN}.get(c.unit)
                if key is None:
                    holds = any(_counts(b, chess.WHITE)["nonpawn"] == _counts(b, chess.BLACK)["nonpawn"] for b in boards)
                else:
                    holds = any(_counts(b, chess.WHITE)[key] == _counts(b, chess.BLACK)[key] for b in boards)
            else:
                holds = any(abs(d) <= (2 if c.hedged else 0) for d in diffs)
            if not holds:
                out.append(f"{said(c.span)} (not {'about ' if c.hedged else ''}equal: {c.span})")
            continue
        if c.kind == "diff":
            if not any(abs(abs(d) - c.points) <= 1 for d in diffs):
                out.append(f"{said(c.span)} (not a difference of {c.points} points: {c.span})")
            continue
        color = resolve(c.who, ctx)
        if color is None:
            continue
        sign = (1 if color == chess.WHITE else -1) * (1 if c.more else -1)
        if c.points is None:
            holds = any(d * sign > 0 for d in diffs)
        else:
            tol = 0 if c.points <= 2 else 1  # pawns are counted exactly; a piece's worth within a pawn
            if c.atleast:  # «лишние слон, конь и пешка»: those extras at least — more may be left unnamed
                holds = any(d * sign >= c.points - tol for d in diffs)
            else:
                holds = any(abs(d * sign - c.points) <= tol for d in diffs)
        if not holds:
            out.append(f"{said(c.span)} (not: {c.span})")
    return out


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
        if _is_hypothetical(text, original, m.start(), whole=True, ctx=ctx):
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
        if _is_hypothetical(text, original, m.start(), whole=True, ctx=ctx):
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


def _could_go_there(ctx: CheckContext, ptype: int, sq: int) -> bool:
    """A piece of *ptype* of either side can move to *sq* on a given board of the turn (pseudo-legal, either side to
    move)."""
    for b in ctx.boards:
        if not ctx.is_given(b):
            continue
        for color in (chess.WHITE, chess.BLACK):
            trial = b.copy(stack=False)
            trial.turn = color
            trial.ep_square = None
            if any(mv.to_square == sq and trial.piece_type_at(mv.from_square) == ptype for mv in trial.pseudo_legal_moves):
                return True
    return False


def _instrument_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
    for m in _INSTRUMENT.finditer(text):
        if _is_hypothetical(text, original, m.start(), whole=True, ctx=ctx):
            continue
        word = m["piece"].lower().replace("ё", "е").split()[-1]
        ptype = _INSTRUMENT_TYPE.get(word[:3])
        if ptype is None:
            continue
        sq = chess.parse_square(m["a"])
        if any((pc := b.piece_at(sq)) is not None and pc.piece_type == ptype for b in ctx.boards):
            continue
        acting = bool(re.search(r"(?:ом|ем|ой|ей)$", word)) or m["piece"].lower().startswith("with")  # not «убрать коня с d3»
        if acting and not _lesson(ctx) and _could_go_there(ctx, ptype, sq):
            # fix1102 K5: «Чёрные могут дать шах ферзём с a5» — «ферзём с a5» also means the queen acting from a5, the
            # square it goes to (Qa5+): when a piece of that kind can move there, the words have two readings, and
            # neither is judged (fresh-miss true control chkT2, cut on both trees)
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


# (fix1102 K5: «Конь d4 под ударом коня c6, но его защищают ферзь d2 и слон e3» — «под ударом/атакой/прицелом» is
# the passive too: the clause is about its first square, the piece attacked, not the attacker named last.)
_PASSIVE_V1031 = re.compile(r"атакован\w*|защищ[её]н\w*|прикрыт\w*|бь[её]тся|под\s+боем|attacked|defended|protected|"
                            r"covered|guarded|\bhit\b|by\s+the|висит|hanging", re.IGNORECASE)  # the /learn tutor's
_PASSIVE = re.compile(r"атакован\w*|защищ[её]н\w*|прикрыт\w*|бь[её]тся|под\s+(?:боем|ударом|атакой|угрозой|прицелом|"
                      r"обстрелом|давлением)|attacked|defended|protected|covered|guarded|under\s+(?:attack|fire)|"
                      r"\bhit\b|by\s+the|висит|hanging", re.IGNORECASE)


def _pronoun_square(text: str, upto: int, ctx: CheckContext) -> Optional[str]:
    """What "it" / «её» at *upto* stands for.

    The clause the pronoun is in is skipped («но её защищает конь c3»: c3 is
    the subject of that clause). In the clause before it, a passive one («пешка
    f7 атакована слоном c4», "it's attacked by the b6 pawn") is about its first
    square, an active one («конь f6 напал на пешку e4») about its last; a clause
    that opens with a pronoun, or no clause with a square at all, means the
    previous sentence's square."""
    passive = _PASSIVE_V1031 if _lesson(ctx) else _PASSIVE
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
        return squares[0] if passive.search(clause) else squares[-1]
    if _OPENS_WITH_PRONOUN.match(text) and ctx.topic:
        return ctx.topic
    squares = _SQ_RE.findall(clauses[-1]) if clauses else []
    if squares and not passive.search(clauses[-1]):
        return squares[0]  # "the pawn on a4 is hanging and nothing defends it"
    if squares:
        return squares[0]
    return ctx.topic


def _object_first_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    issues = []
    for m in _OBJECT_FIRST.finditer(text):
        if _NEGATION.search(text[: m.start("verb")]):
            continue
        if _is_hypothetical(text, original, m.start(), ctx=ctx):
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
        held = bool(re.match(r"держ|hold", m["verb"], re.IGNORECASE)) and ctx.current is not None and not _lesson(ctx)
        for sm in _SUBJECT.finditer(m["subjects"]):
            word = (sm["piece"] or sm["piece2"]).lower()
            ptype = _piece_type(word) or _INSTRUMENT_TYPE.get(word[:3])
            if ptype is None:
                continue
            a = chess.parse_square(sm["a"] or sm["a2"])
            if a == target:
                continue
            if held:
                from src.board_rules import pawn_held_back

                if pawn_held_back(ctx.current, a, target):
                    continue  # «её (пешку d4) держит пешка e6»: the pawn held back — d5 is under e6 (review-fp 03.11)
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
        if _lesson(ctx):
            boards = ctx.boards  # the lesson tutor's reading as it was (Асан 19.10)
        else:
            # Not the starting position the context keeps for unknown ones: «Поле b8 под ударом слона» with b8 empty
            # now was judged where the b8 knight stands in the initial setup (review-fp 03.11: S1, S2, E2, K1).
            boards = [b for b in ctx.boards if b is ctx.current or b.board_fen() != chess.STARTING_BOARD_FEN]
        standing = [b for b in boards if b.piece_at(sq) is not None]
        hypothetical = _is_hypothetical(text, original, m.start(), ctx=ctx)
        if hypothetical:
            # «после Rg1 ферзь h4 под ударом ладьи»: judged on the positions the
            # sentence's moves lead to, never on the board as it is now
            standing = [b for b in standing if not ctx.is_given(b)]
        if any(any(b.piece_type_at(a) == ptype for a in b.attackers(not b.piece_at(sq).color, sq)) for b in standing):
            continue
        if not _lesson(ctx) and not hypothetical and ctx.current.piece_at(sq) is None:
            # an empty square now: under attack when a piece of that kind (of either side) hits it on the board
            if any(ctx.current.piece_type_at(a) == ptype
                   for a in ctx.current.attackers(chess.WHITE, sq) | ctx.current.attackers(chess.BLACK, sq)):
                continue
            if not m["obj3"]:
                continue  # «пешка e4 под ударом коня» with e4 empty: a piece not there (the ghost check's), not this claim
        elif not standing:
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
        if _is_hypothetical(text, original, m.start(), ctx=ctx):
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
        if _is_hypothetical(text, original, m.start(), ctx=ctx):
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
        if _NEGATION.search(text[: m.start("verb")]) or _is_hypothetical(text, original, m.start(), ctx=ctx):
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
            + (_ghost_issues(text, ctx) if not _is_hypothetical(text, original, 0, whole=True, ctx=ctx) else [])
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
# A name is not language either (K7 02.11, live theory move-french-adv: «А 3...Bd7 — это линия «French Defense: Advance
# Variation, Extended Bishop Swap»» was cut as English and left a headless rest): a quoted title with no Cyrillic in it,
# and a run of two or more capitalised Latin words («French Defense: Advance Variation», «Morphy's Opera Game») — a
# book name, a player, a place. English prose keeps its lower-case words and function words, so it is still told.
_NAME_RUN = re.compile(
    r"«[^«»а-яёА-ЯЁ]*»|“[^“”а-яёА-ЯЁ]*”|\"[^\"а-яёА-ЯЁ]*\""
    r"|(?<![A-Za-z'’])[A-Z][A-Za-zÀ-ÿ'’-]*(?:(?:\s*[:,]\s*|\s+(?:(?:of|the|de|da|di|del|von|van|and|in|for|vs\.?)\s+)?)"
    r"[A-Z][A-Za-zÀ-ÿ'’-]*)+(?![A-Za-z])")
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
    if language != "en":
        stripped = _NAME_RUN.sub(" ", stripped)
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
    if language != "en":
        text = _NAME_RUN.sub(" ", text)
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
    r"бери(?:те)?|возьми(?:те)?|забирай(?:те)?|сыграем|играем|берём|берем|ставим|идём|идем|выбирай(?:те)?|выбери(?:те)?|"
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
# main's proposal words (02bb40d0), for structure_read 'off' and the lesson tutor (verify1102 B3)
_PROPOSES_V1029 = re.compile(
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

# Plan 31.10 C1a (propose_vocab): a closed list of imperatives that hand the student moves — «Пока же просто
# развивайся: Qe2, Be3» (prod castle-00 29.10: Qe2 hangs the queen to the c4 bishop) — only when «:» or «—» and a
# move follow at once. No general imperative: that was measured at 3 wrong engine flags in 17.
_PROPOSE_VOCAB = re.compile(
    r"(?<![а-яa-z])(?:развивайся|развивайтесь|развейся|развейтесь|выводи(?:те)?(?:\s+фигуры)?|продолжай(?:те)?(?:\s+развитие)?|"
    r"заканчивай(?:те)?\s+развитие|готовь(?:те)?)(?:\s+(?:дальше|спокойно|сначала|просто))?\s*[:—–-]\s*"
    r"(?=[*_]*(?:\d{1,3}\s?\.{1,3}\s?)?(?:[KQRBNКФЛС][a-h]?[1-8]?[x:]?[a-h][1-8]|[a-h][1-8]|[a-h]x[a-h][1-8]|O-O|0-0))",
    re.IGNORECASE)
# Plan 31.10 C1b (plan_place) and C1a (propose_vocab), rebuilt 01.11 (F5) as one reader of structure, not of the graded
# wording. A FRAME opens a scope: a plan noun («План за чёрных прост:», «Идея —», «Главная задача:», "The plan is"), an
# evaluative or modal predicate («логично», «полезно», «неплохо», «хорошо бы сыграть»), a «next move» noun («Твой
# следующий ход —», «Лучший ответ —»), a development imperative with a connector («Готовь длинную рокировку: Qe2, Be3»,
# «Продолжай развитие ходом Qe2»), the side to move told in the present («Чёрные готовят Nf6 и Bg4», «Чёрные ставят
# коня на f6»), a piece of it told to go to a square («Конь g8 идёт на f6»), and «Сначала …». The scope's ITEMS come in
# order: a written move, «конь на f6» / «коня на f6» / «ход конём на f6», «конь f6» right after «:» or «—», a bare
# pawn move in a list position. The first item is the move proposed now, judged by the engine (src/hypothetical.
# verify_recommendation) — unless the words defer it: a later-word before it («со временем», «потом»), a precondition
# right after it («…, но только после того, как …», «… — но сначала f4»); then the move «сначала» names is the move now.
# Not judged: a question, a sentence that says the move fails, the past («план был»), a condition («если», «когда»), a
# line written before the frame, the other side's plan, the game's own next move told in the present.
_F_PLAN = re.compile(
    r"(?<![а-яa-z])(?P<adj>(?:(?:мой|наш|твой|ваш|главн\w+|основн\w+|типичн\w+|стандартн\w+|обычн\w+|естественн\w+|логичн\w+|"
    r"прост\w+|хорош\w+|правильн\w+|сильн\w+|лучш\w+|ближайш\w+|перв\w+|разумн\w+|долгосрочн\w+|стратегическ\w+)\s+){0,2})"
    r"(?P<noun>план|идея|задача|замысел|цель)"
    r"(?:\s+(?:за|у|для)\s+(?P<side>бел\w+|черн\w+|тебя|вас))?(?:\s+(?P<gside>белых|черных))?"
    r"(?P<gap>(?:\s+(?!(?:кон[ьяе]|слон|ладь|ферз|пешк|корол)\w*(?![а-я]))[а-я]+){0,2})\s*(?:[:—–]|-\s|,?\s+это\s)"
    r"|(?<![a-z])(?:(?:the|my|our|your|a|typical|main|usual)\s+){0,2}(?P<enoun>plan|idea)(?:\s+for\s+(?P<eside>white|black))?"
    r"(?:\s+here)?\s*(?:is\s+|:|—|–)", re.IGNORECASE)
_F_EVAL = re.compile(
    r"(?<![а-яa-z])(?P<side>(?:белым|черным|тебе|вам)\s+)?(?:(?:здесь|тут|сейчас|теперь|дальше|далее|затем)\s+)?"
    r"(?P<pred>логич\w*|естествен\w*|полез\w*|неплох\w*|хорошо|разум\w*|умест\w*|целесообраз\w*|желател\w*|рациональн\w*|"
    r"имеет\s+смысл|напрашива\w+|самое\s+время|пора|следует|рекомендуется)(?![а-яa-z])", re.IGNORECASE)
_F_NEXT = re.compile(
    r"(?<![а-яa-z])(?:(?:тво\w+|наш\w+|мой|ваш\w+)\s+)?(?:следующ\w+|лучш\w+|сильнейш\w+|естественн\w+|логичн\w+|"
    r"правильн\w+|верн\w+|точн\w+|разумн\w+|хорош\w+|отличн\w+|сильн\w+|полезн\w+)\s+(?:ход|вариант|выбор|ответ|продолжение|шаг)"
    r"(?:\s+(?:здесь|тут|сейчас|теперь|в\s+этой\s+позиции|за\s+\w+|для\s+\w+|белых|ч[её]рных|соперника|противника))*"
    r"\s*(?:[:—–]|-\s|,?\s+это\s)"
    # «Лучшее место для коня g8 — поле f6»: the best square of a piece (review-miss2 01.11)
    r"|(?<![а-яa-z])(?:лучш\w+|естественн\w+|идеальн\w+|правильн\w+)\s+(?:место|поле)\s+для\s+\w+(?:\s+[a-h][1-8])?\s*[:—–]\s*"
    r"(?:(?:поле|клетка)\s+)?(?=[a-h][1-8])"
    r"|(?<![a-z])(?:your\s+|the\s+)?(?:next|best|natural|logical)\s+(?:move|reply|continuation)(?:\s+here)?\s*(?:is\s+|:|—|–)",
    re.IGNORECASE)
_F_IMPER = re.compile(
    r"(?<![а-яa-z])(?:развивай(?:те)?(?:сь|ся)?|разве(?:й|йте)(?:сь|ся)|продолжа(?:й|йте)|заканчива(?:й|йте)|заверша(?:й|йте)|заверши(?:те)?|"
    r"законч(?:и|ите)|готов(?:ь|ьте)|подготов(?:ь|ьте)|вывод(?:и|ите)|вывед(?:и|ите)|усил(?:ь|ьте|ивай)|укреп(?:и|ите|ляй)|"
    r"займ(?:и|ите)|занима(?:й|йте)|develop|continue|finish|prepare)(?![а-яa-z])"
    r"(?P<obj>(?:\s+(?!(?:ход\w*|через|например|with|by)(?![а-яa-z]))[а-яa-z0-9-]+){0,3}?)"
    r"\s*(?:[:—–]|-\s|\s(?:ходом|ходами|через|например|with|by|e\.g\.)(?![а-яa-z]))", re.IGNORECASE)
_F_THIRD = re.compile(
    r"(?<![а-яa-z])(?P<side>белые|черные)\s+(?:(?:здесь|тут|сейчас|теперь|обычно|часто|как\s+правило|в\s+этой\s+позиции|"
    r"в\s+этом\s+варианте|спокойно|просто|сразу|дальше|уже|первым\s+делом|прежде\s+всего|сначала|сперва|в\s+первую\s+очередь)\s+)*(?:(?:хотят|собираются|планируют|стремятся|могут|должны|"
    r"готовы)\s+)?(?P<verb>ставят|поставят|развивают|разовьют|выводят|выведут|готовят|подготовят|играют|сыграют|переводят|"
    r"переведут|двигают|продвигают|сыграть|поставить|вывести|развить|перевести|играть|продвинуть)(?![а-я])"
    r"|(?<![a-z])(?P<eside>white|black)\s+(?:usually\s+|often\s+|here\s+|now\s+)*(?:wants\s+to\s+|will\s+|plans\s+to\s+)?"
    r"(?P<everb>plays?|puts?|develops?|prepares?|brings?)(?![a-z])", re.IGNORECASE)
_F_GOES = re.compile(
    r"(?<![а-яa-z])(?:(?P<pside>бел\w+|черн\w+|тво\w+)\s+)?(?P<piece>конь|слон|ладья|ферзь|пешка)(?:\s+(?P<from>[a-h][1-8]))?"
    r"(?:\s+(?:с|из)\s+(?P<from2>[a-h][1-8]))?\s+(?:(?:обычно|здесь|тут|сейчас|дальше|сразу|часто|как\s+правило|теперь)\s+)*"
    r"(?:ид[её]т|пойд[её]т|вста[её]т|встанет|прыгает|прыгнет|переходит|перейд[её]т|отправляется|отправится|направляется|"
    r"направится|перебирается|переберется|выходит|выйдет|становится|станет|"
    r"(?:должен|должна|может|хочет|собирается|стремится|готов|готова)\s+(?:идти|пойти|встать|прыгнуть|перейти|отправиться|выйти|"
    r"перебраться|переходить))\s+(?:на|в)\s+(?P<sq>[a-h][1-8])(?![0-9])",
    re.IGNORECASE)
# «Ферзь на e2 — лучший вариант», «Конь на f6 — естественный ход»: the placement first, the praise after it.
_F_PRAISED_PLACE = re.compile(
    r"(?<![а-яa-z])(?:ход\s+)?(?P<piece>конь|слон|ладья|ферзь|пешка|кон[её]м|слоном|ладь[её]й|ферз[её]м|пешкой)(?:\s+(?P<from>[a-h][1-8]))?"
    r"(?:\s+(?:с|из)\s+(?P<from2>[a-h][1-8]))?\s+(?:(?:на|в)\s+)?(?P<sq>[a-h][1-8])(?![0-9])\s*(?:[—–:-]|,)?\s*"
    r"(?:это\s+|здесь\s+|тут\s+|сейчас\s+|как\s+раз\s+)*(?:(?:тво|ваш|наш)\w*\s+)?(?:сам\w+\s+)?(?:лучш|логич|естествен|полез|сильн|точн|"
    r"правильн|верн|хорош|отличн|разумн)\w*\s+(?:вариант|ход|выбор|решение|продолжение|идея|план)(?![а-яa-z])", re.IGNORECASE)
# «Ход Qe2 здесь логичен», «Nf6 — естественное развитие»: a written move, then an evaluation _PRAISED does not read.
_F_PRAISED_SAN = re.compile(
    r"(?<![A-Za-z0-9])(?:ход\s+)?(?:\.{2,3}|…)?(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|O-O(?:-O)?)[+#]?[*_]*\s*(?:[—–:-]|,)?\s*"
    r"(?:это\s+|здесь\s+|тут\s+|сейчас\s+|как\s+раз\s+|вполне\s+)*(?:сам\w+\s+)?(?:логич|естествен|полез|разум|умест|"
    r"целесообраз|рациональн)\w*(?![а-яa-z])", re.IGNORECASE)
_F_FIRST = re.compile(r"(?:^|[.!?:;—–]\s*|,\s*)[\s*_>#«\"-]*(?:сначала|сперва|для\s+начала|прежде\s+всего|first(?:\s+of\s+all)?|"
                      r"to\s+start(?:\s+with)?)(?![а-яa-z])\s*,?", re.IGNORECASE)
# From the frame to its first item: adverbs, a side, an infinitive of playing, «ход», «бы», a colon.
_F_LINK = re.compile(
    r"\s*(?:бы\s+)?(?:(?:для|за|у)\s+(?:бел\w+|черн\w+)\s+)?(?:(?:здесь|сейчас|тут|теперь|дальше|далее|сразу|просто|"
    r"спокойно|всего|всех|now|here|simply)\s+)*(?:(?:сыграть|играть|поставить|вывести|перевести|развить|продолжить(?:\s+\w+)?|"
    r"начать|сделать\s+ход|ход(?:ом)?|play(?:ing)?|to\s+play|go\s+for)\s+)?(?:[—–:]\s*)?$", re.IGNORECASE)
_ITEM_PLACE = re.compile(
    r"(?<![а-яa-z])(?:ход(?:ом)?\s+)?(?P<piece>кон(?:ь|я|ем)|слон(?:а|ом)?|ладь(?:я|ю|ей)|ферз(?:ь|я|ем)|пешк(?:а|у|ой))"
    r"(?:\s+(?P<from>[a-h][1-8]))?(?:\s+(?:с|из)\s+(?P<from2>[a-h][1-8]))?\s+(?:на|в)\s+(?P<sq>[a-h][1-8])(?![0-9])"
    r"|(?<![a-z])(?P<epiece>knight|bishop|rook|queen|pawn)\s+(?:to|on|onto)\s+(?P<esq>[a-h][1-8])(?![0-9])", re.IGNORECASE)
_ITEM_BARE = re.compile(r"\s*(?P<piece>конь|слон|ладья|ферзь|пешка)\s+(?P<sq>[a-h][1-8])(?![0-9])", re.IGNORECASE)
_PLACE_TYPE_ANY = {"кон": chess.KNIGHT, "слон": chess.BISHOP, "ладь": chess.ROOK, "ферз": chess.QUEEN, "пешк": chess.PAWN,
                   "knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK, "queen": chess.QUEEN, "pawn": chess.PAWN}
# What a bare pawn move («c5») may follow to be an item of a list, not a square («давит на e4»).
_BARE_PAWN_BEFORE = re.compile(r"(?:^|[:—–,(]|(?<![а-яa-z])(?:и|или|затем|потом|далее|дальше|сначала|сперва|ходом|ходами|сыграть|"
                               r"играть|играют|сыграют|продвинуть|толкнуть|через|then|and|or|first|with|play))\s*$",
                               re.IGNORECASE)
# Where a plan's list ends: a contrast or a condition starts another thought.
_SCOPE_END = re.compile(r"(?<!\d)(?<!\.)\.(?!\.)(?!\s?(?:[KQRBNO]|[a-h][1-8x]))|[;!?\n]|(?<![а-яa-z])(?:но|однако|а\s+не|вместо|иначе|"
                        r"если|чтобы|пока\s+не|but|however|instead|unless|otherwise|if)(?![а-яa-z])", re.IGNORECASE)
_LATER_WORD = re.compile(r"(?<![а-яa-z])(?:потом|затем|позже|позднее|со\s+временем|впоследствии|в\s+будущем|в\s+перспективе|"
                         r"рано\s+или\s+поздно|когда-нибудь|в\s+дальнейшем|в\s+конце\s+концов|долгосрочн\w*|стратегическ\w*|"
                         r"later|eventually|afterwards|in\s+the\s+long\s+run|at\s+some\s+point|long-term|then)(?![а-яa-z])",
                         re.IGNORECASE)
# A precondition right after the item (only connectors between): «конь на d5, но только после того, как e6 уйдёт»,
# «конь на d5 — но сначала f4», "Nd5, but only once e6 has gone".
_PRECOND_AFTER = re.compile(
    r"^[\s,—–-]*(?:(?:но|а|однако|и\s+то|but|however|yet)\s+)?(?:(?:только|лишь|не\s+раньше|only|not\s+until|не\s+сейчас)\s*,?\s*)?"
    r"(?:(?:надо|нужно|следует|стоит)\s+)?"
    r"(?:после\s+того,?\s+как|после(?!\s+(?:чего|этого))|когда|как\s+только|пока\s+не|сначала|сперва|прежде|для\s+начала|"
    r"с\s+подготовк\w*|после\s+подготовк\w*|в\s+будущем|со\s+временем|в\s+перспективе|"
    r"after|once|when|as\s+soon\s+as|until|first|eventually)(?![а-яa-z])", re.IGNORECASE)
_FIRST_WORD = re.compile(r"(?<![а-яa-z])(?:сначала|сперва|для\s+начала|прежде\s+всего|first)(?![а-яa-z])", re.IGNORECASE)
# A condition or a time clause before the frame: the plan holds in another position.
_COND_BEFORE = re.compile(r"(?<![а-яa-z])(?:если|когда|как\s+только|после\s+того|пока\s+не|в\s+случае|при\s+условии|бы|"
                          # «После рокировки ладья встанет на f8», «При размене …»: a step named by a noun (review-fp 03.11)
                          r"после(?=\s+[а-я])|при(?=\s+(?!этом)[а-я])|"
                          r"if|when|once|after|until|unless|would)(?![а-яa-z])", re.IGNORECASE)
_PAST_PLAN = re.compile(r"(?<![а-яa-z])(?:был|была|было|были|стоило|следовало|хотел\w*|собирал\w*|планировал\w*|пытал\w*|"
                        r"готовил\w*|сыграл\w*|поставил\w*|вывел\w*|ставил\w*|развил\w*|играл\w*|пош[её]л|"
                        r"was|were|had|wanted|planned|played|tried)(?![а-яa-z])", re.IGNORECASE)


# A move told in the present or the future before a frame (the student's or the other side's): the plan is after it.
_TOLD_ACTION = re.compile(
    r"(?<![а-яa-z])(?:бер[её]шь|забира\w*шь|забер[её]шь|возьм[её]шь|бь[её]шь|побь[её]шь|играешь|сыграешь|отвечаешь|ответишь|"
    r"ставишь|поставишь|пойд[её]шь|ид[её]шь|двигаешь|разменяешь|разменива\w*шь|бер[её]т|берут|забира(?:ет|ют)|забер(?:[её]т|ут)|"
    r"возьм(?:[её]т|ут)|бь[её]т|бьют|побь(?:[её]т|ют)|сыгра(?:ет|ют)|ответ(?:ит|ят)|отвеча(?:ет|ют)|разменя(?:ет|ют)|"
    r"you\s+(?:take|play|capture)|(?:white|black|he|they)\s+(?:takes|plays|captures|replies))(?![а-яa-z])", re.IGNORECASE)


def _item_move(board: chess.Board, kind: str, m) -> tuple:
    """(move, san) for a scope item on *board*, or (None, None) when it names no single legal move of the side to move."""
    if kind == "san":
        try:
            move = board.parse_san(m["san"] + (m["check"] or ""))
        except ValueError:
            return None, None
        return move, board.san(move)
    word = (m["piece"] or m.groupdict().get("epiece") or "").lower()
    ptype = next((t for stem, t in _PLACE_TYPE_ANY.items() if word.startswith(stem)), None)
    sq_name = (m["sq"] or m.groupdict().get("esq") or "").lower()
    if ptype is None or not sq_name:
        return None, None
    sq = chess.parse_square(sq_name)
    there = board.piece_at(sq)
    if there is not None and there.color == board.turn and there.piece_type == ptype:
        return None, None  # already there: a description, not a move
    frm = (m.groupdict().get("from") or m.groupdict().get("from2") or "").lower()
    moves = [mv for mv in board.legal_moves if mv.to_square == sq and board.piece_type_at(mv.from_square) == ptype
             and not mv.promotion and (not frm or mv.from_square == chess.parse_square(frm))]
    if len(moves) != 1:
        return None, None
    return moves[0], board.san(moves[0])


def _scope_items(scope: str, bare_first: bool) -> list:
    """The items of a plan's scope, in order: (start, end, kind, match)."""
    end = _SCOPE_END.search(scope)
    body = scope[: end.start()] if end else scope
    found = []
    for m in _MOVE.finditer(body):
        san = m["san"]
        if san[0] not in "KQRBNO" and not m["num"] and not m["bdots"] and "x" not in san \
                and not _BARE_PAWN_BEFORE.search(body[max(0, m.start() - 24): m.start()]):
            continue  # «давит на e4»: a square, not a move
        found.append((m.start(), m.end(), "san", m))
    for m in _ITEM_PLACE.finditer(body):
        if not any(s <= m.start() < e or m.start() <= s < m.end() for s, e, _, _ in found):
            found.append((m.start(), m.end(), "place", m))
    if bare_first:
        m = _ITEM_BARE.match(body)
        if m and not any(s < m.end() and m.start() < e for s, e, _, _ in found):
            found.append((m.start(), m.end(), "place", m))
    return sorted(found, key=lambda x: x[0])


def _frames(conv: str) -> list:
    """(start, end, detector, side word, strict link) of every frame in *conv*, in order."""
    out = []
    for m in _F_PLAN.finditer(conv):
        out.append((m.start(), m.end(), "plan_place", m["side"] or m["gside"] or m["eside"], False, m.group(0)))
    for m in _F_EVAL.finditer(conv):
        out.append((m.start(), m.end(), "propose_vocab", m["side"], True, m.group(0)))
    for m in _F_NEXT.finditer(conv):
        out.append((m.start(), m.end(), "propose_vocab", None, False, m.group(0)))
    for m in _F_IMPER.finditer(conv):
        out.append((m.start(), m.end(), "propose_vocab", "ты", False, m.group(0)))
    for m in _F_THIRD.finditer(conv):
        out.append((m.start(), m.end(), "plan_place", m["side"] or m["eside"], True, m.group(0)))
    for m in _F_GOES.finditer(conv):
        out.append((m.start(), m.start(), "plan_place", m["pside"] or "", None, m.group(0)))
    for m in _F_PRAISED_PLACE.finditer(conv):
        out.append((m.start(), m.start(), "propose_vocab", "", None, m.group(0)))
    for m in _F_PRAISED_SAN.finditer(conv):
        out.append((m.start(), m.start(), "propose_vocab", "", "san", m.group(0)))
    for m in _F_FIRST.finditer(conv):
        out.append((m.start(), m.end(), "plan_place", None, True, m.group(0)))
    return sorted(out, key=lambda x: x[0])


def _side_of_word(word: Optional[str], ctx: CheckContext, text: str) -> Optional[bool]:
    w = (word or "").lower().strip()
    if not w:
        return student_side(ctx, text)
    if w.startswith(("бел", "white")):
        return chess.WHITE
    if w.startswith(("черн", "black")):
        return chess.BLACK
    if w in ("ты", "тебе", "тебя", "вам", "вас") or w.startswith("тво"):
        return student_side(ctx, text)
    return None


def _deferred(conv: str, frame_end: int, items: list, k: int) -> bool:
    """Whether item *k* of a plan is put off: a later-word between the frame and it, or a precondition right after the
    list it ends (only connectors between)."""
    start, end = items[k][0], items[k][1]
    if _LATER_WORD.search(conv[frame_end: frame_end + start]):
        return True
    last = end
    for s, e, _, _ in items[k + 1:]:
        if re.fullmatch(r"[\s,]*(?:(?:и|или|and|or)\s+)?", conv[frame_end + last: frame_end + s]):
            last = e
        else:
            break
    return bool(_PRECOND_AFTER.match(conv[frame_end + last:]))


def _plan_frame(conv: str, ctx: CheckContext, frame) -> Optional[tuple]:
    """(detector, move, san) a frame proposes for the side to move, or None (not judged)."""
    board = ctx.current
    start, end, det, side_word, strict, words = frame
    side = _side_of_word(side_word, ctx, conv)
    if strict is None and not side_word:  # «Конь g8 идёт на f6»: the piece on its square tells the side
        g = _F_GOES.match(conv, start) or _F_PRAISED_PLACE.match(conv, start)
        frm = g and (g["from"] or g["from2"])
        if frm and board.piece_at(chess.parse_square(frm.lower())) is not None:
            side = board.piece_at(chess.parse_square(frm.lower())).color
    if side_word is not None and side_word != "" and side is None:
        return None
    if side != board.turn:
        return None  # the other side's plan, or the student's side unknown
    student = ctx.student_color
    if student is not None and side_word and side_word.lower().startswith(("бел", "черн", "white", "black")) \
            and side != student:
        return None  # the engine's own plan in a game: a forecast, not advice
    before = conv[:start]
    if _COND_BEFORE.search(before) or _NEGATION.search(conv[max(0, start - 24): start]):
        return None
    if _LATER_WORD.search(before[max(before.rfind(c) for c in ".;!?\n,") + 1:]):
        return None  # «Со временем конь встанет на d5», «…, потом конь пойдёт на f6»: not the move now
    if any(mv["num"] or mv["bdots"] or mv["san"][0] in "KQRBN" or "x" in mv["san"] for mv in _MOVE.finditer(before)):
        return None  # a step of a line written before it, judged in that line
    if _TOLD_ACTION.search(before):
        return None  # «Играешь и забираешь пешку f4, а взамен у тебя идея — …»: a move told first, the plan after it
    if _WORD_STEP_CASTLE.search(before):
        return None  # «Рокируйся: ладья встанет на f8», «После рокировки ладья встанет на f8»: castling told first (review-fp 03.11)
    if before.strip():
        from src.move_words import prose_moves

        if any(pm["move"] is not None for pm in prose_moves(before, board)):
            return None  # «Забираешь пешку f4, а взамен у тебя идея — ферзь на h4»: the plan comes after a move told in words
    if re.search(r"(?<![а-яa-z])(?:не|ни|not|never)(?![а-яa-z])", words):
        return None
    if strict == "san":  # «Ход Qe2 здесь логичен»: the written move is the item
        m = _F_PRAISED_SAN.match(conv, start)
        if m is None or _PRECOND_AFTER.match(conv[m.end():]):
            return None
        move, san = _item_move(board, "san", {"san": m["san"], "check": ""})
        return (det, move, san) if move is not None else None
    if strict is None:  # «Конь g8 идёт на f6»: the frame is its own item
        m = _F_GOES.match(conv, start) or _F_PRAISED_PLACE.match(conv, start)
        if m is None or _LATER_WORD.search(words) or _PRECOND_AFTER.match(conv[m.end():]):
            return None
        move, san = _item_move(board, "place", m)
        return (det, move, san) if move is not None else None
    scope = conv[end:]
    items = _scope_items(scope, bare_first=det == "plan_place" and words.rstrip().endswith((":", "—", "–")))
    if not items:
        return None
    if strict and not _F_LINK.fullmatch(scope[: items[0][0]]):
        return None  # «хорошо видно, что …»: the predicate is not about the move
    if _PAST_PLAN.search(words) or _PAST_PLAN.search(scope[: items[0][0]]):
        return None
    if _NEGATION.search(scope[max(0, items[0][0] - 24): items[0][0]]) and items[0][0] > 0:
        return None
    k = 0
    if _deferred(conv, end, items, 0):
        # «… — но сначала надо подготовить это ходом f4»: the move «сначала» names is the move now
        after = conv[end + items[0][1]:]
        first = _FIRST_WORD.search(after)
        if not first:
            return None
        rest = after[first.end():]
        later = _scope_items(rest, bare_first=False)
        if not later or not re.fullmatch(r"[\s,—–:-]*(?:(?:надо|нужно|следует|стоит)\s+)?(?:\w+\s+){0,3}?"
                                         r"(?:(?:ходом|ходами|сыграть|играть|through|with|by)\s+)?", rest[: later[0][0]]):
            return None
        move, san = _item_move(board, later[0][2], later[0][3])
        return (det, move, san) if move is not None else None
    move, san = _item_move(board, items[k][2], items[k][3])
    return (det, move, san) if move is not None else None


def _plan_place_move(text: str, ctx: CheckContext) -> Optional[tuple]:
    """C1a/C1b: (board, move, san) for the move a plan, an idea or an evaluation proposes to the side to move now."""
    board = ctx.current
    if board is None or "?" in text or _FAILS.search(text) or _DENIES.search(text):
        return None
    conv, _ = _to_san(text)
    conv = re.sub(r"(?<![0-9A-Za-z])0-0-0(?![0-9-])", "O-O-O", conv)
    conv = re.sub(r"(?<![0-9A-Za-z])0-0(?![0-9-])", "O-O", conv)
    from src.config import detector_mode

    review = _review_asked(ctx)
    for frame in _frames(conv):
        try:
            got = _plan_frame(conv, ctx, frame)
        except Exception:  # noqa: BLE001 — a broken reading never blocks an answer
            logger.debug("plan frame failed", exc_info=True)
            got = None
        if got is None:
            continue
        det, move, san = got
        if (ctx._key(board), move.uci()) in ctx.line_next or (review and det == "plan_place"):
            return None  # the game's or the line's own next move, told in the present: narration, not advice
        mode = detector_mode(det, ctx)
        if mode == "shadow":
            record_shadow(ctx, det, [f"«{frame[5].strip()}» proposes {san}: proposed to the engine"])
        if mode != "on":
            return None
        return board, move, san
    return None


# A proposal word that proposes nothing now (F5 01.11): governed by a preventing verb («не давая чёрным спокойно сыграть
# e5», "not letting Black play e5": the move denied to the other side — prod 2026-11-01 review, six true sentences cut on
# main), in the past («можно было закрыться ферзём — Qf6», «надо было сыграть»), or a possibility outranked in the same
# sentence («Можно закрыться и ферзём на d2, но слон лучше»).
_GOVERNOR_NOT = re.compile(
    r"(?<![а-яa-z])(?:не\s+(?:[а-я]+\s+)?(?:дава\w*|дать|даст|дает|дадут|даю|позвол\w*|пуска\w*|пуст\w*)|меша\w*|помеша\w*|"
    r"лиша\w*|запреща\w*|запрет\w*|предотвра\w*|препятству\w*|not\s+(?:letting|allowing)|without\s+letting|"
    r"prevent\w*|stopping|denying|"
    # difficulty, danger or impossibility governing the infinitive (review fp2 01.11: «чёрным трудно сыграть d5»):
    # what the words say the side cannot or should not play — not a proposal
    r"трудно|тяжело|сложно|непросто|опасно|рискованно|нельзя|невозможно|не\s+стоит|не\s+следует|не\s+надо|не\s+нужно|"
    r"не\s+получится|не\s+удастся|не\s+удаётся|не\s+удается|не\s+(?:сможет|смогут|сможешь|может|могут|можешь)|"
    r"(?:hard|difficult|dangerous|risky|impossible|tough)\s+(?:for\s+\w+\s+)?to|cannot|can'?t|should\s+not|shouldn'?t)"
    r"(?:\s+[^\s,.;:!?—–]+){0,3}\s*$", re.IGNORECASE)
_PAST_MODAL = re.compile(r"\s*(?:бы\s+)?(?:был[аио]?|had)(?![а-яa-z])", re.IGNORECASE)
_WEAK_PROPOSAL = re.compile(r"можно|могу|можешь|could|can|might", re.IGNORECASE)
_OUTRANKED = re.compile(r"(?<![а-яa-z])(?:но|а|однако|but|however|though)(?![а-яa-z])[^.!?;]*?(?<![а-яa-z])(?:лучше|сильнее|точнее|"
                        r"надежнее|предпочтительн\w*|better|stronger|preferable)(?![а-яa-z])", re.IGNORECASE)


def _not_a_proposal(text: str, m) -> bool:
    if m.group(0).strip().lower() == "стоит" and re.match(r"\s*(?:[,.;:!?—–)]|$|(?:на|в|у|за|рядом|перед)\s)", text[m.end():]):
        return True  # «Ферзь h5 уже стоит, …», «конь стоит на f6»: stands, not «it is worth»
    cut = max(text.rfind(c, 0, m.start()) for c in ".;:!?—–(")
    if _GOVERNOR_NOT.search(text[cut + 1: m.start()]):
        return True
    if _PAST_MODAL.match(text, m.end()) or re.search(r"(?<![а-яa-z])был[аио]?\s+$", text[max(0, m.start() - 8): m.start()]):
        return True
    return bool(_WEAK_PROPOSAL.fullmatch(m.group(0).strip()) and _OUTRANKED.search(text, m.end()))


def _put_off(after: str) -> bool:
    """Whether the move whose text ends where *after* begins is put off by the words right after it (its list too)."""
    rest = re.sub(r"^(?:[\s,]*(?:(?:и|или|and|or)\s+)?[*_]*(?:\d{1,3}\s?\.{1,3}\s?)?(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|"
                  r"[a-h]x?[a-h]?[1-8]|O-O(?:-O)?)[+#]?[*_]*)*", "", after)
    return bool(_PRECOND_AFTER.match(rest))


# Where the recommended move must sit: in the same clause, before any «если»/«после»
# (those start a hypothetical, not the recommendation) and before «но»/«а не»/«вместо».
# The /learn lesson tutor is the team's (Асан 19.10): it keeps the proposal reading of 31.10 exactly.
_PROPOSAL_END_V1031 = re.compile(
    r"\.(?!\s?(?:[KQRBNO]|[a-h][1-8x]))|[;!?\n]|"
    r",\s*(?:но|а|если|когда|после|пока|потому|вместо|but|if|when|after|instead|rather|because)(?![а-яa-z])|"
    r"\s(?:если|после|когда|вместо|а\s+не|но\s+не|if|after|when|instead\s+of|rather\s+than|not)(?![а-яa-z])",
    re.IGNORECASE)


def _lesson(ctx) -> bool:
    return getattr(ctx, "relation_surface", "text") == "lesson"


def _main_reading(ctx) -> bool:
    """main's reading (31.10) of proposals, recapture pairs and written lines: F5 (01.11) reads them by structure, and
    its switch structure_read (verify1102 B3) brings main's back — 'off' everywhere, and always in the lesson tutor
    (src/config.detector_mode gives the lesson 'off'); 'shadow' reads as main and records what F5 proposes otherwise."""
    return _lesson(ctx) or _switch_mode("structure_read", ctx) != "on"


_PROPOSAL_END = re.compile(
    r"(?<![\d.])\.(?!\.)(?!\s?(?:[KQRBNO]|[a-h][1-8x]))|[;!?\n]|"  # not the dots of «...Nf6», «3...Nf6» (F5 01.11)
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
_PAWN_MOVE_WORDS_V1031 = re.compile(
    r"(?:пешк\w*\s*(?:на|в|[:—–-])\s*|пешкой\s+(?:на\s+)?|pawn\s+(?:to|on|onto)\s+|push(?:ing)?\s+(?:the\s+pawn\s+(?:to\s+)?)?|"
    r"(?:толкн\w+|продвин\w+|двин\w+)\s+(?:пешку\s+)?(?:на\s+)?)$", re.IGNORECASE)  # not «пешка e5 висит»: that names a square
# …nor «разобраться с пешкой f3», «с пешкой на e5»: «с» + the pawn names the pawn standing there (K3 02.11, st3#7 live).
# The /learn lesson tutor keeps the reading above.
_PAWN_MOVE_WORDS = re.compile(
    r"(?:(?<!\bс\s)(?<!\bсо\s)пешк\w*\s*(?:на|в|[:—–-])\s*|(?<!\bс\s)(?<!\bсо\s)пешкой\s+(?:на\s+)?|pawn\s+(?:to|on|onto)\s+|push(?:ing)?\s+(?:the\s+pawn\s+(?:to\s+)?)?|"
    r"(?:толкн\w+|продвин\w+|двин\w+)\s+(?:пешку\s+)?(?:на\s+)?)$", re.IGNORECASE)


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
_I_MOVED = re.compile(r"(?<![а-яa-z])я\s+(?:(?!бы\s)[а-яa-z]+\s+)?(?:пош[её]л|сходил|сыграл\w*|взял\w*|побил\w*|поставил\w*|отош[её]л|"
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


# K3 02.11 (VERDICT §6.1): a move is judged on the board where it is played. python-chess reads «Qxf3» as Qf3 on a board
# where f3 is empty (st3#7 live: «Вот что было лучше: Qxf3» — the capture of a past position, judged as Qf3 now): a move
# written as a capture that captures nothing here is another board's move.
def _parse_here(board: chess.Board, san: str, lesson: bool = False) -> chess.Move:
    move = board.parse_san(san)
    if not lesson and "x" in san.split("=")[0] and not board.is_capture(move):  # the /learn tutor keeps 31.10's reading
        raise ValueError(f"{san} captures nothing on this board")
    return move


# Advice for a past position («было лучше Qxf3», «надо было забирать», "should have played"): the board it was meant for
# is not the board now, and which earlier board it is the words do not say — not judged on the board now (K3 02.11).
_PAST_ADVICE = re.compile(
    r"(?<![а-яa-z])(?:(?:лучше|сильнее|точнее|правильнее|над[её]жнее|надо|нужно|можно|следовало|стоило)\s+(?:бы\s+)?был[оаи]?"
    r"|был[оаи]?\s+(?:бы\s+)?(?:лучше|сильнее|точнее|правильнее|над[её]жнее|надо|нужно|можно)|стоило|следовало|"
    r"should\s+have|could\s+have|would\s+have|(?:was|would\s+have\s+been)\s+(?:better|stronger|the\s+(?:best|right|correct)))"
    r"(?![а-яa-z])", re.IGNORECASE)
# The other side's answer told before the praise («После Qxd4 чёрные отвечают c5 и нападают на ферзя», «После 4.Nxe5
# чёрные отвечают Qg5 — ферзь нападает на коня»): the praise is the reply's, on the board after it — a line, whose outcome
# is line_verdict's to judge, not advice of the first move (K3 02.11: trap-noah, trap-blackburne live).
_SIDE_REPLIES = re.compile(
    r"(?<![а-яa-z])(?:белые|черные|соперник\w*|противник\w*|оппонент\w*|white|black|(?:the\s+|your\s+|my\s+)?opponent)\s+"
    r"(?:[а-яa-z]+\s+){0,2}?(?:игра\w*|сыгра\w*|пойд\w*|ход(?:ит|ят)|бер[её]т|берут|возьм\w+|бь[её]т|бьют|забира\w+|забер\w+|"
    r"отвеча\w+|ответ\w*|plays?|takes?|captures?|replies|answers?)(?![а-яa-z])", re.IGNORECASE)


def _praise_of_reply(before_praise: str) -> bool:
    """The words between a candidate move and its praise tell the other side's answer (a reply verb, the other side
    playing, or another written move): the praise is about the line, not the candidate."""
    return bool(_REPLY.search(before_praise) or _SIDE_REPLIES.search(before_praise)
                or _SAN_IN_TEXT.search(_to_san(before_praise)[0]))


def _reply_in_words(board: chess.Board, move: chess.Move, words: str) -> bool:
    """*words* tell a move of the other side after *move* («ферзь идёт на g5»): the praise after them is the reply's."""
    if not words.strip():
        return False
    try:
        from src.move_words import prose_moves

        after = board.copy(stack=False)
        after.push(move)
        return any(pm.get("move") is not None for pm in prose_moves(words, after))
    except Exception:  # noqa: BLE001
        return False


# (named apart from _NOMINATIVE_PIECE above, the Russian subject after the verb in «e5 атакует конь f3»: one name for
# both made «d4 attacks the knight on e5» read the English object as the subject — integration 02.11)
_PRAISE_SUBJECT_PIECE = re.compile(
    r"(?<![а-яa-z])(конь|слон|ладья|ферзь|король|пешка|knight|bishop|rook|queen|king|pawn)(?![а-яa-z])", re.IGNORECASE)


def _other_subject(before_praise: str, moved: Optional[int]) -> bool:
    """The praise word's subject, named right before it, is a piece of another kind than the one the candidate moves
    («После 5.Nxe5 слон забирает ферзя…»): what it wins is that piece's, on the board after the reply."""
    names = list(_PRAISE_SUBJECT_PIECE.finditer(before_praise))
    if not names or moved is None:
        return False
    return _piece_type(names[-1].group(1).lower()) != moved


def _past_praise(tail: str, praise) -> bool:
    """The praise word is in the past («ферзь забирал пешку», «бил по g2»): what the move would have done on a board
    that is gone."""
    end = praise.end()
    while end < len(tail) and (tail[end].isalpha()):
        end += 1
    start = praise.start()
    while start > 0 and tail[start - 1].isalpha():
        start -= 1
    word = tail[start:end].lower()
    return bool(re.search(r"[а-я](?:л|ла|ло|ли|лся|лась|лось|лись)$", word))


_COMPARES = re.compile(r"(?<![а-яa-z])(?:сильнее|лучше|точнее|над[её]жнее|правильнее|предпочтительн\w*|better|stronger)(?![а-яa-z])",
                       re.IGNORECASE)


def board_before_students_move(ctx: Optional[CheckContext], sentence: str, san: str) -> Optional[tuple]:
    """(board, move, san) of *san* on the board before the student's move this turn played, when *sentence* compares
    («Можно, но сильнее d5», "d5 was stronger") and the move is legal there: the advice may be the move the student
    could have played instead (K3 02.11, fresh-fp f10: judged only after the engine's reply, «сильнее d5» was cut)."""
    if ctx is None or not getattr(ctx, "student_moved_now", False) or not _COMPARES.search(sentence or ""):
        return None
    moves = list(getattr(ctx, "game_moves", None) or [])
    if ctx.student_color is None or not moves:
        return None
    try:
        board = chess.Board()
        for m in moves:
            board.push_san(m)
        # back to the board the student moved on: one ply when it is the engine's turn, two after its reply
        back = 1 if board.turn != ctx.student_color else 2
        if len(moves) < back:
            return None
        for _ in range(back):
            board.pop()
        if board.turn != ctx.student_color:
            return None
        before = chess.Board(board.fen())
        move = _parse_here(before, san)
        return before, move, before.san(move)
    except ValueError:
        return None


def proposed_move(sentence: str, ctx: Optional[CheckContext]) -> Optional[tuple]:
    """The move the coach recommends to the side to move on the board on the
    screen: (board, move, san), or None. In notation («Rg1», «Лg1») or in words
    («поставь ладью на g1»). A sentence that refutes a move («Rg1 сыграть
    нельзя»), or says not to play it, recommends nothing. The move the student
    asked about («А если Be7+?») is looked at, not advised — «Ход Be7+ даёт шах:
    слон бьёт по королю» describes it — unless the sentence recommends it in so
    many words («Be7+ — хороший ход», «лучше Be7+»)."""
    found = _proposed_move(sentence, ctx)
    if found and not _lesson(ctx):
        try:
            if _not_now(sentence, found):
                return None
        except Exception:  # noqa: BLE001 — the reading stays as it was
            logger.debug("not-now reading failed", exc_info=True)
    if found and ctx.quoted and not _RECOMMENDS.search(sentence.replace("ё", "е")):
        bare = found[2].rstrip("+#").replace("x", "")
        if bare in {q.rstrip("+#").replace("x", "") for q in ctx.quoted}:
            return None
    return found


# Where the proposed move is named, what around it says it is not the move now (review-fp 03.11, the voice's five new
# engine cuts, written twins cut since 31.10): a step before it in the same thought («После длинной рокировки можно
# слоном на h6», «Сначала отступи слоном на h4, а потом можно ферзём на c2»), castling told before a rook or king move
# (its result: «Рокируйся: ладья встанет на f8»), or the words after it putting it off or ruling it out («Конём на f3
# сейчас рано», «Ферзём на c2 нападать … не стоит:», «…, но сейчас это рано»).
_STEP_BEFORE = re.compile(r"(?<![а-яa-z])(?:после|при(?=\s+(?!этом)[а-я])|потом|затем|позже|позднее|впоследствии|"
                          r"after|later|afterwards)(?![а-яa-z])", re.IGNORECASE)
_RULED_OUT_AFTER = re.compile(
    r"^[^.!?;]*?(?:(?<![а-яa-z])(?:рано(?!\s+или\s+поздно)|преждевременн\w*)(?![а-яa-z])"
    r"|(?<![а-яa-z])не\s+(?:стоит|надо|нужно|следует|время|спеши\w*)(?=\s*(?:[.,:;!?—–]|$))"
    r"|(?<![a-z])(?:too\s+early|premature|not\s+yet)(?![a-z]))", re.IGNORECASE)


def _named_span(sentence: str, board: chess.Board, move: chess.Move) -> Optional[tuple]:
    """(start, end) of where *sentence* names *move* of the side to move — in words or in notation — or None."""
    from src.move_words import prose_moves, resolve, _ptype

    text = sentence.replace("ё", "е")
    low = text.lower()
    spans = []
    for pm in prose_moves(text, board):
        if pm["move"] == move:
            at = low.find(pm["words"].lower(), max(0, pm.get("at", 0) - 2))
            if at >= 0:
                spans.append((at, at + len(pm["words"])))
    for rx in (_TOLD_WITH, _TOLD_GOES):
        for m in rx.finditer(low):
            ptype = _ptype(m["piece"])
            if ptype is not None and resolve(board, ptype, chess.parse_square(m["to"]))[1] == move:
                spans.append((m.start(), m.end()))
    converted, _ = _to_san(text)
    for m in _MOVE.finditer(converted):
        try:
            if board.parse_san(m["san"]) == move:
                spans.append((m.start(), m.end()))
        except ValueError:
            continue
    return min(spans) if spans else None


def _not_now(sentence: str, found: tuple) -> bool:
    board, move, _san = found
    span = _named_span(sentence, board, move)
    if span is None:
        return False
    low = sentence.replace("ё", "е").lower()
    before, after = low[: span[0]], low[span[1]:]
    thought = before[max(before.rfind(c) for c in ".;!?") + 1:]
    if _STEP_BEFORE.search(thought):
        return True
    if _WORD_STEP_CASTLE.search(before) and board.piece_type_at(move.from_square) in (chess.ROOK, chess.KING) \
            and not board.is_castling(move):
        return True
    return bool(_RULED_OUT_AFTER.match(after))


def _proposed_move(sentence: str, ctx: Optional[CheckContext]) -> Optional[tuple]:
    """The proposal reading as structure_read's switch says (verify1102 B3): 'on' the reading widened since main, 'off'
    main's (the lesson tutor always), 'shadow' main's, with the widened one's other answer recorded."""
    if ctx is None or ctx.current is None or not sentence:
        return None
    mode = "off" if _lesson(ctx) else _switch_mode("structure_read", ctx)
    if mode == "on":
        return _proposed_move_read(sentence, ctx, False)
    got = _proposed_move_read(sentence, ctx, True)
    if mode == "shadow":
        new = _fail_open(_proposed_move_read, sentence, ctx, False) or None
        if (new or (None, None, None))[2] != (got or (None, None, None))[2]:
            record_shadow(ctx, "structure_read", [f"the widened reading proposes {new[2] if new else 'nothing'}, "
                                                f"main's {got[2] if got else 'nothing'}"])
    return got


def _proposed_move_read(sentence: str, ctx: CheckContext, lesson: bool) -> Optional[tuple]:
    """*lesson*: main's proposal reading of 31.10 (the lesson tutor's, and structure_read 'off')."""
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
            move = _parse_here(ctx.current, mv["san"] + (mv["check"] or ""), lesson)
        except ValueError:
            break
        return ctx.current, move, ctx.current.san(move)
    starts = list((_PROPOSES_V1029 if lesson else _PROPOSES).finditer(text))
    if not lesson:
        # The proposal words the legality check reads (_WORD_PROPOSES: «давай», «двинь», «пора», «хороший план —», «тут
        # сильно пойти», «обрати внимание на ход») propose to the engine too — one set of sentences for both stages
        # (review-miss 03.11: «Двинь пешку на c4» judged when illegal, never when it loses 4 pawns). A question only as a
        # suggestion; not after a line written or told before it.
        for w in _WORD_PROPOSES.finditer(text):
            if any(st.start() <= w.start() < st.end() for st in starts):
                continue
            head = text[max(text.rfind(c, 0, w.start()) for c in ".;!?\n") + 1: w.start()]
            if "?" in text[w.end():] and not _SUGGEST_Q.match(text[max(text.rfind(c, 0, w.start()) for c in ".;!?\n") + 1:]):
                continue
            if _WORD_LINE.search(head) or _PAST_ADVICE.search(text[max(0, w.start() - 30): w.end() + 16]):
                continue
            starts.append(w)
        starts.sort(key=lambda x: x.start())
    vocab = list(_PROPOSE_VOCAB.finditer(text))
    if vocab:
        from src.config import detector_mode

        mode = detector_mode("propose_vocab", ctx)
        if mode == "on":
            starts = sorted(starts + vocab, key=lambda x: x.start())
        elif mode == "shadow":
            record_shadow(ctx, "propose_vocab", [f"advice «{v.group(0).strip()}» proposed to the engine" for v in vocab])
    you_play = _YOU_PLAY.match(text)
    if you_play and "?" not in text and not _FAILS.search(text) and not _REPLY.search(text) \
            and student_side(ctx, text) == ctx.current.turn and not _tells_line(text[you_play.end():]) \
            and not _review_asked(ctx):
        starts.insert(0, you_play)
    from src.claim_rules import prevention_frame, prevention_start

    for m in starts:
        if _NEGATION.search(text[max(0, m.start() - 24): m.start()]):
            continue  # «не стоит играть Rg1», "don't play Rg1"
        if not lesson and _not_a_proposal(text, m):
            continue
        if not lesson and prevention_frame(text[:m.start()]):
            continue  # «d4, не давая чёрным спокойно сыграть e5»: the move the sentence says is stopped, not advice (F3)
        clause = text[m.end():]
        rest_conv = _to_san(clause)[0]
        end = (_PROPOSAL_END_V1031 if lesson else _PROPOSAL_END).search(clause)
        if end:
            clause = clause[: end.start()]
        if not lesson:
            stop = prevention_start(clause)
            if stop is not None:
                clause = clause[:stop]  # «стоит, не давая чёрным поставить коня на f6»: the stopped move is no proposal
        clause = clause[:90]
        converted, _ = _to_san(clause)
        for mv in _MOVE.finditer(converted):
            if not lesson and (_GOVERNOR_NOT.search(converted[: mv.start()]) or re.match(r"[*_]*\?", rest_conv[mv.end():])):
                continue  # «стоит, не давая чёрным сыграть e5»; «Kd2? Нет, лучше Bd2»
            san = mv["san"]
            if san[0] not in "KQRBNO" and not mv["num"] and not mv["bdots"] and "x" not in san \
                    and not (_PAWN_MOVE_WORDS_V1031 if lesson else _PAWN_MOVE_WORDS).search(converted[max(0, mv.start() - 24): mv.start()]) \
                    and not re.fullmatch(r"[\s—–:\-]*(?:здесь\s+|сейчас\s+|here\s+|now\s+)?", converted[: mv.start()]):
                continue  # «e4» is a square («пешка e5 висит») unless a pawn is told to go there («пешкой: g6», "pawn to e4») or it is the move itself («лучше d4»)
            if _EXPLORES.fullmatch(m.group(0).strip()) and san.replace("x", "") in {q.replace("x", "") for q in ctx.quoted}:
                continue  # «Сыграем Be7+ и посмотрим», «можно Be7+»: the student's own idea looked at, not advice
            try:
                move = _parse_here(ctx.current, san + (mv["check"] or ""), lesson)
            except ValueError:
                continue
            if m is you_play and (ctx._key(ctx.current), move.uci()) in ctx.line_next:
                break  # the game's or the line's own next move, told in the present: narration, not advice
            if not lesson and _put_off(rest_conv[mv.end():]):
                break  # «Сыграй Nd5, но только после f4»: not the move now
            return ctx.current, move, ctx.current.san(move)
        try:
            from src.move_words import prose_moves

            noun = None if lesson else _noun_frame_item(m.group(0), clause, ctx.current)
            if noun is not None and (_TOLD_ACTION.search(text[:m.start()]) or prose_moves(text[:m.start()], ctx.current)):
                noun = None  # «Играешь и забираешь пешку f4 …, а взамен — идея: ферзь на h4»: a plan after a told move
            if noun is None and not lesson and _WORD_TAKE.match(m.group(0).strip()):
                noun = _with_frame_verb(m.group(0), clause, ctx.current)  # «Возьми конём ферзя на d8»: not «ферзя на d8» as Q
            for pm in ([noun] if noun is not None else []) + prose_moves(clause, ctx.current):
                if pm["move"] is not None:
                    if m is you_play and (ctx._key(ctx.current), pm["move"].uci()) in ctx.line_next:
                        break
                    at = clause.lower().replace("ё", "е").find(pm["words"].lower())
                    if not lesson and at >= 0 and (_GOVERNOR_NOT.search(clause[:at])
                                    or re.match(r"[\s—–:-]*[*_]*(?:[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8])?[+#]?[*_]*\?",
                                                rest_conv[at + len(pm["words"]):])):
                        continue  # the move denied to the other side, or the doubtful one («увести короля — Kd2?»)
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
        if not lesson and _PAST_ADVICE.search(converted[: mv.start()]):
            continue  # «Было лучше Qxf3!»: a past board's move (K3 02.11)
        try:
            move = _parse_here(ctx.current, san + (mv["check"] or ""), lesson)
        except ValueError:
            continue
        return ctx.current, move, ctx.current.san(move)
    # A move with what it wins after it, in notation or in words («если конь прыгнет
    # на f7 — он бьёт ладью и ферзя»): the coach's idea, checked like advice.
    candidates = []
    for mv in _MOVE.finditer(converted):
        san = mv["san"]
        if san[0] in "KQRBNO" or mv["num"] or mv["bdots"] or "x" in san \
                or (_PAWN_MOVE_WORDS_V1031 if lesson else _PAWN_MOVE_WORDS).search(converted[max(0, mv.start() - 24): mv.start()]):
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
        cut = max(converted.rfind(c, 0, start) for c in ".;:!?—–(")
        if not lesson and (_GOVERNOR_NOT.search(converted[cut + 1: start]) or re.match(r"[*_]*\?", converted[end:])):
            continue  # «не давая чёрным поставить коня на f6 из-за мата»: the move denied to the other side
        if ctx.student_color is not None and ctx.current.turn == ctx.student_color \
                and _COACH_OWN_PIECE.search(text[max(0, start - 30): start] + " " + converted[max(0, start - 30): start]):
            continue  # «моя пешка на f6 забирает твоего слона» in a game: the engine's pawn told, not advice (prod Live 29.10)
        tail = text[end: end + 90]
        cut = re.search(r"[.;!?\n]|\s(?:но|а\s+не|однако|but|however)(?![а-яa-z])", tail)
        tail = tail[: cut.start()] if cut else tail
        if not _PRAISE.search(tail) or _NEGATED_WORD.search(tail[: _PRAISE.search(tail).start()]):
            continue
        praise = _PRAISE.search(tail)
        if not lesson and (_praise_of_reply(tail[: praise.start()]) or _past_praise(tail, praise)
                           or _PAST_ADVICE.search(text[:start])):
            continue  # the reply's praise (a line), or what the move would have done on a past board (K3 02.11)
        if move is None:
            try:
                move = _parse_here(ctx.current, san, lesson)
            except ValueError:
                continue
        if san.replace("x", "") in {q.replace("x", "") for q in ctx.quoted} and not _PRAISE.search(tail):
            continue
        if not lesson and (_reply_in_words(ctx.current, move, tail[: praise.start()])
                           or _other_subject(tail[: praise.start()], ctx.current.piece_type_at(move.from_square))):
            continue  # «После 4.Nxe5 ферзь идёт на g5 и атакует коня», «…слон забирает ферзя»: another piece's praise (K3 02.11)
        return ctx.current, move, ctx.current.san(move)
    try:
        return _plan_place_move(text, ctx)
    except Exception:  # noqa: BLE001 — a broken plan reader never blocks an answer
        logger.debug("plan placement failed", exc_info=True)
        return None


# ── A move proposed in words that cannot be played (voice 02.11, word_move) ────────────────────────────────────────
# Live 02.11 (a game, White to move 9): «пойти ферзём на d1» with the queen on d1, «может попробуешь пойти пешкой на d2
# на d3?» and «Давай лучше пешкой на d3 пойдём» with Black's bishop on d3 — no check read them: the proposal reader
# (_proposed_move_read) takes only a move that is legal and hands it to the engine, so a move that cannot be played was
# no proposal at all. Here the same frames (_PROPOSES, and the spoken suggestion frames below) and the same move reader
# (src/move_words.prose_moves) are read for the move that has NO legal form: the piece already stands there, the square
# holds an own piece (any piece, for a pawn going straight), the way is blocked, no such piece, nothing to take, the
# move would leave the king in check (src/move_words.why_not). Several pieces able to go there is fine.
# Left unjudged: a line («если …», «после …», «потом/затем», «вместо», a written move before it, a sentence going on
# with the line before it), the other side's move, the coach's own move in a game, a question that is not a suggestion,
# a denial, a past board («надо было …»), a piece told in the nominative («лучше ферзь на d1» may name where it stands —
# only «no such piece» is judged there), a move numbered for another move of the game.
_WORD_PROPOSES = re.compile(
    # «может» as "maybe" — a comma after it, or the student addressed («может, пойти…», «может попробуешь…»); not the
    # verb "can" of a third person («(соперник) может пойти ферзём на h4»)
    r"(?<![а-яa-z])(?:(?:а\s+)?может(?:\s*,?\s*быть)?(?=\s*,|\s+(?:ты|тебе|вам|вы|стоит|лучше)(?![а-я])|\s+(?:просто\s+|сейчас\s+)?"
    r"(?:попробуешь|пойд[её]шь|сходишь|сыграешь|двинешь|поставишь|перевед[её]шь|отвед[её]шь|возьм[её]шь|побь[её]шь)(?![а-я]))|"
    r"давай(?:те)?|почему\s+бы\s+(?:тебе\s+)?не|как\s+насч[её]т|сходи(?:те)?|иди(?:те)?|двинь(?:те)?|двигай(?:те)?|"
    r"толкни(?:те)?|продвинь(?:те)?|подвинь(?:те)?|передвинь(?:те)?|прыгни(?:те)?|выведи(?:те)?|пойд[её]м|сходим|двинем|"
    r"поставим|перевед[её]м|отвед[её]м|можешь|попробуешь|я\s+бы\s+(?:пош[её]л|сходил|двинул|пошла|сходила|побил\w*|забрал\w*|"
    r"съел\w*|срубил\w*)|"
    # review-miss 02.11 #4: the proposal wordings no frame read
    r"переставь(?:те)?|переставим|отправь(?:те)?|отправим|спрячь(?:те)?|убери(?:те)?|съешь(?:те)?|побей(?:те)?|"
    r"забери(?:те)?|сруби(?:те)?|руби(?:те)?|(?:сейчас\s+)?самое\s+время|пора|хорош\w*\s+ход|неплохо(?:\s+было)?(?:\s+бы)?|"
    r"(?:отличн|хорош|неплох|сильн|интересн|достойн|лучш)\w*\s+(?:вариант|идея|продолжение|решение|выбор|план)|"
    r"(?:тебе\s+)?нуж(?:ен|но)\s+ход|"
    # review-miss 03.11: an adverb with an infinitive of playing («Тут сильно пойти конём на f3»), «обрати внимание на
    # ход …», «посмотри на ход …» — read by the legality check and the engine stage alike
    r"(?:сильно|интересно|полезно|логично|разумно|хорошо|отлично|здорово|любопытно)(?:\s+бы)?(?=\s+(?:было\s+)?(?:пойти|сыграть|"
    r"сходить|двинуть|поставить|перевести|отвести|продвинуть|переставить|вывести|взять|побить|забрать)(?![а-я]))|"
    r"обрати(?:те)?\s+внимание\s+на(?=\s+(?:ход|продолжение|идею|вариант)(?![а-я]))|"
    r"посмотри(?:те)?\s+на(?=\s+(?:ход|продолжение|идею)(?![а-я]))|"
    r"move|bring|let'?s|how\s+about|what\s+about|why\s+not|maybe)(?![а-яa-z])", re.IGNORECASE)
# The words allowed between the proposal word and the move: verbs of moving, the student, adverbs, a possessive.
_WORD_GAP_OK = re.compile(
    r"(?:пойти|пойди(?:те)?|пойд[её]м|пойд[её]шь|сходить|сходи(?:те)?|сходим|сходишь|сыграть|сыграй(?:те)?|сыграем|сыграешь|"
    r"играть|двинуть|двинь(?:те)?|двинем|двинешь|подвинуть|продвинуть|передвинуть|толкнуть|поставить|поставь(?:те)?|"
    r"поставим|поставишь|перевести|переведи(?:те)?|перевед[её]м|перевед[её]шь|отвести|отведи(?:те)?|отвед[её]шь|увести|"
    r"уведи(?:те)?|вывести|выведи(?:те)?|ходить|ходи(?:те)?|идти|иди(?:те)?|походить|прыгнуть|прыгни(?:те)?|отступить|"
    r"взять|возьми(?:те)?|возьм[её]шь|побить|побей(?:те)?|бить|бей(?:те)?|забрать|забери(?:те)?|съесть|съешь|сделать|"
    r"сделай(?:те)?|ход|ходом|попробовать|попробуй(?:те)?|попробуешь|попытаться|рискнуть|"
    r"переставить|переставь(?:те)?|переставим|отправить|отправь(?:те)?|спрятать|спрячь(?:те)?|убрать|убери(?:те)?|"
    r"уведи(?:те)?|увед[её]м|возьм[её]м|съедим|побь[её]м|забер[её]м|того|чтобы|было|"
    r"bringing|putting|placing|sending|taking|"
    r"тебе|вам|ты|вы|бы|сейчас|здесь|тут|теперь|сразу|просто|все-таки|всетаки|же|лучше|всего|еще|уже|наконец|спокойно|"
    r"смело|именно|может|быть|можно|стоит|наверное|пожалуй|все|сначала|сперва|прямо|своим|своей|свою|своего|сво[ей]|"
    r"твоим|твоей|твою|твоего|этим|этой|эту|этого|этот|эта|ли|вот|и|а|ну|да|давай(?:те)?|например|"
    r"you|could|should|can|just|now|here|simply|the|your|to|try|play|move|put|bring|push|advance|go|with|i'?d|would|"
    r"consider|playing|moving|putting|pushing|going|maybe|perhaps|instead|first|then)", re.IGNORECASE)
_WORD_LINE = re.compile(
    r"(?<![а-яa-z])(?:если|когда|после|потом|затем|дальше|далее|следом|вместо|иначе|пока|в\s+ответ|в\s+случае|"
    r"следующ\w+\s+ход\w*|на\s+следующем\s+ходу|вторым\s+ходом|в\s+варианте|if|when|after|then|next|later|once|"
    # a time to come (review-fp 02.11: «Позже можно поставить ладью на d1», «Через пару ходов можно поставить коня на d3»)
    r"позже|позднее|со\s+временем|в\s+будущем|в\s+дальнейшем|впоследствии|в\s+перспективе|через\s+(?:\w+\s+)?ход\w*|"
    r"как\s+только|eventually|in\s+a\s+few\s+moves|"
    r"otherwise|instead|unless|in\s+reply)(?![а-яa-z])", re.IGNORECASE)
_WORD_SIDE = re.compile(
    r"(?<![а-яa-z])(?:(?P<w>белым|белые|за\s+белых|white)|(?P<b>черным|черные|за\s+черных|black)|"
    r"(?P<o>сопернику|соперник|противнику|противник|оппоненту|оппонент|он|она|они|ему|ей|им|opponent|he|she|they)|"
    r"(?P<me>я)(?!\s+бы)|(?P<you>ты|тебе|вам|вы|you))(?![а-яa-z])", re.IGNORECASE)
_WORD_KEEP_AFTER = re.compile(r"\s*(?:и\s+)?(?:не|оставить|оставь\w*|оставим|держать|держи\w*|сохранить|сохрани\w*|пусть|"
                              r"оста[её]тся|остается|стоять|постоит|стоит|keep|stays?|leave|not)(?![а-яa-z])", re.IGNORECASE)
_WORD_TAKE = re.compile(r"(?<![а-яa-z])(?:возьм\w*|взять|бери(?:те)?|бер[её]м|бей(?:те)?|бить|побить|побей(?:те)?|забер\w*|"
                        r"побил\w*|взял\w*|забрал\w*|"
                        r"забрать|забирай(?:те)?|съе\w*|руби\w*|срубить|разменя\w*|take|capture|grab|win)(?![а-яa-z])",
                        re.IGNORECASE)
# The piece named as the object of a capture («коня на d4», "the knight on d4"): the piece taken.
_WORD_INSTRUMENT = re.compile(r"(?<![а-яa-z])(?:ладь[её]й|кон[её]м|слоном|ферз[её]м|корол[её]м|пешкой|with\s+(?:the|my|your)\s+"
                              r"(?:rook|knight|bishop|queen|king|pawn))(?![а-яa-z])", re.IGNORECASE)
_WORD_OBJECT = re.compile(r"(?<![а-яa-z])(?:ладью|ладьи|коня|слона|ферзя|короля|пешку|пешки|(?:the\s+|his\s+|her\s+|their\s+)?"
                          r"(?:rook|knight|bishop|queen|king|pawn)\s+on)(?![а-яa-z])", re.IGNORECASE)
# A piece in the accusative («ладью на g1») goes to the square only with a verb of putting before or right after it.
_WORD_ACCUSATIVE = re.compile(r"(?:ладью|коня|слона|ферзя|короля|пешку)(?![а-яa-z])", re.IGNORECASE)
_WORD_PUT = re.compile(r"\s*(?<![а-яa-z])(?:поставить|постав(?:ь|ьте|им|ишь)|ставь(?:те)?|ставим|перевести|переведи(?:те)?|"
                       r"перевед[её](?:м|шь)|отвести|отведи(?:те)?|отвед[её](?:м|шь)|увести|уведи(?:те)?|вывести|выведи(?:те)?|"
                       r"двинуть|двинь(?:те)?|двигай(?:те)?|двин(?:ем|ешь)|продвинуть|продвинь(?:те)?|подвинуть|подвинь(?:те)?|"
                       r"передвинуть|передвинь(?:те)?|переставить|переставь(?:те)?|толкнуть|толкни(?:те)?|направить|"
                       r"направь(?:те)?|"
                       # review-miss 02.11 #4: «Отправь ладью на …», «Давай уведём коня на …», «Я бы поставил ладью на …»
                       r"отправить|отправь(?:те)?|отправим|спрятать|спрячь(?:те)?|убрать|убери(?:те)?|увед[её]м|"
                       r"поставил\w*|переставил\w*|перев[её]л\w*|отв[её]л\w*|ув[её]л\w*|двинул\w*|отправил\w*|"
                       r"put|place|move|bring|push|advance)(?![а-яa-z])", re.IGNORECASE)
# The student addressed: an imperative, an invitation, the second person, "you", «я бы» / «советую» (to the student).
_WORD_ADDRESSED = re.compile(
    r"(?<![а-яa-z])(?:сыграй\w*|играй\w*|поставь\w*|ставь\w*|пойди\w*|ходи(?:те)?|бей\w*|бери\w*|возьми\w*|забирай\w*|"
    r"выбирай\w*|выбери\w*|попробуй\w*|отведи\w*|уведи\w*|переведи\w*|разменяй\w*|сходи(?:те)?|иди(?:те)?|двинь\w*|"
    r"двигай\w*|толкни\w*|продвинь\w*|подвинь\w*|передвинь\w*|прыгни\w*|выведи\w*|сыграем|играем|бер[её]м|ставим|"
    r"ид[её]м|пойд[её]м|сходим|двинем|поставим|перевед[её]м|отвед[её]м|давай\w*|можешь|сможешь|попробуешь|пойд[её]шь|"
    r"сходишь|сыграешь|двинешь|поставишь|перевед[её]шь|отвед[её]шь|возьм[её]шь|побь[её]шь|тебе|ты|вам|вы|рекомендую|"
    r"побей\w*|съешь\w*|забери\w*|сруби\w*|руби(?:те)?|спрячь\w*|убери\w*|отправь\w*|переставь\w*|"
    r"советую|предлагаю|я\s+бы|you|let'?s|play|try|put|place|take|grab|capture|push|advance|move|bring|consider|"
    r"go\s+for|suggest|recommend)(?![а-яa-z])", re.IGNORECASE)
_SUGGEST_Q = re.compile(r"^\W*(?:а\s+)?(?:может|давай|почему\s+бы|как\s+насч[её]т|how\s+about|what\s+about|why\s+not|maybe)"
                        r"(?![а-яa-z])", re.IGNORECASE)
_PUSH_WORD = re.compile(r"(?<![а-яa-z])(?:push\w*|advance\w*|move|двин\w*|продвин\w*|подвин\w*|толкн\w*|пойти|пойди|сходи\w*|"
                        r"сыгра\w*|ход\w*)(?![а-яa-z])", re.IGNORECASE)


def _word_gap_ok(gap: str, board: chess.Board) -> bool:
    """*gap* holds only the words a proposal puts before its move (and a move number of the move now)."""
    for num in re.finditer(r"(?<![0-9])(\d{1,3})\s?(\.\.\.|…|\.)", gap):
        if int(num.group(1)) != board.fullmove_number or (num.group(2) == ".") != (board.turn == chess.WHITE):
            return False  # «12. конём на f5» while it is move 9: another move of the game
    words = re.findall(r"[а-яa-z'-]+", re.sub(r"(?<![0-9])\d{1,3}\s?(?:\.\.\.|…|\.)", " ", gap.lower().replace("ё", "е")))
    return len(words) <= 6 and all(_WORD_GAP_OK.fullmatch(w) for w in words)


# A move left for later by what follows it in the sentence (review-fp 02.11): «Поставь ладью на e1 после рокировки»,
# «Ставь ладью на e1, когда рокируешься», «…, как только уйдут конь и ферзь», «…, но сначала уведи коня».
_WORD_LATER = re.compile(
    r"(?<![а-яa-z])(?:если|когда|после|как\s+только|пока|потом|затем|позже|позднее|со\s+временем|в\s+будущем|"
    r"в\s+дальнейшем|впоследствии|через\s+(?:\w+\s+)?ход\w*|сначала|сперва|прежде|перед\s+этим|до\s+этого|"
    r"следующим\s+ходом|на\s+следующем\s+ходу|if|when|after|once|later|first|before|until|as\s+soon\s+as|"
    r"next\s+move)(?![а-яa-z])", re.IGNORECASE)
# A route after the square («перевести коня на g3 через d2 и f1»): a manoeuvre of several moves, not one move.
_WORD_ROUTE = re.compile(r"\s*,?\s*(?:[—–-]\s*)?(?:через|via|through)\s+(?:пол[еяю]\s+)?[a-h][1-8](?![0-9])", re.IGNORECASE)
# Verbs of a manoeuvre: «переведи коня на d3» may take more moves than one — only «it already stands there» and «there
# is no such piece» are judged for them (review-fp 02.11).
_WORD_MANOEUVRE = re.compile(
    r"(?<![а-яa-z])(?:перевести|переведи(?:те)?|перевед[её](?:м|шь)|переставить|переставь(?:те)?|переставим|"
    r"перебросить|перебрось(?:те)?|перебросим|перестроить|маневр\w*|манёвр\w*|regroup\w*|reroute|manoeuvre|maneuver|"
    r"transfer)(?![а-яa-z])", re.IGNORECASE)
_WORD_STEP_CASTLE = re.compile(r"(?<![а-яa-z])(?:рок[иеі]р\w*|castl\w*)|(?<![a-z0-9-])(?:o-o(?:-o)?|0-0(?:-0)?)(?![a-z0-9-])",
                               re.IGNORECASE)
# What a move told after another step («Рокируйся и ставь ладью на f1») is judged for on the board after that step: the
# other side's answer between them could change the rest.
_WORD_AFTER_STEP_KEEP = re.compile(r"already stands on|is occupied by \w+'s own|has no |there is no ")
_WORD_PLAY_VERB = re.compile(r"(?:сыграй(?:те)?|играй(?:те)?|сыграть|сыграем|play|try|go\s+for)$", re.IGNORECASE)
# The move first and its verb after it: «Конём на d3 сыграй», «Ферзём на d1 сходи».
_WORD_VERB_AFTER = re.compile(
    r"\s*(?:,\s*)?(?:сыграй(?:те)?|сходи(?:те)?|иди(?:те)?|пойди(?:те)?|ходи(?:те)?|ставь(?:те)?|поставь(?:те)?|двинь(?:те)?|"
    r"бей(?:те)?|бери(?:те)?|возьми(?:те)?)(?![а-яa-z])\s*[.!]*\s*$", re.IGNORECASE)
# A move alone as the sentence, said as advice: «Конём на e4!», «Теперь ферзём на d1.»
_WORD_BARE = re.compile(
    r"^\W*(?:(?:а|и|ну)\s+)?(?:теперь\s+|сейчас\s+|здесь\s+|тут\s+|просто\s+|сразу\s+)?"
    r"(?=(?:ладь[её]й|кон[её]м|слоном|ферз[её]м|корол[её]м|пешкой)\s+на\s+[a-h][1-8](?![0-9])\s*[.!]*\s*$)", re.IGNORECASE)
_WORD_SPOKEN_VERB = re.compile(r"(?:сыграть|сыграй|сыграем|сыграешь|пойти|пойди|пойд[её]м|пойд[её]шь|сходить|сходи|сходим|"
                               r"сходишь|ходи|иди|двинуть|двинь|двинем|двинешь|ход|ходом)$", re.IGNORECASE)
# A suggestion to the student opening the sentence («Может, конём на e4?», «Почему бы не …»), or the move named as the
# good one of the position («Хороший ход здесь — …»): with no other side named here or in the sentence before, its
# move is the side to move's. «Можно увести ферзя на a5», «Лучше ферзём на e6» stay either side's (the opening's
# theory of the other side's replies is told that way).
_WORD_SUGGEST_OPEN = re.compile(r"^\W*(?:а\s+)?(?:может(?:\s*,?\s*быть)?\s*,|почему\s+бы|как\s+насч[её]т|"
                                r"(?:здесь\s+|тут\s+|сейчас\s+)?(?:хорош|лучш|сильн|отличн)\w*\s+ход|"
                                # «Тут сильно пойти …», «Сейчас самое время пойти …», «Обрати внимание на ход …»: the board
                                # now, the side to move (review-miss 03.11)
                                r"(?:здесь|тут|сейчас|теперь)\s+(?:\w+\s+){0,2}?(?:пойти|сыграть|сходить|двинуть|поставить|"
                                r"продвинуть|взять|побить|забрать)|обрати(?:те)?\s+внимание\s+на\s+ход|"
                                r"(?:отличн|хорош|сильн|интересн|лучш)\w*\s+(?:идея|план|вариант|продолжение)\s*[—–:])(?![а-яa-z])",
                                re.IGNORECASE)
# …and in a game on the student's turn, advice with a verb of playing («Стоит пойти конём на e4», «Лучше сыграть …»).
_WORD_ADVICE_PLAY = re.compile(r"(?<![а-яa-z])(?:стоит|лучше|можно|предлагаю|рекомендую|советую|надо|нужно|следует)(?![а-яa-z])"
                               r".*(?<![а-яa-z])(?:сыграть|пойти|сходить|ходить|двинуть|поставить|играть)(?![а-яa-z])",
                               re.IGNORECASE)
_EMPTY = re.compile(r"")
_SAN_PARTS = re.compile(r"(?P<p>[KQRBN])?(?P<ff>[a-h])?(?P<fr>[1-8])?(?P<x>x)?(?P<to>[a-h][1-8])(?:=[QRBN])?")


def _word_step_board(head: str, board: chess.Board) -> Optional[chess.Board]:
    """The board after the step *head* tells before the proposal («Рокируйся и …», «Сыграй конём на f3 и …»), with the
    same side to move again; None when the step is not one clear legal move (or is denied)."""
    from src.board_rules import castling_status
    from src.move_words import prose_moves

    low = head.lower().replace("ё", "е")
    castle = _WORD_STEP_CASTLE.search(low)
    words = [x for x in prose_moves(low, board) if x.get("move") is not None or x.get("note")]
    if bool(castle) == bool(words) or re.search(r"(?<![а-яa-z])(?:не|нельзя|без|до|перед|after|before|don'?t|not)\s+(?:\w+\s+)?$",
                                                 low[:castle.start()] if castle else low[:words[0]["at"]]):
        return None
    if castle:
        st = castling_status(board, board.turn)
        if re.search(r"длинн\w*|ферзев\w*|queenside|long|o-o-o|0-0-0", low):
            wings = ["O-O-O"]
        elif re.search(r"коротк\w*|королевск\w*|kingside|short|(?<![-0o])(?:o-o|0-0)(?!-)", low):
            wings = ["O-O"]
        else:
            wings = [w for w in ("O-O", "O-O-O") if st[w][0]]
        if len(wings) != 1 or not st[wings[0]][0]:
            return None
        rank = 0 if board.turn == chess.WHITE else 7
        move = chess.Move(chess.square(4, rank), chess.square(6 if wings[0] == "O-O" else 2, rank))
    else:
        if len(words) != 1 or words[0].get("move") is None:
            return None
        move = words[0]["move"]
    if move not in board.legal_moves:
        return None
    after = board.copy(stack=False)
    after.push(move)
    after.turn = board.turn
    after.ep_square = None
    return after


def _san_item(mv: "re.Match", board: chess.Board) -> Optional[dict]:
    """A written move that is no legal move on *board*, as the move reader's item: None when it is legal, ambiguous,
    a pawn capture or a move named only by part of its square of departure."""
    san = mv["san"]
    if san.startswith("O-O"):
        return {"san": san, "move": None, "note": None, "words": mv.group(0), "at": mv.start(), "castle": san}
    try:
        board.parse_san(san + (mv["check"] or ""))
        return None
    except chess.AmbiguousMoveError:
        return None
    except ValueError:
        pass
    parts = _SAN_PARTS.fullmatch(san)
    if parts is None or bool(parts["ff"]) != bool(parts["fr"]) or (not parts["p"] and (parts["x"] or parts["ff"])):
        return None
    ptype = {"K": chess.KING, "Q": chess.QUEEN, "R": chess.ROOK, "B": chess.BISHOP, "N": chess.KNIGHT}.get(parts["p"] or "",
                                                                                                      chess.PAWN)
    frm = chess.parse_square(parts["ff"] + parts["fr"]) if parts["ff"] else None
    return {"san": san, "move": None, "note": None, "words": mv.group(0), "at": mv.start(), "ptype": ptype,
            "to": chess.parse_square(parts["to"]), "from": frm, "capture": bool(parts["x"])}


def _opponent_named(t: str, ctx: CheckContext) -> bool:
    for s in _WORD_SIDE.finditer((t or "").lower().replace("ё", "е")):
        if s["o"]:
            return True
        if (s["w"] or s["b"]) and ctx.student_color is not None and (chess.WHITE if s["w"] else chess.BLACK) != ctx.student_color:
            return True
    return False


def _word_move_all(text: str, ctx: CheckContext) -> dict:
    """The word_move issues of *text* by detector: 'word_move' (a move told in words), 'word_move_san' (a written move
    after a proposal word), 'castle_advice' (castling proposed by the king's step or O-O). Computed once a sentence."""
    cached = getattr(ctx, "_word_move_cache", None)
    if cached is not None and cached[0] == text and cached[1] is ctx.current:
        return cached[2]
    out = {"word_move": [], "word_move_san": [], "castle_advice": []}
    try:
        _word_move_read(text, ctx, out)
    finally:
        try:
            ctx._word_move_cache = (text, ctx.current, out)
        except Exception:  # noqa: BLE001
            pass
    return out


def _word_move_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx is None or ctx.current is None or not text.strip():
        return []
    return _word_move_all(text, ctx)["word_move"]


def _word_move_san_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx is None or ctx.current is None or not text.strip():
        return []
    return _word_move_all(text, ctx)["word_move_san"]


def _castle_word_move_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx is None or ctx.current is None or not text.strip():
        return []
    return _word_move_all(text, ctx)["castle_advice"]


def _word_move_read(text: str, ctx: CheckContext, out: dict) -> None:
    board = ctx.current
    if _DENIES.search(text) or _CONTINUES.match(text):
        return
    from src.board_rules import castling_status
    from src.claim_rules import prevention_frame
    from src.move_words import file_pushes, prose_moves, why_no_push, why_not

    frames = [(m, "frame") for m in list(_PROPOSES.finditer(text)) + list(_WORD_PROPOSES.finditer(text))]
    # the move alone as the sentence («Конём на e4!»), or before its verb («Конём на d3 сыграй») — review-miss 02.11 #4
    for st in [0] + [x.end() for x in re.finditer(r"[.!?;\n]\s*", text)]:
        if _WORD_BARE.match(text, st):
            frames.append((_EMPTY.match(text, _WORD_BARE.match(text, st).end()), "bare"))
        else:
            lead = re.match(r"\W*(?:(?:а|и|ну)\s+)?(?:теперь\s+|сейчас\s+|здесь\s+|тут\s+|просто\s+|сразу\s+)?", text[st:])
            frames.append((_EMPTY.match(text, st + lead.end()), "after"))
    frames.sort(key=lambda x: (x[0].start(), -x[0].end()))
    prev = getattr(ctx, "sentence_before", "") or ""
    done_to = -1
    for m, kind in frames:
        if m.start() < done_to:
            continue
        sent_start = max(text.rfind(c, 0, m.start()) for c in ".;!?\n") + 1
        clause_start = max([text.rfind(c, 0, m.start()) for c in ".;:!?\n—–(,"]) + 1
        head = text[sent_start:m.start()]
        if kind == "frame" and (_NEGATION.search(text[max(0, m.start() - 24): m.start()]) or _not_a_proposal(text, m)
                                or prevention_frame(text[:m.start()]) or _PAST_ADVICE.search(text[clause_start: m.end() + 16])):
            continue
        if _WORD_LINE.search(head) or any(mv["num"] or mv["bdots"] or mv["san"][0] in "KQRBNO" or "x" in mv["san"]
                                          for mv in _MOVE.finditer(_to_san(head)[0])):
            continue  # a step of a line: judged on the line's board, which is not this one
        # a step told in words before the proposal («Рокируйся и ставь ладью на e1»): the move is judged after it
        step = None
        if head.strip() and (_WORD_STEP_CASTLE.search(head) or prose_moves(head, board)):
            step = _word_step_board(head, board)
            if step is None:
                continue
        judge = step if step is not None else board
        clause = text[m.end():]
        end = _PROPOSAL_END.search(clause)
        stop_at = end.start() if end else len(clause)
        clause = clause[:stop_at][:120]
        found = sorted(prose_moves(clause, judge) + file_pushes(clause, judge), key=lambda x: x["at"])
        if kind == "frame" and _WORD_TAKE.match(m.group(0).strip()):
            # «Возьми конём ферзя на d8», «Забери ладью a8 слоном»: the take verb is the frame — read the capture with it,
            # or the piece taken («ферзя на d8») is read as the one that moves (review-miss 03.11)
            whole = _with_frame_verb(m.group(0), clause, judge)
            if whole is not None:
                found = [whole] + [x for x in found if x["at"] >= whole["at"] + len(whole["words"])]
        if kind == "frame":
            noun = _noun_frame_item(m.group(0), clause, judge)
            if noun is not None:
                found = [noun] + [x for x in found if x["at"] > noun["at"] + len(noun["words"])]
        if kind == "after":
            found = [x for x in found if x["at"] == 0 and "to" in x and _WORD_VERB_AFTER.match(clause[len(x["words"]):] + text[m.end() + stop_at:m.end() + stop_at + 1])]
            if not found:
                continue
        if not found and kind == "frame" and _WORD_SPOKEN_VERB.search(m.group(0).strip()):
            # «Сыграй ферзём d1», «Сходи пешкой d3»: the frame is the verb the spoken reading needs (review-miss #12)
            off = len(m.group(0)) + 1
            for x in prose_moves(m.group(0) + " " + clause, judge):
                end_p = x["at"] + len(x["words"])
                if end_p > off:
                    x = dict(x, at=max(0, x["at"] - off))
                    x["words"] = clause[x["at"]:end_p - off]
                    found.append(x)
        sans = []
        if not found and kind == "frame":
            conv = _to_san(clause)[0]
            for mv in _MOVE.finditer(conv):
                if mv["num"] and (int(mv["num"]) != judge.fullmove_number
                                  or (mv["dots"] == ".") != (judge.turn == chess.WHITE)):
                    break
                if mv["bdots"] and judge.turn == chess.WHITE:
                    break
                if mv["san"][0] not in "KQRBNO" and not (mv.start() == 0 or not conv[:mv.start()].strip()) \
                        or (mv["san"][0] not in "KQRBNO" and not _WORD_PLAY_VERB.search(m.group(0).strip())):
                    break  # «e4» is a square unless it follows a verb of playing right away
                item = _san_item(mv, judge)
                if item is not None:
                    sans.append(item)
                break
            found = sans
            if sans:
                clause = conv  # the written move's offsets are the converted text's
        if not found:
            continue
        first = found[0]
        gap = clause[: first["at"]]
        if not _word_gap_ok(gap, board) or _WORD_LINE.search(gap):
            continue
        if "file" in first and not _PUSH_WORD.search(m.group(0) + " " + gap):
            continue
        # whose move: a side named before the move, else the student (the side to move outside a game)
        side = student_side(ctx, text)
        named = list(_WORD_SIDE.finditer(text[sent_start: m.end()] + " " + gap))
        if named:
            last = named[-1]
            if last["me"]:
                continue  # «давай я пойду ферзём…»: the coach's own move in a game
            if not last["you"]:
                side = chess.WHITE if last["w"] else chess.BLACK if last["b"] else (
                    None if ctx.student_color is None else not ctx.student_color)
        if side is None or side != board.turn:
            continue
        # a question is judged only as a suggestion («Может, пойдёшь ферзём на d1?»)
        tail = text[m.end() + stop_at:]
        sentence_end = re.search(r"[.!?\n]", tail)
        if (sentence_end and sentence_end.group(0) == "?") and not _SUGGEST_Q.match(text[sent_start:]):
            continue
        # the move in its alternatives: «ферзём на d1 или конём на f3»
        chain = [first]
        for nxt in found[1:]:
            between = clause[chain[-1]["at"] + len(chain[-1]["words"]): nxt["at"]].lower()
            if re.fullmatch(r"\s*,?\s*(?:или|либо|or)\s+(?:же\s+)?(?:(?:пойти|сходить|сыграть|двинуть|поставить)\s+)?", between):
                chain.append(nxt)
            else:
                break
        frame_words = m.group(0) + " " + gap
        take = bool(_WORD_TAKE.search(frame_words))
        put = bool(_WORD_PUT.search(frame_words))
        manoeuvre = bool(_WORD_MANOEUVRE.search(frame_words))
        # «Можно увести ферзя на a5», «лучше конём на c6» name no side: the other side's piece may be meant (after a
        # reply) — a move the other side could make is judged only when a side is named or the student is addressed
        # (an imperative, «давай», «ты», "you": the student, the side to move outside a game — student_side). In a game
        # on the student's turn, or a sentence opening as a suggestion, the move is the student's unless the other side
        # is named here or in the sentence before (review-miss 02.11 #6).
        either = not named and not _WORD_ADDRESSED.search(frame_words) and kind != "after" and kind != "bare"
        if either and not _opponent_named(text[sent_start:], ctx) and not _opponent_named(prev, ctx) \
                and (_WORD_SUGGEST_OPEN.match(text[sent_start:])
                     or (ctx.student_color is not None and ctx.student_color == board.turn
                         and _WORD_ADVICE_PLAY.search(frame_words))):
            either = False
        sentence_rest = re.split(r"[.!?\n]", text[m.end():], maxsplit=1)[0]
        for item in chain:
            if _WORD_ACCUSATIVE.match(item["words"]) and not take and not put and not item.get("noun_frame") \
                    and not _WORD_PUT.match(clause[item["at"] + len(item["words"]):]):
                continue  # «Лучше ладью на a1 пока не трогать»: the object of another verb, not a piece told to go there
            item_end = item["at"] + len(item["words"])
            if _WORD_ROUTE.match(clause[item_end:]) or _WORD_ROUTE.match(sentence_rest[item_end:]):
                continue  # «перевести коня на g3 через d2 и f1»: a manoeuvre's route
            phrase = clause[item["at"]: item_end].strip()
            bucket = "word_move_san" if item in sans else "word_move"
            if item.get("castle") or (item.get("ptype") == chess.KING and item.get("move") is None and "to" in item
                                      and _king_castles(judge, item)):
                wing = item.get("castle") or ("O-O" if chess.square_file(item["to"]) == 6 else "O-O-O")
                legal, why = castling_status(judge, judge.turn)[wing]
                if legal or _WORD_LATER.search(sentence_rest[item_end:]):
                    continue
                if step is not None or (not getattr(ctx, "game_moves", None) and ctx.student_color is None
                                        and "right to castle is lost" in why):
                    continue  # the rights of a set-up FEN are no evidence; after another step: not judged
                out["castle_advice"].append(f"«{phrase}» proposes castling ({wing}) that cannot be played on the board now "
                                            f"({'White' if judge.turn else 'Black'} to move): {why}")
                continue
            why = _word_move_why(item, judge, ctx, clause, why_not, why_no_push, take)
            taking = take or bool(_WORD_TAKE.match(item["words"]))
            if why and either and "to" in item and not (taking and judge.piece_at(item["to"]) is None):
                # (a capture on an empty square: the other side has nothing to take there either)
                flipped = judge.copy(stack=False)
                flipped.turn = not judge.turn
                if why_not(flipped, item["ptype"], item["to"], item.get("from"), item.get("capture", False) or take) is None:
                    continue
            if not why:
                continue
            if _WORD_LATER.search(sentence_rest[item_end:]):
                continue  # «Поставь ладью на e1 после рокировки», «…, когда рокируешься»: a move for later
            if manoeuvre and re.search(r"can reach .* in one move|the way of the .* is blocked", why):
                continue  # «переведи коня на d3»: a manoeuvre may take several moves to get there
            if step is not None and not _WORD_AFTER_STEP_KEEP.search(why):
                continue
            where = " after the step told before it" if step is not None else ""
            out[bucket].append(f"«{phrase}» proposes a move that cannot be played on the board{where} now "
                               f"({'White' if board.turn else 'Black'} to move): {why}")
        done_to = m.end() + stop_at


# «Хороший ход — пешка на e4», «Лучший ход — ферзь с d8 на b8», «Хороший план: конь на h7»: after a frame that names a
# move by a noun and a dash or colon, a piece in the nominative with its square is the move itself — not a piece standing
# there (review-miss 03.11: 0/5 «пешка на», 2/12 «<piece> [с X] на Y» caught).
_NOUN_FRAME_END = re.compile(r"(?<![а-яa-z])(?:ход|вариант|продолжение|идея|план|решение|выбор|ответ)\s*$", re.IGNORECASE)
_NOUN_FRAME_ITEM = re.compile(
    r"^\s*[—–:-]\s*(?:это\s+)?(?P<piece>ладья|конь|слон|ферзь|король|пешка|ладью|коня|слона|ферзя|короля|пешку)"
    r"(?:\s+(?:с|из)\s+(?P<frm>[a-h][1-8]))?\s+(?:на|в)\s+(?:пол[ея]\s+)?(?P<to>[a-h][1-8])(?![0-9])", re.IGNORECASE)


def _noun_frame_item(frame: str, clause: str, board: chess.Board) -> Optional[dict]:
    """The move a move-noun frame names in the nominative or the accusative right after its dash, as a prose_moves item
    (nominative False: it is a move, every reason it cannot be played is judged), or None."""
    from src.move_words import _ptype, resolve

    if not _NOUN_FRAME_END.search(frame.rstrip()):
        return None
    m = _NOUN_FRAME_ITEM.match(clause.replace("ё", "е").lower())
    if not m:
        return None
    ptype = _ptype(m["piece"])
    if ptype is None:
        return None
    to = chess.parse_square(m["to"])
    frm = chess.parse_square(m["frm"]) if m["frm"] else None
    san, move, note = resolve(board, ptype, to, from_sq=frm)
    at = m.start("piece")
    return {"san": san, "move": move, "note": note, "words": clause[at:m.end()].strip(), "at": at, "ptype": ptype,
            "to": to, "from": frm, "capture": False, "nominative": False, "noun_frame": True}


def _with_frame_verb(frame: str, clause: str, board: chess.Board) -> Optional[dict]:
    """The move read with the frame's own verb in front («Возьми» + « конём ферзя на d8»), as an item of *clause*
    (its offsets and words the clause's), when it starts at the verb and reaches into the clause; else None."""
    from src.move_words import prose_moves

    off = len(frame) + 1
    for x in prose_moves(frame + " " + clause, board):
        end_p = x["at"] + len(x["words"])
        if x["at"] == 0 and end_p > off:
            return dict(x, at=0, words=clause[: end_p - off])
    return None


# ── A check claimed (review-miss 03.11, check_claim) ─────────────────────────────────────────────────────────────────
# «Конём на g4 — шах», «Иди ладьёй на b1 с шахом», «Ход Na5 объявляет шах королю», «После хода ферзём на c7 королю
# соперника шах»: a move of the side to move (in words or notation) with a check bound to it in the same clause — judged
# by board.gives_check, as «+» in SAN is. «Внимание: тебе шах» — the board now, for the side addressed. Not judged: a
# condition or a question, a denial («не даёт шаха», «без шаха»), a line of several moves, rule talk (hidden before).
_CHECK_AFTER_MOVE = re.compile(
    r"^(?P<gap>(?:\s*[—–:,-]\s*|\s+)(?:(?:и|а|то)\s+)?(?:это\s+)?(?:(?:сразу|тоже|будет|уже)\s+)?"
    r"(?:(?:королю|корол[юя]\s+соперника|соперник[уа]|ч[её]рным|белым|тебе|ему)\s+)?(?:(?:объявля\w*|объяв\w*|да[её]т|даст|"
    r"дают|ставит|поставит|будет)\s+)?(?:(?:королю|соперник[уа]|ч[её]рным|белым)\s+)?)(?P<pred>шах|с\s+шахом)(?![а-я])",
    re.IGNORECASE)
_CHECK_NOW_YOU = re.compile(r"(?<![а-яa-z])(?:тебе|вам)\s+(?:сейчас\s+|уже\s+|теперь\s+)?(?:объявлен\s+|поставлен\s+)?шах(?![а-я])",
                            re.IGNORECASE)
_CHECK_HYPO = re.compile(r"(?<![а-яa-z])(?:если|бы|когда|может|могут|можешь|сможешь|был\s+бы|иначе|грозит|угроза|угрожа\w*|"
                         r"хочет|хотят|пытается|правило|правилам|нельзя|if|would|could)(?![а-яa-z])", re.IGNORECASE)


_CHECK_FORCED = re.compile(r"(?<![а-яa-z])(?:вынужд\w*|придется|придётся|приходится|обязан\w*|forced|has\s+to|must)(?![а-яa-z])",
                           re.IGNORECASE)


def _check_claim_issues(text: str, ctx: CheckContext) -> list[str]:
    board = ctx.current
    if board is None or "шах" not in text.lower() or "?" in text or _DENIES.search(text) or _CHECK_HYPO.search(text):
        return []
    from src.move_words import prose_moves

    low = text.replace("ё", "е")
    told = []  # (start, end, move) of the moves of the side to move the sentence names
    for pm in prose_moves(low, board):
        at = low.lower().find(pm["words"].lower(), max(0, pm.get("at", 0) - 2))
        if at >= 0:
            told.append((at, at + len(pm["words"]), pm["move"]))
    for rx in (_TOLD_WITH, _TOLD_GOES):
        for m in rx.finditer(low.lower()):
            if not any(a <= m.start() < b for a, b, _ in told):
                from src.move_words import _ptype, resolve

                ptype = _ptype(m["piece"])
                if ptype is not None:
                    told.append((m.start(), m.end(), resolve(board, ptype, chess.parse_square(m["to"]))[1]))
    converted, _ = _to_san(low)
    for m in _MOVE.finditer(converted):
        san = m["san"]
        if san[0] not in "KQRBNO" and "x" not in san and not re.search(r"(?:ход\w*|пешк\w*)\s+$", converted[:m.start()]):
            continue
        if m["check"]:
            return []  # «Bb5+»: the written mark is judged by the SAN check already — one verdict, not two
        try:
            told.append((m.start(), m.end(), board.parse_san(san)))
        except ValueError:
            told.append((m.start(), m.end(), None))
    told.sort(key=lambda t: t[0])
    if len(told) > 1:
        return []  # a line of moves: whose check is not read here
    if not told:
        m = _CHECK_NOW_YOU.search(low)
        if m is None or _NEGATION.search(low[max(0, m.start() - 12): m.start()]):
            return []
        student = student_side(ctx, text)
        if student is None:
            return []
        if board.turn == student and board.is_check():
            return []
        side = "White" if student == chess.WHITE else "Black"
        return [f"{side}'s king is not in check on the board now"]
    start, end, move = told[0]
    if move is None or move not in board.legal_moves:
        return []  # a move that cannot be played: word_move's to say
    if _CHECK_FORCED.search(low[:end]):
        return []  # «Конь вынужден уйти на g5 с шахом»: a reply forced in a line, not the move now
    after = low[end:]
    m = _CHECK_AFTER_MOVE.match(after)
    if m is None or _NEGATION.search(m["gap"] + " "):
        return []
    if board.gives_check(move):
        return []
    san = board.san(move)
    if board.is_checkmate() or san.endswith("#"):
        return []
    return [f"{san} gives no check: after it the {'black' if board.turn == chess.WHITE else 'white'} king is not attacked"]


# ── A material claim with no amount (review-miss 03.11, material_direction) ─────────────────────────────────────────
_MAT_DIR_SIDE = r"(?P<side>ты|вы|я|белые|черные|соперник|противник)"
_MAT_DIRECTION = [
    ("behind", re.compile(r"(?<![а-я])" + _MAT_DIR_SIDE + r"\s+(?:сейчас\s+|пока\s+|уже\s+|теперь\s+)?(?:отста(?:ешь|ете|ют|ет)|"
                          r"уступа(?:ешь|ете|ют|ет))\s+по\s+материалу(?![а-я])")),
    ("ahead", re.compile(r"(?<![а-я])" + _MAT_DIR_SIDE + r"\s+(?:сейчас\s+|пока\s+|уже\s+|теперь\s+)?(?:впереди|опережа(?:ешь|ете|ют|ет)|"
                         r"вед(?:ешь|ете|ут|ет))\s+по\s+материалу(?![а-я])")),
    ("equal", re.compile(r"(?<![а-я])материал\w*\s+(?:сейчас\s+|пока\s+|на\s+доске\s+)?(?:равн(?:ый|ы|ое)|равен|одинаков\w*|поровну)(?![а-я])")),
    ("unequal", re.compile(r"(?<![а-я])материал\w*\s+(?:сейчас\s+|пока\s+|на\s+доске\s+)?(?:не\s+равн(?:ый|ы|ое)|не\s+равен|неравн\w*)(?![а-я])")),
    ("exchange_down", re.compile(r"(?<![а-я])" + _MAT_DIR_SIDE + r"\s+(?:уже\s+)?(?:потерял\w*|отдал\w*)\s+качество(?![а-я])")),
    ("exchange_up", re.compile(r"(?<![а-я])" + _MAT_DIR_SIDE + r"\s+(?:уже\s+)?(?:выиграл\w*|забрал\w*)\s+качество(?![а-я])")),
]
_MAT_DIR_HYPO = re.compile(r"(?<![а-я])(?:если|бы|после|когда|станешь|будешь|будет|будут|окажешься|можешь|может|рискуешь|"
                           r"иначе|then|if)(?![а-я])")
_MAT_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def _material_direction_issues(text: str, ctx: CheckContext) -> list[str]:
    board = ctx.current
    if board is None or "материал" not in text and "качество" not in text or "?" in text or _MAT_DIR_HYPO.search(text):
        return []

    def total(color):
        return sum(v * len(board.pieces(t, color)) for t, v in _MAT_VALUE.items())

    for kind, rx in _MAT_DIRECTION:
        for m in rx.finditer(text):
            if _NEGATION.search(text[max(0, m.start() - 14): m.start() + len(m.groupdict().get("side") or "") + 1]) \
                    or re.search(r"(?<![а-я])не\s+(?:отста|уступа|впереди|опережа|вед|потерял|отдал|выиграл|забрал)",
                                 m.group(0)):
                continue
            side_word = m.groupdict().get("side")
            color = None
            if side_word in ("ты", "вы"):
                color = student_side(ctx, text)
            elif side_word == "я":
                color = None if ctx.student_color is None else not ctx.student_color
            elif side_word in ("соперник", "противник"):
                st = student_side(ctx, text)
                color = None if st is None else not st
            elif side_word:
                color = chess.WHITE if side_word.startswith("бел") else chess.BLACK
            if side_word and color is None:
                continue
            if kind in ("equal", "unequal"):
                diff = total(chess.WHITE) - total(chess.BLACK)
                if (kind == "equal") == (diff == 0):
                    continue
                return [f"the material is {'equal' if diff == 0 else 'not equal'} on the board now (White {total(chess.WHITE)}, "
                        f"Black {total(chess.BLACK)} in pawn units)"]
            mine, theirs = total(color), total(not color)
            side = "White" if color == chess.WHITE else "Black"
            if kind == "behind" and mine < theirs or kind == "ahead" and mine > theirs:
                continue
            if kind in ("behind", "ahead"):
                return [f"{side} is {'ahead' if mine > theirs else 'level' if mine == theirs else 'behind'} in material on the "
                        f"board now ({side} {mine}, the other side {theirs} in pawn units)"]
            rooks = len(board.pieces(chess.ROOK, color)) - len(board.pieces(chess.ROOK, not color))
            minors = (len(board.pieces(chess.KNIGHT, color)) + len(board.pieces(chess.BISHOP, color))
                      - len(board.pieces(chess.KNIGHT, not color)) - len(board.pieces(chess.BISHOP, not color)))
            down = rooks < 0 and minors > 0
            up = rooks > 0 and minors < 0
            if (kind == "exchange_down" and down) or (kind == "exchange_up" and up):
                continue
            return [f"{side} has not {'lost' if kind == 'exchange_down' else 'won'} the exchange: the rooks are "
                    f"{len(board.pieces(chess.ROOK, color))} against {len(board.pieces(chess.ROOK, not color))}, the minor pieces "
                    f"{len(board.pieces(chess.KNIGHT, color)) + len(board.pieces(chess.BISHOP, color))} against "
                    f"{len(board.pieces(chess.KNIGHT, not color)) + len(board.pieces(chess.BISHOP, not color))}"]
    return []


def _king_castles(board: chess.Board, item: dict) -> bool:
    """«королём на g1» from e1: castling told as the king's step."""
    rank = 0 if board.turn == chess.WHITE else 7
    home = chess.square(4, rank)
    if board.piece_at(home) != chess.Piece(chess.KING, board.turn) or item.get("from") not in (None, home):
        return False
    return item["to"] in (chess.square(6, rank), chess.square(2, rank))


def _word_move_why(item: dict, board: chess.Board, ctx: CheckContext, clause: str, why_not, why_no_push,
                   take: bool = False) -> Optional[str]:
    if (take or _WORD_TAKE.match(item["words"])) and _WORD_OBJECT.search(item["words"]) \
            and not _WORD_INSTRUMENT.search(item["words"]):
        return None  # «возьми коня на d4», "take the knight on d4": the piece named is the one taken, not the mover
                     # (with the mover named too — «возьми конём ферзя на d8», «забери ладью a8 слоном» — it is judged)
    # «Давай возьмём конём на e5», «Я бы побил ферзём на f6»: the capture is told by the move's own words
    take = take or bool(_WORD_TAKE.match(item["words"]))
    if take and "to" in item and item.get("move") is not None and not board.is_capture(item["move"]) \
            and board.piece_at(item["to"]) is None:
        return f"there is nothing to take on {chess.square_name(item['to'])}"
    if item.get("move") is not None or (item.get("note") and "ambiguous" in item["note"]) \
            or (item.get("note") and "more than one" in item["note"]):
        return None  # playable (by one piece or several)
    after = clause[item["at"] + len(item["words"]):]
    if _WORD_KEEP_AFTER.match(after):
        return None  # «лучше ферзя на d1 оставить», «ферзём на d1 не ходи»
    if "file" in item:
        why = why_no_push(board, item["file"])
        return why if item.get("pushes", 0) == 0 else None
    if "to" not in item:
        note = item.get("note") or ""
        return note if note.startswith("there is no ") else None
    why = why_not(board, item["ptype"], item["to"], item.get("from"), item.get("capture", False) or take)
    if why is None:
        return None
    if item.get("nominative") and not re.match(r"(?:white|black) has no ", why, re.IGNORECASE):
        return None  # «лучше ферзь на d1» may name where the queen stands, or a plan in more moves than one
    # Another position the turn has as a position (the student's idea, a board a tool showed) or the line the sentence
    # before wrote: a move legal there may be meant there — not judged. The game's history (its earlier positions) and
    # the start position standing in for an unknown one are not such positions.
    others = [b for b in ctx.boards if b is not board and ctx._key(b) in ctx.state_keys
              and b.board_fen() != chess.STARTING_BOARD_FEN]
    scene = getattr(ctx, "scene", None)
    if scene is not None and getattr(ctx, "scene_age", 9) <= 1:
        others.append(scene)
    for other in others:
        trial = other.copy(stack=False)
        trial.turn = board.turn
        if why_not(trial, item["ptype"], item["to"], item.get("from"), item.get("capture", False)) is None:
            return None
    return why


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


# ── The game's own record (plan 31.10, P1: M3 student_capture, M4 block_kind, M6 free_capture, M7 gave_up) ──────────
# Each judges a claim about the game on the board against its score (src/game_record.py) and names the true fact.
_COLOR_EN = {chess.WHITE: "White", chess.BLACK: "Black"}
from src.claim_scope import NOW as _NOW_WORD  # noqa: E402


def _owner_words(ctx: CheckContext, color: bool, possessive: bool = False) -> str:
    """«White (the engine)», «Black's (the student's)»: a colour and who plays it in this game."""
    student = getattr(ctx, "student_color", None)
    s = "'s" if possessive else ""
    if student is None:
        return _COLOR_EN[color] + s
    return f"{_COLOR_EN[color]}{s} ({'the student' if color == student else 'the engine'}{s})"


# M3: «твоя пешка с f6 забрала слона на e7», «ты взял коня»: a capture called the student's must be one the student
# made in this game (prod st2#5 29.10: it was White's 5.fxe7, the engine's) — the mirror of _COACH_TOOK.
# Read as a frame (fix 01.11 F4): the CAPTURER with its OWNER — a possessive («твоя пешка»), a colour adjective («чёрная
# пешка») or genitive («пешка чёрных», «пешка f6 твоего цвета»), a relative clause about who moved it («пешка, которую
# ты двинул на f6»), or the subject itself (ты / белые / чёрные) — its square (from or to), a capture verb in the past,
# the instrument and the TARGET with its square; all compared with the game's record (src/game_record.captures).
_SC_PIECE = r"(?:пешк[аи]|кон[ьи]|слон(?:ы)?|ладь[яи]|ферзь|король)"
_SC_SQ = r"(?:\s+(?P<{p}>на|с|со|из)?\s*(?P<{s}>[a-h][1-8])(?![0-9]))?"
_STUDENT_TOOK = re.compile(
    r"(?<![а-яё])(?:(?:(?P<poss>тво(?:й|я|е|ё|и)|ваш(?:а|е|и)?)\s+(?P<p1>" + _SC_PIECE + r")"
    r"|(?P<adj>бел(?:ый|ая|ое|ые)|ч[её]рн(?:ый|ая|ое|ые))\s+(?P<p2>" + _SC_PIECE + r")"
    r"|(?P<p3>" + _SC_PIECE + r"))" + _SC_SQ.format(p="fp", s="from")
    + r"(?:\s+(?P<gen>белых|ч[её]рных|тво(?:его|ей)\s+цвета|ваш(?:его|ей)\s+цвета))?" + _SC_SQ.format(p="fp2", s="from2")
    + r"(?:\s*,\s*котор\w+\s+(?P<rel>ты|вы|белые|ч[её]рные)\s+(?:[а-яё]+\s+){0,2}?(?:двинул|продвинул|поставил|сыграл|"
    r"вывел|перев[её]л|переставил|отв[её]л)\w*(?:\s+(?:на|с)\s+(?P<relsq>[a-h][1-8]))?\s*,)?"
    r"|(?P<who>ты|вы|белые|ч[её]рные))\s+"
    r"(?:(?:только\s+что|уже|сразу|просто|тоже|сам|сама|сами|затем|потом|тут\s+же|ещ[её]\s+и|и)\s+){0,3}"
    r"(?P<verb>забрал\w*|побил\w*|взял\w*|съел\w*|сбил\w*|срубил\w*)\s+"
    rf"(?:(?P<inst>{_INSTR})(?:\s+(?P<isq>[a-h][1-8]))?\s+)?(?:(?:мо\w+|его|тво\w+|ваш\w+|ч[её]рн\w+|бел\w+)\s+)?"
    # the taken piece in the accusative only («взял конём пешку»: конём is the taker)
    r"(?P<target>пешку|пешки|коня|коней|слона|слонов|ладью|ладьи|ферзя)(?:\s+(?:на\s+)?(?P<tsq>[a-h][1-8])(?![0-9]))?"
    rf"(?:\s+(?P<inst2>{_INSTR})(?:\s+(?P<isq2>[a-h][1-8]))?)?(?![а-яё])", re.IGNORECASE)


def _capture_owner(m, ctx: CheckContext) -> tuple[Optional[bool], bool]:
    """(the colour the words give the capturer, whether they name the student) — (None, False) when no owner."""
    for word in (m["poss"], m["adj"], m["gen"], m["rel"], m["who"]):
        if not word:
            continue
        w = word.lower().replace("ё", "е")
        if w.startswith(("тво", "ваш", "ты", "вы")):
            return ctx.student_color, True
        return (chess.WHITE if w.startswith("бел") else chess.BLACK), False
    return None, False


def _student_capture_issues(text: str, ctx: CheckContext) -> list[str]:
    moves = getattr(ctx, "game_moves", None)
    if not moves or ctx.student_color is None or "?" in text or "«" in text or '"' in text:
        return []
    claims = [m for m in _STUDENT_TOOK.finditer(text) if not _NOT_TOLD.search(text[max(0, m.start() - 40):])
              and not _TOOK_IDIOM.match(text, m.end())]
    framed = _frame_take_issues(text, text, ctx, [(m.start(), m.end()) for m in _STUDENT_TOOK.finditer(text)]
                                + [(m.start(), m.end()) for m in _COACH_TOOK.finditer(text)])
    if not claims:
        return framed
    from src.game_record import _players, captures

    caps = captures(ctx)
    converted, _ = _to_san(text)
    played = {str(x).rstrip("+#") for x in moves}
    in_a_line = any(x["san"].rstrip("+#") not in played for x in _MOVE.finditer(converted)
                    if x["num"] or x["bdots"] or x["san"][0] in "KQRBNO" or "x" in x["san"])
    out = []
    for m in claims:
        color, students = _capture_owner(m, ctx)
        if color is None:
            continue
        if not students and (in_a_line or _players(ctx) or _OTHER_GAME.search(text)):
            continue  # a colour in a line or in a famous game: that line's capture, judged elsewhere
        piece = _took_type(m["p1"] or m["p2"] or m["p3"]) or _took_type(m["inst"]) or _took_type(m["inst2"])
        target = _took_type(m["target"])
        if target is None:
            continue
        # the capturer's squares: «с f6» / «из f6» is where it came from; «на e7», a bare «f6» where it stands, either
        named = [(m[s].lower(), (m[p] or "").lower()) for s, p in (("from", "fp"), ("from2", "fp2")) if m[s]]
        named += [(m[s].lower(), "с") for s in ("relsq", "isq", "isq2") if m[s]]

        def fits(c) -> bool:
            if c.captured != target or (m["tsq"] and chess.square_name(c.square) != m["tsq"].lower()):
                return False
            if piece is not None and piece != c.piece and not (c.piece == chess.PAWN and "=" in c.san):
                return False
            for sq, prep in named:
                where = {chess.square_name(c.from_square)} if prep in ("с", "со", "из") else \
                    {chess.square_name(c.from_square), chess.square_name(c.to_square)}
                if c.from_square < 0:  # a record without the from-square: the pawn's file
                    if c.piece == chess.PAWN and prep in ("с", "со", "из") and c.san[0].lower() != sq[0]:
                        return False
                    continue
                if sq not in where:
                    return False
            return True
        hits = [c for c in caps if fits(c)]
        owner = "the student" if students else _COLOR_EN[color]
        if hits and not any(c.mover == color for c in hits):
            c = hits[-1]
            out.append(f"{c.label} was {_owner_words(ctx, c.mover, True)} capture, not "
                       + (f"the student's — the student plays {_COLOR_EN[ctx.student_color]}" if students
                          else f"{_COLOR_EN[color]}'s")
                       + f": it took {'the student' + chr(39) + 's' if students else _owner_words(ctx, not c.mover, True)} "
                       f"{_NAMES.get(c.captured, 'pawn')} on "
                       f"{chess.square_name(c.square)}")
        elif not hits:
            what = _NAMES.get(target, "pawn") + (f" on {m['tsq']}" if m["tsq"] else "") \
                + (f" with a {_NAMES.get(piece, 'pawn')}" if piece else "")
            mine = [c.label for c in caps if c.mover == color]
            out.append(f"in this game {owner} never captured a {what}: {owner}'s captures so far are "
                       + (", ".join(mine) if mine else "none"))
    return out + framed


# M4: a block of the check claimed — «закрыться конём — Nxd8», «перекрыть шах ходом Bd2», «Шах можно перекрыть»,
# «Встань конём между ладьёй и королём», «Nxd8 — это заслон» — must be one on the board in check: a block lands between
# the checker and the king; it neither takes the checker nor moves the king (prod st2#8 29.10: Nxd8 takes the checking
# rook). Read by structure (F5 01.11): a block word (a reflexive verb, a transitive one with «шах»/«короля», the noun
# «заслон», «встать между … и королём»), the move bound to it (written after it, after «ходом», or as its subject
# before «— это заслон»), the piece it names (instrumental «конём», a subject «Конь может заслонить», «только …»), and
# its square («конём c6» the piece, «на d7» the target). A claim with no move is judged against the board's blocks.
# Not judged: a denial («закрыться нечем»), a question, a condition, the past.
# Only the forms that propose or claim a block to make (infinitive, imperative, 2nd person, future) — not the present of a
# piece already standing between («ферзь прикрывает короля от шахов по линии f», «Qf3+ перекрывает королю выход»: a
# description), and not «пешечный заслон» (a pawn shield).
_BLOCK_WORD = re.compile(
    r"(?<![а-яa-z])(?:"
    # every voice of the block lemmas (review-miss2 01.11: «шах закрывается ходом Bd7», «шах перекрывается конём»,
    # «конём c6 ты загораживаешь короля» were not read)
    r"(?P<refl>(?:за|пере|при)кр(?:ыться|ываться|ывайся|ывайтесь|ойся|ойтесь|оешься|оется|оются|ыл(?:ся|ась|ись)|"
    r"ывается|ываются|ываешься)"
    r"|заслон(?:иться|ись|итесь|ишься|ится|яться|яйся|яется|яешься)|загород(?:иться|ись|итесь|ишься|ится)|"
    r"загоражива(?:ться|йся|ешься|ется))"
    r"|(?P<trans>(?:за|пере|при)кр(?:ыть|ой|ойте|оешь|оет|ывать|ывай|ываешь|ывает)|заслон(?:ить|и|ите|ишь|ит|ять|яй|яешь|яет)|"
    r"загород(?:ить|и|ите|ишь|ит)|загоражива(?:ть|ешь|ет|й)|(?:за)?блокир(?:овать|уй|уйте|уешь|овав)|block(?![a-z]))"
    r"|(?P<noun>(?<!пешечн[ыо]м\s)(?<!пешечный\s)(?<!пешечного\s)заслон(?:ом|а|ы|е)?|перекрыти\w*|блокировк\w*|interpos\w*|"
    r"a\s+block)"
    r"|(?P<between>вста(?:ть|нь|ньте|нет|вать)|поставить|поставь|ставь|put|place))(?![а-яa-z])", re.IGNORECASE)
_BLOCK_OBJ = re.compile(r"(?<![а-яa-z])(?:шах\w*|корол[яю]|линию\s+шаха|от\s+шаха|check|the\s+king)(?![а-яa-z])", re.IGNORECASE)
_BLOCK_BETWEEN = re.compile(r"(?<![а-яa-z])(?:(?:между|between)(?![а-яa-z])[^.;!?]*?(?:корол\w*|king)|на\s+(?:е[её]\s+|его\s+)?пути|"
                            r"на\s+лини(?:ю|и)\s+шаха|in\s+the\s+way)", re.IGNORECASE)
# The object of a block verb that is the king's way out (fix1102 K2, verify1102 B2): «Qf3+ … перекрывает королю выход»,
# «закрыть королю поля отхода», «перекрытие путей отступления», "blocks the king's escape" — the side that gives the
# check takes the king's squares away; that is not the side in check putting a piece between. Up to three words of
# whose way it is before the noun («королю», «чёрному королю», «последний», "the king's") — not «слоном на поле d7».
_BLOCK_ESCAPE = re.compile(
    r"^\s*(?:(?:королю|ему|ей|ч[её]рному|белому|вражескому|неприятельскому|чужому|последн\w*|единственн\w*|вс[её]|"
    r"оба|обе|свободн\w*|запасн\w*|the|of|king'?s|its|his|her|enemy|black'?s|white'?s|all|last|only|remaining)\s+){0,3}"
    r"(?:выход\w*|отход\w*|отступлени\w*|бегств\w*|пут(?:ь|и|ей|ям|ях)|дорог[уиа]|"
    r"пол(?:е|я|ю|ей|ям|ях)|клет(?:ку|ки|ок|кам)|квадрат\w*|лазейк\w*|форточк\w*|escape\w*|flight|exit\w*|retreat\w*|"
    r"way\s+out|squares?)(?![а-яёa-z])", re.IGNORECASE)
_BLOCK_NOT = re.compile(r"(?<![а-яa-z])(?:не|ни|нельзя|нечем|некуда|невозможно|никак|cannot|can'?t|no\s+way|nothing)(?![а-яa-z])"
                        r"(?:\s+[а-яa-z]+){0,2}\s*$", re.IGNORECASE)
_BLOCK_NOT_AFTER = re.compile(r"^[^.;!?:—–]*?(?<![а-яa-z])(?:нельзя|нечем|некуда|невозможно|не\s+(?:получится|выйдет|удастся|"
                              r"может|можешь|могут|сможешь|сможет)|никак|не\s+чем)(?![а-яa-z])", re.IGNORECASE)
_BLOCK_PAST = re.compile(r"(?<![а-яa-z])(?:можно\s+было|надо\s+было|нужно\s+было|стоило|следовало|был[аио]?\s+бы|"
                         r"(?:за|пере|при)крыл\w*|заслонил\w*|загородил\w*|could\s+have|should\s+have|blocked)(?![а-яa-z])",
                         re.IGNORECASE)
_PIECE_INSTR = re.compile(
    r"(?<![а-яa-z])(?:(?P<only>только|лишь|only)\s+)?(?:(?P<ru>пешкой|кон[её]м|слоном|ладь[её]й|ферз[её]м|корол[её]м)"
    r"|with\s+(?:the\s+|a\s+|your\s+)?(?P<en>knight|bishop|rook|queen|pawn|king))(?:\s+(?P<sq>[a-h][1-8])(?![0-9]))?",
    re.IGNORECASE)
_PIECE_SUBJ = re.compile(r"(?<![а-яa-z])(?P<ru>пешка|конь|слон|ладья|ферзь|король)(?:\s+(?P<sq>[a-h][1-8]))?\s+"
                         r"(?:(?:может|можешь|могут|сможет|должен|должна|обязан\w*|способ\w*)\s+)?$", re.IGNORECASE)
_SAN_HERE = r"[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?"
_SAN_AFTER = re.compile(r"[^.;!?]*?(?:[:—–]|(?<![а-яa-z])(?:ходом|например|e\.g\.|with|by))\s*[*_]*(?P<san>" + _SAN_HERE
                        + r")(?![A-Za-z0-9])", re.IGNORECASE)
_SAN_BEFORE = re.compile(r"[*_]*(?P<san>" + _SAN_HERE + r")[+#]?[*_]*\s*(?:[—–:-]\s*)?(?:(?:это|is|—\s*это)\s+)?"
                         r"(?:(?:хороший|лучший|надежный|единственный|отличный|правильный|a|the)\s+)?$", re.IGNORECASE)
_PTYPE_WORD = {"пешк": chess.PAWN, "кон": chess.KNIGHT, "слон": chess.BISHOP, "ладь": chess.ROOK, "ферз": chess.QUEEN,
               "корол": chess.KING, "pawn": chess.PAWN, "knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK,
               "queen": chess.QUEEN, "king": chess.KING}


def _ptype_word(word: Optional[str]) -> Optional[int]:
    w = (word or "").lower()
    return next((t for stem, t in _PTYPE_WORD.items() if w.startswith(stem)), None)


# A bare square right after a piece noun («от слона b4», «шах ферзём e4»), after «с/со/от/из/на», or after «шах(ом)» names
# a piece or a place, never a pawn move (review fp2 01.11: «Тебе шах от слона b4: закройся …» bound b4 as the block).
_NOUN_BEFORE_SQ = re.compile(r"(?<![а-яa-z])(?:(?:пешк|кон|слон|ладь|ферз|корол|фигур)[а-яё]*|шах\w*|check|"
                             r"с|со|от|из|на|по|у|под|над|between|from|on|by|of|the|a|bishop|knight|rook|queen|king|pawn)"
                             r"\s+$", re.IGNORECASE)


def _square_of_noun(text: str, m) -> bool:
    san = m["san"]
    if not re.fullmatch(r"[a-h][1-8]", san or ""):
        return False
    return bool(_NOUN_BEFORE_SQ.search(text[: m.start("san")].rstrip("*_ ") + " "))


def _block_claims(conv: str) -> list:
    """The block claims of *conv*: dicts with the move bound (san), the piece named (ptype, from, only), the target."""
    out = []
    for m in _BLOCK_WORD.finditer(conv):
        cs = max(conv.rfind(c, 0, m.start()) for c in ".;!?\n") + 1
        ends = [i for i in (conv.find(c, m.end()) for c in ".;!?\n") if i >= 0]
        ce = min(ends) if ends else len(conv)
        # the dots of «3...Bd7» do not end the clause
        while ce < len(conv) and conv[ce] == "." and re.match(r"\.{0,2}[KQRBNa-h]|\d", conv[ce + 1:ce + 3] or ""):
            nxt = [i for i in (conv.find(c, ce + 3) for c in ".;!?\n") if i >= 0]
            ce = min(nxt) if nxt else len(conv)
        before, after = conv[cs: m.start()], conv[m.end(): ce]
        near = conv[max(cs, m.start() - 30): m.start()] + " " + after[:30]
        if m["trans"] and not _BLOCK_OBJ.search(near):
            continue  # «закрыть диагональ», «прикрыть f1»: not the check
        if m["trans"] and m["trans"].lower().startswith("прикр") and not re.search(
                r"(?<![а-яa-z])(?:от\s+шаха|шах\w*|check)(?![а-яa-z])", near) and not (
                re.search(r"(?<![а-яa-z])корол[яю](?![а-яa-z])", near) and (_PIECE_INSTR.search(after[:30])
                                                                     or _SAN_AFTER.match(after))):
            continue  # «прикрыть короля»: shelter in general, not a block of this check (but «прикрыть короля конём»)
        if m["noun"] and not re.search(r"(?<![а-яa-z])(?:от\s+шаха|шах\w*|check)(?![а-яa-z])", near) \
                and not (_PIECE_INSTR.search(after[:30]) or re.match(r"\s*(?:[:—–]\s*)?[*_]*(?:" + _SAN_HERE + r")(?![A-Za-z0-9])",
                                                                     after)):
            continue  # «блокировка пешки», «зажат своим заслоном»: not a block of the check (but «заслон: Nxd8»)
        if m["between"] and not _BLOCK_BETWEEN.search(after):
            continue
        if (m["trans"] or m["noun"]) and _BLOCK_ESCAPE.match(after):
            continue  # «Qf3+ … перекрывает королю выход»: the checker cuts the king off — not a block of the check
        clause = conv[cs: ce]
        if re.search(r"(?<![а-яa-z])(?:чтобы|дабы|so\s+that|in\s+order\s+to|подума\w*|посмотр\w*|найди\w*|поищи\w*|"
                     r"think|look\s+for|find)(?![а-яa-z])", before):
            continue  # a purpose or a hint («…, чтобы заодно прикрыть короля», «Подумай, как закрыться»): no claim
        if "?" in conv[m.start(): ce + 1] or _BLOCK_NOT.search(before) or _BLOCK_NOT_AFTER.match(after) \
                or _BLOCK_PAST.search(clause) \
                or (_HYPO.search(before.lower()) and not _NOW_WORD.search(before.lower())):
            continue
        claim = {"at": m.start(), "san": None, "ptype": None, "from": None, "to": None, "only": False}
        sa = _SAN_AFTER.match(after)
        sb = _SAN_BEFORE.search(before)
        if sa and not re.search(r"(?<![а-яa-z])(?:или|а|но|or|but)(?![а-яa-z])", after[: sa.start("san")]):
            claim["san"] = sa["san"]
        elif re.match(r"\s*[*_]*(?P<san>" + _SAN_HERE + r")(?![A-Za-z0-9])", after):
            claim["san"] = re.match(r"\s*[*_]*(?P<san>" + _SAN_HERE + r")(?![A-Za-z0-9])", after)["san"]
        elif sb and (m["noun"] or re.search(r"[—–:-]", before[sb.end("san"):])) and not _square_of_noun(before, sb):
            claim["san"] = sb["san"]
        own = re.split(r"(?:,\s*|\s)(?:но|а|однако|или|либо|кроме|but|or|except)(?![а-яa-z])", after[:40], maxsplit=1)[0]
        pi = next((p for p in _PIECE_INSTR.finditer(own) if not re.search(r"(?<![а-яa-z])(?:не|ни|not)\s+$", own[:p.start()])),
                  None) or next((p for p in _PIECE_INSTR.finditer(before[-30:]) if not before[-30:][p.end():].strip()), None)
        if pi and re.match(r"\s*,?\s*(?:или|либо|and|or|и)\s", after[pi.end():]):
            pass  # «закройся конём или слоном»: one of several pieces — only that a block exists is read
        elif pi:
            claim["ptype"] = _ptype_word(pi["ru"] or pi["en"])
            claim["from"] = pi["sq"]
            claim["only"] = bool(pi["only"])
        else:
            ps = _PIECE_SUBJ.search(before)
            if ps:
                claim["ptype"], claim["from"] = _ptype_word(ps["ru"]), ps["sq"]
        to = re.match(r"(?:\s+[а-яa-z]+){0,3}?\s+(?:на|on|to)\s+(?P<sq>[a-h][1-8])(?![0-9])", after)
        if to and not re.search(r"(?<![а-яa-z])(?:корол\w*|king)\s+(?:на|on)\s+$", after[: to.end()][:-2]):
            claim["to"] = to["sq"]
        out.append(claim)
    return out


def _real_blocks(board: chess.Board) -> list:
    checkers = board.checkers()
    if len(checkers) != 1:
        return []
    between = chess.SquareSet(chess.between(board.king(board.turn), next(iter(checkers))))
    return [mv for mv in board.legal_moves if board.piece_type_at(mv.from_square) != chess.KING
            and mv.to_square not in checkers and mv.to_square in between]


def _check_tail(board: chess.Board) -> str:
    real = [board.san(x) for x in _real_blocks(board)]
    if real:
        return f"the blocks here are {', '.join(real)}"
    checker = next(iter(board.checkers()), None)
    why = ""
    if checker is not None and len(board.checkers()) == 1:
        pc = board.piece_at(checker)
        why = (" (a knight's check)" if pc.piece_type == chess.KNIGHT else
               f" (the {_NAMES.get(pc.piece_type, 'piece')} on {chess.square_name(checker)} stands next to the king)"
               if not chess.between(board.king(board.turn), checker) else "")
    elif len(board.checkers()) > 1:
        why = " (a double check)"
    return f"this check cannot be blocked{why}: the replies are " + ", ".join(board.san(x) for x in board.legal_moves)


def _block_verdict(board: chess.Board, claim: dict) -> Optional[str]:
    """Why *claim* is false on *board* (in check), '' when it holds, None when the words name nothing judgeable here."""
    blocks = _real_blocks(board)
    if claim["san"] and re.fullmatch(r"[a-h][1-8]", claim["san"]) and \
            board.piece_at(chess.parse_square(claim["san"])) is not None:
        return None  # a bare square that is taken (the checker's, a piece's): a pawn never moves onto it — a reference
    if claim["san"]:
        try:
            mv = board.parse_san(claim["san"])
        except ValueError:
            side = "White" if board.turn else "Black"
            return (f"{claim['san']} is not a legal move here: {side} is in check, and {claim['san']} does not answer it — "
                    + _check_tail(board))
        if mv in blocks:
            return ""
        san = board.san(mv)
        if board.piece_type_at(mv.from_square) == chess.KING:
            return f"{san} is a king move, not a block of the check — {_check_tail(board)}"
        if mv.to_square in board.checkers():
            pc = board.piece_at(mv.to_square)
            return (f"{san} takes the checking {_NAMES.get(pc.piece_type, 'piece')} on {chess.square_name(mv.to_square)} — "
                    f"it captures the checker, it does not block the check; {_check_tail(board)}")
        return f"{san} does not stand between the checker and the king — {_check_tail(board)}"
    ptype = claim["ptype"]
    if ptype == chess.KING:
        return None  # «закрыться королём»: the words already say a king move — loose wording, no false move
    if not blocks:
        return _check_tail(board)  # no block at all: whatever piece the words name
    frm = chess.parse_square(claim["from"].lower()) if claim["from"] else None
    if frm is not None and (board.piece_at(frm) is None or board.piece_at(frm).color != board.turn
                            or (ptype is not None and board.piece_type_at(frm) != ptype)):
        return None  # the square names another piece (or the king's square): not read
    to = chess.parse_square(claim["to"].lower()) if claim["to"] else None
    named = [mv for mv in blocks if (ptype is None or board.piece_type_at(mv.from_square) == ptype)
             and (frm is None or mv.from_square == frm) and (to is None or mv.to_square == to)]
    if not named:
        if not blocks:
            return _check_tail(board)
        what = (f"the {_NAMES[ptype]}" + (f" on {chess.square_name(frm)}" if frm is not None else "")) if ptype else "nothing"
        return f"{what} cannot block this check" + (f" on {chess.square_name(to)}" if to is not None else "") \
            + f" — {_check_tail(board)}"
    if claim["only"] and ptype is not None and any(board.piece_type_at(mv.from_square) != ptype for mv in blocks):
        return f"not only the {_NAMES[ptype]} can block this check — {_check_tail(board)}"
    return ""


def _block_kind_issues(text: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    boards = []
    for b in (ctx.current, (ctx.scene_before or (None,))[0], ctx.scene):
        if b is not None and b.is_check() and all(b is not x for x in boards):
            boards.append(b)
    if not boards:
        return []
    converted, _ = _to_san(text)
    out = []
    claims = _block_claims(converted)
    for claim in claims:
        here = boards
        # The scene this sentence's own line set, when that line is written after the block word: it is the claim's
        # board only when the line follows on from the board the claim is made on. A line that skips a move of the side
        # to move (walked with the turn changed), jumps between boards, or lands on the very square the sentence
        # blocks on («Закройся конём на c6, хотя после Qxc6+ конь теряется»: Qxc6+ presupposes the knight on c6) was
        # read on a board without the block the sentence proposed first. Such a scene may still clear the claim, but
        # it never condemns it (fix1102 K2, verify1102 B2).
        guessed = ctx.scene if (ctx.scene is not None and ctx.scene_trail
                                and _later_line_ignores_claim(converted, claim, ctx)) else None
        # A line written before the block word («Rc8+ загоняет короля на h7, потом Qb1+ — спокойно закройся g6»): the
        # claim is about the position after its last move, which the walk must have reached in this sentence.
        told = [mv for mv in _MOVE.finditer(converted[: claim["at"]])
                if (mv["san"][0] in "KQRBNO" or mv["num"] or mv["bdots"] or "x" in mv["san"] or mv["check"])
                and mv["san"] != claim["san"]]  # not the block's own move («Nxd8 — это заслон»)
        if told and any(all(_parses(b, x["san"] + (x["check"] or "")) for x in told) for b in boards):
            pass  # «У тебя три хода: Kxd8, Ke7 или закрыться — Nxd8»: the replies of this very board, listed
        elif told:
            # only a line written out move by move («Rc8+ Kh7 Qb1+»), every move of it walked in this sentence: a move
            # told in words between («Rc8+ загоняет короля на h7, потом Qb1+») leaves the walk on a guessed board
            whole = all(re.fullmatch(r"[\s,]*(?:\d{1,3}\s?\.{1,3}\s*)?", converted[x.end(): y.start()])
                        for x, y in zip(told, told[1:]))
            walked = [san.rstrip("+#").replace("x", "") for san, _, _ in ctx.scene_trail]
            if not whole or walked[-len(told):] != [x["san"].replace("x", "") for x in told]:
                continue
            here = [b for _, b, _ in ctx.scene_trail[-1:] if b.is_check()]
            guessed = None  # the walk ends on the told line itself: the board right after the line the claim sits in
        here = [b for b in here if not b.is_checkmate()]  # mate: nothing answers it, no block to judge
        if not here:
            continue
        verdicts = [_block_verdict(b, claim) for b in here]
        if any(v == "" for v in verdicts) or all(v is None for v in verdicts):
            continue  # holds on some board in check of the sentence, or names nothing here
        condemn = [v for b, v in zip(here, verdicts) if v and b is not guessed]
        if condemn:
            out.append(condemn[0])
    if not claims and not _BLOCK_WORD.search(converted):
        out = _reply_in_check_issues(converted, ctx, boards)
    return out


def _block_target(claim: dict) -> Optional[int]:
    """The square the claim blocks on: its move's destination, else the square named after «на»."""
    if claim["san"]:
        sq = re.findall(r"[a-h][1-8]", claim["san"])
        if sq:
            return chess.parse_square(sq[-1])
    return chess.parse_square(claim["to"].lower()) if claim["to"] else None


def _later_line_ignores_claim(conv: str, claim: dict, ctx: CheckContext) -> bool:
    """Whether the scene of this sentence comes from a line written after the block word that was read without the
    position the claim is made in: the line does not follow on from the board before this sentence (the turn's board,
    or the scene the sentence before left) move by move with each side in turn, or one of its moves lands on the
    square the claim blocks on. A line written before the block word is the told walk's business, not this one."""
    later = [mv for mv in _MOVE.finditer(conv, claim["at"])
             if (mv["san"][0] in "KQRBNO" or mv["num"] or mv["bdots"] or "x" in mv["san"] or mv["check"])
             and mv["san"] != claim["san"]]
    if not later:
        return False
    target = _block_target(claim)
    if target is not None and any(re.findall(r"[a-h][1-8]", mv["san"])[-1:] == [chess.square_name(target)]
                                  for mv in later):
        return True  # «…на c6, хотя после Qxc6+»: the later line takes on the block's own square
    starts = [b for b in (ctx.current, (ctx.scene_before or (None,))[0]) if b is not None]
    prev = None
    for i, (_san, after, move) in enumerate(ctx.scene_trail):
        froms = [prev] if i else starts
        follows = False
        for b in froms:
            if b is None or not b.is_legal(move):
                continue  # the move is not one of the side to move there: the walk changed the turn or the board
            nxt = b.copy(stack=False)
            nxt.push(move)
            if nxt.board_fen() == after.board_fen() and nxt.turn == after.turn:
                follows = True
                break
        if not follows:
            return True
        prev = after
    return False


# The reply to a check proposed for the side in check («Лучший ответ — Qd7», «Сыграй Bd7» with Black in check from an
# adjacent rook) must be legal there: a move that does not answer the check is not a reply at all (review 01.11: the
# lenient «reachable in two moves» excused it). Only the sentence's first move, only after a proposal word in its
# clause, and only when no other position of the turn with that side to move allows it.
def _reply_in_check_issues(conv: str, ctx: CheckContext, boards: list) -> list[str]:
    board = ctx.current
    if not board.is_check() or "?" in conv or _DENIES.search(conv):
        return []
    first = next(iter(_MOVE.finditer(conv)), None)
    if first is None or first["num"] or first["san"] in ctx.quoted:
        return []
    imper = _REPLY_IMPER.search(conv[max(conv.rfind(c, 0, first.start()) for c in ".;!?\n") + 1: first.start()])
    if first["san"].startswith("O-O") and not imper:
        return []
    san = first["san"] + (first["check"] or "")
    cs = max(conv.rfind(c, 0, first.start()) for c in ".;!?\n") + 1
    head = conv[cs: first.start()]
    if first["san"][0] not in "KQRBN" and "x" not in first["san"] and not first["bdots"] \
            and not re.search(r"(?:[:—–]|(?<![а-яa-z])(?:ходом|сыграй|играй|сыграть|лучше|ответ\w*))\s*[*_]*$", head):
        return []  # «перекрой шах ферзём на d7»: a square, not a move
    trig = [m for m in list(_PROPOSES.finditer(head)) + list(_F_NEXT.finditer(head)) + list(_REPLY_IMPER.finditer(head))
            if not _not_a_proposal(head, m) and not _NEGATION.search(head[max(0, m.start() - 24): m.start()])]
    if not trig or _COND_BEFORE.search(conv[:first.start()]) or _PAST_PLAN.search(head):
        return []
    if _parses(board, san):
        return []
    if _not_the_reply(conv, first.start(), san, board, ctx):
        return []
    if any(b is not board and b.turn == board.turn and ctx.is_given(b) and ctx._key(b) not in ctx.passed_keys
           and ctx._key(b) not in ctx.other_board_keys and _parses(b, san) for b in ctx.boards):
        return []  # another position of the turn (not one the game passed through on its way here) allows it
    side = "White" if board.turn else "Black"
    return [f"{san} is not a legal move here: {side} is in check, and {san} does not answer it — {_check_tail(board)}"]


# An imperative of replying to the check (review-miss2 01.11): «Ответь Be6», «Защитись от шаха: Bd7», «Рокируйся:
# O-O», «Подумай о ходе Bg4» — the move after it is proposed as the reply.
_REPLY_IMPER = re.compile(r"(?<![а-яa-z])(?:ответь(?:те)?|отвечай(?:те)?|защит(?:ись|итесь)|защищайся|защищайтесь|"
                          r"рокируйся|рокируйтесь|подумай(?:те)?\s+(?:о|об|про)\s+ход\w*|рассмотри(?:те)?|"
                          r"уйди(?:те)?\s+от\s+шаха|выбирай(?:те)?|выбери(?:те)?)(?![а-яa-z])", re.IGNORECASE)


# Whose move a proposal on a board in check names (review fp2 01.11: «Ты дал шах; следующим ходом сыграй Nc3» after the
# student's 3.Bb5+ was read as Black's reply). The reply belongs to the side in check; the words propose another move
# when they defer it («дальше», «следующим ходом», «потом», «после его ответа», "next", "then"), when the student is not
# the side in check and the clause does not name the side that is, or — the student's side unknown — when the move is
# the other side's after some legal reply.
_LATER_MOVE = re.compile(r"(?<![а-яa-z])(?:дальше|далее|потом|затем|позже|следующ\w+\s+ход\w*|в\s+следующ\w+|"
                         r"после\s+(?:(?:его|е[её]|их|твоего|вашего|этого|чужого|любого|их)\s+)?(?:ответ\w*|хода)|"
                         r"на\s+следующ\w+\s+ходу|next|then|later|afterwards)(?![а-яa-z])", re.IGNORECASE)
_SIDE_WORD_OF = {chess.WHITE: re.compile(r"(?<![а-яa-z])(?:бел\w+|white)(?![а-яa-z])", re.IGNORECASE),
                 chess.BLACK: re.compile(r"(?<![а-яa-z])(?:ч[её]рн\w+|black)(?![а-яa-z])", re.IGNORECASE)}
_OPPONENT_WORD = re.compile(r"(?<![а-яa-z])(?:соперник\w*|противник\w*|opponent)(?![а-яa-z])", re.IGNORECASE)


def _not_the_reply(conv: str, at: int, san: str, board: chess.Board, ctx: CheckContext) -> bool:
    cs = max(conv.rfind(c, 0, at) for c in ".;!?\n") + 1
    head = conv[cs: at]
    if _LATER_MOVE.search(head):
        return True
    student = getattr(ctx, "student_color", None)
    if student is not None and student != board.turn:
        named = _SIDE_WORD_OF[board.turn].search(head) or _OPPONENT_WORD.search(head)
        return not named
    if student is None:
        try:
            for reply in list(board.legal_moves)[:40]:
                after = board.copy(stack=False)
                after.push(reply)
                if _parses(after, san):
                    return True
        except Exception:  # noqa: BLE001
            return True
    return False


# M6 (with eval C3): «белые забирают фигуру бесплатно» about a capture of the game (prod st2#4 29.10: after 4.exf6
# the pawn on f6 is taken back by gxf6 or Qxf6 — a knight for a pawn): a capture told as free loses nothing back.
# Read as a frame (fix 01.11 F4): a FREE marker («бесплатно», «даром», «ни за что», «без компенсации», «без потерь»,
# «ничего не отдав», "for free") + a capture verb of either party — the TAKER («белые забрали», «пешка e5 съела»), the
# LOSER («конь потерян», «ты потерял коня», «конь погиб») or the RECEIVER («конь достался белым») — bound to the capture
# of the game it names (its from-square, its square or the taken piece's). Not negated («даром не возьмёшь»), not
# «просто так» alone, not a capture to come («заберёт бесплатно»: a threat, judged as a line).
_FREE = re.compile(r"(?<![а-яё])(?:бесплатно|даром|задаром|за\s+просто\s+так|за\s+ничего|ни\s+за\s+что(?!\s+не(?![а-яё]))|"
                   r"без\s+(?:всякой\s+|какой-либо\s+|какой-нибудь\s+|никакой\s+)?(?:компенсаци|возмещени)\w*|"
                   r"без\s+(?:всяких\s+|каких-либо\s+)?потерь|ничего\s+не\s+(?:отдав|потеряв|отдавая)|не\s+отдав\s+ничего)(?![а-яё])"
                   r"|(?<![a-z])(?:for\s+(?:free|nothing)|without\s+(?:any\s+)?compensation)(?![a-z])", re.IGNORECASE)
_TAKE_NOW = re.compile(r"(?<![а-яё])(?:забира\w+|забрал\w*|бер[её]т|берут|бер[её]шь|взял\w*|выигрыва\w+|выиграл\w*|съел\w*|"
                       r"съеда\w+|получа\w+|получил\w*|срубил\w*|побил\w*|сбил\w*|прихватил\w*|урвал\w*)(?![а-яё])|"
                       r"(?<![a-z])(?:wins?|won|takes?|took|grabs?|grabbed|picks?\s+up|picked\s+up)(?![a-z])",
                       re.IGNORECASE)
# the loser's verbs, told as done (past or passive): the side named is the one whose piece was taken. Not the present
# («ты теряешь ещё фигуру»: what follows, a threat — not the game's capture)
_LOSE_NOW = re.compile(r"(?<![а-яё])(?:отдал\w*|отдан\w*|потерял\w*|потерян\w*|пропал\w*|погиб\w*|"
                       r"зевнул\w*|подарил\w*|сдал(?:и|а)?)(?![а-яё])|(?<![a-z])(?:gave\s+up|lost)(?![a-z])",
                       re.IGNORECASE)
# «ещё фигуру», "another piece": a unit beyond the one taken — not the recorded capture
_ONE_MORE = re.compile(r"(?<![а-яё])(?:ещ[её]\s+(?:одн\w+\s+|и\s+)?|друг\w+\s+|втор\w+\s+)(?=(?:пешк|кон|слон|ладь|ферз|фигур))|"
                       r"(?<![a-z])another\s+", re.IGNORECASE)
# the receiver's: «конь достался белым» — the side named (a dative) took it
_GOT_NOW = re.compile(r"(?<![а-яё])(?:достал(?:ся|ась|ось|ись)|достанется|достаются|достается|доста[её]тся)(?![а-яё])", re.IGNORECASE)
_CAPTURED_WORD = (("пешк", {chess.PAWN}), ("кон", {chess.KNIGHT}), ("слон", {chess.BISHOP}), ("ладь", {chess.ROOK}),
                  ("ферз", {chess.QUEEN}), ("фигур", {chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN}),
                  ("pawn", {chess.PAWN}), ("knight", {chess.KNIGHT}), ("bishop", {chess.BISHOP}), ("rook", {chess.ROOK}),
                  ("queen", {chess.QUEEN}), ("piece", {chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN}))
_UNIT_WORD = re.compile(r"(?<![а-яёa-z])(?:пешк\w*|кон[ьяе]\w*|слон\w*|ладь\w*|ферз\w*|фигур\w*|pawns?|knights?|bishops?|rooks?|"
                        r"queens?|pieces?)(?![а-яёa-z])", re.IGNORECASE)
# «ничего не можешь взять в ответ», «отыграть ничего нельзя», «пешку f6 не взять», «забрать обратно не выйдет»: the
# capture just played cannot be answered by a capture back — judged on the board now (fix 01.11 F4).
_BACK_VERB = re.compile(r"(?<![а-яё])(?P<v>взять|забрать|отыграть|отыграешь|отыграют|отбить|побить|съесть|вернуть|"
                        r"возьмешь|возьм[её]шь|заберешь|заберешь|забер[её]шь)(?![а-яё])", re.IGNORECASE)
_BACK_MARK = re.compile(r"(?<![а-яё])(?:в\s+ответ|обратно|назад)(?![а-яё])|отыгр|отбит|вернуть", re.IGNORECASE)
# impossibility, not advice: «нельзя», «нечем», «не можешь / не выйдет», or «не» right on the verb («пешку f6 не взять») —
# not «не спеши взять обратно», «лучше не брать»
_NO_WAY = re.compile(r"(?<![а-яё])(?:нельзя|нечем|никак|невозможно|не\s+(?:можешь|может|могут|можете|сможешь|сможет|смогут|"
                     r"получится|выйдет|удастся|удаться|удается|удаётся))(?![а-яё])", re.IGNORECASE)
_ADVICE = re.compile(r"(?<![а-яё])(?:не\s+(?:спеши|торопись|надо|нужно|стоит|советую|обязательно)|лучше\s+не|можно\s+не)(?![а-яё])",
                     re.IGNORECASE)
_WHY = re.compile(r"(?<![а-яё])(?:потому|из-за|так\s+как|иначе|поскольку|ведь|мат\w*|шах\w*|связ\w*|вилк\w*|because|since|mate)(?![а-яё])",
                  re.IGNORECASE)


def _clause_at(text: str, at: int) -> tuple[int, int]:
    """The clause of *text* around *at*: between the nearest «.;:!?—–,» on each side."""
    seps = ".;:!?—–,("
    start = max(text.rfind(c, 0, at) for c in seps) + 1
    ends = [i for i in (text.find(c, at) for c in seps) if i >= 0]
    return start, min(ends) if ends else len(text)


def _game_board_before(moves: list, ply: int) -> Optional[chess.Board]:
    board = chess.Board()
    try:
        for san in moves[: ply - 1]:
            board.push_san(san)
    except ValueError:
        return None
    return board


def _no_recapture_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    """«ты ничего не можешь взять в ответ» right after a capture of the game that can be taken back with profit."""
    moves = getattr(ctx, "game_moves", None)
    if not moves or "?" in text or _WHY.search(text):
        return []
    from src.game_record import captures

    caps = captures(ctx)
    if not caps or caps[-1].ply != len(moves):
        return []  # only right after the capture: later the board now is another one
    cap = caps[-1]
    for v in _BACK_VERB.finditer(text):
        start, end = _clause_at(text, v.start())
        clause = text[start:end]
        if not (_NO_WAY.search(clause) or re.search(r"(?<![а-яё])не\s+$", text[max(start, v.start() - 4): v.start()])):
            continue
        if _ADVICE.search(clause) or _is_hypothetical(text, original, start, ctx=ctx):
            continue
        squares = {x.lower() for x in _SQ_RE.findall(clause)}
        board = _game_board_before(moves, cap.ply)
        if board is None:
            return []
        move = board.parse_san(moves[cap.ply - 1])
        landing = chess.square_name(move.to_square)
        if squares and landing not in squares:
            continue
        if not (_BACK_MARK.search(clause) or landing in squares):
            continue
        back = _recaptures(board, move)
        after = board.copy(stack=False)
        after.push(move)
        sound = []
        for san in back:  # a recapture that allows a mate in one is no way back
            b2 = after.copy(stack=False)
            b2.push_san(san)
            if not _mate_in_one(b2):
                sound.append(san)
        if sound:
            lands = _NAMES.get(move.promotion or cap.piece, "pawn")
            return [f"after {cap.label} the {lands} on {landing} can be taken back: {' or '.join(sound)}"]
    return []


def _mate_in_one(board: chess.Board) -> bool:
    for mv in board.legal_moves:
        board.push(mv)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return True
    return False


def _free_capture_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    moves = getattr(ctx, "game_moves", None)
    if not moves or ctx.current is None:
        return []
    free = _FREE.search(text)
    if not free:
        return _no_recapture_issues(text, original, ctx)
    start, end = _clause_at(text, free.start())
    clause = text[start:end]
    # the marker itself is no denial («ни за что», «ничего не отдав»); a «не» left is («не бесплатно», «даром не возьмёшь»)
    bare = _FREE.sub(" ", clause)
    take, lose, got = _TAKE_NOW.search(bare), _LOSE_NOW.search(bare), _GOT_NOW.search(bare)
    if not (take or lose or got) and start > 0 and text[start - 1] == ",":
        # «белые забрали коня, ничего не отдав»: the marker is a participle phrase of the clause before it
        start = _clause_at(text, start - 1)[0]
        clause = text[start:end]
        bare = _FREE.sub(" ", clause)
        take, lose, got = _TAKE_NOW.search(bare), _LOSE_NOW.search(bare), _GOT_NOW.search(bare)
    verb = take or lose or got
    if not verb or _NEGATED_WORD.search(bare) or "?" in text[free.end():free.end() + 40].split(".")[0] \
            or _ONE_MORE.search(clause):
        return []
    if _is_hypothetical(text, original, free.start(), ctx=ctx) or _FUTURE_VERB.search(clause):
        return []
    from src.board_math import capture_is_free, move_loss
    from src.game_record import captures, last_capture

    caps = captures(ctx)
    if not caps:
        return []
    converted, _ = _to_san(original)
    written = [m["san"].rstrip("+#") for m in _MOVE.finditer(converted)
               if m["num"] or m["bdots"] or m["san"][0] in "KQRBNO" or "x" in m["san"]]
    game_caps = {c.san.rstrip("+#") for c in caps}
    if any(w not in game_caps and w not in {s.rstrip("+#") for s in moves} for w in written):
        return []  # a move of a line, not of the game: the capture told is that line's
    named_in_sentence = any("x" in w and w in game_caps for w in written)
    scene = (getattr(ctx, "scene_san", "") or "").rstrip("+#")
    cap = last_capture(ctx, original)
    if cap is None:
        return []
    unit = _UNIT_WORD.search(clause)
    want = next((t for k, t in _CAPTURED_WORD if unit and unit.group(0).lower().startswith(k)), None)
    if not named_in_sentence and not ("x" in scene and scene == cap.san.rstrip("+#")):
        # the last ply played: only when the words fit it — the piece taken and the side taking
        if want is None:
            return []
    from src.game_record import side_words

    board = _game_board_before(moves, cap.ply)
    if board is None:
        return []
    move = board.parse_san(moves[cap.ply - 1])
    if want is not None and cap.captured not in want:
        # «пешка e5 съела коня»: the unit named first may be the capturer — the taken piece is another unit word
        units = [u for u in _UNIT_WORD.finditer(clause)]
        kinds = [next((t for k, t in _CAPTURED_WORD if u.group(0).lower().startswith(k)), set()) for u in units]
        if not any(cap.captured in k for k in kinds):
            return []
    side = side_words(ctx, clause)
    if side is not None:
        mover_named = side if (take or got) and not (lose and lose.start() < (take or got).start()) else not side
        if mover_named != cap.mover:
            return []
    squares = {s.lower() for s in _SQ_RE.findall(clause.lower())}
    if squares and not squares & {chess.square_name(cap.square), chess.square_name(move.to_square),
                                  chess.square_name(move.from_square)}:
        return []
    if move.promotion:
        free_now = move_loss(board, move) == 0 and not _recaptures(board, move)
    else:
        free_now = capture_is_free(board, move)
    if free_now:
        return []
    back = _recaptures(board, move)
    taken = _NAMES.get(cap.captured, "pawn")
    lands = _NAMES.get(move.promotion or cap.piece, "pawn")
    return [f"{cap.label} is not free: the {lands} on {chess.square_name(move.to_square)} can be taken back by "
            f"{' or '.join(back) if back else 'force'} — {_COLOR_EN[cap.mover]} wins a {taken} for a {lands}"
            if back else f"{cap.label} is not free: it loses material back by force"]


def _recaptures(board: chess.Board, move: chess.Move) -> list[str]:
    """The captures of the piece *move* lands with, on the board after it, that win for the side taking back."""
    from src.board_math import see

    after = board.copy(stack=False)
    after.push(move)
    return [after.san(m) for m in after.legal_moves if m.to_square == move.to_square and see(after, m) > 0]


# M7: a loss told as done in a game — «Чёрные отдали центральную пешку» after 1.e4 c5 (prod st1#1 29.10: nothing was
# taken) — must be in the game's record: a capture of that side's unit. «в партии Морфи …», a famous game among the
# turn's records, or a line written in the sentence: another game's or a line's loss, judged elsewhere (trades, P6).
# Read as a frame (fix 01.11 F4): a SIDE in the nominative (белые / чёрные / ты / вы / я / соперник), a few words, a
# LOSS VERB in the past (отдать, потерять, пожертвовать, разменять, уступить, сдать; «остаться без», «лишиться»), the
# UNIT in its case (a number, «c-пешку», adjectives, a square). Unjudged: a unit that is no material («центр», «темп»),
# «отказались от» (declined or gave up), a sacrifice still on offer (the unit can be taken now).
_GAVE_SIDE = r"(?P<side>белые|ч[её]рные|ты|вы|я|соперник|противник)"
_GAVE_VERB = (r"(?P<verb>отдал[аи]?|отдан[аоы]?|потерял[аи]?|пожертвовал[аи]?|разменял[аи]?|уступил[аи]?|сдал[аи]?|"
              r"(?P<without>остал(?:ся|ась|ись)\s+без|лишил(?:ся|ась|ись)))")
_GAVE_ACC = r"(?:пешку|пешки|пешек|коня|коней|слона|слонов|ладью|ладьи|ладей|ферзя|фигуру|фигуры|фигур|качество)"
_GAVE_GEN = r"(?:пешки|пешек|коня|коней|слона|слонов|ладьи|ладей|ферзя|фигуры|фигур|качества)"
_GAVE = re.compile(
    rf"(?<![а-яё]){_GAVE_SIDE}\s+(?P<gap>(?:[а-яё-]+\s+){{0,2}}?){_GAVE_VERB}\s+"
    r"(?:(?:тебе|вам|мне|белым|ч[её]рным|сопернику|противнику|сразу|уже|даже|целую|целого|сво\w+|одн\w+|центральн\w+|"
    r"ферзев\w+|королев\w+|лишн\w+|(?P<n>две|двух|три|тр[её]х|четыре|2|3|4))\s+){0,3}"
    rf"(?:[a-h]-)?(?P<unit>{_GAVE_ACC}|{_GAVE_GEN})(?![а-яё])", re.IGNORECASE)
_OTHER_GAME = re.compile(r"(?<![а-яё])(?:в|из|во)\s+(?:(?:сво\w+|прошл\w+|друг\w+|т(?:ой|ую|ом)|известн\w+|знаменит\w+|"
                         r"бессмертн\w+|вечнозел\w+|оперн\w+|классическ\w+|старин\w+|той\s+самой)\s+)?парти[ия]\s+"
                         r"(?:[А-ЯЁA-Z]|против|с\s+[А-ЯЁA-Z]|\d{4})"
                         r"|(?<![а-яё])(?:прошл\w+|друг\w+|т(?:ой|ую|ом)|известн\w+|знаменит\w+|бессмертн\w+|вечнозел\w+|оперн\w+)\s+парти",
                         re.IGNORECASE)
_GAVE_UNIT = (("пеш", {chess.PAWN}, "pawn"), ("кон", {chess.KNIGHT}, "knight"), ("слон", {chess.BISHOP}, "bishop"),
              ("лад", {chess.ROOK}, "rook"), ("ферз", {chess.QUEEN}, "queen"),
              ("фигур", {chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN}, "piece"),
              ("качеств", {chess.ROOK}, "exchange (a rook)"))


def _gave_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    moves = getattr(ctx, "game_moves", None)
    if not moves or ctx.current is None or "?" in text or _OTHER_GAME.search(original):
        return []
    from src.board_math import see
    from src.game_record import _players, captures, recap_end

    claims = [m for m in _GAVE.finditer(text) if not _NOT_TOLD.search(text[max(0, m.start() - 40): m.start()])
              and not _NEGATED_WORD.search(m["gap"] or "") and not _FUTURE_VERB.search(m["gap"] or "")
              and not _is_hypothetical(text, original, m.start(), ctx=ctx)]
    framed = _frame_lose_issues(text, original, ctx, [(m.start(), m.end()) for m in _GAVE.finditer(text)])
    if not claims or _players(ctx):
        return framed
    converted, _ = _to_san(original)
    if any(m["num"] or m["bdots"] or m["san"][0] in "KQRBN" or "x" in m["san"] for m in _MOVE.finditer(converted)) \
            and recap_end(ctx, original) is None:
        return []  # moves of a line written in the sentence: its loss, not the game's
    caps = captures(ctx)
    board = ctx.current
    out = []
    for m in claims:
        side = m["side"].lower().replace("ё", "е")
        if side.startswith("бел"):
            color = chess.WHITE
        elif side.startswith("черн"):
            color = chess.BLACK
        elif ctx.student_color is None:
            continue
        else:
            color = ctx.student_color if side in ("ты", "вы") else not ctx.student_color
        unit = m["unit"].lower()
        want, name = next((w, nm) for k, w, nm in _GAVE_UNIT if unit.startswith(k))
        n = _num(m["n"]) if m["n"] else 1
        lost = [c for c in caps if c.mover != color and c.captured in want]
        # «одну пешку», «всего пешку», «пешку e4 и больше ничего»: that count exactly (review-miss2 01.11)
        exact = bool(re.search(r"(?<![а-яё])(?:одн(?:у|ого|а)|всего|только|лишь|ровно)\s+(?:[а-яё-]+\s+)?$",
                               text[m.start(): m.start("unit")])) or bool(_MAT_NOTHING_ELSE.match(
                                   text, m.end() + (len(re.match(r"\s*[a-h][1-8]", text[m.end():]).group(0))
                                                    if re.match(r"\s*[a-h][1-8]", text[m.end():]) else 0)))
        if len(lost) >= n and not (exact and len(lost) != n):
            continue
        verb = m["verb"].lower()
        if re.search(r"(?<![а-яё])(?:не\s+(?:взял\w*|принял\w*|забрал\w*|стал\w*\s+брать)|отказал\w*|отклонил\w*)(?![а-яё])",
                     text):
            continue  # «пожертвовали пешку, но чёрные её не взяли»: an offer declined, not a loss
        trade = verb.startswith("разменя") or re.match(
            r"\s*(?:[a-h]\b\s*)?(?:[a-h][1-8]\s+)?(?:за|на)\s+(?:[а-яё-]+\s+){0,2}?(?:пешк|кон|слон|ладь|ферз|фигур|центральн)",
            text[m.end():])
        if trade and any(c.mover == color for c in caps):
            continue  # «разменяли c-пешку на центральную», «отдали пешку c за пешку d» after 2...cxd4: under way
        if board.turn != color and any(board.is_capture(mv) and (v := board.piece_at(mv.to_square)) is not None
                                       and v.color == color and v.piece_type in want and see(board, mv) > 0
                                       for mv in board.legal_moves):
            continue  # «белые пожертвовали пешку» after 2.f4: the sacrifice is on offer, not taken yet. A piece that
            # can only be traded off evenly (Bxd5+ Qxd5 after 6...Kxf7) is no sacrifice on offer.
        theirs = [f"{c.label} ({_NAMES.get(c.captured, 'pawn')})" for c in caps if c.mover != color]
        out.append(f"in this game {_owner_words(ctx, color)} has lost "
                   + (f"no {name}" if not lost else f"{'only ' if len(lost) < n else ''}{len(lost)} {name}"
                      f"{'s' if len(lost) > 1 else ''}, not {n}") + ": "
                   + (f"its losses so far are {', '.join(theirs)}" if theirs else "nothing of it has been captured yet"))
    return out + framed


# ── the game-record claims read by their parts (src/capture_frames, review-miss2 01.11) ─────────────────────────────
# What the closed patterns above miss («Слона e7 съела твоя пешка», «Чёрные расстались с d-пешкой», «Ход fxe7 сделал
# ты», «Ты потерял одну пешку»): the clause's events, judged by the game's record exactly as the patterns' claims are.
# A clause one of the patterns already read is left to it.
def _frame_owner(who: str, ctx: CheckContext, ptypes) -> Optional[bool]:
    from src.capture_frames import resolve

    if who.startswith("@"):
        # «Пешка c5 отдана»: the owner of the unit that stood on that square in this game
        sq = chess.parse_square(who[1:])
        from src.game_record import _walk, _sans

        colour = None
        for _ply, board, _mv, _san in _walk(_sans(ctx)):
            p = board.piece_at(sq)
            if p is not None and p.piece_type in ptypes:
                colour = p.color if colour is None or colour == p.color else "both"
        if ctx.current is not None and (p := ctx.current.piece_at(sq)) is not None and p.piece_type in ptypes:
            colour = p.color if colour is None or colour == p.color else "both"
        return None if colour in (None, "both") else colour
    return resolve(who, ctx)


def _frame_guarded(text: str, original: str, ctx: CheckContext) -> bool:
    """The sentence may be read for game-record events: a game on the board, no question, no quote, no other game,
    no line of moves the game did not play."""
    moves = getattr(ctx, "game_moves", None)
    if not moves or ctx.current is None or "?" in text or "«" in text or '"' in text or _OTHER_GAME.search(original):
        return False
    from src.game_record import _players

    if _players(ctx):
        return False
    converted, _ = _to_san(original)
    played = {str(x).rstrip("+#") for x in moves}
    return not any(x["san"].rstrip("+#") not in played for x in _MOVE.finditer(converted)
                   if x["num"] or x["bdots"] or x["san"][0] in "KQRBNO" or "x" in x["san"])


def _frame_events(original: str, kinds: tuple, taken: list) -> list:
    """The events of *kinds* in *original* whose clause none of the spans in *taken* (the patterns' claims) touches."""
    from src.capture_frames import events

    converted, _ = _to_san(original)
    out = []
    for ev in events(converted):
        if ev.kind not in kinds:
            continue
        if any(a < ev.end and ev.at < b for a, b in taken):
            continue
        out.append(ev)
    return out


def _frame_take_issues(text: str, original: str, ctx: CheckContext, taken: list) -> list[str]:
    if not _frame_guarded(text, original, ctx):
        return []
    from src.game_record import captures

    caps = captures(ctx)
    moves = [str(x).rstrip("+#") for x in ctx.game_moves]
    out = []
    for ev in _frame_events(original, ("take", "played"), taken):
        if _is_hypothetical(text, original, min(ev.at, len(text) - 1), ctx=ctx) or \
                _NOT_TOLD.search(original[max(0, ev.at - 40): ev.end]):
            continue
        color = _frame_owner(ev.who, ctx, set())
        if color is None:
            continue
        who_words = "the student" if ev.who == "S" else _owner_words(ctx, color)
        if ev.kind == "played":
            mm = re.fullmatch(r"(?:(\d{1,3})\s?(\.{1,3})\s?)?(.+?)[+#]?", ev.san or "")
            if not mm:
                continue
            san = mm.group(3)
            plies = [i + 1 for i, m in enumerate(moves) if m == san]
            if mm.group(1):
                want = 2 * int(mm.group(1)) - (0 if len(mm.group(2)) == 3 else 1)
                plies = [p for p in plies if p == want]
            if not plies:
                continue
            if all((chess.WHITE if p % 2 else chess.BLACK) != color for p in plies):
                p = plies[-1]
                mover = chess.WHITE if p % 2 else chess.BLACK
                out.append(f"{(p - 1) // 2 + 1}{'.' if p % 2 else '...'}{san} was {_owner_words(ctx, mover, True)} move, "
                           f"not {who_words}'s")
            continue
        def fits(c) -> bool:
            if c.captured not in ev.ptypes or (ev.sq and chess.square_name(c.square) != ev.sq):
                return False
            if ev.instr is not None and ev.instr != c.piece and not (c.piece == chess.PAWN and "=" in c.san):
                return False
            if ev.instr_sq and c.from_square >= 0:
                where = {chess.square_name(c.from_square)} if ev.instr_from else \
                    {chess.square_name(c.from_square), chess.square_name(c.to_square)}
                if ev.instr_sq not in where:
                    return False
            if ev.san and c.san.rstrip("+#") != re.sub(r"^\d{1,3}\s?\.{1,3}\s?", "", ev.san).rstrip("+#"):
                return False
            return True
        hits = [c for c in caps if fits(c)]
        mine = [c for c in hits if c.mover == color]
        unit = " or ".join(sorted({_NAMES.get(t, "piece") for t in ev.ptypes})) if len(ev.ptypes) < 4 else "piece"
        if not mine:
            if hits:
                c = hits[-1]
                out.append(f"{c.label} was {_owner_words(ctx, c.mover, True)} capture, not {who_words}'s: it took "
                           f"{_owner_words(ctx, not c.mover, True)} {_NAMES.get(c.captured, 'pawn')} on "
                           f"{chess.square_name(c.square)}")
            else:
                done = [c.label for c in caps if c.mover == color]
                out.append(f"in this game {who_words} never captured a {unit}"
                           + (f" on {ev.sq}" if ev.sq else "") + ": its captures so far are "
                           + (", ".join(done) if done else "none"))
            continue
        all_mine = [c for c in caps if c.mover == color and c.captured in ev.ptypes]
        if (ev.exact and len(all_mine) != ev.count) or len(all_mine) < ev.count:
            out.append(f"in this game {who_words} captured {len(all_mine)} {unit}{'s' if len(all_mine) != 1 else ''}, "
                       f"not {ev.count}: " + ", ".join(c.label for c in all_mine))
            continue
        if ev.gain:
            out += _no_gain_issue(mine, color, who_words, unit, ctx)
    return out


def _no_gain_issue(mine: list, color: bool, who_words: str, unit: str, ctx: CheckContext) -> list[str]:
    """«Ты выиграл пешку на d4» over 3...cxd4 4.Nxd4 (fresh-miss mat07): to WIN a unit is to come out of the exchange
    ahead, not to capture it. Every capture the words can mean ended an exchange that is over, with no gain for that
    side, and the material now shows none either — else unjudged (an exchange still going on, a gain later)."""
    from src.board_math import VALUE
    from src.game_record import exchanges

    moves = [str(x) for x in ctx.game_moves]
    runs = exchanges(moves)
    told = None
    for c in mine:
        run = next((r for r in runs if r.start_ply <= c.ply <= r.end_ply), None)
        if run is None or run.end_ply >= len(moves):
            return []
        net = sum(VALUE[pt] * k for pt, k in run.lost[not color].items()) - sum(VALUE[pt] * k for pt, k in run.lost[color].items())
        if net > 0:
            return []
        told = (c, run, net)
    board = ctx.current
    if told is None or board is None:
        return []
    lead = sum(VALUE[pt] * (len(board.pieces(pt, color)) - len(board.pieces(pt, not color))) for pt in VALUE if pt != chess.KING)
    if lead > 0:
        return []
    c, run, net = told
    return [f"{c.label} won {who_words} no {unit}: the exchange {run.text} left the material "
            + ("even" if net == 0 else f"{-net} point{'s' if net != -1 else ''} down for that side")
            + f", and now {_imbalance(board)}"]


def _frame_lose_issues(text: str, original: str, ctx: CheckContext, taken: list) -> list[str]:
    if not _frame_guarded(text, original, ctx):
        return []
    from src.board_math import see
    from src.game_record import captures

    caps = captures(ctx)
    board = ctx.current
    out = []
    for ev in _frame_events(original, ("lose",), taken):
        if _is_hypothetical(text, original, min(ev.at, len(text) - 1), ctx=ctx) or \
                _NOT_TOLD.search(original[max(0, ev.at - 40): ev.end]):
            continue
        color = _frame_owner(ev.who, ctx, set(ev.ptypes))
        if color is None:
            continue
        lost = [c for c in caps if c.mover != color and c.captured in ev.ptypes
                and (not ev.sq or chess.square_name(c.square) == ev.sq)]
        if (len(lost) == ev.count) or (not ev.exact and len(lost) > ev.count):
            continue
        if re.search(r"(?<![а-яё])(?:не\s+(?:взял\w*|принял\w*|забрал\w*|стал\w*\s+брать)|отказал\w*|отклонил\w*)(?![а-яё])",
                     text):
            continue  # an offer declined, not a loss
        if not lost and board.turn != color and any(
                board.is_capture(mv) and (v := board.piece_at(mv.to_square)) is not None and v.color == color
                and v.piece_type in ev.ptypes and see(board, mv) > 0 for mv in board.legal_moves):
            continue  # a sacrifice still on offer
        unit = " or ".join(sorted({_NAMES.get(t, "piece") for t in ev.ptypes})) if len(ev.ptypes) < 4 else "piece"
        who_words = _owner_words(ctx, color)
        theirs = [f"{c.label} ({_NAMES.get(c.captured, 'pawn')})" for c in caps if c.mover != color]
        out.append(f"in this game {who_words} has lost "
                   + (f"no {unit}" if not lost else f"{len(lost)} {unit}{'s' if len(lost) > 1 else ''}, not {ev.count}")
                   + (f" on {ev.sq}" if ev.sq else "") + ": "
                   + (f"its losses so far are {', '.join(theirs)}" if theirs else "nothing of it has been captured yet"))
    return out


def _coach_move_issues(text: str, ctx: CheckContext) -> list[str]:
    """In a game, a move the coach says it made must be one the engine made."""
    played = ctx.game_engine_moves
    if played is None:
        return []
    out = _move_number_issues(text, played, ctx.student_color) + _students_move_issues(text, ctx) + _coach_capture_issues(text, ctx)
    out += _detector("student_capture", ctx, _fail_open(_student_capture_issues, text, ctx))  # plan 31.10 M3
    text = _MOVE_NUMBER.sub("", text)
    norm = {m.rstrip("+#") for m in played}
    for m in _COACH_MOVE.finditer(text):
        sans, _ = _to_san(_told_move_as_san(m.group("rest")))
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


def _told_move_as_san(rest: str) -> str:
    """fix1102 K5: «Мой первый ход — пешка с c2 пошла на c4» — a move told in words from-to names its destination;
    the square it left («c2») is no move of its own. The phrase at the start of *rest* becomes the move it tells
    («c4», «Nf6»), the rest kept."""
    low = rest.lower().replace("ё", "е")
    lead = len(low) - len(low.lstrip())
    for ptype, rx in _MOVE_CLAIMS:
        m = rx.match(low, lead)
        if m and m.groupdict().get("b"):
            letter = "" if ptype == chess.PAWN else chess.piece_symbol(ptype).upper()
            return rest[:lead] + letter + m["b"] + rest[m.end():]
    return rest


def _last_move_issues(text: str, last: str) -> list[str]:
    text = _MOVE_NUMBER.sub("", text)
    out = _castling_issues(text, last)
    for m in _MY_REPLY.finditer(text):
        if _in_a_line(text, m.start()):
            continue
        # «e7–e5», «e5:d4» — no spaces: «d6: e5 теперь под защитой», «Nf6 — e4 под ударом» explain the move
        rest = re.sub(r"([KQRBNКФЛС]?)[a-h][1-8][–—:]([a-h][1-8])", r"\1\2", m.group("rest"))
        rest = _told_move_as_san(rest)
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
    if ctx.current is None or "?" in text or _is_hypothetical(text, original, 0, whole=True, ctx=ctx) \
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
    if not m or _CONTRAST.search(text) or _is_hypothetical(text, original, 0, whole=True, ctx=ctx):
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
    # A claim told right after a move («Хорошо конём на d5: он атакует слона e3», «Сыграй Nd5. Конь атакует слона
    # e3», «Ферзь может встать на e7. Или на c7, тогда …») may be about the board after that move: a cut of the board
    # as it is is kept only when the claim is false there too (_after_told_move, review-fp 03.11).
    told, snapshot = [], None
    if ctx.current is not None and sentence.strip() and not _lesson(ctx):
        try:
            told = _told_moves(sentence, ctx)
            # (a sentence replayed for the voice check, *spoken*: its issues are dropped anyway — no re-judging)
            if (told or ctx.told_before) and not spoken:
                import copy

                snapshot = copy.deepcopy(ctx)
        except Exception:  # noqa: BLE001 — a bonus: the sentence is still judged on the board as it is
            logger.debug("told moves failed", exc_info=True)
            told, snapshot = [], None
    issues = _check_sentence(sentence, ctx)
    if issues and snapshot is not None and _switch_mode("after_told_move", ctx) == "on":
        try:
            issues = _after_told_move(sentence, snapshot, issues, told + [m for m in snapshot.told_before if m not in told])
        except Exception:  # noqa: BLE001
            logger.debug("after-told-move judging failed", exc_info=True)
    if ctx.current is not None and sentence.strip() and not _lesson(ctx):
        ctx.told_before = told
    if issues:
        ctx.line_scene = line_before
        if line_before is not None:
            line_before["age"] = age_before
        ctx._line_end, ctx._line_advice, ctx.forced_line = kept
        if not spoken:
            ctx.relation_state = relation_kept
    return issues


# The issues that judge a claim about where things stand on the board as it is — an attack, a reach, a piece on a
# square: such a claim told right after a move may be about the board after it.
_STANDING_ISSUE = re.compile(
    r"is not attacked by anything in this position|on the board now:|does not reach|does not attack|"
    r"^there is no (?:white |black )?(?:king|queen|rook|bishop|knight|pawn) on [a-h][1-8] in this position|"
    r"^no (?:king|queen|rook|bishop|knight|pawn) attacks [a-h][1-8]|is not on a line with")
# «конём на d5», «слоном жэ пять» → «слоном g5»: an instrument with its square, «на» dropped by the transcription.
_TOLD_WITH = re.compile(r"(?<![а-яa-z])(?P<piece>ладь[её]й|кон[её]м|слоном|ферз[её]м|корол[её]м|пешкой)\s+(?:на\s+)?"
                        r"(?P<to>[a-h][1-8])(?![0-9])(?!\s*[-–—]?\s*[a-h][1-8](?![0-9]))")
# «Слон может пойти на d6», «конь может прыгнуть на b3», «ферзь встанет на e7»: a piece told to go, in the infinitive
# after a modal or in the future (prose_moves reads the present and the future of a few verbs only).
_TOLD_GOES = re.compile(r"(?<![а-яa-z])(?P<piece>конь|слон|ладья|ферзь|король|пешка)(?:\s+[a-h][1-8])?(?:\s+(?!на\s|в\s)[а-я]+){0,2}?\s+"
                        r"(?:пойти|встать|прыгнуть|перейти|уйти|отойти|отступить|вернуться|выйти|переместиться|"
                        r"пойд[её]т|встанет|прыгнет|перейд[её]т|уйд[её]т|отойд[её]т|отступит|вернется|выйдет)\s+(?:на|в)\s+"
                        r"(?P<to>[a-h][1-8])(?![0-9])")
_TOLD_PIECE = re.compile(r"(?<![а-яa-z])(?P<piece>конь|слон|ладья|ферзь|король|пешка|кон[её]м|слоном|ладь[её]й|ферз[её]м|"
                         r"корол[её]м|пешкой|коня|слона|ладью|ферзя|пешку)(?![а-я])")
# «Или на c7, тогда …», «Либо сразу на h4»: another square for the piece the sentence before moved.
_ELLIPTIC_SQUARE = re.compile(r"^[\s*_«\"(-]*(?:или|либо|а\s+можно|можно\s+и|or)\s+(?:же\s+|даже\s+|сразу\s+)?(?:на|в|to)\s+"
                              r"(?P<to>[a-h][1-8])(?![0-9])", re.IGNORECASE)


def _told_moves(sentence: str, ctx: CheckContext) -> list:
    """The legal moves of the side to move *sentence* names — in words («конём на d5», «слоном g5»), in notation
    (a piece move, a capture, castling; a bare «e4» is a square), or as another square for the piece of the move the
    sentence before told («Или на c7»). At most three, in order."""
    from src.move_words import prose_moves, resolve, _ptype

    board = ctx.current
    text = sentence.replace("ё", "е")
    low = text.lower()
    out: list = []

    def add(mv):
        if mv is not None and mv in board.legal_moves and mv not in out:
            out.append(mv)

    for pm in prose_moves(text, board):
        add(pm["move"])
    for rx in (_TOLD_WITH, _TOLD_GOES):
        for m in rx.finditer(low):
            ptype = _ptype(m["piece"])
            if ptype is not None:
                add(resolve(board, ptype, chess.parse_square(m["to"]))[1])
    converted, _ = _to_san(text)
    for mv in _MOVE.finditer(converted):
        san = mv["san"]
        if san[0] not in "KQRBNO" and "x" not in san:
            continue
        try:
            add(board.parse_san(san))
        except ValueError:
            continue
    ell = _ELLIPTIC_SQUARE.match(low)
    if ell:
        # the piece: the one the sentence before moved, else the first piece it named (it is read before this sentence
        # is judged: ctx.sentence_now is still the sentence before)
        to = chess.parse_square(ell["to"])
        kinds = [(board.piece_type_at(prev.from_square), prev.from_square) for prev in ctx.told_before]
        named = _TOLD_PIECE.search((ctx.sentence_now or "").replace("ё", "е").lower())
        if not kinds and named and _ptype(named["piece"]) is not None:
            kinds = [(_ptype(named["piece"]), None)]
        for ptype, frm in kinds:
            if ptype is not None:
                # that piece; else the only piece of its kind that gets there («Конь может пойти на b3. Или на h4» — the
                # other knight)
                add(resolve(board, ptype, to, from_sq=frm)[1] or resolve(board, ptype, to)[1])
    return out[:3]


def _after_told_move(sentence: str, snapshot: CheckContext, issues: list, told: list) -> list:
    """*issues* without the cuts of a standing claim (_STANDING_ISSUE) that is true on the board after one of the moves
    *told* (this sentence's, then the sentence before's) — judged by the same checks on a copy of the context as it was
    before this sentence, with the move made and the same side to move. Every other issue stays; a standing claim false
    there too stays cut."""
    # a verdict that names the told move already judged the claim with it («after Bg5 Black can still play O-O», «Ba6
    # still hits f1») — the claim is about the move, not a standing one to re-judge after it
    sans = set()
    for mv in told[:3]:
        try:
            sans.add(snapshot.current.san(mv).rstrip("+#"))
        except Exception:  # noqa: BLE001
            continue
    standing = [i for i in issues if _STANDING_ISSUE.search(i)
                and not any(re.search(r"(?<![A-Za-z0-9])" + re.escape(x) + r"(?![0-9])", i) for x in sans)]
    if not standing:
        return issues
    import copy

    for k, mv in enumerate(told[:3]):
        clone = snapshot if k == len(told[:3]) - 1 else copy.deepcopy(snapshot)
        after = clone.current.copy(stack=False)
        after.push(mv)
        after.turn = clone.current.turn  # the same side to move: «твой», «соперник» keep their meaning
        after.ep_square = None
        clone.add(after.fen(), derived=True)
        clone.current = next((b for b in clone.boards if clone._key(b) == clone._key(after)), after)
        clone.told_before = []
        got = _check_sentence(sentence, clone)
        if not any(_STANDING_ISSUE.search(i) for i in got):
            return [i for i in issues if i not in standing]
    return issues


def _rule_scope(text: str, ctx: CheckContext) -> Optional[str]:
    """*text* without its rule talk (src/claim_scope.rule_spans) when the switch ``rule_scope`` is on, else None (the
    sentence is judged whole). In shadow the parts are only recorded. A yes/no opening pins the head of a law frame
    when the question is about this board (no conditional in it): «Нет — рокироваться нельзя, пока король под шахом»
    still answers «Можно мне рокироваться?»; the condition after «пока» stays a rule. Fail-open."""
    try:
        from src.claim_scope import CONDITIONAL, rule_spans, without_spans

        question = getattr(ctx, "question", "") or ""
        spans = rule_spans(text, anchored_answer=bool(question.strip()) and not CONDITIONAL.search(question))
        if not spans:
            return None
        mode = _switch_mode("rule_scope", ctx)
        if mode == "on":
            return without_spans(text, spans)
        if mode == "shadow":
            record_shadow(ctx, "rule_scope", ["rule talk, not this board: " + " | ".join(text[s:e].strip()[:120] for s, e in spans)])
    except Exception:  # noqa: BLE001 — the scope must never break a turn
        logger.debug("rule scope failed", exc_info=True)
    return None


def _check_sentence(sentence: str, ctx: CheckContext) -> list[str]:
    if sentence.strip():
        ctx.scene_age += 1  # the scene a move of this sentence sets is age 0; the explanation after it still sees it
        ctx.scene_before = (ctx.scene, ctx.scene_san, ctx.scene_age) if ctx.scene is not None else None
        ctx.scene_trail = []
        ctx.written_trail = []
        ctx.sentence_before = ctx.sentence_now
        ctx.sentence_now = sentence
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
    # Rule talk is not a claim about this board (fix1102 K4, src/claim_scope.rule_spans): «Рокировка разрешена, только
    # если …», "you can't castle while your king is in check", «Двойной знак означает …», «Запись хода состоит из …:
    # К:d5 — конь берёт на d5». Every detector that judges the position reads the sentence without those parts; the
    # detectors that judge a law (src/answer_check_rules.law_issues) and the opening book read all of it.
    law_text, law_lowered = text, lowered
    hidden = _rule_scope(text, ctx)
    if hidden is not None:
        text = hidden
        lowered = text.lower()
    # Written moves first: the positions they lead to join the boards of the
    # turn, and the claims after them («Rg1, ладья нападает на ферзя») are judged there.
    san_issues = _history_issues(text, ctx) + _san_issues(text, ctx) + _recapture_issues(text, ctx)
    from src.castle_reason import castle_advice_issues as _castle_advice_issues
    from src.castle_reason import castle_reason_issues as _castle_reason_issues
    from src.castle_reason import castle_state_issues as _castle_state_issues
    from src.answer_check_openings import opening_book_issues
    from src.answer_check_rules import rules_issues

    issues = (_move_issues(lowered) + _attack_issues(lowered, text, ctx) + san_issues
              + _opening_issues(law_text) + _opening_identity_issues(text, ctx) + _told_move_issues(lowered, text, ctx)
              + _fact_issues(lowered, text, ctx)
              + _plan_move_issues(lowered, text, ctx)
              + rules_issues(lowered, ctx, law_lowered=law_lowered) + _coach_move_issues(text, ctx) + _scene_issues(text, ctx)
              # the game's own record (plan 31.10 P1): the kind of reply to a check, a capture told as free, a loss
              + _detector("block_kind", ctx, _fail_open(_block_kind_issues, text, ctx))
              + _detector("free_capture", ctx, _fail_open(_free_capture_issues, lowered, text, ctx))
              + _detector("gave_up", ctx, _fail_open(_gave_issues, lowered, text, ctx))
              # a move proposed in words that cannot be played now (voice 02.11)
              + _detector("word_move", ctx, _fail_open(_word_move_issues, text, ctx))
              # …a written move after a proposal word («Сыграй Qg4» with no way there), review-miss 02.11 #11
              + _detector("word_move_san", ctx, _fail_open(_word_move_san_issues, text, ctx))
              # castling proposed when it cannot be played («Рокируйся коротко», «Сыграй O-O», «королём на g1»)
              + _detector("castle_advice", ctx, _fail_open(_castle_word_move_issues, text, ctx)
                          + _fail_open(_castle_advice_issues, lowered, ctx))
              # the reason given for castling being impossible, judged against the rule (voice1102: «поле f2 под боем»)
              + _detector("castle_reason", ctx, _fail_open(_castle_reason_issues, lowered, ctx))
              # a named side said to have castled, or still / no longer able to (review-miss 03.11)
              + _detector("castle_state", ctx, _fail_open(_castle_state_issues, lowered, ctx))
              # a check claimed for a move or for the board now (review-miss 03.11)
              + _detector("check_claim", ctx, _fail_open(_check_claim_issues, text, ctx))
              # a material claim with no amount, by the sign of the balance (review-miss 03.11)
              + _detector("material_direction", ctx, _fail_open(_material_direction_issues, lowered, ctx))
              + _asked_motif_issues(lowered, text, ctx) + _composition_issues(lowered, text, ctx)
              # ECO codes, variations named after a person, «usually X» — by the ECO book (prod check 29.10)
              + opening_book_issues(law_text, ctx))
    from src.answer_check_facts import record_fact_issues

    facts = record_fact_issues(lowered, text, ctx)
    if any("advise only a move the piece can make" in i for i in facts):
        # the move advised in words is told once: by the facts' reader (src/answer_check_facts.advice_move_issues)
        issues = [i for i in issues if "proposes a move that cannot be played" not in i]
    issues += facts
    # «белые отдали ферзя за ладью» about a recorded game: against the game's exchanges (src/trade_claims.py, plan 31.10;
    # fail-open — a broken trade check never blocks an answer).
    from src.trade_claims import trade_issues

    try:
        issues += trade_issues(text, ctx)
    except Exception:  # noqa: BLE001
        logger.debug("trade check failed", exc_info=True)
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
# «то есть», «точнее», «вернее» alone refine what was said — «пешка d5 поддерживается пешкой e7... точнее, стоит как есть)»,
# «Смотри на свою пешку e5... точнее, на то, что …» (live 02.11 ep-expired, st2#3): the rest of the same sentence, not
# thinking aloud. A retraction («нет», «стоп», «хм», "wait") is.
_SELF_CORRECTION = re.compile(r"^\W*(?:нет|стоп|хм|подожди|wait|no)(?:[,—:\s]|$)", re.IGNORECASE)


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
