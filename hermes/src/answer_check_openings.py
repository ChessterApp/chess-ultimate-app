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
"""

from __future__ import annotations

import re
from typing import Optional

import chess

from src.claim_scope import CONDITIONAL, denied_before

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
]
# What a name is a name of: «вариант Алапина», «атака в стиле Алёхина», «система Ботвинника», "the Alapin
# Variation", "Alekhine's Defense". A bare surname is a person, not a variation («Алёхин любил…»).
_KIND_RU = (r"(?:вариант\w*|систем\w*|атак\w*|гамбит\w*|защит\w*|контратак\w*|контргамбит\w*|ловушк\w*|построени\w*|"
            r"схем\w*|лини(?:я|ю|и|ей))")
_KIND_EN = r"(?:variation|attack|gambit|defen[cs]e|system|line|countergambit|counterattack|trap)"
_PERSON = "|".join(f"(?:{p})" for p, _ in _PEOPLE)
_PERSON_PHRASE = re.compile(
    rf"{_W}{_KIND_RU}\s+(?:[а-яё-]+\s+){{0,2}}?(?P<ru>{_PERSON}){_E}"
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
    r"^[\s*_#>«\"'(-]*(?:(?:да|итак|так|ну|yes|so|well)[\s,]+)?(?:[а-яёa-z-]+\s+){0,3}?"
    r"(?:это|перед\s+нами|у\s+нас|на\s+доске|разыграли|сыграли|называется|this\s+is|that'?s|it'?s|it\s+is|we\s+have|"
    r"is\s+called|бұл)"
    r"(?:\s+(?:здесь|тут|сейчас|теперь|уже|именно|как\s+раз|сам(?:ый|ая|ое)|настоящ\w+|типичн\w+|классическ\w+|"
    r"на\s+доске|в\s+партии|here|now|already|exactly|the|an?|typical))*"
    r"\s*[—–:-]?\s*(?:[^,.;:!?—–]{1,40},\s*)?$", re.IGNORECASE)
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
    said = (match["ru"] or match["en"] or match["en2"] or "").lower().replace("ё", "е")
    for pattern, word in _PEOPLE:
        if re.fullmatch(pattern, said, re.IGNORECASE):
            return word if _book_knows(word) else None
    return None


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


def _consistent(entries, word: str, family: Optional[str] = None) -> bool:
    return any(_has_word(e[1], word) and (family is None or e[1].startswith(family)) for e in entries)


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


def _said_of_board(lowered: str, start: int, end: int) -> bool:
    """The name at [start, end) is what the sentence says the board is: the predicate of an identity («Это
    открытый вариант…», «Перед нами вариант Найдорфа»), or a headline opening the sentence that the sentence does
    not go on to describe («Открытый вариант сицилианской защиты, и у белых…», prod 29.10)."""
    if _PREDICATE.match(lowered[:start]):
        return True
    if start > len(_HEADLINE.match(lowered).group(0)) + 1:
        return False
    tail = re.split(r"[,.;!?]", lowered[end:], 1)[0]
    return not _SUBJECT_TAIL.search(tail)


def _name_issues(text: str, ctx) -> list[str]:
    from src.answer_check import _ASKS_BOARD_NAME, _ON_THE_BOARD, _to_san

    converted, _ = _to_san(text)
    lowered = converted.lower()
    phrases = []
    for m in _PERSON_PHRASE.finditer(lowered):
        word = _person(m)
        if word:
            phrases.append((m.start(), m.end(), word, False))
    for m in _PLAIN_PHRASE.finditer(lowered):
        said = (m["ru"] or "").lower()
        word = next((w for p, w in _PLAIN if said.startswith(p)), None) or _PLAIN_EN.get((m["en"] or "").lower())
        if word:
            phrases.append((m.start(), m.end(), word, True))
    if not phrases:
        return []
    book = _book()
    named = _named_in(converted)
    moves = _written_moves(converted, ctx)
    out = []
    for start, end, word, plain in phrases:
        if _HEDGE.search(lowered[max(0, start - 40):start]) or denied_before(lowered, start):
            continue
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
        after = [mv for mv in moves if mv[0] >= end]
        if after and re.fullmatch(r"[\s*_—–:(-]*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?", converted[end:after[0][0]]):
            attached = after[0]
        before = [mv for mv in moves if mv[1] <= start]
        if attached is None and before:
            last = before[-1]
            gap = converted[last[1]:start]
            if len(gap) <= 90 and not re.search(r"[.!?;]", gap) and not _CONTRAST.search(gap):
                attached = last
        if attached is not None:
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
        if ctx.scene_trail or re.search(r"(?<![0-9])1\s?\.\s?(?:[KQRBN]?[a-h]?x?[a-h][1-8]|O-O)", converted):
            continue  # a line of moves: the name may be about any position of it («…возникает после 2.Кf3 и 3.d4»)
        # Said of the board: the name is the predicate of «Это…», «Перед нами…», or the sentence's headline; and about
        # the board in front of the student — a game, a question for its name, «здесь».
        if not _said_of_board(lowered, start, end):
            continue
        q = ctx.question_raw or ctx.question or ""
        asks_board = bool(_ASKS_BOARD_NAME.search(q)) and not _named_in(q)
        if not (getattr(ctx, "game_moves", None) or asks_board or _ON_THE_BOARD.search(lowered)):
            continue
        if CONDITIONAL.search(lowered) or _HEDGE.search(lowered) or lowered.rstrip().endswith("?"):
            continue  # «…получится, если белые сыграют…», «это может перейти в…», a question
        board = _board_now(ctx)
        if board is None:
            continue
        reached, ahead = book.lineage(board)
        if not reached:
            continue
        family = None
        if plain:
            fams = [n.split(":")[0].strip() for n, _ in named] or sorted(_families(reached))
            family = next((f for f in fams if f in _families(reached + ahead)), None)
            if family is None:
                continue  # an opening that is not the board's: the family check's business
        if _consistent(reached, word, family):
            continue
        truth = _describe(board)
        # A sub-line of a variation the board is already in is a name players give the whole variation: the
        # book's Sveshnikov begins 8...b5 inside the Lasker-Pelikan the board reached at 5...e5, its «Zaitsev» inside
        # the Closed Ruy (review 30.10).
        stages = [e[1] for e in reached if ":" in e[1]]
        ahead_named = [e for e in ahead if _has_word(e[1], word) and (family is None or e[1].startswith(family))
                       and not any(e[1].startswith(s + ",") for s in stages)]
        # The turn has a position of that variation (the line the student steps through, a tool's line): the
        # name is about it, the board is on the way.
        shown = [b for b in ctx.boards if not _start(b) and _consistent(book.lineage(b)[0], word, family)]
        if ahead_named and not shown:
            from src.openings_book import _split_moves

            first = min(ahead_named, key=lambda e: len(_split_moves(e[2])))
            out.append(f"the board has not reached the {first[1]} yet — it begins {first[2]}; the position on the "
                       f"board is the {truth[1]} ({truth[0]}) by the ECO book")
        elif not plain and not line_named and not _consistent(reached + ahead, word):
            # Another opening's name for the board («Это вариант Свешникова» in the Ruy Lopez): only for a name the
            # book gives to one opening, and not this one — another branch of the board's own opening is the
            # identity check's (one issue, not two), a spread name may be the players' usage.
            home = _home_family(word)
            if home is not None and home not in _families(reached + ahead):
                out.append(f"the position on the board is the {truth[1]} ({truth[0]}) by the ECO book: no book line "
                           f"through it is named after {word}; {word}'s lines are in the {home}")
    return out


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


def opening_book_issues(text: str, ctx) -> list[str]:
    """The opening facts of *text* (one sentence) the ECO book denies; [] when it denies none or cannot tell."""
    if ctx is None or not _index_at_hand():
        return []
    try:
        return _eco_issues(text, ctx) + _name_issues(text, ctx)
    except Exception:  # noqa: BLE001 — a broken lookup never stops an answer
        import logging

        logging.getLogger(__name__).debug("opening book check failed", exc_info=True)
        return []
