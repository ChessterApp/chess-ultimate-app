"""Dependency-free semantic tool subsetting for coach turns.

The coach ships every chess-tool schema on every turn, which is a large, mostly
irrelevant token payload. This selects a small, query-relevant subset via a
lightweight keyword/intent overlap score (no embedding model) while always
keeping a ``core`` set so coaching quality cannot collapse.

Kept intentionally simple and deterministic. Enabled only behind the
``COACH_TOOL_SUBSET`` flag; when off the coach sends the full toolset unchanged.

Three mechanisms on top of the keyword score (live site, 03.11: «Найди в базе партию Синдаров —
Накамура и загрузи её на доску» got neither search_master_games nor get_game_pgn — the coach
searched the web seven times and said the game did not exist):
  * a keyword matches its word in any case form — «база» finds «базе / базы / базу», «ошибк»
    finds «ошибок» (``_word_matches``: the word's root, the fleeting vowel), and a phrase matches
    word by word («партии мастеров» → «партию мастеров»);
  * a request for a particular game («партию X — Y», «последнюю партию Карлсена», "game X vs Y",
    a tournament and a year, «загрузи партию из базы») brings the games-database search
    (``asks_for_game``, ``INTENT_TOOLS``);
  * a tool chosen for the query brings the tools it needs to finish the job — the one its
    description says to use next («Use get_game_pgn with a returned id»), or the table
    ``COMPANION_TOOLS`` — so a found game can be loaded (``companions``).
These add at most ``MAX_EXTRA_TOOLS`` tools after the ranked ones; core tools are never pushed out.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Tools the coach needs on essentially every turn: board setup, engine analysis,
# engine-free move-legality checks, and the teaching tools the prompt makes
# mandatory — "call get_topic before explaining a concept", "puzzles only from
# get_puzzle", "recommend real lessons". Keyword selection missed them on plain
# questions: for "how do I improve my endgame?" the coach got neither, wrote the
# get_topic call out as text and told the student its tools were missing (bench
# 2026-09-28). Never dropped in the default (``full``) mode.
CORE_TOOLS = frozenset({
    "board_control", "analyze_position", "check_moves",
    "get_topic", "get_puzzle", "get_learning_path", "get_lesson",
    # A game asked for in any words, a move typed in a game («е4» carries no keyword): 2026-10-12.
    "start_game", "make_game_move",
    # Resign / take back / draw / new game in words (2026-10-13).
    "game_action",
})

# Board-render / FEN-parse tools that are redundant when the board is already
# rendered on the student's screen. Suppressed only in ``panel`` mode.
PANEL_SUPPRESSED_TOOLS = frozenset({"board_control"})

# High-frequency words that carry no tool-selection signal (EN / RU / KK).
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "of", "to", "in", "for", "on", "my", "me",
        "i", "what", "whats", "how", "do", "does", "did", "can", "could", "should",
        "would", "this", "that", "with", "and", "or", "get", "show", "please",
        "you", "your", "it", "at", "be", "was", "were", "here", "there", "about",
        "best", "good", "vs", "against", "play", "playing", "move", "moves",
        # Russian
        "и", "в", "во", "на", "не", "что", "как", "я", "мне", "мой", "моя", "мои",
        "моё", "у", "с", "со", "по", "за", "к", "ко", "это", "этот", "эта", "эти",
        "ты", "вы", "он", "она", "они", "мы", "а", "но", "или", "ли", "же", "бы",
        "для", "от", "до", "из", "о", "об", "про", "есть", "был", "была", "было",
        "быть", "можно", "нужно", "надо", "хочу", "давай", "пожалуйста", "скажи",
        "какой", "какая", "какие", "какое", "где", "когда", "почему", "зачем",
        "лучше", "лучший", "хорошо", "плохо", "ход", "ходы", "ходить",
        # Kazakh
        "және", "мен", "менің", "сен", "сіз", "ол", "бұл", "осы", "не", "қалай",
        "үшін", "туралы", "бар", "жоқ", "керек", "болады", "маған", "қандай",
        "қайда", "қашан", "неге", "жүріс", "жүрістер",
    }
)

_STOPWORDS_NORM = frozenset(w.replace("ё", "е") for w in _STOPWORDS)

# Query-language bridge for tools whose schemas are written in English. Each
# entry lists lowercase RU / KK word stems; a query token matches a stem when it
# *starts with* it, so one stem covers the whole inflection paradigm
# ("парти" -> партия / партии / партию / партий). Only non-core tools need
# entries (core tools are always sent), but the map is harmless for any tool.
# Keep stems specific: a stem shared by many tools carries no ranking signal.
TOOL_KEYWORDS = {
    "search_master_games": (
        "мастер", "гроссмейстер", "база", "партии мастеров", "турнир", "найди парти",
        "поищи парти", "сыгран", "шедевр", "классическ", "ойындар", "шебер", "базасы", "базадан",
    ),
    "get_game_pgn": ("pgn", "полн", "текст парти", "запись парти", "толық"),
    "get_opening_stats": (
        "дебют", "статистик", "eco", "сицилиан", "испанск", "итальянск", "французск",
        "каро", "славянск", "ферзев", "королевск", "гамбит", "защит", "начало",
        "ашылу",
    ),
    "get_position_stats": (
        "позици", "статистик", "как часто", "процент", "популярн", "играют", "выигрыш",
        "победа", "ничь", "жиілік",
    ),
    "get_player_openings": ("репертуар", "какие дебюты", "чем играет", "мастер", "шебер"),
    "get_player_profile": (
        "профил", "рейтинг", "аккаунт", "ник", "lichess", "личес", "chess.com", "чесском",
    ),
    "opponent_prep": (
        "соперник", "противник", "подготов", "оппонент", "против", "готовит", "готовлюс",
        "қарсылас", "дайынд",
    ),
    "lichess_game_import": ("lichess", "личес", "импорт", "загрузи", "скачай", "подтяни"),
    "chesscom_game_import": ("chess.com", "чесском", "chesscom", "импорт", "загрузи", "скачай"),
    "import_game_from_url": (
        "ссылк", "по ссылке", "http", "lichess.org/", "chess.com/game", "chess.com/analysis",
        "link", "url", "сілтеме",
    ),
    "get_user_games": (
        "мои парти", "моих парти", "мою парти", "последн", "недавн", "сыграл", "сохранён",
        "сохранен", "истори", "ойындарым", "соңғы",
    ),
    "get_user_repertoire": ("мой репертуар", "моего репертуар", "репертуар", "мои дебюты", "чем я играю"),
    "get_user_progress": (
        "прогресс", "успех", "статистик", "решён", "решен", "задач", "урок", "курс",
        "пройден", "достижен", "прогрес", "сабақ", "есеп",
    ),
    "get_game_insights": ("разбор", "разобран", "вывод", "итог", "тенденц", "закономерн", "инсайт"),
    "weakness_tracker": (
        "слаб", "ошибк", "зевк", "зевн", "промах", "проблем", "недостат", "типичн",
        "повторя", "әлсіз", "қате",
    ),
    "training_recommender": (
        "тренир", "тренировк", "упражн", "занят", "план", "программ", "что учить",
        "что изучать", "рекоменд", "совет", "жаттығу", "кеңес", "слаб", "подтянуть",
    ),
    "get_learning_path": (
        "курс", "урок", "программ", "следующий урок", "что дальше", "дальше учить",
        "продолж", "пройти", "пройден", "обучен", "учебн", "модул", "оқу", "сабақ", "курстар",
        "course", "lesson", "curriculum", "syllabus",
    ),
    "get_lesson": (
        "урок", "объясни урок", "открой урок", "разбери урок", "тема урока", "из урока",
        "упражнение урока", "сабақ", "сабақты", "lesson", "explain the lesson",
    ),
    "get_topic": (
        "объясни", "расскажи", "что такое", "как играть", "тем", "принцип", "идея",
        "вилк", "связк", "сквозн", "изолир", "изолятор", "висяч", "сдвоен", "отстал", "проходн",
        "цеп", "меньшинств", "форпост", "два слона", "плох", "профилакт", "пространств",
        "оппозиц", "лусен", "филидор", "цугцванг", "прорыв", "ёж", "мароци", "карлсбад",
        "спёрт", "сперт", "отвлеч", "завлеч", "промежуточ", "разносторон", "греческ",
        "түсіндір", "деген не", "explain", "what is", "how to play", "concept", "structure",
    ),
    "list_topics": (
        "что изуч", "какие тем", "список тем", "чему учить", "разделы", "база знаний",
        "что ещё", "что еще", "topics", "what can i learn", "curriculum of ideas",
    ),
    "find_critical_moments": (
        "критич", "переломн", "ключев", "решающ", "где ошиб", "поворотн", "момент",
        "шешуші", "сәт",
    ),
    "compare_variations": ("сравн", "вариант", "лини", "альтернатив", "разниц", "салыстыр"),
    "score_position_themes": (
        "оцен", "материал", "простран", "активн", "безопасн", "корол", "мобильн",
        "план", "стратег", "тем", "бағала", "қауіпсіз",
    ),
    "find_games_by_position": (
        "в этой позиции", "эту позицию", "такую позицию", "кто играл", "встречал", "встречает", "встречаю",
        "партии с этой", "как играли мастера", "как играют", "осы позиция",
    ),
    "identify_opening": ("какой это дебют", "что за дебют", "как называется", "название дебюта", "бұл қандай"),
    "get_puzzle": (
        "задач", "головолом", "реши", "порешать", "потренир", "упражн", "тактик", "мат в",
        "есеп", "жаттығу", "тапсырма",
    ),
    # «найди в» was a stem here: «Найди в базе партию …» went to the web search (live site, 03.11).
    # «статья» by its forms: its root «стат» is also «стать» (to become).
    "search_web": (
        "интернет", "новост", "найди в сети", "поищи в сети", "в гугле", "погугли", "сайт",
        "статья", "статьи", "статью", "статей", "статье", "видео", "жаңалық",
    ),
    "analyze_position": ("анализ", "проанализ", "оцен", "движ", "stockfish", "стокфиш", "талда"),
    "board_control": ("доск", "покажи", "поставь", "стрелк", "подсвет", "тақта", "көрсет"),
    "check_moves": ("легал", "можно ли", "разрешён", "разрешен", "правил", "заңды"),
}

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_CYRILLIC = re.compile(r"[а-яёәғқңөұүһі]")


def _tokenize(text: str) -> set:
    """Lowercase word tokens of *text* (letters/digits in any script) as a set."""
    return set(_TOKEN_RE.findall((text or "").lower().replace("ё", "е")))


def _token_list(text: str) -> list:
    """The word tokens of *text* in order (for phrases)."""
    return _TOKEN_RE.findall((text or "").lower().replace("ё", "е"))


# Russian inflection endings, longest first: one is dropped to get a word's root («базе» → «баз»,
# «загрузить» → «загруз», «ошибками» → «ошибк»). A light stemmer, not a dictionary: it only has to
# make a keyword and its case forms meet.
_ENDINGS = tuple(sorted({
    "иями", "ями", "ами", "ией", "ием", "иях", "ого", "его", "ому", "ему", "ыми", "ими", "ешь", "ете",
    "ишь", "ите", "ить", "ать", "ять", "еть", "уть", "ыть", "ая", "яя", "ое", "ее", "ые", "ие", "ый",
    "ий", "ой", "ей", "ую", "юю", "ом", "ем", "ым", "им", "ых", "их", "ах", "ях", "ам", "ям", "ов", "ев",
    "ию", "ия", "ии", "ье", "ья", "ью", "ьи", "ай", "яй", "ют", "ет", "ит", "ут", "ат", "ят",
    "а", "я", "о", "е", "ы", "и", "у", "ю", "ь", "й",
}, key=len, reverse=True))
# A keyword ending so is a whole word form («база», «загрузи», «запись»), not a cut-off prefix.
_WORD_FORM_END = frozenset("аяоеёыиуюьй")
# The fleeting vowel of a genitive plural: «ошибок» / «ошибка», «ссылок» / «ссылка», «зевок» / «зевка».
_FLEETING = re.compile(r"([^аеиоуыэюя])[ое]к$")


def _root(word: str) -> str:
    """*word* without its inflection ending (at least three letters stay) and its fleeting vowel."""
    if not _CYRILLIC.search(word):
        return word
    for end in _ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 3:
            word = word[: -len(end)]
            break
    return _FLEETING.sub(r"\1к", word)


def _word_matches(token: str, stem: str) -> bool:
    """A query word matches a keyword: it starts with it (``парти`` → «партию»), its root does
    (``ошибк`` → «ошибок»), or the keyword is a whole word form and the query word is another form
    of it (``база`` → «базе», ``загрузи`` → «загрузить»). A keyword cut after a consonant is a
    prefix only: ``ферзев`` (ферзевый гамбит) is not «ферзь»."""
    if token.startswith(stem):
        return True
    if not _CYRILLIC.search(stem):
        return False
    root = _root(token)
    if root.startswith(stem):
        return True
    if stem[-1] not in _WORD_FORM_END:
        return False
    if token.endswith(("ть", "ться", "тся")) and stem[-1] not in "ийь":
        return False  # a verb is a form of a verb keyword («загрузи» → «загрузить»), not of a noun («статья» ≠ «стать»)
    stem_root = _root(stem)
    return len(stem_root) >= 3 and root == stem_root


def _phrase_matches(tokens: list, words: list) -> bool:
    """The words of a keyword phrase follow each other in the query, each matching its word."""
    n = len(words)
    for i in range(len(tokens) - n + 1):
        if all(_word_matches(tokens[i + j], words[j]) for j in range(n)):
            return True
    return False


def _stem_hits(query: str, query_tokens: set, stems: tuple, tokens: list = None) -> int:
    """Count keyword stems matched by the query.

    Single-word stems match any query token (``_word_matches``); a phrase matches word by word on
    consecutive tokens; a stem with a dot or a slash (``chess.com``, ``lichess.org/``) as a substring.
    """
    text = (query or "").lower().replace("ё", "е")
    if tokens is None:
        tokens = _token_list(query)
    hits = 0
    for stem in stems:
        stem = stem.replace("ё", "е")
        if "." in stem or "/" in stem:
            if stem in text:
                hits += 1
        elif " " in stem:
            if _phrase_matches(tokens, stem.split()):
                hits += 1
        elif any(_word_matches(tok, stem) for tok in query_tokens):
            hits += 1
    return hits


def _score(query_tokens: set, declaration: dict, query: str = "", tokens: list = None) -> int:
    """Overlap between the query and a tool's name, description, and keyword stems."""
    haystack = _tokenize(declaration.get("name", "")) | _tokenize(
        declaration.get("description", "")
    )
    stems = TOOL_KEYWORDS.get(declaration.get("name", ""), ())
    return len(query_tokens & haystack) + _stem_hits(query, query_tokens, stems, tokens)


