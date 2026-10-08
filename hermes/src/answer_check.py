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

# «конь с f3 прыгает на d5», «слон уходит с c5 на a7», «knight from f3 to d5»
_MOVE_CLAIMS = []
for _ptype, _pat in _RU_PIECES:
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid1>(?:\s+{_STOP_MOVE}+?){{0,2}}?)\s+(?:с|со|из)\s+(?:пол[яе]\s+)?(?P<a>{SQ})"
        rf"(?P<mid2>(?:\s+{_STOP_MOVE}+?){{0,3}}?)\s+на\s+(?P<b>{SQ})(?![0-9])")))
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"\s+(?:с\s+)?(?P<a>{SQ})\s*[-–]\s*(?P<b>{SQ})(?![0-9])")))
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid1>(?:\s+{_STOP_MOVE}+?){{0,3}}?)\s+на\s+(?P<b>{SQ})"
        rf"(?P<mid2>(?:\s+{_STOP_MOVE}+?){{0,1}}?)\s+(?:с|со)\s+(?:пол[яе]\s+)?(?P<a>{SQ})(?![0-9])")))
for _ptype, _pat in _EN_PIECES:
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid1>(?:\s+{_STOP_MOVE}+?){{0,2}}?)\s+(?:from|on)\s+(?P<a>{SQ})"
        rf"(?P<mid2>(?:\s+{_STOP_MOVE}+?){{0,3}}?)\s+(?:to|onto)\s+(?P<b>{SQ})(?![0-9])")))

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
              r"попада[её]т|попад[её]т|окажется|оказывается|становится|стоит|стоящ\w*|будет|уже|теперь|сейчас)\s+)?")
_EN_PLACED = (r"(?:(?:sits|stands|lands|goes|comes|moves|arrives|jumps|hops|drops|swings|is|gets|"
              r"sitting|standing|landing|ends\s+up|will\s+be|would\s+be)\s+)?")
# «на g1, бьющая h4», "on g1, which attacks h4": the comma of a participle or
# relative clause stays inside the claim; any other comma ends it.
_COMMA_CLAUSE = r"(?:,(?=\s*(?:котор\w+|что|which|that|who|[а-яa-z]+(?:ющ|ящ|ащ|ущ|ing)\w*)(?![а-яa-z])))?"
_ATTACK_CLAIMS = []
for _ptype, _pat in _RU_SUBJECTS:
    _ATTACK_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"\s+{_RU_PLACED}(?:на\s+)?(?P<a>{SQ})(?![0-9]){_COMMA_CLAUSE}(?P<mid>{_STOP_MID}{{0,40}}?)"
        rf"(?P<verb>{_RU_VERBS})(?P<targets>{_STOP}{{0,90}})")))
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
    _W + r"(?:он|она|it|he|she)\s+(?:сам\w*\s+|же\s+|also\s+|now\s+|still\s+|itself\s+)?(?:нападает\s*:\s*|атакует\s*:\s*)?"
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
_NEGATION = re.compile(r"(?:^|[\s*_«\"(])(?:не|ни|нет|never|not|n't|cannot|can't)[*_]*\s*$|(?:не|not)\s+\w+\s*$"
                       r"|[a-z]+n'?t\s*$", re.IGNORECASE)  # "doesn't attack", "won't hit"
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
_CYR_PIECE_FILE = re.compile(r"(?<![А-Яа-яЁёA-Za-z])(Кр|[КСЛФKQRBN])([x:×]?)([асе])(?=[1-8](?![0-9]))")
_CYR_FILE = {"а": "a", "с": "c", "е": "e"}


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
            self.add(fen)
        for pgn in re.findall(r'"pgn"\s*:\s*"([^"]{8,})"', text or ""):
            self.add_line(pgn.replace("\\n", " "))

    @staticmethod
    def _key(board: chess.Board) -> str:
        return board.board_fen() + (" w" if board.turn else " b")

    def is_given(self, board: chess.Board) -> bool:
        return self._key(board) in self.given

    def add(self, fen: Optional[str], derived: bool = False) -> None:
        if not fen:
            return
        try:
            board = chess.Board(fen)
        except ValueError:
            return
        key = self._key(board)
        if not derived:
            self.given.add(key)
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
        self.add(board.fen())
        for san in _split_moves(pgn):
            try:
                board.push_san(san)
            except ValueError:
                return
            self.add(board.fen())


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


