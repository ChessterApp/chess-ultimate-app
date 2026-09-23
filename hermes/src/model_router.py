"""Model router — selects model tier based on query complexity.

Extends config.yaml model_tiers with keyword-based heuristic routing:
- Quick questions → fast (Gemini Flash)
- Position analysis → analysis (Claude Sonnet)
- Deep strategy/game review → deep (Claude Opus)
"""

import re


# Keywords that indicate higher complexity tiers. Each set covers EN, RU and KK:
# the audience is Russian/Kazakh-speaking, and with English-only patterns every
# non-English question silently fell through to the fast tier. Python's ``\b``
# and ``\w`` are Unicode-aware, so word boundaries work for Cyrillic too.
_DEEP_KEYWORDS = re.compile(
    r"\b(deep\s+analysis|game\s+review|strategic\s+plan|preparation|repertoire\s+review"
    r"|long[- ]term|middlegame\s+plan|pawn\s+structure\s+analysis|positional\s+understanding"
    r"|comprehensive"
    # Russian
    r"|глубок\w*\s+анализ|разбор\w*\s+(?:моей\s+|этой\s+|всей\s+)?парти\w*"
    r"|разбери\w*\s+(?:мою\s+|эту\s+|всю\s+)?парти\w*|стратегическ\w*\s+план\w*"
    r"|план\s+на\s+(?:парти\w*|миттельшпил\w*)|долгосрочн\w*|подробн\w*\s+разбор\w*"
    r"|полн\w*\s+разбор\w*|анализ\w*\s+пешечн\w*\s+структур\w*|позиционн\w*\s+понимани\w*"
    r"|разбор\w*\s+(?:моего\s+)?репертуар\w*|подготовк\w*\s+к\s+(?:турнир\w*|соперник\w*|противник\w*)"
    # Kazakh
    r"|терең\s+талдау|ойын\w*\s+талда\w*|стратегиялық\s+жоспар\w*|ұзақ\s*мерзімді"
    r")\b",
    re.IGNORECASE,
)

_BOARD_KEYWORDS = re.compile(
    r"(?:"
    r"show\s+(?:on\s+)?(?:the\s+)?board|show\s+me|set\s+up|demonstrate|display"
    r"|put\s+on\s+the\s+board"
    r"|покажи|доск[аеуи]|позици[яюи]|поставь|продемонстрируй|на\s+доске|установи"
    r")",
    re.IGNORECASE,
)

_ANALYSIS_KEYWORDS = re.compile(
    r"\b(analy[sz]e|evaluat\w*|critical|tactic\w*|calculat\w*|variation|candidate\s+move"
    r"|sacrifice|combin\w*|attack|defend|endgame\s+technique|compare|assess"
    # Russian. "защища" (the verb) rather than "защит": opening names such as
    # «сицилианская защита» must not promote a definition question.
    r"|анализ|проанализ|оцени|оценк|критич|тактик|посчита|рассчита|расч[её]т|вариант"
    r"|ход\w*[- ]кандидат|кандидат\w*\s+ход|жертв|комбинац|атак|защища|техник\w*\s+эндшпил"
    r"|сравни|сравнен"
    # Kazakh
    r"|талда|бағала|тактика|есепте|құрбан|комбинация|шабуыл|қорған|салыстыр"
    r")",
    re.IGNORECASE,
)


# A pasted game: at least six numbered moves ("1. e4 e5 2. Nf3 …" or "1.e4 e5 2.Nf3").
# This is the one deterministic signal that a turn is a game review — it goes to the
# deep tier regardless of how the question is phrased (decision 2026-09-23).
_PGN_RE = re.compile(r"(?:\b\d{1,3}\.\s*[a-hNBRQKO][^\s]*\s+(?:[a-hNBRQKO][^\s]*|\d)[^\n]*?){6,}")


def looks_like_pgn(query: str) -> bool:
    return bool(query) and _PGN_RE.search(query) is not None


def explain_route(query: str, model_tiers: dict, default_model: str) -> dict:
    """Resolve the model AND why it was chosen, for logging/telemetry.

    Returns a dict with ``model``, ``tier`` (``deep`` | ``analysis`` | ``fast`` |
    ``default``), ``reason`` (short slug), and ``matched`` (the keyword text that
    triggered the tier, or ``None``). :func:`route_model` is a thin wrapper that
    returns only the model, so existing callers are unchanged.
    """
    if not query or not model_tiers:
        return {"model": default_model, "tier": "default", "reason": "no_query_or_tiers", "matched": None}
    if looks_like_pgn(query):
        return {"model": model_tiers.get("deep", default_model), "tier": "deep",
                "reason": "pgn_in_message", "matched": "pgn"}

    m = _DEEP_KEYWORDS.search(query)
    if m:
        return {"model": model_tiers.get("deep", default_model), "tier": "deep",
                "reason": "deep_keyword", "matched": m.group(0)}

    m = _BOARD_KEYWORDS.search(query)
    if m:
        return {"model": model_tiers.get("analysis", default_model), "tier": "analysis",
                "reason": "board_keyword", "matched": m.group(0)}

    m = _ANALYSIS_KEYWORDS.search(query)
    if m:
        return {"model": model_tiers.get("analysis", default_model), "tier": "analysis",
                "reason": "analysis_keyword", "matched": m.group(0)}

    return {"model": model_tiers.get("fast", default_model), "tier": "fast",
            "reason": "default_fast", "matched": None}


def route_model(query: str, model_tiers: dict, default_model: str) -> str:
    """Select the appropriate model based on query complexity.

    Args:
        query: The user's message text.
        model_tiers: Dict mapping tier names to model IDs
                     (e.g. {"fast": "...", "analysis": "...", "deep": "..."}).
        default_model: Fallback model if no tier matches.

    Returns:
        Model ID string.
    """
    return explain_route(query, model_tiers, default_model)["model"]
