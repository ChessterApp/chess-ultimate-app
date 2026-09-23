"""The first-stage reaction call: prompt shape and SSE parsing, no network."""

import json

import httpx
import pytest

from src import quick_reply
from src.quick_reply import build_quick_messages, stream_quick_reply


def _sse(*events) -> bytes:
    body = ""
    for e in events:
        body += "data: " + (e if isinstance(e, str) else json.dumps(e)) + "\n\n"
    return body.encode()


def _chunk(text=None, usage=None):
    ev = {"choices": [{"delta": {"content": text} if text is not None else {}}]}
    if usage:
        ev["usage"] = usage
    return ev


def _run(handler, **kw):
    """Call stream_quick_reply against an httpx.MockTransport."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    class _Client(real_client):
        def __init__(self, *a, **k):
            k["transport"] = transport
            super().__init__(*a, **k)

    original = quick_reply.httpx.Client
    quick_reply.httpx.Client = _Client
    try:
        return stream_quick_reply(model="test/model", api_key="k", message="что играть?", **kw)
    finally:
        quick_reply.httpx.Client = original


@pytest.mark.unit
def test_prompt_names_language_and_hides_the_fen():
    msgs = build_quick_messages("что играть?", "ru", "8/8/8/8/8/8/8/K6k w - - 0 1")
    assert msgs[0]["role"] == "system"
    assert "in Russian" in msgs[0]["content"]
    assert "NEVER name a move" in msgs[0]["content"]
    assert msgs[1]["content"].startswith("[A position is set up")
    assert "8/8/8" not in msgs[1]["content"]  # the FEN itself is not sent
    assert "in Kazakh" in build_quick_messages("x", "kz", None)[0]["content"]
    assert "the student's language" in build_quick_messages("x", None, None)[0]["content"]


@pytest.mark.unit
def test_streams_chunks_and_collects_usage():
    seen = []
    captured = {}

    def handler(request: httpx.Request):
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=_sse(
            _chunk("Смотрю "), _chunk("на позицию."),
            _chunk(None, usage={"prompt_tokens": 41, "completion_tokens": 7}), "[DONE]",
        ))

    reply = _run(handler, on_delta=seen.append, locale="ru", max_tokens=33)
    assert reply.ok
    assert seen == ["Смотрю ", "на позицию."]
    assert reply.text == "Смотрю на позицию."
    assert (reply.prompt_tokens, reply.completion_tokens) == (41, 7)
    assert reply.first_token_ms is not None
    body = captured["body"]
    assert body["model"] == "test/model"
    assert body["stream"] is True
    assert body["max_tokens"] == 33
    assert body["reasoning"] == {"enabled": False}
    assert captured["auth"] == "Bearer k"


@pytest.mark.unit
def test_http_error_is_reported_not_raised():
    def handler(request):
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    reply = _run(handler)
    assert not reply.ok
    assert reply.error.startswith("http_429")
    assert reply.text == ""


@pytest.mark.unit
def test_abort_stops_reading():
    seen = []

    def handler(request):
        return httpx.Response(200, content=_sse(_chunk("a "), _chunk("b "), _chunk("c"), "[DONE]"))

    reply = _run(handler, on_delta=seen.append, should_abort=lambda: len(seen) >= 1)
    assert seen == ["a "]
    assert reply.error == "aborted"


@pytest.mark.unit
def test_missing_key_short_circuits():
    reply = stream_quick_reply(model="m", api_key="", message="x")
    assert reply.error == "no_api_key"
    assert not reply.ok


@pytest.mark.unit
def test_too_short_reaction_is_not_ok():
    def handler(request):
        return httpx.Response(200, content=_sse(_chunk("OK"), "[DONE]"))

    reply = _run(handler)
    assert reply.text == "OK"
    assert not reply.ok


@pytest.mark.unit
def test_greetings_and_asides_get_no_reaction():
    from src.quick_reply import wants_reaction

    assert not wants_reaction("Привет!", False)
    assert not wants_reaction("спасибо", False)
    assert not wants_reaction("", True)
    assert wants_reaction("Что играть?", True)  # short, but a position is on the board
    assert wants_reaction("Объясни идею сицилианской защиты", False)