# A sentence about what could be, not what is: a line of play, a condition, a
# future form, or a move written before the claim.
_HYPO = re.compile(
    r"(?<![а-яa-z])(?:после|если|когда|пока|тогда|будет|будут|бы|сыграй|сыграйте|сыграв|сыграть|играй|играйте|"
    r"поставь|поставьте|переведи|переведите|представь|допустим|скажем|вместо|"
    r"after|if|when|once|then|would|will|could|should|were|play|plays|played|playing|put|place|instead|"
    r"imagine|suppose|say|let'?s)(?![а-яa-z])", re.IGNORECASE)


def _is_hypothetical(text: str, original: str, upto: int, whole: bool = False) -> bool:
    """A marker or a written move BEFORE the claim; what follows it («у чёрных
    лишняя пешка, и после Rg1 Nxa4…») does not excuse the claim itself — a
    claim about the position after those moves holds on the derived boards.
    *whole*: the whole sentence counts («твой конь на c5 — если бы он туда
    попал — доминировал бы»), for claims about whose piece stands where."""
    if _HYPO.search(text if whole else text[:upto]):
        return True
    converted, _ = _to_san(original[:upto])
    return any(m["san"] for m in _MOVE.finditer(converted) if m["num"] or m["bdots"] or m["san"][0] in "KQRBN")


# Verbs that say a piece reaches a square now — blockers count; «смотрит»,
# "eyes", "x-rays" look through pieces and are not checked for them.
_HARD_VERB = re.compile(r"бь[её]т|бьют|атаку|напада|угрожа|держ|защища|контролир|вилк|"
                        r"attack|hit|fork|target|threaten|defend|protect|control|cover|guard|pin", re.IGNORECASE)
_FUTURE_VERB = re.compile(r"буд(?:ет|ут)|бы\b|would|will|can|could|с\s+(?:нападением|темпом|атакой|ударом)", re.IGNORECASE)


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
    now = about_now or not _is_hypothetical(text, original if original is not None else text, m.start())
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


_NEGATED_WORD = re.compile(r"(?<![а-яa-z])(?:не|ни|нет|никак|нельзя|not|never|nor|cannot|n't)(?![а-яa-z])|[a-z]+n'?t(?![a-z])",
                           re.IGNORECASE)


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


def _attack_issues(text: str, original: Optional[str] = None, ctx: Optional["CheckContext"] = None) -> list[str]:
    """*text* is lowercased for the piece words; *original* keeps the case of
    written moves (Rg1, Лг1) for the subject scan."""
    issues = []
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
        candidates = ([(prev, [prev.turn])] if prev is not None and prev.turn in colors else []) \
            + [(b, colors) for b in ordered]
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
                    trial.push(move)
                    prev, prev_trusted = trial, trusted
                    ctx.add(trial.fen(), derived=True)  # a line written in the answer goes on from here
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
    r"(?P<v>ничем\s+не\s+защищ\w+|не\s+защищ\w+|без\s+защиты|беззащит\w+|висит|повис\w*|под\s+боем|под\s+ударом|атакован\w*|защищ[ёе]н\w*|"
    r"not\s+defended|not\s+protected|undefended|unprotected|hanging|en\s+prise|loose|under\s+attack|attacked|defended|protected|covered|guarded)"
    rf"|(?P<v2>висит|повис\w*|hangs|hanging)\s+(?:is\s+)?(?:the\s+)?(?P<p2>{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<b>{SQ})(?![0-9])"
    rf"|(?P<v3>ничто\s+не\s+защищает|никто\s+не\s+защищает|nothing\s+(?:defends|protects|covers|guards))\s+"
    rf"(?:(?:the\s+)?(?:{_PIECE_ANY}\s+)?(?:на\s+|on\s+)?(?P<c>{SQ})(?![0-9])|(?P<pron>it|её|ее|его)(?![а-яa-z])))", re.IGNORECASE)
