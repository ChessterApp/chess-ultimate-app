"""Tests for CL Phase-1 memory prompt injection + flag-off no-op.

Verifies the 'Recent verified mistakes' block is injected only when
COACH_MEMORY_WRITER is on, and that with the flag off the prompt is
byte-identical and NO corrections are ever loaded (grep-provable no-op).
"""

from unittest.mock import MagicMock, patch

import pytest

import src.config as config
import src.memory_writer as mw
from src.prompt_builder import build_system_prompt
from src.user_profile import UserProfile

MOCK_SOUL = "# Chess Coach\nYou are a chess coach."


@pytest.fixture(autouse=True)
def _no_rating_sync():
    """maybe_sync_ratings spawns a network thread — stub it out for determinism."""
    with patch("src.prompt_builder.maybe_sync_ratings"):
        yield


@pytest.mark.unit
class TestFlagOff:
    def test_flag_off_does_not_load_corrections(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_MEMORY_WRITER", False), \
             patch.object(mw, "load_active_corrections") as load:
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        load.assert_not_called()
        assert "Recent verified mistakes" not in prompt

    def test_flag_off_is_byte_identical(self):
        profile = UserProfile(user_id="u1", rating=1400, weaknesses=["hangs pieces"])
        with patch.object(config, "COACH_MEMORY_WRITER", False):
            baseline = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        # A second build with the flag still off must match exactly, and never
        # contains the injected block.
        with patch.object(config, "COACH_MEMORY_WRITER", False):
            again = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        assert baseline == again
        assert "Recent verified mistakes" not in baseline


@pytest.mark.unit
class TestFlagOn:
    def test_flag_on_injects_block(self):
        profile = UserProfile(user_id="u1", rating=1400)
        corrections = [{"reflection": "Claimed Ke2 at FEN; engine says check. Verify moves with tools before asserting."}]
        with patch.object(config, "COACH_MEMORY_WRITER", True), \
             patch.object(mw, "load_active_corrections", return_value=corrections) as load:
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        load.assert_called_once_with("u1", limit=3)
        assert "## Recent verified mistakes to avoid repeating" in prompt
        assert "Claimed Ke2" in prompt

    def test_flag_on_no_corrections_omits_block(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_MEMORY_WRITER", True), \
             patch.object(mw, "load_active_corrections", return_value=[]):
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        assert "Recent verified mistakes" not in prompt

    def test_flag_on_failopen_on_load_error(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_MEMORY_WRITER", True), \
             patch.object(mw, "load_active_corrections", side_effect=RuntimeError("db down")):
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        # Fail-open: the block is simply omitted, the prompt still builds.
        assert "Recent verified mistakes" not in prompt
        assert "Chess Coach" in prompt


@pytest.mark.unit
class TestServerWiring:
    """The chat path schedules the writer only when the flag is on."""

    def setup_method(self):
        from fastapi.testclient import TestClient
        from src.server import app
        from src.sessions import session_store
        from src.middleware.rate_limiter import rate_limiter

        self.client = TestClient(app)
        session_store._sessions.clear()
        rate_limiter.reset()

    def _run_turn(self):
        agent_instance = MagicMock()
        agent_instance.tools = []
        agent_instance._api_call_count = 1
        agent_instance.max_iterations = 5
        agent_instance.session_prompt_tokens = 10
        agent_instance.session_completion_tokens = 5

        def _chat(message, stream_callback=None):
            if stream_callback:
                stream_callback("Play e4.")
            return "Play e4."

        agent_instance.chat.side_effect = _chat
        return agent_instance

    def test_flag_off_does_not_schedule(self):
        agent_instance = self._run_turn()
        with patch("src.server._create_agent", return_value=agent_instance), \
             patch("src.server.load_user_profile", return_value=UserProfile(user_id="mw-user")), \
             patch("src.server.config.COACH_MEMORY_WRITER", False), \
             patch("src.memory_writer.schedule_memory_writer") as sched:
            resp = self.client.post(
                "/api/coach/chat", headers={"X-User-Id": "mw-user"}, json={"message": "hi"}
            )
        assert resp.status_code == 200
        sched.assert_not_called()

    def test_flag_on_schedules_writer(self):
        agent_instance = self._run_turn()
        with patch("src.server._create_agent", return_value=agent_instance), \
             patch("src.server.load_user_profile", return_value=UserProfile(user_id="mw-user")), \
             patch("src.server.config.COACH_MEMORY_WRITER", True), \
             patch("src.memory_writer.schedule_memory_writer") as sched:
            resp = self.client.post(
                "/api/coach/chat", headers={"X-User-Id": "mw-user"}, json={"message": "hi"}
            )
        assert resp.status_code == 200
        sched.assert_called_once()
        kwargs = sched.call_args.kwargs
        assert kwargs["user_id"] == "mw-user"
        assert kwargs["coach_reply"] == "Play e4."
        assert "turn_id" in kwargs
