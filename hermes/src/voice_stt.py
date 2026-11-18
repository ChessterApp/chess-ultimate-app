"""The student's words for the site's voice pipeline: one utterance, recorded by the page, turned into text
through OpenRouter's transcription endpoint on the coach's one balance (18.11).

Until now the page streamed the microphone straight to Google (the transcription-only Live model, a one-use
token minted by the site with the team's Google key). On 18.11 that project ran out of prepaid credit and Google
closed every voice connection («Your prepayment credits are depleted») — the pipeline hung on «Подключение…»,
Gemini Live answered «disconnected». Alexander: «подключи его через OpenRouter». The words now take the road the
voice already takes (src/voice_tts.py): the page cuts an utterance by its own silence detector, sends it here, and
this server asks OpenRouter with OPENROUTER_API_KEY — the site holds no key, Google is not in the path.

The model is COACH_VOICE_STT_MODEL (default openai/gpt-transcribe). Measured 18.11 on the 90 recordings of
local-preview/voice-test/speech-1117 (10 Russian and 10 Kazakh chess phrases, four voices), wrong words ru / kk,
the request's time p50, the price of a minute of audio:

    openai/gpt-transcribe            0.4 % / 11.9 %   1.2 s   $0.0054      (the default)
    google/gemini-3.5-transcribe     1.3 % / 10.8 %   3.0 s   $0.0061
    elevenlabs/scribe-v2             0.4 % / 17.0 %   1.5 s   $0.0045
    deepgram/nova-3                  8.9 % / 19.9 %   1.6 s   $0.0043
    openai/whisper-large-v3-turbo    4.9 % / 38.6 %   1.4 s   $0.0005
    openai/gpt-4o-transcribe         0.9 % / 48.9 %   1.4 s   $0.0045

The language named and the chess words given as key terms are part of that result: without the language Kazakh
went from 11.9 % to 23.3 % wrong, without the key terms Russian from 0.4 % to 2.2 % and Kazakh to 17.6 %.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Optional

import httpx
from fastapi.responses import JSONResponse

from src.voice_tts import language_of

logger = logging.getLogger(__name__)

OPENROUTER_STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
DEFAULT_MODEL = "openai/gpt-transcribe"
TIMEOUT_S = 20.0
# One utterance: a minute of 16 kHz mono 16-bit audio is 1.9 MB. More than that is not a phrase said to a coach.
MAX_BYTES = 2_500_000
MIN_BYTES = 3_200          # a tenth of a second: a click, not a word
FORMATS = ("wav", "webm", "ogg", "mp3", "m4a", "flac")
# The chess words a recogniser mishears without a hint — the list the site gives Google's transcription
# (frontend/src/app/api/coach/live-token/route.ts, CHESS_VOCABULARY): kept the same, so both roads hear alike.
KEYTERMS = [
    "рокировка", "взятие на проходе", "пат", "мат", "шах", "ферзь", "ладья", "слон", "конь", "пешка",
    "позиция Лусены", "Лусена", "позиция Филидора", "Филидор", "жареная печень", "сицилианская защита",
    "дебют", "эндшпиль", "связка", "вилка", "отвлечение", "завлечение",
    "рокировка жасау", "уәзір", "тура", "піл", "ат", "сарбаз", "патша",
    "castling", "en passant", "stalemate", "checkmate", "Lucena", "Philidor",
]


def stt_model() -> str:
    return (os.environ.get("COACH_VOICE_STT_MODEL") or "").strip() or DEFAULT_MODEL


def stt_ready() -> bool:
    """This server can hear for the page: it has the key, and the road is not switched off
    (COACH_VOICE_STT=off leaves the page on Google's streaming transcription, as before 18.11)."""
    if (os.environ.get("COACH_VOICE_STT") or "").strip().lower() in ("off", "0", "google", "gemini"):
        return False
    return bool((os.environ.get("OPENROUTER_API_KEY") or "").strip())


def audio_format(content_type: Optional[str]) -> str:
    """wav for audio/wav and anything unnamed; the container the page names otherwise (audio/webm;codecs=opus → webm)."""
    kind = (content_type or "").split(";")[0].strip().lower()
    name = kind.split("/")[-1].replace("x-", "")
    name = {"mpeg": "mp3", "mp4": "m4a", "wave": "wav"}.get(name, name)
    return name if name in FORMATS else "wav"


async def ask(key: str, model: str, audio: bytes, fmt: str, language: Optional[str]) -> httpx.Response:
    """The upstream call. Replaced in tests."""
    payload = {"model": model, "input_audio": {"data": base64.b64encode(audio).decode(), "format": fmt},
               "keyterms": KEYTERMS}
    if language:
        payload["language"] = language
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=10.0)) as client:
        return await client.post(
            OPENROUTER_STT_URL, json=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://chesster.io", "X-Title": "Chesster coach"})


async def transcribe(audio: bytes, content_type: Optional[str], locale: Optional[str]):
    """The FastAPI response for one utterance: {"text", "model", "ms"} — the text may be empty (a cough, a noise:
    the page then sends nothing to the coach) — or a JSON error: 429 (a rate limit) and 402 (no credit) kept
    apart from a failure (502), as the reading's are (src/voice_tts.speak)."""
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return JSONResponse({"error": "STT not configured"}, status_code=500)
    if not audio or len(audio) < MIN_BYTES:
        return JSONResponse({"text": "", "model": stt_model(), "ms": 0})
    if len(audio) > MAX_BYTES:
        return JSONResponse({"error": "Audio too long"}, status_code=413)
    model = stt_model()
    started = time.monotonic()
    try:
        resp = await ask(key, model, audio, audio_format(content_type), language_of(locale))
    except Exception as exc:  # noqa: BLE001 — the network, the timeout
        logger.warning("voice stt: upstream unreachable: %s", exc)
        return JSONResponse({"error": "STT unreachable"}, status_code=502)
    ms = int((time.monotonic() - started) * 1000)
    if resp.status_code != 200:
        logger.warning("voice stt: upstream %s %s", resp.status_code, (resp.text or "")[:200])
        status = 429 if resp.status_code == 429 else 402 if resp.status_code == 402 else 502
        headers = {}
        retry_after = resp.headers.get("retry-after")
        if retry_after:
            headers["Retry-After"] = retry_after
        return JSONResponse({"error": f"STT failed: {resp.status_code}"}, status_code=status, headers=headers)
    try:
        text = str((resp.json() or {}).get("text") or "").strip()
    except Exception:  # noqa: BLE001 — not JSON
        logger.warning("voice stt: upstream answer is not JSON")
        return JSONResponse({"error": "STT failed: bad answer"}, status_code=502)
    logger.info("voice stt: %s, %d bytes, %d ms, %d chars", model, len(audio), ms, len(text))
    return JSONResponse({"text": text, "model": model, "ms": ms}, headers={"Cache-Control": "no-store"})
