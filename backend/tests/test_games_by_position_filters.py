"""Tests for /api/openings/games/by-position rating + wide-filter handling.

Regression test for the bug where moving the Elo slider on /database
returned almost no results because the candidate-first SQL path took
the first 5000 games matching white_elo >= N, most of which never
reached the queried position.
"""

import os
import sqlite3
import tempfile

import pytest
from unittest.mock import patch


# FEN for a position we'll plant in the test DB. Hash strips the en-passant +
# halfmove/fullmove fields, matching _get_board_hash().
TEST_FEN = "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R w KQkq - 0 5"
BOARD_HASH = "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R w KQkq -"


def _build_test_db(path: str) -> None:
    """Build a tiny TWIC-shaped SQLite DB.

    100 games at the test position (ids 1-100, white_elo 1500-2499) plus
    50,000 noise games (ids 101-50100) NOT at the position with white_elo
    spread across 800-3000. The candidate-first bug would pick the noise
    games' ids first when filtering by elo, producing ~0 matches.
    """
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            white_name TEXT NOT NULL, white_name_normalized TEXT NOT NULL,
            black_name TEXT NOT NULL, black_name_normalized TEXT NOT NULL,
            white_elo INTEGER, black_elo INTEGER,
            white_title TEXT, black_title TEXT,
            white_fide_id TEXT, black_fide_id TEXT,
            result TEXT, date TEXT, year INTEGER,
            eco TEXT, opening TEXT, variation TEXT,
            event TEXT, site TEXT, round TEXT,
            pgn_offset INTEGER, pgn_length INTEGER
        );
        CREATE INDEX idx_white_elo ON games(white_elo);
        CREATE INDEX idx_black_elo ON games(black_elo);
        CREATE INDEX idx_result ON games(result);

        CREATE TABLE game_positions (
            game_id INTEGER NOT NULL,
            board_hash TEXT NOT NULL
        );
        CREATE INDEX idx_positions_hash ON game_positions(board_hash);
        CREATE INDEX idx_positions_game ON game_positions(game_id);

        CREATE TABLE move_stats (
            board_hash TEXT NOT NULL,
            move TEXT,
            games INTEGER
        );
        """
    )

    rows = []
    positions = []
    # 100 games AT the test position, ids 1-100, elo 1500..2499
    for i in range(1, 101):
        elo = 1500 + (i * 10) - 10
        rows.append((
            i, "Player A", "player a", "Player B", "player b",
            elo, elo - 50,
            "", "", "", "",
            "1-0", "2024.01.01", 2024,
            "B90", "Sicilian", "",
            "Test Event", "Test", "1", 0, 0,
        ))
        positions.append((i, BOARD_HASH))

    # 50,000 noise games, ids 101..50100, NOT at the test position.
    # Mix of low- and high-elo so the elo filter alone returns lots of them.
    for i in range(101, 50101):
        elo = 800 + (i % 2200)  # 800..2999
        rows.append((
            i, f"Noise{i}", f"noise{i}", "Opp", "opp",
            elo, elo - 30,
            "", "", "", "",
            "1-0", "2020.01.01", 2020,
            "A00", "Other", "",
            "Other", "Other", "1", 0, 0,
        ))

    cur.executemany(
        "INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    cur.executemany("INSERT INTO game_positions VALUES (?, ?)", positions)
    cur.execute(
        "INSERT INTO move_stats VALUES (?, ?, ?)",
        (BOARD_HASH, "Nf6", 100),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def app_client():
    """Flask app with the openings blueprint pointed at a temp test DB."""
    from flask import Flask
    from api import openings as openings_mod

    tmpfd, tmppath = tempfile.mkstemp(suffix=".db")
    os.close(tmpfd)
    _build_test_db(tmppath)

    # Patch the read-only connection helper to point at our temp DB.
    def _fake_conn():
        uri = f"file:{tmppath}?mode=ro"
        c = sqlite3.connect(uri, uri=True)
        c.row_factory = sqlite3.Row
        return c

    # Reset caches that survive between tests.
    openings_mod._position_count_cache.clear()
    openings_mod._max_game_id_cache['value'] = None
    openings_mod._max_game_id_cache['ts'] = 0

    with patch.object(openings_mod, "get_internal_db_connection", _fake_conn), \
         patch.object(openings_mod, "check_internal_db_exists", lambda: True):
        app = Flask(__name__)
        app.register_blueprint(openings_mod.openings_bp)
        app.config["TESTING"] = True
        yield app.test_client()

    os.unlink(tmppath)


def _get_json(client, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    resp = client.get(f"/api/openings/games/by-position?fen={TEST_FEN}&{qs}")
    assert resp.status_code == 200, resp.data
    return resp.get_json()


def test_no_filter_returns_all_position_games(app_client):
    data = _get_json(app_client, limit=50)
    assert data["total"] == 100
    assert len(data["games"]) == 50  # capped by limit
    assert all(g["id"] <= 100 for g in data["games"])


def test_white_elo_min_does_not_drop_to_zero(app_client):
    """Regression: moving slider to 1500 must still find ~all 100 games,
    not hit the candidate-first bug that returned ~0."""
    data = _get_json(app_client, limit=50, white_elo_min=1500)
    # All 100 position games have white_elo in 1500..2499
    assert data["total"] == 100
    assert len(data["games"]) == 50


def test_white_elo_min_high_filters_correctly(app_client):
    """Slider at 2000 should keep games with white_elo >= 2000 only."""
    data = _get_json(app_client, limit=50, white_elo_min=2000)
    # Position games with elo >= 2000: ids 51..100 → 50 games
    assert data["total"] == 50
    assert all(g["white_elo"] >= 2000 for g in data["games"])


def test_white_elo_range_filters_both_bounds(app_client):
    """Slider min=1700 max=1900 should keep only that band."""
    data = _get_json(app_client, limit=50, white_elo_min=1700, white_elo_max=1900)
    # Position games with elo 1700..1900: 21 games (1700,1710,...,1900)
    assert data["total"] == 21
    for g in data["games"]:
        assert 1700 <= g["white_elo"] <= 1900


def test_elo_filter_excludes_noise_games(app_client):
    """Elo filter must NOT pull in the 50K noise games that don't reach
    the position (the original bug was the inverse)."""
    data = _get_json(app_client, limit=50, white_elo_min=1500)
    # Noise games have ids > 100; none should appear.
    assert all(g["id"] <= 100 for g in data["games"])


def test_black_elo_min_filters_position_pool(app_client):
    """Black elo slider works on position pool too. Position games have
    black_elo = white_elo - 50, so 1500..2449. min=2000 → ids 56..100."""
    data = _get_json(app_client, limit=50, black_elo_min=2000)
    assert data["total"] == 45
    assert all(g["black_elo"] >= 2000 for g in data["games"])


def test_count_exact_set_when_wide_filter_applied(app_client):
    """The filtered count is computed exactly from the position pool, so
    count_exact must be true once a wide filter is in play."""
    data = _get_json(app_client, limit=50, white_elo_min=2000)
    assert data["count_exact"] is True
