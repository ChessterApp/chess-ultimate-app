"""Unit tests for /api/coach/* FastAPI routes."""

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.server import app, clear_voice_profile_cache
from src.sessions import session_store, Session
from src.middleware.rate_limiter import (
    rate_limiter,
    voice_tool_rate_limiter,
    voice_token_rate_limiter,
)
from src.user_profile import UserProfile


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Clear session store and rate-limit state between tests."""
    session_store._sessions.clear()
    rate_limiter.reset()
    voice_tool_rate_limiter.reset()
    voice_token_rate_limiter.reset()
    clear_voice_profile_cache()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()
    voice_tool_rate_limiter.reset()
    voice_token_rate_limiter.reset()
    clear_voice_profile_cache()


USER_HEADERS = {"X-User-Id": "test-user-123"}


@pytest.mark.unit
class TestCoachSessions:
    """Tests for GET/POST /api/coach/sessions."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_list_sessions_empty(self):
        resp = self.client.get("/api/coach/sessions", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_session(self):
        resp = self.client.post(
            "/api/coach/sessions",
            headers=USER_HEADERS,
            json={},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert body["message_count"] == 0

    def test_list_sessions_after_create(self):
        self.client.post("/api/coach/sessions", headers=USER_HEADERS, json={})
        self.client.post("/api/coach/sessions", headers=USER_HEADERS, json={})

        resp = self.client.get("/api/coach/sessions", headers=USER_HEADERS)
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 2

    def test_sessions_scoped_by_user(self):
        self.client.post("/api/coach/sessions", headers=USER_HEADERS, json={})
        resp = self.client.get(
            "/api/coach/sessions",
            headers={"X-User-Id": "other-user"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_sessions_require_user_id(self):
        resp = self.client.get("/api/coach/sessions")
        assert resp.status_code == 401

    def test_create_session_requires_user_id(self):
        resp = self.client.post("/api/coach/sessions", json={})
        assert resp.status_code == 401


@pytest.mark.unit
class TestCoachSessionMessages:
    """Tests for GET/POST /api/coach/sessions/{id}/messages."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_get_messages_404_for_unknown_session(self):
        resp = self.client.get(
            "/api/coach/sessions/does-not-exist/messages", headers=USER_HEADERS
        )
        assert resp.status_code == 404

    def test_get_messages_returns_list(self):
        session = session_store.create(user_id="test-user-123")
        session.add_message("user", "What is e4?")
        session.add_message("assistant", "The King's Pawn opening.")

        resp = self.client.get(
            f"/api/coach/sessions/{session.id}/messages", headers=USER_HEADERS
        )
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "What is e4?"
        assert messages[0]["source"] == "text"
        assert "timestamp" in messages[0]

    def test_get_messages_limit(self):
        session = session_store.create(user_id="test-user-123")
        for i in range(5):
            session.add_message("user", f"msg {i}")

        resp = self.client.get(
            f"/api/coach/sessions/{session.id}/messages?limit=2",
            headers=USER_HEADERS,
        )
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        assert len(messages) == 2
        # Last N, oldest-first order preserved.
        assert messages[0]["content"] == "msg 3"
        assert messages[1]["content"] == "msg 4"

    def test_get_messages_scoped_by_user(self):
        session = session_store.create(user_id="test-user-123")
        session.add_message("user", "secret")

        resp = self.client.get(
            f"/api/coach/sessions/{session.id}/messages",
            headers={"X-User-Id": "other-user"},
        )
        assert resp.status_code == 404

    def test_get_messages_requires_user_id(self):
        session = session_store.create(user_id="test-user-123")
        resp = self.client.get(f"/api/coach/sessions/{session.id}/messages")
        assert resp.status_code == 401

    def test_post_message_appends_without_agent_turn(self):
        session = session_store.create(user_id="test-user-123")

        resp = self.client.post(
            f"/api/coach/sessions/{session.id}/messages",
            headers=USER_HEADERS,
            json={"role": "user", "content": "spoken hello", "source": "voice"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["message_count"] == 1

        stored = session_store.get(session.id, "test-user-123")
        assert len(stored.messages) == 1
        assert stored.messages[0].role == "user"
        assert stored.messages[0].content == "spoken hello"
        assert stored.messages[0].source == "voice"

    def test_post_message_threads_client_ts_and_turn_id(self):
        """Task 4: utterance time + turn id reach persist_message as extra."""
        from unittest.mock import MagicMock, patch

        from src.sessions import SessionStore

        # A recording persistence backend captures the extra columns the endpoint
        # builds (client_ts + turn_id), without needing a live Supabase.
        fake = MagicMock()
        store = SessionStore(persistence=fake)
        session = store.create(user_id="test-user-123", session_id="sess-ts")

        with patch("src.server.session_store", store):
            resp = self.client.post(
                f"/api/coach/sessions/{session.id}/messages",
                headers=USER_HEADERS,
                json={
                    "role": "user",
                    "content": "spoken hello",
                    "source": "voice",
                    "client_ts": "2026-09-08T12:00:00.000Z",
                    "turn_id": "t-voice-1",
                },
            )
        assert resp.status_code == 200
        assert fake.persist_message.called
        args, kwargs = fake.persist_message.call_args
        # add_message passes (session_id, role, content, source) positionally.
        assert args[3] == "voice"
        assert kwargs["extra"] == {
            "client_ts": "2026-09-08T12:00:00.000Z",
            "turn_id": "t-voice-1",
        }

    def test_post_message_defaults_source_to_text(self):
        session = session_store.create(user_id="test-user-123")
        resp = self.client.post(
            f"/api/coach/sessions/{session.id}/messages",
            headers=USER_HEADERS,
            json={"role": "assistant", "content": "hi"},
        )
        assert resp.status_code == 200
        stored = session_store.get(session.id, "test-user-123")
        assert stored.messages[0].source == "text"

    def test_post_message_creates_session_if_missing(self):
        resp = self.client.post(
            "/api/coach/sessions/brand-new-id/messages",
            headers=USER_HEADERS,
            json={"role": "user", "content": "hello"},
        )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "brand-new-id"
        stored = session_store.get("brand-new-id", "test-user-123")
        assert stored is not None
        assert len(stored.messages) == 1

    def test_post_message_rejects_invalid_role(self):
        session = session_store.create(user_id="test-user-123")
        resp = self.client.post(
            f"/api/coach/sessions/{session.id}/messages",
            headers=USER_HEADERS,
            json={"role": "system", "content": "nope"},
        )
        assert resp.status_code == 400

    def test_post_message_scoped_by_user(self):
        session = session_store.create(user_id="test-user-123")
        # A different user hitting the owner's id must be refused (404), never
        # allowed to append to or clobber the owner's session.
        resp = self.client.post(
            f"/api/coach/sessions/{session.id}/messages",
            headers={"X-User-Id": "other-user"},
            json={"role": "user", "content": "intruder"},
        )
        assert resp.status_code == 404
        owner_session = session_store.get(session.id, "test-user-123")
        assert owner_session is not None
        assert len(owner_session.messages) == 0

    def test_post_message_requires_user_id(self):
        resp = self.client.post(
            "/api/coach/sessions/some-id/messages",
            json={"role": "user", "content": "hi"},
        )
        assert resp.status_code == 401


@pytest.mark.unit
class TestCoachProfile:
    """Tests for GET/PUT /api/coach/profile."""

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.load_user_profile")
    def test_get_profile(self, mock_load):
        mock_load.return_value = UserProfile(
            user_id="test-user-123",
            rating=1500,
            goals=["improve tactics"],
            style="aggressive",
        )
        resp = self.client.get("/api/coach/profile", headers=USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "test-user-123"
        assert body["rating"] == 1500
        assert body["goals"] == ["improve tactics"]
        assert body["style"] == "aggressive"
        mock_load.assert_called_once_with("test-user-123")

    def test_get_profile_requires_user_id(self):
        resp = self.client.get("/api/coach/profile")
        assert resp.status_code == 401

    @patch("src.server.save_user_profile")
    def test_update_profile(self, mock_save):
        mock_save.return_value = True
        resp = self.client.put(
            "/api/coach/profile",
            headers=USER_HEADERS,
            json={
                "rating": 1600,
                "goals": ["endgame mastery"],
                "preferred_openings": ["Sicilian"],
                "weaknesses": ["time management"],
                "style": "positional",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "test-user-123"
        assert body["rating"] == 1600
        assert body["goals"] == ["endgame mastery"]
        assert body["preferred_openings"] == ["Sicilian"]
        assert body["style"] == "positional"
        mock_save.assert_called_once()

    @patch("src.server.save_user_profile")
    def test_update_profile_defaults(self, mock_save):
        mock_save.return_value = True
        resp = self.client.put(
            "/api/coach/profile",
            headers=USER_HEADERS,
            json={},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rating"] == 1200
        assert body["style"] == "unknown"

    def test_update_profile_requires_user_id(self):
        resp = self.client.put("/api/coach/profile", json={})
        assert resp.status_code == 401


def _parse_sse(text: str) -> list[dict]:
    """Parse an SSE response body into a list of decoded `data:` frames."""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def _deltas(events: list[dict]) -> str:
    """Concatenate all `delta` frames into the full message."""
    return "".join(e["delta"] for e in events if "delta" in e)


@pytest.mark.unit
class TestCoachChat:
    """Tests for POST /api/coach/chat (SSE token streaming)."""

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_streams_event_stream_content_type(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "The Sicilian Defense is a strong reply to 1.e4."
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "What is the Sicilian Defense?"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_deltas_reconstruct_message(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        full = "The Sicilian Defense is a strong reply to 1.e4."
        agent_instance = MagicMock()
        agent_instance.chat.return_value = full
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "What is the Sicilian Defense?"},
        )
        events = _parse_sse(resp.text)
        assert _deltas(events) == full

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_streams_real_tokens_via_callback(self, mock_profile, mock_agent):
        """When the agent supports a stream callback, real tokens stream through
        and still concatenate to the final message."""
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        chunks = ["The ", "Sicilian ", "Defense."]

        def _chat(message, stream_callback=None):
            for c in chunks:
                if stream_callback:
                    stream_callback(c)
            return "".join(chunks)

        agent_instance = MagicMock()
        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "What is the Sicilian Defense?"},
        )
        events = _parse_sse(resp.text)
        delta_frames = [e for e in events if "delta" in e]
        # Each chunk arrived as its own delta frame (real token streaming).
        assert [e["delta"] for e in delta_frames] == chunks
        assert _deltas(events) == "".join(chunks)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_final_done_event_has_session_id(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Hello!"
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Hi"},
        )
        events = _parse_sse(resp.text)
        done = events[-1]
        assert done.get("done") is True
        assert done.get("session_id")
        session = session_store.get(done["session_id"], "test-user-123")
        assert session is not None

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_persists_assistant_message(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        full = "The King's Pawn opening."
        agent_instance = MagicMock()
        agent_instance.chat.return_value = full
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "What is e4?"},
        )
        events = _parse_sse(resp.text)
        session_id = events[-1]["session_id"]
        session = session_store.get(session_id, "test-user-123")
        assert session is not None
        assert len(session.messages) == 2  # user + assistant
        assert session.messages[-1].role == "assistant"
        assert session.messages[-1].content == full

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_with_fen(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Interesting position."
        mock_agent.return_value = agent_instance

        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Analyze this", "fen": fen},
        )
        assert resp.status_code == 200
        session_id = _parse_sse(resp.text)[-1]["session_id"]
        session = session_store.get(session_id, "test-user-123")
        assert session.board_state == fen

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_with_existing_session(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Response"
        mock_agent.return_value = agent_instance

        session = session_store.create(user_id="test-user-123")
        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Continue", "session_id": session.id},
        )
        assert resp.status_code == 200
        assert _parse_sse(resp.text)[-1]["session_id"] == session.id

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_emits_board_actions(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Let me show you."

        def _on_chat(message, stream_callback=None):
            # Simulate a tool emitting a board action captured by the callback.
            agent_instance.tool_complete_callback(
                "call-1",
                "highlight_squares",
                {},
                json.dumps({"type": "highlight_squares", "squares": ["e4"]}),
            )
            return "Let me show you."

        agent_instance.chat.side_effect = _on_chat
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Show me the center"},
        )
        events = _parse_sse(resp.text)
        board_events = [e for e in events if "board_actions" in e]
        assert board_events
        assert board_events[0]["board_actions"][0]["type"] == "highlight_squares"

    def test_chat_requires_user_id(self):
        resp = self.client.post(
            "/api/coach/chat",
            json={"message": "Hello"},
        )
        assert resp.status_code == 401

    @patch("src.server.build_system_prompt")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_passes_locale(self, mock_profile, mock_agent, mock_prompt):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Привет!"
        mock_agent.return_value = agent_instance
        mock_prompt.return_value = "system prompt"

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Привет", "locale": "ru"},
        )
        assert resp.status_code == 200
        # Drain the stream so the endpoint runs to completion.
        _parse_sse(resp.text)
        mock_prompt.assert_called_once()
        call_kwargs = mock_prompt.call_args
        assert call_kwargs.kwargs.get("locale") == "ru"

    @patch("src.server.build_system_prompt")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_locale_defaults_none(self, mock_profile, mock_agent, mock_prompt):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Hello!"
        mock_agent.return_value = agent_instance
        mock_prompt.return_value = "system prompt"

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Hello"},
        )
        assert resp.status_code == 200
        _parse_sse(resp.text)
        mock_prompt.assert_called_once()
        call_kwargs = mock_prompt.call_args
        assert call_kwargs.kwargs.get("locale") is None

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_agent_error_emits_error_frame(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.side_effect = RuntimeError("model unavailable")
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Hello"},
        )
        # The stream itself opens successfully; the failure is an SSE error frame.
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        error_events = [e for e in events if "error" in e]
        assert error_events
        assert "model unavailable" in error_events[0]["error"]
        # No trailing done event when the agent fails.
        assert not any("done" in e for e in events)


@pytest.mark.unit
class TestSaveUserProfile:
    """Tests for save_user_profile function."""

    @patch("src.user_profile.httpx.post")
    def test_save_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from src.user_profile import save_user_profile

        profile = UserProfile(user_id="u1", rating=1500, goals=["tactics"])
        result = save_user_profile(
            profile, supabase_url="https://fake.supabase.co", supabase_key="key"
        )
        assert result is True
        mock_post.assert_called_once()

    def test_save_no_supabase(self):
        from src.user_profile import save_user_profile

        profile = UserProfile(user_id="u1")
        result = save_user_profile(profile, supabase_url="", supabase_key="")
        assert result is False

    @patch("src.user_profile.httpx.post")
    def test_save_error(self, mock_post):
        mock_post.side_effect = Exception("connection refused")

        from src.user_profile import save_user_profile

        profile = UserProfile(user_id="u1")
        result = save_user_profile(
            profile, supabase_url="https://fake.supabase.co", supabase_key="key"
        )
        assert result is False


@pytest.mark.unit
class TestCoachChatToolFrames:
    """SSE tool-activity frames (Task 4): tool_call on start, tool_result on complete."""

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_emits_tool_call_and_result_frames(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()

        def _chat(message, stream_callback=None):
            # Server wires tool_start_callback / tool_complete_callback onto the
            # agent before .chat runs; a real tool-using turn fires both.
            agent_instance.tool_start_callback("c1", "analyze_position", {})
            agent_instance.tool_complete_callback(
                "c1", "analyze_position", {}, '{"eval": 0.3}'
            )
            if stream_callback:
                stream_callback("Here is the eval.")
            return "Here is the eval."

        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat", headers=USER_HEADERS, json={"message": "analyze"}
        )
        events = _parse_sse(resp.text)
        calls = [e for e in events if "tool_call" in e]
        results = [e for e in events if "tool_result" in e]
        assert calls and calls[0]["tool_call"] == "analyze_position"
        assert results and results[0]["tool_result"]["tool"] == "analyze_position"
        assert results[0]["tool_result"]["ok"] is True

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_tool_result_marks_failure(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()

        def _chat(message, stream_callback=None):
            agent_instance.tool_start_callback("c1", "search_master_games", {})
            agent_instance.tool_complete_callback(
                "c1", "search_master_games", {}, '{"error": "boom"}'
            )
            return "Could not search."

        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat", headers=USER_HEADERS, json={"message": "find games"}
        )
        events = _parse_sse(resp.text)
        results = [e for e in events if "tool_result" in e]
        assert results and results[0]["tool_result"]["ok"] is False


@pytest.mark.unit
class TestVoicePromptEndpoint:
    """POST /api/coach/voice/prompt (Task 2/3): single-source prompt + profile."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_requires_user_id(self):
        resp = self.client.post("/api/coach/voice/prompt", json={})
        assert resp.status_code == 401

    @patch("src.server.load_user_profile")
    def test_returns_prompt_and_profile_context(self, mock_load):
        mock_load.return_value = UserProfile(
            user_id="test-user-123", rating=1650, weaknesses=["endgames"]
        )
        resp = self.client.post(
            "/api/coach/voice/prompt",
            headers=USER_HEADERS,
            json={"fen": "8/8/8/8/8/8/8/K6k w - - 0 1", "locale": "en"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "system_prompt" in body and "profile_context" in body
        # Profile parity: the rendered profile context is present in both.
        assert "Student rating: 1650" in body["profile_context"]
        assert "Student rating: 1650" in body["system_prompt"]
        # Spoken-style + FEN present in the single-source prompt.
        assert "Speaking Style (voice mode)" in body["system_prompt"]
        assert "8/8/8/8/8/8/8/K6k w - - 0 1" in body["system_prompt"]

    @patch("src.server.load_user_profile")
    def test_profile_cached_across_calls(self, mock_load):
        mock_load.return_value = UserProfile(user_id="test-user-123", rating=1400)
        for _ in range(3):
            resp = self.client.post(
                "/api/coach/voice/prompt", headers=USER_HEADERS, json={}
            )
            assert resp.status_code == 200
        # The Supabase profile fetch is cached — one load for repeated mints.
        assert mock_load.call_count == 1

    @patch("src.server.load_user_profile")
    def test_token_mint_rate_limited(self, mock_load):
        mock_load.return_value = UserProfile(user_id="test-user-123")
        # Free tier allows 10 mints/hour; the 11th is rejected.
        statuses = []
        for _ in range(12):
            statuses.append(
                self.client.post(
                    "/api/coach/voice/prompt", headers=USER_HEADERS, json={}
                ).status_code
            )
        assert statuses.count(200) == 10
        assert 429 in statuses


@pytest.mark.unit
class TestVoiceSessionMetering:
    """POST /api/coach/metrics 'end' beacon meters a voice session row (Task 1)."""

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.record_voice_event")
    def test_end_event_records_voice_session(self, mock_record):
        resp = self.client.post(
            "/api/coach/metrics",
            headers=USER_HEADERS,
            json={"sessionId": "sess-xyz", "event": "end", "session_ms": 42000},
        )
        assert resp.status_code == 204
        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert kwargs.get("duration_ms") == 42000
        assert mock_record.call_args[0][0] == "test-user-123"
        assert mock_record.call_args[0][1] == "sess-xyz"

    @patch("src.server.record_voice_event")
    def test_non_end_event_does_not_meter(self, mock_record):
        resp = self.client.post(
            "/api/coach/metrics",
            headers=USER_HEADERS,
            json={"sessionId": "sess-xyz", "event": "connect", "connect_ms": 120},
        )
        assert resp.status_code == 204
        mock_record.assert_not_called()
