"""Unit tests for coach_events emission on the text chat loop (Phase 1, Task 4).

Patches ``src.server.log_event`` so we assert on the emitted event stream rather
than the spool/Supabase sinks (those are covered in test_event_logger).
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.server import app
from src.sessions import session_store
from src.middleware.rate_limiter import rate_limiter
from src.user_profile import UserProfile


USER_HEADERS = {"X-User-Id": "evt-user"}


@pytest.fixture(autouse=True)
def _clear_state():
    session_store._sessions.clear()
    rate_limiter.reset()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()


def _events_by_type(mock_log):
    """Map event_type -> list of the kwargs each log_event call was made with."""
    out: dict[str, list[dict]] = {}
    for call in mock_log.call_args_list:
        etype = call.args[0] if call.args else call.kwargs.get("event_type")
        out.setdefault(etype, []).append(call.kwargs)
    return out


@pytest.mark.unit
class TestChatEvents:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.log_event")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_happy_path_with_tool_call(self, mock_profile, mock_agent, mock_log):
        mock_profile.return_value = UserProfile(user_id="evt-user")
        agent_instance = MagicMock()
        agent_instance.tools = [{"function": {"name": "check_moves"}}]
        agent_instance._api_call_count = 2
        agent_instance.max_iterations = 5
        agent_instance.session_prompt_tokens = 120
        agent_instance.session_completion_tokens = 45

        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        check_result = json.dumps({
            "results": [{"legal": True}, {"legal": False}],
            "legal_moves": ["e4", "d4"],
        })

        def _chat(message, stream_callback=None):
            agent_instance.tool_start_callback("c1", "check_moves", {"fen": fen, "moves": ["e4", "Ke2"]})
            agent_instance.tool_complete_callback("c1", "check_moves", {"fen": fen, "moves": ["e4", "Ke2"]}, check_result)
            if stream_callback:
                stream_callback("Play e4.")
            return "Play e4."

        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat", headers=USER_HEADERS, json={"message": "what move?"}
        )
        assert resp.status_code == 200

        events = _events_by_type(mock_log)
        assert "turn_start" in events
        assert "tool_call" in events
        assert "turn_end" in events

        # turn_start carries routing + prompt version + tool subset.
        ts = events["turn_start"][0]
        assert ts["surface"] == "text"
        assert ts["turn_id"]
        assert ts["payload"]["prompt_version"]
        assert ts["payload"]["routing_tier"]
        assert ts["payload"]["tools_selected"] == ["check_moves"]

        # tool_call: timing, ok, and the check_moves hallucination verdict.
        tc = events["tool_call"][0]
        assert tc["tool_name"] == "check_moves"
        assert tc["ok"] is True
        assert tc["payload"]["check_moves_verdict"] == {"candidates": 2, "legal": 1, "illegal": 1}

        # turn_end: token counts + iteration count, all correlated by turn_id.
        te = events["turn_end"][0]
        assert te["ok"] is True
        assert te["payload"]["prompt_tokens"] == 120
        assert te["payload"]["completion_tokens"] == 45
        assert te["payload"]["iterations"] == 2
        assert te["payload"]["finish_reason"] == "stop"
        assert te["turn_id"] == ts["turn_id"] == tc["turn_id"]

    @patch("src.server.diag")
    @patch("src.server.log_event")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_llm_error_emits_event_and_diagnostic(self, mock_profile, mock_agent, mock_log, mock_diag):
        mock_profile.return_value = UserProfile(user_id="evt-user")
        agent_instance = MagicMock()
        agent_instance.tools = []
        agent_instance.chat.side_effect = RuntimeError("openrouter 500")
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat", headers=USER_HEADERS, json={"message": "hi"}
        )
        assert resp.status_code == 200
        text = resp.text
        assert "Agent error" in text  # error frame still emitted to client

        events = _events_by_type(mock_log)
        assert "llm_error" in events
        err = events["llm_error"][0]
        assert err["severity"] == "error"
        assert err["error_code"] == "RuntimeError"
        assert "openrouter 500" in err["payload"]["message"]
        # The streaming path now ALSO records a diagnostic (previously it didn't).
        mock_diag.record.assert_called_once()
        assert mock_diag.record.call_args.kwargs["model"]
        # No turn_end on the error path.
        assert "turn_end" not in events

    @patch("src.server.log_event")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_max_iterations_hit(self, mock_profile, mock_agent, mock_log):
        mock_profile.return_value = UserProfile(user_id="evt-user")
        agent_instance = MagicMock()
        agent_instance.tools = []
        agent_instance._api_call_count = 5
        agent_instance.max_iterations = 5
        agent_instance.session_prompt_tokens = 10
        agent_instance.session_completion_tokens = 5
        agent_instance.chat.return_value = "Reached the iteration limit."
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat", headers=USER_HEADERS, json={"message": "go deep"}
        )
        assert resp.status_code == 200
        events = _events_by_type(mock_log)
        assert "max_iterations_hit" in events
        mih = events["max_iterations_hit"][0]
        assert mih["severity"] == "warn"
        assert mih["payload"]["iterations"] == 5
        assert events["turn_end"][0]["payload"]["finish_reason"] == "max_iterations"

    @patch("src.server.log_event")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_empty_response_warns(self, mock_profile, mock_agent, mock_log):
        mock_profile.return_value = UserProfile(user_id="evt-user")
        agent_instance = MagicMock()
        agent_instance.tools = []
        agent_instance._api_call_count = 1
        agent_instance.max_iterations = 5
        agent_instance.session_prompt_tokens = 0
        agent_instance.session_completion_tokens = 0
        agent_instance.chat.return_value = ""  # nothing usable
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat", headers=USER_HEADERS, json={"message": "hmm"}
        )
        assert resp.status_code == 200
        events = _events_by_type(mock_log)
        assert "empty_response" in events
        assert events["empty_response"][0]["severity"] == "warn"

    def test_stream_disconnect_emitted(self):
        """Aborting the async generator mid-stream fires a stream_disconnect event.

        Drives the streaming endpoint's generator directly and calls ``aclose()``
        after the first delta — the same GeneratorExit Starlette raises when a
        client drops the connection — then asserts the event carries the partial
        assistant text and chars-streamed count.
        """
        import asyncio

        from fastapi import Request

        from src import server

        captured: list[dict] = []

        def _fake_log(event_type, **kwargs):
            captured.append({"event_type": event_type, **kwargs})

        agent_instance = MagicMock()
        agent_instance.tools = []
        agent_instance._api_call_count = 1
        agent_instance.max_iterations = 5

        def _chat(message, stream_callback=None):
            import time as _t
            if stream_callback:
                for chunk in ["one ", "two ", "three "]:
                    stream_callback(chunk)
                    _t.sleep(0.05)  # keep the stream open so we can abort mid-way
            return "one two three "

        agent_instance.chat.side_effect = _chat

        async def _drive():
            scope = {
                "type": "http",
                "method": "POST",
                "headers": [(b"x-user-id", b"evt-user")],
                "path": "/api/coach/chat",
                "query_string": b"",
            }

            async def _receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            request = Request(scope, receive=_receive)
            request.state.request_id = "req-test"

            body = server.CoachChatRequest(message="count")
            with patch.object(server, "log_event", _fake_log), \
                    patch.object(server, "_create_agent", return_value=agent_instance), \
                    patch.object(server, "load_user_profile", return_value=UserProfile(user_id="evt-user")):
                resp = await server.coach_chat(body, request)
                gen = resp.body_iterator
                # Pull the first streamed frame, then abort like a dropped client.
                await gen.__anext__()
                await gen.aclose()

        asyncio.run(_drive())

        types = [e["event_type"] for e in captured]
        assert "stream_disconnect" in types
        sd = next(e for e in captured if e["event_type"] == "stream_disconnect")
        assert sd["severity"] == "warn"
        assert sd["payload"]["chars_streamed"] >= 1
        assert "partial_text" in sd["payload"]
        # turn_end must NOT fire on an aborted stream.
        assert "turn_end" not in types
