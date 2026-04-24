"""Unit tests for Tool 7: get_user_games."""

from unittest.mock import MagicMock, patch

import pytest

from src.tools.user_data import get_user_games


def _mock_httpx_get(data):
    """Create a mock httpx.get that returns canned data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = data
    mock_resp.raise_for_status = MagicMock()
    return MagicMock(return_value=mock_resp)


@pytest.mark.unit
def test_returns_games(fake_supabase):
    """Returns games for a valid user."""
    with patch("src.tools.user_data.httpx.get", _mock_httpx_get(fake_supabase["user_games"])):
        result = get_user_games(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert len(result) == 3


@pytest.mark.unit
def test_limit_parameter(fake_supabase):
    """Limit parameter is passed to API."""
    mock_get = _mock_httpx_get(fake_supabase["user_games"][:1])
    with patch("src.tools.user_data.httpx.get", mock_get):
        get_user_games(
            user_id="user123",
            limit=1,
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    call_args = mock_get.call_args
    params = call_args.kwargs.get("params") or call_args[1].get("params", {})
    assert params.get("limit") == "1"


@pytest.mark.unit
def test_empty_for_unknown_user(fake_supabase):
    """Unknown user returns empty list."""
    with patch("src.tools.user_data.httpx.get", _mock_httpx_get([])):
        result = get_user_games(
            user_id="nonexistent",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert result == []


@pytest.mark.unit
def test_ordered_by_date(fake_supabase):
    """Request includes order by played_at descending."""
    mock_get = _mock_httpx_get(fake_supabase["user_games"])
    with patch("src.tools.user_data.httpx.get", mock_get):
        get_user_games(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    call_args = mock_get.call_args
    params = call_args.kwargs.get("params") or call_args[1].get("params", {})
    assert params.get("order") == "played_at.desc"


@pytest.mark.unit
def test_result_schema(fake_supabase):
    """Each game entry has expected fields."""
    with patch("src.tools.user_data.httpx.get", _mock_httpx_get(fake_supabase["user_games"])):
        result = get_user_games(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    for game in result:
        assert "user_id" in game
        assert "result" in game
        assert "pgn" in game
