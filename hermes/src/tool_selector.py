"""Dependency-free semantic tool subsetting for coach turns.

The coach ships every chess-tool schema on every turn, which is a large, mostly
irrelevant token payload. This selects a small, query-relevant subset via a
lightweight keyword/intent overlap score (no embedding model) while always
keeping a ``core`` set so coaching quality cannot collapse.

Kept intentionally simple and deterministic. Enabled only behind the
``COACH_TOOL_SUBSET`` flag; when off the coach sends the full toolset unchanged.
"""

import re

# Tools the coach needs on essentially every turn: board setup, engine analysis,
# and engine-free move-legality checks. Never dropped in the default
# (``full``) mode.
CORE_TOOLS = frozenset({"board_control", "analyze_position", "check_moves"})

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

# Query-language bridge for tools whose schemas are written in English. Each
# entry lists lowercase RU / KK word stems; a query token matches a stem when it
# *starts with* it, so one stem covers the whole inflection paradigm
# ("парти" -> партия / партии / партию / партий). Only non-core tools need
# entries (core tools are always sent), but the map is harmless for any tool.
# Keep stems specific: a stem shared by many tools carries no ranking signal.
TOOL_KEYWORDS = {
    "search_master_games": (
        "мастер", "гроссмейстер", "база", "партии мастеров", "турнир", "найди парти",
        "поищи парти", "сыгран", "шедевр", "классическ", "ойындар", "шебер",
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
        "соперник", "противник", "подготов", "оппонент", "против", "готовиться",
        "қарсылас", "дайынд",
    ),
    "lichess_game_import": ("lichess", "личес", "импорт", "загрузи", "скачай", "подтяни"),
    "chesscom_game_import": ("chess.com", "чесском", "chesscom", "импорт", "загрузи", "скачай"),
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
        "что изучать", "рекоменд", "совет", "жаттығу", "кеңес",
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
    "get_puzzle": (
        "задач", "головолом", "реши", "порешать", "потренир", "упражн", "тактик", "мат в",
        "есеп", "жаттығу", "тапсырма",
    ),
    "search_web": ("интернет", "новост", "найди в", "погугли", "сайт", "статья", "видео", "жаңалық"),
    "analyze_position": ("анализ", "проанализ", "оцен", "движ", "stockfish", "стокфиш", "талда"),
    "board_control": ("доск", "покажи", "поставь", "стрелк", "подсвет", "тақта", "көрсет"),
    "check_moves": ("легал", "можно ли", "разрешён", "разрешен", "правил", "заңды"),
}

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _tokenize(text: str) -> set:
    """Lowercase word tokens of *text* (letters/digits in any script) as a set."""
    return set(_TOKEN_RE.findall((text or "").lower()))


def _stem_hits(query: str, query_tokens: set, stems: tuple) -> int:
    """Count keyword stems matched by the query.

    Single-word stems match any query token by prefix; multi-word stems are
    matched as substrings of the whole lowercased query.
    """
    text = (query or "").lower()
    hits = 0
    for stem in stems:
        if " " in stem or "." in stem:
            if stem in text:
                hits += 1
        elif any(tok.startswith(stem) for tok in query_tokens):
            hits += 1
    return hits


def _score(query_tokens: set, declaration: dict, query: str = "") -> int:
    """Overlap between the query and a tool's name, description, and keyword stems."""
    haystack = _tokenize(declaration.get("name", "")) | _tokenize(
        declaration.get("description", "")
    )
    stems = TOOL_KEYWORDS.get(declaration.get("name", ""), ())
    return len(query_tokens & haystack) + _stem_hits(query, query_tokens, stems)


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

    query_tokens = _tokenize(query) - _STOPWORDS

    core_decls = [d for d in declarations if d.get("name") in core]
    others = [d for d in declarations if d.get("name") not in core]

    # Stable sort keeps original relative order for equal scores -> deterministic.
    ranked = sorted(
        others, key=lambda d: _score(query_tokens, d, query), reverse=True
    )

    return core_decls + ranked[: max(topk, 0)]


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
    *query*. The result length is at most ``topk + len(core)``. Ordering is
    deterministic: core tools first (original order), then ranked others.

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
