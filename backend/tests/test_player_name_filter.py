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


def _get_json(client, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    resp = client.get(f"/api/openings/games/by-position?fen={TEST_FEN}&{qs}")
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
