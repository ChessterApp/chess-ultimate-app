"""Tool: get_position_stats — Query TWIC move_stats for position frequency and win rates."""

import json
import logging
import os
import sqlite3

import chess

from tools.registry import registry

logger = logging.getLogger(__name__)

TWIC_DB_PATH = os.environ.get(
    "TWIC_DB_PATH",
    "/root/chess-app/backend/data/twic/games_index.db",
)

POSITION_STATS_SCHEMA = {
    "name": "get_position_stats",
    "description": (
        "Query the TWIC database for position statistics: how often a position "
        "occurs, win rates, and top moves played from that position."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fen": {
                "type": "string",
                "description": "FEN string of the position to look up.",
            },
        },
        "required": ["fen"],
    },
}


def _fen_to_board_hash(fen: str) -> str:
    """Convert a full FEN to the board hash used in move_stats (position + side only)."""
    parts = fen.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]} - -"
    return fen


def get_position_stats(
    fen: str,
    db_path: str = None,
    conn: sqlite3.Connection = None,
) -> dict:
    """Query TWIC move_stats table for position frequency and win rates."""
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            return {"error": f"Invalid FEN: {fen}"}
    except (ValueError, IndexError):
        return {"error": f"Invalid FEN: {fen}"}

    board_hash = _fen_to_board_hash(fen)

    own_conn = False
    if conn is None:
        path = db_path or TWIC_DB_PATH
        conn = sqlite3.connect(path)
        own_conn = True

    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT move_san, games, white_wins, draws, black_wins "
            "FROM move_stats WHERE board_hash = ? ORDER BY games DESC",
            (board_hash,),
        )
        rows = cur.fetchall()
    finally:
        if own_conn:
            conn.close()

    if not rows:
        return {
            "fen": fen,
            "total_games": 0,
            "white_wins": 0,
            "draws": 0,
            "black_wins": 0,
            "top_moves": [],
        }

    total_games = sum(r["games"] for r in rows)
    total_white = sum(r["white_wins"] for r in rows)
    total_draws = sum(r["draws"] for r in rows)
    total_black = sum(r["black_wins"] for r in rows)

    top_moves = [
        {
            "move": r["move_san"],
            "games": r["games"],
            "white_wins": r["white_wins"],
            "draws": r["draws"],
            "black_wins": r["black_wins"],
        }
        for r in rows[:10]
    ]

    return {
        "fen": fen,
        "total_games": total_games,
        "white_wins": total_white,
        "draws": total_draws,
        "black_wins": total_black,
        "top_moves": top_moves,
    }


def _handle_get_position_stats(args: dict, **kwargs) -> str:
    result = get_position_stats(fen=args.get("fen", ""))
    return json.dumps(result, indent=2)


registry.register(
    name="get_position_stats",
    toolset="chess",
    schema=POSITION_STATS_SCHEMA,
    handler=_handle_get_position_stats,
    description="Get position frequency and win rates from master database.",
    emoji="📊",
)
