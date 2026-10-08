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
    return loaded


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
