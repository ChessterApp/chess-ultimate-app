"""18.11: the student's words for the voice pipeline go through this server and OpenRouter (src/voice_stt.py).

The page streamed the microphone to Google with a token of the site; the Google project ran out of prepaid credit
and every voice connection was closed («Your prepayment credits are depleted»). An utterance cut by the page now
comes here, is transcribed through OpenRouter's /audio/transcriptions on the server's key — the language named,
the chess words as key terms — and the text goes back; a rate limit and no credit are kept apart from a failure.
"""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from src import voice_stt
from src.middleware.rate_limiter import rate_limiter, voice_tts_rate_limiter
from src.server import app

pytestmark = pytest.mark.unit

H = {"X-User-Id": "stt-user"}
WAV = b"RIFF" + b"\x00" * 8000


class _Resp:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code = status
        self._body = body if body is not None else {"text": " Конь эф три. ", "usage": {"cost": 0.0002}}
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(self._body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.fixture
def upstream(monkeypatch):
    calls = []
    state = {"resp": _Resp()}

    async def fake_ask(key, model, audio, fmt, language):
        calls.append({"key": key, "model": model, "bytes": len(audio), "fmt": fmt, "language": language})
        if isinstance(state["resp"], Exception):
            raise state["resp"]
        return state["resp"]

    monkeypatch.setattr(voice_stt, "ask", fake_ask)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    for k in ("COACH_VOICE_STT_MODEL", "COACH_VOICE_STT", "COACH_VOICE_MODE"):
        monkeypatch.delenv(k, raising=False)
    rate_limiter.reset(); voice_tts_rate_limiter.reset()
    yield calls, state
    rate_limiter.reset(); voice_tts_rate_limiter.reset()


def _post(audio=WAV, locale="ru", content_type="audio/wav", headers=H):
    return TestClient(app).post("/api/coach/voice/stt", content=audio,
                                headers={**headers, "Content-Type": content_type, "X-Voice-Locale": locale})


def test_an_utterance_is_transcribed_through_openrouter_on_the_servers_key(upstream):
    calls, _ = upstream
    resp = _post()
    assert resp.status_code == 200
    out = resp.json()
    assert out["text"] == "Конь эф три." and out["model"] == "openai/gpt-transcribe" and isinstance(out["ms"], int)
    assert calls == [{"key": "sk-or-test", "model": "openai/gpt-transcribe", "bytes": len(WAV), "fmt": "wav", "language": "ru"}]


@pytest.mark.parametrize("locale, language", [("kk", "kk"), ("kz", "kk"), ("ru-RU", "ru"), ("en", "en"), ("de", None), ("", None)])
def test_the_language_of_the_talk_is_named_to_the_recogniser(upstream, locale, language):
    """Measured 18.11: without the language Kazakh went from 11.9 % wrong words to 23.3 %."""
    calls, _ = upstream
    assert _post(locale=locale).status_code == 200
    assert calls[0]["language"] == language


def test_the_model_is_a_setting_and_the_container_is_read_from_the_content_type(upstream, monkeypatch):
    calls, _ = upstream
    monkeypatch.setenv("COACH_VOICE_STT_MODEL", "google/gemini-3.5-transcribe")
    assert _post(content_type="audio/webm;codecs=opus").json()["model"] == "google/gemini-3.5-transcribe"
    assert (calls[0]["model"], calls[0]["fmt"]) == ("google/gemini-3.5-transcribe", "webm")
    assert voice_stt.audio_format("audio/x-wav") == "wav" and voice_stt.audio_format("audio/mpeg") == "mp3"
    assert voice_stt.audio_format(None) == "wav" and voice_stt.audio_format("application/octet-stream") == "wav"


def test_the_request_names_the_chess_words_and_sends_the_audio_as_base64(monkeypatch):
    """What goes to OpenRouter: the documented JSON shape, the key terms the measurement was made with."""
    sent = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent.update(url=url, json=json, headers=headers)
            return _Resp()

    monkeypatch.setattr(voice_stt.httpx, "AsyncClient", _Client)
    import asyncio

    asyncio.run(voice_stt.ask("sk-or-test", "openai/gpt-transcribe", WAV, "wav", "kk"))
    assert sent["url"] == "https://openrouter.ai/api/v1/audio/transcriptions"
    assert sent["headers"]["Authorization"] == "Bearer sk-or-test"
    body = sent["json"]
    assert body["model"] == "openai/gpt-transcribe" and body["language"] == "kk"
    assert base64.b64decode(body["input_audio"]["data"]) == WAV and body["input_audio"]["format"] == "wav"
    assert "рокировка" in body["keyterms"] and "уәзір" in body["keyterms"] and "en passant" in body["keyterms"]


def test_a_noise_is_no_words_and_no_call(upstream):
    """A click shorter than a tenth of a second is not sent anywhere; words the recogniser did not find are ''."""
    calls, state = upstream
    assert _post(audio=b"RIFF" + b"\x00" * 100).json()["text"] == "" and calls == []
    state["resp"] = _Resp(body={"text": "   "})
    assert _post().json()["text"] == ""


def test_a_rate_limit_and_no_credit_are_told_apart_from_a_failure(upstream):
    _, state = upstream
    state["resp"] = _Resp(429, {"error": "slow down"}, {"retry-after": "5"})
    resp = _post()
    assert resp.status_code == 429 and resp.headers["retry-after"] == "5"
    state["resp"] = _Resp(402, {"error": "credit"})
    assert _post().status_code == 402
    state["resp"] = _Resp(500, {"error": "boom"})
    assert _post().status_code == 502
    state["resp"] = RuntimeError("connect failed")
    assert _post().status_code == 502
    state["resp"] = _Resp(200, ValueError("not json"), text="<html>")
    assert _post().status_code == 502


def test_refusals(upstream, monkeypatch):
    assert TestClient(app).post("/api/coach/voice/stt", content=WAV).status_code == 401      # no student id
    assert _post(audio=b"\x00" * (voice_stt.MAX_BYTES + 1)).status_code == 413               # not one utterance
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert _post().status_code == 500


def test_the_server_tells_the_page_who_hears(upstream, monkeypatch):
    """GET /api/coach/voice/mode: `stt` is "server" with the key — the page sends utterances here — and "google"
    without it or when the road is switched off (COACH_VOICE_STT=off): the page streams to Google as before."""
    get = lambda: TestClient(app).get("/api/coach/voice/mode", headers=H).json()
    assert get() == {"mode": "live", "stt": "server"}
    monkeypatch.setenv("COACH_VOICE_MODE", "pipeline")
    assert get() == {"mode": "pipeline", "stt": "server"}
    monkeypatch.setenv("COACH_VOICE_STT", "off")
    assert get() == {"mode": "pipeline", "stt": "google"}
    monkeypatch.delenv("COACH_VOICE_STT")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert get()["stt"] == "google"
