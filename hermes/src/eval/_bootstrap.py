"""Make ``src.tools.*`` importable without the hermes-agent framework.

``src/tools/__init__.py`` does ``from tools.registry import registry`` at import
time. In the deployment/dev venv the real framework provides ``tools.registry``;
in CI or a bare offline checkout it does not. The eval harness only needs the
pure ``analyze_position`` / ``check_moves`` functions — not tool registration —
so when the real registry is missing we install a no-op stub. When it IS present
we leave it untouched, so nothing about runtime behavior changes.
"""

import sys
import types


def ensure_tools_importable() -> None:
    """Install a stub ``tools.registry`` iff the real one can't be imported."""
    try:  # real framework present (deployment / dev venv) — do nothing.
        import tools.registry  # noqa: F401
        return
    except Exception:
        pass

    if "tools.registry" in sys.modules:
        return

    class _StubRegistry:
        """No-op stand-in: swallows the module-level register() calls."""

        def register(self, *args, **kwargs):
            return None

        def get_tool_names_for_toolset(self, *args, **kwargs):
            return []

    registry_mod = types.ModuleType("tools.registry")
    registry_mod.registry = _StubRegistry()

    tools_pkg = sys.modules.get("tools")
    if tools_pkg is None:
        tools_pkg = types.ModuleType("tools")
        tools_pkg.__path__ = []  # mark as a package
        sys.modules["tools"] = tools_pkg
    tools_pkg.registry = registry_mod
    sys.modules["tools.registry"] = registry_mod
