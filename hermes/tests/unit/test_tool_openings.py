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


@pytest.mark.unit
class TestOpeningBook:
    """The ECO book from backend/data/openings/*.tsv replaces 33 hand-typed codes."""

    def test_book_loads_thousands_of_lines(self):
        from src.openings_book import get_book

        book = get_book()
        assert len(book.entries) > 3000
        assert book.source != "embedded"

    def test_russian_names_resolve(self):
        for name, expect in [
            ("Сицилианская защита", "Sicilian Defense"),
            ("найдорф", "Najdorf"),
            ("Испанская партия", "Ruy Lopez"),
            ("защита Каро-Канн", "Caro-Kann"),
            ("староиндийская", "King's Indian"),
            ("защита Уфимцева", "Pirc"),
        ]:
            out = get_opening_stats(opening_name=name, db_path=":memory:")
            assert expect in out["name"], (name, out)

    def test_name_lookup_returns_family_main_line_and_variations(self):
        out = get_opening_stats(opening_name="Sicilian Defense", db_path=":memory:")
        assert out["eco"] == "B20"
        assert out["main_line"] == "1. e4 c5"
        assert out["lines_in_book"] > 100
        assert len(out["variations"]) == 14
        assert "B90" in out["eco_codes"]

    def test_identify_opening_by_moves_and_pgn(self):
        from src.tools.openings import identify_opening

        out = identify_opening(moves=["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "h3", "e5"])
        assert out["eco"] == "B90"
        assert "Najdorf" in out["name"]
        assert out["out_of_book_after"] == 11 and out["total_plies"] == 12

        out = identify_opening(pgn="1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Nc3 e6")
        assert "Semi-Slav" in out["name"]
        assert "error" in identify_opening(moves=[])

    def test_embedded_fallback_when_tsv_dir_missing(self, monkeypatch, tmp_path):
        from src import openings_book

        monkeypatch.setattr(openings_book, "_CANDIDATE_DIRS", [str(tmp_path / "nope")])
        openings_book.get_book.cache_clear()
        try:
            book = openings_book.get_book()
            assert book.source == "embedded"
            assert book.by_name("сицилианская")[0][0] == "B20"
        finally:
            openings_book.get_book.cache_clear()
