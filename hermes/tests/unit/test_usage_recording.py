"""Unit tests for wiring real token usage into the completion path.

Covers the server-side helpers that read a completed agent's per-turn token
counters and hand them to ``cost_monitor.record_usage`` — fire-and-forget, so a
recording failure can never propagate into (or slow) a coach reply.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src import server


class _FakeAgent:
    """Minimal stand-in for AIAgent after a completed turn."""

    def __init__(self, prompt_tokens=0, completion_tokens=0, model="m"):
        self.session_prompt_tokens = prompt_tokens
        self.session_completion_tokens = completion_tokens
        self.model = model


@pytest.mark.unit
class TestDoRecordUsage:
    """The synchronous recorder that runs off the request path."""

    def test_calls_record_usage_with_correct_args(self):
        with patch.object(server.cost_monitor, "record_usage") as mock_record:
            server._do_record_usage("u1", "s1", "gemini", 120, 34, "text")
        mock_record.assert_called_once_with(
            user_id="u1",
            session_id="s1",
            model="gemini",
            prompt_tokens=120,
            completion_tokens=34,
            surface="text",
        )

    def test_recording_failure_does_not_propagate(self):
        with patch.object(
            server.cost_monitor, "record_usage", side_effect=RuntimeError("supabase down")
        ):
            # Must swallow the exception, not re-raise.
            server._do_record_usage("u1", "s1", "m", 10, 5, "analysis")


@pytest.mark.unit
class TestRecordTurnUsage:
    """The fire-and-forget entrypoint wired into every completion path."""

    def test_records_real_token_counts_from_agent(self):
        agent = _FakeAgent(prompt_tokens=200, completion_tokens=50)
        with patch.object(server.cost_monitor, "record_usage") as mock_record:
            thread = server._record_turn_usage(agent, "u1", "s1", "gemini", surface="text")
            assert thread is not None
            thread.join(timeout=2)
        mock_record.assert_called_once_with(
            user_id="u1",
            session_id="s1",
            model="gemini",
            prompt_tokens=200,
            completion_tokens=50,
            surface="text",
        )

    def test_skips_when_no_tokens(self):
        agent = _FakeAgent(prompt_tokens=0, completion_tokens=0)
        with patch.object(server.cost_monitor, "record_usage") as mock_record:
            thread = server._record_turn_usage(agent, "u1", "s1", "m")
        assert thread is None
        mock_record.assert_not_called()

    def test_missing_counters_do_not_raise(self):
        agent = SimpleNamespace()  # no token attributes at all
        with patch.object(server.cost_monitor, "record_usage") as mock_record:
            thread = server._record_turn_usage(agent, "u1", "s1", "m")
        assert thread is None
        mock_record.assert_not_called()

    def test_failure_in_recording_never_reaches_caller(self):
        agent = _FakeAgent(prompt_tokens=10, completion_tokens=5)
        with patch.object(
            server.cost_monitor, "record_usage", side_effect=RuntimeError("boom")
        ):
            thread = server._record_turn_usage(agent, "u1", "s1", "m", surface="review")
            # Caller never sees the error; the daemon thread swallows it.
            assert thread is not None
            thread.join(timeout=2)

    def test_default_surface_is_text(self):
        agent = _FakeAgent(prompt_tokens=1, completion_tokens=1)
        with patch.object(server.cost_monitor, "record_usage") as mock_record:
            thread = server._record_turn_usage(agent, "u1", "s1", "m")
            thread.join(timeout=2)
        assert mock_record.call_args.kwargs["surface"] == "text"
