"""Unit tests for platform linking: link_platform and sync_ratings."""

from unittest.mock import MagicMock, patch

import pytest

from src.platform_linking import link_platform, sync_ratings

LICHESS_PROFILE = {
    "username": "testuser",
    "platform": "lichess",
    "ratings": {"bullet": 1500, "blitz": 1600, "rapid": 1700},
    "games_played": 1000,
    "member_since": "2020-01-01",
}

CHESSCOM_PROFILE = {
    "username": "testuser",
    "platform": "chesscom",
    "ratings": {"bullet": 1400, "blitz": 1500, "rapid": 1600},
    "games_played": 800,
    "member_since": "2019-06-15",
}


@pytest.mark.unit
def test_link_lichess_success():
    """Successfully links a Lichess account."""
    with patch("src.platform_linking.get_player_profile", return_value=LICHESS_PROFILE):
        with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
            result = link_platform(
                user_id="user123",
                platform="lichess",
                username="testuser",
                supabase_url="https://fake.supabase.co",
                supabase_key="fake-key",
            )

    assert result["status"] == "linked"
    assert result["platform"] == "lichess"
    assert result["username"] == "testuser"
    assert result["ratings"]["rapid"] == 1700
    mock_upsert.assert_called_once()


@pytest.mark.unit
def test_link_chesscom_success():
    """Successfully links a Chess.com account."""
    with patch("src.platform_linking.get_player_profile", return_value=CHESSCOM_PROFILE):
        with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
            result = link_platform(
                user_id="user123",
                platform="chesscom",
                username="testuser",
                supabase_url="https://fake.supabase.co",
                supabase_key="fake-key",
            )

    assert result["status"] == "linked"
    assert result["platform"] == "chesscom"
    mock_upsert.assert_called_once()
    upsert_data = mock_upsert.call_args[0][1]
    assert upsert_data["chesscom_username"] == "testuser"


@pytest.mark.unit
def test_link_unknown_platform():
    """Unknown platform returns error."""
    result = link_platform(user_id="u1", platform="fics", username="test")
    assert "error" in result
    assert "Unknown platform" in result["error"]


@pytest.mark.unit
def test_link_user_not_found():
    """Nonexistent user returns verification error."""
    error_profile = {"error": "User 'nonexistent' not found on Lichess."}
    with patch("src.platform_linking.get_player_profile", return_value=error_profile):
        result = link_platform(user_id="u1", platform="lichess", username="nonexistent")

    assert "error" in result
    assert "Cannot verify" in result["error"]


@pytest.mark.unit
def test_link_stores_correct_column():
    """Lichess link stores lichess_username column."""
    with patch("src.platform_linking.get_player_profile", return_value=LICHESS_PROFILE):
        with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
            link_platform(
                user_id="user123",
                platform="lichess",
                username="testuser",
                supabase_url="https://fake.supabase.co",
                supabase_key="fake-key",
            )

    upsert_data = mock_upsert.call_args[0][1]
    assert upsert_data["lichess_username"] == "testuser"


@pytest.mark.unit
def test_sync_ratings_both_platforms():
    """Sync fetches ratings from both linked platforms."""
    chess_profile = {
        "user_id": "user123",
        "lichess_username": "lichess_user",
        "chesscom_username": "chesscom_user",
    }

    with patch("src.platform_linking._get_chess_profile", return_value=chess_profile):
        with patch("src.platform_linking.get_player_profile") as mock_profile:
            mock_profile.side_effect = [LICHESS_PROFILE, CHESSCOM_PROFILE]
            with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
                result = sync_ratings(
                    user_id="user123",
                    supabase_url="https://fake.supabase.co",
                    supabase_key="fake-key",
                )

    assert result["synced"] is True
    assert "lichess" in result["ratings"]
    assert "chesscom" in result["ratings"]
    assert result["ratings"]["lichess"]["rapid"] == 1700
    assert result["ratings"]["chesscom"]["rapid"] == 1600
    mock_upsert.assert_called_once()


@pytest.mark.unit
def test_sync_ratings_lichess_only():
    """Sync works with only Lichess linked."""
    chess_profile = {
        "user_id": "user123",
        "lichess_username": "lichess_user",
        "chesscom_username": None,
    }

    with patch("src.platform_linking._get_chess_profile", return_value=chess_profile):
        with patch("src.platform_linking.get_player_profile", return_value=LICHESS_PROFILE):
            with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
                result = sync_ratings(
                    user_id="user123",
                    supabase_url="https://fake.supabase.co",
                    supabase_key="fake-key",
                )

    assert result["synced"] is True
    assert "lichess" in result["ratings"]
    assert "chesscom" not in result["ratings"]


@pytest.mark.unit
def test_sync_ratings_no_linked_platforms():
    """Returns error when no platforms are linked."""
    with patch("src.platform_linking._get_chess_profile", return_value=None):
        result = sync_ratings(user_id="user123")

    assert "error" in result
    assert "No linked platforms" in result["error"]


@pytest.mark.unit
def test_sync_ratings_updates_rapid_rating():
    """Sync updates lichess_rapid_rating in the profile."""
    chess_profile = {
        "user_id": "user123",
        "lichess_username": "lichess_user",
    }

    with patch("src.platform_linking._get_chess_profile", return_value=chess_profile):
        with patch("src.platform_linking.get_player_profile", return_value=LICHESS_PROFILE):
            with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
                sync_ratings(
                    user_id="user123",
                    supabase_url="https://fake.supabase.co",
                    supabase_key="fake-key",
                )

    upsert_data = mock_upsert.call_args[0][1]
    assert upsert_data["lichess_rapid_rating"] == 1700


@pytest.mark.unit
def test_sync_ratings_handles_profile_error():
    """Sync handles platform API errors gracefully."""
    chess_profile = {
        "user_id": "user123",
        "lichess_username": "baduser",
    }
    error_profile = {"error": "Lichess API error: 500"}

    with patch("src.platform_linking._get_chess_profile", return_value=chess_profile):
        with patch("src.platform_linking.get_player_profile", return_value=error_profile):
            with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
                result = sync_ratings(user_id="user123")

    # No ratings to sync, but not an error
    assert result["synced"] is True
    assert result["ratings"] == {}
    mock_upsert.assert_not_called()
