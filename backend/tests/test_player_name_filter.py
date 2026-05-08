"""Tests for /api/openings/games/by-position player_name / opponent_name filter.

Regression test for the bug where `?player_name=carlsen` on /database returned
`returned=0 total=136830 timeout=true` because the leading-`%` LIKE pattern
disabled the name index and forced a 3.6 M-row table scan.

These tests run against the real TWIC DB (read-only) — they assert behaviour
that depends on production data such as the number of Carlsen games at the
open Sicilian position.
"""

import os
import sqlite3
import time

import pytest
from unittest.mock import patch


TWIC_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data/twic/games_index.db",
)

# Open Sicilian after 5...d6: a high-volume position used in the smoke test.
TEST_FEN = "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R w KQkq - 0 5"

# Standard starting position — every game in the DB reaches it (~3.3 M).
# Worst case for the position-side cost; used to regression-test the
# narrow-filter EXISTS+UNION rewrite.
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Najdorf after 5...a6 6.f3-ish (mid-pool position, far less common than start).
NAJDORF_FEN = "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"


pytestmark = pytest.mark.skipif(
    not os.path.exists(TWIC_DB_PATH) or os.path.getsize(TWIC_DB_PATH) < 1_000_000,
    reason="TWIC games_index.db not present — these tests require the real DB",
)


@pytest.fixture
def app_client():
    """Flask app with the openings blueprint pointed at the real read-only TWIC DB."""
    from flask import Flask
    from api import openings as openings_mod

    def _ro_conn():
        uri = f"file:{TWIC_DB_PATH}?mode=ro"
        c = sqlite3.connect(uri, uri=True)
        c.row_factory = sqlite3.Row
        return c

    openings_mod._position_count_cache.clear()
    openings_mod._max_game_id_cache['value'] = None
    openings_mod._max_game_id_cache['ts'] = 0

    with patch.object(openings_mod, "get_internal_db_connection", _ro_conn), \
         patch.object(openings_mod, "check_internal_db_exists", lambda: True):
        app = Flask(__name__)
        app.register_blueprint(openings_mod.openings_bp)
        app.config["TESTING"] = True
        yield app.test_client()


