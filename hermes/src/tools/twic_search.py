"""Tools 3 & 4: search_master_games and get_game_pgn — TWIC database queries."""

import json
import logging
import os
import re
import sqlite3

import chess

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
        "Search the TWIC master games database (millions of real games with their full moves, updated "
        "weekly). Filter by player and opponent (any spelling: «Карлсен», «Синдаров — Накамура», Carlsen), "
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


# --- The name index (the site's search, backend/api/openings.py games_by_position) ---------------------------
#
# ``LIKE '%carlsen%'`` reads every row: 1.1–1.6 s on a million rows, past the 3 s budget on the 4.35 M of
# production. The site asks the index instead: the normalized name («carlsen magnus», see
# backend/scripts/incremental_index.normalize_name) starts with the surname, so ``… LIKE 'carlsen%'`` is a range
# of an index on white_name_normalized / black_name_normalized, one UNION branch per column (an OR of the two
# columns is a scan). The coach does the same with each spelling of the name (src/player_names.py), as GLOB:
# GLOB is case-sensitive by itself, so the index range needs no ``PRAGMA case_sensitive_like`` — which would also
# make the event and opening LIKEs of the same query case-sensitive. The names are lower case in the index.

_NAME_COLUMNS = ("white_name_normalized", "black_name_normalized")
_RESULT_COLUMNS = "id, white_name, black_name, result, date, eco, opening, event, white_elo, black_elo"
_layouts: dict = {}


def _db_file(conn: sqlite3.Connection) -> str:
    try:
        for row in conn.execute("PRAGMA database_list"):
            if row[1] == "main":
                return row[2] or ""
    except sqlite3.Error:
        pass
    return ""


def name_index_layout(conn: sqlite3.Connection) -> dict:
    """How the database can be searched by name: ``{"normalized": bool, "indexes": {column: index name}}``.

    The indexes are those whose first column is a normalized name column in the binary collation (the one a
    GLOB prefix range uses); ``indexed`` is True when both columns have one. Read with PRAGMAs, cached per file
    (and its modification time: a rebuilt index is seen without a restart)."""
    path = _db_file(conn)
    key = None
    if path:
        try:
            st = os.stat(path)
            key = (path, st.st_mtime_ns, st.st_size)
        except OSError:
            key = None
        if key in _layouts:
            return _layouts[key]
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
        indexes = {}
        if set(_NAME_COLUMNS) <= cols:
            for idx in conn.execute("PRAGMA index_list(games)").fetchall():
                name, partial = idx[1], (idx[4] if len(idx) > 4 else 0)
                if partial:
                    continue
                first = next((r for r in conn.execute(f'PRAGMA index_xinfo("{name}")') if r[0] == 0), None)
                if first and first[2] in _NAME_COLUMNS and (first[4] or "BINARY").upper() == "BINARY":
                    indexes.setdefault(first[2], name)
    except sqlite3.Error:
        cols, indexes = set(), {}
    layout = {"normalized": set(_NAME_COLUMNS) <= cols, "indexes": indexes,
              "indexed": set(_NAME_COLUMNS) <= set(indexes)}
    if key:
        _layouts[key] = layout
    return layout


def _glob(like: str) -> str:
    """A LIKE pattern as GLOB: ``%`` → ``*``, ``_`` → ``?``, GLOB's own ``*?[`` taken literally."""
    out = []
    for ch in like:
        out.append({"%": "*", "_": "?", "*": "[*]", "?": "[?]", "[": "[[]"}.get(ch, ch))
    return "".join(out)


def _glob_prefix(pattern: str) -> str:
    """The literal start of a GLOB *pattern* — the index range it reads (empty: no range, a full pass)."""
    for i, ch in enumerate(pattern):
        if ch in "*?[":
            return pattern[:i]
    return pattern


