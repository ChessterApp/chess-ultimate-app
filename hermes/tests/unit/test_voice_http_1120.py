"""20.11: the voice's calls keep one connection (src/voice_http.py) instead of a handshake per phrase."""

import asyncio

import pytest

from src import voice_http


@pytest.mark.unit
def test_one_client_per_loop_kept_open_by_the_callers_close():
    async def go():
        a, b = voice_http.client(), voice_http.client()
        await voice_http.KEPT.aclose()
        same = a is b and not a.is_closed
        await a.aclose()
        return same, voice_http.client() is not a  # a closed one is replaced

    assert asyncio.run(go()) == (True, True)


@pytest.mark.unit
def test_warming_never_fails(monkeypatch):
    async def go():
        await voice_http.warm(("http://127.0.0.1:9/nothing",))
        return True

    assert asyncio.run(go())
