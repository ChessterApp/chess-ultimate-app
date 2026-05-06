"""Tests for openings repertoire filter fixes (PRD Item C).

Covers:
- fetch_internal_games gains the position-hash FAST PATH so a rare position
  (mostly older games) does not return 0 rows after a global newest-first scan.
- min_rating in fetch_internal_games_progressive (TWIC) requires BOTH
  white_elo and black_elo >= threshold (was OR).

These tests use the real TWIC SQLite DB (read-only) so they can verify
behaviour against production data.
"""

import inspect
import os
import sqlite3

import pytest
from unittest.mock import patch


TWIC_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data/twic/games_index.db",
)

# Open Sicilian after 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 — high-volume position
# with thousands of TWIC games including plenty of GM-vs-GM pairings.
TEST_FEN = "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R w KQkq - 0 5"


pytestmark = pytest.mark.skipif(
    not os.path.exists(TWIC_DB_PATH) or os.path.getsize(TWIC_DB_PATH) < 1_000_000,
    reason="TWIC games_index.db not present — these tests require the real DB",
)


@pytest.fixture
def openings_mod():
    """Import the openings module with a clean cache state."""
    from api import openings as mod

    mod._position_count_cache.clear()
    mod._max_game_id_cache['value'] = None
    mod._max_game_id_cache['ts'] = 0
    return mod


def test_internal_games_uses_position_index_when_available(openings_mod):
    """fetch_internal_games must return games for the position even though the
    global newest-first scan would have missed it."""
    results = openings_mod.fetch_internal_games(
        search_query="", max_games=10, filter_fen=TEST_FEN,
    )
    assert len(results) > 0, "FAST PATH should return games at this FEN"
    assert len(results) <= 10


def test_internal_games_returns_position_matches_only(openings_mod):
    """Every returned game's PGN must actually reach the requested FEN."""
    results = openings_mod.fetch_internal_games(
        search_query="", max_games=5, filter_fen=TEST_FEN,
    )
    assert len(results) > 0
    for game in results:
        pgn = game.get("pgn") or ""
        assert pgn, f"Game {game.get('id')} missing pgn payload"
        assert openings_mod.check_game_reaches_fen(pgn, TEST_FEN, str(game.get("id"))), (
            f"Game {game.get('id')} PGN does not reach {TEST_FEN}"
        )


def test_internal_games_no_filter_fen_baseline(openings_mod):
    """Without filter_fen the result is up to max_games newest games — unchanged."""
    results = openings_mod.fetch_internal_games(
        search_query="", max_games=7, filter_fen=None,
    )
    assert len(results) == 7
    for game in results:
        # No PGN was requested, so the row should still have core fields.
        assert "id" in game
        assert "white_name" in game


def test_internal_games_combined_with_eco_filter(openings_mod):
    """filter_fen + eco_filter='B90' returns only B90 games at the FEN."""
    results = openings_mod.fetch_internal_games(
        search_query="", max_games=10, filter_fen=TEST_FEN, eco_filter="B90",
    )
    assert len(results) > 0
    for game in results:
        eco = (game.get("eco") or "")
        assert eco.startswith("B90"), f"Got eco={eco!r} for game {game.get('id')}"
        pgn = game.get("pgn") or ""
        assert openings_mod.check_game_reaches_fen(pgn, TEST_FEN, str(game.get("id")))


def test_min_rating_uses_and_in_progressive_fast_path(openings_mod):
    """FAST PATH: every yielded 'game' event must have BOTH elos >= 2500."""
    games = []
    for ev in openings_mod.fetch_internal_games_progressive(
        filter_fen=TEST_FEN, min_rating=2500, max_games=10,
    ):
        if ev.get("type") == "game":
            games.append(ev["game"])

    assert len(games) > 0, "Expected at least one 2500+ vs 2500+ game at this position"
    for g in games:
        w = g.get("white_elo") or 0
        b = g.get("black_elo") or 0
        assert w >= 2500, f"white_elo={w} should be >= 2500 (game {g.get('id')})"
        assert b >= 2500, f"black_elo={b} should be >= 2500 (game {g.get('id')})"


def test_min_rating_uses_and_in_progressive_slow_path(openings_mod):
    """SLOW PATH (forced via _has_position_index=False): both elos still >= 2500."""
    with patch.object(openings_mod, "_has_position_index", lambda conn: False):
        games = []
        for ev in openings_mod.fetch_internal_games_progressive(
            filter_fen=TEST_FEN, min_rating=2500, max_games=5, stop_after=4000,
        ):
            if ev.get("type") == "game":
                games.append(ev["game"])

    assert len(games) > 0, (
        "SLOW PATH should still find 2500+ vs 2500+ games at this position"
    )
    for g in games:
        w = g.get("white_elo") or 0
        b = g.get("black_elo") or 0
        assert w >= 2500, f"white_elo={w} should be >= 2500 (game {g.get('id')})"
        assert b >= 2500, f"black_elo={b} should be >= 2500 (game {g.get('id')})"


def test_min_rating_excludes_mismatched_pair(openings_mod):
    """No returned game may have either side below the threshold — i.e. a
    synthesized 2700-vs-1500 game would not pass min_rating=2500."""
    games = []
    for ev in openings_mod.fetch_internal_games_progressive(
        filter_fen=TEST_FEN, min_rating=2500, max_games=20,
    ):
        if ev.get("type") == "game":
            games.append(ev["game"])

    assert len(games) > 0
    mismatched = [
        g for g in games
        if (g.get("white_elo") or 0) < 2500 or (g.get("black_elo") or 0) < 2500
    ]
    assert mismatched == [], (
        f"Found mismatched games (one side <2500) — AND filter regressed: {mismatched}"
    )


def test_no_regression_for_lichess_and_chesscom_paths(openings_mod):
    """Lichess and Chess.com progressive functions must still use the
    `max(w_elo, b_elo) < min_rating` predicate. Whether OR or AND is correct
    there is a separate UX decision — this PRD must not change them.

    Verifies via inspect.getsource that the substring appears exactly twice
    in api/openings.py (once for Lichess, once for Chess.com)."""
    src = inspect.getsource(openings_mod)
    occurrences = src.count("max(w_elo, b_elo) < min_rating")
    assert occurrences == 2, (
        f"Expected 'max(w_elo, b_elo) < min_rating' to appear exactly twice "
        f"(lichess + chesscom), got {occurrences}."
    )
