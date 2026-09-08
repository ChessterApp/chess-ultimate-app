"""Session management for chess coaching.

Sessions track conversation messages and current board state, scoped by user ID
(Clerk user_id from request header). An in-memory dict is the hot cache; when a
:class:`SessionPersistence` backend is configured, writes are mirrored to
Supabase and cache misses lazy-load from it so conversations survive a Hermes
restart. With no backend configured everything runs pure in-memory as before.
"""

import time
import uuid
from typing import Optional

import chess
from pydantic import BaseModel, Field, PrivateAttr

from src.session_persistence import SessionPersistence


class SessionMessage(BaseModel):
    role: str
    content: str
    timestamp: float = Field(default_factory=time.time)
    source: str = "text"


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: float = Field(default_factory=time.time)
    messages: list[SessionMessage] = Field(default_factory=list)
    board_state: str = chess.STARTING_FEN

    # Optional write-through backend. Not part of the serialized model.
    _persistence: Optional[SessionPersistence] = PrivateAttr(default=None)

    def add_message(
        self,
        role: str,
        content: str,
        source: str = "text",
        extra: Optional[dict] = None,
        evt: Optional[dict] = None,
    ) -> None:
        """Append a message and mirror it to the persistence backend.

        ``extra`` optionally stamps the Phase-1 coach_messages enrichment columns
        (turn_id, model, prompt_version, latency/token counts); ``evt`` is the
        event context used to emit a persistence_failure if the write fails. Both
        are only passed by the instrumented text chat path — other callers are
        unchanged.
        """
        self.messages.append(
            SessionMessage(role=role, content=content, source=source)
        )
        if self._persistence is not None:
            self._persistence.persist_message(
                self.id, role, content, source, extra=extra, evt=evt
            )

    def set_board_state(self, fen: str) -> None:
        """Update the current board state (validates FEN)."""
        chess.Board(fen)  # raises ValueError if invalid
        self.board_state = fen
        if self._persistence is not None:
            self._persistence.update_board_state(self.id, fen)


class SessionStore:
    """Session store keyed by session ID, scoped by user.

    In-memory dict is the hot cache; an optional persistence backend mirrors
    writes and reconstructs sessions on cache miss.
    """

    def __init__(self, persistence: SessionPersistence = None):
        self._sessions: dict[str, Session] = {}
        self._persistence = (
            persistence if persistence is not None else SessionPersistence()
        )

    def create(self, user_id: str, session_id: str = None) -> Session:
        """Create a new session for a user."""
        session = Session(
            id=session_id or str(uuid.uuid4()),
            user_id=user_id,
        )
        session._persistence = self._persistence
        self._sessions[session.id] = session
        self._persistence.persist_session(session.id, user_id, session.board_state)
        return session

    def get(self, session_id: str, user_id: str = None) -> Optional[Session]:
        """Get a session by ID, optionally scoped to a user.

        On cache miss, lazy-loads the session + its messages from the
        persistence backend (survives restarts).
        """
        session = self._sessions.get(session_id)
        if session is None:
            session = self._load(session_id)
        if session is None:
            return None
        if user_id and session.user_id != user_id:
            return None
        return session

    def _load(self, session_id: str) -> Optional[Session]:
        """Reconstruct a session from the persistence backend, or None."""
        row = self._persistence.load_session(session_id)
        if row is None:
            return None
        session = Session(
            id=row["id"],
            user_id=row["user_id"],
            board_state=row.get("board_state") or chess.STARTING_FEN,
        )
        for m in self._persistence.load_messages(session_id):
            # Append directly to avoid re-persisting loaded messages.
            session.messages.append(
                SessionMessage(
                    role=m["role"],
                    content=m["content"],
                    source=m.get("source", "text") or "text",
                )
            )
        session._persistence = self._persistence
        self._sessions[session.id] = session
        return session

    def list(self, user_id: str) -> list[Session]:
        """List all sessions for a user (merges cache with backend)."""
        for row in self._persistence.load_user_sessions(user_id):
            if row["id"] not in self._sessions:
                self._load(row["id"])
        return [s for s in self._sessions.values() if s.user_id == user_id]

    def delete(self, session_id: str, user_id: str = None) -> bool:
        """Delete a session. Returns True if deleted, False if not found."""
        session = self.get(session_id, user_id)
        if session is None:
            return False
        del self._sessions[session.id]
        self._persistence.delete_session(session.id)
        return True


# Global session store instance
session_store = SessionStore()
