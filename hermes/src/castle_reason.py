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

Review 02.11 (review-fp, review-miss): the side is read from the sentence's subject («соперник», «его король», «чёрные
под шахом»; both kings when it cannot be told), a reason after another predicate of its own («…, и уйти королём на d2
тоже нельзя: …») is that predicate's, «а» going on to the rule links, a claim opening with «поэтому / значит» takes the
attacked square of the sentence before, a piece of the other side named as the reason off the back rank («из-за слона
c5») is judged by what it attacks, and castling advised for the student's move now is judged (castle_advice_issues).

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
# «рокировке в длинную сторону мешает …» (review-miss 02.11: three words between castling and its verb)
_SIDEWAYS = r"(?:в\s+(?:длинную|короткую|королевскую|ферзевую)\s+сторону\s+|на\s+(?:королевский|ферзевый)\s+фланг\s+)?"
# «X мешает рокировке», «не даёт рокироваться», "prevents castling" — the subject is the reason.
_BARRIER = re.compile(
    _W + r"(?:меша\w*|не\s+да[её]т|не\s+позволя\w*|запреща\w*|лиша\w*|препятству\w*|блокиру\w*)\s+(?:[а-яё]+\s+){0,2}?"
    r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*"
    r"|" + _W + r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*\s+" + _SIDEWAYS + r"(?:[а-яё]+\s+){0,2}?(?<!не\s)(?:меша\w*|препятству\w*)" + _E
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
                            + r"\s+(?:под\s+(?:прицелом|ударом|боем|контролем|обстрелом)\s+)?(?:по\s+)?(?P<noun>" + _NOUN + r"\s+|the\s+)?" + _SQ.format("s") + r"(?:\s+square)?",
                            re.IGNORECASE)),
    # «поле f1 бьёт слон d3»
    ("attacked", re.compile(r"(?P<noun>" + _NOUN + r"\s+)" + _SQ.format("s") + r"\s+(?:[а-яё]+\s+)?"
                            r"(?:бь[её]т|бьют|атакует|контролирует|держит|простреливает)\s+" + _SIDE_ADJ
                            + r"(?P<pt>" + r"(?:слон|конь|ладья|ферзь|пешка|король)" + r")(?:\s+(?:на\s+|с\s+)?"
                            + _SQ.format("s2") + r")?", re.IGNORECASE)),
    # «из-за поля f2», «из-за битого поля f2»
    ("attacked", re.compile(_W + r"из-за\s+(?:битого\s+|атакованного\s+)?(?P<noun>пол[яе]\s+)" + _SQ.format("s"),
                            re.IGNORECASE)),
    # «король встанет на g1, а это поле под ударом», «пройдёт через f1, а оно под боем слона» (review-miss 02.11 #10):
    # the square named as the king's, then said attacked by «это поле» / «оно» / «там»
    ("attacked", re.compile(_W + r"(?:корол\w*|рок[иеі]р\w*)\s+(?:[а-яё]+\s+){0,3}?(?:на|через|сквозь)\s+(?P<noun>"
                            + _NOUN + r"\s+)?" + _SQ.format("s") + r"\s*,?\s*(?:а|и|но|однако)\s+(?:это\s+пол\w+|эта\s+клетк\w+|"
                            r"оно|она|там|это)\s+" + _ATTACKED + _BY_RU, re.IGNORECASE)),
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
    # «…невозможна: мешает конь на c1», «…, мешает слон на f8»: the verb first, as speech has it (review-miss 03.11)
    re.compile(_W + r"(?:мешает|меша[ею]т|загораживает|перекрывает|стоит\s+на\s+пути)\s+(?:ещ[её]\s+|сейчас\s+|пока\s+|тебе\s+|"
               r"вс[её]\s+ещ[её]\s+)?(?:тво\w+\s+|сво\w+\s+)?(?P<pt>" + _PT_NOM + r")(?:\s+(?:на\s+|с\s+)?" + _SQ.format("s") + r")?"
               + _E, re.IGNORECASE),
    # «между королём и ладьёй стоит слон (на f1)», "between the king and the rook stands the bishop"
    re.compile(r"(?:между\s+корол\w+\s+и\s+ладь\w+|на\s+пути\s+(?:корол\w+|ладь\w+))\s+(?:ещ[её]\s+|вс[её]\s+ещ[её]\s+)?"
               r"(?:стоит|стоят|есть|находится|находятся)\s+(?:тво\w+\s+|сво\w+\s+|сво\w+\s+же\s+)?(?P<pt>" + _PT_NOM + r")"
               r"(?:\s+(?:на\s+)?" + _SQ.format("s") + r")?", re.IGNORECASE),
    # «короткой рокировке мешает ферзь d1», "castling is blocked by the knight on g1"
    re.compile(_W + r"(?:меша\w*|загоражива\w*|перекрыва\w*)\s+(?:тебе\s+|белым\s+|ч[её]рным\s+)?(?:коротк\w+\s+|длинн\w+\s+)?"
               r"рок[иеі]р\w*\s+" + _SIDEWAYS + r"(?:ещ[её]\s+|сейчас\s+)?(?:тво\w+\s+|сво\w+\s+)?(?P<pt>" + _PT_NOM + r")(?:\s+(?:на\s+)?"
               + _SQ.format("s") + r")?"
               r"|castl\w*\s+(?:\w+\s+)?is\s+blocked\s+by\s+(?:the\s+|your\s+)?(?P<pte>bishop|knight|queen)(?:\s+on\s+"
               + _SQ.format("s3") + r")?", re.IGNORECASE),
    # «короткой рокировке мешает ферзь d1»
    re.compile(_W + r"рок[иеі]р\w*\s+" + _SIDEWAYS + r"(?:ещ[её]\s+|сейчас\s+|тебе\s+)?(?:меша\w*|препятству\w*|загоражива\w*)\s+"
               r"(?:тво\w+\s+|сво\w+\s+)?(?P<pt>" + _PT_NOM + r")(?:\s+(?:на\s+)?" + _SQ.format("s") + r")?", re.IGNORECASE),
    # «поле f1 занято», "g1 is occupied"
    re.compile(r"(?:" + _NOUN + r"\s+|the\s+)?" + _SQ.format("s") + r"(?:\s+square)?\s+(?:ещ[её]\s+)?(?:занят\w*|не\s+свободн\w*|"
               r"не\s+пуст\w*|is\s+(?:still\s+)?(?:occupied|not\s+empty|blocked))", re.IGNORECASE),
]
# «рокироваться нельзя из-за слона c5», «из-за чёрного коня на b4»
_BECAUSE_PIECE = re.compile(_W + r"из-за\s+" + _SIDE_ADJ + r"(?P<pt>слона|коня|ладьи|ферзя|пешки)\s+(?:на\s+|с\s+)?"
                            + _SQ.format("s"), re.IGNORECASE)
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