# ── A particular game asked for ────────────────────────────────────────────────────────────

# Tools a request for a particular game needs, whatever its words scored.
INTENT_TOOLS = ("search_master_games",)

# A game: «партия» in its forms (also the Kazakh «партиясын»), «игру Карлсена», «ойын», "game", «матч».
_GAME_NOUN = re.compile(
    r"(?<![\w-])(?:парти(?:я|и|ю|ей|й|ям|ями|ях)|партия\w+|игр(?:а|у|ы|е|ой)|ойын\w*|матч\w*|games?|match(?:es)?)"
    r"(?![\w-])", re.IGNORECASE)
# …the student's own, or the one on the board: not the database's.
_OWN_GAME = re.compile(
    r"(?<![\w-])(?:мо(?:я|ю|ей|и|их|им|ими)|сво(?:ю|ей|и|их|ими)|my|mine|менің|өзімнің|"
    r"я\s+(?:сыграл|играл|проиграл|выиграл)\w*|i\s+(?:played|lost|won)|"
    r"(?:эт(?:а|у|ой|ом|и|их)|данн\w+|текущ\w+|нашу|нашей|наша|this|current|our|осы|бұл)\s+(?:[\w-]+\s+)?"
    r"(?:парти\w*|игр\w*|game|ойын\w*))(?![\w-])", re.IGNORECASE)