_HANGING_KIND = (("ничем не защищ", "undefended"), ("не защищ", "undefended"), ("без защиты", "undefended"),
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
        if kind == "hanging" and re.match(r"\s+(?:в\s+воздухе|in\s+the\s+air|без\s+дела)", text[m.end():]):
            continue  # «ладья висит в воздухе и ничего не делает»: idle, not en prise (replay, 2026-10-05)
        if kind != "undefended" and _NEGATION.search(text[: m.start(verb and ("v" if m["v"] else "v2" if m["v2"] else "v3"))]):
            continue  # «не висит», "is not hanging"
        if _is_hypothetical(text, original, m.start()):
            continue
        sq = chess.parse_square(sq_name)
        seen = False
        for board in ctx.boards:
            piece = board.piece_at(sq)
            if piece is None:
                continue
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


_FUTURE_FILL = re.compile(r"останеш|останет|останут|будеш|будет|будут|окажеш|окажет|окажут|получиш|получит|"
                          r"will|would|'ll|end\s+up|going\s+to|get\s+left", re.IGNORECASE)


def _material_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None:
        return []
    issues = []
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
            if not any(_material_holds(b, color, kind, points, n, more, balance) for b in ctx.boards[1:] or ctx.boards):
                issues.append(f"material: {_imbalance(ctx.current)} (not: {m.group(0).strip()})")
    for m in _MATERIAL_EQUAL.finditer(text):
        if _is_hypothetical(text, original, m.start()):
            continue
        if _NEGATION.search(text[: m.start()]):
            continue  # «материал не равен»
        if not any(_counts(b, chess.WHITE)["nonpawn"] + _counts(b, chess.WHITE)[chess.PAWN]
                   == _counts(b, chess.BLACK)["nonpawn"] + _counts(b, chess.BLACK)[chess.PAWN]
                   for b in ctx.boards[1:] or ctx.boards):
            issues.append(f"material: {_imbalance(ctx.current)} (not equal)")
    return issues


# «твой конь на c5» (the student's), «слон на e1» (a rook stands there).
_OWN_PIECE = re.compile(
    _B2 + rf"(?P<own>тво[йяеию]\w*|ваш\w*|your|мо[йяеию]\w*|наш\w*|my|our)\s+(?:(?:белый|белая|ч[её]рный|ч[её]рная|white|black)\s+)?"
    rf"(?:(?P<piece>{_PIECE_ANY})\s+(?:на\s+|on\s+)?(?P<a>{SQ})|(?P<a2>{SQ})[- ](?P<piece2>pawn|knight|bishop|rook|queen|king))(?![0-9])",
    re.IGNORECASE)


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
    r"(?:'s|'re)?\s+(?:сейчас\s+|уже\s+|is\s+|are\s+|was\s+|were\s+|gets\s+|now\s+|still\s+)*"
    r"(?P<verb>атакуют|атакует|бьют|бь[её]т|держат|держит|защищают|защищает|прикрывают|прикрывает|"
    r"attacked|hit|defended|protected|covered|guarded|pinned|threatened)\s+"
    r"(?:сразу\s+|только\s+|only\s+|just\s+)?(?:(?:две|три|two|three)\s+)?(?:ч[её]рн\w+\s+|бел\w+\s+|black\s+|white\s+)?(?:фигур\w*\s*[—–-]?\s*|pieces?\s*[—–:-]?\s*)?"
    r"(?:by\s+)?(?P<subjects>(?:(?:the\s+|your\s+|my\s+|a\s+)?(?:(?:конь|слон|ладья|ферзь|король|пешка|knight|bishop|rook|queen|king|pawn)\s+(?:на\s+|on\s+|from\s+|с\s+)?[a-h][1-8]|[a-h][1-8][- ](?:pawn|knight|bishop|rook|queen|king))"
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
    rf"(?:the\s+)?(?:(?:{_PIECE_ANY})\s+(?:on\s+|на\s+)?)?(?:(?P<b>{SQ})|(?P<it>it|её|ее|его))(?![0-9])", re.IGNORECASE)


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
        if a == target:
            continue
        piece = ctx.current.piece_at(a)
        if piece is None:
            continue  # an empty square now: a line of play, not judged
        if target == _ep_victim(ctx.current, a):
            continue  # «e5 бьёт пешку d5» on the move after d7-d5: en passant
        if target not in ctx.current.attacks(a):
            issues.append(f"the {_NAMES[piece.piece_type]} on {m['a']} does not reach {target_name}")
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
    if _DENIES.search(text):
        return _legality_issues(text, original, ctx)
    return (_hanging_issues(text, original, ctx) + _pin_issues(text, original, ctx)
            + _material_issues(text, original, ctx) + _presence_issues(text, original, ctx)
            + _instrument_issues(text, original, ctx) + _object_first_issues(text, original, ctx)
            + _square_subject_issues(text, original, ctx) + _legality_issues(text, original, ctx)
            + _object_typed_issues(text, original, ctx) + _not_attacked_issues(text, original, ctx)
            + _not_defended_issues(text, original, ctx) + _eval_issues(text, original, ctx))


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


