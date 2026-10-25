"""2026-10-25: the site's voice pipeline reads the coach's answer aloud through Hermes (src/voice_tts.py):
OpenRouter's speech endpoint on the server's own key, raw PCM streamed back; a rate limit (429) and no
credit (402) kept apart from a failure. The site holds no key of its own (Asan: «сделай через Hermes»)."""

import pytest
from fastapi.testclient import TestClient

from src import voice_tts
from src.server import app


class _Resp:
    def __init__(self, status, chunks=(), headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = list(chunks)
        self.closed = False

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c

    async def aread(self):
        return b"".join(self._chunks)

    async def aclose(self):
        self.closed = True


class _Client:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


@pytest.fixture
def upstream(monkeypatch):
    calls = []
    state = {"resp": _Resp(200, [b"\x01\x00", b"\x02\x00\x03\x00"], {"content-type": "audio/pcm;rate=24000;channels=1"})}

    async def fake_open(key, model, voice, text):
        calls.append({"key": key, "model": model, "voice": voice, "text": text})
        return _Client(), state["resp"]

    monkeypatch.setattr(voice_tts, "open_stream", fake_open)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    for k in ("COACH_TTS_MODEL", "COACH_TTS_VOICE", "COACH_TTS_MODEL_KK", "COACH_TTS_VOICE_KK"):
        monkeypatch.delenv(k, raising=False)
    return calls, state


def _post(json, headers=None):
    return TestClient(app).post("/api/coach/voice/tts", json=json, headers={"X-User-Id": "tts-user", **(headers or {})})


def test_a_chunk_is_read_through_openrouter_and_the_bytes_stream_back(upstream):
    calls, _ = upstream
    resp = _post({"text": "  Конь эф три нападает на пешку.  ", "locale": "ru"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert resp.headers["x-sample-rate"] == "24000" and resp.headers["x-tts-model"] == "google/gemini-3.8-flash-tts"
    assert resp.content == b"\x01\x00\x02\x00\x03\x00"
    assert calls == [{"key": "sk-or-test", "model": "google/gemini-3.8-flash-tts", "voice": "Kore", "text": "Конь эф три нападает на пешку."}]


def test_kazakh_has_its_own_model_and_voice_and_the_main_pair_is_a_setting(upstream, monkeypatch):
    calls, _ = upstream
    monkeypatch.setenv("COACH_TTS_MODEL", "elevenlabs/eleven-flash-v2.5")
    monkeypatch.setenv("COACH_TTS_VOICE", "21m00Tcm4TlvDq8ikWAM")
    assert _post({"text": "Жақсы жүріс!", "locale": "kk"}).status_code == 200
    assert _post({"text": "Хороший ход.", "locale": "ru"}).status_code == 200
    assert (calls[0]["model"], calls[0]["voice"]) == ("google/gemini-3.8-flash-tts", "Kore")
    assert (calls[1]["model"], calls[1]["voice"]) == ("elevenlabs/eleven-flash-v2.5", "21m00Tcm4TlvDq8ikWAM")


def test_a_rate_limit_and_no_credit_are_told_apart_from_a_failure(upstream):
    _, state = upstream
    state["resp"] = _Resp(429, [b"quota"], {"retry-after": "7"})
    resp = _post({"text": "Привет"})
    assert resp.status_code == 429 and resp.headers["retry-after"] == "7" and state["resp"].closed
    state["resp"] = _Resp(402, [b"credit"])
    assert _post({"text": "Привет"}).status_code == 402
    state["resp"] = _Resp(500, [b"boom"])
    assert _post({"text": "Привет"}).status_code == 502


def test_refusals(upstream, monkeypatch):
    assert TestClient(app).post("/api/coach/voice/tts", json={"text": "x"}).status_code == 401   # no student id
    assert _post({"text": "   "}).status_code == 400
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert _post({"text": "Привет"}).status_code == 500


def test_an_unreachable_upstream_is_a_502_not_a_crash(monkeypatch):
    async def boom(key, model, voice, text):
        raise RuntimeError("connect failed")

    monkeypatch.setattr(voice_tts, "open_stream", boom)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert _post({"text": "Привет"}).status_code == 502