# The side whose castling a sentence is about, read from its subject (review-fp 02.11: «Соперник не может
# рокироваться: его король под шахом», «Чёрные под шахом — рокировка у них невозможна» were judged on the student's king).
# A side named in the nominative or dative, «у белых», «король чёрных», "White can't"; the opponent named («соперник»,
# «противник», «у него», «его король», «он не может»); the student addressed («ты», «твой король»). Not the genitive of a
# piece's owner: «слон чёрных бьёт f1» is about White's castling.
_SUBJ_W = re.compile(_W + r"(?:белые|белым|у\s+белых|корол\w*\s+белых|бел(?:ый|ого|ому)\s+корол\w*|white(?:'s)?\s+(?:king|can|cannot|"
                     r"can'?t|may|is|has)|white\s+(?:to\s+move))" + _E, re.IGNORECASE)
_SUBJ_B = re.compile(_W + r"(?:ч[её]рные|ч[её]рным|у\s+ч[её]рных|корол\w*\s+ч[её]рных|ч[её]рн(?:ый|ого|ому)\s+корол\w*|"
                     r"black(?:'s)?\s+(?:king|can|cannot|can'?t|may|is|has))" + _E, re.IGNORECASE)
_SUBJ_OPP = re.compile(_W + r"(?:соперник\w*|противник\w*|оппонент\w*|у\s+(?:него|не[её]|них)|(?:его|е[её]|их)\s+корол\w*|"
                       r"(?:он|она|они)(?=\s+(?:[а-яё]+\s+){0,2}?(?:не\s|нельзя|рок|уже|под\s+шахом))|(?:ему|им)\s+(?:сейчас\s+|уже\s+)?"
                       r"(?:нельзя|не\s)|opponent\w*|(?:his|their)\s+king|(?:he|they)\s+(?:can'?t|cannot|is|are|has|have))" + _E,
                       re.IGNORECASE)
_SUBJ_YOU = re.compile(_W + r"(?:ты|тебе|тебя|тво[йяеёи]\w*|вы|вам|вас|ваш\w*|you|your)" + _E, re.IGNORECASE)
_SUBJ_ME = re.compile(_W + r"(?:я(?!\s+бы\s)|мне|меня|мо[йяеёи]|моего|моему|my|i(?!'?d\s))" + _E, re.IGNORECASE)


