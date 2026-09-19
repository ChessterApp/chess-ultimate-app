"""Unit tests for src.identity — student id resolution in tool handlers."""

import json
from unittest.mock import patch

import pytest

from src.identity import current_user_id, resolve_user_id
from src.sessions import session_store


@pytest.fixture(autouse=True)
def _clear_ctx():
    token = current_user_id.set("")
    yield
    current_user_id.reset(token)


@pytest.mark.unit
def test_session_wins_over_model_argument():
    session = session_store.create(user_id="user_real")
    assert resolve_user_id({"user_id": "user_guess"}, {"session_id": session.id}) == "user_real"


@pytest.mark.unit
def test_context_var_used_when_no_session():
    current_user_id.set("user_ctx")
    assert resolve_user_id({"user_id": "user_guess"}, {}) == "user_ctx"


@pytest.mark.unit
def test_model_argument_is_last_resort():
    assert resolve_user_id({"user_id": "user_guess"}, {}) == "user_guess"


@pytest.mark.unit
def test_anonymous_session_falls_through():
    session = session_store.create(user_id="anonymous")
    current_user_id.set("user_ctx")
    assert resolve_user_id({}, {"session_id": session.id}) == "user_ctx"


@pytest.mark.unit
def test_placeholder_argument_is_ignored():
    assert resolve_user_id({"user_id": "the user's ID"}, {}) == ""
    assert resolve_user_id({}, {}) == ""


@pytest.mark.unit
def test_unknown_session_falls_through():
    assert resolve_user_id({"user_id": "u1"}, {"session_id": "no-such-session"}) == "u1"


@pytest.mark.unit
def test_handler_uses_resolved_id():
    """get_user_games handler queries the session's user, not the model's guess."""
    from src.tools.user_data import _handle_get_user_games

    session = session_store.create(user_id="user_real")
    seen = {}

    def fake_query(user_id, limit, supabase_url=None, supabase_key=None):
        seen["user_id"] = user_id
        return []

    with patch("src.tools.user_data._query_user_games", fake_query):
        out = json.loads(_handle_get_user_games({"user_id": "user_guess"}, session_id=session.id))
    assert seen["user_id"] == "user_real"
    assert out["user_id"] == "user_real"
