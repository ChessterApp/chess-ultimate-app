"""Unit tests for Supabase-backed session persistence.

No live-database access — a mocked supabase client (httpx) and an in-memory
fake backend stand in for Supabase.
"""

import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.session_persistence import SessionPersistence
from src.sessions import SessionStore


class FakePersistence:
    """In-memory stand-in for SessionPersistence + the Supabase tables.

    Records write-through calls and serves lazy-loads, so a fresh SessionStore
    can reconstruct a session after a simulated restart.
    """

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.calls: list[str] = []

    def persist_session(self, session_id, user_id, board_state):
        self.calls.append("persist_session")
        self.sessions[session_id] = {
            "id": session_id,
            "user_id": user_id,
            "board_state": board_state,
        }
        self.messages.setdefault(session_id, [])

    def persist_message(self, session_id, role, content, source, extra=None, evt=None):
        self.calls.append("persist_message")
        row = {"role": role, "content": content, "source": source}
        if extra:
            row.update(extra)
        self.messages.setdefault(session_id, []).append(row)

    def update_board_state(self, session_id, fen):
        self.calls.append("update_board_state")
        if session_id in self.sessions:
            self.sessions[session_id]["board_state"] = fen

    def delete_session(self, session_id):
        self.calls.append("delete_session")
        self.sessions.pop(session_id, None)
        self.messages.pop(session_id, None)

    def load_session(self, session_id):
        return self.sessions.get(session_id)

    def load_user_sessions(self, user_id):
        return [s for s in self.sessions.values() if s["user_id"] == user_id]

    def load_messages(self, session_id):
        return list(self.messages.get(session_id, []))


@pytest.mark.unit
class TestWriteThrough:
    def setup_method(self):
        self.backend = FakePersistence()
        self.store = SessionStore(persistence=self.backend)

    def test_create_persists_session(self):
        session = self.store.create(user_id="user1")
        assert session.id in self.backend.sessions
        assert "persist_session" in self.backend.calls

    def test_add_message_persists(self):
        session = self.store.create(user_id="user1")
        session.add_message("user", "hi", source="voice")
        rows = self.backend.messages[session.id]
        assert rows == [{"role": "user", "content": "hi", "source": "voice"}]

    def test_set_board_state_persists(self):
        session = self.store.create(user_id="user1")
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        session.set_board_state(fen)
        assert self.backend.sessions[session.id]["board_state"] == fen

    def test_delete_removes_from_backend(self):
        session = self.store.create(user_id="user1")
        assert self.store.delete(session.id) is True
        assert session.id not in self.backend.sessions


@pytest.mark.unit
class TestLazyLoadAfterRestart:
    def test_get_reconstructs_session_after_restart(self):
        backend = FakePersistence()
        store = SessionStore(persistence=backend)
        session = store.create(user_id="user1")
        session.add_message("user", "What is e4?")
        session.add_message("assistant", "King's Pawn.", source="voice")
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        session.set_board_state(fen)
        sid = session.id

        # Simulate Hermes restart: fresh store, same (persisted) backend data.
        fresh = SessionStore(persistence=backend)
        loaded = fresh.get(sid, user_id="user1")

        assert loaded is not None
        assert loaded.id == sid
        assert loaded.board_state == fen
        assert [(m.role, m.content, m.source) for m in loaded.messages] == [
            ("user", "What is e4?", "text"),
            ("assistant", "King's Pawn.", "voice"),
        ]

    def test_lazy_loaded_session_stays_scoped_by_user(self):
        backend = FakePersistence()
        store = SessionStore(persistence=backend)
        sid = store.create(user_id="user1").id

        fresh = SessionStore(persistence=backend)
        assert fresh.get(sid, user_id="user2") is None
        assert fresh.get(sid, user_id="user1") is not None

    def test_lazy_loaded_messages_are_not_re_persisted(self):
        backend = FakePersistence()
        store = SessionStore(persistence=backend)
        session = store.create(user_id="user1")
        session.add_message("user", "hi")
        sid = session.id

        fresh = SessionStore(persistence=backend)
        loaded = fresh.get(sid)
        # Reconstruction must not duplicate the persisted message.
        assert len(backend.messages[sid]) == 1
        assert len(loaded.messages) == 1

    def test_list_merges_backend_sessions_after_restart(self):
        backend = FakePersistence()
        store = SessionStore(persistence=backend)
        store.create(user_id="user1")
        store.create(user_id="user1")
        store.create(user_id="user2")

        fresh = SessionStore(persistence=backend)
        assert len(fresh.list("user1")) == 2
        assert len(fresh.list("user2")) == 1


