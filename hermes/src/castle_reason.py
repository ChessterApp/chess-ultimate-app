"""Why castling is impossible: the reason the coach names, judged against the rule (voice1102, 02.11).

Live 02.11 (voice, the student White, r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq): «Я не могу сделать
рокировку, потому что поле f2 под боем слона… слон на c5 бьёт поле f2, и по правилам проходить через битое поле при
рокировке нельзя». Short castling IS illegal there, but because the bishop d3 hits f1; f2 is not on the king's path.
The engine note said both facts and the model merged them; the check judged only whether castling is possible, so a
right conclusion carried a false reason through.

The castling rule, as python-chess and src/board_rules.castling_status apply it: the king is not in check; the squares
it passes and lands on are not attacked (O-O: f1, g1; O-O-O: d1, c1 — b1 only has to be empty); the squares between
king and rook are empty; the rights remain. A reason the sentence gives for «castling is impossible» is read as one
of these and judged:

  * an attacked square («поле f2 под боем», «слон c5 бьёт поле f2», «через битое поле f2», "f2 is attacked by …",
    «король пройдёт через f2»): false when the square is not on the king's path for that castling — on any board, so
    a told line or a hypothetical changes nothing — or, on a board the sentence pins (now, or after the move it tells),
    when nothing of the other side attacks it, or the attacker it names does not;
  * a check («король под шахом»): false when that king is not attacked;
  * a piece in the way («конь на g1 мешает», «между королём и ладьёй стоит слон», «поле f1 занято»): false when the
    square is empty, not between the king and the rook, or holds another piece;
  * a moved king or rook («король уже ходил»): false only in a game whose record the check has (the rights of a set-up
    FEN are not evidence), when the king and that rook stand at home with the right kept.

A reason is bound to the claim only inside one sentence and with no contrast between them («, а …», «; …», «кроме
того», "but", "also"); the nearest one on each side is taken. A reason denied («не из-за поля f2», «это не мешает»), a
question, a quoted opinion («ты думаешь…»), or castling advice («рокируйся, ведь…») is not judged. Rule talk with no
square of the board was hidden before this reader sees it (src/claim_scope.rule_spans, K4) — «нельзя рокироваться
через битое поле» alone is a law, and stays unjudged. The issue gives the true reason as src/board_rules states it.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

from src.board_rules import castling_status

_W = r"(?<![а-яёa-zәғқңөұүһі])"
_E = r"(?![а-яёa-zәғқңөұүһі])"
_SQ = r"(?<![a-z0-9])(?P<{0}>[a-h][1-8])(?![0-9a-z])"
_CASTLE = re.compile(r"рок[иеі]р\w*|castl\w*|(?<![a-z0-9-])(?:o-o(?:-o)?|0-0(?:-0)?)(?![a-z0-9-])", re.IGNORECASE)

# ── the claim: castling impossible, or something forbids it ─────────────────────────────────────────────────────────
_NEG_WORD = (r"(?:нельзя|не\s+(?:мог[уа]|можешь|можете|может|могут|можем|сможешь|сможете|сможет|смогут|смогу|сможем|"
             r"получится|получ\w+|выйдет|удастся|удаст\w*|разрешен\w*|имеешь\s+права|имеет\s+права|сделать|сделаешь|"
             r"сделает|сделаю)|невозможн\w*|запрещен\w*|недоступн\w*)")
_NEG = re.compile(
    _W + _NEG_WORD + r"\s+(?:[а-яё]+\s+){0,3}?(?:сделать\s+|провести\s+|выполнить\s+)?(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*"
    r"|" + _W + r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*\s+(?:[а-яё]+\s+){0,3}?(?:" + _NEG_WORD
    + r"|не\s+(?:возможн\w*|доступн\w*|пройд[её]т|состоится|сделать))" + _E
    + r"|(?<![a-z])(?:can'?t|cannot|can\s+not|unable\s+to|not\s+able\s+to|may\s+not|(?:is|are)n'?t\s+allowed\s+to|"
    r"(?:is|are)\s+not\s+allowed\s+to)\s+castle"
    r"|castling\s+(?:\w+\s+){0,2}?(?:is|isn'?t)\s+(?:not\s+(?:possible|legal|allowed|available)|illegal|impossible|"
    r"ruled\s+out|possible|legal|allowed|available)(?![a-z])"
    r"|(?<![a-z])(?:o-o(?:-o)?|0-0(?:-0)?)\s+(?:сейчас\s+|здесь\s+|тут\s+)?(?:невозможн\w*|нельзя|запрещен\w*|"
    r"is\s+(?:not\s+possible|illegal|impossible))", re.IGNORECASE)
# «X мешает рокировке», «не даёт рокироваться», "prevents castling" — the subject is the reason.
_BARRIER = re.compile(
    _W + r"(?:меша\w*|не\s+да[её]т|не\s+позволя\w*|запреща\w*|лиша\w*|препятству\w*|блокиру\w*)\s+(?:[а-яё]+\s+){0,2}?"
    r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*"
    r"|" + _W + r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*\s+(?:[а-яё]+\s+){0,2}?(?<!не\s)(?:меша\w*|препятству\w*)" + _E
    + r"|(?<![a-z])(?:prevents?|stops?|forbids?|rules?\s+out|blocks?)\s+(?:\w+\s+){0,2}?castl\w*", re.IGNORECASE)
# «проходить через битое поле при рокировке нельзя», "you can't castle through an attacked square": the rule named,
# its square elsewhere in the sentence («слон c5 бьёт поле f2, и по правилам …»).
_RULE = re.compile(
    r"(?:через|сквозь)\s+(?:битое|атакованн\w+|простреливаем\w+|контролируем\w+|опасн\w+)\s+пол\w*"
    r"|через\s+пол\w+\s*,?\s+(?:которое\s+)?(?:находится\s+)?под\s+(?:боем|ударом|атакой)"
    r"|(?:на|в)\s+(?:битое|атакованн\w+)\s+поле"
    r"|through\s+(?:an?\s+|the\s+)?(?:attacked|controlled|covered)\s+square|through\s+check", re.IGNORECASE)
# What turns a claim of «impossible» around: the coach saying it does not matter, or quoting an opinion.
_IRRELEVANT = re.compile(
    _W + r"(?:не\s+(?:на\s+пути|меша\w*|важн\w*|имеет\s+значени\w*|влия\w*|отменя\w*|запреща\w*|препятству\w*|меня\w*|"
    r"касается|проходит|пройд[её]т|ид[её]т|участвует|задева\w*)|неважно|ни\s+при\s+ч[её]м|роли\s+не\s+игра\w*)" + _E
    + r"|(?<![a-z])(?:does\s*n[o']t|doesn'?t|do\s*n[o']t|don'?t)\s+(?:matter|pass|prevent|affect|stop|cross|block|forbid|rule\s+out)|"
      r"not\s+on\s+the\s+(?:king'?s\s+)?(?:path|way)|irrelevant", re.IGNORECASE)
_OPINION = re.compile(_W + r"(?:думаешь|думал\w*|считаешь|считал\w*|кажется|казалось|пишешь|говоришь|сказал\w*|"
                      r"спрашиваешь|неверно|ошибочно|заблуждение|ошиб\w+|think|thought|seems?|you\s+say|wonder|"
                      r"not\s+true|mistaken|wrong)" + _E, re.IGNORECASE)
# A contrast or an addition: what follows it is not the reason of the claim before it.
_CONTRAST = re.compile(r";|\(|\)|" + _W + r"(?:а|но|однако|зато|кроме\s+того|к\s+тому\s+же|также|а\s+также|плюс|кстати|"
                       r"при\s+этом|вдобавок|заодно|помимо|but|however|also|whereas|while|plus|besides|meanwhile)" + _E,
                       re.IGNORECASE)
# What moves the claim off the board as it is: a condition, a line, a future.
_HYPO = re.compile(
    _W + r"(?:после|если|когда|бы|будет|будут|станет|станут|сможешь|сможете|сможет|потом|затем|тогда|сначала|прежде|"
    r"позже|допустим|представь|предположим|пока\s+не|after|if|when|once|would|will|then|later|first|until|unless|"
    r"suppose|imagine)" + _E + r"|(?<![a-z0-9])\d{1,3}\s?\.{1,3}\s?(?=[a-hkqrbnoкфлс])", re.IGNORECASE)
_NOW = re.compile(_W + r"(?:сейчас|здесь|тут|в\s+этой\s+позиции|на\s+доске|now|here|right\s+now)" + _E, re.IGNORECASE)

# ── reasons ────────────────────────────────────────────────────────────────────────────────────────────────────────
_NOUN = r"(?:пол[еяю]|полем|клетк[аиуе]|клеткой|квадрат\w*)"
_PT_NOM = r"(?:слон|конь|ладья|ферзь|пешка|король|bishop|knight|rook|queen|pawn|king)"
_PT_OBL = (r"(?:слона|коня|ладьи|ферзя|пешки|короля|слоном|конем|конём|ладьей|ладьёй|ферзем|ферзём|пешкой|королем|"
           r"королём)")
_SIDE_ADJ = (r"(?:(?:ч[её]рн|бел|чуж|вражеск|сопернико?в?|противнико?в?)\w*\s+|(?:black|white|enemy|opponent'?s|"
             r"black'?s|white'?s)\s+)?")
_ATTACKED = (r"(?:(?:находится|стоит|оказывается|оказалось|тоже|уже|сейчас|ещ[её]|вс[её]\s+ещ[её]|было|является)\s+)*"
             r"(?:под\s+(?:боем|ударом|атакой|контролем|прицелом|обстрелом)|атакован[оа]?|атакуется|бь[её]тся|"
             r"простреливается|контролируется|битое|"
             r"(?:is|are)\s+(?:also\s+|still\s+)?(?:attacked|covered|controlled|under\s+attack|hit|guarded|being\s+attacked))")
_BY_RU = (r"(?:\s+(?:у\s+)?" + _SIDE_ADJ + r"(?P<pt>" + _PT_OBL + r")(?:\s+(?:на\s+|с\s+)?" + _SQ.format("s2") + r")?)?")
_BY_EN = (r"(?:\s+by\s+(?:the\s+|a\s+|your\s+|his\s+|my\s+)?" + _SIDE_ADJ + r"(?:" + _SQ.format("s2b") + r"\s+)?"
          r"(?P<pte>bishop|knight|rook|queen|pawn|king)(?:\s+(?:on|from)\s+" + _SQ.format("s2c") + r")?)?")
_VERB = (r"(?:бь[её]т|бьют|атакует|атакуют|контролирует|контролируют|держит|держат|простреливает|простреливают|"
         r"смотрит\s+на|нацелен\s+на|attacks?|covers?|controls?|hits?|eyes|guards?)")

_REASONS = [
    # «поле f2 под боем слона c5», «f1 атаковано слоном», "f2 is attacked by the bishop on c5", «битое поле f1»
    ("attacked", re.compile(r"(?P<noun>" + _NOUN + r"\s+|the\s+)?" + _SQ.format("s") + r"(?:\s+square)?\s+"
                            + _ATTACKED + _BY_RU + _BY_EN, re.IGNORECASE)),
    ("attacked", re.compile(_W + r"(?:битое|атакованн\w+|простреливаем\w+)\s+(?P<noun>" + _NOUN + r"\s+)?" + _SQ.format("s"),
                            re.IGNORECASE)),
    # «слон на c5 бьёт поле f2», "the bishop on c5 covers f2", "the c5 bishop attacks the f2 square"
    ("attacked", re.compile(_W + r"(?:" + _SQ.format("s2b") + r"\s+)?(?P<pt>" + _PT_NOM + r")"
                            r"(?:\s+(?:на|с|on|from)\s+" + _SQ.format("s2") + r"|\s+" + _SQ.format("s2c") + r")?"
                            r"\s+(?:(?:тоже|уже|сейчас|ещ[её]|также|и|also|still|now)\s+)?" + _VERB
                            + r"\s+(?:по\s+)?(?P<noun>" + _NOUN + r"\s+|the\s+)?" + _SQ.format("s") + r"(?:\s+square)?",
                            re.IGNORECASE)),
    # «поле f1 бьёт слон d3»
    ("attacked", re.compile(r"(?P<noun>" + _NOUN + r"\s+)" + _SQ.format("s") + r"\s+(?:[а-яё]+\s+)?"
                            r"(?:бь[её]т|бьют|атакует|контролирует|держит|простреливает)\s+" + _SIDE_ADJ
                            + r"(?P<pt>" + r"(?:слон|конь|ладья|ферзь|пешка|король)" + r")(?:\s+(?:на\s+|с\s+)?"
                            + _SQ.format("s2") + r")?", re.IGNORECASE)),
    # «из-за поля f2», «из-за битого поля f2»
    ("attacked", re.compile(_W + r"из-за\s+(?:битого\s+|атакованного\s+)?(?P<noun>пол[яе]\s+)" + _SQ.format("s"),
                            re.IGNORECASE)),
    # «король пройдёт через f2», «через битое поле f2», "the king passes through f2"
    ("path", re.compile(_W + r"(?:через|сквозь)\s+(?:битое\s+|атакованн\w+\s+|простреливаем\w+\s+)?(?P<noun>" + _NOUN
                        + r"\s+)?" + _SQ.format("s") + r"|(?:through|over|across)\s+(?:the\s+)?(?:attacked\s+)?(?P<noun2>square\s+)?"
                        + _SQ.format("s3"), re.IGNORECASE)),
    ("path", re.compile(_W + r"корол\w*\s+(?:[а-яё]+\s+){0,2}?(?:встанет|вста[её]т|вставать|встать|окажется|приземлится|"
                        r"попад[её]т|прыгнет|перепрыгнет|пересечет|пересеч[её]т)\s+на\s+(?P<noun>" + _NOUN + r"\s+)?"
                        + _SQ.format("s"), re.IGNORECASE)),
]
_CHECK = re.compile(_W + r"(?:корол\w*|ты|вы|я|белые|ч[её]рные)\s+(?:сейчас\s+|уже\s+|стоит\s+|находится\s+)*"
                    r"(?:под\s+шахом|в\s+шахе)" + _E + r"|" + _W + r"(?:из-за|от)\s+шах\w*" + _E
                    + r"|(?<![a-z])(?:king\s+)?(?:is|are|am)\s+in\s+check|because\s+of\s+(?:the\s+)?check", re.IGNORECASE)
_BLOCK = [
    # «конь на g1 мешает», «слон f1 ещё не ушёл», «ферзь d1 стоит на пути», "the knight on g1 is in the way"
    re.compile(_W + r"(?P<pt>" + _PT_NOM + r")(?:\s+(?:на\s+|с\s+|on\s+)?" + _SQ.format("s") + r")?\s+(?:ещ[её]\s+|вс[её]\s+ещ[её]\s+|"
               r"пока\s+|still\s+)?(?:мешает|меша[ею]т|стоит\s+(?:между|на\s+пути|на\s+месте)|загораживает|перекрывает|"
               r"не\s+ушел|не\s+ушёл|не\s+выведен\w*|не\s+развит\w*|is\s+in\s+the\s+way|stands?\s+in\s+the\s+way|"
               r"(?:is|are)\s+still\s+(?:at\s+home|on\s+its\s+square))", re.IGNORECASE),
    # «между королём и ладьёй стоит слон (на f1)», "between the king and the rook stands the bishop"
    re.compile(r"(?:между\s+корол\w+\s+и\s+ладь\w+|на\s+пути\s+(?:корол\w+|ладь\w+))\s+(?:ещ[её]\s+|вс[её]\s+ещ[её]\s+)?"
               r"(?:стоит|стоят|есть|находится|находятся)\s+(?:тво\w+\s+|сво\w+\s+|сво\w+\s+же\s+)?(?P<pt>" + _PT_NOM + r")"
               r"(?:\s+(?:на\s+)?" + _SQ.format("s") + r")?", re.IGNORECASE),
    # «короткой рокировке мешает ферзь d1», "castling is blocked by the knight on g1"
    re.compile(_W + r"(?:меша\w*|загоражива\w*|перекрыва\w*)\s+(?:тебе\s+|белым\s+|ч[её]рным\s+)?(?:коротк\w+\s+|длинн\w+\s+)?"
               r"рок[иеі]р\w*\s+(?:ещ[её]\s+|сейчас\s+)?(?:тво\w+\s+|сво\w+\s+)?(?P<pt>" + _PT_NOM + r")(?:\s+(?:на\s+)?"
               + _SQ.format("s") + r")?"
               r"|castl\w*\s+(?:\w+\s+)?is\s+blocked\s+by\s+(?:the\s+|your\s+)?(?P<pte>bishop|knight|queen)(?:\s+on\s+"
               + _SQ.format("s3") + r")?", re.IGNORECASE),
    # «короткой рокировке мешает ферзь d1»
    re.compile(_W + r"рок[иеі]р\w*\s+(?:ещ[её]\s+|сейчас\s+|тебе\s+)?(?:меша\w*|препятству\w*|загоражива\w*)\s+"
               r"(?:тво\w+\s+|сво\w+\s+)?(?P<pt>" + _PT_NOM + r")(?:\s+(?:на\s+)?" + _SQ.format("s") + r")?", re.IGNORECASE),
    # «поле f1 занято», "g1 is occupied"
    re.compile(r"(?:" + _NOUN + r"\s+|the\s+)?" + _SQ.format("s") + r"(?:\s+square)?\s+(?:ещ[её]\s+)?(?:занят\w*|не\s+свободн\w*|"
               r"не\s+пуст\w*|is\s+(?:still\s+)?(?:occupied|not\s+empty|blocked))", re.IGNORECASE),
]
_MOVED = re.compile(
    _W + r"(?P<who>корол\w*|ладь\w*)\s+(?:(?:на\s+)?[ah][18]\s+)?(?:уже\s+)?(?:ходил\w*|двигал\w*|сходил\w*|сделал\w*\s+ход|"
    r"сдвинул\w*|уходил\w*|ушел|ушла|ушёл)" + _E
    + r"|" + _W + r"(?:уже\s+)?(?:ходил\w*|сходил\w*)\s+(?P<who2>королем|королём|ладьей|ладьёй)" + _E
    + r"|" + _W + r"(?:потерял\w*|утратил\w*|лишил\w*\s+себя|нет)\s+(?:прав[ао]?|прав\s+на)\s+(?:на\s+)?рок[иеі]р\w*"
    + r"|(?<![a-z])(?P<who3>king|rook)\s+(?:has|had)\s+(?:already\s+)?moved|lost\s+(?:the\s+)?(?:right|castling\s+rights)",
    re.IGNORECASE)

# What makes «через S» the king's way: the king or castling moving, right before it.
_KING_MOTION = re.compile(_W + r"(?:корол\w*|рок[иеі]р\w*|проход\w*|пройд\w*|пройти|прош[её]л\w*|переход\w*|перейд\w*|"
                          r"пересека\w*|пош[её]л\w*|пойд[её]т|ид[её]т|идти|шагн\w*|king|castl\w*|pass\w*|cross\w*|битое|атакованн\w+)" + _E, re.IGNORECASE)
_ATTACK_LEAD = re.compile(_W + r"(?:бь[её]т|бьют|атаку\w+|контролиру\w+|смотрит|простреливает|держит|нацелен|attacks?|"
                          r"covers?|controls?|hits?|x-?rays?)" + _E + r"(?![^,;:—]*(?:корол|king))", re.IGNORECASE)

_TYPES = {"слон": chess.BISHOP, "кон": chess.KNIGHT, "лад": chess.ROOK, "ферз": chess.QUEEN, "пешк": chess.PAWN,
          "корол": chess.KING, "bishop": chess.BISHOP, "knight": chess.KNIGHT, "rook": chess.ROOK, "queen": chess.QUEEN,
          "pawn": chess.PAWN, "king": chess.KING}
_PATH = {"O-O": (5, 6), "O-O-O": (3, 2)}
_BETWEEN = {"O-O": (5, 6), "O-O-O": (1, 2, 3)}


def _ptype(word: Optional[str]) -> Optional[int]:
    if not word:
        return None
    w = word.lower()
    return next((t for k, t in _TYPES.items() if w.startswith(k)), None)


def _wing(text: str) -> Optional[str]:
    long_ = re.search(_W + r"(?:длинн\w*|ферзев\w*|queenside|long)" + _E + r"|(?<![a-z0-9-])(?:o-o-o|0-0-0)(?![a-z0-9-])",
                      text, re.IGNORECASE)
    short = re.search(_W + r"(?:коротк\w*|королевск\w*|kingside|short)" + _E
                      + r"|(?<![a-z0-9-])(?:o-o|0-0)(?![a-z0-9-])", text, re.IGNORECASE)
    if bool(long_) == bool(short):
        return None
    return "O-O-O" if long_ else "O-O"


_BOTH = re.compile(_W + r"(?:ни\s+в\s+одну|ни\s+в\s+какую|в\s+обе|ни\s+туда|both\s+ways|either\s+(?:way|side))" + _E,
                   re.IGNORECASE)


def _claim_wing(text: str, claims: list) -> Optional[str]:
    """The castling the claim names («короткая рокировка невозможна», "can't castle kingside"): read around the claim
    itself, not the whole sentence — «на ферзевом фланге стоят конь и слон» later is not the claim's wing."""
    for c0, c1, _kind in claims:
        lo = max(0, c0 - 30)
        window = text[lo:c1 + 25]
        cut = _CONTRAST.search(text, c1)
        if cut is not None and cut.start() < c1 + 25:
            window = text[lo:cut.start()]
        if _BOTH.search(window):
            return None
        w = _wing(window)
        if w:
            return w
    return None


