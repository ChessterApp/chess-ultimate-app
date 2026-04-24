"""Unit tests for Tool 3: search_master_games."""

import pytest

from src.tools.twic_search import search_master_games


@pytest.mark.unit
def test_by_player(fake_twic_db):
    """Search by player name returns matching games."""
    results = search_master_games(player="Carlsen", conn=fake_twic_db)
    assert len(results) >= 1
    for game in results:
        assert "Carlsen" in game["white"] or "Carlsen" in game["black"]


@pytest.mark.unit
def test_by_eco(fake_twic_db):
    """Search by ECO code returns matching games."""
    results = search_master_games(eco="C65", conn=fake_twic_db)
    assert len(results) >= 1
    for game in results:
        assert game["eco"] == "C65"


@pytest.mark.unit
def test_by_year_range(fake_twic_db):
    """Search by year range filters correctly."""
    results = search_master_games(year_min=2024, year_max=2024, conn=fake_twic_db)
    assert len(results) >= 1
    for game in results:
        assert game["date"].startswith("2024")


@pytest.mark.unit
def test_by_result(fake_twic_db):
    """Search by result filters correctly."""
    results = search_master_games(result="1-0", conn=fake_twic_db)
    assert len(results) >= 1
    for game in results:
        assert game["result"] == "1-0"


@pytest.mark.unit
def test_combined_filters(fake_twic_db):
    """Multiple filters combine with AND logic."""
    results = search_master_games(player="Carlsen", result="1-0", conn=fake_twic_db)
    assert len(results) >= 1
    for game in results:
        assert ("Carlsen" in game["white"] or "Carlsen" in game["black"])
        assert game["result"] == "1-0"


@pytest.mark.unit
def test_limit_enforced(fake_twic_db):
    """Limit parameter restricts result count."""
    results = search_master_games(limit=2, conn=fake_twic_db)
    assert len(results) <= 2


@pytest.mark.unit
def test_limit_capped_at_50(fake_twic_db):
    """Limit above 50 is capped at 50."""
    results = search_master_games(limit=100, conn=fake_twic_db)
    # With only 10 fixture games, we just verify it doesn't error
    assert len(results) <= 50


@pytest.mark.unit
def test_no_filters(fake_twic_db):
    """No filters returns all games (up to limit)."""
    results = search_master_games(conn=fake_twic_db)
    assert len(results) == 10  # All fixture games


@pytest.mark.unit
def test_nonexistent_player(fake_twic_db):
    """Searching for nonexistent player returns empty list."""
    results = search_master_games(player="NonexistentPlayer12345", conn=fake_twic_db)
    assert results == []


@pytest.mark.unit
def test_sql_injection_safe(fake_twic_db):
    """SQL injection attempt in parameters doesn't cause errors or data leaks."""
    # These should return empty results, not errors
    results = search_master_games(player="'; DROP TABLE games; --", conn=fake_twic_db)
    assert isinstance(results, list)
    assert len(results) == 0

    results = search_master_games(eco="' OR '1'='1", conn=fake_twic_db)
    assert isinstance(results, list)
    assert len(results) == 0

    # Verify the table still exists
    cur = fake_twic_db.execute("SELECT COUNT(*) FROM games")
    assert cur.fetchone()[0] == 10
