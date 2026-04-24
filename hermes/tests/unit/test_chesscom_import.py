"""Unit tests for chesscom_game_import tool."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.tools.external_apis import chesscom_game_import

SAMPLE_CHESSCOM_RESPONSE = {
    "games": [
        {
            "url": "https://www.chess.com/game/live/111111",
            "pgn": '[Event "Live Chess"]\n\n1. e4 e5 2. Nf3 Nc6 1-0',
            "white": {"username": "testuser", "result": "win"},
            "black": {"username": "opponent1", "result": "lose"},
            "end_time": 1714521600,  # 2024-05-01
            "rules": "chess",
        },
        {
            "url": "https://www.chess.com/game/live/222222",
            "pgn": '[Event "Live Chess"]\n\n1. d4 d5 2. c4 e6 0-1',
            "white": {"username": "opponent2", "result": "lose"},
            "black": {"username": "testuser", "result": "win"},
            "end_time": 1714608000,  # 2024-05-02
            "rules": "chess",
        },
        {
            "url": "https://www.chess.com/game/live/333333",
            "pgn": '[Event "Live Chess"]\n\n1. e4 c5 2. Nf3 d6 1/2-1/2',
            "white": {"username": "testuser", "result": "draw"},
            "black": {"username": "opponent3", "result": "draw"},
            "end_time": 1714694400,  # 2024-05-03
            "rules": "chess",
        },
    ]
}

EMPTY_RESPONSE = {"games": []}


def _make_mock_response(data=None, status=200):
    resp = MagicMock()
    resp.json.return_value = data or {}
    resp.status_code = status
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.unit
def test_import_returns_count():
    """Import returns the count of imported games."""
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(SAMPLE_CHESSCOM_RESPONSE),
        _make_mock_response(EMPTY_RESPONSE),
    ]

    result = chesscom_game_import("testuser", client=client)

    assert result["imported"] == 3
    assert result["source"] == "chesscom"
    assert result["username"] == "testuser"


@pytest.mark.unit
def test_import_results_summary():
    """Import returns results breakdown."""
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(SAMPLE_CHESSCOM_RESPONSE),
        _make_mock_response(EMPTY_RESPONSE),
    ]

    result = chesscom_game_import("testuser", client=client)

    assert result["results"]["1-0"] == 1
    assert result["results"]["0-1"] == 1
    assert result["results"]["1/2-1/2"] == 1


@pytest.mark.unit
def test_import_extracts_usernames():
    """Extracts white/black usernames from game objects."""
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(SAMPLE_CHESSCOM_RESPONSE),
        _make_mock_response(EMPTY_RESPONSE),
    ]

    with patch("src.tools.external_apis._supabase_post") as mock_post:
        mock_post.return_value = 3
        chesscom_game_import("testuser", user_id="u1", client=client,
                             supabase_url="https://fake.supabase.co", supabase_key="k")

    rows = mock_post.call_args[0][1]
    assert rows[0]["white"] == "testuser"
    assert rows[0]["black"] == "opponent1"


@pytest.mark.unit
def test_import_no_games():
    """Returns zero when no games found."""
    client = MagicMock()
    # Both months return empty
    client.get.side_effect = [
        _make_mock_response(EMPTY_RESPONSE),
        _make_mock_response(EMPTY_RESPONSE),
    ]

    result = chesscom_game_import("testuser", client=client)

    assert result["imported"] == 0


@pytest.mark.unit
def test_import_404_skipped():
    """404 on a month archive is skipped, not an error."""
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(status=404),  # current month 404
        _make_mock_response(SAMPLE_CHESSCOM_RESPONSE),  # previous month has data
    ]

    result = chesscom_game_import("testuser", client=client)

    assert result["imported"] == 3


@pytest.mark.unit
def test_import_rate_limited():
    """Returns error on rate limit."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(status=429)

    result = chesscom_game_import("testuser", client=client)

    assert "error" in result
    assert "rate limit" in result["error"].lower()


@pytest.mark.unit
def test_import_user_agent_sent():
    """User-Agent header is sent per Chess.com requirements."""
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(EMPTY_RESPONSE),
        _make_mock_response(EMPTY_RESPONSE),
    ]

    chesscom_game_import("testuser", client=client)

    for call in client.get.call_args_list:
        headers = call.kwargs.get("headers") or call[1].get("headers", {})
        assert "User-Agent" in headers


@pytest.mark.unit
def test_import_stores_in_supabase():
    """When user_id provided, games are POSTed to Supabase."""
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(SAMPLE_CHESSCOM_RESPONSE),
        _make_mock_response(EMPTY_RESPONSE),
    ]

    with patch("src.tools.external_apis._supabase_post") as mock_post:
        mock_post.return_value = 3
        result = chesscom_game_import(
            "testuser",
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
            client=client,
        )

    assert result["imported"] == 3
    mock_post.assert_called_once()
    rows = mock_post.call_args[0][1]
    assert rows[0]["source"] == "chesscom"


@pytest.mark.unit
def test_import_max_games_limit():
    """max_games limits the number of returned games."""
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(SAMPLE_CHESSCOM_RESPONSE),
        _make_mock_response(EMPTY_RESPONSE),
    ]

    result = chesscom_game_import("testuser", max_games=2, client=client)

    assert result["imported"] == 2


@pytest.mark.unit
def test_import_skips_games_without_pgn():
    """Games without PGN are skipped."""
    data = {
        "games": [
            {
                "url": "https://www.chess.com/game/live/111111",
                "pgn": "",
                "white": {"username": "a", "result": "win"},
                "black": {"username": "b", "result": "lose"},
                "end_time": 1714521600,
            },
            {
                "url": "https://www.chess.com/game/live/222222",
                "pgn": "1. e4 e5 1-0",
                "white": {"username": "a", "result": "win"},
                "black": {"username": "b", "result": "lose"},
                "end_time": 1714521600,
            },
        ]
    }
    client = MagicMock()
    client.get.side_effect = [
        _make_mock_response(data),
        _make_mock_response(EMPTY_RESPONSE),
    ]

    result = chesscom_game_import("testuser", client=client)

    assert result["imported"] == 1