def _named_colour(text: str) -> Optional[bool]:
    """The side whose castling the claim is about, when the sentence names it as the subject: «белые не могут»,
    «у чёрных», «чёрным нельзя», "White can't castle"."""
    found = set()
    for m in re.finditer(_W + r"(?:(?P<w>белые|белым|у\s+белых|white)|(?P<b>ч[её]рные|ч[её]рным|у\s+ч[её]рных|black))"
                         r"(?=\s+(?:не\s+|нельзя|никак|can|cannot|can'?t|may|is|are|ещ[её]|уже|сейчас|рок))", text,
                         re.IGNORECASE):
        found.add(chess.WHITE if m["w"] else chess.BLACK)
    return found.pop() if len(found) == 1 else None


def _side_name(colour: bool) -> str:
    return "White" if colour == chess.WHITE else "Black"


def _truth(board: chess.Board, colour: bool, wings: list) -> str:
    """The castling of *colour* on *board* as src/board_rules states it."""
    st = castling_status(board, colour)
    label = {"O-O": "short castling (O-O)", "O-O-O": "long castling (O-O-O)"}
    parts = []
    for w in wings:
        legal, why = st[w]
        parts.append(f"{label[w]} is legal now" if legal else f"{label[w]} is NOT possible now — {why}")
    return f"{_side_name(colour)}: " + "; ".join(parts)