def _anchored_patterns(name: str, strict: bool) -> list:
    """GLOB prefixes of the normalized name column for one player, in all its spellings."""
    return list(dict.fromkeys(_glob(normalized_pattern(p)) for p in name_patterns(name, strict=strict, anchored=True)))


def _people(player: str, opponent: str = None) -> list:
    people = split_players(player) if player else []
    if opponent and len(people) < 2:
        people = (people or [])[:1] + [opponent]
    return people[:2]


def _indexed_branches(player: str, opponent: str, strict: bool) -> "list | None":
    """The UNION branches of an indexed name search: ``[(where, params)]``, or None when no player of the
    query has a spelling with a literal start (only a pass over every row would find it).

    One branch per colour × spelling of the driving player — the first player with a spelling that has a
    literal start; that player's spellings without one are left out (a loose «?v?n?v» skeleton next to
    «ivanov»). The other player is a filter of the branch, on the other colour, in all their spellings."""
    pats = [p for p in (_anchored_patterns(x, strict) for x in _people(player, opponent)) if p]
    if not pats:
        return []
    ranged = [[g for g in p if _glob_prefix(g)] for p in pats]
    driver = next((i for i, r in enumerate(ranged) if r), None)
    if driver is None:
        return None
    other = [p for i, p in enumerate(pats) if i != driver][:1]
    white, black = _NAME_COLUMNS
    branches = []
    for col, opp_col in ((white, black), (black, white)):
        for g in ranged[driver]:
            where, params = [f"{col} GLOB ?"], [g]
            if other:
                where.append("(" + " OR ".join([f"{opp_col} GLOB ?"] * len(other[0])) + ")")
                params.extend(other[0])
            branches.append((" AND ".join(where), params))
    return branches


def _player_condition(player: str, opponent: str = None,
                      columns: tuple = ("white_name", "black_name", False), strict: bool = True) -> tuple[str, list]:
    """The WHERE part for one player (either colour) or two players against each other.

    Names are matched in any spelling (src/player_names.py): «Карлсена» → Carlsen, «Javohir» →
    Javokhir; a ``player`` like «Синдаров — Накамура» is read as both players."""
    white_col, black_col, normalized = columns
    pats = [name_patterns(p, strict=strict) for p in _people(player, opponent)]
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
    rows = _search_once(conn, player, opponent, event, eco, opening, result, year_min, year_max, limit, True)
    if not rows and (player or opponent) and _loosens(player or "", opponent):
        # «Robert Hübner» asks for both words; a database that has only «Hubner,R» gets the surname alone. A plain
        # «Stahlberg» finds the row stored as «St\ufffdhlberg» by its consonants (src/player_names._skeleton).
        rows = _search_once(conn, player, opponent, event, eco, opening, result, year_min, year_max, limit, False)
    return rows


def _loosens(player: str, opponent: str) -> bool:
    """The second try (``strict=False``) asks something the first did not."""
    return any(name_patterns(p, strict=False) != name_patterns(p, strict=True) for p in _people(player, opponent))


