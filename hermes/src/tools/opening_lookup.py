"""Tool: lookup_opening — the opening a question names, for the voice coach.

The text coach gets this before the model is called (src/opening_knowledge.py,
the opening pre-step). The voice coach runs in the browser on Gemini Live and
has only tools, so the site calls this one when the student's words contain
an opening name («что такое жареная печень», «как из этой позиции перейти в
защиту двух коней») — exactly as it calls get_topic for a concept — puts the
line on the board from the ``board_actions`` and hands the model the ``note``.

The result mirrors the text pre-step: the book line, the defences of the
side that meets it, verified facts of its final position; and, when the
question is about the position on the board, a comparison instead of a
replaced board.
"""

from __future__ import annotations

import json
from typing import Optional

from tools.registry import registry

from src.opening_knowledge import plan_opening

LOOKUP_OPENING_SCHEMA = {
    "name": "lookup_opening",
    "description": (
        "The opening the student's words name (Russian, Kazakh, English and slang names: "
        "«жареная печень», «сицилианка», «детский мат», Fried Liver): its ECO-book line, "
        "the defences against it and verified facts of its final position. Puts the line "
        "on the board unless the question is about the position already there."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The student's words, as said."},
            "fen": {"type": "string", "description": "The position on the board now (optional)."},
            "pgn": {"type": "string", "description": "The moves on the board now, if known (optional)."},
        },
        "required": ["question"],
    },
}


def lookup_opening(question: str, fen: Optional[str] = None, pgn: Optional[str] = None) -> dict:
    plan = plan_opening(question or "", fen, pgn)
    if plan is None:
        return {"found": False}
    out = {
        "found": True,
        "name": plan.name,
        "eco": plan.eco,
        "line": plan.pgn,
        "loaded": plan.load,
        "about_the_board": plan.relative,
        "note": plan.block,
    }
    if plan.load:
        out["board_actions"] = [{"type": "load_pgn", "pgn": plan.pgn}]
    return out


def _handle_lookup_opening(args: dict, **kwargs) -> str:
    result = lookup_opening(
        question=args.get("question") or "", fen=args.get("fen"), pgn=args.get("pgn")
    )
    return json.dumps(result, ensure_ascii=False)


registry.register(
    name="lookup_opening",
    toolset="chess",
    schema=LOOKUP_OPENING_SCHEMA,
    handler=_handle_lookup_opening,
    description="The opening a question names: its book line, defences and facts.",
    emoji="📖",
)