def _path_text(colour: Optional[bool], wings: list) -> str:
    out = []
    for w in wings:
        f, g = (chess.FILE_NAMES[x] for x in _PATH[w])
        if colour is None:
            out.append(f"{w}: {f}1, {g}1 ({f}8, {g}8 for Black)")
        else:
            r = "1" if colour == chess.WHITE else "8"
            out.append(f"{w}: {f}{r}, {g}{r}")
    return "the king passes and lands on " + "; ".join(out)


def _claims(text: str) -> list:
    """(start, end, kind) of the claims in *text* that castling is impossible or something forbids it."""
    out = []
    for kind, rx in (("neg", _NEG), ("barrier", _BARRIER), ("rule", _RULE)):
        for m in rx.finditer(text):
            if kind == "barrier" and re.search(r"(?:^|\s)не\s+$", text[max(0, m.start() - 4):m.start()]):
                continue  # «не мешает рокировке»
            if kind == "neg" and re.search(r"castling\s+(?:\w+\s+){0,2}?is\s+(?:possible|legal|allowed|available)", m.group(0)):
                continue
            if kind != "rule" and _after_castling(text, m):
                continue  # «после рокировки ты не сможешь …»: castling is the time, not the claim
            out.append((m.start(), m.end(), kind))
    return sorted(out)


