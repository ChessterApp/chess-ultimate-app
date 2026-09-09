"""Coach feedback persistence — best-effort Supabase UPSERT / DELETE.

Stores the explicit 👍/👎 a user gives a coach answer (migration 009). This is a
**LOG-ONLY** signal: it is never read in the serving path and never alters
prompts, routing, memory, or rewards. Follows the fail-open style of
``session_persistence.py`` — every entry point swallows exceptions and reports
success as a bool, so the endpoint can return ``{persisted: ...}`` without ever
500ing on a sink failure or blocking a turn.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("hermes.coach_feedback")

TIMEOUT = 10
COMMENT_MAX = 500  # persisted comment length cap (truncated, not rejected)


def _supabase() -> tuple[str, str]:
    """Read the Supabase REST creds fresh (so tests can monkeypatch env)."""
    return (
        os.environ.get("SUPABASE_URL", ""),
        os.environ.get("SUPABASE_SERVICE_KEY", ""),
    )


def _headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def upsert_feedback(
    user_id: str,
    turn_id: str,
    rating: int,
    *,
    session_id: Optional[str] = None,
    comment: Optional[str] = None,
    surface: str = "text",
    client_ts: Optional[str] = None,
) -> bool:
    """UPSERT one ``(user_id, turn_id)`` verdict into ``coach_feedback``.

    Best-effort: returns ``True`` only when the row was persisted. Missing
    Supabase config or any network/HTTP error returns ``False`` — the caller
    still succeeds (the feedback event is spooled regardless). Never raises.
    """
    url, key = _supabase()
    if not (url and key):
        return False
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "user_id": user_id,
        "turn_id": turn_id,
        "rating": rating,
        "session_id": session_id,
        "comment": comment[:COMMENT_MAX] if comment else None,
        "surface": surface,
        "client_ts": client_ts,
        "updated_at": now,
    }
    headers = _headers(key)
    headers["Prefer"] = "resolution=merge-duplicates"
    try:
        httpx.post(
            f"{url}/rest/v1/coach_feedback",
            params={"on_conflict": "user_id,turn_id"},
            json=row,
            headers=headers,
            timeout=TIMEOUT,
        ).raise_for_status()
        return True
    except Exception:
        logger.debug(
            "coach_feedback upsert failed for turn %s", turn_id, exc_info=True
        )
        return False


def delete_feedback(user_id: str, turn_id: str) -> bool:
    """DELETE the ``(user_id, turn_id)`` verdict — the rating-0 retraction.

    Best-effort: returns ``True`` on a clean delete, ``False`` on missing config
    or any error. Never raises.
    """
    url, key = _supabase()
    if not (url and key):
        return False
    try:
        httpx.delete(
            f"{url}/rest/v1/coach_feedback",
            params={"user_id": f"eq.{user_id}", "turn_id": f"eq.{turn_id}"},
            headers=_headers(key),
            timeout=TIMEOUT,
        ).raise_for_status()
        return True
    except Exception:
        logger.debug(
            "coach_feedback delete failed for turn %s", turn_id, exc_info=True
        )
        return False