@pytest.mark.unit
class TestGracefulDegradation:
    def test_no_env_vars_operates_in_memory(self):
        # Explicitly-empty creds => persistence disabled, pure in-memory.
        store = SessionStore(persistence=SessionPersistence(url="", key=""))
        session = store.create(user_id="user1")
        session.add_message("user", "hi")
        session.set_board_state(
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        )
        assert store.get(session.id) is session
        assert store.delete(session.id) is True

    def test_disabled_backend_makes_no_http_calls(self):
        with patch("src.session_persistence.httpx") as mock_httpx:
            store = SessionStore(persistence=SessionPersistence(url="", key=""))
            session = store.create(user_id="user1")
            session.add_message("user", "hi")
            store.get(session.id)
            store.list("user1")
            store.delete(session.id)
            mock_httpx.post.assert_not_called()
            mock_httpx.get.assert_not_called()
            mock_httpx.patch.assert_not_called()
            mock_httpx.delete.assert_not_called()

    def test_missing_session_returns_none(self):
        store = SessionStore(persistence=SessionPersistence(url="", key=""))
        assert store.get("does-not-exist") is None


@pytest.mark.unit
class TestSessionPersistenceHttp:
    """Directly exercise the httpx wiring with a mocked supabase client."""

    def _persistence(self):
        return SessionPersistence(url="https://sb.example", key="secret")

    def test_enabled_flag(self):
        assert self._persistence().enabled is True
        assert SessionPersistence(url="", key="").enabled is False

    def test_persist_session_posts_row(self):
        p = self._persistence()
        with patch("src.session_persistence.httpx") as mock_httpx:
            p._persist_session("sid-1", "user1", "fen-here")
            mock_httpx.post.assert_called_once()
            args, kwargs = mock_httpx.post.call_args
            assert args[0].endswith("/rest/v1/coach_sessions")
            assert kwargs["json"]["id"] == "sid-1"
            assert kwargs["json"]["user_id"] == "user1"
            assert kwargs["json"]["board_state"] == "fen-here"

    def test_persist_message_posts_row(self):
        p = self._persistence()
        with patch("src.session_persistence.httpx") as mock_httpx:
            p._persist_message("sid-1", "user", "hello", "voice")
            args, kwargs = mock_httpx.post.call_args
            assert args[0].endswith("/rest/v1/coach_messages")
            assert kwargs["json"] == {
                "session_id": "sid-1",
                "role": "user",
                "content": "hello",
                "source": "voice",
            }

    def test_persist_message_includes_extra_columns(self):
        p = self._persistence()
        with patch("src.session_persistence.httpx") as mock_httpx:
            p._persist_message(
                "sid-1", "assistant", "hi", "text",
                extra={"turn_id": "t1", "model": "gpt", "latency_ms": 42, "prompt_tokens": None},
            )
            _, kwargs = mock_httpx.post.call_args
            body = kwargs["json"]
            assert body["turn_id"] == "t1"
            assert body["model"] == "gpt"
            assert body["latency_ms"] == 42
            # None-valued extras are dropped (never sent).
            assert "prompt_tokens" not in body

    def test_persist_message_retries_without_extra_on_missing_column(self):
        p = self._persistence()
        # First POST fails with a PostgREST "column not found" (PGRST204);
        # the write must retry with just the base row.
        err_resp = MagicMock()
        err_resp.status_code = 400
        err_resp.text = '{"code":"PGRST204","message":"Column turn_id not found"}'
        err = httpx.HTTPStatusError("bad", request=MagicMock(), response=err_resp)

        ok_resp = MagicMock()
        ok_resp.raise_for_status = MagicMock()
        fail_resp = MagicMock()
        fail_resp.raise_for_status = MagicMock(side_effect=err)

        with patch("src.session_persistence.httpx") as mock_httpx:
            mock_httpx.HTTPStatusError = httpx.HTTPStatusError
            mock_httpx.post.side_effect = [fail_resp, ok_resp]
            p._persist_message(
                "sid-1", "assistant", "hi", "text", extra={"turn_id": "t1"}
            )
            assert mock_httpx.post.call_count == 2
            # Retry payload is the base row with no enrichment columns.
            retry_body = mock_httpx.post.call_args_list[1].kwargs["json"]
            assert "turn_id" not in retry_body
            assert retry_body["role"] == "assistant"

    def test_persist_message_emits_persistence_failure_when_both_fail(self):
        p = self._persistence()
        with patch("src.session_persistence.httpx") as mock_httpx, \
                patch("src.event_logger.log_event") as mock_log:
            mock_httpx.post.side_effect = RuntimeError("network down")
            p._persist_message(
                "sid-1", "assistant", "hi", "text",
                extra={"turn_id": "t1"},
                evt={"user_id": "u1", "turn_id": "t1", "surface": "text", "model": "gpt"},
            )
            mock_log.assert_called_once()
            assert mock_log.call_args.args[0] == "persistence_failure"
            assert mock_log.call_args.kwargs["severity"] == "error"
            assert mock_log.call_args.kwargs["turn_id"] == "t1"