def _after_castling(text: str, m: re.Match) -> bool:
    w = _CASTLE.search(m.group(0))
    at = m.start() + (w.start() if w else 0)
    return bool(re.search(_W + r"(?:после|до|перед|без|after|before)\s+$", text[max(0, at - 12):at], re.IGNORECASE))


# «Чёрные могут рокироваться коротко: поля f8 и g8 свободны» — castling said possible, pinned to the board by a square
# of the king's path in the same clause.
_POS = re.compile(
    _W + r"(?:можешь|можете|можно|могут|может|могу|можем|сможешь|сможете|смогут)\s+(?:[а-яё]+\s+){0,2}?(?:сделать\s+)?"
    r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*"
    r"|" + _W + r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]ровк\w*\s+(?:[а-яё]+\s+){0,2}?(?:возможна|доступна|разрешена|"
    r"легальна)" + _E
    + r"|(?<![a-z])(?:can|may)\s+(?:still\s+|now\s+|already\s+)?castle|castling\s+(?:\w+\s+){0,2}?is\s+(?:possible|"
      r"legal|allowed|available)", re.IGNORECASE)


def _possible_issues(text: str, ctx, neg_claims: list) -> list[str]:
    from src.claim_scope import denied_before

    current = ctx.current
    if _HYPO.search(text):
        return []
    for m in _POS.finditer(text):
        if denied_before(text, m.start(), window=18) or _after_castling(text, m):
            continue
        if any(c[0] <= m.start() < c[1] or m.start() <= c[0] < m.end() for c in neg_claims):
            continue
        # the squares of the king's path named after the claim, in its clause
        cut = _CONTRAST.search(text, m.end())
        clause = text[m.end():cut.start() if cut else len(text)]
        squares = [chess.parse_square(x) for x in re.findall(r"(?<![a-z0-9])([cdfg][18])(?![0-9a-z])", clause)]
        if not squares:
            return []
        owners = {chess.WHITE if chess.square_rank(x) == 0 else chess.BLACK for x in squares}
        named = _named_colour(text)
        if len(owners) != 1 or (named is not None and named not in owners):
            return []
        colour = owners.pop()
        wings = {"O-O" if chess.square_file(x) >= 5 else "O-O-O" for x in squares}
        wing = _wing(text[max(0, m.start() - 30):m.end() + 25])
        if wing is not None and wing not in wings:
            return []
        wings = sorted(wings)
        st = castling_status(current, colour)
        if any(st[w][0] for w in wings):
            return []
        return [f"the castling reason is wrong: castling is not possible here, whatever "
                f"{', '.join(chess.square_name(x) for x in squares)} are said to be. "
                f"The truth on this board — {_truth(current, colour, wings)}"]
    return []


