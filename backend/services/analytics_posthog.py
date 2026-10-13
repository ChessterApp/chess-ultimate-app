"""Server-side PostHog capture for Flask (tracking plan §7 / F6).

Authoritative events (level assignment, lesson progress, reviews, databases)
are captured here so ad blockers can't drop them. `distinct_id` is always the
Clerk user id (the parent account). Analytics must never break a request: a
missing key or any PostHog error is logged and swallowed.

Event names must also be registered in the frontend's single registry
(`frontend/src/lib/analytics/events.ts` ANALYTICS_EVENTS) — `SERVER_EVENTS`
mirrors the subset used here and tests/test_analytics_posthog.py asserts it is
a subset of the TS registry.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

POSTHOG_CAPTURE_HOST = 'https://us.i.posthog.com'

# Event names emitted from Flask. Keep ⊆ ANALYTICS_EVENTS in events.ts.
LEVEL_ASSIGNED = 'level_assigned'
LESSON_STARTED = 'lesson_started'
LESSON_COMPLETED = 'lesson_completed'
LEVEL_COMPLETED = 'level_completed'
GAME_REVIEW_COMPLETED = 'game_review_completed'
DATABASE_CREATED = 'database_created'
DATABASE_SHARED = 'database_shared'

SERVER_EVENTS = frozenset({
    LEVEL_ASSIGNED,
    LESSON_STARTED,
    LESSON_COMPLETED,
    LEVEL_COMPLETED,
    GAME_REVIEW_COMPLETED,
    DATABASE_CREATED,
    DATABASE_SHARED,
})

# Mirror of PII_DENYLIST / PII_DENYLIST_PREFIXES in events.ts.
PII_DENYLIST = frozenset({
    'name', 'companion_name', 'email', 'fen', 'pgn', 'san', 'uci', 'move',
    'moves', 'squares', 'placement', 'solution', 'prompt', 'hint', 'text',
    'phone', 'dob', 'transcript', 'message', 'content',
})
PII_DENYLIST_PREFIXES = ('birth',)

_client = None
_client_lock = threading.Lock()


def _is_pii_key(key: str) -> bool:
    k = key.lower()
    return k in PII_DENYLIST or k.startswith(PII_DENYLIST_PREFIXES)


def strip_pii(props: dict[str, Any] | None) -> dict[str, Any]:
    """Drop PII / raw-chess-text keys, recursing into nested dicts ($set …)."""
    out: dict[str, Any] = {}
    for key, value in (props or {}).items():
        if _is_pii_key(key):
            continue
        out[key] = strip_pii(value) if isinstance(value, dict) else value
    return out


def _project_key() -> str | None:
    return os.environ.get('POSTHOG_PROJECT_KEY') or os.environ.get('NEXT_PUBLIC_POSTHOG_KEY') or None


def _get_client():
    """Lazily build one process-wide client (batched background sender)."""
    global _client
    if _client is not None:
        return _client
    key = _project_key()
    if not key:
        return None
    with _client_lock:
        if _client is None:
            from posthog import Posthog
            _client = Posthog(key, host=POSTHOG_CAPTURE_HOST)
    return _client


def capture(distinct_id: str | None, event: str, props: dict[str, Any] | None = None) -> None:
    """Capture `event` for `distinct_id`. Never raises."""
    if not distinct_id:
        return
    try:
        client = _get_client()
        if client is None:
            return
        client.capture(event, distinct_id=distinct_id, properties=strip_pii(props))
    except Exception as exc:  # analytics never breaks a request
        logger.warning('posthog capture %s failed: %s', event, exc)