# …named by a year, the database, an event.
_YEAR = re.compile(r"(?<!\d)(?:1[89]\d\d|20\d\d)(?!\d)")
_DATABASE = re.compile(
    r"(?<![\w-])(?:баз(?:а|е|ы|у|ой|ах|ам)?(?!\s+знани)|database|db|twic|базасы\w*|базадан|дерекқор\w*)(?![\w-])",
    re.IGNORECASE)
_EVENT = re.compile(
    r"(?<![\w-])(?:турнир\w*|супертурнир\w*|чемпионат\w*|олимпиад\w*|претендент\w*|мемориал\w*|кубк\w*|кубок|"
    r"гран-при|жарыс\w*|tournament\w*|championship\w*|candidates|olympiad|memorial|wijk|tata\s+steel|"
    r"norway\s+chess|sinquefield|grand\s+(?:chess\s+tour|prix|swiss))(?![\w-])", re.IGNORECASE)
# «найди / загрузи / открой партию …» — fetching a game, not discussing one.
_FETCH = re.compile(
    r"(?<![\w-])(?:найд\w*|найти|поищ\w*|ищ[иу]\w*|отыщ\w*|загруз\w*|подгруз\w*|открой\w*|открыть|"
    r"find|search|look\s+up|load|pull\s+up|fetch|open|тап\w*|ізде\w*|жүкте\w*|аш)(?![\w-])", re.IGNORECASE)