def _search_once(conn, player, opponent, event, eco, opening, result, year_min, year_max, limit,
                 strict: bool) -> list[dict]:
    conditions = []
    params = []
    branches = None
    if (player or opponent) and name_index_layout(conn)["indexed"]:
        # [] — no name in the argument at all: no name condition, as on the path without the index
        branches = _indexed_branches(player or "", opponent, strict) or None
    indexed = branches is not None
    # On the indexed path the other filters must not pick an index of their own (``+column``): with idx_date
    # SQLite may walk every game of the years asked for instead of the player's range of the name index.
    plain = "+" if indexed else ""

    if (player or opponent) and not indexed:
        # A known player by any word of the name, else its words in their database spellings — a Russian
        # name transliterated, kh/h and umlauts varied (src/player_names.py). Two names: a game between
        # them, either colour.
        clause, clause_params = _player_condition(player or "", opponent, _name_columns(conn), strict)
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
        conditions.append(f"{plain}eco = ?")
        params.append(eco.upper())

    if opening:
        conditions.append("opening LIKE ?")
        params.append(f"%{opening}%")

    if result:
        conditions.append(f"{plain}result = ?")
        params.append(result)

    # TWIC dates are the PGN's «2026.03.10» (backend/scripts/incremental_index.py): ``date <=
    # '2026-12-31'`` left out every game of 2026 itself ('.' sorts after '-'). The bounds are by
    # the year's prefix, which holds for either separator.
    year_min, year_max = _year(year_min), _year(year_max)
    if year_min is not None:
        conditions.append(f"{plain}date >= ?")
        params.append(f"{year_min:04d}")

    if year_max is not None:
        conditions.append(f"{plain}date < ?")
        params.append(f"{year_max + 1:04d}")

    if indexed:
        # One branch per colour × spelling, each a range of the name index; UNION drops a game two branches found.
        parts, query_params = [], []
        for where, branch_params in branches:
            parts.append(f"SELECT {_RESULT_COLUMNS} FROM games WHERE " + " AND ".join([where] + conditions))
            query_params.extend(branch_params + params)
        query = f"SELECT * FROM ({' UNION '.join(parts)}) ORDER BY date DESC, id DESC LIMIT ?"
        params = query_params
    else:
        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT {_RESULT_COLUMNS} FROM games WHERE {where} ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)

    conn.row_factory = sqlite3.Row
    # Without the name index the player/opening/event filters are LIKE '%…%' — a full scan of the games
    # table; the budget turns a stuck search into an error the model skips.
    install_timeout(conn)
    cur = conn.execute(query, params)
    rows = cur.fetchall()
    return [dict(row) for row in rows]


