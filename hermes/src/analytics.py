"""Usage analytics — tracks tool invocations, session duration, popular tools.

Stores analytics data in Supabase (analytics_events table) and provides
a GET /api/coach/analytics endpoint for admin dashboard.
"""

import logging
import os
import queue
import time
import threading
from collections import Counter, defaultdict, deque
from typing import Optional

import httpx

from src import supabase_http as _supabase_http


def _sb():
    """The pooled Supabase client (src/supabase_http.py), or this module's httpx."""
    return _supabase_http.client() or httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AnalyticsEvent(BaseModel):
    user_id: str
    event_type: str  # "tool_invocation", "session_start", "session_end", "chat"
    tool_name: Optional[str] = None
    session_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class AnalyticsTracker:
    """In-memory analytics tracker with Supabase persistence."""

    def __init__(self):
        self._events: deque = deque(maxlen=5000)  # in-memory summary only; the rows go to Supabase
        self._session_starts: dict[str, float] = {}
        self._lock = threading.Lock()
        self._queue: "queue.Queue[AnalyticsEvent] | None" = None
        self._writer: threading.Thread | None = None

    def track_tool_invocation(self, user_id: str, tool_name: str, session_id: str = "") -> None:
        """Record a tool invocation event."""
        event = AnalyticsEvent(
            user_id=user_id,
            event_type="tool_invocation",
            tool_name=tool_name,
            session_id=session_id,
        )
        with self._lock:
            self._events.append(event)
        self._persist(event)

    def track_session_start(self, user_id: str, session_id: str) -> None:
        """Record session start."""
        with self._lock:
            self._session_starts[session_id] = time.time()
        event = AnalyticsEvent(
            user_id=user_id,
            event_type="session_start",
            session_id=session_id,
        )
        with self._lock:
            self._events.append(event)
        self._persist(event)

    def track_session_end(self, user_id: str, session_id: str) -> None:
        """Record session end with duration."""
        with self._lock:
            start = self._session_starts.pop(session_id, None)
        duration = time.time() - start if start else 0
        event = AnalyticsEvent(
            user_id=user_id,
            event_type="session_end",
            session_id=session_id,
            metadata={"duration_seconds": round(duration, 2)},
        )
        with self._lock:
            self._events.append(event)
        self._persist(event)

    def track_chat(self, user_id: str, session_id: str = "") -> None:
        """Record a chat event."""
        event = AnalyticsEvent(
            user_id=user_id,
            event_type="chat",
            session_id=session_id,
        )
        with self._lock:
            self._events.append(event)
        self._persist(event)

    def get_analytics(self, user_id: Optional[str] = None) -> dict:
        """Get aggregated analytics, optionally filtered by user."""
        with self._lock:
            events = list(self._events)

        if user_id:
            events = [e for e in events if e.user_id == user_id]

        # Tool invocation counts
        tool_counts: Counter = Counter()
        for e in events:
            if e.event_type == "tool_invocation" and e.tool_name:
                tool_counts[e.tool_name] += 1

        # Session durations
        session_durations = [
            e.metadata.get("duration_seconds", 0)
            for e in events
            if e.event_type == "session_end"
        ]
        avg_duration = (
            round(sum(session_durations) / len(session_durations), 2)
            if session_durations
            else 0
        )

        # Event type breakdown
        type_counts: Counter = Counter()
        for e in events:
            type_counts[e.event_type] += 1

        # Unique users
        unique_users = len({e.user_id for e in events})

        return {
            "total_events": len(events),
            "unique_users": unique_users,
            "tool_invocations": dict(tool_counts.most_common(20)),
            "popular_tools": [t for t, _ in tool_counts.most_common(5)],
            "event_breakdown": dict(type_counts),
            "total_sessions": type_counts.get("session_start", 0),
            "avg_session_duration_seconds": avg_duration,
        }

    def _persist(self, event: AnalyticsEvent) -> None:
        """Queue the event for the writer thread (never blocks the caller).

        It used to POST to Supabase inline — on the event loop, for every chat
        turn, 150–500 ms from the production host, holding every other student's
        turn meanwhile (2026-09-30). One daemon thread now drains a queue; when
        the queue is full the event is dropped, not waited for.
        """
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return
        with self._lock:
            if self._writer is None:
                self._queue = queue.Queue(maxsize=1000)
                self._writer = threading.Thread(target=self._drain, name="analytics-writer", daemon=True)
                self._writer.start()
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.debug("analytics queue full; event dropped")

    def _drain(self) -> None:
        while True:
            event = self._queue.get()
            try:
                self._write(event)
            except Exception:  # noqa: BLE001 — never let the writer die
                logger.debug("analytics write failed", exc_info=True)
            finally:
                self._queue.task_done()

    def _write(self, event: AnalyticsEvent) -> None:
        """POST one event to Supabase."""
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return

        try:
            _sb().post(
                f"{url}/rest/v1/analytics_events",
                json={
                    "user_id": event.user_id,
                    "event_type": event.event_type,
                    "tool_name": event.tool_name,
                    "session_id": event.session_id,
                    "metadata": event.metadata,
                },
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                timeout=5,
            )
        except Exception:
            logger.exception("Failed to persist analytics event")


# Global instance
analytics_tracker = AnalyticsTracker()
