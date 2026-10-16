"""Route map of the openings blueprint after the repertoire feature was removed.

The Database page's Master tab only searches positions: /games/by-position and
/positions/candidates must stay registered and respond; the repertoire, node,
training and game-link routes are gone.
"""

from unittest.mock import patch

import pytest
from flask import Flask

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.fixture
def client():
    from api import openings as openings_mod

    # No TWIC DB: the kept routes answer with their empty-result shape.
    with patch.object(openings_mod, "check_internal_db_exists", lambda: False):
        app = Flask(__name__)
        app.register_blueprint(openings_mod.openings_bp)
        app.config["TESTING"] = True
        yield app.test_client()


def _rules():
    from api.openings import openings_bp

    app = Flask(__name__)
    app.register_blueprint(openings_bp)
    return {(r.rule, m) for r in app.url_map.iter_rules() for m in r.methods}


def test_position_search_routes_still_registered():
    rules = _rules()
    for path in [
        "/api/openings/games/by-position",
        "/api/openings/positions/candidates",
        "/api/openings/games/position-count",
        "/api/openings/games/<int:game_id>/pgn",
        "/api/openings/games/lichess/<game_id>/pgn",
        "/api/openings/games/<int:game_id>/meta",
        "/api/openings/games/search",
        "/api/openings/games/search/stream",
        "/api/openings/games/internal/status",
        "/api/openings/positions/top-players",
    ]:
        assert (path, "GET") in rules, path
    assert ("/api/openings/_cache/invalidate", "POST") in rules


def test_no_repertoire_routes_registered():
    paths = {rule for rule, _ in _rules()}
    for prefix in ("/api/openings/repertoires", "/api/openings/nodes", "/api/openings/training"):
        assert not any(p.startswith(prefix) for p in paths), prefix


def test_games_by_position_responds(client):
    resp = client.get(f"/api/openings/games/by-position?fen={START_FEN}&limit=50")
    assert resp.status_code == 200
    assert resp.get_json() == {"games": [], "total": 0, "indexed": False}


def test_position_candidates_responds(client):
    resp = client.get(f"/api/openings/positions/candidates?fen={START_FEN}&limit=20")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["moves"] == []


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/openings/repertoires"),
    ("POST", "/api/openings/repertoires"),
    ("GET", "/api/openings/repertoires/rep-1"),
    ("PUT", "/api/openings/repertoires/rep-1"),
    ("DELETE", "/api/openings/repertoires/rep-1"),
    ("PUT", "/api/openings/repertoires/rep-1/starting-position"),
    ("GET", "/api/openings/repertoires/rep-1/pgn"),
    ("POST", "/api/openings/repertoires/rep-1/import"),
    ("POST", "/api/openings/repertoires/rep-1/repair-tree"),
    ("POST", "/api/openings/nodes"),
    ("PUT", "/api/openings/nodes/node-1"),
    ("DELETE", "/api/openings/nodes/node-1"),
    ("POST", "/api/openings/nodes/node-1/arrows"),
    ("DELETE", "/api/openings/nodes/node-1/arrows/arrow-1"),
    ("GET", "/api/openings/nodes/node-1/games"),
    ("POST", "/api/openings/nodes/node-1/games"),
    ("GET", "/api/openings/training/due"),
    ("POST", "/api/openings/training/result"),
    ("GET", "/api/openings/training/stats"),
    ("DELETE", "/api/openings/games/link-1"),
    ("DELETE", "/api/openings/games/123"),
])
def test_removed_routes_are_gone(client, method, path):
    resp = client.open(path, method=method)
    assert resp.status_code in (404, 405)
