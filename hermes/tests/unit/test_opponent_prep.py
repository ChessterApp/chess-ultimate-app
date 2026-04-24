"""Unit tests for opponent_prep tool."""

from unittest.mock import patch

import pytest

from src.tools.opponent_prep import opponent_prep


MOCK_PROFILE = {
    "username": "testplayer",
    "platform": "lichess",
    "ratings": {"blitz": 2100, "rapid": 2200},
    "games_played": 500,
    "member_since": "2020-01-01",
}


@pytest.mark.unit
def test_basic_prep(fake_twic_db):
    """Returns opponent prep with profile and openings."""
    with patch("src.tools.opponent_prep.get_player_profile", return_value=MOCK_PROFILE):
        result = opponent_prep(
            opponent_username="testplayer",
            platform="lichess",
            user_color="white",
            conn=fake_twic_db,
        )

    assert "error" not in result
    assert result["opponent"]["username"] == "testplayer"
    assert "opponent_openings" in result
    assert "suggested_preparation" in result


@pytest.mark.unit
def test_profile_error():
    """Profile fetch error is propagated."""
    with patch("src.tools.opponent_prep.get_player_profile",
               return_value={"error": "User not found"}):
        result = opponent_prep(
            opponent_username="nonexistent",
            platform="lichess",
            user_color="white",
        )

    assert "error" in result


@pytest.mark.unit
def test_opponent_color_white(fake_twic_db):
    """When user plays black, opponent's white openings are analyzed."""
    with patch("src.tools.opponent_prep.get_player_profile", return_value=MOCK_PROFILE):
        result = opponent_prep(
            opponent_username="Carlsen",
            platform="lichess",
            user_color="black",
            conn=fake_twic_db,
        )

    assert "error" not in result
    assert "opponent_openings" in result


@pytest.mark.unit
def test_weakness_detection(fake_twic_db):
    """Weaknesses list is included in result."""
    with patch("src.tools.opponent_prep.get_player_profile", return_value=MOCK_PROFILE):
        result = opponent_prep(
            opponent_username="Carlsen",
            platform="lichess",
            user_color="white",
            conn=fake_twic_db,
        )

    assert "weaknesses" in result
    assert isinstance(result["weaknesses"], list)
