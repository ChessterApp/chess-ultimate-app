"""Two-stage answer and provider fallback on /api/coach/chat.

The agent and the reaction call are both faked, so these tests pin the SSE
contract: frame order, the separator between reaction and answer, what gets
persisted, and what the student sees when the provider fails.
"""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src import config, server
from src.quick_reply import QuickReply
from src.server import app
from src.sessions import session_store
from src.middleware.rate_limiter import rate_limiter
from src.user_profile import UserProfile


USER = {"X-User-Id": "two-stage-user"}


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    rate_limiter.reset()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()


def _frames(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _deltas(frames):
    return "".join(f["delta"] for f in frames if "delta" in f)


def _stages(frames):
    return [f["stage"] for f in frames if "stage" in f]


def _agent(reply="Ход e4 хорош.", stream=True, delay=0.0, chat_side_effect=None):
    agent = MagicMock()
    agent.tools = []
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = 100
    agent.session_completion_tokens = 20
    agent.session_cache_read_tokens = 0

    def _chat(message, stream_callback=None):
        if delay:
            time.sleep(delay)
        if stream and stream_callback:
            for chunk in reply.split(" "):
                stream_callback(chunk + " ")
        return reply

    agent.chat.side_effect = chat_side_effect or _chat
    return agent


def _quick(text="Смотрю на позицию, сейчас проверю на движке.", delay=0.0, chunk_delay=0.0,
           fail=None, first_token_ms=300):
    """A fake stream_quick_reply that behaves like the real one, minus the network."""

    def _fake(*, on_delta=None, should_abort=None, **kw):
        if delay:
            time.sleep(delay)
        reply = QuickReply(model=kw.get("model", "q"), prompt_tokens=40, completion_tokens=12)
        if fail:
            reply.error = fail
            return reply
        words = text.split(" ")
        parts = []
        for i, w in enumerate(words):
            if should_abort and should_abort():
                reply.error = "aborted"
                break
            piece = w + (" " if i < len(words) - 1 else "")
            parts.append(piece)
            if on_delta:
                on_delta(piece)
            if chunk_delay:
                time.sleep(chunk_delay)
        reply.text = "".join(parts).strip()
        reply.first_token_ms = first_token_ms
        reply.latency_ms = 900
        return reply

    return _fake


@pytest.mark.unit
class TestTwoStage:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_reaction_then_answer_in_one_message(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_TWO_STAGE", True)
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        # The answer takes a while (engine); the reaction is instant.
        mock_agent.return_value = _agent(delay=0.4)
        with patch("src.quick_reply.stream_quick_reply", _quick()):
            resp = self.client.post("/api/coach/chat", headers=USER,
                                    json={"message": "что мне здесь играть?", "locale": "ru"})
        assert resp.status_code == 200
        frames = _frames(resp.text)

        assert _stages(frames) == ["quick", "answer"]
        text = _deltas(frames)
        assert text.startswith("Смотрю на позицию, сейчас проверю на движке.")
        assert "\n\nХод e4 хорош. " in text
        # quick stage marker comes before any delta; answer marker sits right
        # after the separator and before the first answer delta.
        kinds = [("stage", f["stage"]) if "stage" in f else ("delta", f.get("delta")) for f in frames
                 if "stage" in f or "delta" in f]
        assert kinds[0] == ("stage", "quick")
        i_sep = kinds.index(("delta", "\n\n"))
        assert kinds[i_sep + 1] == ("stage", "answer")
        assert kinds[i_sep + 2] == ("delta", "Ход ")
        assert frames[-1]["done"] is True

        # Persisted assistant message == what the screen shows (modulo whitespace).
        session = session_store.get(frames[-1]["session_id"], "two-stage-user")
        assistant = [m for m in session.messages if m.role == "assistant"][-1]
        assert assistant.content == "Смотрю на позицию, сейчас проверю на движке.\n\nХод e4 хорош."

        events = {c.args[0]: c.kwargs for c in mock_log.call_args_list}
        assert events["quick_reaction"]["payload"]["shown"] is True
        assert events["turn_end"]["payload"]["quick_shown"] is True

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_answer_first_abandons_reaction(self, mock_agent, mock_profile, mock_log, monkeypatch):
        """If the answer starts before the reaction's first token, no reaction is shown."""
        monkeypatch.setattr(config, "COACH_TWO_STAGE", True)
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        mock_agent.return_value = _agent()  # instant answer
        # Timestamp frames as the generator emits them: the TestClient hands the
        # body over only when the request's worker threads are done, so wall
        # time at the client would include the abandoned reaction's sleep.
        emitted: list[tuple[float, dict]] = []
        real_sse = server._sse

        def _timed_sse(data):
            emitted.append((time.monotonic(), data))
            return real_sse(data)

        with patch("src.quick_reply.stream_quick_reply", _quick(delay=0.5)), \
             patch("src.server._sse", _timed_sse):
            t0 = time.monotonic()
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": "what should I play here?"})
        frames = _frames(resp.text)
        assert _stages(frames) == []
        assert _deltas(frames) == "Ход e4 хорош. "
        assert "Смотрю" not in resp.text
        # The terminal frame did not wait for the abandoned reaction.
        done_at = next(ts for ts, d in emitted if d.get("done")) - t0
        assert done_at < 0.3, done_at
        session = session_store.get(frames[-1]["session_id"], "two-stage-user")
        assert [m for m in session.messages if m.role == "assistant"][-1].content == "Ход e4 хорош."
        events = {c.args[0]: c.kwargs for c in mock_log.call_args_list}
        assert events["quick_reaction"]["payload"]["shown"] is False
        assert events["quick_reaction"]["payload"]["abandoned"] is True

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_answer_deltas_are_held_while_reaction_streams(self, mock_agent, mock_profile, mock_log, monkeypatch):
        """Reaction mid-stream + answer arriving → answer waits for the separator."""
        monkeypatch.setattr(config, "COACH_TWO_STAGE", True)
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        mock_agent.return_value = _agent(delay=0.1)
        with patch("src.quick_reply.stream_quick_reply", _quick(chunk_delay=0.05)):
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": "what should I play here?"})
        text = _deltas(_frames(resp.text))
        assert text == "Смотрю на позицию, сейчас проверю на движке.\n\nХод e4 хорош. "

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_reaction_failure_is_silent(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_TWO_STAGE", True)
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        mock_agent.return_value = _agent(delay=0.1)
        with patch("src.quick_reply.stream_quick_reply", _quick(fail="http_429: slow down")):
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": "what should I play here?"})
        frames = _frames(resp.text)
        assert _stages(frames) == []
        assert _deltas(frames) == "Ход e4 хорош. "
        assert frames[-1]["done"] is True
        events = {c.args[0]: c.kwargs for c in mock_log.call_args_list}
        assert events["quick_reaction"]["error_code"] == "http_429: slow down"

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_reaction_crash_never_hangs_the_stream(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_TWO_STAGE", True)
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        mock_agent.return_value = _agent(delay=0.1)

        def _boom(**kw):
            raise RuntimeError("import gone")

        with patch("src.quick_reply.stream_quick_reply", _boom):
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": "what should I play here?"})
        frames = _frames(resp.text)
        assert frames[-1]["done"] is True
        assert _deltas(frames) == "Ход e4 хорош. "

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_flag_off_is_byte_identical(self, mock_agent, mock_profile, mock_log):
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        mock_agent.return_value = _agent()
        with patch("src.quick_reply.stream_quick_reply") as quick:
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": "what should I play here?"})
            quick.assert_not_called()
        frames = _frames(resp.text)
        assert _stages(frames) == []
        assert _deltas(frames) == "Ход e4 хорош. "
        events = [c.args[0] for c in mock_log.call_args_list]
        assert "quick_reaction" not in events

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_non_streaming_answer_after_reaction(self, mock_agent, mock_profile, mock_log, monkeypatch):
        """A tool-only agent turn (no token callback) still lands after the separator."""
        monkeypatch.setattr(config, "COACH_TWO_STAGE", True)
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        mock_agent.return_value = _agent(reply="Готово.", stream=False, delay=0.1)
        with patch("src.quick_reply.stream_quick_reply", _quick()):
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": "what should I play here?"})
        frames = _frames(resp.text)
        assert _stages(frames) == ["quick", "answer"]
        assert _deltas(frames) == "Смотрю на позицию, сейчас проверю на движке.\n\nГотово."


@pytest.mark.unit
class TestProviderErrorAsText:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.diag")
    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_framework_error_text_is_not_an_answer(self, mock_agent, mock_profile, mock_log, mock_diag):
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        raw = ("API call failed after 3 retries: HTTP 429: Rate limit exceeded: "
               "new-account-rpm/google/gemini-3.8-flash-20260902.")
        mock_agent.return_value = _agent(reply=raw, stream=False)
        resp = self.client.post("/api/coach/chat", headers=USER,
                                json={"message": "разбери партию", "locale": "ru"})
        frames = _frames(resp.text)
        assert "429" not in resp.text
        assert frames[-1] == {"error": "Тренер сейчас недоступен — попробуйте ещё раз через минуту."}
        assert not any("done" in f for f in frames)
        # Nothing persisted as an assistant message.
        sessions = list(session_store._sessions.values())
        assert sessions and not [m for m in sessions[0].messages if m.role == "assistant"]
        events = {c.args[0]: c.kwargs for c in mock_log.call_args_list}
        assert events["llm_error"]["error_code"] == "provider_error"
        assert "HTTP 429" in events["llm_error"]["payload"]["message"]
        mock_diag.record.assert_called_once()

    @patch("src.server.diag")
    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_error_text_is_localized(self, mock_agent, mock_profile, mock_log, mock_diag):
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        mock_agent.return_value = _agent(chat_side_effect=RuntimeError("boom"))
        for locale, needle in (("en", "The coach is unavailable"), ("kz", "Жаттықтырушы"), (None, "Тренер")):
            body = {"message": "hi"}
            if locale:
                body["locale"] = locale
            resp = self.client.post("/api/coach/chat", headers=USER, json=body)
            assert needle in _frames(resp.text)[-1]["error"]
            assert "boom" not in resp.text


@pytest.mark.unit
class TestFallbackWiring:
    def test_create_agent_arms_framework_fallback(self):
        captured = {}

        class _Fake:
            def __init__(self, **kw):
                captured.update(kw)
                self.tools = []
                self.valid_tool_names = set()

        with patch("run_agent.AIAgent", _Fake):
            server._create_agent(model="deepseek/deepseek-v4.1-flash", system_prompt="s",
                                 fallback_model="google/gemini-3.8-flash")
        fb = captured["fallback_model"]
        assert fb["provider"] == "openrouter"
        assert fb["model"] == "google/gemini-3.8-flash"
        assert fb["base_url"] == server.OPENROUTER_BASE_URL

    def test_create_agent_without_fallback_passes_nothing(self):
        captured = {}

        class _Fake:
            def __init__(self, **kw):
                captured.update(kw)
                self.tools = []
                self.valid_tool_names = set()

        with patch("run_agent.AIAgent", _Fake):
            server._create_agent(model="m", system_prompt="s", fallback_model=None)
            assert "fallback_model" not in captured
            server._create_agent(model="m", system_prompt="s", fallback_model="m")
            assert "fallback_model" not in captured  # same model is no fallback

    def test_turn_fallback_respects_kill_switch(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_MODEL_FALLBACK_ENABLED", False)
        assert server._turn_fallback_model("deepseek/deepseek-v4.1-flash") is None
        monkeypatch.setattr(config, "COACH_MODEL_FALLBACK_ENABLED", True)
        assert server._turn_fallback_model("deepseek/deepseek-v4.1-flash") == "google/gemini-3.8-flash"
        # A review already on Gemini falls back to the fast model, never to itself.
        assert server._turn_fallback_model("google/gemini-3.8-flash") == "deepseek/deepseek-v4.1-flash"

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_served_model_follows_the_failover(self, mock_agent, mock_profile, mock_log):
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        agent = _agent()
        agent.model = "google/gemini-3.8-flash"  # the framework switched mid-turn
        agent._fallback_activated = True
        mock_agent.return_value = agent
        with patch("src.server._do_record_usage") as rec:
            resp = self.client_post()
            events = {c.args[0]: c.kwargs for c in mock_log.call_args_list}
            assert events["model_fallback"]["payload"] == {
                "routed_model": "deepseek/deepseek-v4.1-flash",
                "served_model": "google/gemini-3.8-flash",
            }
            assert events["turn_end"]["model"] == "google/gemini-3.8-flash"
            assert events["turn_end"]["payload"]["routed_model"] == "deepseek/deepseek-v4.1-flash"
            # Usage is billed to the model that answered.
            deadline = time.monotonic() + 2
            while not rec.call_args_list and time.monotonic() < deadline:
                time.sleep(0.01)
            assert rec.call_args.args[2] == "google/gemini-3.8-flash"
        assert _frames(resp.text)[-1]["done"] is True

    def client_post(self):
        return TestClient(app).post("/api/coach/chat", headers=USER, json={"message": "что мне здесь играть?"})

    def test_provider_error_detector(self):
        assert server._looks_like_provider_error("API call failed after 3 retries: HTTP 429")
        assert server._looks_like_provider_error("  Invalid API response after 3 retries: x")
        assert not server._looks_like_provider_error("Сыграйте e4 — API call failed не при чём")
        assert not server._looks_like_provider_error("")
        assert not server._looks_like_provider_error(None)


@pytest.mark.unit
class TestReactionPolish:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_greeting_skips_the_reaction(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_TWO_STAGE", True)
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        mock_agent.return_value = _agent(reply="Привет! Чем займёмся?", delay=0.1)
        with patch("src.quick_reply.stream_quick_reply", _quick()) as quick:
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": "Привет!"})
        frames = _frames(resp.text)
        assert _stages(frames) == []
        assert _deltas(frames).startswith("Привет! ")
        assert "quick_reaction" not in [c.args[0] for c in mock_log.call_args_list]

    @patch("src.server.log_event")
    @patch("src.server.load_user_profile")
    @patch("src.server._create_agent")
    def test_answer_leading_blank_lines_are_dropped_after_reaction(self, mock_agent, mock_profile, mock_log, monkeypatch):
        monkeypatch.setattr(config, "COACH_TWO_STAGE", True)
        mock_profile.return_value = UserProfile(user_id="two-stage-user")
        agent = _agent(delay=0.1)

        def _chat(message, stream_callback=None):
            time.sleep(0.1)
            for chunk in ["\n", "\n", "Ход ", "e4."]:
                stream_callback(chunk)
            return "\n\nХод e4."

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        with patch("src.quick_reply.stream_quick_reply", _quick()):
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": "что мне здесь играть?"})
        frames = _frames(resp.text)
        assert _deltas(frames) == "Смотрю на позицию, сейчас проверю на движке.\n\nХод e4."
        session = session_store.get(frames[-1]["session_id"], "two-stage-user")
        assert [m for m in session.messages if m.role == "assistant"][-1].content == \
            "Смотрю на позицию, сейчас проверю на движке.\n\nХод e4."
