"""Tool 2: get_opening_stats — ECO code lookup with TWIC statistics."""

import logging
import os
import sqlite3

from tools.registry import registry

logger = logging.getLogger(__name__)

# ECO reference data: common openings with names and main lines
ECO_DATA = {
    "A00": {"name": "Uncommon Opening", "main_line": "1. ..."},
    "A04": {"name": "Reti Opening", "main_line": "1. Nf3"},
    "A10": {"name": "English Opening", "main_line": "1. c4"},
    "A13": {"name": "English Opening", "main_line": "1. c4 e6"},
    "A15": {"name": "English Opening", "main_line": "1. c4 Nf6"},
    "A20": {"name": "English Opening", "main_line": "1. c4 e5"},
    "A40": {"name": "Queen's Pawn Game", "main_line": "1. d4"},
    "A45": {"name": "Queen's Pawn Game", "main_line": "1. d4 Nf6"},
    "B00": {"name": "King's Pawn Opening", "main_line": "1. e4"},
    "B01": {"name": "Scandinavian Defense", "main_line": "1. e4 d5"},
    "B06": {"name": "Modern Defense", "main_line": "1. e4 g6"},
    "B07": {"name": "Pirc Defense", "main_line": "1. e4 d6 2. d4 Nf6 3. Nc3"},
    "B10": {"name": "Caro-Kann Defense", "main_line": "1. e4 c6"},
    "B12": {"name": "Caro-Kann Defense", "main_line": "1. e4 c6 2. d4 d5 3. e5"},
    "B20": {"name": "Sicilian Defense", "main_line": "1. e4 c5"},
    "B90": {"name": "Sicilian Najdorf", "main_line": "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6"},
    "C00": {"name": "French Defense", "main_line": "1. e4 e6"},
    "C20": {"name": "King's Pawn Game", "main_line": "1. e4 e5"},
    "C42": {"name": "Petrov Defense", "main_line": "1. e4 e5 2. Nf3 Nf6"},
    "C44": {"name": "King's Pawn Game", "main_line": "1. e4 e5 2. Nf3 Nc6"},
    "C50": {"name": "Italian Game", "main_line": "1. e4 e5 2. Nf3 Nc6 3. Bc4"},
    "C60": {"name": "Ruy Lopez", "main_line": "1. e4 e5 2. Nf3 Nc6 3. Bb5"},
    "C65": {"name": "Ruy Lopez Berlin", "main_line": "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6"},
    "C67": {"name": "Ruy Lopez Berlin", "main_line": "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. O-O Nxe4"},
    "C70": {"name": "Ruy Lopez", "main_line": "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"},
    "D00": {"name": "Queen's Pawn Game", "main_line": "1. d4 d5"},
    "D30": {"name": "Queen's Gambit Declined", "main_line": "1. d4 d5 2. c4 e6"},
    "D37": {"name": "Queen's Gambit Declined", "main_line": "1. d4 Nf6 2. c4 e6 3. Nf3 d5 4. Nc3 Be7"},
    "D80": {"name": "Grunfeld Defense", "main_line": "1. d4 Nf6 2. c4 g6 3. Nc3 d5"},
    "D85": {"name": "Grunfeld Defense", "main_line": "1. d4 Nf6 2. c4 g6 3. Nc3 d5 4. cxd5 Nxd5"},
    "E00": {"name": "Queen's Pawn Game", "main_line": "1. d4 Nf6 2. c4 e6"},
    "E20": {"name": "Nimzo-Indian Defense", "main_line": "1. d4 Nf6 2. c4 e6 3. Nc3 Bb4"},
    "E60": {"name": "King's Indian Defense", "main_line": "1. d4 Nf6 2. c4 g6"},
}

# Reverse lookup: name -> eco list
_NAME_TO_ECO: dict[str, list[str]] = {}
for _eco, _info in ECO_DATA.items():
    _key = _info["name"].lower()
    _NAME_TO_ECO.setdefault(_key, []).append(_eco)

TWIC_DB_PATH = os.environ.get(
    "TWIC_DB_PATH",
    "/root/chess-app/backend/data/twic/games_index.db",
)

OPENING_STATS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_opening_stats",
        "description": "Get statistics and information about a chess opening by ECO code or name.",
        "parameters": {
            "type": "object",
            "properties": {
                "eco": {
                    "type": "string",
                    "description": "ECO code (e.g. 'B90', 'C65').",
                },
                "opening_name": {
                    "type": "string",
                    "description": "Opening name (e.g. 'Sicilian Najdorf', 'Ruy Lopez').",
                },
            },
        },
    },
}


def _get_stats_from_db(eco: str, db_path: str = None) -> dict:
    """Query TWIC database for win/draw/loss stats for an ECO code."""
    path = db_path or TWIC_DB_PATH
    if not os.path.exists(path):
        return {"games_count": 0, "white_win_pct": 0, "draw_pct": 0, "black_win_pct": 0}

    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            "SELECT result, COUNT(*) FROM games WHERE eco = ? GROUP BY result",
            (eco,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    total = sum(count for _, count in rows)
    if total == 0:
        return {"games_count": 0, "white_win_pct": 0, "draw_pct": 0, "black_win_pct": 0}

    white_wins = sum(c for r, c in rows if r == "1-0")
    draws = sum(c for r, c in rows if r == "1/2-1/2")
    black_wins = sum(c for r, c in rows if r == "0-1")

    return {
        "games_count": total,
        "white_win_pct": round(white_wins / total * 100, 1),
        "draw_pct": round(draws / total * 100, 1),
        "black_win_pct": round(black_wins / total * 100, 1),
    }


def get_opening_stats(
    eco: str = None,
    opening_name: str = None,
    db_path: str = None,
) -> dict:
    """Look up opening info by ECO code or name."""
    resolved_eco = None
    info = None

    if eco:
        resolved_eco = eco.upper().strip()
        info = ECO_DATA.get(resolved_eco)
    elif opening_name:
        key = opening_name.lower().strip()
        # Try exact match first
        if key in _NAME_TO_ECO:
            resolved_eco = _NAME_TO_ECO[key][0]
            info = ECO_DATA.get(resolved_eco)
        else:
            # Substring match
            for name, eco_list in _NAME_TO_ECO.items():
                if key in name or name in key:
                    resolved_eco = eco_list[0]
                    info = ECO_DATA.get(resolved_eco)
                    break

    if resolved_eco is None or info is None:
        return {"error": f"Unknown opening: {eco or opening_name}"}

    stats = _get_stats_from_db(resolved_eco, db_path)
    return {
        "eco": resolved_eco,
        "name": info["name"],
        "main_line": info["main_line"],
        **stats,
    }


def _handle_get_opening_stats(args: dict, **kwargs) -> str:
    import json
    result = get_opening_stats(eco=args.get("eco"), opening_name=args.get("opening_name"))
    return json.dumps(result, indent=2)


registry.register(
    name="get_opening_stats",
    toolset="chess",
    schema=OPENING_STATS_SCHEMA,
    handler=_handle_get_opening_stats,
    description="Get chess opening statistics by ECO code or name.",
    emoji="📖",
)
