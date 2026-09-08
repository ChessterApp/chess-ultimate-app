"""Supabase-backed persistence for coach sessions.

Write-through layer for :class:`~src.sessions.SessionStore`: writes go to
Supabase in the background so message appends stay off the critical path, and
reads lazy-load a session + its messages on cache miss (this is what makes a
Hermes restart survivable).

Every Supabase interaction is wrapped so a failure — missing env vars, network
error, or missing tables — degrades to pure in-memory operation and can NEVER
propagate into a chat/voice turn. Follows the httpx REST pattern used in
``user_profile.py`` and ``platform_linking.py``.
"""

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 10


def _is_missing_column_error(exc: Exception) -> bool:
    """True when a PostgREST write failed because a column doesn't exist yet.

    PostgREST surfaces an unknown column as HTTP 400 with schema-cache code
    ``PGRST204`` (or Postgres ``42703`` / a "column ... does not exist" message).
    Used to decide whether to retry the insert without the enrichment fields.
    """
    resp = getattr(exc, "response", None)
    if resp is None:
        return False
    try:
        if resp.status_code not in (400, 404):
            return False
        body = resp.text.lower()
    except Exception:
        return False
    return (
        "pgrst204" in body
        or "42703" in body
        or ("column" in body and ("does not exist" in body or "not found" in body))
    )