def foreign_word_issue(sentence: str, language: Optional[str]) -> Optional[str]:
    """An English chess word in a sentence that is otherwise in *language* (ru/kk), or None."""
    if language not in ("ru", "kk", "kz") or not sentence:
        return None
    cyrillic = sum(1 for ch in sentence if "а" <= ch.lower() <= "я" or ch.lower() in "ёәғқңөұүһі")
    if cyrillic < MIN_LANGUAGE_LETTERS:
        return None
    m = _FOREIGN_WORD.search(_NOT_LANGUAGE.sub(lambda mm: " " * len(mm.group(0)), sentence))
    if not m:
        return None
    name = {"ru": "Russian", "kk": "Kazakh", "kz": "Kazakh"}[language]
    return f"«{m.group(0)}» is an English word in a {name} sentence: say it in {name} (белые, чёрные, сразу, мат, пат, темп)"


_TOPIC_TARGET = re.compile(
    rf"(?:бь[её]т|бьют|атакует|атакуют|нападает|нападают|защищает|защищают|прикрывает|прикрывают|держит|держат|"
    rf"attacks|hits|defends|protects|covers|guards|eyes|eyeing|attacking|hitting|defending)\s+"
    rf"(?:на\s+|по\s+|в\s+|the\s+|your\s+|my\s+)?(?:{_PIECE_ANY}\s+)?(?:на\s+|on\s+)?({SQ})(?![0-9])", re.IGNORECASE)


