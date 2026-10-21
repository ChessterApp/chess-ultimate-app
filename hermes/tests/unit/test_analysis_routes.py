"""Unit tests for /api/coach/analysis* FastAPI routes.

These mirror the Flask /api/chat/analysis contract. They follow the auth,
persistence, and SSE mocking patterns from test_coach_routes.py.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.server import app
from src.sessions import session_store
from src.middleware.rate_limiter import rate_limiter
from src.user_profile import UserProfile


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Clear session store and rate-limit state between tests."""
    session_store._sessions.clear()
    rate_limiter.reset()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()


USER_HEADERS = {"X-User-Id": "test-user-123"}
FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


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
class TestCoachAnalysis:
    """Tests for POST /api/coach/analysis (non-streaming)."""

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_analysis_happy_path(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "The best move is Nf3."
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/analysis",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "What is the best move?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["response"] == "The best move is Nf3."
        assert body["conversation_id"]
        assert isinstance(body["tokens_used"], int)
        assert "hourly_remaining" in body["usage"]
        assert "daily_remaining" in body["usage"]
        assert "tier" in body["usage"]

        # User + assistant messages were persisted, board state set.
        session = session_store.get(body["conversation_id"], "test-user-123")
        assert session is not None
        assert session.board_state == FEN
        assert [m.role for m in session.messages] == ["user", "assistant"]
        assert session.messages[-1].content == "The best move is Nf3."

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_analysis_reuses_conversation(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Response"
        mock_agent.return_value = agent_instance

        session = session_store.create(user_id="test-user-123")
        resp = self.client.post(
            "/api/coach/analysis",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "Continue", "conversation_id": session.id},
        )
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == session.id

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_analysis_unowned_conversation_404(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="other-user")
        session = session_store.create(user_id="other-user")

        resp = self.client.post(
            "/api/coach/analysis",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "Hi", "conversation_id": session.id},
        )
        assert resp.status_code == 404
        assert resp.json()["success"] is False

    def test_analysis_missing_fen_400(self):
        resp = self.client.post(
            "/api/coach/analysis",
            headers=USER_HEADERS,
            json={"query": "What is the best move?"},
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_analysis_missing_query_400(self):
        resp = self.client.post(
            "/api/coach/analysis",
            headers=USER_HEADERS,
            json={"fen": FEN},
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_analysis_empty_query_400(self):
        resp = self.client.post(
            "/api/coach/analysis",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "   "},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "Query cannot be empty"

    def test_analysis_query_too_long_400(self):
        resp = self.client.post(
            "/api/coach/analysis",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "x" * 2001},
        )
        assert resp.status_code == 400
        assert "too long" in resp.json()["error"].lower()

    def test_analysis_rate_limited_429(self):
        info = {"limit": 5, "remaining": 0, "retry_after": 30, "tier": "free"}
        with patch.object(rate_limiter, "check", return_value=(False, info)):
            resp = self.client.post(
                "/api/coach/analysis",
                headers=USER_HEADERS,
                json={"fen": FEN, "query": "What is the best move?"},
            )
        assert resp.status_code == 429
        body = resp.json()
        assert body["success"] is False
        assert body["rate_limited"] is True

    def test_analysis_requires_user_id(self):
        resp = self.client.post(
            "/api/coach/analysis",
            json={"fen": FEN, "query": "What is the best move?"},
        )
        assert resp.status_code == 401


@pytest.mark.unit
class TestCoachAnalysisStream:
    """Tests for POST /api/coach/analysis/stream (SSE token streaming)."""

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_stream_content_type(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "The best move is Nf3."
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/analysis/stream",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "Best move?"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_stream_deltas_reconstruct_message(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        chunks = ["The ", "best ", "move ", "is Nf3."]

        def _chat(message, stream_callback=None):
            for c in chunks:
                if stream_callback:
                    stream_callback(c)
            return "".join(chunks)

        agent_instance = MagicMock()
        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/analysis/stream",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "Best move?"},
        )
        events = _parse_sse(resp.text)
        assert _deltas(events) == "".join(chunks)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_stream_marks_become_board_actions(self, mock_profile, mock_agent):
        """Review Explain bubble showed [[arrows: …]] raw (production, 2026-10-21)."""
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        chunks = ["Knight to the centre [[arr", "ows: c6d4 green, d4e2 red]]. ",
                  "Taking on d5 was weaker [[arrows: d8d5 blue]]."]

        def _chat(message, stream_callback=None):
            for c in chunks:
                if stream_callback:
                    stream_callback(c)
            return "".join(chunks)

        agent_instance = MagicMock()
        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/analysis/stream",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "Explain"},
        )
        events = _parse_sse(resp.text)
        text = _deltas(events)
        assert "[[" not in text and "]]" not in text
        assert "Knight to the centre" in text and "Taking on d5 was weaker" in text
        actions = [a for e in events if "board_actions" in e for a in e["board_actions"]]
        arrows = actions[-1]["arrows"]
        assert {(a["from"], a["to"], a["brush"]) for a in arrows} == {
            ("c6", "d4", "green"), ("d4", "e2", "red"), ("d8", "d5", "blue"),
        }
        session = session_store.get(events[-1]["conversation_id"], "test-user-123")
        assert "[[" not in session.messages[-1].content

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_stream_marks_stripped_when_nothing_streamed(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "Play Nf6 [[arrows: g8f6 green]]."
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/analysis/stream",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "Explain"},
        )
        events = _parse_sse(resp.text)
        assert "[[" not in _deltas(events)
        assert any(e.get("board_actions") for e in events)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_stream_final_done_frame(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="test-user-123")
        agent_instance = MagicMock()
        agent_instance.chat.return_value = "The best move is Nf3."
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/analysis/stream",
            headers=USER_HEADERS,
            json={"fen": FEN, "query": "Best move?"},
        )
        events = _parse_sse(resp.text)
        done = events[-1]
        assert done.get("done") is True
        assert done.get("conversation_id")
        assert isinstance(done.get("tokens_used"), int)

        # Assistant message persisted to the returned conversation.
        session = session_store.get(done["conversation_id"], "test-user-123")
        assert session is not None
        assert session.messages[-1].role == "assistant"

    def test_stream_missing_fen_400(self):
        resp = self.client.post(
            "/api/coach/analysis/stream",
            headers=USER_HEADERS,
            json={"query": "Best move?"},
        )
        assert resp.status_code == 400

    def test_stream_rate_limited_429(self):
        info = {"limit": 5, "remaining": 0, "retry_after": 30, "tier": "free"}
        with patch.object(rate_limiter, "check", return_value=(False, info)):
            resp = self.client.post(
                "/api/coach/analysis/stream",
                headers=USER_HEADERS,
                json={"fen": FEN, "query": "Best move?"},
            )
        assert resp.status_code == 429
        assert resp.json()["rate_limited"] is True

    def test_stream_requires_user_id(self):
        resp = self.client.post(
            "/api/coach/analysis/stream",
            json={"fen": FEN, "query": "Best move?"},
        )
        assert resp.status_code == 401


