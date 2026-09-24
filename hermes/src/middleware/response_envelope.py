"""Response envelope middleware.

Wraps AI agent responses to separate text from board actions.
Board actions are extracted from tool call results and packaged
into a clean JSON envelope for the frontend.
"""

import json
import logging
import re
from typing import Any

from src.board_protocol import ActionType, ResponseEnvelope

logger = logging.getLogger(__name__)

# Pattern to detect JSON board actions in tool output
_BOARD_ACTION_TYPES = {e.value for e in ActionType}


def extract_board_actions(text: str) -> tuple[str, list[dict]]:
    """Extract board action JSON blocks from agent response text.

    Returns (clean_text, board_actions) where clean_text has the
    JSON blocks removed and board_actions is a list of action dicts.
    """
    board_actions = []
    # Match JSON objects that contain a "type" field with a known action type
    json_pattern = re.compile(r'\{[^{}]*"type"\s*:\s*"[^"]*"[^{}]*\}')

    clean_parts = []
    last_end = 0

    for match in json_pattern.finditer(text):
        try:
            obj = json.loads(match.group())
            if obj.get("type") in _BOARD_ACTION_TYPES:
                board_actions.append(obj)
                clean_parts.append(text[last_end:match.start()])
                last_end = match.end()
                continue
        except (json.JSONDecodeError, TypeError):
            pass

    clean_parts.append(text[last_end:])
    clean_text = "".join(clean_parts).strip()

    return clean_text, board_actions


_GAME_RESULT_REQUIRED_KEYS = {"id", "white_name", "black_name"}
_USER_GAME_REQUIRED_KEYS = {"id", "white", "black", "pgn"}
MAX_GAME_CARDS = 20


def _header(pgn: str, tag: str) -> str:
    import re

    m = re.search(rf'^\[{tag} "([^"]*)"\]', pgn or "", re.M)
    return m.group(1) if m else ""


def _user_game_card(row: dict, source: str) -> dict:
    """One of the student's own / imported games in the card shape the clients
    render for TWIC results, plus ``source`` and the PGN itself (no TWIC fetch)."""
    pgn = row.get("pgn") or ""

    def _elo(key: str, tag: str):
        v = row.get(key)
        if isinstance(v, (int, float)):
            return int(v)
        try:
            return int(_header(pgn, tag))
        except (TypeError, ValueError):
            return None

    return {
        "id": row.get("id"),
        "white_name": row.get("white") or _header(pgn, "White") or "?",
        "black_name": row.get("black") or _header(pgn, "Black") or "?",
        "white_elo": _elo("white_elo", "WhiteElo"),
        "black_elo": _elo("black_elo", "BlackElo"),
        "result": row.get("result") or _header(pgn, "Result") or "*",
        "date": row.get("date") or _header(pgn, "UTCDate") or _header(pgn, "Date") or "",
        "eco": row.get("eco") or _header(pgn, "ECO") or "",
        "opening": row.get("opening_name") or row.get("opening") or _header(pgn, "Opening") or "",
        "event": row.get("event") or _header(pgn, "Event") or "",
        "source": row.get("source") or source,
        "pgn": pgn,
    }


def extract_game_results(tool_results: list[Any]) -> list[dict]:
    """Game cards from tool output, for the clients' clickable game list.

    Three shapes are recognised: a TWIC search (a JSON array of rows with
    id/white_name/black_name — returned as is), the student's saved games
    (``{"games": [rows with id/white/black/pgn]}`` from get_user_games) and a
    Lichess / Chess.com import (``{"last_games": [...]}``). The last two carry
    the PGN in the card and a ``source`` so a client can open them without a
    TWIC lookup.
    """
    if not tool_results:
        return []

    for result in tool_results:
        if not isinstance(result, str):
            continue
        try:
            obj = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            isinstance(obj, list)
            and obj
            and isinstance(obj[0], dict)
            and _GAME_RESULT_REQUIRED_KEYS.issubset(obj[0].keys())
        ):
            return obj
        if isinstance(obj, dict) and "error" not in obj:
            rows = obj.get("games")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict) \
                    and _USER_GAME_REQUIRED_KEYS.issubset(rows[0].keys()):
                return [_user_game_card(r, "user") for r in rows[:MAX_GAME_CARDS] if isinstance(r, dict)]
            rows = obj.get("last_games")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict) and rows[0].get("pgn"):
                source = "chesscom" if "chess.com" in json.dumps(obj).lower() else "lichess"
                cards = []
                for i, r in enumerate(rows[:MAX_GAME_CARDS]):
                    if not isinstance(r, dict):
                        continue
                    card = _user_game_card({**r, "id": r.get("id") or f"{source}-{i}"}, source)
                    cards.append(card)
                return cards
    return []


def wrap_response(message: str, tool_results: list[Any] = None) -> dict:
    """Wrap an agent response into a ResponseEnvelope dict.

    Args:
        message: The text response from the agent.
        tool_results: Optional list of raw tool call result strings.

    Returns:
        Dict with 'message', 'board_actions', and 'game_results' keys.
    """
    board_actions = []

    # Extract from tool results
    if tool_results:
        for result in tool_results:
            if not isinstance(result, str):
                continue
            try:
                obj = json.loads(result)
                if isinstance(obj, dict) and obj.get("type") in _BOARD_ACTION_TYPES:
                    board_actions.append(obj)
            except (json.JSONDecodeError, TypeError):
                pass

    # Also extract any board actions embedded in the message text
    clean_message, embedded_actions = extract_board_actions(message)
    board_actions.extend(embedded_actions)

    envelope = ResponseEnvelope(
        message=clean_message if embedded_actions else message,
        board_actions=board_actions,
    )
    result = envelope.model_dump()
    result["game_results"] = extract_game_results(tool_results)
    return result
