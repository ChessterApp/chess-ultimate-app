"""Unified coach event log — local-first dual sink.

Every instrumented moment in a coach turn (``turn_start``, ``turn_end``,
``tool_call``, ``llm_error``, ``stream_disconnect``, ...) is emitted through
:func:`log_event`. The logger is fail-open and off the hot path by design:

  1. **Spool (local, synchronous, first):** the event is appended as one JSON
     line to a daily-rotating file ``metrics/coach-events-YYYYMMDD.jsonl`` (same
     directory pattern as ``voice_metrics``). A plain append needs no lock, and
     if Supabase is down nothing is ever lost — the spool always has it.
  2. **Supabase (remote, background, best-effort):** the event is enqueued onto
     a bounded queue drained by a single daemon thread that POSTs to the
     ``coach_events`` REST table. If the queue is full we drop the OLDEST event
     and count the drop (logged at most once per minute). A Supabase outage is
     invisible to callers and to users.

Nothing here ever raises into the caller — a broken logger must never break a
chat turn. Follows the fail-open daemon-thread pattern of
``session_persistence.py`` / ``cost_monitor.py``.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("hermes.event_logger")

# Daily JSONL spool lives next to the voice-latency beacons.
METRICS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metrics"
)

# Truncation limits (keep the log cheap and Supabase rows bounded).
_STR_FIELD_MAX = 2000       # any single string value in payload
_PAYLOAD_BYTES_MAX = 8192   # total serialized payload

# Bounded background queue → Supabase.
_QUEUE_MAX = 1000
_HTTP_TIMEOUT = 10
_DROP_LOG_INTERVAL_S = 60  # log the dropped-event count at most this often


def new_turn_id() -> str:
    """Return a short (12 hex char) turn correlation id."""
    return uuid.uuid4().hex[:12]


def _truncate_payload(payload: Any) -> Any:
    """Bound a payload before persistence. Never raises.

    Individual string values longer than ``_STR_FIELD_MAX`` are cut and suffixed
    with ``…[truncated]``. If the whole payload still serializes larger than
    ``_PAYLOAD_BYTES_MAX`` it is replaced with a compact key-listing stub so a
    single oversized event can't bloat the log or the Supabase row.
    """
    if payload is None:
        return None
    try:
        if isinstance(payload, dict):
            trimmed: dict[str, Any] = {}
            for k, v in payload.items():
                if isinstance(v, str) and len(v) > _STR_FIELD_MAX:
                    trimmed[k] = v[:_STR_FIELD_MAX] + "…[truncated]"
                else:
                    trimmed[k] = v
        elif isinstance(payload, str) and len(payload) > _STR_FIELD_MAX:
            trimmed = payload[:_STR_FIELD_MAX] + "…[truncated]"
        else:
            trimmed = payload

        serialized = json.dumps(trimmed, ensure_ascii=False, default=repr)
        if len(serialized.encode("utf-8")) > _PAYLOAD_BYTES_MAX:
            keys = list(trimmed.keys()) if isinstance(trimmed, dict) else []
            return {"truncated": True, "keys": keys}
        return trimmed
    except Exception:  # pragma: no cover - defensive: never break the caller
        return {"truncated": True, "keys": []}


class _EventLogger:
    """Dual-sink event logger. All public entry points are exception-safe."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=_QUEUE_MAX)
        self._worker: Optional[threading.Thread] = None
        self._worker_lock = threading.Lock()
        self._dropped = 0
        self._last_drop_log = 0.0

    # ---------------------------------------------------------------- config

    @property
    def _url(self) -> str:
        return os.environ.get("SUPABASE_URL", "")

    @property
    def _key(self) -> str:
        return os.environ.get("SUPABASE_SERVICE_KEY", "")

    @property
    def _supabase_enabled(self) -> bool:
        return bool(self._url and self._key)

    # ------------------------------------------------------------- spool sink

    @staticmethod
    def _spool_path(now: Optional[datetime] = None) -> str:
        now = now or datetime.now(timezone.utc)
        os.makedirs(METRICS_DIR, exist_ok=True)
        return os.path.join(METRICS_DIR, f"coach-events-{now:%Y%m%d}.jsonl")

    def _write_spool(self, record: dict) -> None:
        path = self._spool_path()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=repr) + "\n")

    # --------------------------------------------------------- supabase sink

    def _ensure_worker(self) -> None:
        """Lazily start the single daemon drain thread (idempotent)."""
        if self._worker is not None and self._worker.is_alive():
            return
        with self._worker_lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._drain_loop, name="coach-events-drain", daemon=True
            )
            self._worker.start()

    def _enqueue(self, record: dict) -> None:
        """Best-effort enqueue; drop-oldest when full (bounded memory)."""
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            try:
                self._queue.get_nowait()  # drop oldest
            except queue.Empty:
                pass
            self._count_drop()
            try:
                self._queue.put_nowait(record)
            except queue.Full:
                self._count_drop()

    def _count_drop(self) -> None:
        self._dropped += 1
        now = time.monotonic()
        if now - self._last_drop_log >= _DROP_LOG_INTERVAL_S:
            logger.warning("coach_events queue overflow: dropped %d events", self._dropped)
            self._last_drop_log = now

    def _drain_loop(self) -> None:
        while True:
            record = self._queue.get()
            try:
                self._post_supabase(record)
            except Exception:
                logger.debug("coach_events Supabase write failed", exc_info=True)
            finally:
                self._queue.task_done()

    def _post_supabase(self, record: dict) -> None:
        if not self._supabase_enabled:
            return
        httpx.post(
            f"{self._url}/rest/v1/coach_events",
            json=record,
            headers={
                "apikey": self._key,
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            timeout=_HTTP_TIMEOUT,
        ).raise_for_status()

    # ------------------------------------------------------------- public API

    def log_event(
        self,
        event_type: str,
        *,
        severity: str = "info",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        surface: str,
        model: Optional[str] = None,
        tool_name: Optional[str] = None,
        duration_ms: Optional[int] = None,
        ok: Optional[bool] = None,
        error_code: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        """Record one coach event. Never raises, never blocks on network I/O.

        Spool is written first (local, durable); the Supabase write is enqueued
        for the background worker. A failure in either sink is swallowed.
        """
        try:
            record = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "severity": severity,
                "user_id": user_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "surface": surface,
                "model": model,
                "tool_name": tool_name,
                "duration_ms": duration_ms,
                "ok": ok,
                "error_code": error_code,
                "payload": _truncate_payload(payload),
            }
        except Exception:  # pragma: no cover - defensive
            return

        # (1) Local-first: always spool, even if Supabase is down.
        try:
            self._write_spool(record)
        except Exception:
            logger.debug("coach_events spool write failed", exc_info=True)

        # (2) Best-effort background Supabase write.
        try:
            if self._supabase_enabled:
                self._ensure_worker()
                self._enqueue(record)
        except Exception:
            logger.debug("coach_events enqueue failed", exc_info=True)


# Global instance + module-level convenience wrapper.
event_logger = _EventLogger()


def log_event(
    event_type: str,
    *,
    severity: str = "info",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    surface: str,
    model: Optional[str] = None,
    tool_name: Optional[str] = None,
    duration_ms: Optional[int] = None,
    ok: Optional[bool] = None,
    error_code: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    """Module-level shim to :meth:`_EventLogger.log_event`. Never raises."""
    event_logger.log_event(
        event_type,
        severity=severity,
        user_id=user_id,
        session_id=session_id,
        turn_id=turn_id,
        surface=surface,
        model=model,
        tool_name=tool_name,
        duration_ms=duration_ms,
        ok=ok,
        error_code=error_code,
        payload=payload,
    )
