"""One connection pool for every request to Supabase.

Every module used to call ``httpx.get`` / ``httpx.post`` — a new TCP and TLS
handshake per request. From the production host that is 50–150 ms on top of
each roundtrip, and a turn makes several (session, boards, messages, profile,
analytics, events). A process-wide ``httpx.Client`` keeps the connections open
between requests; it is thread-safe, so the persistence threads share it.

Each module keeps a tiny ``_sb()``: ``client() or httpx`` — the pooled client
takes what ``httpx.get`` took. SUPABASE_HTTP_POOL=0 goes back to a fresh
connection per request.
"""

from __future__ import annotations

import os
import threading

import httpx

_client: httpx.Client | None = None
_lock = threading.Lock()

_POOLED = os.environ.get("SUPABASE_HTTP_POOL", "1").strip().lower() not in ("0", "false", "no", "off")


def client():
    """The shared pooled client, or None when the pool is off (callers then use
    their own ``httpx`` module functions — which is also what the unit tests
    patch)."""
    global _client
    if not _POOLED:
        return None
    if _client is None:
        with _lock:
            if _client is None:
                _client = httpx.Client(
                    timeout=10.0,
                    limits=httpx.Limits(max_connections=32, max_keepalive_connections=16, keepalive_expiry=120.0),
                )
    return _client
