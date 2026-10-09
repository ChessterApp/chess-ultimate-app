"""Tests for the PUBLIC board-position thumbnail endpoints (Share Game Phase 3b).

These power the Open Graph *image* in `/g/<slug>` and `/g/u/<token>` link
previews — an actual chessboard of the game's FINAL position. They are PUBLIC
(no Clerk auth) and reveal only the rendered position: never the PGN text, the
move list, or any owner identity. Unknown id/token → 404.

Master games live in `api/openings.py`; shared user games in `api/user_games.py`.
"""

import os
import sqlite3
import tempfile

import pytest
from unittest.mock import patch

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

SAMPLE_PGN = (
    '[Event "Sinquefield Cup"]\n'
    '[White "Carlsen, M"]\n'
    '[Black "Nakamura, H"]\n'
    '[Result "1-0"]\n\n'
    '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 1-0\n'
)


# ─── Master games (/api/openings/games/<id>/thumbnail.png) ────────────────────

def _build_test_db(path: str, offset: int, length: int) -> None:
    """Tiny TWIC-shaped DB with one game pointing at a PGN file slice."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pgn_offset INTEGER, pgn_length INTEGER
        );
        """
    )
    conn.execute("INSERT INTO games VALUES (?,?,?)", (1, offset, length))
    conn.commit()
    conn.close()


@pytest.fixture
def master_client():
    """Flask client with the openings blueprint pointed at a temp DB + PGN file."""
    from flask import Flask
    from api import openings as openings_mod

    dbfd, dbpath = tempfile.mkstemp(suffix=".db")
    os.close(dbfd)
    pgnfd, pgnpath = tempfile.mkstemp(suffix=".pgn")
    with os.fdopen(pgnfd, "w") as f:
        f.write(SAMPLE_PGN)
    _build_test_db(dbpath, offset=0, length=len(SAMPLE_PGN))

    def _fake_conn():
        c = sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        return c

    with patch.object(openings_mod, "get_internal_db_connection", _fake_conn), \
         patch.object(openings_mod, "check_internal_db_exists", lambda: True), \
         patch.object(openings_mod, "TWIC_PGN_PATH", pgnpath):
        app = Flask(__name__)
        app.register_blueprint(openings_mod.openings_bp)
        app.config["TESTING"] = True
        yield app.test_client()

    os.unlink(dbpath)
    os.unlink(pgnpath)


def test_master_thumbnail_happy_path(master_client):
    resp = master_client.get("/api/openings/games/1/thumbnail.png?source=twic")
    assert resp.status_code == 200, resp.data
    assert resp.mimetype == "image/png"
    assert resp.data.startswith(PNG_MAGIC)


def test_master_thumbnail_defaults_to_twic(master_client):
    resp = master_client.get("/api/openings/games/1/thumbnail.png")
    assert resp.status_code == 200, resp.data
    assert resp.data.startswith(PNG_MAGIC)


def test_master_thumbnail_sets_immutable_cache(master_client):
    resp = master_client.get("/api/openings/games/1/thumbnail.png?source=twic")
    assert resp.headers["Cache-Control"] == "public, max-age=86400"


def test_master_thumbnail_requires_no_auth(master_client):
    resp = master_client.get("/api/openings/games/1/thumbnail.png?source=twic")
    assert resp.status_code == 200
    assert "WWW-Authenticate" not in resp.headers


def test_master_thumbnail_unknown_id_404(master_client):
    resp = master_client.get("/api/openings/games/999999/thumbnail.png?source=twic")
    assert resp.status_code == 404
    assert resp.is_json


def test_master_thumbnail_unknown_source_400(master_client):
    resp = master_client.get("/api/openings/games/1/thumbnail.png?source=chesscom")
    assert resp.status_code == 400
    assert resp.is_json


def test_master_thumbnail_lichess_source(master_client):
    """Lichess source renders from the exported PGN (mocked)."""
    from api import openings as openings_mod

    class _Resp:
        status_code = 200
        text = SAMPLE_PGN

    with patch.object(openings_mod.requests, "get", lambda *a, **k: _Resp()):
        resp = master_client.get("/api/openings/games/5/thumbnail.png?source=lichess")
    assert resp.status_code == 200, resp.data
    assert resp.data.startswith(PNG_MAGIC)


# ─── Shared user games (/api/games/shared/<token>/thumbnail.png) ──────────────

TOKEN = "abc123_share_token"


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeBuilder:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def execute(self):
        return _FakeResult(self._data)


def _fake_table(data):
    return lambda name: _FakeBuilder(data)


@pytest.fixture
def user_client():
    from flask import Flask
    from api.user_games import user_games_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(user_games_bp)
    return app.test_client()


def test_shared_thumbnail_happy_path(user_client):
    with patch("api.user_games.supabase") as mock_sb:
        mock_sb.table = _fake_table([{"pgn": SAMPLE_PGN}])
        resp = user_client.get(f"/api/games/shared/{TOKEN}/thumbnail.png")
    assert resp.status_code == 200, resp.data
    assert resp.mimetype == "image/png"
    assert resp.data.startswith(PNG_MAGIC)


def test_shared_thumbnail_is_public(user_client):
    with patch("api.user_games.supabase") as mock_sb:
        mock_sb.table = _fake_table([{"pgn": SAMPLE_PGN}])
        resp = user_client.get(f"/api/games/shared/{TOKEN}/thumbnail.png")
    assert resp.status_code == 200
    assert "WWW-Authenticate" not in resp.headers


def test_shared_thumbnail_sets_immutable_cache(user_client):
    with patch("api.user_games.supabase") as mock_sb:
        mock_sb.table = _fake_table([{"pgn": SAMPLE_PGN}])
        resp = user_client.get(f"/api/games/shared/{TOKEN}/thumbnail.png")
    assert resp.headers["Cache-Control"] == "public, max-age=86400"


def test_shared_thumbnail_unknown_token_404(user_client):
    with patch("api.user_games.supabase") as mock_sb:
        mock_sb.table = _fake_table([])
        resp = user_client.get("/api/games/shared/nope/thumbnail.png")
    assert resp.status_code == 404
    assert resp.is_json


def test_shared_thumbnail_unrenderable_pgn_404(user_client):
    """A row with empty/garbage PGN → 404, not a broken image."""
    with patch("api.user_games.supabase") as mock_sb:
        mock_sb.table = _fake_table([{"pgn": ""}])
        resp = user_client.get(f"/api/games/shared/{TOKEN}/thumbnail.png")
    assert resp.status_code == 404


# ─── Pure renderer (utils/board_image.py) ─────────────────────────────────────

def test_render_returns_valid_png():
    from utils.board_image import render_final_position_png

    png = render_final_position_png(SAMPLE_PGN)
    assert png is not None
    assert png.startswith(PNG_MAGIC)


def test_render_none_on_empty():
    from utils.board_image import render_final_position_png

    assert render_final_position_png("") is None
    assert render_final_position_png("   ") is None
    assert render_final_position_png(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