# A score typed into the message is the student's own game, whatever the words.
_MOVE_LIST = re.compile(r"(?<![\w.])1\.\s*(?:[a-hKQRBNOКФЛС]|e4|d4)", re.IGNORECASE)


def asks_for_game(query: str) -> bool:
    """The message asks for a particular game from the master database.

    A game («партия», "game", «ойын», «матч») that is not the student's own or the one on the board,
    named by a player, a year, an event or the database, or fetched («найди / загрузи / открой
    партию»); or two players named against each other («Синдаров — Накамура»), or a player and the
    database («что есть в базе по Карлсену»)."""
    from src.player_names import mentions_player, names_two_players

    text = query or ""
    if names_two_players(text):
        return True
    own = bool(_OWN_GAME.search(text)) or bool(_MOVE_LIST.search(text))
    game = bool(_GAME_NOUN.search(text))
    if game and not own:
        if _YEAR.search(text) or _DATABASE.search(text) or _EVENT.search(text) or _FETCH.search(text):
            return True
        if mentions_player(text):
            return True
    if not own and _DATABASE.search(text) and mentions_player(text):
        return True
    return False


# ── Companions: what a chosen tool needs to finish the job ──────────────────────────────────

# When a tool's description does not say it: the tool → the tools its result is used with.
COMPANION_TOOLS = {
    "search_master_games": ("get_game_pgn",),
    "find_games_by_position": ("get_game_pgn",),
}
# «Use get_game_pgn with a returned id», «Then call board_control …», «use find_critical_moments to …».
_FOLLOW_UP = re.compile(r"\b(?:then\s+)?(?:use|call)\s+([a-z][a-z0-9_]+)", re.IGNORECASE)
# At most this many tools beyond core + topk: the intent's and the companions.
MAX_EXTRA_TOOLS = 4


