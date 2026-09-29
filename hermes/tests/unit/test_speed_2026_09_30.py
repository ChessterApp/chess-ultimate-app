"""Speed-ups of 2026-09-30: warm-up at startup, the served model after a race."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src import server


@pytest.mark.unit
def test_warm_up_builds_an_agent_and_runs_the_engine_once():
    with patch.object(server, "_create_agent") as create, \
            patch("src.voice_engine_note.engine_note") as note, \
            patch("src.knowledge_base.load_topics") as topics:
        server._warm_up()
    create.assert_called_once()
    note.assert_called_once()
    assert note.call_args.kwargs["movetime_ms"] == 200
    topics.assert_called_once()


@pytest.mark.unit
def test_a_failing_warm_up_step_does_not_stop_the_others():
    with patch.object(server, "_create_agent", side_effect=RuntimeError("no key")), \
            patch("src.voice_engine_note.engine_note") as note, \
            patch("src.knowledge_base.load_topics"):
        server._warm_up()
    note.assert_called_once()


@pytest.mark.unit
def test_the_served_model_is_the_backup_when_it_won_the_race():
    agent = SimpleNamespace(model="deepseek/deepseek-v4.1-flash",
                            _coach_hedge={"fired": True, "winner": "backup", "model": "google/gemini-3.8-flash"})
    assert server._served_model(agent, "deepseek/deepseek-v4.1-flash") == "google/gemini-3.8-flash"
    agent._coach_hedge = {"fired": True, "winner": "primary", "model": "deepseek/deepseek-v4.1-flash"}
    assert server._served_model(agent, "deepseek/deepseek-v4.1-flash") == "deepseek/deepseek-v4.1-flash"


@pytest.mark.unit
def test_agents_go_through_the_shared_transport():
    agent = server._create_agent("deepseek/deepseek-v4.1-flash", "sys", session_id="t", user_query="что играть?")
    assert agent._coach_hedge == {"fired": False, "winner": None, "model": None}
    assert agent._create_request_openai_client.__qualname__.startswith("install.")