def _subject(text: str, ctx) -> tuple:
    """(colours, how) — the sides the castling claim of *text* may be about: one colour when the sentence says whose,
    both when it cannot be told (then a reason is false only when it fits neither king)."""
    current = ctx.current
    in_game = getattr(ctx, "student_color", None) is not None
    student = ctx.student_color if in_game else current.turn
    found = set()
    if _SUBJ_W.search(text):
        found.add(chess.WHITE)
    if _SUBJ_B.search(text):
        found.add(chess.BLACK)
    if len(found) == 1:
        return [found.pop()], "named"
    if found:
        return [chess.WHITE, chess.BLACK], "unclear"
    opp = bool(_SUBJ_OPP.search(text))
    you = bool(_SUBJ_YOU.search(text))
    if opp and not you:
        # outside a game the student is only guessed (the side to move): «соперник» there is not known to be the other
        return ([not student], "opponent") if in_game else ([chess.WHITE, chess.BLACK], "unclear")
    if you and not opp:
        return [student], "you"
    playing = bool(getattr(ctx, "game_engine_moves", None) or getattr(ctx, "game_moves", None))
    if playing and not opp and not you and _SUBJ_ME.search(text):
        return [not student], "coach"  # «я не могу рокироваться» in a game: the coach's side
    if not opp and not you:
        return [student], "default"
    return [chess.WHITE, chess.BLACK], "unclear"


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
        # not a square where a piece is said to stand: «ладья d1 стоит на линии d», «конь на f1 стоит» (review-fp 02.11)
        squares = [chess.parse_square(x.group(1)) for x in re.finditer(r"(?<![a-z0-9])([cdfg][18])(?![0-9a-z])", clause)
                   if not re.search(_W + r"(?:" + _PT_NOM + r"|" + _PT_OBL + r"|ладью|коня|слона|ферзя|пешку|короля)"
                                    r"\s+(?:на\s+|с\s+)?$", clause[max(0, x.start() - 14):x.start()], re.IGNORECASE)
                   and not re.match(r"\s+(?:стоит|стоят|находится|занят\w*)", clause[x.end():])]
        if not squares:
            return []
        owners = {chess.WHITE if chess.square_rank(x) == 0 else chess.BLACK for x in squares}
        named = _named_colour(text)
        if len(owners) != 1 or (named is not None and named not in owners):
            return []
        # the side the claim is about must be the side of the squares (named, else the student / the side to move)
        subject, how = _subject(text[:m.end()] + " " + clause, ctx)
        if len(subject) == 1 and subject[0] not in owners:
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


_A_LINK = re.compile(r"\s+(?:по\s+правилам|значит|поэтому|следовательно|через\s+(?:битое|атакованн\w+)|проходить|"
                     r"король\s+(?:не\s+)?(?:может|должен)|рок[иеі]р\w*)", re.IGNORECASE)
_OTHER_NEG = re.compile(_W + r"(?:нельзя|не\s+(?:мож\w+|мог\w*|смож\w+|получится|выйдет|удастся)|невозможн\w*|запрещен\w*|"
                        r"can'?t|cannot)" + _E, re.IGNORECASE)


def _bound(text: str, claim: tuple, at: int, end: int) -> bool:
    """The reason at *at*…*end* belongs to *claim*: no contrast or addition between them."""
    lo, hi = (claim[1], at) if at >= claim[1] else (end, claim[0])
    if lo > hi:
        return True  # overlapping («…мешает рокировке» with the reason as its subject)
    between = text[lo:hi]
    for c in _CONTRAST.finditer(between):
        # «…бьёт поле f2, а по правилам через битое поле рокироваться нельзя»: «а» going on to the rule or the
        # conclusion links the two (review-miss 02.11 #5) — any other contrast parts them
        if c.group(0).strip().lower() == "а" and _A_LINK.match(between, c.end()):
            continue
        return False
    # «Рокироваться нельзя — ты под шахом, и уйти королём на d2 тоже нельзя: поле d2 бьёт слон b4» (review-fp 02.11): a
    # reason after another predicate of its own («… тоже нельзя:») is that predicate's reason
    if _OTHER_NEG.search(between):
        return False
    return True


def _denied(text: str, at: int) -> bool:
    before = text[max(0, at - 16):at]
    return bool(re.search(r"(?:^|[\s,(«\"])(?:не|ни|not)\s+(?:из-за\s+|в\s+|because\s+of\s+)?(?:\w+\s+)?$", before))


def _piece_reason(board: chess.Board, sq: int, pt: Optional[int], wings: list, colours: list) -> Optional[str]:
    """Why the piece on *sq* (off the back rank) is no reason castling is impossible, or None when it may be one: it
    is the other side's (of a castling side among *colours*), that side keeps the right, and the piece attacks neither
    the king nor a square the king passes or lands on (on either wing, when the claim names none)."""
    p = board.piece_at(sq)
    if p is None or (pt is not None and p.piece_type != pt) or p.piece_type == chess.KING:
        return None
    side = not p.color
    if side not in colours:
        return None
    rank = 0 if side == chess.WHITE else 7
    if board.piece_at(chess.square(4, rank)) != chess.Piece(chess.KING, side):
        return None
    rights = {"O-O": board.has_kingside_castling_rights(side), "O-O-O": board.has_queenside_castling_rights(side)}
    if not all(rights[w] for w in wings):
        return None  # a right lost: the piece may have forced the king or the rook to move earlier
    hits = board.attacks(sq)
    squares = {chess.square(4, rank)} | {chess.square(f, rank) for w in wings for f in _PATH[w]}
    if any(x in hits for x in squares):
        return None
    names = ", ".join(chess.square_name(x) for x in sorted(squares))
    return (f"the castling reason is wrong: the {_side_name(p.color).lower()} {chess.piece_name(p.piece_type)} on "
            f"{chess.square_name(sq)} attacks none of {names} (the king's square and its path) — it does not forbid "
            f"castling. The truth on this board — {_truth(board, side, wings)}")


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


