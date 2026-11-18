"""The coach's voice for the site's voice pipeline: one chunk of the answer read aloud through OpenRouter's
speech endpoint, on the coach's one balance (25.10).

Google's own API allows a project 100 TTS calls a day on Tier 1 — the team's key in Vercel spent them in half
an hour of the stand. OpenRouter has the same Gemini Flash TTS without that cap; the key is the server's
OPENROUTER_API_KEY, so the site needs no key of its own (Asan, 25.10: «сделай через Hermes»). The audio comes
back as raw 16-bit PCM, mono, at the rate the provider names (24 kHz for Gemini), streamed through as it
arrives. Model and voice by language: COACH_TTS_MODEL / COACH_TTS_VOICE, COACH_TTS_MODEL_KK / COACH_TTS_VOICE_KK
(ElevenLabs, which streams and starts in ~0.6 s, goes in as elevenlabs/eleven-flash-v2.5 + a voice ID).

With ELEVENLABS_API_KEY set, an `elevenlabs/<model_id>` model is asked of ElevenLabs itself (16.11): OpenRouter
carries only part of their models, and the ones that speak Kazakh (eleven_v4_turbo, eleven_v3_conversational)
are asked by their own ids. The language goes along, so a short phrase is not read in a neighbouring one."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

OPENROUTER_SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format=pcm_24000"
ELEVENLABS_PREFIX = "elevenlabs/"
_LANGUAGES = ("kk", "ru", "en")
MAX_CHARS = 600
TIMEOUT_S = 20.0
DEFAULT_MODEL = "google/gemini-3.8-flash-tts"
# The voice of Gemini's TTS — what speaks when no other voice is set, and what reads a chunk ElevenLabs did not
# (the spare voice in speak()). A man's, as the coach's own is since 18.11 («мужской приветливый голос, и чтобы не
# менялся»): with Kore, a woman, a chunk read by the spare voice changed the coach's sex mid-answer. Achird is
# Google's «Friendly»; measured median pitch 141 Hz against Kore's 174.
DEFAULT_VOICE = "Achird"
# After ElevenLabs fails a chunk, the default voice reads for this long before ElevenLabs is asked again.
DIRECT_PAUSE_S = 60.0
_direct_down_until = 0.0


def voice_mode() -> str:
    """`pipeline` when COACH_VOICE_MODE says so, else `live` — the site's default voice (GET /api/coach/voice/mode)."""
    return "pipeline" if os.environ.get("COACH_VOICE_MODE", "").strip().lower() == "pipeline" else "live"


def model_and_voice(locale: Optional[str]) -> tuple[str, str]:
    """The model and voice for *locale*: Kazakh has its own pair, every other language the main one."""
    if (locale or "").lower().startswith("kk"):
        return (os.environ.get("COACH_TTS_MODEL_KK") or DEFAULT_MODEL, os.environ.get("COACH_TTS_VOICE_KK") or DEFAULT_VOICE)
    return (os.environ.get("COACH_TTS_MODEL") or DEFAULT_MODEL, os.environ.get("COACH_TTS_VOICE") or DEFAULT_VOICE)


async def open_stream(key: str, model: str, voice: str, text: str) -> tuple[httpx.AsyncClient, httpx.Response]:
    """The upstream call, left open for streaming: the caller closes both. Replaced in tests."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=10.0))
    try:
        req = client.build_request(
            "POST", OPENROUTER_SPEECH_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://chesster.io", "X-Title": "Chesster coach"},
            json={"model": model, "input": text, "voice": voice, "response_format": "pcm"},
        )
        resp = await client.send(req, stream=True)
    except Exception:
        await client.aclose()
        raise
    return client, resp


def language_of(locale: Optional[str]) -> Optional[str]:
    """The language code a provider is told for *locale* — None when it is not one of the coach's three."""
    low = (locale or "").lower()
    if low.startswith("kz"):
        return "kk"
    return next((code for code in _LANGUAGES if low.startswith(code)), None)


