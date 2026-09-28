"""Tool: compare_variations — Stockfish multipv analysis comparing top lines."""

import json
import logging

import chess

from tools.registry import registry
from src.tools.stockfish import DEFAULT_DEPTH, MAX_DEPTH, _bounded_int, analyze_position

logger = logging.getLogger(__name__)

COMPARE_SCHEMA = {
    "name": "compare_variations",
    "description": (
        "Compare the top N variations in a position using Stockfish multipv analysis. "
        "Shows each line's moves, evaluation score, and mate-in if applicable."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fen": {
                "type": "string",
                "description": "FEN string of the position to analyze.",
            },
            "num_lines": {
                "type": "integer",
                "description": "Number of lines to compare (default 3).",
            },
            "depth": {
                "type": "integer",
                "description": f"Search depth; leave unset (default {DEFAULT_DEPTH}, max {MAX_DEPTH}).",
            },
        },
        "required": ["fen"],
    },
}

DEFAULT_NUM_LINES = 3


def compare_variations(
    fen: str,
    num_lines: int = DEFAULT_NUM_LINES,
    depth: int = DEFAULT_DEPTH,
    stockfish_path: str = None,
) -> dict:
    """Run Stockfish multipv analysis to compare top lines side-by-side."""
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            return {"error": f"Invalid FEN: {fen}"}
    except (ValueError, IndexError):
        return {"error": f"Invalid FEN: {fen}"}

    num_lines = max(1, min(num_lines, 10))
    depth = max(1, min(depth, MAX_DEPTH))

    kwargs = {"fen": fen, "depth": depth, "multipv": num_lines}
    if stockfish_path:
        kwargs["stockfish_path"] = stockfish_path

    result = analyze_position(**kwargs)

    if "error" in result:
        return result

    variations = []
    for line in result.get("lines", []):
        entry = {
            "moves": line.get("pv", ""),
            "score": line.get("score", 0.0),
        }
        if "mate_in" in line:
            entry["mate_in"] = line["mate_in"]
        variations.append(entry)

    return {
        "fen": fen,
        "depth": depth,
        "variations": variations,
    }


def _handle_compare_variations(args: dict, **kwargs) -> str:
    result = compare_variations(
        fen=args.get("fen", ""),
        num_lines=_bounded_int(args.get("num_lines"), DEFAULT_NUM_LINES, 1, 10),
        depth=_bounded_int(args.get("depth"), DEFAULT_DEPTH, 1, MAX_DEPTH),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="compare_variations",
    toolset="chess",
    schema=COMPARE_SCHEMA,
    handler=_handle_compare_variations,
    description="Compare top engine lines for a position side-by-side.",
    emoji="⚖️",
)
