"""Unit tests for Tool 8: get_player_profile."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.tools.player_profiles import get_player_profile

LICHESS_PROFILE = {
    "username": "DrNykterstein",
    "perfs": {
        "bullet": {"rating": 3200, "games": 5000},
        "blitz": {"rating": 3100, "games": 10000},
        "rapid": {"rating": 2900, "games": 500},
    },
    "count": {"all": 15500},
    "createdAt": 1500000000000,  # 2017-07-14
}

CHESSCOM_PROFILE = {
    "username": "MagnusCarlsen",
    "joined": 1300000000,  # 2011-03-13
    "total_games": 8000,
}

CHESSCOM_STATS = {
    "chess_bullet": {"last": {"rating": 3200}},
    "chess_blitz": {"last": {"rating": 3100}},
    "chess_rapid": {"last": {"rating": 2900}},
}


def _make_mock_response(data, status=200):
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.status_code = status
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.unit
def test_lichess_profile():
    """Lichess profile returns correct structure."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(LICHESS_PROFILE)

    result = get_player_profile("DrNykterstein", "lichess", client=client)

    assert result["username"] == "DrNykterstein"
    assert result["platform"] == "lichess"
    assert "bullet" in result["ratings"]
    assert result["ratings"]["bullet"] == 3200
    assert result["games_played"] == 15500


@pytest.mark.unit
def test_chesscom_profile():
    """Chess.com profile returns correct structure."""
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(CHESSCOM_PROFILE),
        _make_mock_response(CHESSCOM_STATS),
    ]

    result = get_player_profile("MagnusCarlsen", "chesscom", client=client)

    assert result["username"] == "MagnusCarlsen"
    assert result["platform"] == "chesscom"
    assert "blitz" in result["ratings"]
    assert result["ratings"]["blitz"] == 3100


@pytest.mark.unit
def test_lichess_not_found():
    """Nonexistent Lichess user returns error."""
    client = MagicMock()
    resp = _make_mock_response({}, status=404)
    client.get.return_value = resp

    result = get_player_profile("nonexistent_user_xyz", "lichess", client=client)
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.unit
def test_chesscom_not_found():
    """Nonexistent Chess.com user returns error."""
    client = MagicMock()
    resp = _make_mock_response({}, status=404)
    client.get.return_value = resp

    result = get_player_profile("nonexistent_user_xyz", "chesscom", client=client)
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.unit
def test_unknown_platform():
    """Unknown platform returns error."""
    result = get_player_profile("user", "fics")
    assert "error" in result
    assert "Unknown platform" in result["error"]


@pytest.mark.unit
def test_lichess_ratings_schema():
    """Lichess ratings contain expected time controls."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(LICHESS_PROFILE)

    result = get_player_profile("DrNykterstein", "lichess", client=client)
    ratings = result["ratings"]

    assert "bullet" in ratings
    assert "blitz" in ratings
    assert "rapid" in ratings
    assert all(isinstance(v, int) for v in ratings.values())


@pytest.mark.unit
def test_member_since_format():
    """member_since is in YYYY-MM-DD format."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(LICHESS_PROFILE)

    result = get_player_profile("DrNykterstein", "lichess", client=client)
    assert result["member_since"]  # non-empty
    parts = result["member_since"].split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # year


@pytest.mark.unit
def test_result_schema():
    """Profile result has all required fields."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(LICHESS_PROFILE)

    result = get_player_profile("DrNykterstein", "lichess", client=client)
    required = {"username", "platform", "ratings", "games_played", "member_since"}
    assert required.issubset(result.keys())
