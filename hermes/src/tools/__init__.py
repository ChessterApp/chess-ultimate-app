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

    return loaded


def get_registered_tools() -> list[str]:
    """Return names of all tools registered under the chess toolset."""
    return registry.get_tool_names_for_toolset(TOOLSET)
