"""Tools 3 & 4: search_master_games and get_game_pgn — TWIC database queries."""

import json
import logging
import os
import sqlite3

from tools.registry import registry

from src.player_names import event_terms, name_patterns, normalized_pattern, split_players
from src.tools._sqlite_budget import TIMEOUT_ERROR, install_timeout, is_timeout

logger = logging.getLogger(__name__)

TWIC_DB_PATH = os.environ.get(
    "TWIC_DB_PATH",
    "/root/chess-app/backend/data/twic/games_index.db",
)

MAX_LIMIT = 50
DEFAULT_LIMIT = 20

# --- Tool 3: search_master_games ---

SEARCH_GAMES_SCHEMA = {
    "name": "search_master_games",
    "description": (
        "Search the TWIC master games database (millions of real games with their full moves, up to this "
        "week). Filter by player and opponent (any spelling: «Карлсен», «Синдаров — Накамура», Carlsen), "
        "event, ECO, opening, result and years. Newest first: the first row is the latest game of the player. "
        "Then use get_game_pgn with a returned id for the moves (show=true puts the game on the board)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "player": {"type": "string", "description": "Player name (searches both white and black). Surname is enough; Russian or Latin."},
            "opponent": {"type": "string", "description": "The other player of the game, for a game between two players (e.g. player='Sindarov', opponent='Nakamura')."},
            "event": {"type": "string", "description": "Tournament/event name substring (e.g. 'Candidates', 'Tata Steel', 'Miami')."},
            "eco": {"type": "string", "description": "ECO code (e.g. 'B90')."},
            "opening": {"type": "string", "description": "Opening name substring."},
            "result": {"type": "string", "description": "Game result: '1-0', '0-1', or '1/2-1/2'."},
            "year_min": {"type": "integer", "description": "Earliest year."},
            "year_max": {"type": "integer", "description": "Latest year."},
            "limit": {"type": "integer", "description": "Max results (default 20, max 50)."},
        },
    },
}


def _side(column: str, patterns: list) -> tuple[str, list]:
    """``(column LIKE ? OR column LIKE ? …)`` for one player's name patterns."""
    return "(" + " OR ".join([f"{column} LIKE ?"] * len(patterns)) + ")", list(patterns)


def _name_columns(conn: sqlite3.Connection) -> tuple[str, str, bool]:
    """The name columns to match: the site's normalized ones when the database has them (accents
    dropped: «Hubner» finds «Hübner», as the database page does), else the raw names."""
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
    except sqlite3.Error:
        cols = set()
    if {"white_name_normalized", "black_name_normalized"} <= cols:
        return "white_name_normalized", "black_name_normalized", True
    return "white_name", "black_name", False


def _player_condition(player: str, opponent: str = None,
                      columns: tuple = ("white_name", "black_name", False)) -> tuple[str, list]:
    """The WHERE part for one player (either colour) or two players against each other.

    Names are matched in any spelling (src/player_names.py): «Карлсена» → Carlsen, «Javohir» →
    Javokhir; a ``player`` like «Синдаров — Накамура» is read as both players."""
    white_col, black_col, normalized = columns
    people = split_players(player) if player else []
    if opponent and len(people) < 2:
        people = (people or [])[:1] + [opponent]
    pats = [name_patterns(p) for p in people[:2]]
    if normalized:
        pats = [list(dict.fromkeys(normalized_pattern(x) for x in p)) for p in pats]
    pats = [p for p in pats if p]
    if not pats:
        return "", []
    if len(pats) == 1:
        white, wp = _side(white_col, pats[0])
        black, bp = _side(black_col, pats[0])
        return f"({white} OR {black})", wp + bp
    a, b = pats
    wa, pwa = _side(white_col, a)
    bb, pbb = _side(black_col, b)
    wb, pwb = _side(white_col, b)
    ba, pba = _side(black_col, a)
    return f"(({wa} AND {bb}) OR ({wb} AND {ba}))", pwa + pbb + pwb + pba


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
    opponent: str = None,
) -> list[dict]:
    """Search TWIC database with parameterized queries."""
    limit = min(max(1, limit), MAX_LIMIT)

    own_conn = False
    if conn is None:
        path = db_path or TWIC_DB_PATH
        conn = sqlite3.connect(path)
        own_conn = True
    try:
        return _search(conn, player, opponent, event, eco, opening, result, year_min, year_max, limit)
    finally:
        if own_conn:
            conn.close()


def _year(value) -> "int | None":
    """A year argument as an int (the model sends 2026 or "2026"); anything else is no bound."""
    try:
        return int(str(value).strip()[:4]) if value is not None and str(value).strip() else None
    except ValueError:
        return None


