"""Voice Mode minutes ledger — per-user, per-calendar-month (UTC) metering.

Voice Mode is metered by minutes: by default every user gets 30 minutes per
calendar month (see :func:`tier_limit_seconds` / the ``VOICE_MINUTES_*`` env
vars). Text chat is unlimited — this module has nothing to do with it.

Storage is Supabase (``voice_usage`` table, migration 006): one row per
``(user_id, session_id)`` that heartbeats accumulate into, and the monthly usage
is the SUM of ``seconds`` for a user within a ``month_key`` (``YYYY-MM``).

Fail-open by design. If Supabase is unconfigured or unreachable the ledger
transparently falls back to an in-process dict so enforcement degrades
gracefully (best-effort metering) instead of crashing or locking users out —
every fallback is logged. The frontend mint path additionally fails open if the
quota lookup itself errors, so an outage never blocks a voice session.
"""

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("hermes.voice_quota")

# Default monthly allowance, in minutes, for every tier. Billing isn't live yet,
# so premium/pro intentionally match free — "by default users only get 30
# minutes". Ops can raise a tier without a deploy via the env vars below. A
# value of 0 or the string "unlimited" means no cap.
_DEFAULT_MINUTES = 30

# Cap a single heartbeat delta so a bad/replayed client beacon can't inflate
# usage: at most 2 minutes of spoken time can be booked by one heartbeat.
MAX_HEARTBEAT_DELTA = 120

# Short timeout so a slow Supabase never blocks the voice path — we fail open.
_HTTP_TIMEOUT = 5.0


def month_key(now: Optional[datetime] = None) -> str:
    """Return the current UTC month bucket, e.g. ``2026-09``."""
    now = now or datetime.now(timezone.utc)
    return f"{now:%Y-%m}"


def _tier_env(tier: str) -> str:
    """Env var name holding a tier's monthly minute allowance."""
    return f"VOICE_MINUTES_{tier.upper()}"


def tier_limit_seconds(tier: str) -> Optional[int]:
    """Resolve a tier's monthly voice allowance to seconds.

    Reads ``VOICE_MINUTES_<TIER>`` (default 30 for every tier). Returns ``None``
    when the tier is unlimited (env value ``0`` or ``unlimited``).
    """
    raw = os.environ.get(_tier_env(tier))
    if raw is None:
        # Unknown tiers fall back to the free allowance rather than unlimited.
        raw = os.environ.get(_tier_env("free"), str(_DEFAULT_MINUTES))
    raw = raw.strip().lower()
    if raw in ("unlimited", "0"):
        return None
    try:
        minutes = int(raw)
    except ValueError:
        minutes = _DEFAULT_MINUTES
    if minutes <= 0:
        return None
    return minutes * 60


