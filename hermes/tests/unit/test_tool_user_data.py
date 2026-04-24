"""Unit tests for Tool 6: get_user_repertoire."""

from unittest.mock import MagicMock, patch

import pytest

from src.tools.user_data import get_user_repertoire


def _mock_httpx_get(data):
    """Create a mock httpx.get that returns canned data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = data
    mock_resp.raise_for_status = MagicMock()
    return MagicMock(return_value=mock_resp)


@pytest.mark.unit
def test_returns_repertoire(fake_supabase):
    """Returns repertoire entries for a valid user."""
    with patch("src.tools.user_data.httpx.get", _mock_httpx_get(fake_supabase["repertoire"])):
        result = get_user_repertoire(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert len(result) == 3
    assert result[0]["eco"] == "C50"


@pytest.mark.unit
def test_filter_by_color(fake_supabase):
    """Color filter is passed to the API query."""
    mock_get = _mock_httpx_get([fake_supabase["repertoire"][0]])
    with patch("src.tools.user_data.httpx.get", mock_get):
        result = get_user_repertoire(
            user_id="user123",
            color="white",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    # Verify the color param was passed
    call_args = mock_get.call_args
    params = call_args.kwargs.get("params") or call_args[1].get("params", {})
    assert params.get("color") == "eq.white"


@pytest.mark.unit
def test_empty_for_unknown_user(fake_supabase):
    """Unknown user returns empty list."""
    with patch("src.tools.user_data.httpx.get", _mock_httpx_get([])):
        result = get_user_repertoire(
            user_id="nonexistent",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert result == []


@pytest.mark.unit
def test_no_supabase_config():
    """Missing Supabase config returns empty list."""
    result = get_user_repertoire(
        user_id="user123",
        supabase_url="",
        supabase_key="",
    )
    assert result == []


@pytest.mark.unit
def test_result_schema(fake_supabase):
    """Each repertoire entry has expected fields."""
    with patch("src.tools.user_data.httpx.get", _mock_httpx_get(fake_supabase["repertoire"])):
        result = get_user_repertoire(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    for entry in result:
        assert "user_id" in entry
        assert "color" in entry
        assert "eco" in entry
        assert "opening" in entry
