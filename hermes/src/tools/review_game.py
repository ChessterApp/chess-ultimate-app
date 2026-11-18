"""Tool: review_game — a game's critical moments, ready to talk through, for the voice coach.

The text coach gets this before the model is called: a message with a game
in it has the game loaded and its critical moments found by the server while
the reaction streams (coach_chat, COACH_REVIEW_PRESTEP). The voice coach has
only tools, so the site calls this one when the student asks for a review of
the game on the board («разбери мою партию», «где я ошибся») and hands the
model the ``note`` — the same block the text coach gets.
"""

from __future__ import annotations

import json
from typing import Optional

from tools.registry import registry

from src.prompt_builder import review_block
from src.tools.critical_moments import find_critical_moments

REVIEW_GAME_SCHEMA = {
    "name": "review_game",
    "description": (
        "The critical moments of a game (the student's or any PGN): where the evaluation "
        "turned, the move played, the better move and its line, with the position before "
        "each. Use it to review a game instead of judging moves yourself. The game must "
        "already be on the board; this tool does not load it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pgn": {"type": "string", "description": "The game's moves (PGN or a move list)."},
            "side": {"type": "string", "description": "Which side the student played: white or black (optional)."},
        },
        "required": ["pgn"],
    },
}


def review_game(pgn: str, side: Optional[str] = None) -> dict:
    result = find_critical_moments(pgn)
    if not isinstance(result, dict) or "error" in result:
        return {"error": (result or {}).get("error", "could not review the game") if isinstance(result, dict) else "could not review the game"}
    # The card the student gets with this review (src/tool_summaries.build_summary builds the same one from the
    # result): the note names its moments and their count, so the coach's words and the card are one fact (18.11).
    from src.review_moments import build_review_moments

    note = review_block(result, card=build_review_moments(result, pgn=pgn, side=side))
    if side:
        note += f"\nThe student played {side}: judge the student's moves, and the opponent's only where they matter."
    return {
        "moments": result.get("critical_moments") or [],
        "total_moves": result.get("total_moves"),
        "note": note,
    }


def _handle_review_game(args: dict, **kwargs) -> str:
    return json.dumps(review_game(pgn=args.get("pgn") or "", side=args.get("side")), ensure_ascii=False)


registry.register(
    name="review_game",
    toolset="chess",
    schema=REVIEW_GAME_SCHEMA,
    handler=_handle_review_game,
    description="A game's critical moments, ready to talk through.",
    emoji="🔍",
)
