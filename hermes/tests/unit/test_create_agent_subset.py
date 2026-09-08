"""Unit tests for tool-subsetting on the text-coach agent path.

Verifies that ``server._create_agent`` reduces ``agent.tools`` (and keeps
``agent.valid_tool_names`` consistent) when ``COACH_TOOL_SUBSET`` is on and a
raw user query is supplied, and is otherwise byte-identical to today.

``run_agent.AIAgent`` is patched with a lightweight fake so no network/model is
needed — the fake exposes the same ``.tools`` (OpenAI format) and
``.valid_tool_names`` attributes the real agent holds after construction.
"""

from unittest.mock import patch

import pytest

from src import config, server
from src.tool_selector import CORE_TOOLS


def _oai(name, description=""):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
    }


FULL_TOOLS = [
    _oai("board_control", "Control the chess board UI, set positions (FEN)."),
    _oai("analyze_position", "Analyze a chess position using Stockfish."),
    _oai("check_moves", "Verify candidate move legality in a position (engine-free)."),
    _oai("get_opening_stats", "Statistics about a chess opening by ECO code or name."),
    _oai("search_master_games", "Search the master games database by player or event."),
    _oai("get_player_profile", "Get a player's profile ratings from Lichess or Chess.com."),
    _oai("weakness_tracker", "Detect patterns of weakness from a user's recent games."),
    _oai("search_web", "Search the web for chess-related information."),
    _oai("training_recommender", "Suggest personalized training recommendations."),
    _oai("get_user_games", "Get a user's recent games from their profile."),
    _oai("find_critical_moments", "Find turning points in a game move-by-move."),
]


class _FakeAgent:
    """Mimics the post-construction shape of run_agent.AIAgent."""

    def __init__(self, *args, **kwargs):
        # Fresh copies so tests don't share mutable state.
        self.tools = [dict(t) for t in FULL_TOOLS]
        self.valid_tool_names = {t["function"]["name"] for t in self.tools}


@pytest.fixture(autouse=True)
def _fake_aiagent():
    with patch("run_agent.AIAgent", _FakeAgent):
        yield


@pytest.mark.unit
class TestCreateAgentSubset:
    def test_flag_off_leaves_tools_untouched(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_TOOL_SUBSET", False)
        agent = server._create_agent(
            model="m", system_prompt="s", user_query="what opening vs the Sicilian"
        )
        assert len(agent.tools) == len(FULL_TOOLS)
        assert agent.valid_tool_names == {t["function"]["name"] for t in FULL_TOOLS}

    def test_flag_on_with_query_subsets_and_keeps_core(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_TOOL_SUBSET", True)
        monkeypatch.setattr(config, "COACH_TOOL_SUBSET_TOPK", 3)
        agent = server._create_agent(
            model="m", system_prompt="s", user_query="what opening vs the Sicilian"
        )
        names = {t["function"]["name"] for t in agent.tools}
        assert len(agent.tools) < len(FULL_TOOLS)
        assert len(agent.tools) <= 3 + len(CORE_TOOLS)
        for core in CORE_TOOLS:
            assert core in names
        # Consistency invariant: validator matches the reduced tool set exactly.
        assert agent.valid_tool_names == names

    def test_flag_on_no_query_leaves_tools_untouched(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_TOOL_SUBSET", True)
        agent = server._create_agent(
            model="m", system_prompt="s", user_query=None
        )
        assert len(agent.tools) == len(FULL_TOOLS)
        assert agent.valid_tool_names == {t["function"]["name"] for t in FULL_TOOLS}
