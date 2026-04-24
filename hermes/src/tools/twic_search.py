"""Tools 3 & 4: search_master_games and get_game_pgn — TWIC database queries."""

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

MAX_LIMIT = 50
DEFAULT_LIMIT = 20

# --- Tool 3: search_master_games ---

SEARCH_GAMES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_master_games",
        "description": "Search the TWIC master games database. Filter by player, ECO code, opening, result, and year range.",
        "parameters": {
            "type": "object",
            "properties": {
                "player": {"type": "string", "description": "Player name (searches both white and black). Use surname only for best results."},
                "event": {"type": "string", "description": "Tournament/event name substring (e.g. 'Candidates', 'Tata Steel')."},
                "eco": {"type": "string", "description": "ECO code (e.g. 'B90')."},
                "opening": {"type": "string", "description": "Opening name substring."},
                "result": {"type": "string", "description": "Game result: '1-0', '0-1', or '1/2-1/2'."},
                "year_min": {"type": "integer", "description": "Earliest year."},
                "year_max": {"type": "integer", "description": "Latest year."},
                "limit": {"type": "integer", "description": "Max results (default 20, max 50)."},
            },
        },
    },
}


def search_master_games(
    player: str = None,
    event: str = None,
    eco: str = None,
    opening: str = None,
    result: str = None,
    year_min: int = None,
    year_max: int = None,
    limit: int = DEFAULT_LIMIT,
    db_path: str = None,
    conn: sqlite3.Connection = None,
) -> list[dict]:
    """Search TWIC database with parameterized queries."""
    limit = min(max(1, limit), MAX_LIMIT)

    conditions = []
    params = []

    if player:
        # Use the longest token as the primary search term.
        # This handles "Javohir Sindarov" → searches "Sindarov" which matches
        # "Sindarov,Javokhir" despite transliteration differences (kh vs h).
        parts = player.strip().split()
        search_term = max(parts, key=len) if parts else player
        conditions.append("(white_name LIKE ? OR black_name LIKE ?)")
        pattern = f"%{search_term}%"
        params.extend([pattern, pattern])

    if event:
        conditions.append("event LIKE ?")
        params.append(f"%{event}%")

    if eco:
        conditions.append("eco = ?")
        params.append(eco.upper())

    if opening:
        conditions.append("opening LIKE ?")
        params.append(f"%{opening}%")

    if result:
        conditions.append("result = ?")
        params.append(result)

    if year_min is not None:
        conditions.append("date >= ?")
        params.append(f"{year_min}-01-01")

    if year_max is not None:
        conditions.append("date <= ?")
        params.append(f"{year_max}-12-31")

    where = " AND ".join(conditions) if conditions else "1=1"
    query = f"SELECT id, white_name, black_name, result, date, eco, opening, event, white_elo, black_elo FROM games WHERE {where} ORDER BY date DESC LIMIT ?"
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
        return [dict(row) for row in rows]
    finally:
        if own_conn:
            conn.close()


def _handle_search_master_games(args: dict, **kwargs) -> str:
    logger.info("search_master_games called with args: %s", json.dumps(args))
    results = search_master_games(
        player=args.get("player"),
        event=args.get("event"),
        eco=args.get("eco"),
        opening=args.get("opening"),
        result=args.get("result"),
        year_min=args.get("year_min"),
        year_max=args.get("year_max"),
        limit=args.get("limit", DEFAULT_LIMIT),
    )
    logger.info("search_master_games returned %d results", len(results))
    return json.dumps(results, indent=2)


registry.register(
    name="search_master_games",
    toolset="chess",
    schema=SEARCH_GAMES_SCHEMA,
    handler=_handle_search_master_games,
    description="Search the TWIC master games database.",
    emoji="🗄️",
)


# --- Tool 4: get_game_pgn ---

GET_PGN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_game_pgn",
        "description": "Retrieve the full PGN and headers for a specific game by its database ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "game_id": {
                    "type": "integer",
                    "description": "The game ID from the database.",
                }
            },
            "required": ["game_id"],
        },
    },
}


PGN_FILE_PATH = os.environ.get(
    "TWIC_PGN_PATH",
    "/root/chess-app/backend/data/twic/twic_master_database.pgn",
)


def get_game_pgn(
    game_id: int,
    db_path: str = None,
    conn: sqlite3.Connection = None,
) -> dict:
    """Retrieve full PGN and headers for a game by ID."""
    own_conn = False
    if conn is None:
        path = db_path or TWIC_DB_PATH
        conn = sqlite3.connect(path)
        own_conn = True

    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM games WHERE id = ?", (game_id,)
        )
        row = cur.fetchone()
    finally:
        if own_conn:
            conn.close()

    if row is None:
        return {"error": f"Game ID {game_id} not found."}

    row_dict = dict(row)

    # Read PGN from file by offset
    pgn_offset = row_dict.get("pgn_offset", 0)
    pgn_length = row_dict.get("pgn_length", 0)
    pgn_text = ""
    if pgn_length > 0:
        try:
            with open(PGN_FILE_PATH, "r") as f:
                f.seek(pgn_offset)
                pgn_text = f.read(pgn_length)
        except (FileNotFoundError, IOError) as e:
            logger.warning("Could not read PGN file: %s", e)
            pgn_text = ""

    headers = {
        "White": row_dict.get("white_name", ""),
        "Black": row_dict.get("black_name", ""),
        "Result": row_dict.get("result", ""),
        "Date": row_dict.get("date", ""),
        "ECO": row_dict.get("eco", ""),
        "Event": row_dict.get("event", ""),
        "WhiteElo": str(row_dict.get("white_elo", "")),
        "BlackElo": str(row_dict.get("black_elo", "")),
    }

    return {"pgn": pgn_text.strip(), "headers": headers}


def _handle_get_game_pgn(args: dict, **kwargs) -> str:
    result = get_game_pgn(game_id=args.get("game_id", 0))
    return json.dumps(result, indent=2)


registry.register(
    name="get_game_pgn",
    toolset="chess",
    schema=GET_PGN_SCHEMA,
    handler=_handle_get_game_pgn,
    description="Retrieve full PGN for a game by ID.",
    emoji="📄",
)
