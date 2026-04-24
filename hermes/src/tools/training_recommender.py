"""Tool: training_recommender — Suggest training based on detected weaknesses."""

import json
import logging
import os

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TIMEOUT = 10

TRAINING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "training_recommender",
        "description": (
            "Suggest personalized training recommendations based on the user's "
            "detected weaknesses. Returns puzzle themes, courses, and practice activities."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID.",
                },
            },
            "required": ["user_id"],
        },
    },
}

# Mapping from weakness categories to training recommendations
WEAKNESS_TO_TRAINING = {
    "opening_theory": [
        {
            "type": "course",
            "title": "Opening Principles",
            "description": "Review fundamental opening principles: center control, development, king safety.",
            "priority": "high",
        },
        {
            "type": "practice",
            "title": "Opening Explorer",
            "description": "Use the opening explorer to study your most-played lines deeper.",
            "priority": "medium",
        },
    ],
    "tactics": [
        {
            "type": "puzzle",
            "title": "Tactical Patterns",
            "description": "Solve puzzles focusing on forks, pins, skewers, and discovered attacks.",
            "priority": "high",
        },
        {
            "type": "puzzle",
            "title": "Mate in 2-3",
            "description": "Practice checkmate patterns to sharpen tactical vision.",
            "priority": "medium",
        },
    ],
    "endgame": [
        {
            "type": "course",
            "title": "Essential Endgames",
            "description": "Study king and pawn endings, rook endings, and basic checkmates.",
            "priority": "high",
        },
        {
            "type": "practice",
            "title": "Endgame Drills",
            "description": "Practice converting winning endgame positions against the engine.",
            "priority": "medium",
        },
    ],
    "time_management": [
        {
            "type": "practice",
            "title": "Rapid Games",
            "description": "Play rapid games to practice decision-making under time pressure.",
            "priority": "medium",
        },
    ],
    "positional_play": [
        {
            "type": "course",
            "title": "Positional Chess",
            "description": "Study pawn structures, piece placement, and strategic planning.",
            "priority": "high",
        },
        {
            "type": "puzzle",
            "title": "Positional Puzzles",
            "description": "Solve puzzles that require finding the best strategic move, not just tactics.",
            "priority": "medium",
        },
    ],
}

# Default recommendations when no weaknesses detected
DEFAULT_RECOMMENDATIONS = [
    {
        "type": "puzzle",
        "title": "Daily Puzzles",
        "description": "Solve daily puzzles to maintain tactical sharpness.",
        "priority": "medium",
        "weakness_addressed": "general",
    },
    {
        "type": "practice",
        "title": "Analyze Your Games",
        "description": "Review your recent games to identify areas for improvement.",
        "priority": "medium",
        "weakness_addressed": "general",
    },
]


def _fetch_user_weaknesses(
    user_id: str,
    supabase_url: str = None,
    supabase_key: str = None,
) -> list[dict]:
    """Fetch user weaknesses from Supabase user_chess_profiles."""
    base = supabase_url or SUPABASE_URL
    api_key = supabase_key or SUPABASE_KEY

    if not base or not api_key:
        return []

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = httpx.get(
            f"{base}/rest/v1/user_chess_profiles",
            params={"user_id": f"eq.{user_id}", "select": "weaknesses"},
            headers=headers,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0].get("weaknesses", []) or []
    except Exception:
        logger.exception("Failed to fetch weaknesses for user %s", user_id)

    return []


def training_recommender(
    user_id: str,
    supabase_url: str = None,
    supabase_key: str = None,
    _weaknesses: list[dict] = None,
) -> dict:
    """Suggest training based on detected weaknesses."""
    # Use provided weaknesses or fetch from Supabase
    weaknesses = _weaknesses if _weaknesses is not None else _fetch_user_weaknesses(
        user_id,
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )

    if not weaknesses:
        return {
            "user_id": user_id,
            "recommendations": DEFAULT_RECOMMENDATIONS,
        }

    recommendations = []
    seen_titles = set()

    # Sort by frequency (most frequent weakness first)
    sorted_weaknesses = sorted(
        weaknesses,
        key=lambda w: w.get("frequency", 0),
        reverse=True,
    )

    for weakness in sorted_weaknesses:
        category = weakness.get("category", "")
        training_options = WEAKNESS_TO_TRAINING.get(category, [])

        for option in training_options:
            if option["title"] not in seen_titles:
                seen_titles.add(option["title"])
                recommendations.append({
                    **option,
                    "weakness_addressed": category,
                })

    # If no specific recommendations matched, add defaults
    if not recommendations:
        recommendations = DEFAULT_RECOMMENDATIONS

    return {
        "user_id": user_id,
        "recommendations": recommendations,
    }


def _handle_training_recommender(args: dict, **kwargs) -> str:
    result = training_recommender(user_id=args.get("user_id", ""))
    return json.dumps(result, indent=2)


registry.register(
    name="training_recommender",
    toolset="chess",
    schema=TRAINING_SCHEMA,
    handler=_handle_training_recommender,
    description="Suggest training based on user weaknesses.",
    emoji="🎓",
)
