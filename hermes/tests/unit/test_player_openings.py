"""Unit tests for get_player_openings tool."""

import pytest

from src.tools.player_openings import get_player_openings


@pytest.mark.unit
def test_by_player(fake_twic_db):
    """Returns opening stats for a known player."""
    result = get_player_openings(player_name="Carlsen", conn=fake_twic_db)
    assert result["player_name"] == "Carlsen"
    assert len(result["openings"]) >= 1


@pytest.mark.unit
def test_filter_white(fake_twic_db):
    """Filter by white returns only white openings."""
    result = get_player_openings(player_name="Carlsen", color="white", conn=fake_twic_db)
    assert result["color"] == "white"
    # Carlsen plays white in game 1 (C65 Ruy Lopez)
    assert len(result["openings"]) >= 1


@pytest.mark.unit
def test_filter_black(fake_twic_db):
    """Filter by black returns only black openings."""
    result = get_player_openings(player_name="Carlsen", color="black", conn=fake_twic_db)
    assert result["color"] == "black"


@pytest.mark.unit
def test_unknown_player(fake_twic_db):
    """Unknown player returns empty openings list."""
    result = get_player_openings(player_name="Unknown12345", conn=fake_twic_db)
    assert result["openings"] == []


@pytest.mark.unit
def test_empty_name():
    """Empty player name returns error."""
    result = get_player_openings(player_name="")
    assert "error" in result


@pytest.mark.unit
def test_opening_fields(fake_twic_db):
    """Each opening has expected fields."""
    result = get_player_openings(player_name="Carlsen", conn=fake_twic_db)
    for opening in result["openings"]:
        assert "eco" in opening
        assert "opening_name" in opening
        assert "games" in opening
        assert "wins" in opening
        assert "draws" in opening
        assert "losses" in opening
        assert "win_pct" in opening


@pytest.mark.unit
def test_limit(fake_twic_db):
    """Limit restricts the number of openings returned."""
    result = get_player_openings(player_name="Carlsen", limit=1, conn=fake_twic_db)
    assert len(result["openings"]) <= 1


@pytest.mark.unit
def test_sorted_by_games(fake_twic_db):
    """Openings are sorted by game count descending."""
    result = get_player_openings(player_name="Carlsen", conn=fake_twic_db)
    if len(result["openings"]) > 1:
        games_counts = [o["games"] for o in result["openings"]]
        assert games_counts == sorted(games_counts, reverse=True)
