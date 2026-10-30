"""Opening facts the ECO book decides, checked in the coach's answer (prod check 29.10).

The live production check of 29.10 (theory set) found the coach naming openings from memory where the book on
the server knows them exactly:

  * «**2. c3** (система с последующим d4, любимая атака в стиле Алёхина)» — after 1.e4 c5 2.c3 the book's line
    is the Alapin Variation; no line through it carries Alekhine's name;
  * «Открытый вариант сицилианской защиты, и у белых тут три главных пути» on 1.e4 c5 — the Open Sicilian
    begins with 2.Nf3 and 3.d4, the board is the plain Sicilian (B20);
  * «белый конь обычно идёт на c3» after 1.e4 e5 2.f4 exf4 — the book works out 3.Nf3 (92 lines) and 3.Bc4 (29),
    3.Nc3 not at all.

Three claims are judged here, each only against the book (src/openings_book.py — the 3,800 named lines Hermes
ships), never from a guess:

  * an ECO code («вариант Морфи (C70)», «код E20») must be a code of the board's position or of a stage on the
    way to it, of a line the answer writes, or of an opening the sentence names;
  * a variation named by a person («вариант Алапина», «атака … Алёхина», "the Alapin Variation") attached to a
    written move must be a name of a book line through the position after that move or before it; said of the
    board («Это открытый вариант…», «Перед нами вариант Найдорфа»), it must be a line the board has reached —
    not one still ahead of it;
  * «обычно играют X», «главный ход здесь — X», «конь обычно идёт на c3»: X must not be a move the book hardly
    knows while another one carries ten times more of its theory (the book's measure of the main move — the
    same one the opening block gives the model, src/opening_knowledge.py).

A claim about another position is left alone: a condition or a plan («если», «после», «будет»), a denial, a
question, a hedge («похоже на», «не путай с»), a range of codes («C60–C99»), an opening the sentence names that
is not the board's, a position the book does not have. The names of whole openings («это сицилианская защита»)
stay with src/answer_check._opening_identity_issues.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

from src.claim_scope import CONDITIONAL, DENIAL, denied_before

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

# «обычно играют Кf6», «чаще всего отвечают e6», "usually plays d4" — and «главный/основной ход здесь — 4.Ba4».
_USUAL = r"(?:обычно|чаще\s+всего|как\s+правило|традиционно|usually|most\s+often|normally|typically)"
_USUAL_MOVE = re.compile(
    _W + _USUAL + r"\s+(?:[а-яёa-z]+\s+){0,2}?(?:игра\w*|отвеча\w*|ход[яи]т|пойд[её]т|ид[её]т|идут|ставят|выбира\w*|"
    r"следует|делают|plays?|answers?|repl(?:y|ies)|goes|go|chooses?|continues?)\s+"
    # «идёт на c3» names a square, not the pawn move c3 — that is the piece's claim (_USUAL_PIECE)
    r"(?:(?!(?:на|в|to|on)(?![а-яёa-z]))[а-яёa-z]+\s+){0,2}?"
    r"(?:[*_«\"(]+)?(?P<mv>(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8]|O-O-O|O-O))"
    r"(?![A-Za-z0-9])", re.IGNORECASE)
_MAIN_MOVE = re.compile(
    r"(?:главн|основн|книжн)\w*\s+(?:теоретическ\w*\s+)?(?:ход|продолжени|ответ)\w*\s+(?:(?:здесь|тут|сейчас|теперь|"
    r"за\s+бел\w+|за\s+ч[её]рн\w+|бел\w+|ч[её]рн\w+|в\s+этой\s+позиции|по\s+теории)\s+){0,2}"
    r"(?:[—–:-]|это)\s*(?:это\s+)?(?:[*_«\"(]+)?"
    r"(?P<mv>(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8]|O-O-O|O-O))"
    r"(?![A-Za-z0-9])"
    r"|(?<![a-z])the\s+main\s+(?:move|line|continuation)\s+(?:here\s+)?is\s+(?:[*_\"(]+)?"
    r"(?P<mv2>(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8]|O-O-O|O-O))"
    r"(?![A-Za-z0-9])", re.IGNORECASE)
# «белый конь обычно идёт на c3» — the move told by its piece and square.
_PIECES = {"конь": chess.KNIGHT, "слон": chess.BISHOP, "ладья": chess.ROOK, "ферзь": chess.QUEEN, "король": chess.KING,
           "пешка": chess.PAWN, "knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK,
           "queen": chess.QUEEN, "king": chess.KING, "pawn": chess.PAWN}
_USUAL_PIECE = re.compile(
    _W + r"(?:(?P<color>бел\w+|ч[её]рн\w+|white|black)\s+)?(?P<piece>конь|слон|ладья|ферзь|король|пешка|knight|bishop|"
    r"rook|queen|king|pawn)\s+(?:[а-яёa-z]+\s+)?" + _USUAL + r"\s+(?:ид[её]т|вста[её]т|выходит|прыгает|отходит|уходит|"
    r"становится|развивается|goes|jumps|comes|retreats|develops)\s+(?:на|to)\s+(?P<sq>[a-h][1-8])(?![0-9])",
    re.IGNORECASE)
_NEXT = re.compile(_W + r"(?:дальше|далее|следующ\w*|в\s+ответ|ответ\w*|теперь|сейчас|здесь|тут|в\s+этой\s+позиции|"
                   r"next|in\s+reply|now|here|in\s+this\s+position)" + _E, re.IGNORECASE)
_ASKS_MAIN = re.compile(r"(?:главн|основн|теоретическ|книжн|обычн|чаще)\w*\s+(?:\w+\s+)?(?:ход|продолжени|игра|отвеча)"
                        r"|main\s+(?:move|line)|usual\s+move|what\s+do\s+(?:they|players|people)\s+(?:usually\s+)?play",
                        re.IGNORECASE)
# How much more of the book a move must carry than the one called usual, and the least it must carry, before
# «usually X» is wrong: 3.Nf3 92 lines to 3.Nc3's 0 is a verdict, 2.Bb5 235 to 2.Bc4 186 is not.
_MAIN_RATIO = 10
_MAIN_MIN_LINES = 20

# A hedge before a name: it is compared, not claimed («не путай с атакой Панова», «похоже на вариант…»).
_HEDGE = re.compile(_W + r"(?:не|нет|похож\w*|напомина\w*|отлич\w*|в\s+отличие|вместо|как\s+в|путай|переход\w*|"
                    r"перейд\w*|ведет|ведут|приведет|станет|может|могут|бывает|unlike|like|not|instead|leads?|"
                    r"transpos\w*|could|would)" + _E, re.IGNORECASE)
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

def _eco_issues(text: str, ctx) -> list[str]:
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
    out = []
    for m, code in codes:
        if code in allowed or m.start() in ranged:
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


def _name_issues(text: str, ctx) -> list[str]:
    from src.answer_check import _ASKS_BOARD_NAME, _IDENTITY, _ON_THE_BOARD, _to_san

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
        before = [mv for mv in moves if mv[1] <= start]
        after = [mv for mv in moves if mv[0] >= end]
        attached = None
        if before:
            last = before[-1]
            gap = converted[last[1]:start]
            if len(gap) <= 90 and not re.search(r"[.!?;]", gap):
                attached = last
        if attached is None and after and re.fullmatch(r"[\s*_—–:(-]*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?",
                                                       converted[end:after[0][0]]):
            attached = after[0]  # «вариант Алапина — 2.c3»
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
            truth = _describe(position)
            out.append(f"after {san} the position is the {truth[1]} ({truth[0]}) by the ECO book: no book line "
                       f"through it is named after {word}" if truth else
                       f"no book line through the position after {san} is named after {word}")
            continue
        if ctx.scene_trail or re.search(r"(?<![0-9])1\s?\.\s?(?:[KQRBN]?[a-h]?x?[a-h][1-8]|O-O)", converted):
            continue  # a line of moves: the name may be about any position of it («…возникает после 2.Кf3 и 3.d4»)
        # Said of the board: «Это вариант…», «Перед нами…», or the name opening the sentence; and about the board
        # in front of the student — a game, a question for its name, «здесь».
        headline = start <= len(_HEADLINE.match(lowered).group(0)) + 1
        if not (_IDENTITY.search(lowered[:start + 1]) or headline):
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
        ahead_named = [e for e in ahead if _has_word(e[1], word) and (family is None or e[1].startswith(family))]
        # The turn has a position of that variation (the line the student steps through, a tool's line): the
        # name is about it, the board is on the way.
        shown = [b for b in ctx.boards if not _start(b) and _consistent(book.lineage(b)[0], word, family)]
        if ahead_named and not shown:
            from src.openings_book import _split_moves

            first = min(ahead_named, key=lambda e: len(_split_moves(e[2])))
            out.append(f"the board has not reached the {first[1]} yet — it begins {first[2]}; the position on the "
                       f"board is the {truth[1]} ({truth[0]}) by the ECO book")
        elif not plain and not line_named and not ahead_named:
            # (a named line said of the board but on another branch is the identity check's: one issue, not two)
            out.append(f"the position on the board is the {truth[1]} ({truth[0]}) by the ECO book: no book line "
                       f"through it is named after {word}")
    return out


# ── «Usually X», «the main move is X» ────────────────────────────────────────

def _main_move_verdict(board: chess.Board, move: chess.Move) -> Optional[str]:
    """Why *move* is not the usual move of *board* by the book, or None (it may be, or the book cannot tell)."""
    conts = _book().continuations(board)
    if not conts:
        return None
    san = board.san(move)
    top = conts[0]
    if top["san"] == san:
        return None
    lines = next((c["lines"] for c in conts if c["san"] == san), 0)
    if top["lines"] < _MAIN_MIN_LINES or lines * _MAIN_RATIO > top["lines"]:
        return None
    num = f"{board.fullmove_number}." if board.turn == chess.WHITE else f"{board.fullmove_number}..."
    others = ", ".join(f"{num}{c['san']} ({c['lines']})" for c in conts[1:3] if c["san"] != san)
    return (f"{num}{san} is not the usual move here: the ECO book's main move is {num}{top['san']} "
            f"({top['lines']} book lines follow it{', then ' + others if others else ''}), {num}{san} has "
            f"{lines or 'no'} book line{'' if lines == 1 else 's'}")


def _candidates(ctx, color: Optional[bool]) -> list:
    """The positions a «usually» may be about, nearest first: the scene the answer's moves set, the board, the
    positions the student's idea leads to — never the bare start standing in for an unknown position."""
    out = []
    if ctx.scene is not None and ctx.scene_age <= 1:
        out.append(ctx.scene)
    now = _board_now(ctx)
    if now is not None:
        out.append(now)
    out += [b for b in ctx.boards if ctx.is_given(b)]
    seen, uniq = set(), []
    for b in out:
        key = b.fen()
        if key in seen or (_start(b) and not (now is not None and _start(now))):
            continue
        seen.add(key)
        if color is None or b.turn == color:
            uniq.append(b)
    return uniq


