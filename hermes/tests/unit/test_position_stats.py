"""Unit tests for get_position_stats tool."""

import chess
import pytest

from src.tools.position_stats import get_position_stats


@pytest.mark.unit
def test_starting_position_stats(fake_twic_db):
    """Starting position returns stats with top moves."""
    result = get_position_stats(chess.STARTING_FEN, conn=fake_twic_db)
    assert result["total_games"] == 2150  # 1000 + 800 + 200 + 150
    assert result["white_wins"] > 0
    assert len(result["top_moves"]) == 4


@pytest.mark.unit
def test_top_moves_sorted_by_games(fake_twic_db):
    """Top moves are sorted by game count descending."""
    result = get_position_stats(chess.STARTING_FEN, conn=fake_twic_db)
    games_counts = [m["games"] for m in result["top_moves"]]
    assert games_counts == sorted(games_counts, reverse=True)


@pytest.mark.unit
def test_unknown_position(fake_twic_db):
    """Unknown position returns zero stats."""
    fen = "8/8/8/4k3/8/8/8/4K2R w - - 0 1"
    result = get_position_stats(fen, conn=fake_twic_db)
    assert result["total_games"] == 0
    assert result["top_moves"] == []


@pytest.mark.unit
def test_invalid_fen():
    """Invalid FEN returns error."""
    result = get_position_stats("not a valid fen")
    assert "error" in result
    assert "Invalid FEN" in result["error"]


@pytest.mark.unit
def test_move_stats_fields(fake_twic_db):
    """Each top move has expected fields."""
    result = get_position_stats(chess.STARTING_FEN, conn=fake_twic_db)
    for move in result["top_moves"]:
        assert "move" in move
        assert "games" in move
        assert "white_wins" in move
        assert "draws" in move
        assert "black_wins" in move


@pytest.mark.unit
def test_totals_match_sum_of_moves(fake_twic_db):
    """Total counts equal sum of individual move counts."""
    result = get_position_stats(chess.STARTING_FEN, conn=fake_twic_db)
    assert result["total_games"] == sum(m["games"] for m in result["top_moves"])
    assert result["white_wins"] == sum(m["white_wins"] for m in result["top_moves"])
