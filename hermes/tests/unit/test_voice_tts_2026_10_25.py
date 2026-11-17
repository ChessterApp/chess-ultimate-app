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
    for k in ("COACH_TTS_MODEL", "COACH_TTS_VOICE", "COACH_TTS_MODEL_KK", "COACH_TTS_VOICE_KK", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(voice_tts, "_direct_down_until", 0.0)
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


def test_with_its_own_key_an_elevenlabs_model_is_asked_of_elevenlabs_with_the_language(upstream, monkeypatch):
    """16.11: the ElevenLabs models that speak Kazakh are not all on OpenRouter — with ELEVENLABS_API_KEY the
    `elevenlabs/<model_id>` pair goes to ElevenLabs itself, the language named; other models stay on OpenRouter."""
    calls, state = upstream
    direct = []

    async def fake_eleven(key, model, voice, text, language):
        direct.append({"key": key, "model": model, "voice": voice, "text": text, "language": language})
        return _Client(), _Resp(200, [b"\x05\x00"], {"content-type": "audio/pcm"})

    monkeypatch.setattr(voice_tts, "open_elevenlabs_stream", fake_eleven)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    monkeypatch.setenv("COACH_TTS_MODEL_KK", "elevenlabs/eleven_v4_turbo")
    monkeypatch.setenv("COACH_TTS_VOICE_KK", "voice-kk")
    resp = _post({"text": "Жақсы жүріс!", "locale": "kk"})
    assert resp.status_code == 200 and resp.content == b"\x05\x00"
    assert resp.headers["x-sample-rate"] == "24000" and resp.headers["x-tts-model"] == "elevenlabs/eleven_v4_turbo"
    assert direct == [{"key": "el-test", "model": "eleven_v4_turbo", "voice": "voice-kk", "text": "Жақсы жүріс!", "language": "kk"}]
    assert _post({"text": "Хороший ход.", "locale": "ru"}).status_code == 200
    assert [c["model"] for c in calls] == ["google/gemini-3.8-flash-tts"] and len(direct) == 1


def test_without_its_own_key_an_elevenlabs_model_stays_on_openrouter(upstream, monkeypatch):
    calls, _ = upstream
    monkeypatch.setenv("COACH_TTS_MODEL", "elevenlabs/eleven-flash-v2.5")
    assert _post({"text": "Хороший ход.", "locale": "ru"}).status_code == 200
    assert calls[0]["model"] == "elevenlabs/eleven-flash-v2.5" and calls[0]["key"] == "sk-or-test"


def test_a_chunk_elevenlabs_does_not_read_is_read_by_the_default_voice(upstream, monkeypatch):
    """17.11: ElevenLabs out of quota (or away) must not silence the coach — the chunk goes to the default voice
    through OpenRouter, and ElevenLabs is left alone for a while, then asked again."""
    calls, _ = upstream
    direct = []
    answer = {"resp": lambda: _Resp(401, [b'{"detail":{"status":"quota_exceeded"}}'])}

    async def fake_eleven(key, model, voice, text, language):
        direct.append(text)
        resp = answer["resp"]()
        if isinstance(resp, Exception):
            raise resp
        return _Client(), resp

    clock = {"now": 1000.0}
    monkeypatch.setattr(voice_tts, "open_elevenlabs_stream", fake_eleven)
    monkeypatch.setattr(voice_tts.time, "monotonic", lambda: clock["now"])
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    monkeypatch.setenv("COACH_TTS_MODEL", "elevenlabs/eleven_v4_turbo")
    monkeypatch.setenv("COACH_TTS_VOICE", "voice-ru")
    resp = _post({"text": "Первый кусок.", "locale": "ru"})
    assert resp.status_code == 200 and resp.content == b"\x01\x00\x02\x00\x03\x00"
    assert resp.headers["x-tts-model"] == "google/gemini-3.8-flash-tts"
    assert (calls[0]["model"], calls[0]["voice"], calls[0]["key"]) == ("google/gemini-3.8-flash-tts", "Kore", "sk-or-test")
    # Within the pause the next chunk does not wait on ElevenLabs at all.
    assert _post({"text": "Второй кусок.", "locale": "ru"}).headers["x-tts-model"] == "google/gemini-3.8-flash-tts"
    assert direct == ["Первый кусок."] and len(calls) == 2
    # After it ElevenLabs is asked again — and, back in service, reads.
    clock["now"] += voice_tts.DIRECT_PAUSE_S + 1
    answer["resp"] = lambda: _Resp(200, [b"\x09\x00"], {"content-type": "audio/pcm"})
    resp = _post({"text": "Третий кусок.", "locale": "ru"})
    assert resp.content == b"\x09\x00" and resp.headers["x-tts-model"] == "elevenlabs/eleven_v4_turbo" and len(calls) == 2
    # Away altogether (the network): the same way out.
    answer["resp"] = lambda: RuntimeError("connect failed")
    assert _post({"text": "Четвёртый кусок.", "locale": "ru"}).headers["x-tts-model"] == "google/gemini-3.8-flash-tts"


def test_without_openrouter_an_elevenlabs_refusal_is_told_as_it_is(upstream, monkeypatch):
    async def fake_eleven(key, model, voice, text, language):
        return _Client(), _Resp(429, [b"busy"], {"retry-after": "3"})

    monkeypatch.setattr(voice_tts, "open_elevenlabs_stream", fake_eleven)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    monkeypatch.setenv("COACH_TTS_MODEL", "elevenlabs/eleven_v4_turbo")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    resp = _post({"text": "Привет", "locale": "ru"})
    assert resp.status_code == 429 and resp.headers["retry-after"] == "3"
    assert _post({"text": "Привет ещё раз", "locale": "ru"}).status_code == 429   # no pause without a way out


@pytest.mark.parametrize("locale, language", [("kk", "kk"), ("kz", "kk"), ("ru-RU", "ru"), ("en", "en"), ("de", None), (None, None)])
def test_the_language_named_to_the_provider(locale, language):
    assert voice_tts.language_of(locale) == language


def test_the_server_names_the_default_voice_mode(monkeypatch):
    """17.11: the site asks which voice to turn on by default; COACH_VOICE_MODE=pipeline switches it, anything
    else (and nothing) is Gemini Live."""
    get = lambda: TestClient(app).get("/api/coach/voice/mode", headers={"X-User-Id": "tts-user"})
    monkeypatch.delenv("COACH_VOICE_MODE", raising=False)
    assert get().json() == {"mode": "live"}
    monkeypatch.setenv("COACH_VOICE_MODE", " Pipeline ")
    assert get().json() == {"mode": "pipeline"}
    monkeypatch.setenv("COACH_VOICE_MODE", "something")
    assert get().json() == {"mode": "live"}
    assert TestClient(app).get("/api/coach/voice/mode").status_code == 401