def _supabase_creds() -> Optional[tuple[str, str]]:
    """Return (url, service_key) if Supabase is configured, else None."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if url and key:
        return url, key
    return None


class VoiceQuotaLedger:
    """Accumulates voice seconds per session and sums monthly usage.

    Prefers Supabase; on any failure (unconfigured or a request error) it uses a
    per-process in-memory ledger so enforcement never crashes the request path.
    """

    def __init__(self) -> None:
        # (user_id, session_id) -> {"seconds": int, "month_key": str}
        self._mem: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    # ── In-memory fallback ────────────────────────────────────────────────
    def _mem_record(self, user_id: str, session_id: str, delta: int, mk: str) -> None:
        with self._lock:
            key = (user_id, session_id)
            entry = self._mem.get(key)
            if entry is None:
                self._mem[key] = {"seconds": delta, "month_key": mk}
            else:
                entry["seconds"] += delta

    def _mem_used(self, user_id: str, mk: str) -> int:
        with self._lock:
            return sum(
                e["seconds"]
                for (uid, _sid), e in self._mem.items()
                if uid == user_id and e["month_key"] == mk
            )

    # ── Supabase-backed store ─────────────────────────────────────────────
    def _headers(self, key: str) -> dict:
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _sb_record(self, url: str, key: str, user_id: str, session_id: str,
                   delta: int, mk: str) -> None:
        """Read-modify-write the session's row, accumulating ``delta`` seconds."""
        headers = self._headers(key)
        now_iso = datetime.now(timezone.utc).isoformat()
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(
                f"{url}/rest/v1/voice_usage",
                params={
                    "user_id": f"eq.{user_id}",
                    "session_id": f"eq.{session_id}",
                    "select": "id,seconds",
                },
                headers=headers,
            )
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                row = rows[0]
                new_seconds = int(row.get("seconds") or 0) + delta
                patch = client.patch(
                    f"{url}/rest/v1/voice_usage",
                    params={"id": f"eq.{row['id']}"},
                    json={"seconds": new_seconds, "last_heartbeat_at": now_iso},
                    headers=headers,
                )
                patch.raise_for_status()
            else:
                insert = client.post(
                    f"{url}/rest/v1/voice_usage",
                    json={
                        "user_id": user_id,
                        "session_id": session_id,
                        "seconds": delta,
                        "month_key": mk,
                        "started_at": now_iso,
                        "last_heartbeat_at": now_iso,
                    },
                    headers=headers,
                )
                insert.raise_for_status()

    def _sb_used(self, url: str, key: str, user_id: str, mk: str) -> int:
        headers = self._headers(key)
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(
                f"{url}/rest/v1/voice_usage",
                params={
                    "user_id": f"eq.{user_id}",
                    "month_key": f"eq.{mk}",
                    "select": "seconds",
                },
                headers=headers,
            )
            resp.raise_for_status()
            return sum(int(r.get("seconds") or 0) for r in resp.json())

    # ── Public API ────────────────────────────────────────────────────────
    def record_heartbeat(self, user_id: str, session_id: str,
                          seconds_delta: int) -> None:
        """Book ``seconds_delta`` (clamped to ``MAX_HEARTBEAT_DELTA``) of voice.

        Never raises: on a Supabase error it records into the in-memory fallback
        and logs a warning, so metering degrades gracefully.
        """
        delta = max(0, min(int(seconds_delta), MAX_HEARTBEAT_DELTA))
        if delta == 0:
            return
        mk = month_key()
        creds = _supabase_creds()
        if creds is None:
            self._mem_record(user_id, session_id, delta, mk)
            return
        url, key = creds
        try:
            self._sb_record(url, key, user_id, session_id, delta, mk)
        except Exception:
            logger.warning(
                "voice heartbeat Supabase write failed; using in-memory fallback",
                exc_info=True,
            )
            self._mem_record(user_id, session_id, delta, mk)

    def get_quota(self, user_id: str, tier: str) -> dict:
        """Return the user's current monthly voice quota state.

        Keys: ``limit_seconds`` (``None`` if unlimited), ``used_seconds``,
        ``remaining_seconds``, ``month_key``, ``unlimited``. Never raises: on a
        Supabase error it reads the in-memory fallback and logs a warning.
        """
        mk = month_key()
        limit = tier_limit_seconds(tier)
        creds = _supabase_creds()
        if creds is None:
            used = self._mem_used(user_id, mk)
        else:
            url, key = creds
            try:
                used = self._sb_used(url, key, user_id, mk)
            except Exception:
                logger.warning(
                    "voice quota Supabase read failed; using in-memory fallback",
                    exc_info=True,
                )
                used = self._mem_used(user_id, mk)

        if limit is None:
            return {
                "limit_seconds": None,
                "used_seconds": used,
                "remaining_seconds": None,
                "month_key": mk,
                "unlimited": True,
            }
        remaining = max(0, limit - used)
        return {
            "limit_seconds": limit,
            "used_seconds": used,
            "remaining_seconds": remaining,
            "month_key": mk,
            "unlimited": False,
        }

    def check_exhausted(
        self, user_id: str, tier: str, quota: Optional[dict] = None
    ) -> bool:
        """Return whether the user is out of monthly voice minutes.

        This is the enforcement check the mint path runs. When it rejects for
        exhaustion it emits a ``quota_exhausted`` coach event (Phase 2, Task 3)
        so the block is visible in ``coach_events`` alongside the client-side
        ``mint_rejected``. Pass an already-fetched ``quota`` to avoid a second
        ledger read. Fail-open: an event-log failure never affects the return
        value or the request.
        """
        if quota is None:
            quota = self.get_quota(user_id, tier)
        exhausted = (
            not quota["unlimited"]
            and quota["remaining_seconds"] is not None
            and quota["remaining_seconds"] <= 0
        )
        if exhausted:
            try:
                from src.event_logger import log_event

                log_event(
                    "quota_exhausted",
                    severity="warn",
                    surface="voice",
                    user_id=user_id,
                    ok=False,
                    error_code="quota_exhausted",
                    payload={
                        "used_seconds": quota["used_seconds"],
                        "limit_seconds": quota["limit_seconds"],
                        "month_key": quota["month_key"],
                    },
                )
            except Exception:  # pragma: no cover - telemetry never breaks metering
                pass
        return exhausted


# Global instance shared by the server endpoints.
voice_quota_ledger = VoiceQuotaLedger()
