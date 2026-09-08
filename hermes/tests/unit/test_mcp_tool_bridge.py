"""Unit tests for MCP tools in build_tool_declarations (Phase 2).

With COACH_MCP_ENABLED off, declarations are byte-identical to the chess-only
behavior (no ``mcp-`` tools). With it on, tools registered under an ``mcp-*``
toolset are included, and Phase-1 tool-subsetting still applies to the combined
set.
"""

from unittest.mock import patch

import pytest

from src import config, tool_bridge
from src.tool_bridge import build_tool_declarations
from src.tool_selector import CORE_TOOLS

MCP_TOOL_NAME = "mcp-engine.stockfish_multipv"
MCP_TOOLSET = "mcp-engine"

_MCP_SCHEMA = {
    "name": MCP_TOOL_NAME,
    "description": "Analyse a FEN with local Stockfish multipv (MCP engine).",
    "parameters": {
        "type": "object",
        "properties": {"fen": {"type": "string"}},
        "required": ["fen"],
    },
}


def _register_mcp_tool():
    tool_bridge.registry.register(
        name=MCP_TOOL_NAME,
        toolset=MCP_TOOLSET,
        schema=_MCP_SCHEMA,
        handler=lambda args: "{}",
    )


@pytest.fixture
def mcp_tool_registered():
    _register_mcp_tool()
    try:
        yield MCP_TOOL_NAME
    finally:
        tool_bridge.registry.deregister(MCP_TOOL_NAME)


@pytest.mark.unit
class TestMcpDeclarations:
    def test_flag_off_excludes_mcp_tools(self, mcp_tool_registered):
        with patch.object(config, "COACH_MCP_ENABLED", False):
            decls = build_tool_declarations()
        names = {d["name"] for d in decls}
        assert MCP_TOOL_NAME not in names
        assert "board_control" in names  # native chess tools remain

    def test_flag_on_includes_mcp_tools(self, mcp_tool_registered):
        with patch.object(config, "COACH_MCP_ENABLED", True):
            decls = build_tool_declarations()
        names = {d["name"] for d in decls}
        assert MCP_TOOL_NAME in names
        assert "board_control" in names  # native chess tools remain
        # The MCP tool declaration is well-formed Gemini shape.
        mcp_decl = next(d for d in decls if d["name"] == MCP_TOOL_NAME)
        assert mcp_decl["description"]
        assert mcp_decl["parameters"]["type"] == "object"

    def test_byte_identical_with_flag_off(self):
        # Registering an mcp-* tool must not change the flag-off output at all.
        with patch.object(config, "COACH_MCP_ENABLED", False):
            baseline = build_tool_declarations()
            _register_mcp_tool()
            try:
                with_mcp = build_tool_declarations()
            finally:
                tool_bridge.registry.deregister(MCP_TOOL_NAME)
        assert with_mcp == baseline

    def test_subset_applies_to_combined_set(self, mcp_tool_registered):
        # With subsetting on, the combined (chess + mcp) set is ranked and
        # trimmed; a stockfish query keeps the MCP engine tool while the total
        # stays bounded by topk + core (proving it ran over the combined set).
        with patch.object(config, "COACH_MCP_ENABLED", True), patch.object(
            config, "COACH_TOOL_SUBSET", True
        ):
            decls = build_tool_declarations(
                query="run stockfish multipv analysis on this position", topk=5
            )
        names = {d["name"] for d in decls}
        assert MCP_TOOL_NAME in names
        # core + topk (5) — far fewer than the full combined toolset.
        assert len(decls) <= 5 + len(CORE_TOOLS)
