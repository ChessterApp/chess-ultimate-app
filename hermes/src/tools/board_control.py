"""Board control tool — emits BoardAction commands for the frontend.

The AI calls this tool to manipulate the chess board UI (set positions,
draw arrows, highlight squares, navigate moves, etc.).
"""

import json
import logging

from pydantic import ValidationError
from tools.registry import registry

from src.board_protocol import (
    ActionType,
    ClearBoard,
    DrawArrows,
    FlipBoard,
    HighlightSquares,
    LoadPgn,
    Navigate,
    SetFen,
    SetPuzzle,
)

logger = logging.getLogger(__name__)

BOARD_CONTROL_SCHEMA = {
    "name": "board_control",
    "description": (
        "Control the chess board UI. Use this to set positions (FEN), "
        "load games (PGN), set puzzles, draw arrows, highlight squares, "
        "navigate through moves, flip the board, or clear it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "enum": [e.value for e in ActionType],
                "description": "The type of board action to perform.",
            },
            "fen": {
                "type": "string",
                "description": "FEN string (for set_fen, set_puzzle).",
            },
            "pgn": {
                "type": "string",
                "description": "PGN string (for load_pgn).",
            },
            "solution": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Solution moves in SAN (for set_puzzle).",
            },
            "arrows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "brush": {"type": "string", "default": "green"},
                    },
                    "required": ["from", "to"],
                },
                "description": "Arrows to draw (for draw_arrows).",
            },
            "squares": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Squares to highlight (for highlight_squares).",
            },
            "color": {
                "type": "string",
                "description": "Color for highlights (default: yellow).",
            },
            "direction": {
                "type": "string",
                "enum": ["first", "prev", "next", "last"],
                "description": "Navigation direction (for navigate).",
            },
        },
        "required": ["action_type"],
    },
}

# Map action types to their model constructors
_ACTION_BUILDERS = {
    ActionType.SET_FEN: lambda args: SetFen(fen=args["fen"]),
    ActionType.LOAD_PGN: lambda args: LoadPgn(pgn=args["pgn"]),
    ActionType.SET_PUZZLE: lambda args: SetPuzzle(
        fen=args["fen"],
        solution=args.get("solution", []),
    ),
    ActionType.DRAW_ARROWS: lambda args: DrawArrows(arrows=args["arrows"]),
    ActionType.HIGHLIGHT_SQUARES: lambda args: HighlightSquares(
        squares=args["squares"],
        color=args.get("color", "yellow"),
    ),
    ActionType.NAVIGATE: lambda args: Navigate(direction=args["direction"]),
    ActionType.FLIP_BOARD: lambda args: FlipBoard(),
    ActionType.CLEAR_BOARD: lambda args: ClearBoard(),
}


def build_board_action(action_type: str, params: dict) -> dict:
    """Construct and validate a BoardAction, returning its dict representation."""
    try:
        atype = ActionType(action_type)
    except ValueError:
        return {"error": f"Unknown action type: {action_type}"}

    builder = _ACTION_BUILDERS[atype]
    try:
        action = builder(params)
        return action.model_dump(by_alias=True)
    except (ValidationError, KeyError, ValueError) as exc:
        return {"error": str(exc)}


def _handle_board_control(args: dict, **kwargs) -> str:
    """Handler for the Hermes tool registry."""
    action_type = args.get("action_type", "")
    result = build_board_action(action_type, args)
    return json.dumps(result, indent=2)


registry.register(
    name="board_control",
    toolset="chess",
    schema=BOARD_CONTROL_SCHEMA,
    handler=_handle_board_control,
    description="Control the chess board UI (set positions, draw arrows, navigate, etc.).",
    emoji="♟️",
)
