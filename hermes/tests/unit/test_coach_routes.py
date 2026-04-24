"""Unit tests for /api/coach/* FastAPI routes."""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.server import app
from src.sessions import session_store, Session
from src.user_profile import UserProfile


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Clear session store between tests."""
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


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


@pytest.mark.unit
class TestCoachChat:
    """Tests for POST /api/coach/chat."""

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_basic(self, mock_profile, mock_agent):
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
        body = resp.json()
        assert "message" in body
        assert "board_actions" in body
        assert "session_id" in body
        assert body["message"] == "The Sicilian Defense is a strong reply to 1.e4."

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_creates_session(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Hello!"
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Hi"},
        )
        session_id = resp.json()["session_id"]
        session = session_store.get(session_id, "test-user-123")
        assert session is not None
        assert len(session.messages) == 2  # user + assistant

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
        session_id = resp.json()["session_id"]
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
        assert resp.json()["session_id"] == session.id

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
        mock_prompt.assert_called_once()
        call_kwargs = mock_prompt.call_args
        assert call_kwargs.kwargs.get("locale") is None

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_agent_error(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.side_effect = RuntimeError("model unavailable")
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat",
            headers=USER_HEADERS,
            json={"message": "Hello"},
        )
        assert resp.status_code == 502


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