def companions(declaration: dict, names: set) -> list:
    """The tools *declaration*'s own description says to use next, plus ``COMPANION_TOOLS`` — those
    among *names* (the tools on offer)."""
    name = declaration.get("name", "")
    found = [m.group(1) for m in _FOLLOW_UP.finditer(declaration.get("description", "") or "")]
    found += list(COMPANION_TOOLS.get(name, ()))
    return [n for n in dict.fromkeys(found) if n in names and n != name]


def _select_flat(
    declarations: list,
    query: str,
    topk: int,
    mode: str,
    core: frozenset,
    panel_suppressed: frozenset,
) -> list:
    """Core scoring/selection over flat dicts (each has ``name``/``description``).

    Shared by :func:`select_tool_subset` (flat declarations) and
    :func:`select_openai_tool_subset` (flat proxies). Keeps the tokenizer,
    scorer, core-first ordering, and ``panel`` suppression logic in one place.
    """
    if mode == "panel":
        declarations = [
            d for d in declarations if d.get("name") not in panel_suppressed
        ]
        core = core - panel_suppressed

    query_tokens = _tokenize(query) - _STOPWORDS_NORM
    tokens = _token_list(query)

    core_decls = [d for d in declarations if d.get("name") in core]
    others = [d for d in declarations if d.get("name") not in core]

    # Stable sort keeps original relative order for equal scores -> deterministic.
    scores = {id(d): _score(query_tokens, d, query, tokens) for d in others}
    ranked = sorted(others, key=lambda d: scores[id(d)], reverse=True)
    chosen = ranked[: max(topk, 0)]

    # The intent's tools, then the companions of the tools that carry the turn: after the ranked
    # ones, at most MAX_EXTRA_TOOLS, so core and ranked tools are never pushed out.
    by_name = {d.get("name"): d for d in others}
    taken = {d.get("name") for d in core_decls} | {d.get("name") for d in chosen}
    extra: list = []
    intent = [n for n in INTENT_TOOLS if n in by_name] if asks_for_game(query) else []
    for name in intent:
        if name not in taken and len(extra) < MAX_EXTRA_TOOLS:
            extra.append(by_name[name])
            taken.add(name)
    added_companions: list = []
    # Companions come with the tools that carry the turn: the intent's, and the best-scored tool
    # when the query clearly asked for it (two signals or more). A tool that only touched one word
    # of the query («в этой позиции», «lichess») brings none — an ordinary question keeps its set.
    leaders = [by_name[n] for n in intent]
    if chosen and scores[id(chosen[0])] >= 2:
        leaders.append(chosen[0])
    for d in leaders:
        for name in companions(d, set(by_name)):
            if name not in taken and len(extra) < MAX_EXTRA_TOOLS:
                extra.append(by_name[name])
                added_companions.append(name)
                taken.add(name)

    selected = core_decls + chosen + extra
    logger.info(
        "tool subset: %d sent %s; intent=%s companions=%s",
        len(selected), [d.get("name") for d in selected], intent, added_companions,
    )
    return selected


