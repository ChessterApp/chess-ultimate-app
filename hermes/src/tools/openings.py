"""Tools: get_opening_stats and identify_opening — ECO book + TWIC statistics.

Opening names and lines come from the 3,800-line ECO book in
``backend/data/openings/*.tsv`` (see src/openings_book.py), not from a
hand-typed table; statistics come from the TWIC games index.
"""

import json
import logging
import os
import sqlite3

from tools.registry import registry

from src.openings_book import get_book

logger = logging.getLogger(__name__)

TWIC_DB_PATH = os.environ.get(
    "TWIC_DB_PATH",
    "/root/chess-app/backend/data/twic/games_index.db",
)

OPENING_STATS_SCHEMA = {
    "name": "get_opening_stats",
    "description": (
        "Look up a chess opening by ECO code or name: main line, named variations "
        "from the ECO book (3,800 lines), and master-game statistics from the TWIC "
        "database. Russian names work too («Сицилианская», «Найдорф», «Испанская»)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "eco": {
                "type": "string",
                "description": "ECO code (e.g. 'B90', 'C65').",
            },
            "opening_name": {
                "type": "string",
                "description": "Opening name in English or Russian (e.g. 'Sicilian Najdorf', 'Ruy Lopez', 'Каро-Канн').",
            },
        },
    },
}

IDENTIFY_OPENING_SCHEMA = {
    "name": "identify_opening",
    "description": (
        "Name the opening of a move sequence: the longest ECO-book line matching "
        "the moves, and the ply where the game left the book. Pass SAN moves or a PGN."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "moves": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Moves in SAN from the start position, e.g. ['e4','c5','Nf3'].",
            },
            "pgn": {
                "type": "string",
                "description": "Alternatively, the PGN movetext (with move numbers).",
            },
        },
    },
}


def _get_stats_from_db(eco, db_path: str = None) -> dict:
    """Query TWIC database for win/draw/loss stats for one ECO code or a list of them."""
    path = db_path or TWIC_DB_PATH
    if not os.path.exists(path):
        return {"games_count": 0, "white_win_pct": 0, "draw_pct": 0, "black_win_pct": 0}

    codes = [eco] if isinstance(eco, str) else sorted(set(eco))
    conn = sqlite3.connect(path)
    try:
        marks = ",".join("?" * len(codes))
        cur = conn.execute(
            f"SELECT result, COUNT(*) FROM games WHERE eco IN ({marks}) GROUP BY result",
            codes,
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
    """Look up opening info by ECO code or name (English or Russian)."""
    book = get_book()
    if eco:
        lines = book.by_eco(eco)
        query = eco.upper().strip()
    elif opening_name:
        lines = book.by_name(opening_name)
        query = opening_name
    else:
        return {"error": "Give an ECO code or an opening name."}

    if not lines:
        return {"error": f"Unknown opening: {query}"}

    main = lines[0]
    eco_codes = sorted({line[0] for line in lines})
    stats = _get_stats_from_db(eco_codes if opening_name else main[0], db_path)
    return {
        "eco": main[0],
        "eco_codes": eco_codes,
        "name": main[1],
        "main_line": main[2],
        "variations": [
            {"eco": e, "name": n, "line": line} for e, n, line in lines[1:15]
        ],
        "lines_in_book": len(lines),
        **stats,
    }


def identify_opening(moves=None, pgn: str = None) -> dict:
    """Longest ECO-book line matching the moves (or PGN)."""
    book = get_book()
    found = book.identify(moves if moves else (pgn or ""))
    if not found:
        return {"error": "No book line matches these moves.", "moves": moves or pgn}
    return found


def _handle_get_opening_stats(args: dict, **kwargs) -> str:
    result = get_opening_stats(eco=args.get("eco"), opening_name=args.get("opening_name"))
    return json.dumps(result, indent=2, ensure_ascii=False)


def _handle_identify_opening(args: dict, **kwargs) -> str:
    result = identify_opening(moves=args.get("moves"), pgn=args.get("pgn"))
    return json.dumps(result, indent=2, ensure_ascii=False)


registry.register(
    name="identify_opening",
    toolset="chess",
    schema=IDENTIFY_OPENING_SCHEMA,
    handler=_handle_identify_opening,
    description="Name the opening of a move sequence from the ECO book.",
    emoji="📚",
)


registry.register(
    name="get_opening_stats",
    toolset="chess",
    schema=OPENING_STATS_SCHEMA,
    handler=_handle_get_opening_stats,
    description="Get chess opening statistics by ECO code or name.",
    emoji="📖",
)
