"""The student's finished games against the coach, as rows of their games (tester's report 19.11).

«Разбор последней партии» offered DrNykterstein – Night-King96, a game the tester had opened in the Database section
the day before, right after they had played the coach: a game with the coach lives only as a board of its session
(``coach_boards``, kind ``game``), never in ``user_games``, and the plan read ``user_games`` alone. The plan now reads
both and offers the latest game; the card's review asks for the game by ``coach-game:<board id>`` and is told it as
the student's own, from their side (``game_state.student_color``).

The rows look like ``user_games`` rows (``id``, ``white``, ``black``, ``pgn``, ``source`` = ``coach_game``,
``created_at`` = when the game ended) so the plan and src/game_owner.py read them the same way. A game against the
coach has no player names and the plan is asked for without a language: ``white`` / ``black`` stay empty and the
card's title is the game's opening and result («1.e4 c5 2.Nf3 … 0-1»), the same in every language.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import chess
import chess.pgn

logger = logging.getLogger(__name__)

PREFIX = "coach-game:"
_BOARD_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
_SELECT = "id,pgn,game_state,updated_at,coach_sessions!inner(user_id)"
TITLE_MOVES = 4  # full moves in the card's title


def is_coach_game_id(game_id) -> bool:
    return isinstance(game_id, str) and game_id.startswith(PREFIX)


def _iso(value) -> Optional[str]:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return value if isinstance(value, str) and value else None


def title(pgn: Optional[str], result: Optional[str]) -> str:
    """«1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 … 1-0»: the opening of the game and its result."""
    words: list[str] = []
    try:
        game = chess.pgn.read_game(io.StringIO(pgn or ""))
        board = game.board() if game else chess.Board()
        moves = list(game.mainline_moves()) if game else []
        for i, move in enumerate(moves[: TITLE_MOVES * 2]):
            san = board.san(move)
            if board.turn == chess.WHITE:
                words.append(f"{board.fullmove_number}.{san}")
            elif i == 0:
                words.append(f"{board.fullmove_number}…{san}")
            else:
                words.append(san)
            board.push(move)
        if len(moves) > TITLE_MOVES * 2:
            words.append("…")
    except Exception:  # noqa: BLE001 — a title is never worth a failed plan
        logger.debug("coach game title failed", exc_info=True)
    if result and result != "*":
        words.append(result)
    return " ".join(words)


def _row(board: dict) -> Optional[dict]:
    """A coach_boards row of a finished game as a row of the student's games."""
    state = board.get("game_state") if isinstance(board.get("game_state"), dict) else {}
    pgn = board.get("pgn")
    if not board.get("id") or not isinstance(pgn, str) or not pgn.strip() or state.get("status") != "finished":
        return None
    return {
        "id": PREFIX + str(board["id"]),
        "source": "coach_game",
        "white": "",
        "black": "",
        "pgn": pgn,
        "result": state.get("result"),
        "student_color": state.get("student_color"),
        "title": title(pgn, state.get("result")),
        "created_at": _iso(state.get("finished_at")) or _iso(board.get("updated_at")),
    }


def recent(user_id: Optional[str], limit: int = 3) -> Optional[list]:
    """The student's latest finished games against the coach, newest first; None when they could not be read."""
    if not user_id:
        return []
    from src.tools.user_data import _supabase_query

    rows = _supabase_query("coach_boards", {
        "select": _SELECT,
        "coach_sessions.user_id": f"eq.{user_id}",
        "kind": "eq.game",
        "game_state->>status": "eq.finished",
        "order": "updated_at.desc",
        "limit": str(max(1, int(limit))),
    })
    if rows is None:
        return None
    return [r for r in (_row(b) for b in rows if isinstance(b, dict)) if r]


def game(user_id: Optional[str], game_id: Optional[str]) -> Optional[dict]:
    """The student's finished game against the coach *game_id* (``coach-game:<board id>``), or None — never another
    student's: the board is read through its session's user."""
    if not user_id or not is_coach_game_id(game_id):
        return None
    board_id = game_id[len(PREFIX):]
    if not _BOARD_ID_RE.match(board_id):
        return None
    from src.tools.user_data import _supabase_query

    rows = _supabase_query("coach_boards", {
        "select": _SELECT,
        "id": f"eq.{board_id}",
        "coach_sessions.user_id": f"eq.{user_id}",
        "limit": "1",
    })
    return _row(rows[0]) if rows and isinstance(rows[0], dict) else None


def latest_first(*groups) -> list:
    """The rows of *groups* (each a list or None), newest first by ``created_at``; rows without a time keep their
    order after the timed ones."""
    rows = [r for g in groups if isinstance(g, list) for r in g if isinstance(r, dict)]

    def when(r):
        try:
            t = datetime.fromisoformat(str(r.get("created_at")).replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    timed = sorted((r for r in rows if when(r)), key=when, reverse=True)
    return timed + [r for r in rows if not when(r)]
