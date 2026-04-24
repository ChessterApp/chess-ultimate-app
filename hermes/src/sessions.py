"""In-memory session management for chess coaching.

Each session tracks conversation messages and current board state,
scoped by user ID (Clerk user_id from request header).
"""

import time
import uuid
from typing import Optional

import chess
from pydantic import BaseModel, Field


class SessionMessage(BaseModel):
    role: str
    content: str
    timestamp: float = Field(default_factory=time.time)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: float = Field(default_factory=time.time)
    messages: list[SessionMessage] = Field(default_factory=list)
    board_state: str = chess.STARTING_FEN

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(SessionMessage(role=role, content=content))

    def set_board_state(self, fen: str) -> None:
        """Update the current board state (validates FEN)."""
        chess.Board(fen)  # raises ValueError if invalid
        self.board_state = fen


class SessionStore:
    """In-memory session store keyed by session ID, scoped by user."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, user_id: str, session_id: str = None) -> Session:
        """Create a new session for a user."""
        session = Session(
            id=session_id or str(uuid.uuid4()),
            user_id=user_id,
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str, user_id: str = None) -> Optional[Session]:
        """Get a session by ID, optionally scoped to a user."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if user_id and session.user_id != user_id:
            return None
        return session

    def list(self, user_id: str) -> list[Session]:
        """List all sessions for a user."""
        return [s for s in self._sessions.values() if s.user_id == user_id]

    def delete(self, session_id: str, user_id: str = None) -> bool:
        """Delete a session. Returns True if deleted, False if not found."""
        session = self.get(session_id, user_id)
        if session is None:
            return False
        del self._sessions[session.id]
        return True


# Global session store instance
session_store = SessionStore()
