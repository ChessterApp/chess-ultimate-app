"""Integration test: full game import flow with mocked external APIs."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.tools.external_apis import lichess_game_import, chesscom_game_import
from src.platform_linking import link_platform, sync_ratings

LICHESS_PGN = """[Event "Rated Rapid game"]
[Site "https://lichess.org/abc12345"]
[White "opponent"]
[Black "testplayer"]
[Result "0-1"]
[UTCDate "2024.05.01"]

1. e4 e5 2. Nf3 Nc6 0-1
"""

CHESSCOM_GAMES = {
    "games": [
        {
            "url": "https://www.chess.com/game/live/999",
            "pgn": "1. d4 d5 2. c4 e6 1-0",
            "white": {"username": "testplayer", "result": "win"},
            "black": {"username": "other", "result": "lose"},
            "end_time": 1714521600,
            "rules": "chess",
        }
    ]
}

LICHESS_PROFILE = {
    "username": "testplayer",
    "platform": "lichess",
    "ratings": {"rapid": 1650, "blitz": 1700},
    "games_played": 500,
    "member_since": "2021-01-01",
}

CHESSCOM_PROFILE = {
    "username": "testplayer",
    "platform": "chesscom",
    "ratings": {"rapid": 1600, "blitz": 1550},
    "games_played": 300,
    "member_since": "2020-06-01",
}


def _make_http_response(text="", json_data=None, status=200):
    resp = MagicMock()
    resp.text = text
    resp.json.return_value = json_data or {}
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


def _make_supabase_response(data=None, status=200):
    resp = MagicMock()
    resp.json.return_value = data or []
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.integration
def test_full_lichess_import_and_link_flow():
    """End-to-end: link Lichess account, import games, sync ratings."""
    supabase_posts = []

    def capture_post(table, rows, **kwargs):
        supabase_posts.append({"table": table, "rows": rows})
        return len(rows)

    # Step 1: Link the account
    with patch("src.platform_linking.get_player_profile", return_value=LICHESS_PROFILE):
        with patch("src.platform_linking._upsert_chess_profile"):
            link_result = link_platform(
                user_id="user42",
                platform="lichess",
                username="testplayer",
                supabase_url="https://fake.supabase.co",
                supabase_key="key",
            )

    assert link_result["status"] == "linked"

    # Step 2: Import games
    client = MagicMock()
    client.get.return_value = _make_http_response(text=LICHESS_PGN)

    with patch("src.tools.external_apis._supabase_post", side_effect=capture_post):
        import_result = lichess_game_import(
            "testplayer",
            user_id="user42",
            supabase_url="https://fake.supabase.co",
            supabase_key="key",
            client=client,
        )

    assert import_result["imported"] == 1
    assert len(supabase_posts) == 1
    assert supabase_posts[0]["table"] == "user_games"
    assert supabase_posts[0]["rows"][0]["source"] == "lichess"

    # Step 3: Sync ratings
    chess_profile = {
        "user_id": "user42",
        "lichess_username": "testplayer",
    }
    with patch("src.platform_linking._get_chess_profile", return_value=chess_profile):
        with patch("src.platform_linking.get_player_profile", return_value=LICHESS_PROFILE):
            with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
                sync_result = sync_ratings(
                    user_id="user42",
                    supabase_url="https://fake.supabase.co",
                    supabase_key="key",
                )

    assert sync_result["synced"] is True
    assert sync_result["ratings"]["lichess"]["rapid"] == 1650


@pytest.mark.integration
def test_full_chesscom_import_flow():
    """End-to-end: import Chess.com games with storage."""
    supabase_posts = []

    def capture_post(table, rows, **kwargs):
        supabase_posts.append({"table": table, "rows": rows})
        return len(rows)

    client = MagicMock()
    client.get.side_effect = [
        _make_http_response(json_data=CHESSCOM_GAMES),
        _make_http_response(json_data={"games": []}),
    ]

    with patch("src.tools.external_apis._supabase_post", side_effect=capture_post):
        result = chesscom_game_import(
            "testplayer",
            user_id="user42",
            supabase_url="https://fake.supabase.co",
            supabase_key="key",
            client=client,
        )

    assert result["imported"] == 1
    assert result["source"] == "chesscom"
    assert len(supabase_posts) == 1
    assert supabase_posts[0]["rows"][0]["white"] == "testplayer"


@pytest.mark.integration
def test_dual_platform_sync():
    """Sync ratings from both Lichess and Chess.com simultaneously."""
    chess_profile = {
        "user_id": "user42",
        "lichess_username": "testplayer",
        "chesscom_username": "testplayer",
    }

    with patch("src.platform_linking._get_chess_profile", return_value=chess_profile):
        with patch("src.platform_linking.get_player_profile") as mock_profile:
            mock_profile.side_effect = [LICHESS_PROFILE, CHESSCOM_PROFILE]
            with patch("src.platform_linking._upsert_chess_profile") as mock_upsert:
                result = sync_ratings(
                    user_id="user42",
                    supabase_url="https://fake.supabase.co",
                    supabase_key="key",
                )

    assert result["synced"] is True
    assert result["ratings"]["lichess"]["rapid"] == 1650
    assert result["ratings"]["chesscom"]["rapid"] == 1600

    upsert_data = mock_upsert.call_args[0][1]
    assert upsert_data["lichess_rapid_rating"] == 1650
    assert upsert_data["chesscom_rapid_rating"] == 1600
