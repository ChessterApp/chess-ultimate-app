"""Chess Coach tool auto-discovery and registration.

Scans this directory for modules containing tool functions
and registers them with the Hermes ToolRegistry.
"""

import importlib
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


def _tell_the_board() -> None:
    """What a tool put on the board is what the model hears, for every tool (src/board_truth.py)."""
    from src.board_truth import board_truth

    for name in get_registered_tools():
        entry = registry.get_entry(name)
        if entry is None or getattr(entry.handler, "_tells_board", False):
            continue

        def handler(args, _inner=entry.handler, **kwargs):
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