def _reasons(text: str, current: chess.Board) -> list:
    """The squares *text* gives as attacked or as the king's way: (start, end, kind, square, match), in order."""
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
        if re.search(_W + r"корол[её]м\s+(?:[а-яё]+\s+)?на\s+(?:поле\s+)?" + chess.square_name(sq) + r"(?![0-9])", text):
            continue  # «уйти королём на d2 нельзя: поле d2 бьёт слон» — the king's own step there, not castling (review-fp)
        reasons.append((at, end, kind, sq, m))
    return reasons


# A claim sentence that goes on from the one before («Поле f2 под боем слона c5. Поэтому рокироваться нельзя.»): the
# reason told there is this claim's reason (review-miss 02.11 #5).
_LINK_OPEN = re.compile(r"^\W*(?:(?:и|а)\s+)?(?:поэтому|значит|так\s+что|вот\s+почему|из-за\s+этого|следовательно|"
                        r"therefore|so|hence|that'?s\s+why)" + _E + r"|^\W*(?:а|и)(?=" + _A_LINK.pattern + r")",
                        re.IGNORECASE)


def castle_reason_issues(text: str, ctx) -> list[str]:
    """The false reasons *text* (lower case, ё → е; rule talk hidden) gives for castling being impossible."""
    current = getattr(ctx, "current", None)
    if current is None or not _CASTLE.search(text):
        return []
    stripped = text.strip()
    if stripped.endswith("?") or _OPINION.search(text):
        return []
    claims = _claims(text)
    # «это не мешает», «f2 не на пути» turn the claim around — not «рокировка не пройдёт», which is the claim itself
    # (review-miss 02.11 #8: «не пройдёт» switched the whole check off)
    if any(not any(c0 <= m.start() < c1 for c0, c1, _k in claims) for m in _IRRELEVANT.finditer(text)):
        return []
    if not claims:
        return _possible_issues(text, ctx, [])
    student = ctx.student_color if getattr(ctx, "student_color", None) is not None else current.turn
    wing = _claim_wing(text, claims)
    wings = [wing] if wing else ["O-O", "O-O-O"]
    named = _named_colour(text)
    subject, how = _subject(text, ctx)
    issues: list[str] = []

    def default_colour() -> bool:
        if named is not None:
            return named
        return subject[0] if len(subject) == 1 else student

    def judged_colours() -> list:
        """The kings a check or a moved king may be about: the subject's, both when the sentence does not say."""
        return subject if how in ("named", "opponent", "you", "coach") else [chess.WHITE, chess.BLACK]

    # ── an attacked square, or a square on the king's way ──
    reasons = _reasons(text, current)
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
    prev = (getattr(ctx, "sentence_before", "") or "").lower().replace("ё", "е")
    own = any(not _denied(text, x.start()) for rx in [_CHECK, _MOVED, _BECAUSE_PIECE] + _BLOCK for x in rx.finditer(text))
    if not picked and not reasons and not own and prev and _LINK_OPEN.match(text) and not _CASTLE.search(prev) \
            and not _HYPO.search(prev) and not prev.rstrip().endswith("?"):
        told = [r for r in _reasons(prev, current) if r[2] == "attacked"]
        if told:
            picked[-1] = ((0, 0) + told[-1][2:], claims[0])
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
        colours = judged_colours()
        if board is not None:
            free = [c for c in colours if board.king(c) is not None and not board.is_attacked_by(not c, board.king(c))]
            if free and len(free) == len(colours):
                colour = default_colour() if default_colour() in free else free[0]
                who = (f"the {_side_name(colour).lower()} king is" if len(colours) == 1 else "neither king is")
                issues.append(f"the castling reason is wrong: {who} not in check. "
                              f"The truth on this board — {_truth(board, colour, wings)}")
    # ── a piece of the other side named as the reason, off the back rank («из-за слона c5», «короткой рокировке мешает
    # слон на c5»): it forbids castling only by attacking the king or a square of its path (review-miss 02.11 #7) ──
    m = bound_reason(_BLOCK + [_BECAUSE_PIECE])
    if m is not None:
        g = m.groupdict()
        sq_name = g.get("s") or g.get("s3")
        if sq_name and chess.square_rank(chess.parse_square(sq_name)) not in (0, 7):
            board = _board_for(text, claim[1] if m.start() > claim[0] else m.start(), ctx)
            if board is not None:
                why = _piece_reason(board, chess.parse_square(sq_name), _ptype(g.get("pt") or g.get("pte")), wings,
                                    subject)
                if why:
                    issues.append(why)
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
    # A right the position keeps is evidence too (review-miss 03.11): the site sends the real game's FEN, and a FEN that
    # keeps the right for that wing with king and rook at home says neither has moved. A right absent stays no evidence.
    m = bound_reason([_MOVED])
    if m is not None:
        board = _board_for(text, claim[1] if m.start() > claim[0] else m.start(), ctx)
        who = (m.groupdict().get("who") or m.groupdict().get("who2") or m.groupdict().get("who3") or "").lower()
        rook_said = who.startswith(("лад", "rook"))
        check = wings if (rook_said or wing) else ["O-O", "O-O-O"]

        def untouched(colour) -> list:
            rank = 0 if colour == chess.WHITE else 7
            if board.piece_at(chess.square(4, rank)) != chess.Piece(chess.KING, colour):
                return []
            kept = [w for w in check if (board.has_kingside_castling_rights(colour) if w == "O-O"
                                         else board.has_queenside_castling_rights(colour))]
            return kept if len(kept) == len(check) else []

        colours = judged_colours()
        if board is not None and all(untouched(c) for c in colours):
            colour = default_colour() if default_colour() in colours else colours[0]
            kept = untouched(colour)
            if kept:
                issues.append(f"the castling reason is wrong: the {_side_name(colour).lower()} king and the rook have "
                              f"not moved in this game — the right to castle ({' and '.join(kept)}) is kept. "
                              f"The truth on this board — {_truth(board, colour, wings)}")
    return issues