def search_check(db_path: str = None) -> dict:
    """For the runbook: does the search use the name index on this database, and how long does it take.

    ``indexed`` — both normalized name columns have an index (name_index_layout); ``plan`` — what SQLite does
    for one branch of the indexed search («SEARCH … USING INDEX», never «SCAN»); then two searches the coach
    makes, with their time against the budget (src/tools/_sqlite_budget.py)."""
    import time

    path = db_path or TWIC_DB_PATH
    conn = sqlite3.connect(path)
    try:
        layout = name_index_layout(conn)
        plan = ""
        if layout["normalized"]:
            plan = "; ".join(r[3] for r in conn.execute(
                "EXPLAIN QUERY PLAN SELECT id FROM games WHERE white_name_normalized GLOB ? AND +date >= ?",
                ("carlsen*", "2026")))
    finally:
        conn.close()
    out = {"db": path, "indexed": layout["indexed"], "indexes": layout["indexes"], "plan": plan}
    for label, kwargs in (("Carlsen", {"player": "Carlsen"}),
                          ("Синдаров — Накамура 2026", {"player": "Синдаров", "opponent": "Накамура",
                                                        "year_min": 2026, "year_max": 2026})):
        start = time.monotonic()
        try:
            rows = search_master_games(db_path=path, limit=5, **kwargs)
            found = f"{len(rows)} games" + (f", newest {rows[0]['date']} id {rows[0]['id']}" if rows else "")
        except sqlite3.OperationalError as exc:
            found = "timeout" if is_timeout(exc) else f"error: {exc}"
        out[label] = f"{found}, {time.monotonic() - start:.2f} s"
    return out


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
        "find_games_by_position. With show=true it also puts the game on the board in front of the student "
        "to step through: set it when the student asks to load, show or open the game. The result spells out "
        "every move: tell the game from that list."
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

    The file is read as bytes: TWIC holds Latin-1 names, and a strict text read
    raised on any such byte near the game, so the coach got no moves for games the
    database page shows (live site, 02.11). A game's bytes are UTF-8 or, when they
    are not, Latin-1 — «Hübner», not «H\ufffdbner», which the model then
    retold as «Штольберг» for Ståhlberg (review 03.11).
    """
    try:
        with open(PGN_FILE_PATH, "rb") as f:
            f.seek(offset)
            data = f.read(length)
    except (OSError, ValueError) as e:
        logger.warning("Could not read PGN file: %s", e)
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


_TAG = re.compile(r'^\[(\w+)\s+"((?:[^"\\]|\\.)*)"\]\s*$', re.MULTILINE)


def _fix_names(headers: dict, pgn_text: str) -> dict:
    """The index's names where it stored a replacement character («St\ufffdhlberg»): the game's own tags."""
    if not any("\ufffd" in str(headers.get(k) or "") for k in ("White", "Black", "Event")):
        return headers
    tags = dict(_TAG.findall(pgn_text or ""))
    fixed = dict(headers)
    for key in ("White", "Black", "Event"):
        if "\ufffd" in str(fixed.get(key) or "") and tags.get(key) and "\ufffd" not in tags[key]:
            fixed[key] = tags[key]
    return fixed


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
    headers = _fix_names(headers, pgn_text)
    if pgn_text and not pgn_text.startswith("["):
        tag_block = "".join(f'[{k} "{v}"]\n' for k, v in headers.items() if v)
        pgn_text = f"{tag_block}\n{pgn_text}"

    if not pgn_text:
        # No moves to show: say so, so the coach never invents the score.
        return {"error": f"The moves of game {game_id} could not be read.", "headers": headers}
    out = {"id": game_id, "pgn": pgn_text, "headers": headers}
    moves = move_list(pgn_text)
    if moves:
        out["moves"] = moves
        out["note"] = MOVES_NOTE
    return out


# The coach retold a loaded game from memory: «на 4-м ходу белые взяли пешку на e4» for 4...Nxe4, «33.d8=Q+» for
# d8=R+, «Хюбнер забрал ладью» for a knight (review 03.11). Every move, told as what it is.
MOVES_NOTE = ("moves: every move of this game in order — who moved, which piece, what it took. Tell the game only from "
              "this list and the headers: a move, a capture or a side you cannot read here was not in this game.")
_PIECE = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook",
          chess.QUEEN: "queen", chess.KING: "king"}


def move_list(pgn_text: str) -> list:
    """«4...Nxe4 Black knight f6 takes pawn e4» for every move of the game's main line ([] if it does not parse)."""
    import io

    import chess.pgn

    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
    except Exception:  # noqa: BLE001 — a score that does not parse gets no list
        return []
    if game is None:
        return []
    board = game.board()
    out = []
    for move in game.mainline_moves():
        try:
            san = board.san(move)
        except (AssertionError, ValueError):
            break
        side = "White" if board.turn == chess.WHITE else "Black"
        num = f"{board.fullmove_number}{'.' if board.turn == chess.WHITE else '...'}"
        piece = board.piece_at(move.from_square)
        words = f"{side} {_PIECE.get(piece.piece_type, '?') if piece else '?'} {chess.square_name(move.from_square)}"
        if board.is_castling(move):
            words = f"{side} castles {'kingside' if board.is_kingside_castling(move) else 'queenside'}"
        elif board.is_capture(move):
            victim_sq = move.to_square if not board.is_en_passant(move) else move.to_square + (-8 if board.turn else 8)
            victim = board.piece_at(victim_sq)
            words += f" takes {_PIECE.get(victim.piece_type, '?') if victim else 'pawn'} {chess.square_name(move.to_square)}"
        else:
            words += f" to {chess.square_name(move.to_square)}"
        if move.promotion:
            words += f", promotes to {_PIECE[move.promotion]}"
        board.push(move)
        if board.is_checkmate():
            words += ", checkmate"
        elif board.is_check():
            words += ", check"
        out.append(f"{num}{san} {words}")
    return out


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
    action = {"type": "load_pgn", "pgn": pgn}
    if result.get("id"):
        action["game_id"] = result["id"]  # the board remembers it is this database game (src/sessions.py)
    return {**result, "board_actions": [action]}


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
