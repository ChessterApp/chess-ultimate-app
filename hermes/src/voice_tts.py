"""The coach's voice for the site's voice pipeline: one chunk of the answer read aloud through OpenRouter's
speech endpoint, on the coach's one balance (25.10).

Google's own API allows a project 100 TTS calls a day on Tier 1 — the team's key in Vercel spent them in half
an hour of the stand. OpenRouter has the same Gemini Flash TTS without that cap; the key is the server's
OPENROUTER_API_KEY, so the site needs no key of its own (Asan, 25.10: «сделай через Hermes»). The audio comes
back as raw 16-bit PCM, mono, at the rate the provider names (24 kHz for Gemini), streamed through as it
arrives. Model and voice by language: COACH_TTS_MODEL / COACH_TTS_VOICE, COACH_TTS_MODEL_KK / COACH_TTS_VOICE_KK
(ElevenLabs, which streams and starts in ~0.6 s, goes in as elevenlabs/eleven-flash-v2.5 + a voice ID)."""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

OPENROUTER_SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
MAX_CHARS = 600
TIMEOUT_S = 20.0
DEFAULT_MODEL = "google/gemini-3.8-flash-tts"
DEFAULT_VOICE = "Kore"


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


async def speak(text: str, locale: Optional[str]):
    """The FastAPI response for one chunk: the PCM stream, or a JSON error — 429 (a rate limit) and 402 (no
    credit) kept apart from a failure (502), so the browser waits the first out and tells the student."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return JSONResponse({"error": "TTS not configured"}, status_code=500)
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        return JSONResponse({"error": "Missing text"}, status_code=400)
    model, voice = model_and_voice(locale)
    try:
        client, resp = await open_stream(key, model, voice, text)
    except Exception as exc:  # noqa: BLE001 — the network, the timeout
        logger.warning("voice tts: upstream unreachable: %s", exc)
        return JSONResponse({"error": "TTS unreachable"}, status_code=502)
    if resp.status_code != 200:
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
        return JSONResponse({"error": f"TTS failed: {resp.status_code}"}, status_code=status, headers=headers)
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