@pytest.mark.unit
class TestCoachHistory:
    """Tests for GET /api/coach/history/{conversation_id}."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_history_returns_messages_for_owned_conversation(self):
        session = session_store.create(user_id="test-user-123")
        session.add_message("user", "What is the best move?")
        session.add_message("assistant", "Nf3 develops a knight.")

        resp = self.client.get(
            f"/api/coach/history/{session.id}", headers=USER_HEADERS
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["conversation"]["id"] == session.id
        assert "type" in body["conversation"]
        assert "created_at" in body["conversation"]
        assert "updated_at" in body["conversation"]
        messages = body["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "What is the best move?"
        assert "timestamp" in messages[0]

    def test_history_404_for_unowned_conversation(self):
        session = session_store.create(user_id="other-user")
        session.add_message("user", "secret")

        resp = self.client.get(
            f"/api/coach/history/{session.id}", headers=USER_HEADERS
        )
        assert resp.status_code == 404
        assert resp.json()["success"] is False

    def test_history_404_for_unknown_conversation(self):
        resp = self.client.get(
            "/api/coach/history/does-not-exist", headers=USER_HEADERS
        )
        assert resp.status_code == 404

    def test_history_requires_user_id(self):
        session = session_store.create(user_id="test-user-123")
        resp = self.client.get(f"/api/coach/history/{session.id}")
        assert resp.status_code == 401