class SessionPersistence:
    """Best-effort Supabase persistence for coach sessions.

    All public methods swallow every exception. Writes run in daemon threads;
    reads block (only on cache miss) but still degrade to ``None``/``[]``.
    """

    def __init__(self, url: str = None, key: str = None):
        self.url = url if url is not None else os.environ.get("SUPABASE_URL", "")
        self.key = key if key is not None else os.environ.get("SUPABASE_SERVICE_KEY", "")
        self._warned = False
        # Per-session ordering gate (fixes the first-turn FK race, Phase 2 Task 5):
        # the session-row insert sets its Event when done, and a message insert for
        # that session waits on it so ``coach_messages`` can never win the race
        # against the ``coach_sessions`` upsert it references.
        self._session_ready: dict[str, threading.Event] = {}
        self._ready_lock = threading.Lock()
        if not self.enabled:
            self._warn_once()

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def _warn_once(self) -> None:
        if not self._warned:
            logger.warning(
                "Supabase not configured (SUPABASE_URL / SUPABASE_SERVICE_KEY); "
                "coach sessions are in-memory only and will not survive restarts"
            )
            self._warned = True

    def _headers(self) -> dict:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _run_bg(fn, *args) -> None:
        """Run a write in a daemon thread, keeping latency off the hot path."""
        t = threading.Thread(target=fn, args=args, daemon=True)
        t.start()

    # -------------------------------------------------- per-session ordering gate

    def _register_session_pending(self, session_id: str) -> threading.Event:
        """Reserve (or reuse) the readiness Event for a session, synchronously.

        Called on the request thread inside ``persist_session`` BEFORE the write
        thread is spawned, so it is guaranteed to exist by the time the first
        ``persist_message`` for the same session runs (add_message follows
        create() on the same thread) — closing the register/read race.
        """
        with self._ready_lock:
            ev = self._session_ready.get(session_id)
            if ev is None:
                ev = threading.Event()
                self._session_ready[session_id] = ev
            return ev

    def _await_session_ready(self, session_id: str) -> None:
        """Block until the session row insert for *session_id* has finished.

        No-op when no session write is pending (e.g. the session was persisted in
        an earlier request and its Event already fired, or persistence is used
        for messages only). Bounded by ``TIMEOUT`` so a stuck session write can
        never wedge a message write forever.
        """
        with self._ready_lock:
            ev = self._session_ready.get(session_id)
        if ev is not None and not ev.is_set():
            ev.wait(timeout=TIMEOUT)

    # ------------------------------------------------------------------ writes

    def persist_session(self, session_id: str, user_id: str, board_state: str) -> None:
        if not self.enabled:
            return
        # Reserve the readiness gate on THIS thread so a racing message write
        # (spawned moments later) always finds it and waits.
        ev = self._register_session_pending(session_id)
        self._run_bg(self._persist_session, session_id, user_id, board_state, ev)

    def _persist_session(
        self, session_id: str, user_id: str, board_state: str,
        ready: Optional["threading.Event"] = None,
    ) -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            httpx.post(
                f"{self.url}/rest/v1/coach_sessions",
                json={
                    "id": session_id,
                    "user_id": user_id,
                    "board_state": board_state,
                    "created_at": now,
                    "updated_at": now,
                },
                headers=headers,
                timeout=TIMEOUT,
            ).raise_for_status()
        except Exception:
            logger.debug("Failed to persist coach session %s", session_id, exc_info=True)
        finally:
            # Release message writers whether the insert succeeded or failed — a
            # genuine failure surfaces as a persistence_failure on the message
            # write, not a hung thread.
            if ready is not None:
                ready.set()

    def persist_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source: str,
        extra: dict | None = None,
        evt: dict | None = None,
    ) -> None:
        """Write a coach_messages row (background, best-effort).

        ``extra`` carries the Phase-1 enrichment columns (turn_id, model,
        prompt_version, latency_ms, prompt/completion tokens). They are additive
        and may not exist yet in prod (pre-migration), so the write fails soft:
        on a column-missing error it retries WITHOUT the extra fields. ``evt`` is
        optional event context ({user_id, turn_id, surface, model}); when a write
        ultimately fails a ``persistence_failure`` event is emitted from it.
        """
        if not self.enabled:
            return
        self._run_bg(self._persist_message, session_id, role, content, source, extra, evt)

    def _persist_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source: str,
        extra: dict | None = None,
        evt: dict | None = None,
    ) -> None:
        # Ordering gate: never insert a message row before the session row it
        # references exists (fixes the first-turn FK race, Phase 2 Task 5).
        self._await_session_ready(session_id)

        base = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "source": source,
        }
        payload = {**base, **{k: v for k, v in (extra or {}).items() if v is not None}}
        try:
            httpx.post(
                f"{self.url}/rest/v1/coach_messages",
                json=payload,
                headers=self._headers(),
                timeout=TIMEOUT,
            ).raise_for_status()
            return
        except Exception as exc:
            # Fail-soft: the enrichment columns may not exist yet in prod. Retry
            # once with just the base row so pre-migration writes still land.
            if extra and _is_missing_column_error(exc):
                logger.warning(
                    "coach_messages enrichment columns missing; retrying base insert "
                    "for session %s", session_id
                )
                try:
                    httpx.post(
                        f"{self.url}/rest/v1/coach_messages",
                        json=base,
                        headers=self._headers(),
                        timeout=TIMEOUT,
                    ).raise_for_status()
                    return
                except Exception:
                    logger.debug(
                        "Failed to persist coach message (base retry) for session %s",
                        session_id, exc_info=True,
                    )
            else:
                logger.debug(
                    "Failed to persist coach message for session %s",
                    session_id, exc_info=True,
                )
        # Both attempts failed — surface it as a persistence_failure event.
        if evt is not None:
            try:
                from src.event_logger import log_event

                log_event(
                    "persistence_failure",
                    severity="error",
                    user_id=evt.get("user_id"),
                    session_id=session_id,
                    turn_id=evt.get("turn_id"),
                    surface=evt.get("surface", "text"),
                    model=evt.get("model"),
                    ok=False,
                    error_code="coach_messages_write",
                    payload={"role": role},
                )
            except Exception:
                pass

    def update_board_state(self, session_id: str, fen: str) -> None:
        if not self.enabled:
            return
        self._run_bg(self._update_board_state, session_id, fen)

    def _update_board_state(self, session_id: str, fen: str) -> None:
        try:
            httpx.patch(
                f"{self.url}/rest/v1/coach_sessions",
                params={"id": f"eq.{session_id}"},
                json={
                    "board_state": fen,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                headers=self._headers(),
                timeout=TIMEOUT,
            ).raise_for_status()
        except Exception:
            logger.debug(
                "Failed to update board_state for session %s", session_id, exc_info=True
            )

    def delete_session(self, session_id: str) -> None:
        if not self.enabled:
            return
        # Drop the ordering gate for this session (bounded memory).
        with self._ready_lock:
            self._session_ready.pop(session_id, None)
        self._run_bg(self._delete_session, session_id)

    def _delete_session(self, session_id: str) -> None:
        try:
            httpx.delete(
                f"{self.url}/rest/v1/coach_sessions",
                params={"id": f"eq.{session_id}"},
                headers=self._headers(),
                timeout=TIMEOUT,
            ).raise_for_status()
        except Exception:
            logger.debug("Failed to delete coach session %s", session_id, exc_info=True)

    # ------------------------------------------------------------------- reads

    def load_session(self, session_id: str) -> dict | None:
        """Fetch a single coach_sessions row. Returns None on miss/failure."""
        if not self.enabled:
            return None
        try:
            resp = httpx.get(
                f"{self.url}/rest/v1/coach_sessions",
                params={"id": f"eq.{session_id}", "select": "*"},
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            rows = resp.json()
            return rows[0] if rows else None
        except Exception:
            logger.debug("Failed to load coach session %s", session_id, exc_info=True)
            return None

    def load_user_sessions(self, user_id: str) -> list[dict]:
        """Fetch all coach_sessions rows for a user. Returns [] on failure."""
        if not self.enabled:
            return []
        try:
            resp = httpx.get(
                f"{self.url}/rest/v1/coach_sessions",
                params={"user_id": f"eq.{user_id}", "select": "*"},
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json() or []
        except Exception:
            logger.debug("Failed to load coach sessions for %s", user_id, exc_info=True)
            return []

    def load_messages(self, session_id: str) -> list[dict]:
        """Fetch coach_messages for a session, ordered oldest-first."""
        if not self.enabled:
            return []
        try:
            resp = httpx.get(
                f"{self.url}/rest/v1/coach_messages",
                params={
                    "session_id": f"eq.{session_id}",
                    "select": "*",
                    "order": "id.asc",
                },
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json() or []
        except Exception:
            logger.debug(
                "Failed to load coach messages for session %s", session_id, exc_info=True
            )
            return []
