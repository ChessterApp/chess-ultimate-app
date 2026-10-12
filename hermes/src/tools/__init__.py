"""Chess Coach tool auto-discovery and registration.

Scans this directory for modules containing tool functions
and registers them with the Hermes ToolRegistry.
"""

import importlib
from contextlib import contextmanager
import logging
import pkgutil
from pathlib import Path

from tools.registry import registry

logger = logging.getLogger(__name__)

TOOLSET = "chess"

# Tool modules that live outside this package (they also serve non-tool code).
# Imported here so the toolset is complete from startup — otherwise
# link_platform / sync_ratings appeared only after the first text chat
# imported the module, and a voice session minted before it lacked them.
EXTRA_TOOL_MODULES = ("src.platform_linking",)


def discover_and_register() -> list[str]:
    """Scan src/tools/ for modules and import them to trigger registration.

    Each tool module registers itself at import time via registry.register().
    Returns list of loaded module names.
    """
    package_dir = Path(__file__).parent
    loaded = []

    for finder, module_name, is_pkg in pkgutil.iter_modules([str(package_dir)]):
        if module_name.startswith("_"):
            continue
        full_name = f"src.tools.{module_name}"
        try:
            importlib.import_module(full_name)
            loaded.append(module_name)
            logger.info("Loaded tool module: %s", module_name)
        except Exception:
            logger.exception("Failed to load tool module: %s", module_name)

    for full_name in EXTRA_TOOL_MODULES:
        try:
            importlib.import_module(full_name)
            loaded.append(full_name.rsplit(".", 1)[-1])
        except Exception:
            logger.exception("Failed to load tool module: %s", full_name)

    _repair_fen_args()
    _hint_on_error()
    _tell_the_board()
    return loaded


# What the model is told when a tool fails (2026-10-08): about 45 kinds of errors came back as a bare
# «error», and when get_game_pgn failed on production (07.10) the coach described the game from memory,
# with its moves wrong.
ERROR_HINT = ("The tool failed. Tell the student in one short sentence that you could not get it this time; "
              "never describe what it would have returned (a game, its moves, a position, a lesson, a puzzle) "
              "from memory.")


def _hint_on_error() -> None:
    import json

    for name in get_registered_tools():
        entry = registry.get_entry(name)
        if entry is None or getattr(entry.handler, "_hints_errors", False):
            continue

        def handler(args, _inner=entry.handler, **kwargs):
            result = _inner(args, **kwargs)
            if isinstance(result, str) and result.lstrip().startswith("{") and '"error"' in result:
                try:
                    data = json.loads(result)
                except ValueError:
                    return result
                if isinstance(data, dict) and data.get("error") and not data.get("hint"):
                    data["hint"] = ERROR_HINT
                    return json.dumps(data, ensure_ascii=False)
            return result

        handler._hints_errors = True
        handler._repairs_fen = getattr(entry.handler, "_repairs_fen", False)
        entry.handler = handler


# The coach session of a text turn, by the task id the server gives the agent (src/server.py,
# _chat_in_session). The framework calls the tools with task_id and user_task, never the session
# (2026-10-12): the board lock, the board truth and the game looked for ``session_id`` in kwargs and
# found none in the text coach — only the server's filter of the streamed actions held the board.
_turn_sessions: dict = {}


@contextmanager
def turn_session(task_id: str, session_id: str, student_message: str = "", game_step: bool = False):
    """While the agent runs a turn under *task_id*, its tools see the coach session *session_id*, the
    student's own words and whether the server already started the game / played the move."""
    _turn_sessions[task_id] = {"session_id": session_id, "student_message": student_message,
                               "turn_game_step": game_step}
    try:
        yield
    finally:
        _turn_sessions.pop(task_id, None)


def _tell_the_board() -> None:
    """Every tool sees its coach session, and what it put on the board is what the model hears
    (src/board_truth.py)."""
    from src.board_truth import board_truth

    for name in get_registered_tools():
        entry = registry.get_entry(name)
        if entry is None or getattr(entry.handler, "_tells_board", False):
            continue

        def handler(args, _inner=entry.handler, **kwargs):
            if not kwargs.get("session_id"):
                turn = _turn_sessions.get(kwargs.get("task_id") or "")
                if turn:
                    kwargs = {**kwargs, **turn}
            return board_truth(_inner(args, **kwargs), kwargs)

        handler._tells_board = True
        handler._hints_errors = getattr(entry.handler, "_hints_errors", False)
        handler._repairs_fen = getattr(entry.handler, "_repairs_fen", False)
        entry.handler = handler


def _repair_fen_args() -> None:
    """Every chess tool gets its ``fen`` with castling/en-passant flags its position allows.

    The model passes the lesson's FEN as it is; 16 of 187 site puzzles have
    castling rights their kings and rooks no longer allow, and the engine tools
    answered «Invalid FEN» to them (production, 2026-10-07).
    """
    from src.fen_repair import repair_fen

    for name in get_registered_tools():
        entry = registry.get_entry(name)
        if entry is None or getattr(entry.handler, "_repairs_fen", False):
            continue
        props = ((entry.schema or {}).get("parameters") or {}).get("properties") or {}
        if "fen" not in props:
            continue

        def handler(args, _inner=entry.handler, **kwargs):
            if isinstance(args, dict) and isinstance(args.get("fen"), str):
                args = {**args, "fen": repair_fen(args["fen"])}
            return _inner(args, **kwargs)

        handler._repairs_fen = True
        entry.handler = handler


def get_registered_tools() -> list[str]:
    """Return names of all tools registered under the chess toolset."""
    return registry.get_tool_names_for_toolset(TOOLSET)