async def open_elevenlabs_stream(key: str, model: str, voice: str, text: str,
                                 language: Optional[str]) -> tuple[httpx.AsyncClient, httpx.Response]:
    """The same call made of ElevenLabs itself: raw 16-bit PCM at 24 kHz, streamed. Replaced in tests."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=10.0))
    payload = {"text": text, "model_id": model}
    if language:
        payload["language_code"] = language
    try:
        req = client.build_request("POST", ELEVENLABS_URL.format(voice=voice),
                                   headers={"xi-api-key": key, "Content-Type": "application/json"}, json=payload)
        resp = await client.send(req, stream=True)
    except Exception:
        await client.aclose()
        raise
    return client, resp


async def _ask(direct: bool, key: str, model: str, voice: str, text: str, locale: Optional[str]):
    """One upstream call: (client, response) with the stream open and no refusal, or the refusal alone — 429
    (a rate limit) and 402 (no credit) kept apart from a failure (502)."""
    try:
        if direct:
            client, resp = await open_elevenlabs_stream(key, model[len(ELEVENLABS_PREFIX):], voice, text, language_of(locale))
        else:
            client, resp = await open_stream(key, model, voice, text)
    except Exception as exc:  # noqa: BLE001 — the network, the timeout
        logger.warning("voice tts: upstream unreachable: %s", exc)
        return None, None, JSONResponse({"error": "TTS unreachable"}, status_code=502)
    if resp.status_code == 200:
        return client, resp, None
    detail = b""
    try:
        detail = await resp.aread()
    finally:
        await resp.aclose()
        await client.aclose()
    logger.warning("voice tts: upstream %s %s", resp.status_code, detail[:200])
    status = 429 if resp.status_code == 429 else 402 if resp.status_code == 402 else 502
    headers = {}
    retry_after = resp.headers.get("retry-after")
    if retry_after:
        headers["Retry-After"] = retry_after
    return None, None, JSONResponse({"error": f"TTS failed: {resp.status_code}"}, status_code=status, headers=headers)


async def speak(text: str, locale: Optional[str]):
    """The FastAPI response for one chunk: the PCM stream, or a JSON error — 429 (a rate limit) and 402 (no
    credit) kept apart from a failure (502), so the browser waits the first out and tells the student.

    A chunk ElevenLabs does not read (its quota spent, its key refused, the service away) is read by the default
    voice through OpenRouter instead (17.11): the coach changes voice, it does not fall silent. ElevenLabs is then
    left alone for DIRECT_PAUSE_S, so a service that is away does not hold every following chunk up."""
    global _direct_down_until
    model, voice = model_and_voice(locale)
    own_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    spare_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    direct = bool(own_key) and model.startswith(ELEVENLABS_PREFIX)
    if not (own_key if direct else spare_key):
        return JSONResponse({"error": "TTS not configured"}, status_code=500)
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        return JSONResponse({"error": "Missing text"}, status_code=400)
    refusal = None
    if direct and (not spare_key or time.monotonic() >= _direct_down_until):
        client, resp, refusal = await _ask(True, own_key, model, voice, text, locale)
        if refusal is not None and spare_key:
            _direct_down_until = time.monotonic() + DIRECT_PAUSE_S
            logger.warning("voice tts: ElevenLabs did not read the chunk (%s) — %s reads for %ss",
                           refusal.status_code, DEFAULT_MODEL, int(DIRECT_PAUSE_S))
    if not direct or (spare_key and (refusal is not None or time.monotonic() < _direct_down_until)):
        if direct:
            model, voice = DEFAULT_MODEL, DEFAULT_VOICE
        client, resp, refusal = await _ask(False, spare_key, model, voice, text, locale)
    if refusal is not None:
        return refusal
    rate_m = re.search(r"rate=(\d+)", resp.headers.get("content-type", ""))
    rate = rate_m.group(1) if rate_m else "24000"

    async def body():
        try:
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(body(), media_type="application/octet-stream",
                             headers={"Cache-Control": "no-store", "X-Sample-Rate": rate, "X-Tts-Model": model})
