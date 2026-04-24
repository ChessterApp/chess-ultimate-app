"""Integration tests verifying Hermes tool registry integration."""

import pytest

from tools.registry import registry
from src.tools import discover_and_register, get_registered_tools


@pytest.mark.integration
def test_auto_discovery_loads_all_modules():
    """discover_and_register() finds and loads all tool modules."""
    loaded = discover_and_register()
    assert "web_search" in loaded
    assert "openings" in loaded
    assert "twic_search" in loaded
    assert "stockfish" in loaded
    assert "user_data" in loaded
    assert "player_profiles" in loaded


@pytest.mark.integration
def test_all_eight_tools_registered():
    """All 8 MVP tools are registered in the Hermes registry."""
    discover_and_register()
    tools = get_registered_tools()
    expected = [
        "search_web",
        "get_opening_stats",
        "search_master_games",
        "get_game_pgn",
        "analyze_position",
        "get_user_repertoire",
        "get_user_games",
        "get_player_profile",
    ]
    for name in expected:
        assert name in tools, f"Tool '{name}' not registered"


@pytest.mark.integration
def test_tool_schemas_valid():
    """Each registered tool has a valid JSON schema."""
    discover_and_register()
    for name in get_registered_tools():
        schema = registry.get_schema(name)
        assert schema is not None, f"Tool '{name}' has no schema"
        assert "function" in schema
        assert "name" in schema["function"]
        assert schema["function"]["name"] == name


@pytest.mark.integration
def test_tool_handlers_callable():
    """Each registered tool has a callable handler."""
    discover_and_register()
    for name in get_registered_tools():
        entry = registry.get_entry(name)
        assert entry is not None
        assert callable(entry.handler)


@pytest.mark.integration
def test_tools_in_chess_toolset():
    """All 8 tools belong to the 'chess' toolset."""
    discover_and_register()
    chess_tools = registry.get_tool_names_for_toolset("chess")
    assert len(chess_tools) >= 8


@pytest.mark.integration
def test_tool_dispatch_returns_string():
    """Dispatching a tool call returns a string result."""
    discover_and_register()
    # Test with get_opening_stats since it doesn't need external services
    result = registry.dispatch("get_opening_stats", {"eco": "B90"})
    assert isinstance(result, str)
    assert "Sicilian" in result or "B90" in result