def _get_json(client, fen=TEST_FEN, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    resp = client.get(f"/api/openings/games/by-position?fen={fen}&{qs}")
    assert resp.status_code == 200, resp.data
    return resp.get_json()


def _has_carlsen(game):
    w = (game.get("white_name") or "").lower()
    b = (game.get("black_name") or "").lower()
    return "carlsen" in w or "carlsen" in b


def test_player_name_carlsen_returns_games(app_client):
    """Regression: `?player_name=carlsen` must return real games, not time out."""
    data = _get_json(app_client, player_name="carlsen", limit=10)
    assert not data.get("timeout"), data
    assert data["total"] > 0
    assert len(data["games"]) > 0
    for g in data["games"]:
        assert _has_carlsen(g), g


def test_player_color_black_only_returns_carlsen_as_black(app_client):
    data = _get_json(app_client, player_name="carlsen", player_color="black", limit=10)
    assert not data.get("timeout"), data
    assert data["total"] > 0
    for g in data["games"]:
        assert "carlsen" in (g.get("black_name") or "").lower(), g


def test_player_color_white_only_returns_carlsen_as_white(app_client):
    data = _get_json(app_client, player_name="carlsen", player_color="white", limit=10)
    assert not data.get("timeout"), data
    assert data["total"] > 0
    for g in data["games"]:
        assert "carlsen" in (g.get("white_name") or "").lower(), g


def test_player_name_with_black_elo_min_combines_filters(app_client):
    data = _get_json(app_client, player_name="carlsen", black_elo_min=2700, limit=10)
    assert not data.get("timeout"), data
    for g in data["games"]:
        assert _has_carlsen(g), g
        assert (g.get("black_elo") or 0) >= 2700, g


def test_full_name_search_matches_carlsen(app_client):
    """`magnus carlsen` (full name) collapses to the longest token (`carlsen`)
    so it must still return Carlsen games."""
    data = _get_json(app_client, player_name="magnus%20carlsen", limit=10)
    assert not data.get("timeout"), data
    assert data["total"] > 0
    for g in data["games"]:
        assert _has_carlsen(g), g


def test_player_name_is_case_insensitive(app_client):
    """All-caps must match the same set as lowercase."""
    lower = _get_json(app_client, player_name="carlsen", limit=50)
    upper = _get_json(app_client, player_name="CARLSEN", limit=50)
    mixed = _get_json(app_client, player_name="Carlsen", limit=50)
    assert lower["total"] == upper["total"] == mixed["total"]
    assert lower["total"] > 0


def test_unknown_player_returns_zero_not_position_total(app_client):
    """Regression: unknown player returned `total=136830` (raw position count)
    when the candidate query timed out. After the fix it must return 0."""
    data = _get_json(app_client, player_name="zzzzznonexistentplayer", limit=10)
    assert data["total"] == 0
    assert data["games"] == []
    assert not data.get("timeout"), data


def test_player_name_query_under_1500ms(app_client):
    """End-to-end wall time for `player_name=carlsen` on a high-volume position
    must stay under the 1.5 s budget."""
    # Warm any caches first.
    _get_json(app_client, player_name="carlsen", limit=10)

    start = time.time()
    data = _get_json(app_client, player_name="carlsen", limit=10)
    elapsed = time.time() - start
    assert not data.get("timeout"), data
    assert data["total"] > 0
    assert elapsed < 1.5, f"player_name query took {elapsed:.2f}s, expected < 1.5s"


# ─────────────────────────────────────────────
# Starting-position regression tests for the EXISTS+UNION rewrite.
# Pre-fix, narrow-filter searches at the starting FEN took 90–140 s
# because every game_id at that hash (~3.3 M) was materialised into a
# Python set. The fix issues a single EXISTS+UNION query that lets SQLite
# pick the name index instead.
# ─────────────────────────────────────────────


def test_start_fen_rare_player_under_5s(app_client):
    """Starting FEN + low-volume player (Shomoev) must finish under 5 s and
    return real games. The pre-fix code timed out at 92 s."""
    start = time.time()
    data = _get_json(app_client, fen=START_FEN, player_name="Shomoev", limit=50)
    elapsed = time.time() - start
    assert not data.get("timeout"), data
    assert elapsed < 5.0, f"Shomoev query took {elapsed:.2f}s, expected < 5s"
    assert len(data["games"]) > 0
    for g in data["games"]:
        w = (g.get("white_name") or "").lower()
        b = (g.get("black_name") or "").lower()
        assert "shomoev" in w or "shomoev" in b, g


def test_start_fen_high_volume_player_under_5s(app_client):
    """Worst case: high-volume player (Carlsen) at the starting FEN. Must
    return up to `limit` games inside 5 s."""
    start = time.time()
    data = _get_json(app_client, fen=START_FEN, player_name="Carlsen", limit=50)
    elapsed = time.time() - start
    assert not data.get("timeout"), data
    assert elapsed < 5.0, f"Carlsen query took {elapsed:.2f}s, expected < 5s"
    assert len(data["games"]) == 50


def test_start_fen_player_color_white_only_white_carlsen(app_client):
    data = _get_json(
        app_client, fen=START_FEN,
        player_name="Carlsen", player_color="white", limit=20,
    )
    assert not data.get("timeout"), data
    assert len(data["games"]) > 0
    for g in data["games"]:
        assert "carlsen" in (g.get("white_name") or "").lower(), g


def test_start_fen_opponent_white_player_means_black_match(app_client):
    """`opponent_name=Shomoev&player_color=white` means: I (the player) am
    white, opponent (Shomoev) must be black."""
    data = _get_json(
        app_client, fen=START_FEN,
        opponent_name="Shomoev", player_color="white", limit=20,
    )
    assert not data.get("timeout"), data
    assert len(data["games"]) > 0
    for g in data["games"]:
        assert "shomoev" in (g.get("black_name") or "").lower(), g


def test_najdorf_player_under_3s(app_client):
    """Mid-pool position (Najdorf) + high-volume player (Caruana). Even
    without the position-fan-out problem this must return inside 3 s."""
    # Warm OS page cache — first hit may pull Najdorf-related pages from disk.
    _get_json(app_client, fen=NAJDORF_FEN, player_name="Caruana", limit=50)

    start = time.time()
    data = _get_json(
        app_client, fen=NAJDORF_FEN, player_name="Caruana", limit=50,
    )
    elapsed = time.time() - start
    assert not data.get("timeout"), data
    assert elapsed < 3.0, f"Najdorf+Caruana took {elapsed:.2f}s, expected < 3s"
    assert len(data["games"]) > 0
    for g in data["games"]:
        w = (g.get("white_name") or "").lower()
        b = (g.get("black_name") or "").lower()
        assert "caruana" in w or "caruana" in b, g


def test_start_fen_no_filter_uses_direct_path(app_client):
    """No filters at the starting FEN must still return games quickly via
    the unchanged DIRECT path — regression guard against the rewrite
    accidentally swallowing the unfiltered case."""
    start = time.time()
    data = _get_json(app_client, fen=START_FEN, limit=10)
    elapsed = time.time() - start
    assert not data.get("timeout"), data
    assert elapsed < 5.0, f"unfiltered start FEN took {elapsed:.2f}s"
    assert len(data["games"]) == 10
    # The DIRECT path reports the position-level total (millions) without
    # an exact count.
    assert data["total"] > 1_000_000


def test_short_player_token_returns_empty_no_timeout(app_client):
    """Single-character `player_name` would force a near-full table scan.
    Guard at the entry must short-circuit to an empty response."""
    data = _get_json(app_client, fen=START_FEN, player_name="A", limit=10)
    assert data["games"] == []
    assert data["total"] == 0
    assert not data.get("timeout"), data
