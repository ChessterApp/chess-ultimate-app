"""Tool: get_player_openings — Aggregate player opening repertoire from TWIC."""

import json
import logging
import os
import sqlite3

from tools.registry import registry

logger = logging.getLogger(__name__)

TWIC_DB_PATH = os.environ.get(
    "TWIC_DB_PATH",
    "/root/chess-app/backend/data/twic/games_index.db",
)

DEFAULT_LIMIT = 10
MAX_LIMIT = 50

PLAYER_OPENINGS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_player_openings",
        "description": (
            "Aggregate a player's opening repertoire from the TWIC master database. "
            "Shows their most-played openings with win/draw/loss stats."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "Player name to search for.",
                },
                "color": {
                    "type": "string",
                    "enum": ["white", "black", "both"],
                    "description": "Filter by color (default: both).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max openings to return (default 10).",
                },
            },
            "required": ["player_name"],
        },
    },
}


def get_player_openings(
    player_name: str,
    color: str = "both",
    limit: int = DEFAULT_LIMIT,
    db_path: str = None,
    conn: sqlite3.Connection = None,
) -> dict:
    """Aggregate player opening repertoire from TWIC master database."""
    if not player_name:
        return {"error": "player_name is required."}

    limit = min(max(1, limit), MAX_LIMIT)
    pattern = f"%{player_name}%"

    # Build query based on color filter
    if color == "white":
        where = "white LIKE ?"
        params = [pattern]
    elif color == "black":
        where = "black LIKE ?"
        params = [pattern]
    else:
        where = "(white LIKE ? OR black LIKE ?)"
        params = [pattern, pattern]

    query = f"""
        SELECT eco, opening,
               COUNT(*) as games,
               SUM(CASE WHEN result = '1-0' THEN 1 ELSE 0 END) as white_wins,
               SUM(CASE WHEN result = '1/2-1/2' THEN 1 ELSE 0 END) as draws,
               SUM(CASE WHEN result = '0-1' THEN 1 ELSE 0 END) as black_wins
        FROM games
        WHERE {where} AND eco IS NOT NULL AND eco != ''
        GROUP BY eco, opening
        ORDER BY games DESC
        LIMIT ?
    """
    params.append(limit)

    own_conn = False
    if conn is None:
        path = db_path or TWIC_DB_PATH
        conn = sqlite3.connect(path)
        own_conn = True

    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, params)
        rows = cur.fetchall()
    finally:
        if own_conn:
            conn.close()

    openings = []
    for r in rows:
        games = r["games"]
        # Calculate win percentage from the player's perspective
        if color == "white":
            wins = r["white_wins"]
            losses = r["black_wins"]
        elif color == "black":
            wins = r["black_wins"]
            losses = r["white_wins"]
        else:
            wins = r["white_wins"] + r["black_wins"]
            losses = 0  # can't determine perspective in "both" mode
        win_pct = round((wins / games * 100) if games else 0, 1)

        openings.append({
            "eco": r["eco"],
            "opening_name": r["opening"] or "",
            "games": games,
            "wins": wins,
            "draws": r["draws"],
            "losses": losses,
            "win_pct": win_pct,
        })

    return {
        "player_name": player_name,
        "color": color,
        "openings": openings,
    }


def _handle_get_player_openings(args: dict, **kwargs) -> str:
    result = get_player_openings(
        player_name=args.get("player_name", ""),
        color=args.get("color", "both"),
        limit=args.get("limit", DEFAULT_LIMIT),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="get_player_openings",
    toolset="chess",
    schema=PLAYER_OPENINGS_SCHEMA,
    handler=_handle_get_player_openings,
    description="Get a player's opening repertoire from master database.",
    emoji="📖",
)
