"""The text coach's tools see the session through the REAL agent framework (28.10).

The framework dispatches a tool with task_id/user_task only; the session reaches the tools through
the turn's task id (server._chat_in_session → src.tools.turn_session). The older test of this seam
used a fake agent, so a hermes_agent upgrade that stops passing our task_id would silently switch
off every in-game guard of the text coach ("no best move in a live game"). This test runs the real
AIAgent with only the LLM call replaced.
"""

import json

import chess
import pytest
from openai.types.chat import ChatCompletion

from src import config, game_mode, server
from src.sessions import session_store
from src.tools import discover_and_register


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    discover_and_register()
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-key")
    monkeypatch.setattr(config, "COACH_TOOL_SUBSET", False, raising=False)
    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))


def _completion(message: dict, finish: str) -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "cmpl-test", "object": "chat.completion", "created": 0, "model": "test/model",
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", **message}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })


def _scripted_llm(agent, tool: str, args: dict, seen: list):
    """The model asks for *tool* once, then answers with the tool's result as its text."""

    def call(api_kwargs, *a, **k):
        tool_msgs = [m for m in api_kwargs.get("messages", []) if m.get("role") == "tool"]
        if not tool_msgs:
            return _completion({"content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": tool, "arguments": json.dumps(args)}}]}, "tool_calls")
        seen.append(tool_msgs[-1]["content"])
        return _completion({"content": "ok"}, "stop")

    agent._interruptible_api_call = call
    agent._interruptible_streaming_api_call = call


@pytest.mark.unit
def test_a_tool_dispatched_by_the_real_agent_in_a_text_turn_receives_the_session():
    session = session_store.create(user_id="text-turn-real-agent")
    agent = server._create_agent(model="test/model", system_prompt="s", session_id=session.id)
    seen: list = []
    _scripted_llm(agent, "start_game", {"color": "white"}, seen)

    reply = server._chat_in_session(agent, "давай сыграем", session.id, student_message="давай сыграем")

    assert reply == "ok" and seen, "the framework did not run the tool"
    result = json.loads(seen[0])
    # start_game needs the session (kwargs session_id): without it the tool answers with an error.
    assert result.get("ok"), result
    assert session.get_board(session.active_board_id).kind == "game"