def _usual_issues(text: str, ctx) -> list[str]:
    from src.answer_check import _to_san

    converted, _ = _to_san(text)
    lowered = converted.lower()
    if lowered.rstrip().endswith("?"):
        return []
    # «Обычно» of the next move, not of a plan in general («конь обычно развивается на f3, слон на c4»): the
    # sentence says it is about the next move («дальше», «в ответ», «здесь»), the student asked for the main move,
    # or the move carries its number.
    next_move = bool(_NEXT.search(lowered)) or bool(_ASKS_MAIN.search(ctx.question_raw or ctx.question or ""))
    claims = []  # (start, color, parse, number) — parse(board) gives the move or None
    for rx in (_USUAL_MOVE, _MAIN_MOVE):
        for m in rx.finditer(converted):
            raw = m["mv"] if "mv" in m.groupdict() and m["mv"] else m.groupdict().get("mv2")
            if not raw:
                continue
            if DENIAL.search(m.group(0)[:-len(raw)]):
                continue  # «обычно играют не Кc3, а Кf3»
            num = re.match(r"\d{1,3}\s?(\.\.\.|…|\.)", raw)
            if rx is _USUAL_MOVE and not (num or next_move):
                continue
            color = None if not num else (chess.WHITE if num.group(1) == "." else chess.BLACK)
            san = re.sub(r"^\d{1,3}\s?(?:\.\.\.|…|\.)\s?", "", raw)

            def parse(board, san=san):
                try:
                    return board.parse_san(san)
                except ValueError:
                    return None

            claims.append((m.start(), color, parse, int(re.match(r"\d+", raw).group(0)) if num else None))
    for m in _USUAL_PIECE.finditer(lowered):
        if not next_move or DENIAL.search(m.group(0)):
            continue
        word = (m["color"] or "").lower()
        color = chess.WHITE if word.startswith(("бел", "white")) else chess.BLACK if word else None
        ptype, sq = _PIECES[m["piece"].lower()], chess.parse_square(m["sq"])

        def parse(board, ptype=ptype, sq=sq):
            found = [mv for mv in board.legal_moves if mv.to_square == sq and board.piece_type_at(mv.from_square) == ptype]
            return found[0] if len(found) == 1 else None

        claims.append((m.start(), color, parse, None))
    if not claims:
        return []
    book = _book()
    out = []
    for start, color, parse, number in claims:
        if denied_before(lowered, start) or re.search(_W + r"(?:если|когда|if|when|unless)" + _E, lowered[:start]):
            continue
        verdicts = []
        for board in _candidates(ctx, color):
            if number is not None and board.fullmove_number != number:
                continue
            move = parse(board)
            if move is None:
                continue
            reached, _ = book.lineage(board)
            if not reached:
                verdicts = []
                break  # a position out of the book: no verdict at all
            # an opening named that is not this board's: «в сицилианской обычно играют Кf3» on a French board
            named = {n.split(":")[0].strip() for n, _ in _named_in(converted)}
            if named and not named & _families(reached):
                verdicts = []
                break
            verdicts.append(_main_move_verdict(board, move))
        if verdicts and all(verdicts):
            out.append(verdicts[0])
    return out


def opening_book_issues(text: str, ctx) -> list[str]:
    """The opening facts of *text* (one sentence) the ECO book denies; [] when it denies none or cannot tell."""
    if ctx is None:
        return []
    try:
        return _eco_issues(text, ctx) + _name_issues(text, ctx) + _usual_issues(text, ctx)
    except Exception:  # noqa: BLE001 — a broken lookup never stops an answer
        import logging

        logging.getLogger(__name__).debug("opening book check failed", exc_info=True)
        return []