# ── castling proposed when it cannot be played (review-miss 02.11 #1) ───────────────────────────────────────────────
# Live 02.11: short castling was illegal (the bishop d3 hits f1), and «Рокируйся коротко», «Давай рокируемся», «Пора
# рокироваться», «Сделай короткую рокировку» passed on every illegal castling tried (0/349): the castling check
# (src/answer_check_rules._castling_issues) judges «можно рокироваться» only with a now-word, and reads no advice. Here
# castling told as advice for the student's move now — an imperative, «давай», «пора», «я бы», «советую»; in a game on
# the student's turn also «можешь / можно рокироваться», «рокировка доступна» — is judged by castling_status. Left
# unjudged: the other side's castling, a question that is not a suggestion, a denial («не рокируйся», «рано
# рокироваться»), a move told before it in the sentence, a condition or a time to come («когда уведёшь слона»,
# «скоро», «при первой возможности», «чтобы …», «готовь рокировку»), a line the sentence before told, the rights of a
# set-up position outside a game (a FEN's «-» is no evidence).
_ADVICE = re.compile(
    _W + r"(?:"
    r"(?P<imp>рокируйся|рокируйтесь|рокируемся|рокирнись|рокирнемся)"
    r"|(?:давай(?:те)?|пора|самое\s+время|(?:я|мы)\s+бы|сделай(?:те)?|проведи(?:те)?|выполни(?:те)?|сыграй(?:те)?|"
    r"давай(?:те)?\s+(?:сделаем|проведем|проведём|сыграем)|"
    r"советую|предлагаю|рекомендую|попробуй(?:те)?|лучше(?:\s+всего)?|стоит|нужно|надо|следует|хорошо\s+бы)\s+"
    r"(?:(?:сейчас|уже|сразу|прямо|тебе|вам|все-таки|просто|наконец|же|именно)\s+){0,2}"
    r"(?:сделать\s+|провести\s+|сыграть\s+|для\s+)?(?:коротк\w+\s+|длинн\w+\s+)?рок[иі]р(?:оваться|уемся|уйся|овался|овалась|овки|"
    r"овку|овка|овкой)(?:\s+в\s+(?:длинную|короткую|королевскую|ферзевую)\s+сторону|\s+на\s+(?:королевский|ферзевый)\s+фланг)?"
    r"|(?P<can>можно|можешь|можете)\s+(?:(?:сейчас|уже|сразу|спокойно|смело|тебе|вам|прямо)\s+){0,2}(?:сделать\s+)?"
    r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иі]р\w*"
    r"|(?P<avail>(?:коротк\w+\s+|длинн\w+\s+)?рокировка\s+(?:(?:тебе|уже|сейчас|здесь|тут|вполне)\s+){0,2}"
    r"(?:доступна|возможна|разрешена))"
    # castling as the next step after a move told before it (review-miss 03.11): «Сначала слоном на c4, а потом сразу
    # рокировка в длинную», «Освободи место: слоном на h3, и длинная рокировка готова» — judged only with that step
    r"|(?P<then>(?:потом|затем)\s+(?:(?:сразу|уже|можно)\s+){0,2}(?:коротк\w+\s+|длинн\w+\s+)?рокировк[ауи]"
    r"(?:\s+в\s+(?:длинную|короткую)(?:\s+сторону)?)?)"
    r"|(?P<ready>(?:коротк\w+\s+|длинн\w+\s+)?рокировк[ауи]\s+(?:(?:уже|сразу|сразу\s+же|тоже)\s+)?готова)"
    r")" + _E
    + r"|(?<![a-z])(?:let'?s\s+castle|you\s+(?:should|can|could)\s+(?:now\s+)?castle|^\W*castle)"
      r"(?:\s+(?:kingside|queenside|short|long))?(?![a-z])", re.IGNORECASE)
