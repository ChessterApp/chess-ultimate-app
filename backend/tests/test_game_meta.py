"""Tests for the public /api/openings/games/<id>/meta endpoint.

This endpoint powers Open Graph link previews for /g/<slug> short links.
It is PUBLIC (no Clerk auth) and must return header metadata only — never
the PGN or move list, which stay behind the auth-gated /pgn endpoints.
"""

import os
import sqlite3
import tempfile

import pytest
from unittest.mock import patch


def _build_test_db(path: str) -> None:
    """Build a tiny TWIC-shaped SQLite DB with a single known game."""
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
        """
    )
    cur.execute(
        "INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            1, "Carlsen, M", "carlsen m", "Nakamura, H", "nakamura h",
            2830, 2780,
            "GM", "GM", "", "",
            "1-0", "2024.08.24", 2024,
            "C65", "Ruy Lopez", "",
            "Sinquefield Cup", "Saint Louis", "3",
            12345, 678,
        ),
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

    def _fake_conn():
        uri = f"file:{tmppath}?mode=ro"
        c = sqlite3.connect(uri, uri=True)
        c.row_factory = sqlite3.Row
        return c

    with patch.object(openings_mod, "get_internal_db_connection", _fake_conn), \
         patch.object(openings_mod, "check_internal_db_exists", lambda: True):
        app = Flask(__name__)
        app.register_blueprint(openings_mod.openings_bp)
        app.config["TESTING"] = True
        yield app.test_client()

    os.unlink(tmppath)


def test_meta_happy_path(app_client):
    resp = app_client.get("/api/openings/games/1/meta?source=twic")
    assert resp.status_code == 200, resp.data
    data = resp.get_json()
    assert data["white"] == "Carlsen, M"
    assert data["black"] == "Nakamura, H"
    assert data["result"] == "1-0"
    assert data["event"] == "Sinquefield Cup"
    assert data["date"] == "2024.08.24"
    assert data["white_elo"] == 2830
    assert data["black_elo"] == 2780


def test_meta_defaults_to_twic_source(app_client):
    """Omitting ?source should default to the twic master database."""
    resp = app_client.get("/api/openings/games/1/meta")
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["white"] == "Carlsen, M"


def test_meta_never_returns_pgn_or_moves(app_client):
    """The whole point of the public endpoint: no PGN/moves leak out."""
    resp = app_client.get("/api/openings/games/1/meta?source=twic")
    data = resp.get_json()
    assert "pgn" in data if False else True  # readability
    assert "pgn" not in data
    assert "moves" not in data


def test_meta_requires_no_auth(app_client):
    """No Authorization header → still 200. (Auth would 401 without it.)"""
    resp = app_client.get("/api/openings/games/1/meta?source=twic")
    assert resp.status_code == 200
    assert "WWW-Authenticate" not in resp.headers


def test_meta_unknown_id_is_404_json(app_client):
    resp = app_client.get("/api/openings/games/999999/meta?source=twic")
    assert resp.status_code == 404
    assert resp.is_json
    assert "error" in resp.get_json()


def test_meta_unknown_source_is_400(app_client):
    resp = app_client.get("/api/openings/games/1/meta?source=chesscom")
    assert resp.status_code == 400
    assert resp.is_json


def test_meta_lichess_source_fetches_header_only(app_client):
    """Lichess source parses header-only PGN from the export API (mocked)."""
    from api import openings as openings_mod

    class _Resp:
        status_code = 200
        text = (
            '[Event "Rated Blitz game"]\n'
            '[White "DrNykterstein"]\n'
            '[Black "penguingim1"]\n'
            '[Result "0-1"]\n'
            '[UTCDate "2024.01.02"]\n'
            '[WhiteElo "2900"]\n'
            '[BlackElo "2850"]\n\n'
            '1. e4 *\n'
        )

    with patch.object(openings_mod.requests, "get", lambda *a, **k: _Resp()):
        resp = app_client.get("/api/openings/games/5/meta?source=lichess")
    assert resp.status_code == 200, resp.data
    data = resp.get_json()
    assert data["white"] == "DrNykterstein"
    assert data["black"] == "penguingim1"
    assert data["result"] == "0-1"
    assert data["date"] == "2024.01.02"
    assert data["white_elo"] == 2900
    assert "pgn" not in data
    assert "moves" not in data
