"""Shared connection and the race against a stalled provider (2026-09-30)."""

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from src import llm_transport, quick_reply
from src.llm_transport import race


class _Stream:
    """A stream that yields *items* after *delay* seconds each; close() ends it."""

    def __init__(self, items, delay=0.0, first_delay=None, fail=None):
        self.items = list(items)
        self.delay = delay
        self.first_delay = delay if first_delay is None else first_delay
        self.fail = fail
        self.closed = threading.Event()

    def __iter__(self):
        for i, item in enumerate(self.items):
            if self.closed.wait(self.first_delay if i == 0 else self.delay):
                return
            yield item
        if self.fail:
            raise self.fail

    def close(self):
        self.closed.set()


def _all(gen):
    return list(gen)


def _says(item):
    return item != "role"


@pytest.mark.unit
def test_a_fast_primary_never_opens_the_backup():
    opened = []
    out = _all(race(_Stream(["role", "a", "b"]), lambda: opened.append(1) or _Stream(["x"]), 0.5, _says))
    assert out == ["role", "a", "b"]
    assert opened == []


@pytest.mark.unit
def test_a_silent_primary_loses_to_the_backup_and_is_closed():
    primary = _Stream(["role", "late"], first_delay=0.0, delay=2.0)
    backup = _Stream(["role", "x", "y"])
    winners = []
    started = time.monotonic()
    out = _all(race(primary, lambda: backup, 0.1, _says, on_winner=winners.append))
    assert out == ["role", "x", "y"]
    assert winners == ["backup"]
    assert time.monotonic() - started < 1.0
    assert primary.closed.is_set()


@pytest.mark.unit
def test_the_primary_still_wins_when_it_speaks_before_the_backup():
    primary = _Stream(["a", "b"], first_delay=0.2)
    backup = _Stream(["x"], first_delay=1.5)
    winners = []
    assert _all(race(primary, lambda: backup, 0.05, _says, on_winner=winners.append)) == ["a", "b"]
    assert winners == ["primary"]
    assert backup.closed.wait(1.0)


@pytest.mark.unit
def test_a_failing_primary_hands_over_to_a_running_backup():
    primary = _Stream(["role"], first_delay=0.3, fail=RuntimeError("provider dropped"))
    backup = _Stream(["x"], first_delay=0.4)
    # Only the backup's own items: nothing of the dead stream reaches the student.
    assert _all(race(primary, lambda: backup, 0.05, _says)) == ["x"]


@pytest.mark.unit
def test_an_error_with_no_backup_is_raised():
    with pytest.raises(RuntimeError):
        _all(race(_Stream([], fail=RuntimeError("boom")), None, 0.1, _says))


@pytest.mark.unit
def test_a_backup_that_cannot_open_leaves_the_primary_alone():
    def broken():
        raise httpx.ConnectError("no route")

    assert _all(race(_Stream(["a"], first_delay=0.2), broken, 0.05, _says)) == ["a"]


@pytest.mark.unit
def test_stopping_early_closes_every_stream():
    primary = _Stream(["a", "b", "c"], delay=0.05)
    gen = race(primary, None, 0.0, _says)
    assert next(gen) == "a"
    gen.close()
    assert primary.closed.is_set()


# ── the agent's calls ───────────────────────────────────────────────────

def _chunk(content=None, role=None):
    delta = SimpleNamespace(content=content, tool_calls=None, reasoning=None, reasoning_content=None, role=role)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=None)], usage=None, model="m")


class _FakeCompletions:
    def __init__(self, streams):
        self.streams = streams
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.streams[kwargs["model"]]()


def _agent(streams, monkeypatch):
    shared = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(streams)))
    monkeypatch.setattr(llm_transport, "shared_openai_client", lambda kwargs: shared)
    monkeypatch.setattr(llm_transport, "hedge_model_for",
                        lambda model: None if model.startswith("google/") else "google/gemini-3.8-flash")
    own = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=None)), closed=False)
    own.close = lambda: setattr(own, "closed", True)
    agent = SimpleNamespace(model="deepseek/deepseek-v4.1-flash", _client_kwargs={"api_key": "k"},
                            _create_request_openai_client=lambda *, reason: own)
    llm_transport.install(agent, hedge_ms=100)
    return agent, shared.chat.completions


_USER_TURN = [{"role": "system", "content": "s"}, {"role": "user", "content": "что играть?"}]


