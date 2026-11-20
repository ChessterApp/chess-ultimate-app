"""One kept-alive connection for the voice's calls to OpenRouter and ElevenLabs (20.11).

Every utterance heard (src/voice_stt.py) and every chunk read aloud (src/voice_tts.py) opened a client of its own:
a new TCP and TLS handshake each time. Measured from the stand 20.11: ElevenLabs' first byte 0.44 s on a kept
connection against 0.56 s on a new one, and 1.36 s for the first chunk on a cold one. One client per event loop
keeps the connections; ``warm`` opens them when the voice starts (GET /api/coach/voice/mode), before the first
phrase needs them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_S = 60.0
WARM_URLS = ("https://openrouter.ai/api/v1/models?limit=1", "https://api.elevenlabs.io/")
_clients: dict[int, httpx.AsyncClient] = {}


def client() -> httpx.AsyncClient:
    """The kept-alive client of the running event loop."""
    loop = asyncio.get_running_loop()
    key = id(loop)
    c = _clients.get(key)
    if c is None or c.is_closed:
        c = httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=10.0),
                              limits=httpx.Limits(max_keepalive_connections=20, keepalive_expiry=120.0))
        _clients[key] = c
    return c


class Kept:
    """What the callers close after a stream: the shared client stays open."""

    async def aclose(self) -> None:
        return None


KEPT = Kept()


async def warm(urls: tuple = WARM_URLS) -> None:
    """Open the connections ahead of the first phrase; a failure is nobody's business."""
    c = client()

    async def one(url: str) -> None:
        try:
            await c.get(url, timeout=5.0)
        except Exception:  # noqa: BLE001 — warming is a bonus
            logger.debug("voice http: warming %s failed", url, exc_info=True)

    await asyncio.gather(*(one(u) for u in urls))


def warm_soon() -> Optional[asyncio.Task]:
    """``warm`` in the background of the running loop."""
    try:
        return asyncio.get_running_loop().create_task(warm())
    except RuntimeError:
        return None
