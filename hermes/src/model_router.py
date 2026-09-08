"""Model router — selects model tier based on query complexity.

Extends config.yaml model_tiers with keyword-based heuristic routing:
- Quick questions → fast (Gemini Flash)
- Position analysis → analysis (Claude Sonnet)
- Deep strategy/game review → deep (Claude Opus)
"""

import re


# Keywords that indicate higher complexity tiers
_DEEP_KEYWORDS = re.compile(
    r"\b(deep\s+analysis|game\s+review|strategic\s+plan|preparation|repertoire\s+review"
    r"|long[- ]term|middlegame\s+plan|pawn\s+structure\s+analysis|positional\s+understanding"
    r"|comprehensive)\b",
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
    r"|sacrifice|combin\w*|attack|defend|endgame\s+technique|compare|assess)",
    re.IGNORECASE,
)


def explain_route(query: str, model_tiers: dict, default_model: str) -> dict:
    """Resolve the model AND why it was chosen, for logging/telemetry.

    Returns a dict with ``model``, ``tier`` (``deep`` | ``analysis`` | ``fast`` |
    ``default``), ``reason`` (short slug), and ``matched`` (the keyword text that
    triggered the tier, or ``None``). :func:`route_model` is a thin wrapper that
    returns only the model, so existing callers are unchanged.
    """
    if not query or not model_tiers:
        return {"model": default_model, "tier": "default", "reason": "no_query_or_tiers", "matched": None}

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
