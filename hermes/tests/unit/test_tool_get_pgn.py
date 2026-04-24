"""Unit tests for Tool 4: get_game_pgn."""

import io

import chess.pgn
import pytest

from src.tools.twic_search import get_game_pgn


@pytest.mark.unit
def test_valid_id(fake_twic_db):
    """Valid game ID returns pgn and headers."""
    result = get_game_pgn(game_id=1, conn=fake_twic_db)
    assert "pgn" in result
    assert "headers" in result
    assert "error" not in result
    assert result["headers"]["White"] == "Carlsen"
    assert result["headers"]["Black"] == "Caruana"


@pytest.mark.unit
def test_invalid_id(fake_twic_db):
    """Invalid game ID returns error."""
    result = get_game_pgn(game_id=99999, conn=fake_twic_db)
    assert "error" in result


@pytest.mark.unit
def test_pgn_parseable(fake_twic_db):
    """Returned PGN string can be parsed by python-chess."""
    result = get_game_pgn(game_id=1, conn=fake_twic_db)
    pgn_text = result["pgn"]
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    assert game is not None
    assert game.headers["White"] == "Carlsen"


@pytest.mark.unit
def test_headers_extracted(fake_twic_db):
    """Headers dict contains expected keys."""
    result = get_game_pgn(game_id=1, conn=fake_twic_db)
    headers = result["headers"]
    assert "White" in headers
    assert "Black" in headers
    assert "Result" in headers
    assert "Date" in headers
    assert "ECO" in headers
    assert "Event" in headers
