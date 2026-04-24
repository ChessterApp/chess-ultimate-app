"""Unit tests for lichess_game_import tool."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.tools.external_apis import lichess_game_import, _parse_pgn_stream

SAMPLE_LICHESS_PGN = """[Event "Rated Rapid game"]
[Site "https://lichess.org/abc12345"]
[Date "2024.05.01"]
[White "player1"]
[Black "testuser"]
[Result "0-1"]
[UTCDate "2024.05.01"]
[WhiteElo "1500"]
[BlackElo "1600"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 0-1

[Event "Rated Blitz game"]
[Site "https://lichess.org/def67890"]
[Date "2024.05.02"]
[White "testuser"]
[Black "player2"]
[Result "1-0"]
[UTCDate "2024.05.02"]
[WhiteElo "1600"]
[BlackElo "1450"]

1. d4 d5 2. c4 e6 3. Nc3 Nf6 1-0

[Event "Rated Rapid game"]
[Site "https://lichess.org/ghi11111"]
[Date "2024.05.03"]
[White "player3"]
[Black "testuser"]
[Result "1/2-1/2"]
[UTCDate "2024.05.03"]
[WhiteElo "1550"]
[BlackElo "1600"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 1/2-1/2
"""


def _make_mock_response(text="", status=200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.unit
def test_parse_pgn_stream():
    """Parses a PGN stream into individual games."""
    games = _parse_pgn_stream(SAMPLE_LICHESS_PGN)
    assert len(games) == 3
    assert games[0]["white"] == "player1"
    assert games[0]["black"] == "testuser"
    assert games[0]["result"] == "0-1"
    assert games[1]["result"] == "1-0"
    assert games[2]["result"] == "1/2-1/2"


@pytest.mark.unit
def test_parse_pgn_extracts_platform_game_id():
    """Platform game ID is extracted from the Site header."""
    games = _parse_pgn_stream(SAMPLE_LICHESS_PGN)
    assert games[0]["platform_game_id"] == "abc12345"
    assert games[1]["platform_game_id"] == "def67890"


@pytest.mark.unit
def test_import_returns_count():
    """Import returns the count of imported games."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(text=SAMPLE_LICHESS_PGN)

    result = lichess_game_import("testuser", max_games=50, client=client)

    assert result["imported"] == 3
    assert result["source"] == "lichess"
    assert result["username"] == "testuser"


@pytest.mark.unit
def test_import_results_summary():
    """Import returns results summary."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(text=SAMPLE_LICHESS_PGN)

    result = lichess_game_import("testuser", client=client)

    assert result["results"]["0-1"] == 1
    assert result["results"]["1-0"] == 1
    assert result["results"]["1/2-1/2"] == 1


@pytest.mark.unit
def test_import_user_not_found():
    """Returns error for nonexistent user."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(status=404)

    result = lichess_game_import("nonexistent", client=client)

    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.unit
def test_import_rate_limited():
    """Returns error on rate limit."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(status=429)

    result = lichess_game_import("testuser", client=client)

    assert "error" in result
    assert "rate limit" in result["error"].lower()


@pytest.mark.unit
def test_import_empty_pgn():
    """Returns zero imported for empty response."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(text="")

    result = lichess_game_import("testuser", client=client)

    assert result["imported"] == 0


@pytest.mark.unit
def test_import_stores_in_supabase():
    """When user_id provided, games are POSTed to Supabase."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(text=SAMPLE_LICHESS_PGN)

    with patch("src.tools.external_apis._supabase_post") as mock_post:
        mock_post.return_value = 3
        result = lichess_game_import(
            "testuser",
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
            client=client,
        )

    assert result["imported"] == 3
    mock_post.assert_called_once()
    rows = mock_post.call_args[0][1]
    assert len(rows) == 3
    assert rows[0]["source"] == "lichess"
    assert rows[0]["user_id"] == "user123"


@pytest.mark.unit
def test_import_passes_time_control():
    """time_control parameter is passed to the API."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(text=SAMPLE_LICHESS_PGN)

    lichess_game_import("testuser", time_control="rapid", client=client)

    call_args = client.get.call_args
    params = call_args.kwargs.get("params") or call_args[1].get("params", {})
    assert params.get("perfType") == "rapid"


@pytest.mark.unit
def test_import_max_games_clamped():
    """max_games is clamped to 1-200 range."""
    client = MagicMock()
    client.get.return_value = _make_mock_response(text="")

    lichess_game_import("testuser", max_games=0, client=client)
    params = client.get.call_args.kwargs.get("params", {})
    assert params["max"] == 1

    lichess_game_import("testuser", max_games=999, client=client)
    params = client.get.call_args.kwargs.get("params", {})
    assert params["max"] == 200
