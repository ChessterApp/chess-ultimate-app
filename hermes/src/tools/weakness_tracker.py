"""Tool: weakness_tracker — Analyze user games to detect weakness patterns."""

import json
import logging
import os

import chess
import chess.pgn
import httpx
import io

from tools.registry import registry
from src.tools.user_data import get_user_games

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TIMEOUT = 10

WEAKNESS_SCHEMA = {
    "name": "weakness_tracker",
    "description": (
        "Analyze a user's recent games to detect patterns of weakness and strength. "
        "Categories: opening_theory, tactics, endgame, time_management, positional_play."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The user's ID.",
            },
            "num_games": {
                "type": "integer",
                "description": "Number of recent games to analyze (default 10).",
            },
        },
        "required": ["user_id"],
    },
}

DEFAULT_NUM_GAMES = 10


def _analyze_game_patterns(games: list[dict], user_id: str) -> dict:
    """Analyze a set of games for weakness and strength patterns."""
    weaknesses = []
    strengths = []

    total_games = len(games)
    if total_games == 0:
        return {"weaknesses": [], "strengths": []}

    # Track patterns
    opening_losses = 0
    endgame_losses = 0
    short_game_losses = 0
    wins = 0
    losses = 0
    draws = 0
    opening_ecos = {}

    for game in games:
        result = game.get("result", "")
        pgn_text = game.get("pgn", "")
        eco = game.get("eco", "")
        is_white = game.get("white", "").lower() == user_id.lower()

        # Determine if user won/lost
        user_won = (is_white and result == "1-0") or (not is_white and result == "0-1")
        user_lost = (is_white and result == "0-1") or (not is_white and result == "1-0")

        if user_won:
            wins += 1
        elif user_lost:
            losses += 1
        else:
            draws += 1

        # Track opening diversity
        if eco:
            opening_ecos[eco] = opening_ecos.get(eco, 0) + 1

        # Analyze game length from PGN
        if pgn_text:
            try:
                game_obj = chess.pgn.read_game(io.StringIO(pgn_text))
                if game_obj:
                    move_count = sum(1 for _ in game_obj.mainline_moves())
                    half_moves = move_count

                    # Short game loss (< 20 moves) suggests opening problems
                    if user_lost and half_moves < 40:
                        opening_losses += 1
                        short_game_losses += 1

                    # Long game loss (> 60 moves) suggests endgame problems
                    if user_lost and half_moves > 120:
                        endgame_losses += 1
            except Exception:
                pass

    # Detect weaknesses
    if losses > 0:
        if opening_losses >= 2 or (opening_losses / max(losses, 1)) >= 0.4:
            weaknesses.append({
                "category": "opening_theory",
                "description": "Frequent losses in the opening phase (under 20 moves).",
                "frequency": opening_losses,
                "example_game": next(
                    (g.get("id") for g in games if g.get("result") in ["0-1", "1-0"]),
                    None,
                ),
            })

        if endgame_losses >= 2 or (endgame_losses / max(losses, 1)) >= 0.4:
            weaknesses.append({
                "category": "endgame",
                "description": "Losses in long games suggest endgame technique needs work.",
                "frequency": endgame_losses,
                "example_game": None,
            })

    # Check opening variety (too narrow = predictable)
    if len(opening_ecos) <= 2 and total_games >= 5:
        weaknesses.append({
            "category": "opening_theory",
            "description": "Very narrow opening repertoire — only using 1-2 openings.",
            "frequency": total_games,
            "example_game": None,
        })

    # Detect strengths
    win_rate = wins / total_games if total_games else 0
    if win_rate >= 0.6:
        strengths.append({
            "category": "positional_play",
            "description": f"Strong overall win rate ({round(win_rate * 100)}%).",
        })

    if len(opening_ecos) >= 5:
        strengths.append({
            "category": "opening_theory",
            "description": "Diverse opening repertoire with multiple systems.",
        })

    if short_game_losses == 0 and total_games >= 5:
        strengths.append({
            "category": "opening_theory",
            "description": "No quick losses — solid opening preparation.",
        })

    return {"weaknesses": weaknesses, "strengths": strengths}


def _update_profile_weaknesses(
    user_id: str,
    weaknesses: list[dict],
    supabase_url: str = None,
    supabase_key: str = None,
) -> None:
    """Update user_chess_profiles.weaknesses in Supabase."""
    base = supabase_url or SUPABASE_URL
    api_key = supabase_key or SUPABASE_KEY

    if not base or not api_key:
        return

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        httpx.patch(
            f"{base}/rest/v1/user_chess_profiles",
            params={"user_id": f"eq.{user_id}"},
            headers=headers,
            json={"weaknesses": weaknesses},
            timeout=TIMEOUT,
        )
    except Exception:
        logger.exception("Failed to update weaknesses for user %s", user_id)


def weakness_tracker(
    user_id: str,
    num_games: int = DEFAULT_NUM_GAMES,
    supabase_url: str = None,
    supabase_key: str = None,
) -> dict:
    """Analyze user recent games to detect patterns of weakness."""
    games = get_user_games(
        user_id=user_id,
        limit=num_games,
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )

    if not games:
        return {
            "user_id": user_id,
            "games_analyzed": 0,
            "weaknesses": [],
            "strengths": [],
        }

    analysis = _analyze_game_patterns(games, user_id)

    # Update profile weaknesses in Supabase
    _update_profile_weaknesses(
        user_id,
        analysis["weaknesses"],
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )

    return {
        "user_id": user_id,
        "games_analyzed": len(games),
        **analysis,
    }


def _handle_weakness_tracker(args: dict, **kwargs) -> str:
    result = weakness_tracker(
        user_id=args.get("user_id", ""),
        num_games=args.get("num_games", DEFAULT_NUM_GAMES),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="weakness_tracker",
    toolset="chess",
    schema=WEAKNESS_SCHEMA,
    handler=_handle_weakness_tracker,
    description="Detect weakness patterns from user's recent games.",
    emoji="🔍",
)
