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


def wrap_response(message: str, tool_results: list[Any] = None) -> dict:
    """Wrap an agent response into a ResponseEnvelope dict.

    Args:
        message: The text response from the agent.
        tool_results: Optional list of raw tool call result strings.

    Returns:
        Dict with 'message' and 'board_actions' keys.
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
    return envelope.model_dump()
