"""Unit tests for semantic tool subsetting (Step 4)."""

import pytest

from src import config, tool_bridge
from src.tool_selector import (
    CORE_TOOLS,
    PANEL_SUPPRESSED_TOOLS,
    select_openai_tool_subset,
    select_tool_subset,
)


def _decl(name, description=""):
    return {"name": name, "description": description, "parameters": {}}


def _oai(name, description=""):
    """OpenAI-format tool dict mirroring what AIAgent puts in `agent.tools`."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {name + "_arg": {"type": "string"}},
            },
        },
    }


SAMPLE = [
    _decl("board_control", "Control the chess board UI, set positions (FEN)."),
    _decl("analyze_position", "Analyze a chess position using Stockfish."),
    _decl("get_opening_stats", "Statistics about a chess opening by ECO code or name."),
    _decl("search_master_games", "Search the master games database by player or event."),
    _decl("get_player_profile", "Get a player's profile ratings from Lichess or Chess.com."),
    _decl("weakness_tracker", "Detect patterns of weakness from a user's recent games."),
    _decl("search_web", "Search the web for chess-related information."),
    _decl("training_recommender", "Suggest personalized training recommendations."),
    _decl("get_user_games", "Get a user's recent games from their profile."),
    _decl("find_critical_moments", "Find turning points in a game move-by-move."),
]


def _names(decls):
    return [d["name"] for d in decls]


@pytest.mark.unit
class TestSelectToolSubset:
    def test_core_always_present(self):
        subset = select_tool_subset(SAMPLE, "tell me about the weather", topk=3)
        for core in CORE_TOOLS:
            assert core in _names(subset)

    def test_length_bounded_by_topk_plus_core(self):
        subset = select_tool_subset(SAMPLE, "opening", topk=3)
        assert len(subset) <= 3 + len(CORE_TOOLS)

    def test_opening_query_surfaces_openings_tool(self):
        subset = select_tool_subset(SAMPLE, "what opening should I use vs the Sicilian", topk=5)
        assert "get_opening_stats" in _names(subset)

    def test_weakness_query_surfaces_weakness_tool(self):
        subset = select_tool_subset(SAMPLE, "what are my recurring weaknesses", topk=5)
        assert "weakness_tracker" in _names(subset)

    def test_panel_mode_suppresses_board_render_tool(self):
        subset = select_tool_subset(SAMPLE, "analyze this position", topk=5, mode="panel")
        for name in PANEL_SUPPRESSED_TOOLS:
            assert name not in _names(subset)
        # A non-suppressed core tool is still present.
        assert "analyze_position" in _names(subset)

    def test_full_mode_keeps_board_control(self):
        subset = select_tool_subset(SAMPLE, "analyze this position", topk=5, mode="full")
        assert "board_control" in _names(subset)

    def test_deterministic(self):
        a = select_tool_subset(SAMPLE, "opening repertoire", topk=4)
        b = select_tool_subset(SAMPLE, "opening repertoire", topk=4)
        assert _names(a) == _names(b)

    def test_board_question_keeps_position_and_engine_tools(self):
        """A board question must retain the board/engine analysis tools.

        With the subset feature now default-ON, the position/engine tools are in
        CORE_TOOLS and must survive selection at the production default TOPK so a
        student asking about the current position always has them available.
        """
        from src.config import COACH_TOOL_SUBSET_TOPK

        subset = _names(
            select_tool_subset(
                SAMPLE,
                "is this position winning for white? what's the best move here",
                topk=COACH_TOOL_SUBSET_TOPK,
            )
        )
        assert "analyze_position" in subset
        assert "board_control" in subset


OAI_SAMPLE = [_oai(d["name"], d["description"]) for d in SAMPLE]


def _oai_names(tools):
    return [t["function"]["name"] for t in tools]


@pytest.mark.unit
class TestSelectOpenAIToolSubset:
    def test_core_always_present(self):
        subset = select_openai_tool_subset(OAI_SAMPLE, "tell me about the weather", topk=3)
        for core in CORE_TOOLS:
            assert core in _oai_names(subset)

    def test_openai_shape_and_parameters_preserved(self):
        subset = select_openai_tool_subset(OAI_SAMPLE, "opening repertoire", topk=5)
        for t in subset:
            assert t["type"] == "function"
            assert t["function"]["name"]
            # Full parameters schema survives the round-trip.
            assert t["function"]["parameters"]["type"] == "object"
            assert t["function"]["parameters"]["properties"]

    def test_object_identity_preserved(self):
        subset = select_openai_tool_subset(OAI_SAMPLE, "opening", topk=5)
        originals = {id(t) for t in OAI_SAMPLE}
        # Every returned dict is one of the original objects (not a copy).
        for t in subset:
            assert id(t) in originals

    def test_length_bounded_by_topk_plus_core(self):
        subset = select_openai_tool_subset(OAI_SAMPLE, "opening", topk=3)
        assert len(subset) <= 3 + len(CORE_TOOLS)

    def test_deterministic(self):
        a = select_openai_tool_subset(OAI_SAMPLE, "opening repertoire", topk=4)
        b = select_openai_tool_subset(OAI_SAMPLE, "opening repertoire", topk=4)
        assert _oai_names(a) == _oai_names(b)

    def test_panel_mode_drops_suppressed(self):
        subset = select_openai_tool_subset(OAI_SAMPLE, "analyze this position", topk=5, mode="panel")
        for name in PANEL_SUPPRESSED_TOOLS:
            assert name not in _oai_names(subset)
        assert "analyze_position" in _oai_names(subset)

    def test_parity_with_flat_selector(self):
        """Same underlying tools -> identical name set as the flat selector."""
        for query, mode in [
            ("what opening should I use vs the Sicilian", "full"),
            ("what are my recurring weaknesses", "full"),
            ("analyze this position", "panel"),
        ]:
            flat = select_tool_subset(SAMPLE, query, topk=5, mode=mode)
            oai = select_openai_tool_subset(OAI_SAMPLE, query, topk=5, mode=mode)
            assert _names(flat) == _oai_names(oai)


@pytest.mark.unit
class TestBuildDeclarationsFlagGate:
    """build_tool_declarations must be byte-identical to today when flag off."""

    def test_flag_off_returns_full_set(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_TOOL_SUBSET", False)
        full = tool_bridge.build_tool_declarations()
        with_query = tool_bridge.build_tool_declarations(query="opening", topk=3)
        assert full == with_query  # query ignored while flag is off

    def test_flag_on_but_no_query_returns_full_set(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_TOOL_SUBSET", True)
        full = tool_bridge.build_tool_declarations()
        assert tool_bridge.build_tool_declarations(query=None) == full

    def test_flag_on_with_query_subsets(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_TOOL_SUBSET", True)
        full = tool_bridge.build_tool_declarations()
        subset = tool_bridge.build_tool_declarations(query="opening", topk=5)
        assert len(subset) < len(full)
        assert len(subset) <= 5 + len(CORE_TOOLS)
        names = [d["name"] for d in subset]
        for core in CORE_TOOLS:
            assert core in names
        assert "get_opening_stats" in names