# «Сыграй Rg1», «лучше Rg1», «можно поставить ладью на g1», "play Rg1", "you
# should put the rook on g1": the coach recommends a move. Its quality is the
# engine's to judge (src/server.py verifies it before the sentence is shown).
_PROPOSES = re.compile(
    r"(?<![а-яa-z])(?:сыграй(?:те)?|играй(?:те)?|поставь(?:те)?|ставь(?:те)?|пойди(?:те)?|ходи(?:те)?|бей(?:те)?|"
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
    for m in _PROPOSES.finditer(text):
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
            return ctx.current, move, ctx.current.san(move)
        try:
            from src.move_words import prose_moves

            for pm in prose_moves(clause, ctx.current):
                if pm["move"] is not None:
                    return ctx.current, pm["move"], pm["san"]
        except Exception:  # noqa: BLE001 — words are a bonus on top of notation
            logger.debug("prose move parse failed", exc_info=True)
    converted, _ = _to_san(text)
    for mv in _MOVE.finditer(converted):
        san = mv["san"]
        if san[0] not in "KQRBNO" and not mv["num"] and not mv["bdots"] and "x" not in san:
            continue
        if not _PRAISED.match(converted, mv.end()) or _NEGATION.search(converted[max(0, mv.start() - 24): mv.start()]):
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


# The move named as the answer to the task: «Первый ход — **...Rxf3!**», «Здесь решает 1...Qh1+!», "The key
# move is Nf6+". On production 07.10 four of 187 lesson puzzles were answered from a diagram of the lesson's
# text — another position, often for the other side («1...Ba6!» with White to move) — and the check, which
# reads a bare capture or a numbered move as a step of some line, let them through.
_ANNOUNCED = re.compile(
    r"(?:(?<![а-яa-z])(?:перв\w*\s+ход\w*|решает|решающ\w+\s+ход|решени\w*|лучш\w+\s+ход\w*|ключев\w+\s+ход\w*|"
    r"начина\w*\s+с|начн\w*\s+с)(?:\s+(?:здесь|тут|в\s+задаче|в\s+этой\s+позиции))?|"
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
            # Any position of the turn: the board, a tool's example, a game, or a line the answer wrote before.
            if (black and board.turn != chess.BLACK) or (white and board.turn != chess.WHITE):
                continue
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


def check_sentence(sentence: str, ctx: Optional[CheckContext] = None) -> list[str]:
    """The reasons *sentence* is wrong on the board; [] when nothing checkable is wrong."""
    ctx = ctx or CheckContext.from_fens()
    if is_meta(sentence):
        return [META_ISSUE]
    wrong_language = language_issue(sentence, ctx.language) or foreign_word_issue(sentence, ctx.language)
    if wrong_language:
        return [wrong_language]
    text = sentence.replace("ё", "е")
    # Speech transcripts write files in Cyrillic lookalikes: «слон на е2», «пешка с4» (voice, 2026-10-06).
    # …and transliterated ones: «конь на ф3», «ферзь на б6», «пешка г4», «ладья х1» (2026-10-08).
    text = re.sub(r"(?<![а-яА-Яa-zA-Z])([асебдфгхАСЕБДФГХ])(?=[1-8](?![0-9]))",
                  lambda m: {"а": "a", "с": "c", "е": "e", "б": "b", "д": "d", "ф": "f", "г": "g", "х": "h"}[m.group(1).lower()], text)
    lowered = text.lower()
    # Written moves first: the positions they lead to join the boards of the
    # turn, and the claims after them («Rg1, ладья нападает на ферзя») are judged there.
    san_issues = _history_issues(text, ctx) + _san_issues(text, ctx) + _recapture_issues(text, ctx)
    from src.answer_check_rules import rules_issues

    issues = (_move_issues(lowered) + _attack_issues(lowered, text, ctx) + san_issues
              + _opening_issues(text) + _fact_issues(lowered, text, ctx) + _plan_move_issues(lowered, text, ctx)
              + rules_issues(lowered, ctx))
    if not san_issues:
        issues += _announced_move_issues(text, ctx)
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
    return list(dict.fromkeys(issues))


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
    r"white|black|белые|белых|ч[её]рные|ч[её]рных)" + _E,
    re.IGNORECASE)


# A piece letter written in Cyrillic by sound or by look: «Нf6+», «Рh8+», «Вf5» (production
# lesson sweep 2026-10-07). Russian notation has no such letters (it is К, Л, С, Ф), so they
# are the Latin N, R, B the rest of the answer uses.
_LOOKALIKE_PIECE = re.compile(r"(?<![А-Яа-яЁёA-Za-z])([НРВ])(?=[x:×]?[a-h][1-8](?![0-9]))")
_LOOKALIKE_MAP = {"Н": "N", "Р": "R", "В": "B"}


def normalize_notation(text: str) -> str:
    """«Нf6+» → «Nf6+», «Рh8+» → «Rh8+», «Вf5» → «Bf5»; Russian letters typed as Latin ones —
    «Cc4» → «Bc4», «Kf7+ (конь с g5…)» → «Nf7+», «1.e4 e5 2.Kf3» → «2.Nf3»."""
    if not text:
        return text
    text = _LOOKALIKE_PIECE.sub(lambda m: _LOOKALIKE_MAP[m.group(1)], text)
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
RELEASE_STARTS = os.environ.get("COACH_STREAM_SENTENCE_STARTS", "0").strip().lower() not in ("0", "false", "no", "off", "")
# «Be3, блокируя... нет, точнее защищая f1»: a self-correction after an ellipsis is the model thinking aloud.
_SELF_CORRECTION = re.compile(r"^\W*(?:нет|стоп|хм|то\s+есть|точнее|вернее|wait|no)(?:[,—:\s]|$)", re.IGNORECASE)


# A word that leans on the sentence before it: when that sentence was left out, «Затем выводи короля…»
# opened what was left of the answer (lucena, the newest code, 2026-10-08).
_LEANS_BACK = re.compile(
    r"^(\s*(?:[>#-]+\s*)?)([*_]{0,2})(?:затем|потом|после\s+этого|дальше|далее|следом|кроме\s+того|также|тоже|then|"
    r"after\s+that|next|also|besides)(?![а-яёa-z])([*_]{0,2})[\s,—–-]*", re.IGNORECASE)


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

    def __init__(self, ctx: Optional[CheckContext] = None, enabled: bool = True, release_starts: Optional[bool] = None):
        self.ctx = ctx or CheckContext.from_fens()
        self.enabled = enabled
        self.release_starts = RELEASE_STARTS if release_starts is None else release_starts
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

    def feed(self, text: str) -> list[tuple[str, list[str], str]]:
        if not self.enabled:
            return [(text, [], text)] if text else []
        self._buf += text
        out: list[tuple[str, list[str], str]] = []
        sentences, self._buf = _split_sentences(self._buf)
        if len(self._buf) > self.MAX_HOLD:
            sentences.append(self._buf)
            self._buf = ""
        for sentence in sentences:
            sentence = normalize_notation(sentence)
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
        rest, self._buf = normalize_notation(self._buf), ""
        full, self._released = self._released + rest, ""
        if not rest:
            return []
        return [(rest, check_sentence(full, self.ctx) if self.enabled else [], full)]


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
    r"|<\s*/?\s*(?:function_calls|invoke|parameter)\b[^>\n]{0,80}>"
    r"|(?m:^[ \t]*(?:parameter\s+)?name=\"[^\n]{0,60}$)", re.IGNORECASE)                    # a stray « name="» line


def strip_leaks(text: str) -> str:
    """*text* without tool-call markup the model wrote as text."""
    return _LEAKS.sub("", text) if text else text
