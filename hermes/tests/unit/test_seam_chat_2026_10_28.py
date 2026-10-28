"""Seam audit 28.10 (chat): the interface language reaches the puzzle/topic tools (text pre-step and voice
tool calls), and a session reloaded after a restart keeps the real time of its messages."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src import tool_bridge
from src.middleware.rate_limiter import voice_tool_rate_limiter
from src.server import app
from src.sessions import SessionStore, session_store

USER_HEADERS = {"X-User-Id": "seam-user"}


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    voice_tool_rate_limiter.reset()
    yield
    session_store._sessions.clear()
    voice_tool_rate_limiter.reset()


def _capture_dispatch(name: str, body: dict) -> dict:
    captured: dict = {}

    def _fake(tool, args, **kwargs):
        captured["args"] = dict(args)
        return json.dumps({"ok": True})

    with patch.object(tool_bridge.registry, "dispatch", side_effect=_fake):
        resp = TestClient(app).post(f"/api/coach/tool/{name}", headers=USER_HEADERS, json=body)
    assert resp.status_code == 200, resp.text
    return captured["args"]


# ── locale: voice tool calls ───────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("tool", ["get_puzzle", "get_topic"])
def test_voice_tool_call_gets_the_interface_locale(tool):
    args = _capture_dispatch(tool, {"args": {"theme": "pin", "topic": "pin"}, "locale": "kz"})
    assert args["locale"] == "kz"


@pytest.mark.unit
def test_voice_tool_call_keeps_the_models_own_locale():
    args = _capture_dispatch("get_topic", {"args": {"topic": "pin", "locale": "en"}, "locale": "kz"})
    assert args["locale"] == "en"


@pytest.mark.unit
def test_locale_not_added_to_tools_that_do_not_read_it():
    args = _capture_dispatch("board_control", {"args": {"action_type": "reset"}, "locale": "kz"})
    assert "locale" not in args


@pytest.mark.unit
def test_unknown_locale_is_ignored():
    args = _capture_dispatch("get_puzzle", {"args": {}, "locale": "de"})
    assert "locale" not in args


# ── locale: the text pre-step that puts a puzzle up ────────────────────────


@pytest.mark.unit
def test_puzzle_prestep_passes_locale_to_get_puzzle():
    from src import server

    store = SessionStore()
    session = store.create(user_id="seam-user")
    captured: dict = {}

    def _fake_get_puzzle(args, **kwargs):
        captured["args"] = dict(args)
        return json.dumps({"puzzles": []})

    with patch("src.tools.puzzles._handle_get_puzzle", side_effect=_fake_get_puzzle):
        server._puzzle_prestep(session, session.active_board(), "дай задачу на связку", "seam-user", "kz")
    assert captured["args"].get("locale") == "kz"


# ── message time after a restart ───────────────────────────────────────────


class _Rows:
    """The Supabase rows of one session, as SessionPersistence.load_* returns them."""

    def __init__(self, session_row, message_rows):
        self.session_row = session_row
        self.message_rows = message_rows

    def load_session(self, session_id):
        return self.session_row if session_id == self.session_row["id"] else None

    def load_boards(self, session_id):
        return []

    def load_messages(self, session_id):
        return list(self.message_rows)

    def load_user_sessions(self, user_id):
        return [self.session_row]

    def persist_session(self, *a, **k):
        pass

    def persist_message(self, *a, **k):
        pass


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()


@pytest.mark.unit
def test_reloaded_messages_keep_their_stored_time():
    rows = _Rows(
        {"id": "s-old", "user_id": "seam-user", "created_at": "2026-10-01T09:00:00+00:00"},
        [
            {"role": "user", "content": "hi", "source": "voice", "created_at": "2026-10-01T09:00:05.5+00:00",
             "client_ts": "2026-10-01T09:00:04Z"},
            {"role": "assistant", "content": "hello", "source": "text", "created_at": "2026-10-01T09:00:09+00:00",
             "client_ts": None},
        ],
    )
    store = SessionStore(persistence=rows)
    session = store.get("s-old", "seam-user")
    assert session is not None
    # the utterance time the client stamped, else the row's own time
    assert session.messages[0].timestamp == pytest.approx(_epoch("2026-10-01T09:00:04Z"), abs=0.01)
    assert session.messages[1].timestamp == pytest.approx(_epoch("2026-10-01T09:00:09+00:00"), abs=0.01)
    assert session.created_at == pytest.approx(_epoch("2026-10-01T09:00:00+00:00"), abs=0.01)


@pytest.mark.unit
def test_sessions_list_orders_reloaded_sessions_by_real_activity():
    rows = _Rows(
        {"id": "s-old", "user_id": "seam-user", "created_at": "2026-10-01T09:00:00+00:00"},
        [{"role": "user", "content": "hi", "source": "text", "created_at": "2026-10-01T09:00:05+00:00"}],
    )
    store = SessionStore(persistence=rows)
    with patch("src.server.session_store", store):
        listed = TestClient(app).get("/api/coach/sessions", headers=USER_HEADERS).json()
        msgs = TestClient(app).get("/api/coach/sessions/s-old/messages", headers=USER_HEADERS).json()
    assert listed[0]["updated_at"] == pytest.approx(_epoch("2026-10-01T09:00:05+00:00"), abs=0.01)
    assert msgs["messages"][0]["timestamp"] == pytest.approx(_epoch("2026-10-01T09:00:05+00:00"), abs=0.01)


@pytest.mark.unit
def test_appended_message_takes_the_client_time():
    store = SessionStore(persistence=_Rows({"id": "x", "user_id": "u"}, []))
    session = store.create(user_id="seam-user")
    session.add_message("user", "spoken", source="voice", extra={"client_ts": "2026-10-28T08:00:00.000Z"})
    assert session.messages[0].timestamp == pytest.approx(_epoch("2026-10-28T08:00:00Z"), abs=0.01)


@pytest.mark.unit
def test_bad_stored_time_falls_back_to_now():
    rows = _Rows({"id": "s-bad", "user_id": "seam-user", "created_at": "not a date"},
                 [{"role": "user", "content": "hi", "source": "text", "created_at": "garbage"}])
    session = SessionStore(persistence=rows).get("s-bad", "seam-user")
    assert session is not None and session.messages[0].timestamp > 1_700_000_000