# A condition or a time to come anywhere around the advice: not the move now.
_ADVICE_LATER = re.compile(
    _W + r"(?:если|когда|как\s+только|пока|после|позже|позднее|скоро|вскоре|ближайш\w+|при\s+первой\s+возможности|"
    r"как\s+можно\s+(?:раньше|скорее|быстрее)|сначала|сперва|прежде|перед\s+этим|до\s+этого|готов\w*|подготов\w*|чтобы|"
    r"сможешь|сможете|обычно|всегда|как\s+правило|таких|дебют\w*|планир\w*|собира\w*|хоч\w*|хотел\w*|"
    r"не\s+сейчас|if|when|once|after|later|soon|first|before|until|prepare\w*|ready|eventually|usually|always|plan\w*|"
    r"want\w*)" + _E, re.IGNORECASE)
_ADVICE_LATER_HEAD = re.compile(_ADVICE_LATER.pattern + r"|" + _W + r"(?:потом|затем|будет|будешь|станет|then|next|"
                                r"after\s+that)" + _E,
                                re.IGNORECASE)
_ADVICE_AGAINST = re.compile(_W + r"(?:не\s+рок[иі]р\w*|рано|не\s+спеши\w*|не\s+торопи\w*|не\s+стоит|не\s+надо|не\s+нужно|"
                             r"не\s+советую|не\s+рекомендую|избега\w*|опасно|рискованно|don'?t|do\s+not|avoid|too\s+early)" + _E,
                             re.IGNORECASE)
# The words that may open the sentence before the advice: it is the sentence's own move, not a step of a plan.
_ADVICE_HEAD_OK = re.compile(r"(?:теперь|сейчас|здесь|тут|так|что|поэтому|значит|лучше|всего|просто|сразу|обязательно|смело|"
                             r"спокойно|а|и|ну|да|вот|ты|тебе|вам|мой|наш|совет|следующим|ходом|самое|время|пора|может|"
                             r"быть|давай|давайте|now|so|just|then|my|advice|here)", re.IGNORECASE)
# «Когда рокироваться?», «Когда мне лучше рокироваться?»: «когда» asks the time — it is not a condition of the answer
_WHEN_Q = re.compile(r"^\W*(?:а\s+)?(?:так\s+)?когда\s+(?:(?:же|мне|нам|лучше|стоит|нужно|надо|можно|уже|пора)\s+){0,3}"
                     r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иі]р\w*(?:\s+[а-яё]+){0,3}\s*\?\s*$"
                     r"|^\W*when\s+(?:should|do|can|must)\s+(?:i|we)\s+castle\b[^?]*\?\s*$", re.IGNORECASE)
# The step words a castling told after a step may carry before it: the step is judged, not a condition
_STEP_HEAD = re.compile(_W + r"(?:сначала|сперва|потом|затем|first|then)" + _E, re.IGNORECASE)
_AT_ONCE = re.compile(_W + r"(?:сразу|тут\s+же|немедленно|следующим\s+ходом|immediately|right\s+after)" + _E, re.IGNORECASE)
_ADVICE_SUGGEST_Q = re.compile(r"^\W*(?:а\s+)?(?:может(?:\s+быть)?|давай(?:те)?|почему\s+бы)" + _E, re.IGNORECASE)


def _castle_after_step(head: str, advice: str, board: chess.Board, ctx) -> Optional[str]:
    """The issue of castling advised right after one step («Сыграй Bc5 и рокируйся коротко», «Сначала слоном на c4, а
    потом сразу рокировка в длинную»), judged on the board after the step with the same side to move, when its own
    pieces still stand between or the king or the rook is gone; None when it is possible, depends on the reply, or the
    step is not one clear legal move."""
    from src.answer_check import _word_step_board

    if re.search(r"(?<![а-яё])(?:не|нельзя|если|когда|бы)(?![а-яё])", head):
        return None
    step = _word_step_board(head, board)
    if step is None:
        from src.answer_check_rules import _MOVE_LOW, _parse_lowered

        sans = []
        for x in _MOVE_LOW.finditer(head):  # the text is lowered: «сыграй nc3»
            mv = _parse_lowered(board, x.group(0))
            if mv is None:
                return None
            sans.append(mv)
        if len(sans) != 1 or board.is_castling(sans[0]):
            return None
        step = board.copy(stack=False)
        step.push(sans[0])
        step.turn = board.turn
        step.ep_square = None
    if step.is_check():
        return None
    student = getattr(ctx, "student_color", None)
    student = board.turn if student is None else student
    if student != board.turn:
        return None
    wing = _wing(advice)
    wings = [wing] if wing else ["O-O", "O-O-O"]
    st = castling_status(step, student)
    if any(st[w][0] for w in wings):
        return None
    lasting = ("pieces stand between", "the king is not on its starting square", "there is no ")
    if not all(st[w][1].startswith(lasting) for w in wings):
        return None  # an attacked square or a check: the reply decides
    why = "; ".join(f"{w}: {st[w][1]}" for w in wings)
    return (f"castling is proposed right after the step told before it, but even after that step it cannot be played "
            f"({_side_name(student)}) — {why}")


