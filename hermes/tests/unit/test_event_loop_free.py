"""A slow Supabase call for one student must not freeze the server for the others (2026-09-29).

coach_chat is an async handler; it loaded the profile, built the prompt and
created the agent on the event loop, so every other stream stopped for the
round trip. Those now run in worker threads.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src import server
from src.user_profile import UserProfile


def _agent():
    a = MagicMock()
    a.tools = []
    a._api_call_count = 1
    a.max_iterations = 5
    a.session_prompt_tokens = a.session_completion_tokens = 0

    def _chat(message, stream_callback=None):
        stream_callback("Играй e4.")
        return "Играй e4."

    a.chat.side_effect = _chat
    return a


@pytest.mark.unit
def test_a_slow_profile_load_does_not_block_other_requests():
    def slow_profile(user_id):
        time.sleep(1.0)  # a slow Supabase round trip
        return UserProfile(user_id=user_id)

    async def scenario():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            async def slow_turn():
                return await client.post("/api/coach/chat", headers={"X-User-Id": "slow-user"},
                                         json={"message": "Что играть?"})

            started = time.monotonic()

            async def other_request():
                await asyncio.sleep(0.2)  # while the first turn is loading the profile
                resp = await client.get("/health")
                # From the scenario start: a blocked loop cannot even wake this
                # task until the profile load is over.
                return resp, time.monotonic() - started

            return await asyncio.gather(slow_turn(), other_request())

    with patch("src.server.load_user_profile", side_effect=slow_profile), \
            patch("src.server._create_agent", return_value=_agent()), \
            patch("src.server.log_event"):
        server.clear_voice_profile_cache()
        turn, (health, waited) = asyncio.run(scenario())

    assert turn.status_code == 200
    assert health.status_code == 200
    # Blocking on the loop, /health came back only after the 1 s profile load.
    assert waited < 0.7, f"/health answered at {waited:.2f} s, behind another student's profile load"