def select_tool_subset(
    declarations: list,
    query: str,
    topk: int = 7,
    mode: str = "full",
    core: frozenset = CORE_TOOLS,
    panel_suppressed: frozenset = PANEL_SUPPRESSED_TOOLS,
) -> list:
    """Return a query-relevant subset of *declarations*.

    Always includes the ``core`` tools (minus any suppressed in ``panel`` mode),
    then the ``topk`` highest-scoring remaining tools by keyword overlap with
    *query*, then the tools a request for a particular game needs and the companions
    of the tools chosen for the query (at most ``MAX_EXTRA_TOOLS``). The result length
    is at most ``topk + len(core) + MAX_EXTRA_TOOLS``. Ordering is deterministic: core
    tools first (original order), then ranked others, then the added ones.

    In ``panel`` mode the board is already on screen, so board-render/FEN-parse
    tools in ``panel_suppressed`` are removed from the candidate pool and not
    force-included. Any other ``mode`` value behaves as ``full``.
    """
    return _select_flat(declarations, query, topk, mode, core, panel_suppressed)


def select_openai_tool_subset(
    tools: list,
    query: str,
    topk: int = 7,
    mode: str = "full",
    core: frozenset = CORE_TOOLS,
    panel_suppressed: frozenset = PANEL_SUPPRESSED_TOOLS,
) -> list:
    """Subset OpenAI-format tool dicts by query relevance.

    ``tools`` are OpenAI-shaped:
    ``{"type": "function", "function": {"name", "description", "parameters"}}``.
    The scorer needs flat ``name``/``description`` keys, so we build lightweight
    proxies carrying an ``_orig`` back-reference, run the SAME selection as
    :func:`select_tool_subset`, then map results back to the ORIGINAL dicts.
    Object identity and full ``parameters`` are preserved.
    """
    proxies = [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "_orig": t,
        }
        for t in tools
    ]
    selected = _select_flat(proxies, query, topk, mode, core, panel_suppressed)
    return [p["_orig"] for p in selected]
