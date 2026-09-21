"""Unit tests for Tools 6 & 7: get_user_repertoire / get_user_games.

Rows mirror the real tables (opening_repertoires + opening_nodes, user_games)
rather than an imagined schema — the previous fixtures matched columns that do
not exist in production, which is how the tools shipped broken.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.tools.user_data import (
    _handle_get_user_games,
    get_user_games,
    get_user_repertoire,
)

URL = "https://fake.supabase.co"
KEY = "fake-key"

REPERTOIRES = [
    {"id": "r1", "name": "Italian", "color": "w", "description": None, "is_primary": True,
     "starting_fen": None, "starting_move_line": "1. e4 e5 2. Nf3 Nc6 3. Bc4", "updated_at": "2026-05-01"},
    {"id": "r2", "name": "Najdorf", "color": "b", "description": "vs 1.e4", "is_primary": False,
     "starting_fen": None, "starting_move_line": "1. e4 c5", "updated_at": "2026-04-01"},
]
NODES = [
    {"repertoire_id": "r1", "move_number": 1, "is_white_move": True, "move_san": "e4",
     "opening_name": None, "eco_code": None, "notes": None, "is_critical": False},
    {"repertoire_id": "r1", "move_number": 1, "is_white_move": False, "move_san": "e5",
     "opening_name": None, "eco_code": None, "notes": None, "is_critical": False},
    {"repertoire_id": "r2", "move_number": 1, "is_white_move": True, "move_san": "e4",
     "opening_name": "Sicilian", "eco_code": "B90", "notes": "main line", "is_critical": True},
]
GAMES = [
    {"id": "g1", "title": None, "white": "user123", "black": "opp", "white_elo": 1500,
     "black_elo": 1550, "result": "1-0", "date": "2026.05.01", "event": None, "eco": "C50",
     "opening_name": "Italian Game", "source": "lichess", "is_favorite": False, "tags": [],
     "created_at": "2026-05-01T10:00:00", "pgn": "1. e4 e5 1-0"},
]


def _routed_get(routes):
    """httpx.get stand-in: picks canned rows by the table name in the URL."""
    def fake_get(url, params=None, headers=None, timeout=None):
        table = url.rsplit("/rest/v1/", 1)[1]
        resp = MagicMock()
        resp.json.return_value = routes[table]
        resp.raise_for_status = MagicMock()
        fake_get.calls.append((table, params))
        return resp
    fake_get.calls = []
    return fake_get


@pytest.mark.unit
class TestRepertoire:
    def test_queries_real_tables_and_attaches_lines(self):
        fake = _routed_get({"opening_repertoires": [dict(r) for r in REPERTOIRES],
                            "opening_nodes": [dict(n) for n in NODES]})
        with patch("src.tools.user_data.httpx.get", fake):
            out = get_user_repertoire("user123", supabase_url=URL, supabase_key=KEY)

        tables = [t for t, _ in fake.calls]
        assert tables == ["opening_repertoires", "opening_nodes"]
        assert fake.calls[0][1]["user_id"] == "eq.user123"
        assert fake.calls[1][1]["repertoire_id"] == "in.(r1,r2)"

        reps = out["repertoires"]
        assert [r["name"] for r in reps] == ["Italian", "Najdorf"]
        assert reps[0]["color"] == "white" and reps[1]["color"] == "black"
        assert [n["move_san"] for n in reps[0]["lines"]] == ["e4", "e5"]
        assert reps[1]["lines"][0]["eco_code"] == "B90"
        assert "repertoire_id" not in reps[1]["lines"][0]

    def test_color_filter_maps_to_db_letters(self):
        fake = _routed_get({"opening_repertoires": [], "opening_nodes": []})
        with patch("src.tools.user_data.httpx.get", fake):
            get_user_repertoire("user123", color="white", supabase_url=URL, supabase_key=KEY)
        assert fake.calls[0][1]["color"] == "eq.w"

    def test_bad_color_is_an_error(self):
        out = get_user_repertoire("user123", color="green", supabase_url=URL, supabase_key=KEY)
        assert "error" in out

    def test_empty_for_unknown_user(self):
        fake = _routed_get({"opening_repertoires": [], "opening_nodes": []})
        with patch("src.tools.user_data.httpx.get", fake):
            out = get_user_repertoire("nobody", supabase_url=URL, supabase_key=KEY)
        assert out["repertoires"] == []
        assert [t for t, _ in fake.calls] == ["opening_repertoires"]  # no node query

    def test_unconfigured_supabase_is_an_error_not_empty(self):
        out = get_user_repertoire("user123", supabase_url="", supabase_key="")
        assert "error" in out

    def test_http_failure_is_an_error_not_empty(self):
        with patch("src.tools.user_data.httpx.get", side_effect=RuntimeError("boom")):
            out = get_user_repertoire("user123", supabase_url=URL, supabase_key=KEY)
        assert "error" in out


@pytest.mark.unit
class TestUserGames:
    def test_query_shape_matches_user_games_table(self):
        fake = _routed_get({"user_games": GAMES})
        with patch("src.tools.user_data.httpx.get", fake):
            games = get_user_games("user123", limit=5, supabase_url=URL, supabase_key=KEY)
        table, params = fake.calls[0]
        assert table == "user_games"
        assert params["deleted_at"] == "is.null"
        assert params["order"] == "created_at.desc"  # no played_at column exists
        assert params["limit"] == "5"
        assert "pgn" in params["select"]
        assert games == GAMES

    def test_limit_clamped(self):
        fake = _routed_get({"user_games": []})
        with patch("src.tools.user_data.httpx.get", fake):
            get_user_games("user123", limit=500, supabase_url=URL, supabase_key=KEY)
        assert fake.calls[0][1]["limit"] == "50"

    def test_list_contract_kept_for_weakness_tracker(self):
        """weakness_tracker consumes a list; failure must still yield []."""
        with patch("src.tools.user_data.httpx.get", side_effect=RuntimeError("boom")):
            assert get_user_games("user123", supabase_url=URL, supabase_key=KEY) == []

    def test_handler_reports_failure_instead_of_no_games(self):
        with patch("src.tools.user_data.httpx.get", side_effect=RuntimeError("boom")), \
             patch("src.tools.user_data.SUPABASE_URL", URL), \
             patch("src.tools.user_data.SUPABASE_KEY", KEY):
            out = json.loads(_handle_get_user_games({"user_id": "user123"}))
        assert "error" in out

    def test_handler_returns_count_and_games(self):
        fake = _routed_get({"user_games": GAMES})
        with patch("src.tools.user_data.httpx.get", fake), \
             patch("src.tools.user_data.SUPABASE_URL", URL), \
             patch("src.tools.user_data.SUPABASE_KEY", KEY):
            out = json.loads(_handle_get_user_games({"user_id": "user123"}))
        assert out["count"] == 1
        assert out["games"][0]["opening_name"] == "Italian Game"