def castle_advice_issues(text: str, ctx) -> list[str]:
    """Castling advised for the student's move now in *text* (lower case, ё → е, rule talk hidden) when it cannot be
    played on the board."""
    current = getattr(ctx, "current", None)
    if current is None or not _CASTLE.search(text):
        return []
    from src.claim_scene import _asks_move
    from src.claim_scope import CONDITIONAL, NOW, denied_before

    in_game = getattr(ctx, "student_color", None) is not None
    if in_game and ctx.student_color != current.turn:
        return []  # the opponent to move: the advice is for the move after its reply
    if not in_game:
        from src.answer_check import student_side

        if student_side(ctx, text) != current.turn:
            return []
    question = getattr(ctx, "question", "") or ""
    if CONDITIONAL.search(question) and not NOW.search(text) and not _WHEN_Q.match(question.strip()):
        return []  # «а если я уведу слона, можно рокироваться?» — not «Когда рокироваться?»
    if _OPINION.search(text) or _ADVICE_AGAINST.search(text):
        return []
    prev = getattr(ctx, "scene_before", None)
    if prev and prev[2] <= 1 and not NOW.search(text):
        return []  # the sentence before told a line: this one may go on with it
    for m in _ADVICE.finditer(text):
        sent_start = max(text.rfind(c, 0, m.start()) for c in ".;!?\n") + 1
        sent_end = min([i for i in (text.find(c, m.end()) for c in ".;!?\n") if i >= 0] or [len(text)])
        sentence = text[sent_start:sent_end + 1]
        if text[sent_end:sent_end + 1] == "?" and not _ADVICE_SUGGEST_Q.match(text[sent_start:]):
            continue
        if (m["can"] or m["avail"]) and not in_game and not _asks_move(ctx):
            # «можно рокироваться» outside a game: the castling check judges it with a now-word — unless the student
            # asked what to play here («что мне делать?»): then «Можешь рокироваться коротко» answers for this board
            continue
        if denied_before(text, m.start(), window=18) or _after_castling(text, m):
            continue
        head = text[sent_start:m.start()]
        tail = text[m.end():sent_end]
        from src.answer_check import _MOVE, _to_san
        from src.move_words import prose_moves

        from src.answer_check_rules import _MOVE_LOW

        told_step = bool(prose_moves(head, current) or any(x["san"][0] in "KQRBN" or "x" in x["san"]
                                                           for x in _MOVE.finditer(_to_san(head)[0])) or _MOVE_LOW.search(head))
        if (m["then"] or m["ready"]) and not told_step:
            continue  # «потом рокировка», «рокировка готова» with no step told: a plan, not the move now
        # «потом/затем» castling right after the step only with «сразу»: «надёжно выглядит ход слоном на e2, а затем
        # короткая рокировка» is a plan (the knight g1 goes out on the way — replay_live 03.11), not the next move
        planned = bool(_STEP_HEAD.search(head) or m["then"]) and not _AT_ONCE.search(head + " " + m.group(0))
        stepped = told_step and (m["then"] or m["ready"] or m["imp"]) and not planned and not _ADVICE_LATER.search(tail) \
            and not _ADVICE_LATER_HEAD.search(_STEP_HEAD.sub(" ", head))
        if (m["then"] or m["ready"]) and not stepped:
            continue
        if not stepped and (_ADVICE_LATER_HEAD.search(head) or _ADVICE_LATER.search(tail)):
            continue
        if told_step:
            # «уведи слона и рокируйся»: castling after another move — judged on the board after that step, and only for
            # what no reply can change: its own pieces still in between, the king or the rook gone (review-miss 03.11:
            # «Сыграй Bc5 и рокируйся коротко» with the knight g8 at home)
            issue = _castle_after_step(head, text[m.start():sent_end], current, ctx)
            if issue:
                return [issue]
            continue
        words = re.findall(r"[а-яёa-z'-]+", head)
        if len(words) > 5 or not all(_ADVICE_HEAD_OK.fullmatch(w) for w in words):
            continue  # «Заверши развитие и рокируйся», «Выведи коня, потом рокируйся»: a plan, castling one step of it
        subject, how = _subject(sentence, ctx)
        student = ctx.student_color if in_game else current.turn
        if how in ("named", "opponent", "coach") and subject != [student]:
            continue  # the other side's castling
        wing = _wing(text[max(0, m.start() - 30):min(sent_end, m.end() + 30)])
        wings = [wing] if wing else ["O-O", "O-O-O"]
        st = castling_status(current, student)
        if any(st[w][0] for w in wings):
            continue
        if not in_game and not getattr(ctx, "game_moves", None) and all("right to castle is lost" in st[w][1] for w in wings):
            continue  # a set-up position's rights are no evidence
        why = "; ".join(f"{w}: {st[w][1]}" for w in wings)
        return [f"castling is proposed for {_side_name(student)}'s move now, but it cannot be played on this board — {why}"]
    return []