def _search(conn, player, opponent, event, eco, opening, result, year_min, year_max, limit) -> list[dict]:
    conditions = []
    params = []

    if player or opponent:
        # One name: its longest word («Javohir Sindarov» → Sindarov), in its database spellings — a
        # Russian name transliterated, kh/h and umlauts varied (src/player_names.py). Two names: a game
        # between them, either colour.
        clause, clause_params = _player_condition(player or "", opponent, _name_columns(conn))
        if clause:
            conditions.append(clause)
            params.extend(clause_params)

    if event:
        # Split event into words and match each independently (OR).
        # "Candidates Match" → searches "Candidates" OR "Match",
        # which matches "FIDE Candidates 2026" in the DB. Russian words
        # go in their database spelling («Майами» → Miami); a year is left to year_min/year_max.
        event_parts = event_terms(event) or [event.strip()]
        event_clauses = " OR ".join(["event LIKE ?"] * len(event_parts))
        conditions.append(f"({event_clauses})")
        for part in event_parts:
            params.append(f"%{part}%")

    if eco:
        conditions.append("eco = ?")
        params.append(eco.upper())

    if opening:
        conditions.append("opening LIKE ?")
        params.append(f"%{opening}%")

    if result:
        conditions.append("result = ?")
        params.append(result)

    # TWIC dates are the PGN's «2026.03.10» (backend/scripts/incremental_index.py): ``date <=
    # '2026-12-31'`` left out every game of 2026 itself ('.' sorts after '-'). The bounds are by
    # the year's prefix, which holds for either separator.
    year_min, year_max = _year(year_min), _year(year_max)
    if year_min is not None:
        conditions.append("date >= ?")
        params.append(f"{year_min:04d}")

    if year_max is not None:
        conditions.append("date < ?")
        params.append(f"{year_max + 1:04d}")

    where = " AND ".join(conditions) if conditions else "1=1"
    query = f"SELECT id, white_name, black_name, result, date, eco, opening, event, white_elo, black_elo FROM games WHERE {where} ORDER BY date DESC LIMIT ?"
    params.append(limit)

    conn.row_factory = sqlite3.Row
    # Player/opening/event filters are LIKE '%…%' — a full scan of the games
    # table; the budget turns a stuck search into an error the model skips.
    install_timeout(conn)
    cur = conn.execute(query, params)
    rows = cur.fetchall()
    return [dict(row) for row in rows]


def _handle_search_master_games(args: dict, **kwargs) -> str:
    logger.info("search_master_games called with args: %s", json.dumps(args))
    try:
        results = search_master_games(
            player=args.get("player"),
            opponent=args.get("opponent"),
            event=args.get("event"),
            eco=args.get("eco"),
            opening=args.get("opening"),
            result=args.get("result"),
            year_min=args.get("year_min"),
            year_max=args.get("year_max"),
            limit=args.get("limit", DEFAULT_LIMIT),
        )
    except sqlite3.OperationalError as exc:
        if not is_timeout(exc):
            raise
        logger.warning("search_master_games timed out: %s", json.dumps(args))
        return json.dumps({"error": TIMEOUT_ERROR, "games": []})
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
    "name": "get_game_pgn",
    "description": (
        "The full game — every move and the headers — for a database game id from search_master_games or "
        "find_games_by_position. With show=true it also puts the game on the board in front of the student, "
        "who steps through the moves: set it when the student asks to load, show or open the game."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "game_id": {
                "type": "integer",
                "description": "The game ID from the database.",
            },
            "show": {
                "type": "boolean",
                "description": "Put the game on the board in front of the student (load it with all its moves).",
            },
        },
        "required": ["game_id"],
    },
}


PGN_FILE_PATH = os.environ.get(
    "TWIC_PGN_PATH",
    "/root/chess-app/backend/data/twic/twic_master_database.pgn",
)


def _read_movetext(offset: int, length: int) -> str:
    """The game's text from the master PGN: ``length`` bytes at ``offset``.

    The file is read as bytes and decoded with replacement, as the site's
    /games/<id>/pgn does (errors='replace'): TWIC holds Latin-1 names, and a
    strict text read raised on any such byte near the game, so the coach got
    no moves for games the database page shows (live site, 02.11).
    """
    try:
        with open(PGN_FILE_PATH, "rb") as f:
            f.seek(offset)
            return f.read(length).decode("utf-8", errors="replace")
    except (OSError, ValueError) as e:
        logger.warning("Could not read PGN file: %s", e)
        return ""


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

    # Production stores movetext by offset into the master PGN file; a row that
    # carries an inline ``pgn`` column (test databases) is used as-is.
    pgn_offset = row_dict.get("pgn_offset") or 0
    pgn_length = row_dict.get("pgn_length") or 0
    pgn_text = row_dict.get("pgn") or ""
    if not pgn_text and pgn_length > 0:
        pgn_text = _read_movetext(pgn_offset, pgn_length)

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

    pgn_text = pgn_text.strip()
    if pgn_text and not pgn_text.startswith("["):
        tag_block = "".join(f'[{k} "{v}"]\n' for k, v in headers.items() if v)
        pgn_text = f"{tag_block}\n{pgn_text}"

    if not pgn_text:
        # No moves to show: say so, so the coach never invents the score.
        return {"error": f"The moves of game {game_id} could not be read.", "headers": headers}
    return {"pgn": pgn_text, "headers": headers}


def _with_board(result: dict) -> dict:
    """*result* with the game put on the board (``load_pgn``, the board protocol every tool uses).

    The model no longer copies a whole game's PGN into board_control: the coach found the game and
    then answered without loading it, or loaded a mistyped score (live site, 03.11). The board lock
    of the turn still applies (src/board_truth.py drops a position action under a strict lock)."""
    from src.board_protocol import parse_pgn_moves

    pgn = result.get("pgn") or ""
    try:
        moves = parse_pgn_moves(pgn)
    except ValueError as exc:
        logger.warning("get_game_pgn: the game's PGN does not load: %s", exc)
        return {**result, "shown": False, "board_hint": "This game's score could not be put on the board."}
    if not moves:
        return {**result, "shown": False, "board_hint": "This game has no moves to put on the board."}
    return {**result, "board_actions": [{"type": "load_pgn", "pgn": pgn}]}


def _handle_get_game_pgn(args: dict, **kwargs) -> str:
    result = get_game_pgn(game_id=args.get("game_id", 0))
    if args.get("show") is True and isinstance(result, dict) and result.get("pgn"):
        result = _with_board(result)
    return json.dumps(result, indent=2)


registry.register(
    name="get_game_pgn",
    toolset="chess",
    schema=GET_PGN_SCHEMA,
    handler=_handle_get_game_pgn,
    description="Retrieve full PGN for a game by ID.",
    emoji="📄",
)
