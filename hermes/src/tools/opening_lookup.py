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
from src.session_persistence import SessionLoadError

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


def lookup_opening(question: str, fen: Optional[str] = None, pgn: Optional[str] = None,
                   show: Optional[bool] = None) -> dict:
    plan = plan_opening(question or "", fen, pgn, show=show)
    if plan is None:
        return {"found": False}
    out = {
        "found": True,
        "name": plan.name,
        "eco": plan.eco,
        "line": plan.pgn,
        "loaded": plan.load,
        "about_the_board": plan.relative,
        "hidden": plan.hidden,
        "note": plan.block,
    }
    if plan.load:
        out["board_actions"] = [{"type": "load_pgn", "pgn": plan.pgn}]
    elif plan.hidden:
        # The line's final position, looked at on the hidden board (the text turn does this itself;
        # the voice coach and the model's own calls get it here).
        try:
            from src import config
            from src.question_position import hidden_note_block
            from src.voice_engine_note import engine_note

            note = engine_note(plan.final_fen, movetime_ms=config.COACH_HIDDEN_BOARD_MOVETIME_MS) if config.COACH_HIDDEN_BOARD else None
            if note and note.get("note"):
                out["hidden_board"] = {"fen": plan.final_fen, "engine": note["note"],
                                       "note": hidden_note_block(note["note"], f"the final position of the {plan.name} line")}
        except Exception:  # noqa: BLE001 — the engine is a bonus on top of the book
            pass
    try:
        # The programme's own lesson on the opening (steps 5 and 7 of «Ступени»: Scotch, Italian, Two Knights,
        # Petrov, Four Knights, Spanish, King's Gambit): the coach teaches it in the programme's words.
        from src.lesson_texts import book_for_words, book_title_extra, book_view

        rec = book_for_words(question or "")
        if rec is not None and book_title_extra(rec, question or "") <= 1 and int(rec.get("docx_step") or 0) >= 4:
            view = book_view(rec)
            out["programme_lesson"] = {
                "step": view["step"], "lesson": view["lesson"], "title": view["title"], "text": view["text"][:2500],
                "parts": view["parts"], "game_pgn": view.get("pgn"),
                "how_to_use": "The student's own programme («Ступени»): explain the opening in its words and name it as theirs.",
            }
    except Exception:  # noqa: BLE001 — the book is a bonus
        pass
    return out


def _handle_lookup_opening(args: dict, **kwargs) -> str:
    # The student's own position stays on the board unless they ask to see the line
    # (src/question_position.show_on_board; the session comes with the call — text and voice alike).
    show = None
    fen, pgn = args.get("fen"), args.get("pgn")
    try:
        from src.question_position import show_on_board
        from src.sessions import session_for

        session = session_for(kwargs)
        if session is not None:
            board = session.get_board(session.active_board_id)
            if board is not None:
                show = show_on_board(str(kwargs.get("student_message") or args.get("question") or ""), board)
                fen, pgn = fen or board.fen, pgn or (board.pgn or None)
    except SessionLoadError:
        raise  # the board is unknown, not absent (28.10)
    except Exception:  # noqa: BLE001 — without a session the old rule holds
        show = None
    result = lookup_opening(question=args.get("question") or "", fen=fen, pgn=pgn, show=show)
    return json.dumps(result, ensure_ascii=False)


registry.register(
    name="lookup_opening",
    toolset="chess",
    schema=LOOKUP_OPENING_SCHEMA,
    handler=_handle_lookup_opening,
    description="The opening a question names: its book line, defences and facts.",
    emoji="📖",
)
