"""Opening facts the ECO book decides, checked in the coach's answer (prod check 29.10).

The live production check of 29.10 (theory set) found the coach naming openings from memory where the book on
the server knows them exactly:

  * «**2. c3** (система с последующим d4, любимая атака в стиле Алёхина)» — after 1.e4 c5 2.c3 the book's line
    is the Alapin Variation; Alekhine's name belongs to another opening (the Alekhine Defense);
  * «Открытый вариант сицилианской защиты, и у белых тут три главных пути» on 1.e4 c5 — the Open Sicilian
    begins with 2.Nf3 and 3.d4, the board is the plain Sicilian (B20).

Two claims are judged here, each only against the book (src/openings_book.py — the 3,800 named lines Hermes
ships), never from a guess:

  * an ECO code the sentence ties to the board («Это испанская партия, код C65», «На доске … (B90)») must be a
    code of the board's position or of a stage on the way to it, of a line the answer writes, or of an opening
    the sentence names;
  * a variation named by a person («вариант Алапина», «атака … Алёхина», "the Alapin Variation") attached to a
    written move must be a name of a book line through the position after that move or before it — judged only
    for a name the book gives mostly to one opening (Alekhine, Najdorf, Winawer), not for one it spreads over
    many (Capablanca, Tarrasch: a usage the book lacks may still be right); a variation the sentence says the
    board IS («Это открытый вариант…», «Перед нами вариант Найдорфа») must be one the board has reached — not
    one still ahead of it.

«Обычно играют X», «главный ход здесь — X» are NOT judged (review 30.10): the book names lines and counts no
games — the Evans Gambit has 51 named sub-lines after 3...Bc5 and 4.d3 five, 2.d4 picks up the whole Indian
theory after 1.c4 Nf6 by transposition — and Hermes ships no statistics of moves played.

A claim about another position is left alone: a condition or a plan («если», «после», «будет»), a denial, a
question, a hedge («похоже на», «не путай с», «впереди», «самый популярный»), a range of codes («C60–C99»), a code
in a clause about another opening («…, а принятый гамбит идёт под D20»), an opening the sentence names that is not
the board's, a position the book does not have. The names of whole openings («это сицилианская защита») stay with
src/answer_check._opening_identity_issues.

Plan 31.10 (package P2; each detector has its switch, src/config.detector_mode):

  * open_plain (on) — «классический» and «современный» name variations too: «классическая сицилианская» on 1.e4 c5
    2.Nf3 d6 (B50, Modern Variations) — the Classical Variation begins 5...Nc6 (st1#2). Russian «классический»
    covers the book's Classical, Orthodox, Normal and Main Line; a plain word counts only as the variation's own
    name («Sicilian Defense: Classical Variation»), never a sub-line's («Ruy Lopez: Open, Classical Defense»); and
    said of an opening («классическая испанская партия») it names a variation only once the board is in a named
    variation of that opening — on the bare opening it is "the classic Ruy Lopez". The word order «вариант
    «современный»» reads as «современный вариант».
  * open_recap (on) — the moves the sentence tells as the game's own record («Nf3 — и чёрные ответили d6: это …»,
    src/game_record.recap_end) and the moves it denies («Дракон без ...g6», «вместо 2.c3») write no line: the name is
    then said of the board, and the identity after the last «:», «—» or «;» is read as the sentence's own.
  * open_character (shadow) — «спокойная игра», «без (тактических) осложнений», «тихая игра» said of a move whose
    position the book names as a line content/openings/lines.yaml calls sharp (6.Be3 in the Najdorf: the English
    Attack — move-najdorf).
  * open_defining (shadow) — advice to the student playing an opening not to make the opening's own defining move
    («если играешь защиту Алехина, логичнее не выводить коня…»: 1...Nf6 IS the Alekhine — g1-resign).
A shadow detector's issues are logged (and kept in ``ctx.detector_shadow`` as (name, sentence, issues)), never shown.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import chess

from src.claim_scope import CONDITIONAL, DENIAL, denied_before

logger = logging.getLogger(__name__)

_W = r"(?<![а-яёa-z])"
_E = r"(?![а-яёa-z])"

# Variations named after a person (or a place) — the Russian forms the coach writes, any case, and the word the
# book uses. Only names the book has count (checked when the book loads); «Кан», «Колле» are whole words only.
_PEOPLE = [
    (r"алапин\w{0,3}|alapin", "Alapin"),
    (r"ал[её]хин(?:а|у|ым|е|ская|ской|скую|ский|ского)?|alekhine", "Alekhine"),
    (r"морфи|morphy", "Morphy"),
    (r"найдорф\w{0,3}|najdorf", "Najdorf"),
    (r"тарраш\w{0,3}|tarrasch", "Tarrasch"),
    (r"ш?тейниц\w{0,3}|steinitz", "Steinitz"),
    (r"винавер\w{0,3}|winawer", "Winawer"),
    (r"рубинштейн\w{0,3}|rubinstein", "Rubinstein"),
    (r"эванс\w{0,3}|evans", "Evans"),
    (r"чигорин\w{0,3}|chigorin", "Chigorin"),
    (r"боголюбов\w{0,3}|bogoljubow", "Bogoljubow"),
    (r"ботвинник\w{0,3}|botvinnik", "Botvinnik"),
    (r"паульсен\w{0,3}|paulsen", "Paulsen"),
    (r"маршалл?\w{0,3}|marshall", "Marshall"),
    (r"тартаковер\w{0,3}|tartakower", "Tartakower"),
    (r"керес\w{0,3}|keres", "Keres"),
    (r"панов(?:а|у|ым|е)?|panov", "Panov"),
    (r"мароци|mar[oó]czy", "Maróczy"),
    (r"петросян\w{0,3}|petrosian", "Petrosian"),
    (r"раузер\w{0,3}|rauzer", "Rauzer"),
    (r"рихтер\w{0,3}|richter", "Richter"),
    (r"авербах\w{0,3}|averbakh", "Averbakh"),
    (r"шевенинген\w{0,3}|scheveningen", "Scheveningen"),
    (r"ласкер\w{0,3}|lasker", "Lasker"),
    (r"тайманов\w{0,3}|taimanov", "Taimanov"),
    (r"андерс[се]н\w{0,3}|anderssen", "Anderssen"),
    (r"шпильман\w{0,3}|spielmann", "Spielmann"),
    (r"смыслов\w{0,3}|smyslov", "Smyslov"),
    (r"спасск(?:ий|ого|ому|им)|spassky", "Spassky"),
    (r"брейер\w{0,3}|breyer", "Breyer"),
    (r"капабланк\w{0,3}|capablanca", "Capablanca"),
    (r"бронштейн\w{0,3}|bronstein", "Bronstein"),
    (r"шлехтер\w{0,3}|schlechter", "Schlechter"),
    (r"карпов(?:а|у|ым|е)?|karpov", "Karpov"),
    (r"созин\w{0,3}|sozin", "Sozin"),
    (r"ларсен\w{0,3}|larsen", "Larsen"),
    (r"россолимо|rossolimo", "Rossolimo"),
    (r"эйве|euwe", "Euwe"),
    (r"свешников\w{0,3}|sveshnikov", "Sveshnikov"),
    (r"пеликан\w{0,3}|pelikan", "Pelikan"),
    (r"шлиман\w{0,3}|schliemann", "Schliemann"),
    (r"корчно(?:й|я|ю|ем|е)|korchnoi", "Korchnoi"),
    (r"глигорич\w{0,3}|gligori[cć]", "Gligoric"),
    (r"зайцев(?:а|у|ым|е)?|zaitsev", "Zaitsev"),
    (r"цукерторт\w{0,3}|zukertort", "Zukertort"),
    (r"земиш\w{0,3}|s[äa]misch", "Sämisch"),
    (r"кизерицк\w{0,3}|kieseritzky", "Kieseritzky"),
    (r"фалькбеер\w{0,3}|falkbeer", "Falkbeer"),
    (r"(?:смит[\s-]+)?морр\w{1,2}|(?:smith[\s-]+)?morra", "Morra"),
    (r"яниш\w{0,3}|jaenisch", "Jaenisch"),
    (r"кан(?:а|у|ом)|kan", "Kan"),
    (r"мел[её]р\w{0,3}|m[øo]ller", "Møller"),
    (r"ленинградск\w{0,3}|leningrad", "Leningrad"),
    (r"меранск\w{0,3}|meran", "Meran"),
    # fix 01.11: heads the book names variations by that are not people — «Дракон» (Dragon 0/7 in review-miss), and
    # the names players say bare («это Найдорф», «Чёрные выбрали Дракон»), read as names only in a frame below
    (r"дракон(?:а|у|ом|е|ий|ья|ье|ьего|ьей|ьему|ьим|ью|ьи)?|dragon", "Dragon"),
    (r"челябинск\w{0,3}|chelyabinsk", "Chelyabinsk"),
    (r"велимирович\w{0,3}|velimirovi[cć]", "Velimirovic"),
    (r"полугаевск\w{0,3}|polugaevsky", "Polugaevsky"),
    (r"чебаненк\w{0,2}|chebanenko", "Chebanenko"),
    (r"стоунвол+\w{0,3}|stonewall", "Stonewall"),
    (r"к[эе]мбридж[\s-]+спрингс|cambridge\s+springs", "Cambridge Springs"),
]
# What a name is a name of: «вариант Алапина», «атака в стиле Алёхина», «система Ботвинника», "the Alapin
# Variation", "Alekhine's Defense". A bare surname is a person, not a variation («Алёхин любил…»).
_KIND_RU = (r"(?:вариант\w*|систем\w*|атак\w*|гамбит\w*|защит\w*|контратак\w*|контргамбит\w*|ловушк\w*|построени\w*|"
            r"схем\w*|лини(?:я|ю|и|ей))")
_KIND_EN = r"(?:variation|attack|gambit|defen[cs]e|system|line|countergambit|counterattack|trap)"
_PERSON = "|".join(f"(?:{p})" for p, _ in _PEOPLE)
_PERSON_PHRASE = re.compile(
    rf"{_W}{_KIND_RU}\s+(?:[а-яё-]+\s+){{0,2}}?(?P<ru>{_PERSON}){_E}"
    # any other name of the book after the kind noun (book_name decides: «вариант Левенфиша»)
    rf"|{_W}(?:вариант\w*|систем\w*|атак\w*|гамбит\w*)\s+(?P<ru2>[а-яё]{{4,}}(?:-[а-яё]{{3,}})?){_E}"
    rf"|{_W}(?P<en>{_PERSON})(?:'s)?\s+{_KIND_EN}{_E}"
    rf"|{_W}{_KIND_EN}\s+of\s+(?P<en2>{_PERSON}){_E}", re.IGNORECASE)
# Plain words that name a variation of an opening («открытый вариант сицилианской», "the Open Sicilian") — judged
# only as «the board is that variation» against what the board has not reached yet: the book names these lines
# narrowly (its Open Sicilian is 2...Nc6 3.d4 only), so a line elsewhere is no proof they are wrong.
_PLAIN = [(r"открыт", "Open"), (r"закрыт", "Closed"), (r"разменн", "Exchange"), (r"продвинут", "Advance"),
          (r"ускоренн", "Accelerated")]
_PLAIN_PHRASE = re.compile(
    rf"{_W}(?P<ru>{'|'.join(p for p, _ in _PLAIN)})\w*\s+(?:(?:вариант|систем)\w*|(?:сицилианск|испанск|французск|"
    rf"дракон|славянск|каро)\w*)"
    rf"|{_W}(?P<en>open|closed|exchange|advance|accelerated)\s+(?:variation|sicilian|ruy|spanish|french|dragon|slav|caro)",
    re.IGNORECASE)
_PLAIN_EN = {"open": "Open", "closed": "Closed", "exchange": "Exchange", "advance": "Advance",
             "accelerated": "Accelerated"}
# open_plain (plan 31.10): the two plain words that are also everyday adjectives — «классический», «современный».
# The book calls the line Russian players call «классический» Classical, Orthodox, Normal or Main Line.
_PLAIN_1031 = [(r"классическ", "Classical"), (r"современн", "Modern")]
_PLAIN_EN_1031 = {"classical": "Classical", "modern": "Modern"}
_GENERIC = {"Classical": ("Classical", "Orthodox", "Normal", "Main Line"), "Modern": ("Modern",)}
_ADJ_1031 = "|".join(p for p, _ in _PLAIN + _PLAIN_1031)
_EN_1031 = "|".join(list(_PLAIN_EN) + list(_PLAIN_EN_1031))
# «классический вариант», «классическая система» (the variation said plainly); «вариант «современный»»; «классическая
# сицилианская», «классический ферзевый гамбит», «классическая защита Каро-Канн» (an opening, read below); English.
_PLAIN_PHRASE_1031 = re.compile(
    rf"{_W}(?P<ru>{_ADJ_1031})\w*\s+(?P<rest>[^,.;:!?()«»\"\n]{{1,40}})"
    rf"|{_W}(?:вариант|систем)\w*\s+[«\"„]?(?P<ru2>{_ADJ_1031})\w*[»\"“]?{_E}"
    rf"|{_W}(?P<en>{_EN_1031})\s+(?P<enrest>[a-z'-]+(?:\s+[a-z'-]+)?)", re.IGNORECASE)
_KIND_NOUN = re.compile(r"(?:вариант|систем)\w*" + _E, re.IGNORECASE)
_KIND_NOUN_EN = re.compile(r"(?:variation|system|line)" + _E, re.IGNORECASE)
_OPENING_WORD = re.compile(r"(?:защит|парти|дебют|начал)\w*\s+$", re.IGNORECASE)

# An ECO code: «C70», «(B22)», «код E20»; Cyrillic lookalikes «С70», «В20», «Е20», «А40» the model writes too.
_ECO = re.compile(r"(?<![A-Za-zА-Яа-яЁё0-9])(?P<l>[A-EАВСЕ])(?P<d>\d\d)(?![0-9A-Za-zА-Яа-яЁё])")
_CYR_LETTER = {"А": "A", "В": "B", "С": "C", "Е": "E"}
# «C60–C99», «от C60 до C99», "C60 to C99": a range — what an opening covers, not the code of a position.
_ECO_RANGE = re.compile(r"[A-EАВСЕ]\d\d\s*(?:[-–—…]|\.\.\.?|до|to|по)\s*[A-EАВСЕ]?\d\d")
# A code is judged only when its clause ties it to the board (review 30.10): «Это испанская партия, код C65», «На
# доске сицилианская (B90)», «Код нашей партии — B33». A code in a clause about something else — another opening
# the lexicon cannot name («…, а принятый гамбит идёт под D20», «берлинский эндшпиль — C67»), the student's options
# («Принять гамбит — D20, отказаться — D30»), a player («Карлсен часто играет C67»), a bare surname («Свешников
# (B33)») — is left alone. Clauses break at «;» and at a contrast («, а», «, но», ", while").
_CLAUSE_BREAK = re.compile(r";|,\s*(?:а|но|и|или|зато|хотя|тогда\s+как|while|whereas|but|and|or)(?![а-яёa-z])"
                           r"|(?<![а-яёa-z])(?:а\s+вот|тогда\s+как|в\s+то\s+время\s+как|whereas)(?![а-яёa-z])",
                           re.IGNORECASE)
_TIE = re.compile(_W + r"(?:перед\s+нами|у\s+нас|на\s+доске|в\s+(?:нашей\s+|этой\s+)?партии|наш\w*\s+(?:парти|дебют|вариант)\w*|"
                  r"эт(?:от|ого|ой|а|у|им|ом)\s+(?:дебют|вариант|позици|парти|начал|защит|систем|лини)\w*|"
                  r"разыгр\w*|сыгран\w*|называется|здесь|тут|this\s+(?:is|opening|variation|position|line)|it'?s|"
                  r"it\s+is|we\s+have|our\s+game|on\s+the\s+board|here|бұл)" + _E, re.IGNORECASE)
# «это» ties a clause to the board when nothing named stands before it: «Это испанская партия, C65» — not «Дракон —
# это B70», where «это» points back at the dragon.
_THIS = re.compile(_W + r"(?:это|this)" + _E, re.IGNORECASE)
# A question for the code or name of the board ties a bare «Код — C68.»; a clause that names an opening of its own
# does not («Принятый гамбит — D20»).
_ASKS_CODE = re.compile(r"(?<![а-яёa-z])(?:код\w*|eco)(?![а-яёa-z])", re.IGNORECASE)
_OPENING_NOUN = re.compile(_W + r"(?:дебют|вариант|защит|гамбит|парти|начал|систем|атак|эндшпил|стен|линия|"
                           r"defen|gambit|variation|opening|attack|system|game|line)", re.IGNORECASE)

# A hedge before a name: it is compared, not claimed («не путай с атакой Панова», «похоже на вариант…»); a variation
# ahead, possible, a choice, the popular one or the student's advice is no claim that the board is it («…и вариант
# Найдорфа здесь ещё впереди», «самый популярный её вариант — Найдорф», «Найдорф — то, что тебе подойдёт»), a
# relative is not the variation itself («московский вариант, родственник варианта Россолимо») — review 30.10.
_HEDGE = re.compile(_W + r"(?:не|нет|похож\w*|напомина\w*|отлич\w*|в\s+отличие|вместо|как\s+в|путай|переход\w*|"
                    r"перейд\w*|ведет|ведут|приведет|станет|может|могут|бывает|впереди|возмож\w*|выбор\w*|выбира\w*|"
                    r"популярн\w*|подойд\w*|подход\w*|родствен\w*|сродни|близ\w*|аналог\w*|unlike|like|not|instead|"
                    r"leads?|transpos\w*|could|would|ahead|possible|choice|popular|suits?|related|similar|akin)" + _E,
                    re.IGNORECASE)
# The name is the predicate of «the board is …» — «Это открытый вариант…», «Перед нами вариант Найдорфа», «Сейчас на
# доске …», "This is the Open Sicilian", «Это сицилианская защита, открытый вариант» — the text before it is the
# identity alone, not a sentence going on to another subject («Это сицилианская защита, и вариант Найдорфа…»,
# «Это французская защита: здесь начинается выбор между вариантом Винавера…» — review 30.10).
_PREDICATE = re.compile(
    r"^[\s*_#>«\"'(-]*(?:(?:да|итак|так|ну|yes|so|well)[\s,]+)?"
    r"(?:(?:[а-яёa-z-]+|(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?[kqrbnкфлс]?[a-h]?x?[a-h][1-8][+#]?)\s+){0,4}?"
    r"(?:это|перед\s+(?:нами|тобой|вами)|у\s+(?:нас|тебя|вас|бел\w+|ч[её]рн\w+)|на\s+доске|разыграли|сыграли|называется|"
    # fix 01.11: the identity told as what came out or what a side chose — «Получился Дракон», «Чёрные выбрали
    # Дракон», «Ты играешь против Дракона» (past or the present of the game; «выбирай», «выбор» stay hedges)
    r"получил(?:ся|ась|ось|ись|и|а)?|получается|выбрал[аи]?|избрал[аи]?|"
    r"(?:ты|мы|вы|белые|ч[её]рные|соперник)\s+(?:сейчас\s+)?игра(?:ешь|ем|ете|ют|ет)(?:\s+(?:против|в|за))?|"
    r"(?:мы|ты|вы)\s+(?:сейчас\s+|уже\s+)?во?|переш(?:ла|ли|[её]л)\s+в|"
    r"(?:you\s+are|you'?re|we\s+are|we'?re)\s+(?:now\s+)?(?:playing|facing|in)(?:\s+against)?|"
    r"(?:black|white|you|we)\s+(?:chose|picked|went\s+for)|(?:it|this)\s+(?:has\s+)?(?:became|become|turned\s+into)|"
    r"we(?:'ve|\s+have)?\s+got|this\s+is|that'?s|it'?s|it\s+is|we\s+have|is\s+called|бұл)"
    r"(?:\s+(?:здесь|тут|сейчас|теперь|уже|именно|как\s+раз|сам(?:ый|ая|ое)|настоящ\w+|типичн\w+|классическ\w+|"
    r"так\s+называем\w+|знаменит\w+|известн\w+|на\s+доске|в\s+партии|here|now|already|exactly|the|an?|typical|"
    r"so-called|famous|well-known))*"
    r"\s*[—–:-]?\s*(?:[^,.;:!?—–]{1,40},\s*)?$", re.IGNORECASE)
# «Наш дебют — Дракон», «Позиция: Найдорф» — the board's own noun as the subject, the name after the dash (fix 01.11);
# not «Лучший вариант — Дракон», where «вариант» is a choice
_SUBJECT_DASH = re.compile(r"^[\s*_#>«\"'(-]*(?:(?:наш|тво|мо|эт)\w*\s+)?(?:дебют|позици[яи])(?:\s+(?:сейчас|теперь|на\s+доске))?"
                           r"\s*[—–:]\s*$", re.IGNORECASE)
# A name opening the sentence is a headline («Открытый вариант сицилианской защиты, и у белых…») — unless the sentence
# goes on to say what the variation is («Вариант Найдорфа — это то, что тебе подойдёт»): then it is the subject.
_SUBJECT_TAIL = re.compile(r"[—–:]|\s-\s|(?<![а-яёa-z])(?:это|является|считается|бывает|is|was|means)(?![а-яёa-z])",
                           re.IGNORECASE)
# A contrast starts another clause: «2.Кf3 d6 3.d4, а вариант Алапина 2.c3…» — the name is not 3.d4's.
_CONTRAST = re.compile(r",\s*(?:а|но|и|или|зато|хотя|тогда\s+как|while|whereas|but|and|or)(?![а-яёa-z])"
                       r"|(?<![а-яёa-z])(?:а\s+вот|тогда\s+как|в\s+то\s+время\s+как|whereas)(?![а-яёa-z])", re.IGNORECASE)
_HEADLINE = re.compile(r"^[\s*_#>«\"'(-]*")


def _book():
    from src.openings_book import get_book

    return get_book()


def _has_word(name: str, word: str) -> bool:
    return re.search(r"(?<![A-Za-zÀ-ÿ])" + re.escape(word) + r"(?![a-zà-ÿ])", name, re.IGNORECASE) is not None


_KNOWN: dict = {}


def _book_knows(word: str) -> bool:
    """The book names some line by *word* — a name it does not use, it cannot judge."""
    if word not in _KNOWN:
        _KNOWN[word] = any(_has_word(e[1], word) for e in _book().entries)
    return _KNOWN[word]


def _person(match) -> Optional[str]:
    said = (match["ru"] or match.groupdict().get("ru2") or match["en"] or match["en2"] or "").lower().replace("ё", "е")
    for pattern, word in _PEOPLE:
        if re.fullmatch(pattern, said, re.IGNORECASE):
            return word if _book_knows(word) else None
    return book_name(said)


# ── every variation name of the book, said in Russian (review-miss2 01.11) ──────────────────────────────────────────
# The list above is the names the coach said in the reviewed answers; «Это Калашников», «вариант Левенфиша» name
# lines of the book too. Each capitalised word of a variation name (after «:») is indexed by a Latin skeleton, and a
# Russian word is looked up by its transliteration with its case ending taken off: Калашникова → kalashnikov,
# Левенфиша → levenfish, Найдорфа → naidorf. Generic words (Variation, Classical, Line…) are not names.
_GENERIC_NAME_WORDS = frozenset(
    "Variation Gambit Defense Attack Classical Line System Modern Knights Closed Fianchetto Exchange Countergambit Main "
    "King's Anglo- Two English Orthodox Accepted Normal Advance Open Symmetrical Indian Anti- Four Slav Spanish Semi- "
    "Reversed Declined Yugoslav Mc Smith- Scotch Benoni Bishop's Pawn Accelerated Formation Sicilian Three Pawns Double "
    "O' Wing Neo- Queen's Old New Black White Center Centre Central Counterattack Countergambit Trap Opening Game "
    "Hedgehog Hyperaccelerated Deferred Improved Lines Grand Little Great Short Long Quiet Wild Dutch French Italian "
    "Russian Polish Swedish Danish Norwegian Hungarian Czech Austrian German Dutch Portuguese Catalan Vienna Ruy Lopez "
    "Giuoco Piano Pianissimo Two Knights Elephant Latvian Philidor Petrov Petroff Pirc Robatsch Modern Caro Kann Slav "
    "Semi-Slav Grünfeld Nimzo Bogo Benko Budapest Englund Bird Larsen Réti Reti King Queen Rook Knight Bishop".split())
_FAMOUS_PEOPLE = frozenset("morphy steinitz lasker capablanca alekhine alekhin botvinnik petrosian karpov tarrasch chigorin "
                           "tal fischer kasparov spassky smyslov euwe anand carlsen kramnik nimzowitsch nimzovich "
                           "anderssen philidor staunton".split())
_LAT = [("sch", "sh"), ("tsch", "ch"), ("tch", "ch"), ("tz", "ts"), ("ck", "k"), ("ph", "f"), ("w", "v"), ("j", "i"),
        ("y", "i"), ("x", "ks"), ("qu", "kv"), ("q", "k")]
_CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "i",
        "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
        "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "iu", "я": "ia"}
_RU_ENDINGS = ("ого", "ему", "ому", "ыми", "ими", "ая", "ое", "ий", "ый", "ой", "ую", "ом", "ым", "им", "ов", "ах", "ам",
               "ей", "а", "у", "е", "ы", "и", "я", "ю", "")


def _skeleton(latin: str) -> str:
    import unicodedata

    w = unicodedata.normalize("NFKD", latin.lower())
    w = "".join(ch for ch in w if not unicodedata.combining(ch))
    w = re.sub(r"[^a-z]", "", w)
    for a, b in _LAT:
        w = w.replace(a, b)
    w = w.replace("c", "k").replace("kh", "h")
    return re.sub(r"(.)\1+", r"\1", w)


@lru_cache(maxsize=1)
def _book_name_index() -> dict:
    """{skeleton: the book's word} for every name word of the book's variation names."""
    out: dict = {}
    try:
        for e in _book().entries:
            tail = e[1].split(":", 1)[1] if ":" in e[1] else ""
            for w in re.findall(r"[A-ZÀ-Þ][a-zà-ÿ]+(?:-[A-ZÀ-Þ][a-zà-ÿ]+)?", tail):
                if w in _GENERIC_NAME_WORDS or len(w) < 4:
                    continue
                for variant in {w, w.replace("ch", "kh")}:
                    out.setdefault(_skeleton(variant), w)
    except Exception:  # noqa: BLE001 — no book, no names
        return {}
    return out


def book_name(said: str) -> Optional[str]:
    """The book's name word a Russian (or Latin) word *said* is, with its case ending, or None."""
    w = (said or "").lower().replace("ё", "е")
    if len(w) < 4:
        return None
    index = _book_name_index()
    if re.fullmatch(r"[a-z'-]+", w):
        return index.get(_skeleton(w))
    if not re.fullmatch(r"[а-я-]+", w):
        return None
    for end in _RU_ENDINGS:
        if end and not w.endswith(end):
            continue
        stem = w[: len(w) - len(end)] if end else w
        if len(stem) < 4:
            continue
        lat = "".join(_CYR.get(ch, ch) for ch in stem)
        got = index.get(_skeleton(lat))
        if got:
            return got
    return None


def _bare_book_name(said: str) -> Optional[str]:
    """A name said bare that the book gives to the lines of one opening, not a great player's (talked about as a person
    as often): «Это Калашников», «Получился Левенфиш»."""
    word = book_name(said)
    if word is None or _skeleton(word) in {_skeleton(x) for x in _FAMOUS_PEOPLE}:
        return None
    return word if _home_family(word) is not None else None


def _start(board: chess.Board) -> bool:
    return board.board_fen() == chess.STARTING_BOARD_FEN


def _board_now(ctx) -> Optional[chess.Board]:
    """The position the student's board shows: the game's last position, else the board given first."""
    moves = getattr(ctx, "game_moves", None)
    if moves:
        board = chess.Board()
        try:
            for san in moves:
                board.push_san(san)
            return board
        except ValueError:
            pass
    return ctx.current


def _game_path(ctx) -> list:
    """The positions of the game on the board, in order — its opening's stages by the book."""
    moves = getattr(ctx, "game_moves", None) or []
    board, out = chess.Board(), []
    for san in moves:
        try:
            board.push_san(san)
        except ValueError:
            break
        out.append(board.copy(stack=False))
    return out


def _named_in(text: str) -> list:
    from src.openings_book import named_openings

    return named_openings(text)


def _families(entries) -> set:
    return {e[1].split(":")[0].strip() for e in entries}


def _describe(board: chess.Board) -> Optional[tuple[str, str]]:
    """(ECO, name) the book gives a position — its own line, else the deepest stage before it."""
    found = _book().by_position(board.fen())
    if found and not found.get("inside_line"):
        return found["eco"], found["name"]
    reached, _ = _book().lineage(board)
    if reached:
        from src.openings_book import _split_moves

        deepest = max(reached, key=lambda e: len(_split_moves(e[2])))
        return deepest[0], deepest[1]
    return None


# ── ECO codes ────────────────────────────────────────────────────────────────

def _clause(text: str, start: int, end: int) -> tuple[int, int]:
    """The clause of *text* around [start, end): from the last break before it to the next break after it."""
    left = max([b.end() for b in _CLAUSE_BREAK.finditer(text[:start])] or [0])
    right = _CLAUSE_BREAK.search(text, end)
    return left, right.start() if right else len(text)


def _tied_to_board(text: str, start: int, end: int, asks: bool) -> bool:
    """The code at [start, end) is said of the board: its clause says so before it («Это …, код C65», «на доске»), or
    the student asked for this board's code and the clause names nothing else («Код — C68.»)."""
    left, right = _clause(text, start, end)
    before = text[left:start]
    if _TIE.search(before):
        return True
    this = _THIS.search(before)
    if this and not re.search(r"[—–]|\s-\s", before[:this.start()]):
        return True
    rest = text[left:start] + text[end:right]
    return asks and not (_OPENING_NOUN.search(rest) or _named_in(rest) or _PERSON_PHRASE.search(rest.lower())
                         or re.search(_W + r"(?:" + _PERSON + r")" + _E, rest.lower()))


def _eco_issues(text: str, ctx) -> list[str]:
    from src.answer_check import _ASKS_BOARD_NAME

    codes = [(m, _CYR_LETTER.get(m["l"], m["l"]) + m["d"]) for m in _ECO.finditer(text)]
    if not codes:
        return []
    ranged = {i for r in _ECO_RANGE.finditer(text) for i in range(r.start(), r.end())}
    asked = {_CYR_LETTER.get(m["l"], m["l"]) + m["d"] for m in _ECO.finditer(ctx.question_raw or "")}
    book = _book()
    # The positions the sentence may be about: the board and the stages before it, the game's, the lines the
    # answer and the tools wrote (every board of the turn but the bare start standing in for an unknown one).
    positions = [b for b in ctx.boards if not _start(b) or (ctx.current is not None and _start(ctx.current))]
    positions += _game_path(ctx) + [b for _, b, _ in (ctx.scene_trail or [])]
    if ctx.scene is not None:
        positions.append(ctx.scene)
    allowed: set = set()
    board_codes: set = set()
    now = _board_now(ctx)
    for board in positions:
        reached, _ = book.lineage(board)
        allowed.update(e[0] for e in reached)
    if now is not None:
        board_codes = {e[0] for e in book.lineage(now)[0]}
    for board in _game_path(ctx):
        board_codes.update(e[0] for e in book.lineage(board)[0])
    if not allowed:
        return []  # no position of the turn is in the book: the code cannot be judged
    # An opening the sentence names gives its own codes: «в отличие от итальянской (C50)».
    on_board = _families(book.lineage(now)[0]) if now is not None else set()
    for name, is_line in _named_in(text):
        family = name.split(":")[0].strip()
        for entry in book.entries:
            if entry[1] == name or (entry[1].startswith(name) and (is_line or family not in on_board)):
                allowed.add(entry[0])
    for m in list(_PERSON_PHRASE.finditer(text.lower())):
        word = _person(m)
        if word:
            allowed.update(e[0] for e in book.entries if _has_word(e[1], word))
    allowed |= getattr(ctx, "text_codes", set()) | asked
    q = ctx.question_raw or ctx.question or ""
    asks = bool(_ASKS_CODE.search(q) or _ASKS_BOARD_NAME.search(q)) and not _named_in(q)
    out = []
    for m, code in codes:
        if code in allowed or m.start() in ranged:
            continue
        if not _tied_to_board(text, m.start(), m.end(), asks):
            continue
        if CONDITIONAL.search(text[:m.start()]) or denied_before(text, m.start()):
            continue
        if not book.by_eco(code):
            continue  # not a code the book has («E99» of some other list): nothing to compare
        truth = _describe(now) if now is not None else None
        where = f"by the ECO book the board is {truth[0]} ({truth[1]})" if truth else "the book has other codes here"
        known = ", ".join(sorted(board_codes)) if board_codes else ""
        out.append(f"{code} is not the ECO code of this opening: {where}"
                   + (f"; the codes of its stages are {known}" if known else "")
                   + f" — {code} is the {book.by_eco(code)[0][1]}")
    return out


# ── Variation names ──────────────────────────────────────────────────────────

def _from_known(ctx, move: chess.Move, after: chess.Board, first: bool) -> bool:
    """*after* follows from a position the turn knows — not from the bare start standing in for an unknown one:
    «Спокойнее — 2.d3, вариант Брейера» about 1.e4 c6 was read from the start as 1.d3, the Mieses Opening
    (prod run 23.10 replayed without the position the tool had put on the board)."""
    now = _board_now(ctx)
    key = after.board_fen() + (" w" if after.turn else " b")
    for board in ctx.boards:
        if move not in board.legal_moves:
            continue
        trial = board.copy(stack=False)
        trial.push(move)
        if trial.board_fen() + (" w" if trial.turn else " b") != key:
            continue
        if not _start(board) or (now is not None and _start(now)) or first:
            return True
    return False


def _written_moves(converted: str, ctx) -> list:
    """The moves this sentence wrote, each with its place in *converted* and the position after it — those whose
    position the turn really knows: a move number that fits the position, a position of the turn before it."""
    from src.answer_check import _MOVE

    trail = list(ctx.scene_trail or [])
    out, k, line_end = [], 0, -1
    for m in _MOVE.finditer(converted):
        if k >= len(trail):
            break
        san, after, move = trail[k]
        # a bare square is a move only numbered or going on from a move (the way _san_issues reads it): «конь на c3»
        # is no pawn move c3
        bare = not (m["num"] or m["bdots"]) and m["san"][0] in "abcdefgh" and "x" not in m["san"]
        if bare and (line_end < 0 or converted[line_end:m.start()].strip()):
            continue
        if not (m["san"].rstrip("+#") == san.rstrip("+#")
                or m["san"][-2:] == san.rstrip("+#")[-2:] and m["san"][0] == san[0]):
            continue
        k += 1
        line_end = m.end()
        known = True
        if m["num"]:
            number, black = int(m["num"]), (m["dots"] or "") in ("...", "…")
            known = (after.fullmove_number, after.turn) == ((number + 1, chess.WHITE) if black else (number, chess.BLACK))
        known = known and _from_known(ctx, move, after, first=m["num"] == "1" and (m["dots"] or "") == ".")
        if known:
            out.append((m.start(), m.end(), san, after))
    return out


def _names(name: str, word: str) -> bool:
    """The book line *name* carries the variation name *word*. A generic plain word (open_plain: Classical with its
    synonyms, Modern) counts only as the variation's own name — the part after «:» up to the first «,»: «Sicilian
    Defense: Classical Variation» is the Classical Sicilian, «Ruy Lopez: Open, Classical Defense» is not a Classical
    Ruy Lopez, «Sicilian Defense: Dragon Variation, Classical Variation» is a Dragon."""
    synonyms = _GENERIC.get(word)
    if synonyms is None:
        return _has_word(name, word)
    head = name.split(":", 1)[1].split(",")[0] if ":" in name else ""
    return any(_has_word(head, w) for w in synonyms)


def _consistent(entries, word: str, family: Optional[str] = None) -> bool:
    return any(_names(e[1], word) and (family is None or e[1].startswith(family)) for e in entries)


_HOME: dict = {}


def _home_family(word: str) -> Optional[str]:
    """The opening most of the book's lines named after *word* belong to (more than half of them), or None.

    Alekhine (56 of 101 in the Alekhine Defense), Najdorf, Winawer, Sveshnikov name one opening: a move of another
    one, or of another branch, called by that name is the coach's mistake. Capablanca, Tarrasch, Rubinstein,
    Zaitsev are spread over many openings, and players attach them to lines the book names otherwise («вариант
    Капабланки» for 4.Qc2 in the Nimzo-Indian, the book's Classical Variation — review 30.10): no verdict."""
    if word not in _HOME:
        from collections import Counter

        counts = Counter(e[1].split(":")[0].strip() for e in _book().entries if _has_word(e[1], word))
        total = sum(counts.values())
        top = counts.most_common(1)
        _HOME[word] = top[0][0] if top and top[0][1] * 2 > total else None
    return _HOME[word]


def _said_of_board(lowered: str, start: int, end: int, after_told: bool = False, told: bool = False,
                   headline: bool = True) -> bool:
    """The name at [start, end) is what the sentence says the board is: the predicate of an identity («Это
    открытый вариант…», «Перед нами вариант Найдорфа»), or a headline opening the sentence that the sentence does
    not go on to describe («Открытый вариант сицилианской защиты, и у белых…», prod 29.10). *after_told*
    (open_recap): the identity may follow the moves told, after the last «:», «—» or «;» before it («Nf3 — и чёрные
    ответили d6: это классическая сицилианская», st1#2)."""
    if _PREDICATE.match(lowered[:start]) or _SUBJECT_DASH.match(lowered[:start]):
        return True
    if after_told:
        cut = max(lowered.rfind(sep, 0, start) for sep in (":", "—", "–", ";"))
        if cut >= 0 and _PREDICATE.match(lowered[cut + 1:start]):
            return True
        # fix 01.11: «Позиция после 1.e4 c5 2.Nf3 d6 — классический вариант сицилианской»: the game's record told up
        # to now (*told*) is the subject, the dash the copula, the name its predicate
        if told and cut >= 0 and lowered[cut] in "—–" and not lowered[cut + 1:start].strip(" «\"*_"):
            return True
    if not headline or start > len(_HEADLINE.match(lowered).group(0)) + 1:
        return False
    tail = re.split(r"[,.;!?]", lowered[end:], 1)[0]
    return not _SUBJECT_TAIL.search(tail)


# fix 01.11 (review-miss: «это Дракон», «Перед нами Найдорф», «Чёрные выбрали Дракон», «это Najdorf» were never read):
# a variation's head word said bare, without «вариант» — the head, or the adjective made from it with a kind noun
# after it («шевенингенская структура», «меранский вариант»). A bare surname is a person as often as a variation («Это
# Найдорф придумал…», «Алёхин любил…»), so it is read as a name only (_bare_heads) when it ends its clause — nothing
# after it but the clause's end or a «без …»/«с …» that qualifies it — and below only as the predicate of «the board
# is …», of an opening its lines mostly belong to, which is the board's own opening.
_BARE_HEAD = re.compile(rf"{_W}(?P<head>{_PERSON})(?P<adj>ск(?:ий|ая|ое|ие|ого|ой|ую|им|ом|их))?"
                        rf"(?:\s+(?:вариант|систем|структур|схем|построени|variation|system|structure|line)\w*)?{_E}",
                        re.IGNORECASE)
_BARE_TAIL = re.compile(r"\s*(?:$|[,.;:!?)(\]—–]|\s-\s|(?:без|с|со|without|with)\s|в\s+(?:чистом|классическом|полном)\s+виде|"
                        r"как\s+(?:он|она)\s+есть|in\s+its\s+pure\s+form)", re.IGNORECASE)
# any other word said bare in the same place: a name of the book (_bare_book_name)
_BARE_ANY = re.compile(rf"{_W}(?P<head>[а-яё]{{4,}}(?:-[а-яё]{{3,}})?){_E}", re.IGNORECASE)
# a family word right before the head: «сицилианский Дракон», «сицилианская защита, Найдорф», "the Sicilian Najdorf"
_FAMILY_GAP = re.compile(r"\w*(?:\s+(?:защит|парти|дебют)\w*)?\s*,?\s*$", re.IGNORECASE)


_AFTER_RECORD = re.compile(r"(?<![а-яёa-z])(?:после|after)\s*$", re.IGNORECASE)


def _without_told_after(lowered: str, converted: str, start: int) -> str:
    """*lowered* without the «после»/"after" that introduces the game's record told up to the name («Позиция после
    1.e4 c5 2.Nf3 d6 — …»): the record is the game's past, not a condition (fix 01.11)."""
    from src.answer_check import _MOVE

    first = next((m.start() for m in _MOVE.finditer(converted[:start])), None)
    if first is None:
        return lowered
    head = lowered[:first]
    lead = _AFTER_RECORD.search(head)
    return (head[:lead.start()] if lead else head) + lowered[first:]


# The names players say alone for the line itself («это Найдорф», «у нас Земиш», «Получился Дракон»): eponyms known
# for their line, places and things. The great players (Morphy, Steinitz, Lasker, Capablanca, Alekhine, Botvinnik,
# Petrosian, Karpov, Tarrasch, Chigorin…) are talked about as people as often — «Это Морфи: развитие прежде всего» —
# so said bare they stay unjudged.
_BARE_OK = frozenset({
    "Alapin", "Najdorf", "Winawer", "Panov", "Maróczy", "Rauzer", "Richter", "Averbakh", "Scheveningen", "Taimanov",
    "Sozin", "Rossolimo", "Sveshnikov", "Pelikan", "Schliemann", "Zaitsev", "Sämisch", "Kieseritzky", "Falkbeer",
    "Morra", "Jaenisch", "Kan", "Møller", "Leningrad", "Meran", "Dragon", "Chelyabinsk", "Velimirovic",
    "Polugaevsky", "Chebanenko", "Stonewall", "Cambridge Springs", "Breyer", "Evans", "Marshall", "Paulsen",
})


def _bare_word(said: str) -> Optional[str]:
    said = said.lower().replace("ё", "е")
    for pattern, word in _PEOPLE:
        if re.fullmatch(pattern, said, re.IGNORECASE):
            return word if word in _BARE_OK and _book_knows(word) else None
    return None


def _bare_heads(lowered: str, taken: list) -> list:
    """(start, end, word) of each head said bare in *lowered* outside the spans *taken* by other phrases; *start*
    goes back over a family word before the head («сицилианский Дракон»), so the predicate is read before both."""
    from src.openings_book import _FAMILIES_RE

    out = []
    for m in _BARE_HEAD.finditer(lowered):
        if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
            continue
        word = _bare_word(m["head"])
        if word is None or not _BARE_TAIL.match(lowered[m.end():]):
            continue
        start = m.start()
        taken = taken + [(m.start(), m.end())]
        for rx, _name in _FAMILIES_RE:
            for f in rx.finditer(lowered[:start]):
                if _FAMILY_GAP.fullmatch(lowered[f.end():start]) and f.start() < start:
                    start = min(start, f.start())
        out.append((start, m.end(), word))
    for m in _BARE_ANY.finditer(lowered):
        if any(a <= m.start() < b or a < m.end() <= b for a, b in taken) or \
                any(a <= m.start() < b for a, b, _w in out):
            continue
        if not _BARE_TAIL.match(lowered[m.end():]) or not _PREDICATE.match(lowered[:m.start()]):
            continue
        word = _bare_book_name(m["head"])
        if word is not None and _book_knows(word):
            out.append((m.start(), m.end(), word))
    return out


def _plain_phrases(lowered: str) -> list:
    """The plain variation names of *lowered* (open_plain): (start, end, word, of_opening) — *of_opening* when the
    word qualifies an opening («классическая сицилианская», «классический ферзевый гамбит») rather than saying
    «вариант»/«система»; the old words (открытый, закрытый…) in the new forms too («вариант «открытый»»)."""
    from src.openings_book import named_openings

    out = []
    for m in _PLAIN_PHRASE_1031.finditer(lowered):
        if m["ru2"]:
            said = m["ru2"].lower()
            word = next((w for p, w in _PLAIN + _PLAIN_1031 if said.startswith(p)), None)
            if word:
                out.append((m.start(), m.end(), word, False))
            continue
        if m["en"]:
            word = {**_PLAIN_EN, **_PLAIN_EN_1031}.get(m["en"].lower())
            rest = m["enrest"] or ""
            if _KIND_NOUN_EN.match(rest):
                out.append((m.start(), m.start("enrest") + len(rest.split()[0]), word, False))
            elif named_openings(rest) and not _KIND_NOUN_EN.search(rest):
                one = rest.split()[0]
                out.append((m.start(), m.start("enrest") + (len(one) if named_openings(one) else len(rest)), word, True))
            continue
        said = m["ru"].lower()
        word = next((w for p, w in _PLAIN + _PLAIN_1031 if said.startswith(p)), None)
        rest = m["rest"] or ""
        if word is None:
            continue
        kind = _KIND_NOUN.match(rest)
        if kind:
            out.append((m.start(), m.start("rest") + kind.end(), word, False))
            continue
        # an opening right after the word, or after «защита/партия/дебют/начало»: the first family or line it names
        from src.openings_book import _FAMILIES_RE, _NAMED_RE

        hits = [(rx.search(rest), name) for rx, name in _NAMED_RE + _FAMILIES_RE]
        hits = [(h, name) for h, name in hits if h is not None and (h.start() == 0 or _OPENING_WORD.fullmatch(rest[:h.start()]))]
        if hits:
            first = min(hits, key=lambda x: x[0].start())[0]
            tail = re.match(r"[\w-]*", rest[first.end():]).end()  # to the end of the word: «сицилианск|ая»
            out.append((m.start(), m.start("rest") + first.end() + tail, word, True))
    return out


_LINE_FROM_ONE = re.compile(r"(?<![0-9])1\s?\.\s?(?:[KQRBN]?[a-h]?x?[a-h][1-8]|O-O)")
# A move the sentence denies writes no line: «Дракон без ...g6», «вместо 2.c3», «не 3.d4, а …», "instead of 2.c3".
_DENIED_MOVE = re.compile(r"(?:^|[\s(«\"*_])(?:без|вместо|кроме|не|ни|нет|without|instead\s+of|rather\s+than|not)"
                          r"\s+(?:(?:хода|ходом|ход)\s+)?[*_]*$", re.IGNORECASE)


def _key(board: chess.Board) -> str:
    from src.openings_book import _position_key

    return _position_key(board)


def _told_trail(converted: str, ctx) -> list:
    """The scene's moves of this sentence, each with where the text writes it: [(match or None, san, after)] —
    aligned the way _written_moves aligns them, without its filters. Every written move the walk followed counts —
    the scene's and those read as a plan on the start position (CheckContext.written_trail; start_scene sets no
    scene for those, yet a name next to them may be about their line)."""
    from src.answer_check import _MOVE

    trail = list(getattr(ctx, "written_trail", None) or ctx.scene_trail or [])
    out, k, line_end = [], 0, -1
    for m in _MOVE.finditer(converted):
        if k >= len(trail):
            break
        san, after, _move = trail[k]
        bare = not (m["num"] or m["bdots"]) and m["san"][0] in "abcdefgh" and "x" not in m["san"]
        if bare and (line_end < 0 or converted[line_end:m.start()].strip()):
            continue
        if not (m["san"].rstrip("+#") == san.rstrip("+#")
                or m["san"][-2:] == san.rstrip("+#")[-2:] and m["san"][0] == san[0]):
            continue
        out.append((m, san, after))
        k += 1
        line_end = m.end()
    out += [(None, san, after) for san, after, _ in trail[k:]]
    return out


def _writes_a_line(converted: str, ctx, start: int, recap: bool) -> bool:
    """The sentence writes a line of moves, so a name in it may be about any position of that line («…возникает
    после 2.Кf3 и 3.d4»). open_recap: the moves it denies and the game's own moves are no line — a move of the
    game (its position is one the game has passed) or a run of written moves before the name that is the game's
    record up to now (src/game_record.recap_end)."""
    numbered = [m for m in _LINE_FROM_ONE.finditer(converted)]
    if not recap:
        return bool(ctx.scene_trail or numbered)
    from src.game_record import recap_end

    moves = getattr(ctx, "game_moves", None) or []
    told = bool(moves) and recap_end(ctx, converted[:start], converted=True) == len(moves)
    played = {_key(b) for b in _game_path(ctx)}
    low = converted.lower()
    for m, _san, after in _told_trail(converted, ctx):
        if m is not None and m.start() < start and told:
            continue  # the game's record told up to now («Nf3 — и чёрные ответили d6: …»)
        if m is not None and _DENIED_MOVE.search(low[max(0, m.start() - 30):m.start()]):
            continue
        if _key(after) in played:
            continue
        return True
    return bool(numbered) and (not told or any(m.start() >= start for m in numbered))


def _name_issues(text: str, ctx, plain_1031: bool = False, recap: bool = False) -> list[str]:
    """*plain_1031*: open_plain; *recap*: open_recap (plan 31.10) — both False is main's check, byte for byte."""
    from src.answer_check import _ASKS_BOARD_NAME, _ON_THE_BOARD, _to_san

    converted, _ = _to_san(text)
    lowered = converted.lower()
    phrases = []
    for m in _PERSON_PHRASE.finditer(lowered):
        word = _person(m)
        if word:
            phrases.append((m.start(), m.end(), word, False, False, False))
    if plain_1031:
        phrases += [(s, e, w, True, of_opening, False) for s, e, w, of_opening in _plain_phrases(lowered)]
        phrases += [(s, e, w, False, False, True)
                    for s, e, w in _bare_heads(lowered, [(p[0], p[1]) for p in phrases])]
    else:
        for m in _PLAIN_PHRASE.finditer(lowered):
            said = (m["ru"] or "").lower()
            word = next((w for p, w in _PLAIN if said.startswith(p)), None) or _PLAIN_EN.get((m["en"] or "").lower())
            if word:
                phrases.append((m.start(), m.end(), word, True, False, False))
    if not phrases:
        return []
    from src.game_record import recap_end

    record = list(getattr(ctx, "game_moves", None) or [])
    book = _book()
    named = _named_in(converted)
    moves = _written_moves(converted, ctx)
    now = _board_now(ctx)
    out = []
    for start, end, word, plain, of_opening, bare in phrases:
        if _HEDGE.search(lowered[max(0, start - 40):start]) or denied_before(lowered, start):
            continue
        # open_recap (fix 01.11): the moves before the name are the game's record told up to now («Nf3 — и чёрные
        # ответили d6: это вариант Найдорфа»): they end at the board, so the name is said of the board — not of a
        # move of the record the walk met on an earlier position of the game (the move comment's boards are every
        # position of the game: «Nf3» was read on the board after 2.Nf3, where the Najdorf is still ahead)
        told = bool(recap and record and now is not None and recap_end(ctx, converted[:start], converted=True) == len(record))
        # A whole opening named by the person («защита Алехина», «защита Нимцовича») is the family check's; a named
        # line («вариант Найдорфа») said of the board is the identity check's (_opening_identity_issues), but
        # attached to a move («2.c3 — вариант Найдорфа») only this one reads it.
        if any(":" not in n and _has_word(n, word) for n, _ in named):
            continue
        line_named = any(_has_word(n, word) for n, _ in named)
        # The move the name is attached to: one written right after it («вариант Алапина 2.c3», «… — 2.c3») first,
        # else the last one before it in the same clause — «2.Кf3 d6 3.d4, а вариант Алапина 2.c3 считается…» names
        # 2.c3, not 3.d4 (review 30.10).
        attached = None
        if bare or (told and _said_of_board(lowered, start, end, after_told=True, told=True)):
            moves_here = []  # a bare head is read only as the board's predicate; the told record ends at the board
        else:
            moves_here = moves
        after = [mv for mv in moves_here if mv[0] >= end]
        if after and re.fullmatch(r"[\s*_—–:(-]*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?", converted[end:after[0][0]]):
            attached = after[0]
        before = [mv for mv in moves_here if mv[1] <= start]
        if attached is None and before:
            last = before[-1]
            gap = converted[last[1]:start]
            if len(gap) <= 90 and not re.search(r"[.!?;]", gap) and not _CONTRAST.search(gap):
                attached = last if not told else (last[0], last[1], record[-1], now)  # the told record ends at the board
        # open_recap: a plain name attached to the game's last move is said of the board now («…6...e5 — это
        # классический вариант»), judged below
        if attached is not None and not (plain and recap and now is not None and _key(attached[3]) == _key(now)
                                         and _key(attached[3]) in {_key(b) for b in _game_path(ctx)}):
            if plain:
                continue  # the book's plain names are narrow: judged only of the board, below
            _, _, san, position = attached
            san = (f"{position.fullmove_number}.{san}" if position.turn == chess.BLACK
                   else f"{position.fullmove_number - 1}...{san}")
            reached, ahead = book.lineage(position)
            if not reached and not ahead:
                continue  # out of the book: nothing to compare
            if _consistent(reached + ahead, word):
                continue
            home = _home_family(word)
            if home is None:
                continue  # a name the book spreads over many openings: players' usage may differ from the book's
            truth = _describe(position)
            whose = (f"; {word}'s lines are in the {home}" if home not in _families(reached + ahead) else
                     f"; {word}'s lines are other branches of the {home}")
            out.append((f"after {san} the position is the {truth[1]} ({truth[0]}) by the ECO book: no book line "
                        f"through it is named after {word}" if truth else
                        f"no book line through the position after {san} is named after {word}") + whose)
            continue
        if _writes_a_line(converted, ctx, start, recap):
            continue  # a line of moves: the name may be about any position of it («…возникает после 2.Кf3 и 3.d4»)
        # Said of the board: the name is the predicate of «Это…», «Перед нами…», or the sentence's headline; and about
        # the board in front of the student — a game, a question for its name, «здесь».
        if not _said_of_board(lowered, start, end, after_told=recap, told=told, headline=not bare):
            continue
        q = ctx.question_raw or ctx.question or ""
        asks_board = bool(_ASKS_BOARD_NAME.search(q)) and not _named_in(q)
        if not (getattr(ctx, "game_moves", None) or asks_board or _ON_THE_BOARD.search(lowered)):
            continue
        if CONDITIONAL.search(_without_told_after(lowered, converted, start) if told else lowered) \
                or _HEDGE.search(lowered) or lowered.rstrip().endswith("?"):
            continue  # «…получится, если белые сыграют…», «это может перейти в…», a question
        board = now
        if board is None:
            continue
        reached, ahead = book.lineage(board)
        if not reached:
            continue
        home = _home_family(word)
        if bare and (home is None or home not in _families(reached + ahead)):
            continue  # a bare name read as a variation only of the board's own opening, and only if it names one
        if plain_1031 and not plain and _structure_shown(board, word, home):
            continue  # the board already has the pawns of a line named so: players may call it that already
        family = None
        if plain:
            fams = [n.split(":")[0].strip() for n, _ in named] or sorted(_families(reached))
            family = next((f for f in fams if f in _families(reached + ahead)), None)
            if family is None:
                continue  # an opening that is not the board's: the family check's business
            if of_opening and word in _GENERIC:
                # «классическая испанская партия» on the bare Ruy Lopez is the classic Ruy Lopez, not its Classical
                # Variation: the word names a variation only once the board is in a named variation of the opening
                from src.openings_book import _split_moves

                own = [e for e in reached if e[1].startswith(family)]
                deepest = max(own, key=lambda e: len(_split_moves(e[2])), default=None)
                if deepest is None or ":" not in deepest[1]:
                    continue
        if _consistent(reached, word, family):
            continue
        truth = _describe(board)
        # A sub-line of a variation the board is already in is a name players give the whole variation: the
        # book's Sveshnikov begins 8...b5 inside the Lasker-Pelikan the board reached at 5...e5, its «Zaitsev» inside
        # the Closed Ruy (review 30.10).
        stages = [e[1] for e in reached if ":" in e[1]]
        ahead_named = [e for e in ahead if _names(e[1], word) and (family is None or e[1].startswith(family))
                       and not any(e[1].startswith(s + ",") for s in stages)]
        # The turn has a position of that variation (the line the student steps through, a tool's line): the
        # name is about it, the board is on the way.
        shown = [b for b in ctx.boards if not _start(b) and _consistent(book.lineage(b)[0], word, family)]
        if ahead_named and not shown:
            from src.openings_book import _split_moves

            # the line named by the word itself before its synonyms («Classical» before «Normal»), the variation
            # itself before its sub-lines («Dragon Variation» before «Dragon Variation, Accelerated Dragon»), then the
            # shortest
            first = min(ahead_named, key=lambda e: (word in _GENERIC and not _has_word(e[1].split(":", 1)[-1].split(",")[0], word),
                                                    not _has_word(e[1].split(":", 1)[-1].split(",")[0], word), "," in e[1],
                                                    len(_split_moves(e[2]))))
            out.append(f"the board has not reached the {first[1]} yet — it begins {first[2]}; the position on the "
                       f"board is the {truth[1]} ({truth[0]}) by the ECO book")
        elif not plain and not _consistent(reached + ahead, word) and not shown \
                and (not line_named or (plain_1031 and home in _families(reached + ahead))):
            # Another opening's name for the board («Это вариант Свешникова» in the Ruy Lopez): only for a name the
            # book gives to one opening — a spread name may be the players' usage. Another branch of the board's own
            # opening («это сицилианская, вариант Свешникова» on 2...d6: the book's Sveshnikov lines all go 2...Nc6) is
            # judged here under open_plain (fix 01.11) — for a name the identity check knows too (*line_named*), since
            # that check reads only its own frames («Чёрные выбрали Тайманов» it does not).
            if home is not None and home not in _families(reached + ahead):
                out.append(f"the position on the board is the {truth[1]} ({truth[0]}) by the ECO book: no book line "
                           f"through it is named after {word}; {word}'s lines are in the {home}")
            elif home is not None and plain_1031 and not _other_eponym(reached, word) \
                    and not _names_the_board(lowered, truth, reached, named):
                out.append(f"the position on the board is the {truth[1]} ({truth[0]}) by the ECO book: no book line "
                           f"through it or on from it is named after {word}; {word}'s lines are other branches of the "
                           f"{home}")
    return out


_STRUCTURES: dict = {}


def _pawn_set(board: chess.Board) -> frozenset:
    return frozenset((sq, color) for color in chess.COLORS for sq in board.pieces(chess.PAWN, color))


def _structure_shown(board: chess.Board, word: str, home: Optional[str]) -> bool:
    """The pawns of *board* are those of a position some book line named after *word* ends in (of its home opening):
    the book names a line at one move order, players name the structure — «Получился Стоунволл» after 1.d4 f5 2.c4
    Nf6 3.g3 e6 4.Bg2 d5 has the Stonewall's f5-e6-d5 the book's lines reach later, with Be7 and castling (fix 01.11).
    A name whose line still needs a pawn the board lacks («Дракон» without g6, «Найдорф» without a6, «Свешников»
    without e5, «Шевенинген» without e6) is not shown."""
    key = (word, home)
    if key not in _STRUCTURES:
        from src.openings_book import _split_moves

        sets = []
        for e in _book().entries:
            if not _names(e[1], word) or (home is not None and not e[1].startswith(home)):
                continue
            b = chess.Board()
            try:
                for san in _split_moves(e[2]):
                    b.push_san(san)
            except ValueError:
                continue
            sets.append(_pawn_set(b))
        _STRUCTURES[key] = sets
    have = _pawn_set(board)
    return any(pawns == have for pawns in _STRUCTURES[key])


def _names_the_board(lowered: str, truth, reached, named) -> bool:
    """The sentence names the board's own line too — its book name, its ECO code, or a name the lexicon resolves to a
    line the board has reached («…вариант Атака Панова — точнее, по книге это B12 «Caro-Kann Defense: Advance
    Variation»»): it corrects itself, as src/answer_check._opening_identity_issues lets it."""
    if truth and (truth[0].lower() in lowered or truth[1].split(":", 1)[-1].strip().lower() in lowered):
        return True
    own = {e[1] for e in reached}
    return any(n in own for n, is_line in named if is_line)


def _other_eponym(reached, word: str) -> bool:
    """The board is already in a variation the book names after someone or something else (the Kan, the Najdorf):
    another eponym said of it may be a name players give that line which the book lacks — no verdict there."""
    heads = [e[1].split(":", 1)[1] for e in reached if ":" in e[1]]
    return any(w != word and _book_knows(w) and any(_has_word(h, w) for h in heads) for _, w in _PEOPLE)


def _index_at_hand() -> bool:
    """The book's position index is built, or may be built here. On the event loop (the text gate) it is never
    waited for: until it is built — in the background — the sentence is not judged by the book; a worker thread
    (POST voice/check) or a script builds it (as src/answer_check_facts._book_index does)."""
    import asyncio
    import threading

    from src.openings_book import _INDEX_LOCK, position_index_ready, warm_position_index

    if position_index_ready():
        return True
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return True  # not the event loop's thread: waiting here blocks nobody
    if not _INDEX_LOCK.locked():
        threading.Thread(target=warm_position_index, name="openings-book-index", daemon=True).start()
    return False


# ── content/openings/lines.yaml: what makes an opening, which lines are sharp ───────────────────────────────────

LINES_PATH = Path(__file__).resolve().parents[1] / "content" / "openings" / "lines.yaml"


@lru_cache(maxsize=1)
def opening_lines() -> dict:
    """content/openings/lines.yaml, parsed: {"openings": [...], "sharp": [...]} (P8 reads it too). Each opening gets
    "defining_moves": [(piece type, to square, from file, SAN)] of its `side`'s moves in `defining`. A missing or
    broken file gives empty lists: the two checks that read it then say nothing."""
    try:
        import yaml

        from src.openings_book import _split_moves

        raw = yaml.safe_load(LINES_PATH.read_text(encoding="utf-8")) or {}
        openings = []
        for o in raw.get("openings") or []:
            board, own = chess.Board(), []
            side = chess.WHITE if str(o.get("side", "")).lower() == "white" else chess.BLACK
            for san in _split_moves(o["defining"]):
                move = board.parse_san(san)
                if board.turn == side:
                    own.append((board.piece_type_at(move.from_square), move.to_square,
                                chess.square_file(move.from_square), san))
                board.push(move)
            openings.append({**o, "side_color": side, "defining_moves": own})
        return {"openings": openings, "sharp": list(raw.get("sharp") or [])}
    except Exception:  # noqa: BLE001 — curated data is a bonus; the checks stay silent without it
        logger.warning("content/openings/lines.yaml could not be read", exc_info=True)
        return {"openings": [], "sharp": []}


def _sharp_line(name: str) -> Optional[dict]:
    """The sharp line of lines.yaml the book line *name* is (or is a sub-line of)."""
    for line in opening_lines()["sharp"]:
        n = line["name"]
        if name == n or name.startswith(n + ",") or (":" not in n and name.startswith(n + ":")):
            return line
    return None


def _move_label(after: chess.Board, san: str) -> str:
    return (f"{after.fullmove_number}.{san}" if after.turn == chess.BLACK
            else f"{after.fullmove_number - 1}...{san}")


# ── open_character: «спокойная игра» said of a sharp line ───────────────────────────────────────────────────────
_CALM = re.compile(
    _W + r"(?:без\s+(?:[а-яё]+\s+){0,2}?осложнени\w*"
    r"|(?:спокойн|тих|мирн)\w*\s+(?:[а-яё]+\s+)?(?:игр|позици|вариант|систем|продолжени|лини|классик|борьб)\w*"
    r"|(?:quiet|calm|peaceful|tranquil)\s+(?:\w+\s+)?(?:game|play|line|variation|position|system)"
    r"|without\s+(?:\w+\s+){0,2}?complications|free\s+of\s+(?:\w+\s+)?(?:tactics|complications))" + _E, re.IGNORECASE)


_CALM_WORD = re.compile(r"осложнени|спокойн|тих|мирн|quiet|calm|peaceful|tranquil|complication|free\s+of", re.IGNORECASE)


def _character_issues(text: str, ctx) -> list[str]:
    """«6.Сe3 — он ведёт к понятной игре без тактических осложнений» in the Najdorf (move-najdorf): the move's position
    is a line content/openings/lines.yaml calls sharp (the English Attack). The calm words must be said of the move:
    the move right after them, or the last move before them in the same clause, nothing denied in between."""
    from src.answer_check import _to_san

    if not _CALM_WORD.search(text) or not opening_lines()["sharp"]:
        return []  # most sentences: no calm word, no SAN conversion
    converted, _ = _to_san(text)
    lowered = converted.lower()
    calm = list(_CALM.finditer(lowered))
    if not calm:
        return []
    moves = _written_moves(converted, ctx)
    if not moves:
        return []
    out = []
    for c in calm:
        if denied_before(lowered, c.start()) or DENIAL.search(lowered[max(0, c.start() - 12):c.start()]):
            continue
        attached = None
        after = [mv for mv in moves if mv[0] >= c.end()]
        if after and re.fullmatch(r"[\s*_—–:(-]*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?", converted[c.end():after[0][0]]):
            attached = after[0]
        before = [mv for mv in moves if mv[1] <= c.start()]
        if attached is None and before:
            gap = lowered[before[-1][1]:c.start()]
            if len(gap) <= 120 and not re.search(r"[.!?;]", gap) and not _CONTRAST.search(gap) and not DENIAL.search(gap):
                attached = before[-1]
        if attached is None:
            continue
        _, _, san, position = attached
        reached, _ = _book().lineage(position)
        hits = [(e, _sharp_line(e[1])) for e in reached]
        hits = [(e, s) for e, s in hits if s is not None]
        if not hits:
            continue
        from src.openings_book import _split_moves

        entry, sharp = max(hits, key=lambda h: len(_split_moves(h[0][2])))
        out.append(f"{_move_label(position, san)} is the {entry[1]} ({entry[0]}) by the ECO book — a sharp, tactical "
                   f"line ({sharp.get('why') or 'forcing play'}), not quiet play without complications")
    return list(dict.fromkeys(out))


# ── open_defining: advice not to make the opening's own move ───────────────────────────────────────────────────
_PIECE_WORDS = [(r"кон(?:ь|я|ю|ём|ем|ями|ей|ем)", chess.KNIGHT), (r"слон\w{0,3}", chess.BISHOP),
                (r"ферз\w{0,3}", chess.QUEEN), (r"ладь\w{0,3}|ладей", chess.ROOK), (r"пешк\w{0,3}|пешек", chess.PAWN),
                (r"knight", chess.KNIGHT), (r"bishop", chess.BISHOP), (r"queen", chess.QUEEN), (r"rook", chess.ROOK),
                (r"pawn", chess.PAWN)]
_PIECE_RE = "|".join(f"(?:{p})" for p, _ in _PIECE_WORDS)
_MOVE_VERB = (r"(?:выв(?:од|ед|ест)\w*|разви\w*|став\w*|постав\w*|игра\w*|сыгра\w*|ходи\w*|пойти|двига\w*|двину\w*|"
              r"выдвига\w*|выдвину\w*|толка\w*|продвига\w*|прыга\w*|пуска\w*|отправля\w*|"
              r"develop|play|move|put|push|bring\s+out)")
_ADVISE_NOT = re.compile(
    _W + r"(?:(?:логичнее|лучше|разумнее|правильнее|стоит|следует|надо|нужно|советую|рекомендую)\s+(?:[а-яё]+\s+)?не"
    r"|не\s+(?:стоит|следует|надо|нужно|спеши|торопись|советую|рекомендую|рекомендуется)"
    r"|не(?=\s+(?:выводи|ставь|играй|ходи|двигай|двигай|выдвигай|толкай|пускай|развивай)" + _E + r")"
    r"|(?:better|best)\s+not\s+to|don'?t|do\s+not|never|avoid)"
    r"\s+(?:[а-яёa-z]+\s+)?(?P<verb>" + _MOVE_VERB + r")" + _E
    + r"(?:\s+(?:the|your|a|сразу|рано|сначала)){0,2}\s+(?P<piece>" + _PIECE_RE + r")" + _E
    + r"(?P<tail>[^,.;!?]{0,30})", re.IGNORECASE)
_TO_SQUARE = re.compile(r"^\s*(?:на|в|to|on)\s+(?P<sq>[a-h][1-8])" + _E, re.IGNORECASE)
# the pawn's file: «пешку c5», «пешку c», «c-пешку» (before the word: read from *lowered* at the piece)
_PAWN_FILE = re.compile(r"^\s*(?:на\s+|с\s+)?(?P<f>[a-h])(?:[1-8])?(?![a-zа-яё0-9])", re.IGNORECASE)
_PAWN_FILE_BEFORE = re.compile(r"(?<![a-z])(?P<f>[a-h])-?\s*$", re.IGNORECASE)
_AGAINST = re.compile(_W + r"(?:против|against|vs\.?|versus)\s+$", re.IGNORECASE)
_SIDE_WORD = {chess.WHITE: re.compile(_W + r"(?:бел(?:ым|ые|ых|ыми)|за\s+белых|white)" + _E, re.IGNORECASE),
              chess.BLACK: re.compile(_W + r"(?:ч[её]рн(?:ым|ые|ых|ыми)|за\s+ч[её]рных|black)" + _E, re.IGNORECASE)}


def _defining_issues(text: str, ctx) -> list[str]:
    """«если играешь защиту Алехина, логичнее не выводить коня под e5» (g1-resign): 1...Nf6, inviting e4-e5, IS the
    Alekhine Defence (content/openings/lines.yaml `defining`). Advice to the side playing an opening not to make
    one of that opening's defining moves — the piece word maps to the move, a pawn needs its file or square, a
    square named for the piece («на c6») must be the move's — contradicts the opening itself. Not judged: an
    opening named after «против», advice addressed to the other side."""
    from src.openings_book import _FAMILIES_RE, _NAMED_RE

    data = opening_lines()["openings"]
    if not data:
        return []
    lowered = text.lower().replace("ё", "е")
    advice = list(_ADVISE_NOT.finditer(lowered))
    if not advice:
        return []
    named = []
    for rx, name in _NAMED_RE + _FAMILIES_RE:
        m = rx.search(lowered)
        if m and not _AGAINST.search(lowered[max(0, m.start() - 12):m.start()]):
            named.append(name)
    out = []
    for o in data:
        if not any(n == o["book"] or n.startswith(o["book"] + ":") or o["book"].startswith(n + ":") for n in named):
            continue
        if _SIDE_WORD[not o["side_color"]].search(lowered):
            continue  # advice to the other side («белым не стоит выводить коня на c3»)
        for a in advice:
            piece = next(t for p, t in _PIECE_WORDS if re.fullmatch(p, a["piece"], re.IGNORECASE))
            own = [d for d in o["defining_moves"] if d[0] == piece]
            if not own:
                continue
            tail = a["tail"] or ""
            to = _TO_SQUARE.match(tail)
            if to and chess.parse_square(to["sq"]) not in {d[1] for d in own}:
                continue
            if piece == chess.PAWN:
                f = _PAWN_FILE.match(tail) or _PAWN_FILE_BEFORE.search(lowered[:a.start("piece")])
                if not to and not (f and chess.FILE_NAMES.index(f["f"].lower()) in {d[2] for d in own}):
                    continue  # «не двигай пешку» alone does not say which pawn
            moves = ", ".join(d[3] for d in own)
            out.append(f"the {o['book']} is defined by {o['defining']}: {moves} is the opening's own move, not one to "
                       f"avoid when playing it; its main line goes {o['main']}"
                       + (f" — {o['idea']}" if o.get("idea") else ""))
            break
    return list(dict.fromkeys(out))


# ── the switches ────────────────────────────────────────────────────────────────────────────────────────────────

def _mode(name: str, ctx) -> str:
    try:
        from src.config import detector_mode

        return detector_mode(name, ctx)
    except Exception:  # noqa: BLE001 — a broken switch is a switched-off detector
        return "off"


def _shadow(ctx, name: str, text: str, issues: list) -> None:
    """A shadow detector's issues: logged and kept on ``ctx.detector_shadow`` as (name, sentence, issues), never shown."""
    from src.answer_check import record_shadow

    record_shadow(ctx, name, issues, text)


def _names_by_mode(text: str, ctx) -> list[str]:
    """_name_issues with open_plain and open_recap as their switches say: what an ``on`` detector finds is shown; what
    only a ``shadow`` one adds is logged."""
    plain, recap = _mode("open_plain", ctx), _mode("open_recap", ctx)
    shown = _name_issues(text, ctx, plain_1031=plain == "on", recap=recap == "on")
    if "shadow" in (plain, recap):
        computed = _name_issues(text, ctx, plain_1031=plain != "off", recap=recap != "off")
        extra = [i for i in computed if i not in shown]
        names = "+".join(n for n, m in (("open_plain", plain), ("open_recap", recap)) if m == "shadow")
        _shadow(ctx, names, text, extra)
    return shown


def _by_mode(name: str, judge, text: str, ctx) -> list[str]:
    mode = _mode(name, ctx)
    if mode == "off":
        return []
    issues = judge(text, ctx)
    if mode == "shadow":
        _shadow(ctx, name, text, issues)
        return []
    return issues


def opening_book_issues(text: str, ctx) -> list[str]:
    """The opening facts of *text* (one sentence) the ECO book denies; [] when it denies none or cannot tell."""
    if ctx is None or not _index_at_hand():
        return []
    try:
        out = _eco_issues(text, ctx) + _names_by_mode(text, ctx)
    except Exception:  # noqa: BLE001 — a broken lookup never stops an answer
        logger.debug("opening book check failed", exc_info=True)
        return []
    for name, judge in (("open_character", _character_issues), ("open_defining", _defining_issues)):
        try:
            out += [i for i in _by_mode(name, judge, text, ctx) if i not in out]
        except Exception:  # noqa: BLE001
            logger.debug("opening check %s failed", name, exc_info=True)
    return out
