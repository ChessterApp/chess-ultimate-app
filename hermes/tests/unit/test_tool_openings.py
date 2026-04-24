"""Unit tests for Tool 2: get_opening_stats."""

import pytest

from src.tools.openings import get_opening_stats


@pytest.mark.unit
def test_by_eco(fake_twic_db):
    """Look up by ECO code returns correct opening info."""
    result = get_opening_stats(eco="C65", db_path=":memory:")
    assert result["eco"] == "C65"
    assert "Ruy Lopez" in result["name"]
    assert "main_line" in result


@pytest.mark.unit
def test_by_name():
    """Look up by opening name returns correct ECO."""
    result = get_opening_stats(opening_name="Sicilian Najdorf", db_path=":memory:")
    assert result["eco"] == "B90"
    assert "Sicilian" in result["name"]


@pytest.mark.unit
def test_schema():
    """Result has all expected fields."""
    result = get_opening_stats(eco="B90", db_path=":memory:")
    expected_keys = {"eco", "name", "main_line", "games_count", "white_win_pct", "draw_pct", "black_win_pct"}
    assert expected_keys.issubset(result.keys())


@pytest.mark.unit
def test_unknown_eco():
    """Unknown ECO code returns an error."""
    result = get_opening_stats(eco="Z99", db_path=":memory:")
    assert "error" in result


@pytest.mark.unit
def test_case_insensitive():
    """Name lookup is case-insensitive."""
    result1 = get_opening_stats(opening_name="sicilian najdorf", db_path=":memory:")
    result2 = get_opening_stats(opening_name="SICILIAN NAJDORF", db_path=":memory:")
    assert result1["eco"] == result2["eco"] == "B90"