def _bound(text: str, claim: tuple, at: int, end: int) -> bool:
    """The reason at *at*…*end* belongs to *claim*: no contrast or addition between them."""
    lo, hi = (claim[1], at) if at >= claim[1] else (end, claim[0])
    if lo > hi:
        return True  # overlapping («…мешает рокировке» with the reason as its subject)
    return not _CONTRAST.search(text[lo:hi])


def _denied(text: str, at: int) -> bool:
    before = text[max(0, at - 16):at]
    return bool(re.search(r"(?:^|[\s,(«\"])(?:не|ни|not)\s+(?:из-за\s+|в\s+|because\s+of\s+)?(?:\w+\s+)?$", before))


def _board_for(text: str, upto: int, ctx):
    """The board the sentence's claim up to *upto* is about: the current one, the one after the move it tells
    («после b3 …», a written line), or None when it is a condition or a line the check cannot set up."""
    current = getattr(ctx, "current", None)
    if current is None:
        return None
    head = text[:upto]
    if not _HYPO.search(text):
        prev = getattr(ctx, "scene_before", None)
        if prev and prev[2] <= 1 and not _NOW.search(text):
            return None  # the sentence before told a line: this one may go on with it
        return current
    from src.answer_check_rules import _AFTER_MOVE, _ON_REPLY, _STEP, _line_scene, _parse_lowered

    # a hypothetical word after the claim («…, если …», «будет») — a condition: no board
    if _HYPO.search(text[upto:]):
        return None
    moves = list(_AFTER_MOVE.finditer(head))
    if moves:
        last = moves[-1]
        rest = head[last.end():]
        others = _HYPO.search(head[:last.start()]) or _HYPO.search(re.sub(r"будет|станет|станут|будут", "", rest))
        if others or _ON_REPLY.search(rest) or _STEP.search(rest):
            return None
        move = _parse_lowered(current, last["m"])
        if move is None or current.is_castling(move):
            return None
        b = current.copy(stack=False)
        b.push(move)
        return b
    try:
        board, _san = _line_scene(text, upto, ctx)
    except Exception:  # noqa: BLE001
        return None
    return board or None


