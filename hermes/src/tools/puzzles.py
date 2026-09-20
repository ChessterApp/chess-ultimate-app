"""Tool: get_puzzle — a verified tactical puzzle from the Lichess puzzle set.

Before this tool the coach had no puzzle source: ``set_puzzle`` took a FEN and
a solution the model made up, and the student could not solve them. Now the
coach asks for a puzzle by theme and rating, gets a real position with a
verified solution, and puts it on the board with ``set_puzzle`` by id.
"""

import json
import logging
import random

from tools.registry import registry

from src.puzzle_db import THEME_ALIASES, db_available, find_puzzles, resolve_theme, stats

logger = logging.getLogger(__name__)

_THEME_LIST = ", ".join(sorted(THEME_ALIASES))

GET_PUZZLE_SCHEMA = {
    "name": "get_puzzle",
    "description": (
        "Get a verified tactical puzzle (Lichess puzzle set) by theme and rating. "
        "Returns the position the student must solve (FEN, side to move), the "
        "solution in SAN, rating and themes. ALWAYS use this instead of inventing "
        "a puzzle; then call board_control set_puzzle with the returned puzzle_id. "
        f"Themes (English tags, RU/KK phrases like «вилка», «связка», «мат в 2» are accepted): {_THEME_LIST}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "theme": {
                "type": "string",
                "description": "Theme tag or phrase, e.g. 'fork', 'pin', 'mateIn2', 'endgame', «связка». Omit for any theme.",
            },
            "rating": {
                "type": "integer",
                "description": "Target puzzle rating (Lichess scale, ~600–2800). Use the student's rating; omit for any.",
            },
            "opening": {
                "type": "string",
                "description": "Optional opening tag filter, e.g. 'Sicilian_Defense', 'Italian_Game'.",
            },
            "count": {
                "type": "integer",
                "description": "How many puzzles to return (1–10, default 1).",
            },
            "exclude_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Puzzle ids already shown in this session, to avoid repeats.",
            },
        },
    },
}


def get_puzzle(
    theme: str = None,
    rating: int = None,
    opening: str = None,
    count: int = 1,
    exclude_ids: list = None,
    db_path: str = None,
    rng: random.Random = None,
) -> dict:
    if not db_available(db_path):
        return {
            "error": "Puzzle database is not installed on this server "
                     "(scripts/import_puzzles.py builds it from the Lichess puzzle set).",
        }
    resolved = resolve_theme(theme) if theme else None
    if theme and not resolved:
        return {
            "error": f"Unknown theme {theme!r}.",
            "known_themes": sorted(THEME_ALIASES),
        }
    try:
        rating_int = int(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_int = None

    puzzles = find_puzzles(
        theme=resolved,
        rating=rating_int,
        opening=opening,
        exclude_ids=exclude_ids,
        count=count,
        db_path=db_path,
        rng=rng,
    )
    if not puzzles:
        return {
            "error": "No puzzle matched.",
            "theme": resolved,
            "rating": rating_int,
            "hint": "Try another theme or drop the opening filter.",
        }
    return {
        "theme": resolved,
        "rating": rating_int,
        "count": len(puzzles),
        "puzzles": puzzles,
        "how_to_show": "Call board_control with action_type='set_puzzle' and puzzle_id=<puzzle_id>.",
    }


def _handle_get_puzzle(args: dict, **kwargs) -> str:
    result = get_puzzle(
        theme=args.get("theme"),
        rating=args.get("rating"),
        opening=args.get("opening"),
        count=args.get("count", 1),
        exclude_ids=args.get("exclude_ids"),
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


registry.register(
    name="get_puzzle",
    toolset="chess",
    schema=GET_PUZZLE_SCHEMA,
    handler=_handle_get_puzzle,
    description="Get a verified tactical puzzle by theme and rating.",
    emoji="🧩",
)


def puzzle_db_stats() -> dict:
    """Health-check helper: is the puzzle DB installed and how big is it."""
    return stats()