@pytest.mark.unit
class TestFirstTurnRace:
    """Task 5: the message insert must never win the race against the session
    upsert it references — even when the session insert is slow."""

    def _persistence(self):
        return SessionPersistence(url="https://sb.example", key="secret")

    def test_message_insert_waits_for_slow_session_insert(self):
        import time

        p = self._persistence()
        order: list[str] = []
        lock = threading.Lock()

        def fake_post(url, *args, **kwargs):
            # The session insert is slow; the message insert is instant. Without
            # the ordering gate the (instant) message POST would land first —
            # exactly the FK-violation race. Record each POST as it lands.
            if url.endswith("/rest/v1/coach_sessions"):
                time.sleep(0.2)
                with lock:
                    order.append("session")
            else:
                with lock:
                    order.append("message")
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            return resp

        with patch("src.session_persistence.httpx") as mock_httpx:
            mock_httpx.post.side_effect = fake_post
            # Fire both as the real request path does: session first (create),
            # then the first user message — both on background threads.
            p.persist_session("sid-race", "user1", "fen")
            p.persist_message("sid-race", "user", "first message", "voice")

            # Wait for both background writes to land (bounded).
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                with lock:
                    if len(order) >= 2:
                        break
                time.sleep(0.01)

        assert order == ["session", "message"], (
            f"message insert raced ahead of the session insert: {order}"
        )

    def test_message_does_not_hang_when_no_session_pending(self):
        """A message with no pending session write proceeds immediately."""
        import time

        p = self._persistence()
        landed = threading.Event()

        def fake_post(url, *args, **kwargs):
            landed.set()
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            return resp

        with patch("src.session_persistence.httpx") as mock_httpx:
            mock_httpx.post.side_effect = fake_post
            # No persist_session() first — the message must not block on a gate.
            p.persist_message("sid-orphan", "user", "hi", "voice")
            assert landed.wait(timeout=2.0) is True

    def test_load_session_parses_first_row(self):
        p = self._persistence()
        resp = MagicMock()
        resp.json.return_value = [{"id": "sid-1", "user_id": "user1", "board_state": "f"}]
        with patch("src.session_persistence.httpx") as mock_httpx:
            mock_httpx.get.return_value = resp
            row = p.load_session("sid-1")
            assert row["id"] == "sid-1"

    def test_load_session_returns_none_on_empty(self):
        p = self._persistence()
        resp = MagicMock()
        resp.json.return_value = []
        with patch("src.session_persistence.httpx") as mock_httpx:
            mock_httpx.get.return_value = resp
            assert p.load_session("sid-1") is None

    def test_load_messages_orders_by_id(self):
        p = self._persistence()
        resp = MagicMock()
        resp.json.return_value = [{"role": "user", "content": "hi", "source": "text"}]
        with patch("src.session_persistence.httpx") as mock_httpx:
            mock_httpx.get.return_value = resp
            rows = p.load_messages("sid-1")
            assert rows[0]["content"] == "hi"
            _, kwargs = mock_httpx.get.call_args
            assert kwargs["params"]["order"] == "id.asc"

    def test_read_swallows_exceptions(self):
        p = self._persistence()
        with patch("src.session_persistence.httpx") as mock_httpx:
            mock_httpx.get.side_effect = RuntimeError("boom")
            assert p.load_session("sid-1") is None
            assert p.load_user_sessions("user1") == []
            assert p.load_messages("sid-1") == []

    def test_write_swallows_exceptions(self):
        p = self._persistence()
        with patch("src.session_persistence.httpx") as mock_httpx:
            mock_httpx.post.side_effect = RuntimeError("boom")
            mock_httpx.patch.side_effect = RuntimeError("boom")
            mock_httpx.delete.side_effect = RuntimeError("boom")
            # None of these may raise.
            p._persist_session("sid-1", "user1", "f")
            p._persist_message("sid-1", "user", "hi", "text")
            p._update_board_state("sid-1", "f")
            p._delete_session("sid-1")
