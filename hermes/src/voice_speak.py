"""The first sentence of a spoken answer, read aloud by this server inside the chat's own stream (20.11).

The voice pipeline read every sentence through its own request — page → site (Vercel) → this server → ElevenLabs —
after the sentence had come down the chat stream: on production the first sound came 1.0-1.8 s after the sentence
against 0.3 s from this server itself. A page that says it takes audio in the stream (``speech_audio``) gets the
first sentence's sound in it: a ``speech`` frame before the sentence's text — ``{"id": 1, "text": <the exact head of
the answer's text it covers>}`` — then ``speech_audio`` frames (``{"id", "pcm"}``, base64 of 16-bit PCM at 24 kHz)
and a ``speech_done`` frame (``{"id", "ok"}``). The page drops that text from what it reads itself and plays the
frames; when ``ok`` is false and no sound came it reads the sentence itself, as before. The rest of the answer is
read by the page: its chunks are fetched while the first one plays.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# The page's own sentence end (frontend lib/coach/voice-pipeline.ts SENTENCE_END): a dot inside a move («1.e4») is
# not one — a boundary needs whitespace or the end after it.
_SENTENCE_END = re.compile(r"[.!?…]+(?:[\"»)]+)?(?=\s|$)")
MIN_PART_BYTES = 4800  # 100 ms of 24 kHz PCM16: the page's own least part (pipeline-voice MIN_PART_BYTES)
FIRST_MAX_CHARS = 220  # a longer first sentence is left to the page, which splits it


def first_sentence(text: str) -> Optional[str]:
    """The head of *text* up to the end of its first sentence, exactly as it stands in *text* — the page drops these
    characters from what it reads. None when no sentence ends in it or the sentence has nothing to say."""
    m = _SENTENCE_END.search(text or "")
    if not m:
        return None
    head = text[: m.end()]
    if len(head) > FIRST_MAX_CHARS or not speakable(head):
        return None
    return head


def speakable(text: str) -> str:
    """The words of *text* as they are read: board marks, links, markdown and system records out (the page's
    voice-pipeline.ts speakable / voice-notes.ts stripNotes)."""
    t = re.sub(r"\[\[[^\]]*\]\]", " ", text or "")
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\((?:https?://|/)[^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\[\s*[A-Za-zА-Яа-яЁё]{2,20}(?:[ \t]+[A-Za-zА-Яа-яЁё]{2,20}){0,2}\s*(?::[^\]\n]{0,200})?\]", " ", t)
    t = re.sub(r"\b[rnbqkpRNBQKP1-8]{1,8}(?:/[rnbqkpRNBQKP1-8]{1,8}){7}\s+[wb]\b[^\n]*", " ", t)
    t = t.replace("`", "")
    t = re.sub(r"\*\*|__", "", t)
    t = re.sub(r"(^|\n)\s{0,3}(?:[-*•]|\d+[.)])\s+", r"\1", t)
    t = re.sub(r"(^|\n)\s{0,3}#{1,6}\s+", r"\1", t)
    t = re.sub(r"(^|\s)[*_](\S[^*_]*\S|\S)[*_](?=[\s.,!?;:]|$)", r"\1\2", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s*\n+\s*", " ", t)
    t = re.sub(r"\s+([.,!?;:])", r"\1", t).strip()
    return t if re.search(r"\w", t) else ""


async def stream(text: str, locale: Optional[str], emit: Callable[[str, dict], Awaitable[None] | None],
                 speech_id: int = 1) -> bool:
    """Read *text* aloud (src/voice_tts.open_speech: ElevenLabs, its spare voice through OpenRouter) and hand each
    part to *emit* as ("speech_audio", {"id", "pcm"}); then ("speech_done", {"id", "ok"}). True when sound went out."""
    from src.voice_tts import open_speech

    sent = False
    client = resp = None
    try:
        client, resp, _model, rate, refusal = await open_speech(speakable(text), locale)
        if refusal is None and str(rate) == "24000":
            held = b""
            async for chunk in resp.aiter_bytes():
                held += chunk
                if len(held) >= MIN_PART_BYTES:
                    even = len(held) - len(held) % 2
                    await _call(emit, "speech_audio", {"id": speech_id, "pcm": base64.b64encode(held[:even]).decode()})
                    held = held[even:]
                    sent = True
            even = len(held) - len(held) % 2
            if even:
                await _call(emit, "speech_audio", {"id": speech_id, "pcm": base64.b64encode(held[:even]).decode()})
                sent = True
    except Exception:  # noqa: BLE001 — the page reads the sentence itself
        logger.warning("voice speak: the first sentence was not read here", exc_info=True)
    finally:
        try:
            if resp is not None:
                await resp.aclose()
            if client is not None:
                await client.aclose()
        except Exception:  # noqa: BLE001
            pass
        await _call(emit, "speech_done", {"id": speech_id, "ok": sent})
    return sent


async def _call(emit, kind: str, payload: dict) -> None:
    out = emit(kind, payload)
    if out is not None and hasattr(out, "__await__"):
        await out