def castle_reason_issues(text: str, ctx) -> list[str]:
    """The false reasons *text* (lower case, ё → е; rule talk hidden) gives for castling being impossible."""
    current = getattr(ctx, "current", None)
    if current is None or not _CASTLE.search(text):
        return []
    stripped = text.strip()
    if stripped.endswith("?") or _OPINION.search(text) or _IRRELEVANT.search(text):
        return []
    claims = _claims(text)
    if not claims:
        return _possible_issues(text, ctx, [])
    student = ctx.student_color if getattr(ctx, "student_color", None) is not None else current.turn
    wing = _claim_wing(text, claims)
    wings = [wing] if wing else ["O-O", "O-O-O"]
    named = _named_colour(text)
    issues: list[str] = []

    def default_colour() -> bool:
        if named is not None:
            return named
        in_game = bool(getattr(ctx, "game_engine_moves", None) or getattr(ctx, "game_moves", None))
        if in_game and re.search(_W + r"(?:я|мне|меня|my|i)" + _E, text) and not re.search(_W + r"(?:ты|тебе|тебя|вы|вам|you)" + _E, text):
            return not student  # «я не могу рокироваться» in a game: the coach's side
        return student

    # ── an attacked square, or a square on the king's way ──
    found = []
    for kind, rx in _REASONS:
        for m in rx.finditer(text):
            sq_name = m.groupdict().get("s") or m.groupdict().get("s3")
            if not sq_name:
                continue
            at, end = m.start(), m.end()
            found.append((at, end, kind, chess.parse_square(sq_name), m))
    # one reading per square: an attack read (it can be judged on the board) over a bare «через S», the longest first
    found.sort(key=lambda r: (r[2] != "attacked", -(r[1] - r[0]), r[0]))
    chosen = []
    for r in found:
        sq_at = r[4].start("s") if r[4].groupdict().get("s") else r[4].start("s3")
        if any(c[5] == sq_at for c in chosen):
            continue
        if r[2] == "path" and r[4].group(0).lstrip().startswith(("через", "сквозь", "through", "over", "across")):
            # «через f2» is the king's way only after a king's or castling's motion, not «слон бьёт f1 через e2»
            lead = text[max(0, r[0] - 40):r[0]]
            if not _KING_MOTION.search(lead) or _ATTACK_LEAD.search(lead):
                continue
        chosen.append(r + (sq_at,))
    chosen.sort(key=lambda r: r[0])
    reasons = []
    for at, end, kind, sq, m, sq_at in chosen:
        noun = (m.groupdict().get("noun") or m.groupdict().get("noun2") or "").strip()
        piece = current.piece_at(sq)
        if not noun and piece is not None and kind == "attacked" and chess.square_rank(sq) not in (0, 7):
            continue  # «f2 под боем» with a pawn there: the piece, not the square
        if _denied(text, at):
            continue
        reasons.append((at, end, kind, sq, m))
    # the nearest bound reason on each side of each claim
    picked = {}
    for claim in claims:
        after = [r for r in reasons if r[0] >= claim[0] and _bound(text, claim, r[0], r[1])]
        before = [r for r in reasons if r[1] <= claim[0] and _bound(text, claim, r[0], r[1])]
        if claim[2] == "rule":
            # the rule names no square: «битое поле» there is the square the sentence called attacked
            before = [r for r in before if r[2] == "attacked"]
            after = [r for r in after if r[2] == "attacked"]
        for r in ([after[0]] if after else []) + ([before[-1]] if before else []):
            picked[r[0]] = (r, claim)
    for at in sorted(picked):
        (at, end, kind, sq, m), claim = picked[at]
        rank = chess.square_rank(sq)
        file = chess.square_file(sq)
        sq_name = chess.square_name(sq)
        owner = chess.WHITE if rank == 0 else chess.BLACK if rank == 7 else None
        colour = owner if owner is not None else default_colour()
        if named is not None and owner is not None and named != owner:
            issues.append(f"the castling reason is wrong: {sq_name} is not on {_side_name(named)}'s castling path "
                          f"({_path_text(named, wings)}). The truth on this board — {_truth(current, named, wings)}")
            continue
        on_path = owner is not None and any(file in _PATH[w] for w in wings)
        king_sq = owner is not None and file == 4
        if not on_path and not king_sq:
            truth_board = _board_for(text, claim[1], ctx) or current
            issues.append(f"the castling reason is wrong: {sq_name} is not on the king's path — "
                          f"{_path_text(owner, wings)}; only those squares (and the king's own) must not be attacked"
                          + (", b1/b8 only has to be empty" if file == 1 and owner is not None else "")
                          + f". The truth on this board — {_truth(truth_board, colour, wings)}")
            continue
        if kind == "path":
            continue  # a square on the path named as passed: the attack (if said) is read by the attacked forms
        board = _board_for(text, min(at, claim[0]) if at < claim[0] else claim[1], ctx)
        if board is None:
            continue
        attackers = board.attackers(not owner, sq)
        if not attackers:
            if king_sq:
                issues.append(f"the castling reason is wrong: the {_side_name(owner).lower()} king on {sq_name} is not "
                              f"in check. The truth on this board — {_truth(board, owner, wings)}")
            else:
                issues.append(f"the castling reason is wrong: nothing of {_side_name(not owner)}'s attacks {sq_name}. "
                              f"The truth on this board — {_truth(board, owner, wings)}")
            continue
        g = m.groupdict()
        pt = _ptype(g.get("pt") or g.get("pte"))
        s2 = g.get("s2") or g.get("s2b") or g.get("s2c")
        if s2:
            a = chess.parse_square(s2)
            p = board.piece_at(a)
            if a not in attackers or (pt is not None and (p is None or p.piece_type != pt)):
                who = ", ".join(f"the {chess.piece_name(board.piece_type_at(x))} on {chess.square_name(x)}" for x in attackers)
                issues.append(f"the castling reason is wrong: {sq_name} is attacked by {who}, not by the piece on {s2}. "
                              f"The truth on this board — {_truth(board, owner, wings)}")
        elif pt is not None and pt not in {board.piece_type_at(x) for x in attackers}:
            who = ", ".join(f"the {chess.piece_name(board.piece_type_at(x))} on {chess.square_name(x)}" for x in attackers)
            issues.append(f"the castling reason is wrong: {sq_name} is attacked by {who}, not by a "
                          f"{chess.piece_name(pt)}. The truth on this board — {_truth(board, owner, wings)}")
    neg = [c for c in claims if c[2] in ("neg", "barrier")]
    if not neg:
        return issues + _possible_issues(text, ctx, claims)
    claim = neg[0]

    def bound_reason(rx_list) -> Optional[re.Match]:
        hits = [m for rx in rx_list for m in rx.finditer(text) if not _denied(text, m.start())]
        hits = [m for m in hits if _bound(text, claim, m.start(), m.end())]
        return min(hits, key=lambda m: abs(m.start() - claim[0])) if hits else None

    # ── a check ──
    m = bound_reason([_CHECK])
    if m is not None:
        board = _board_for(text, claim[1] if m.start() > claim[0] else m.start(), ctx)
        colour = default_colour()
        if board is not None:
            king = board.king(colour)
            if king is not None and not board.is_attacked_by(not colour, king):
                issues.append(f"the castling reason is wrong: the {_side_name(colour).lower()} king is not in check. "
                              f"The truth on this board — {_truth(board, colour, wings)}")
    # ── a piece in the way ──
    m = bound_reason(_BLOCK)
    if m is not None:
        board = _board_for(text, claim[1] if m.start() > claim[0] else m.start(), ctx)
        g = m.groupdict()
        sq_name = g.get("s") or g.get("s3")
        sq = chess.parse_square(sq_name) if sq_name else None
        colour = (chess.WHITE if chess.square_rank(sq) == 0 else chess.BLACK if chess.square_rank(sq) == 7 else None) \
            if sq is not None else None
        colour = colour if colour is not None else default_colour()
        if board is not None and (sq is None or chess.square_rank(sq) in (0, 7)):
            rank = 0 if colour == chess.WHITE else 7
            between = [chess.square(f, rank) for w in wings for f in _BETWEEN[w]]
            pt = _ptype(g.get("pt") or g.get("pte"))
            if sq is not None:
                p = board.piece_at(sq)
                if p is None:
                    issues.append(f"the castling reason is wrong: {chess.square_name(sq)} is empty. "
                                  f"The truth on this board — {_truth(board, colour, wings)}")
                elif sq not in between:
                    issues.append(f"the castling reason is wrong: {chess.square_name(sq)} is not between the king and "
                                  f"the rook for {' or '.join(wings)}. The truth on this board — {_truth(board, colour, wings)}")
                elif pt is not None and p.piece_type != pt:
                    issues.append(f"the castling reason is wrong: on {chess.square_name(sq)} stands a "
                                  f"{chess.piece_name(p.piece_type)}, not a {chess.piece_name(pt)}. "
                                  f"The truth on this board — {_truth(board, colour, wings)}")
            elif pt is not None and pt != chess.KING:
                if not any((board.piece_at(s) is not None and board.piece_at(s).piece_type == pt) for s in between):
                    issues.append(f"the castling reason is wrong: no {chess.piece_name(pt)} stands between the king and "
                                  f"the rook for {' or '.join(wings)}. The truth on this board — {_truth(board, colour, wings)}")
    # ── a moved king or rook: only with the game's record ──
    m = bound_reason([_MOVED])
    in_game = bool(getattr(ctx, "game_moves", None) or getattr(ctx, "game_engine_moves", None))
    if m is not None and in_game:
        board = _board_for(text, claim[1] if m.start() > claim[0] else m.start(), ctx)
        colour = default_colour()
        if board is not None:
            rank = 0 if colour == chess.WHITE else 7
            home = board.piece_at(chess.square(4, rank)) == chess.Piece(chess.KING, colour)
            who = (m.groupdict().get("who") or m.groupdict().get("who2") or m.groupdict().get("who3") or "").lower()
            rook_said = who.startswith(("лад", "rook"))
            check = wings if (rook_said or wing) else ["O-O", "O-O-O"]
            kept = [w for w in check if (board.has_kingside_castling_rights(colour) if w == "O-O"
                                         else board.has_queenside_castling_rights(colour))]
            if home and kept and len(kept) == len(check):
                issues.append(f"the castling reason is wrong: the {_side_name(colour).lower()} king and the rook have "
                              f"not moved in this game — the right to castle ({' and '.join(kept)}) is kept. "
                              f"The truth on this board — {_truth(board, colour, wings)}")
    return issues