# ── A side's castling state (review-miss 03.11, castle_state) ─────────────────────────────────────────────────────────
# «Ты уже рокировался», «Твой король уже спрятан рокировкой»: the side has castled — false when its king stands at home
# with a castling right kept (a king that castled has lost both). «Соперник ещё может рокироваться (в короткую)»: false
# when its king or that rook has left for good. «Соперник уже не может сделать короткую рокировку»: false when that
# castling is legal on its move right now. Judged only for a side the sentence names (you, the opponent, White, Black);
# a sentence that does not say whose, a condition, a question or an opinion is not judged.
_STATE_CASTLED = re.compile(
    _W + r"(?:уже\s+)?(?:рокировал(?:ся|ась|ись)|(?:сделал|провел|провёл|выполнил)\w*\s+(?:коротк\w+\s+|длинн\w+\s+)?"
    r"рокировку|(?:спрятан|укрыт|уведен|уведён)\w*\s+(?:в\s+безопасност\w+\s+)?рокировкой)" + _E
    + r"|(?<![a-z])(?:has|have|'ve)\s+(?:already\s+)?castled(?![a-z])", re.IGNORECASE)
_STATE_STILL = re.compile(
    _W + r"(?:ещ[её]|вс[её]\s+ещ[её]|по-прежнему)\s+(?:может|могут|можешь|можете|сможет|смогут|сможешь|сможете)\s+"
    r"(?:[а-яё]+\s+){0,2}?(?:сделать\s+|провести\s+)?(?:коротк\w+\s+|длинн\w+\s+)?рок[иі]р\w*" + _E
    + r"|(?<![a-z])(?:can|may)\s+still\s+castle(?![a-z])", re.IGNORECASE)
_STATE_NO_LONGER = re.compile(
    _W + r"(?:уже|больше)\s+не\s+(?:может|могут|можешь|можете|сможет|смогут|сможешь|сможете)\s+(?:[а-яё]+\s+){0,2}?"
    r"(?:сделать\s+|провести\s+)?(?:коротк\w+\s+|длинн\w+\s+)?рок[иі]р\w*" + _E
    + r"|(?<![a-z])can\s+no\s+longer\s+castle(?![a-z])", re.IGNORECASE)
_STATE_SIDES = ("named", "opponent", "you", "unclear")


def _state_false(kind: str, board: chess.Board, colour: bool, wings: list) -> Optional[str]:
    """Why the *kind* claim about *colour*'s castling is false on *board*, or None when it is true or cannot be told."""
    rank = 0 if colour == chess.WHITE else 7
    st = castling_status(board, colour)
    if kind == "castled":
        home = board.piece_at(chess.square(4, rank)) == chess.Piece(chess.KING, colour)
        if home and (board.has_kingside_castling_rights(colour) or board.has_queenside_castling_rights(colour)):
            return (f"the {_side_name(colour).lower()} king stands on {chess.square_name(chess.square(4, rank))} with "
                    f"the right to castle kept — it has not castled")
        return None
    if kind == "still":
        gone = ("the king is not on its starting square", "there is no ")
        if all(not st[w][0] and st[w][1].startswith(gone) for w in wings):
            return "; ".join(f"{w}: {st[w][1]}" for w in wings)
        return None
    legal = [w for w in wings if st[w][0]]
    return f"{' and '.join(legal)} is legal on {_side_name(colour)}'s move now" if legal else None


def castle_state_issues(text: str, ctx) -> list[str]:
    """Claims in *text* (lower case; rule talk hidden) about whether a named side has castled or can still castle."""
    current = getattr(ctx, "current", None)
    if current is None or not _CASTLE.search(text):
        return []
    from src.claim_scope import denied_before

    issues: list[str] = []
    for sent in re.finditer(r"[^.;!?\n]+[.;!?\n]?", text):
        s = sent.group(0)
        if s.rstrip().endswith("?") or _OPINION.search(s) or _HYPO.search(s) or not _CASTLE.search(s):
            continue
        for kind, rx in (("castled", _STATE_CASTLED), ("still", _STATE_STILL), ("no_longer", _STATE_NO_LONGER)):
            for m in rx.finditer(s):
                if kind != "no_longer" and denied_before(s, m.start(), window=14):
                    continue  # «ты ещё не рокировался»
                # whose: read in the claim's own clause — «Ты уже рокировался, а белые ещё нет» is about the student
                lo = max([x.end() for x in _CONTRAST.finditer(s, 0, m.start())] or [0])
                hi = next((x.start() for x in _CONTRAST.finditer(s, m.end())), len(s))
                subject, how = _subject(s[lo:hi], ctx)
                if how not in _STATE_SIDES or not subject:
                    continue
                wing = _wing(s[max(0, m.start() - 30):m.end() + 30])
                wings = [wing] if wing else ["O-O", "O-O-O"]
                whys = [_state_false(kind, current, c, wings) for c in subject]
                if all(whys):
                    claim = {"castled": "has already castled", "still": "can still castle",
                             "no_longer": "can no longer castle"}[kind]
                    issues.append(f"«{m.group(0).strip()}» says the side {claim}, which is false on this board — "
                                  + "; ".join(f"{_side_name(c)}: {w}" for c, w in zip(subject, whys)))
                    break
    return issues
