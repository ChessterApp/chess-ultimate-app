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

_ANALYSIS_KEYWORDS = re.compile(
    r"\b(analy[sz]e|evaluat\w*|critical|tactic\w*|calculat\w*|variation|candidate\s+move"
    r"|sacrifice|combin\w*|attack|defend|endgame\s+technique|compare|assess)",
    re.IGNORECASE,
)


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
    if not query or not model_tiers:
        return default_model

    if _DEEP_KEYWORDS.search(query):
        return model_tiers.get("deep", default_model)

    if _ANALYSIS_KEYWORDS.search(query):
        return model_tiers.get("analysis", default_model)

    return model_tiers.get("fast", default_model)