@pytest.mark.unit
def test_a_stalled_first_call_is_answered_by_the_fallback(monkeypatch):
    stalled = _Stream([_chunk("поздно")], first_delay=3.0)
    agent, completions = _agent({
        "deepseek/deepseek-v4.1-flash": lambda: stalled,
        "google/gemini-3.8-flash": lambda: _Stream([_chunk(role="assistant"), _chunk("Ход e4.")]),
    }, monkeypatch)
    client = agent._create_request_openai_client(reason="t")
    stream = client.chat.completions.create(
        model="deepseek/deepseek-v4.1-flash", messages=_USER_TURN, stream=True,
        extra_body={"provider": {"sort": "throughput"}, "reasoning": {"enabled": False}})
    texts = [c.choices[0].delta.content for c in stream]
    assert texts == [None, "Ход e4."]
    assert agent._coach_hedge == {"fired": True, "winner": "backup", "model": "google/gemini-3.8-flash"}
    backup_call = completions.calls[1]
    assert backup_call["model"] == "google/gemini-3.8-flash"
    # Gemini 3 cannot take "enabled: false"; the provider order is kept.
    assert backup_call["extra_body"] == {"provider": {"sort": "throughput"}, "reasoning": {"effort": "minimal"}}
    assert stalled.closed.is_set()


@pytest.mark.unit
def test_later_steps_and_gemini_turns_are_not_raced(monkeypatch):
    agent, completions = _agent({
        "deepseek/deepseek-v4.1-flash": lambda: _Stream([_chunk("a")]),
        "google/gemini-3.8-flash": lambda: _Stream([_chunk("b")]),
    }, monkeypatch)
    client = agent._create_request_openai_client(reason="t")
    after_tool = _USER_TURN + [{"role": "assistant", "content": None}, {"role": "tool", "content": "{}"}]
    step = client.chat.completions.create(model="deepseek/deepseek-v4.1-flash", messages=after_tool, stream=True)
    assert isinstance(step, _Stream)
    review = client.chat.completions.create(model="google/gemini-3.8-flash", messages=_USER_TURN, stream=True)
    assert isinstance(review, _Stream)


@pytest.mark.unit
def test_closing_the_request_client_stops_its_streams(monkeypatch):
    # The framework kills a stale stream by closing the client it asked for.
    stalled = _Stream([_chunk("a")], first_delay=5.0)
    agent, _ = _agent({"deepseek/deepseek-v4.1-flash": lambda: stalled}, monkeypatch)
    client = agent._create_request_openai_client(reason="t")
    client.chat.completions.create(model="deepseek/deepseek-v4.1-flash", messages=_USER_TURN[:1], stream=True)
    client.close()
    assert stalled.closed.is_set() and client.closed


@pytest.mark.unit
def test_mock_clients_of_the_tests_are_left_alone():
    mock = Mock()
    agent = SimpleNamespace(_create_request_openai_client=lambda *, reason: mock)
    llm_transport.install(agent)
    assert agent._create_request_openai_client(reason="t") is mock


@pytest.mark.unit
def test_the_fallback_backs_up_deepseek_but_not_gemini():
    assert llm_transport.hedge_model_for("deepseek/deepseek-v4.1-flash") == "google/gemini-3.8-flash"
    assert llm_transport.hedge_model_for("google/gemini-3.8-flash") is None


# ── the reaction ────────────────────────────────────────────────────────

def _sse(*texts):
    for t in texts:
        yield ("data: " + json.dumps({"choices": [{"delta": {"content": t}}]}) + "\n\n").encode()
    yield b"data: [DONE]\n\n"


def _slow(*texts, wait=2.0):
    time.sleep(wait)
    yield from _sse(*texts)


@pytest.mark.unit
def test_a_silent_reaction_is_taken_over_by_the_fallback(monkeypatch):
    def handler(request):
        model = json.loads(request.content)["model"]
        if model == "test/model":
            return httpx.Response(200, content=_slow("поздно"))
        assert json.loads(request.content)["reasoning"] == {"effort": "minimal"}
        return httpx.Response(200, content=_sse("Смотрю ", "на позицию."))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(quick_reply, "_http", lambda: client)
    started = time.monotonic()
    reply = quick_reply.stream_quick_reply(model="test/model", api_key="k", message="что играть?",
                                           timeout_s=5.0)
    assert reply.text == "Смотрю на позицию."
    assert reply.model == "google/gemini-3.8-flash"
    assert time.monotonic() - started < 1.9


# ── keeping the connection ──────────────────────────────────────────────

class _Body:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.read = 0
        self.closed = threading.Event()

    def __iter__(self):
        for c in self.chunks:
            self.read += 1
            yield c

    def close(self):
        self.closed.set()


@pytest.mark.unit
def test_a_body_closed_after_done_is_read_to_its_end_then_closed():
    body = _Body([b"data: {}\n\n", b"data: [DONE]\n\n", b"", b"tail"])
    stream = llm_transport._DrainAfterDone(body)
    items = iter(stream)
    next(items), next(items)  # the SDK stops at [DONE]
    stream.close()
    assert body.closed.wait(1.0)
    assert body.read == 4  # the rest was read: the connection can go back to the pool


@pytest.mark.unit
def test_a_body_closed_mid_answer_is_closed_at_once():
    body = _Body([b"data: {}\n\n", b"data: {}\n\n", b"data: [DONE]\n\n"])
    stream = llm_transport._DrainAfterDone(body)
    items = iter(stream)
    next(items)
    stream.close()
    assert body.closed.is_set() and body.read == 1
