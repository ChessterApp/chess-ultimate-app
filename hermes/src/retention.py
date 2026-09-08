"""Retention purge — keeps the coach telemetry tables and local spool bounded.

Phase 3, Task 2. Three jobs, run daily as a background asyncio task:

  1. **coach_events**    — delete rows older than ``COACH_EVENTS_RETENTION_DAYS``
     (default 90).
  2. **analytics_events** — delete rows older than 180 days.
  3. **spool JSONL**     — delete local ``coach-events-*.jsonl`` /
     ``voice-latency-*.jsonl`` beacon files older than 14 days.

Explicitly NOT touched: ``coach_messages``, ``token_usage``, ``voice_usage`` —
those are kept indefinitely (product + billing history).

Deletes are batched (``_BATCH`` ids per round) so a purge never takes a long
table lock. Everything is fail-open: a Supabase / filesystem error is logged and
swallowed, and the loop is guarded by the ``RETENTION_ENABLED`` kill-switch.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from src.event_logger import METRICS_DIR, log_event

logger = logging.getLogger("hermes.retention")

_HTTP_TIMEOUT = 15
_BATCH = 1000                    # ids deleted per round — bounds lock duration.
_MAX_BATCHES = 10_000           # safety stop (10M rows) so a bug can't spin forever.

ANALYTICS_RETENTION_DAYS = 180  # fixed by spec.
SPOOL_RETENTION_DAYS = 14       # local JSONL beacons.

_FIRST_RUN_DELAY_S = 600        # first purge 10 min after boot.
_INTERVAL_S = 86_400            # then once per 24h.


# ── config ─────────────────────────────────────────────────────────────


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def coach_events_retention_days() -> int:
    try:
        return max(1, int(os.environ.get("COACH_EVENTS_RETENTION_DAYS", "90")))
    except (TypeError, ValueError):
        return 90


def retention_enabled() -> bool:
    return _env_flag("RETENTION_ENABLED", True)


def _supabase() -> tuple[str, str]:
    return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", "")


# ── Supabase batched delete ────────────────────────────────────────────


def _purge_table(table: str, cutoff: datetime, *, id_col: str = "id") -> int:
    """Batch-delete ``table`` rows with ``created_at < cutoff``. Returns count.

    Each round selects up to ``_BATCH`` ids older than the cutoff and deletes
    exactly those ids, so no single statement scans or locks the whole table.
    Fail-open: returns the count deleted so far on any error.
    """
    url, key = _supabase()
    if not url or not key:
        return 0

    cutoff_iso = cutoff.astimezone(timezone.utc).isoformat()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    deleted = 0
    try:
        for _ in range(_MAX_BATCHES):
            resp = httpx.get(
                f"{url}/rest/v1/{table}",
                params={
                    "select": id_col,
                    "created_at": f"lt.{cutoff_iso}",
                    "order": f"{id_col}.asc",
                    "limit": str(_BATCH),
                },
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            rows = resp.json()
            if not isinstance(rows, list) or not rows:
                break
            ids = [r.get(id_col) for r in rows if r.get(id_col) is not None]
            if not ids:
                break
            id_list = ",".join(str(i) for i in ids)
            del_resp = httpx.delete(
                f"{url}/rest/v1/{table}",
                params={id_col: f"in.({id_list})"},
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
            del_resp.raise_for_status()
            deleted += len(ids)
            if len(rows) < _BATCH:
                break
    except Exception:
        logger.warning("retention purge of %s failed after %d rows", table, deleted, exc_info=True)
    return deleted


# ── Local spool rotation ───────────────────────────────────────────────


def _purge_spool(cutoff_epoch: float) -> int:
    """Delete local coach-events / voice-latency JSONL files older than cutoff."""
    deleted = 0
    try:
        if not os.path.isdir(METRICS_DIR):
            return 0
        for name in os.listdir(METRICS_DIR):
            if not name.endswith(".jsonl"):
                continue
            if not (name.startswith("coach-events-") or name.startswith("voice-latency-")):
                continue
            path = os.path.join(METRICS_DIR, name)
            try:
                if os.path.getmtime(path) < cutoff_epoch:
                    os.remove(path)
                    deleted += 1
            except OSError:
                logger.debug("retention: could not stat/remove %s", path, exc_info=True)
    except Exception:
        logger.warning("retention spool rotation failed", exc_info=True)
    return deleted


# ── Orchestration ──────────────────────────────────────────────────────


def run_purge(now: Optional[datetime] = None) -> dict:
    """Run all three purge jobs once, log a summary event, return the counts."""
    now = now or datetime.now(timezone.utc)
    events_cutoff = now - timedelta(days=coach_events_retention_days())
    analytics_cutoff = now - timedelta(days=ANALYTICS_RETENTION_DAYS)
    spool_cutoff_epoch = time.time() - SPOOL_RETENTION_DAYS * 86_400

    summary = {
        "coach_events": _purge_table("coach_events", events_cutoff),
        "analytics_events": _purge_table("analytics_events", analytics_cutoff),
        "spool_files": _purge_spool(spool_cutoff_epoch),
    }

    logger.info(
        "retention purge complete: coach_events=%d analytics_events=%d spool_files=%d",
        summary["coach_events"],
        summary["analytics_events"],
        summary["spool_files"],
    )
    # Best-effort audit trail through the same event log.
    log_event(
        "retention_purge",
        surface="system",
        severity="info",
        payload=summary,
    )
    return summary


async def retention_loop() -> None:
    """Daily background purge. First run 10 min after boot, then every 24h.

    Honors the ``RETENTION_ENABLED`` kill-switch (checked each cycle) and runs
    the blocking purge off the event loop via ``asyncio.to_thread``. Cancellation
    (on shutdown) is propagated cleanly.
    """
    try:
        await asyncio.sleep(_FIRST_RUN_DELAY_S)
        while True:
            if retention_enabled():
                try:
                    await asyncio.to_thread(run_purge)
                except Exception:  # pragma: no cover - defensive: never kill the loop
                    logger.warning("retention purge raised", exc_info=True)
            else:
                logger.info("retention purge skipped (RETENTION_ENABLED=false)")
            await asyncio.sleep(_INTERVAL_S)
    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        logger.info("retention loop cancelled")
        raise
