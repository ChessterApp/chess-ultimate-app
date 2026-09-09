"""Unit tests for get_game_insights + the 'Recent games' prompt digest (CL
Phase 1, Slice 2)."""

from unittest.mock import MagicMock, patch

import pytest

from src.tools.game_insights import (
    GAMES_BLOCK_CAP,
    get_game_insights,
    load_recent_insights,
    render_games_block,
)


def _mock_httpx_get(data):
    mock_resp = MagicMock()
    mock_resp.json.return_value = data
    mock_resp.raise_for_status = MagicMock()
    return MagicMock(return_value=mock_resp)


_ROWS = [
    {
        "game_ref": "g1",
        "opening": "Sicilian Defense",
        "result": "0-1",
        "accuracy": 82.0,
        "blunders": [{"classification": "blunder", "theme": "middlegame", "move_played": "Qd2"}],
        "summary": "…",
    },
    {
        "game_ref": "g2",
        "opening": "Ruy Lopez",
        "result": "1-0",
        "accuracy": 91.0,
        "blunders": [],
        "summary": "…",
    },
]


@pytest.mark.unit
class TestGetGameInsights:
    def test_returns_rows(self):
        with patch("src.tools.user_data.httpx.get", _mock_httpx_get(_ROWS)):
            result = get_game_insights(
                user_id="u1",
                supabase_url="https://fake.supabase.co",
                supabase_key="fake-key",
            )
        assert len(result) == 2
        assert result[0]["opening"] == "Sicilian Defense"

    def test_opening_filter_passed_as_ilike(self):
        mock_get = _mock_httpx_get([_ROWS[0]])
        with patch("src.tools.user_data.httpx.get", mock_get):
            get_game_insights(
                user_id="u1",
                opening="Sicilian",
                supabase_url="https://fake.supabase.co",
                supabase_key="fake-key",
            )
        params = mock_get.call_args.kwargs["params"]
        assert params["opening"] == "ilike.*Sicilian*"
        assert params["order"] == "created_at.desc"

    def test_limit_is_clamped(self):
        mock_get = _mock_httpx_get([])
        with patch("src.tools.user_data.httpx.get", mock_get):
            get_game_insights(
                user_id="u1",
                limit=999,
                supabase_url="https://fake.supabase.co",
                supabase_key="fake-key",
            )
        assert mock_get.call_args.kwargs["params"]["limit"] == "20"

    def test_no_config_returns_empty(self):
        result = get_game_insights(user_id="u1", supabase_url="", supabase_key="")
        assert result == []

    def test_load_recent_failopen(self):
        with patch("src.tools.game_insights.get_game_insights", side_effect=RuntimeError("db down")):
            assert load_recent_insights("u1") == []


@pytest.mark.unit
class TestRenderGamesBlock:
    def test_empty_returns_empty_string(self):
        assert render_games_block([]) == ""
        assert render_games_block(None) == ""

    def test_renders_opening_result_and_theme(self):
        block = render_games_block(_ROWS)
        assert "## Recent games" in block
        assert "Sicilian Defense" in block
        assert "result 0-1" in block
        assert "blunder in middlegame" in block
        # A game with no blunders still renders opening + result.
        assert "Ruy Lopez" in block

    def test_hard_capped(self):
        big = [
            {"opening": "X" * 500, "result": "1-0", "blunders": []}
            for _ in range(10)
        ]
        block = render_games_block(big)
        assert len(block) <= GAMES_BLOCK_CAP

    def test_malformed_rows_are_skipped(self):
        rows = [
            "not a dict",
            None,
            {"opening": None, "result": None, "blunders": "not-json"},
            {"opening": "Caro-Kann", "result": "½-½", "blunders": [{"classification": "mistake"}]},
        ]
        block = render_games_block(rows)
        assert "Caro-Kann" in block
        assert "mistake" in block

    def test_blunders_as_json_string(self):
        rows = [{
            "opening": "French",
            "result": "0-1",
            "blunders": '[{"classification": "blunder", "theme": "endgame"}]',
        }]
        block = render_games_block(rows)
        assert "blunder in endgame" in block
