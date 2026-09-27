"""The engine line in a text turn, the stored answer, and reasoning switched off.

The agent and the engine are faked: these tests pin what the model is given
(the engine block in the turn context, or nothing when the engine is late),
what gets stored, and the reasoning payload for COACH_REASONING_EFFORT=none.
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src import config, server
from src.server import app
from src.sessions import session_store
from src.middleware.rate_limiter import rate_limiter
from src.user_profile import UserProfile

USER = {"X-User-Id": "engine-note-user"}
SICILIAN = "r1bqkbnr/pp1ppppp/2n5/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
NOTE = {
    "fen": SICILIAN,
    "note": f"[Engine] {SICILIAN} — White to move. Best: d4 (+0.40; line d4 cxd4 Nxd4 g6).",
    "best": "d4",
    "lines": [],
}


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    rate_limiter.reset()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()


def _frames(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def _agent(reply="Играй d4.", streamed=None):
    """Fake agent; records the message it was given. *streamed* overrides the deltas."""
    agent = MagicMock()
    agent.tools = []
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = 100
    agent.session_completion_tokens = 20
    agent.session_cache_read_tokens = 0
    agent.seen = []

    def _chat(message, stream_callback=None):
        agent.seen.append(message)
        if stream_callback:
            for chunk in (streamed if streamed is not None else [reply]):
                stream_callback(chunk)
        return reply

    agent.chat.side_effect = _chat
    return agent


@pytest.mark.unit
class TestEngineNoteInTurn:
    def setup_method(self):
        self.client = TestClient(app)

    def _post(self, body):
        resp = self.client.post("/api/coach/chat", headers=USER, json=body)
        assert resp.status_code == 200
        return _frames(resp.text)

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_engine_line_reaches_the_model(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE", True)
        mock_profile.return_value = UserProfile(user_id="engine-note-user")
        agent = _agent()
        mock_agent.return_value = agent
        with patch("src.server.engine_note", return_value=NOTE) as fake_engine:
            self._post({"message": "Что мне здесь играть?", "fen": SICILIAN})
        fake_engine.assert_called_once_with(SICILIAN)
        message = agent.seen[0]
        assert "## Engine analysis of the board" in message
        assert NOTE["note"] in message
        # The block sits after the student's words, inside the system-supplied part.
        assert message.index("Что мне здесь играть?") < message.index("## Engine analysis")
        events = {c.args[0]: c.kwargs for c in mock_log.call_args_list}
        assert events["turn_end"]["payload"]["engine_note"]["used"] is True

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_late_engine_does_not_hold_the_turn(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE", True)
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE_WAIT_MS", 50)
        mock_profile.return_value = UserProfile(user_id="engine-note-user")
        agent = _agent()
        mock_agent.return_value = agent

        def _slow(fen):
            time.sleep(0.5)
            return NOTE

        emitted: list[tuple[float, dict]] = []
        real_sse = server._sse

        def _timed_sse(data):
            emitted.append((time.monotonic(), data))
            return real_sse(data)

        with patch("src.server.engine_note", side_effect=_slow), patch("src.server._sse", _timed_sse):
            t0 = time.monotonic()
            self._post({"message": "Что мне здесь играть?", "fen": SICILIAN})
        assert "## Engine analysis" not in agent.seen[0]
        first_delta = next(ts for ts, d in emitted if "delta" in d) - t0
        assert first_delta < 0.4, first_delta
        events = {c.args[0]: c.kwargs for c in mock_log.call_args_list}
        assert events["turn_end"]["payload"]["engine_note"]["timed_out"] is True

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_no_board_no_engine(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE", True)
        mock_profile.return_value = UserProfile(user_id="engine-note-user")
        agent = _agent()
        mock_agent.return_value = agent
        with patch("src.server.engine_note") as fake_engine:
            self._post({"message": "Как мне улучшить эндшпиль?"})
        fake_engine.assert_not_called()
        assert "## Engine analysis" not in agent.seen[0]

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_switched_off(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE", False)
        mock_profile.return_value = UserProfile(user_id="engine-note-user")
        mock_agent.return_value = _agent()
        with patch("src.server.engine_note") as fake_engine:
            self._post({"message": "Что мне здесь играть?", "fen": SICILIAN})
        fake_engine.assert_not_called()

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_stored_answer_is_what_streamed(self, mock_agent, mock_profile, mock_log):
        """Text written alongside a tool call streams but is not in the final message."""
        mock_profile.return_value = UserProfile(user_id="engine-note-user")
        mock_agent.return_value = _agent(
            reply="Попробуй сам найти ответ.",
            streamed=["Лучший ход — d4: он открывает центр. ", "Попробуй сам найти ответ."],
        )
        frames = self._post({"message": "Что мне здесь играть?"})
        session = session_store.get(frames[-1]["session_id"], "engine-note-user")
        stored = [m for m in session.messages if m.role == "assistant"][-1].content
        assert stored == "Лучший ход — d4: он открывает центр. Попробуй сам найти ответ."


@pytest.mark.unit
class TestReasoningSwitch:
    @pytest.mark.parametrize("effort,expected", [
        ("none", {"enabled": False}),
        ("off", {"enabled": False}),
        ("low", {"effort": "low"}),
    ])
    def test_reasoning_config(self, monkeypatch, effort, expected):
        monkeypatch.setattr(config, "COACH_REASONING_EFFORT", effort)
        monkeypatch.setattr(config, "COACH_TOOL_SUBSET", False)
        with patch("run_agent.AIAgent") as fake:
            server._create_agent(model="deepseek/deepseek-v4.1-flash", system_prompt="s")
        assert fake.call_args.kwargs["reasoning_config"] == expected
