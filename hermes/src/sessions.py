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

from src.boards import Board, board_from_row, new_board
from src.session_persistence import SessionPersistence


class SessionMessage(BaseModel):
    role: str
    content: str
    timestamp: float = Field(default_factory=time.time)
    source: str = "text"


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str = ""
    created_at: float = Field(default_factory=time.time)
    messages: list[SessionMessage] = Field(default_factory=list)
    # FEN of the active board — kept for every caller that reads it; boards
    # below are the source of truth and this mirrors the active one.
    board_state: str = chess.STARTING_FEN
    boards: list[Board] = Field(default_factory=list)
    active_board_id: Optional[str] = None

    # Optional write-through backend. Not part of the serialized model.
    _persistence: Optional[SessionPersistence] = PrivateAttr(default=None)
    # The student's position this turn when it must stay on the board (they ask
    # about it, or a game is on): tools then explain without replacing it — on
    # production (2026-10-06) get_topic/get_lesson put an example over the
    # student's puzzle and the coach solved the example. Not serialized.
    _board_lock: Optional[str] = PrivateAttr(default=None)
    # A strict lock (the question points at this board: «здесь», «эту задачу», «первый ход», a move,
    # a live game) keeps every position off the board; a plain one (the words only touch on a move
    # or a puzzle) keeps off the examples of get_topic/get_lesson, while a puzzle or a position the
    # coach puts up on purpose goes on — «Есть задачка на мат в два?» asks for one (2026-10-09).
    _board_lock_strict: bool = PrivateAttr(default=False)

    def lock_board(self, fen: Optional[str], strict: bool = False) -> None:
        self._board_lock = fen
        self._board_lock_strict = bool(fen) and strict

    @property
    def board_lock(self) -> Optional[str]:
        return self._board_lock

    @property
    def board_lock_strict(self) -> bool:
        return self._board_lock_strict

    # ── boards ──────────────────────────────────────────────────────
    def ensure_board(self) -> Board:
        """The active board, creating the default study board when the session has none."""
        board = self.active_board()
        if board is None:
            board = new_board(self.id, kind="study", fen=self.board_state)
            self.boards.append(board)
            self.active_board_id = board.id
            if self._persistence is not None:
                self._persistence.persist_board(board.to_public())
                self._persistence.update_session_fields(self.id, active_board_id=board.id)
        return board

    def get_board(self, board_id: Optional[str]) -> Optional[Board]:
        if not board_id:
            return None
        return next((b for b in self.boards if b.id == board_id), None)

    def active_board(self) -> Optional[Board]:
        board = self.get_board(self.active_board_id)
        if board is None and self.boards:
            board = self.boards[0]
            self.active_board_id = board.id
        return board

    def set_active_board(self, board_id: str) -> Board:
        board = self.get_board(board_id)
        if board is None:
            raise KeyError(board_id)
        self.active_board_id = board.id
        self.board_state = board.fen
        if self._persistence is not None:
            self._persistence.update_session_fields(
                self.id, active_board_id=board.id, board_state=board.fen
            )
        return board

    def add_board(self, activate: bool = True, **kwargs) -> Board:
        board = new_board(self.id, **kwargs)
        self.boards.append(board)
        if self._persistence is not None:
            self._persistence.persist_board(board.to_public())
        if activate or self.active_board_id is None:
            self.set_active_board(board.id)
        return board

    def save_board(self, board: Board) -> None:
        board.touch()
        if board.id == self.active_board_id:
            self.board_state = board.fen
            if self._persistence is not None:
                self._persistence.update_board_state(self.id, board.fen)
        if self._persistence is not None:
            self._persistence.persist_board(board.to_public())

    def remove_board(self, board_id: str) -> bool:
        board = self.get_board(board_id)
        if board is None:
            return False
        self.boards = [b for b in self.boards if b.id != board_id]
        if self._persistence is not None:
            self._persistence.delete_board(board_id)
        if self.active_board_id == board_id:
            self.active_board_id = None
            nxt = self.active_board() or self.ensure_board()
            self.set_active_board(nxt.id)
        return True

    def apply_board_actions(self, actions: list, board_id: Optional[str] = None) -> Optional[Board]:
        """Apply the coach's board_control actions to a board (default: active).

        Actions that name a ``board_id`` go to that board. Returns the board
        that changed last, or None when nothing changed.
        """
        changed = None
        for action in actions or []:
            if not isinstance(action, dict):
                continue
            target = self.get_board(action.get("board_id")) or self.get_board(board_id) or self.ensure_board()
            if target.apply_action(action):
                self.save_board(target)
                changed = target
        return changed

    def set_title(self, title: str) -> None:
        self.title = (title or "").strip()[:120]
        if self._persistence is not None:
            self._persistence.update_session_fields(self.id, title=self.title)

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

    def set_board_state(self, fen: str, board_id: Optional[str] = None) -> None:
        """Update the current position (validates FEN).

        Writes the FEN onto the target board (``board_id`` or the active one)
        as a manual position change, and mirrors it into ``board_state``.
        """
        chess.Board(fen)  # raises ValueError if invalid
        if board_id and self.get_board(board_id) and board_id != self.active_board_id:
            self.set_active_board(board_id)
        board = self.ensure_board()
        if board.fen != fen:
            # A position that continues the loaded game is a navigation, not a
            # new study position; anything else replaces the board's history.
            board.set_position(fen)
            self.save_board(board)  # writes board_state too when the board is active
        changed = self.board_state != fen
        self.board_state = fen
        if changed and self._persistence is not None and board.id != self.active_board_id:
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
            title=row.get("title") or "",
            board_state=row.get("board_state") or chess.STARTING_FEN,
            active_board_id=row.get("active_board_id"),
        )
        # Boards and messages depend on the session id only: two roundtrips at
        # once instead of one after the other (250–500 ms each from production).
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="session-load") as pool:
            boards_future = pool.submit(self._persistence.load_boards, session_id)
            messages_future = pool.submit(self._persistence.load_messages, session_id)
            board_rows = boards_future.result()
            message_rows = messages_future.result()
        for b in board_rows:
            try:
                session.boards.append(board_from_row(b))
            except Exception:  # a malformed row must not lose the session
                continue
        active = session.active_board()
        if active is not None:
            session.board_state = active.fen
        for m in message_rows:
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
        """List all sessions for a user (merges cache with backend).

        Sessions not in memory (after a restart) load side by side: a user
        with 13 sessions used to wait for 26 roundtrips one after the other.
        """
        missing = [row["id"] for row in self._persistence.load_user_sessions(user_id)
                   if row["id"] not in self._sessions]
        if missing:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=min(8, len(missing)), thread_name_prefix="session-list") as pool:
                list(pool.map(self._load, missing))
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


BOARD_KEPT_NOTE = (
    "The student's own position stays on the board this turn (they asked about it): nothing was put on the "
    "board. Do not describe the example or lesson position as the board, and do not solve it instead — answer "
    "about the student's position; name the lesson by its link if it helps. If the student was in fact asking "
    "for a new example, lesson or puzzle, offer to put it on the board: a short «да» from them will do it."
)


def _tool_session(kwargs: Optional[dict]):
    session_id = (kwargs or {}).get("session_id")
    if not session_id:
        return None
    try:
        return session_store.get(str(session_id))
    except Exception:  # noqa: BLE001
        return None


def board_lock_for(kwargs: Optional[dict]) -> Optional[str]:
    """The locked position of the coach session a tool runs in (kwargs ``session_id``), else None."""
    session = _tool_session(kwargs)
    return getattr(session, "board_lock", None) if session is not None else None


def board_lock_strict_for(kwargs: Optional[dict]) -> bool:
    """Whether no position at all may replace the board this turn (see Session._board_lock_strict)."""
    session = _tool_session(kwargs)
    return bool(getattr(session, "board_lock_strict", False)) if session is not None else False
