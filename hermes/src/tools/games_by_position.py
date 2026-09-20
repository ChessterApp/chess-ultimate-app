"""Tool: find_games_by_position — master games that reached a given position.

Uses the TWIC ``game_positions`` index (one row per game per ply, keyed by a
board hash) that the site's Database page already queries; the coach could
only search games by player/event/ECO before. Popular positions (the start
position, 1.e4 …) have millions of rows, so the lookup takes a bounded pool
from the hash index and sorts that in Python, and every statement runs under
a 3-second interrupt.
"""

import json
import logging
import os
import sqlite3
import time
from typing import Optional

import chess

from tools.registry import registry

logger = logging.getLogger(__name__)

TWIC_DB_PATH = os.environ.get(
    "TWIC_DB_PATH",
    "/root/chess-app/backend/data/twic/games_index.db",
)

DEFAULT_LIMIT = 10
MAX_LIMIT = 30
POOL_SIZE = 600
QUERY_TIMEOUT_S = 3.0

SCHEMA = {
    "name": "find_games_by_position",
    "description": (
        "Find master games (TWIC database) that reached a given position. Returns "
        "the strongest games first with players, ratings, result, event, ECO, and "
        "the ply at which the position occurred, plus how many games in total "
        "reached it. Use get_game_pgn with a returned id to load a game on the board."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fen": {"type": "string", "description": "FEN of the position to look up."},
            "limit": {"type": "integer", "description": f"Max games (default {DEFAULT_LIMIT}, max {MAX_LIMIT})."},
            "result": {
                "type": "string",
                "enum": ["1-0", "0-1", "1/2-1/2"],
                "description": "Optional: only games with this result.",
            },
            "min_avg_elo": {
                "type": "integer",
                "description": "Optional: only games where both players average at least this rating.",
            },
        },
        "required": ["fen"],
    },
}


def position_hash(fen: str) -> str:
    """Board hash used by game_positions: pieces, side, castling; en passant normalised to '-'."""
    parts = fen.split()
    if len(parts) < 4:
        parts = (parts + ["w", "-", "-"])[:4]
    parts[3] = "-"
    return " ".join(parts[:4])


def _stats_hash(fen: str) -> str:
    """Board hash used by move_stats (pieces + side only)."""
    parts = fen.split()
    return f"{parts[0]} {parts[1]} - -" if len(parts) >= 2 else fen


def _install_timeout(conn: sqlite3.Connection, seconds: float) -> None:
    started = time.monotonic()

    def _handler():
        return 1 if time.monotonic() - started > seconds else 0

    conn.set_progress_handler(_handler, 10_000)


def find_games_by_position(
    fen: str,
    limit: int = DEFAULT_LIMIT,
    result: Optional[str] = None,
    min_avg_elo: Optional[int] = None,
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    try:
        board = chess.Board(fen)
    except ValueError:
        return {"error": f"Invalid FEN: {fen!r}"}
    fen = board.fen()
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))

    own_conn = False
    if conn is None:
        path = db_path or TWIC_DB_PATH
        if not os.path.exists(path):
            return {"error": "Master games database is not available on this server."}
        conn = sqlite3.connect(path)
        own_conn = True
    conn.row_factory = sqlite3.Row

    try:
        _install_timeout(conn, QUERY_TIMEOUT_S)
        has_index = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='game_positions'"
        ).fetchone()
        if not has_index:
            return {"error": "Position index is not built yet.", "games": [], "total": 0}

        # Total games that reached the position: move_stats keeps that count.
        total = None
        try:
            row = conn.execute(
                "SELECT SUM(games) FROM move_stats WHERE board_hash = ?", (_stats_hash(fen),)
            ).fetchone()
            if row and row[0]:
                total = int(row[0])
        except sqlite3.Error:
            total = None

        try:
            pool = conn.execute(
                "SELECT game_id, ply FROM game_positions WHERE board_hash = ? LIMIT ?",
                (position_hash(fen), POOL_SIZE),
            ).fetchall()
        except sqlite3.OperationalError as exc:  # interrupted by the timeout
            logger.warning("find_games_by_position: pool query aborted: %s", exc)
            return {"error": "The position lookup timed out; try a less common position.",
                    "games": [], "total": total}

        if not pool:
            return {"fen": fen, "total": total or 0, "games": []}
        if total is None:
            total = len(pool) if len(pool) < POOL_SIZE else f"{POOL_SIZE}+"

        ply_by_game = {r["game_id"]: r["ply"] for r in pool}
        marks = ",".join("?" * len(ply_by_game))
        where = [f"id IN ({marks})"]
        params: list = list(ply_by_game)
        if result in ("1-0", "0-1", "1/2-1/2"):
            where.append("result = ?")
            params.append(result)
        if min_avg_elo:
            where.append("(COALESCE(white_elo, 0) + COALESCE(black_elo, 0)) / 2 >= ?")
            params.append(int(min_avg_elo))
        rows = conn.execute(
            "SELECT id, white_name, black_name, white_elo, black_elo, result, date, "
            "event, eco, opening FROM games WHERE " + " AND ".join(where) +
            " ORDER BY COALESCE(white_elo, 0) + COALESCE(black_elo, 0) DESC, date DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    finally:
        if own_conn:
            conn.close()

    games = [
        {
            "id": r["id"],
            "white": r["white_name"],
            "black": r["black_name"],
            "white_elo": r["white_elo"],
            "black_elo": r["black_elo"],
            "result": r["result"],
            "date": r["date"],
            "event": r["event"],
            "eco": r["eco"],
            "opening": r["opening"],
            "ply": ply_by_game.get(r["id"]),
        }
        for r in rows
    ]
    return {"fen": fen, "total": total, "games": games}


def _handle(args: dict, **kwargs) -> str:
    out = find_games_by_position(
        fen=args.get("fen", ""),
        limit=args.get("limit", DEFAULT_LIMIT),
        result=args.get("result"),
        min_avg_elo=args.get("min_avg_elo"),
    )
    return json.dumps(out, indent=2, ensure_ascii=False)


registry.register(
    name="find_games_by_position",
    toolset="chess",
    schema=SCHEMA,
    handler=_handle,
    description="Find master games that reached a given position.",
    emoji="🔎",
)
