"""Tool: opponent_prep — Prepare for an upcoming opponent."""

import json
import logging

from tools.registry import registry
from src.tools.player_profiles import get_player_profile
from src.tools.player_openings import get_player_openings

logger = logging.getLogger(__name__)

OPPONENT_PREP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "opponent_prep",
        "description": (
            "Prepare for an upcoming opponent by analyzing their profile, "
            "most-played openings, and suggesting counter-openings."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opponent_username": {
                    "type": "string",
                    "description": "Opponent's username on the platform.",
                },
                "platform": {
                    "type": "string",
                    "enum": ["lichess", "chesscom"],
                    "description": "Platform: 'lichess' or 'chesscom'.",
                },
                "user_color": {
                    "type": "string",
                    "enum": ["white", "black"],
                    "description": "The color you will play as.",
                },
            },
            "required": ["opponent_username", "platform", "user_color"],
        },
    },
}


def opponent_prep(
    opponent_username: str,
    platform: str,
    user_color: str,
    client=None,
    db_path: str = None,
    conn=None,
) -> dict:
    """Prepare for an upcoming opponent with profile and opening analysis."""
    # Get opponent profile
    profile = get_player_profile(
        username=opponent_username,
        platform=platform,
        client=client,
    )

    if "error" in profile:
        return {"error": f"Could not fetch opponent profile: {profile['error']}"}

    # Get opponent's openings for the color they will play (opposite of user_color)
    opponent_color = "black" if user_color == "white" else "white"
    openings_data = get_player_openings(
        player_name=opponent_username,
        color=opponent_color,
        limit=10,
        db_path=db_path,
        conn=conn,
    )

    opponent_openings = openings_data.get("openings", [])

    # Analyze weaknesses from opening stats
    weaknesses = []
    for opening in opponent_openings:
        if opening["games"] >= 3 and opening["win_pct"] < 40:
            weaknesses.append({
                "opening": opening["opening_name"],
                "eco": opening["eco"],
                "games": opening["games"],
                "win_pct": opening["win_pct"],
                "note": "Low win rate — consider steering into this line.",
            })

    # Suggest counter-openings based on opponent's most played
    suggestions = []
    for opening in opponent_openings[:5]:
        eco = opening.get("eco", "")
        name = opening.get("opening_name", "")
        if eco.startswith(("B", "C")) and opponent_color == "black":
            suggestions.append({
                "against": name,
                "suggestion": "Prepare anti-Sicilian or mainline theory",
                "eco": eco,
            })
        elif eco.startswith("D") and opponent_color == "black":
            suggestions.append({
                "against": name,
                "suggestion": "Prepare d4 sidelines or QGD theory",
                "eco": eco,
            })
        elif eco.startswith(("A", "E")):
            suggestions.append({
                "against": name,
                "suggestion": "Study Indian defense structures",
                "eco": eco,
            })
        else:
            suggestions.append({
                "against": name,
                "suggestion": "Review common plans and typical middlegame patterns",
                "eco": eco,
            })

    return {
        "opponent": profile,
        "opponent_openings": opponent_openings,
        "weaknesses": weaknesses,
        "suggested_preparation": suggestions,
    }


def _handle_opponent_prep(args: dict, **kwargs) -> str:
    result = opponent_prep(
        opponent_username=args.get("opponent_username", ""),
        platform=args.get("platform", "lichess"),
        user_color=args.get("user_color", "white"),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="opponent_prep",
    toolset="chess",
    schema=OPPONENT_PREP_SCHEMA,
    handler=_handle_opponent_prep,
    description="Prepare for an upcoming opponent with opening analysis.",
    emoji="🎯",
)
