"""Unit tests for session management."""

import chess
import pytest

from src.sessions import Session, SessionStore


@pytest.mark.unit
class TestSessionStore:
    def setup_method(self):
        self.store = SessionStore()

    def test_create_session(self):
        session = self.store.create(user_id="user1")
        assert session.user_id == "user1"
        assert session.board_state == chess.STARTING_FEN
        assert session.messages == []

    def test_get_session(self):
        created = self.store.create(user_id="user1")
        fetched = self.store.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_session_scoped_by_user(self):
        session = self.store.create(user_id="user1")
        # Same user can access
        assert self.store.get(session.id, user_id="user1") is not None
        # Different user cannot access
        assert self.store.get(session.id, user_id="user2") is None

    def test_list_sessions_by_user(self):
        self.store.create(user_id="user1")
        self.store.create(user_id="user1")
        self.store.create(user_id="user2")

        user1_sessions = self.store.list("user1")
        assert len(user1_sessions) == 2
        user2_sessions = self.store.list("user2")
        assert len(user2_sessions) == 1

    def test_delete_session(self):
        session = self.store.create(user_id="user1")
        assert self.store.delete(session.id) is True
        assert self.store.get(session.id) is None
        # Double delete returns False
        assert self.store.delete(session.id) is False

    def test_delete_scoped_by_user(self):
        session = self.store.create(user_id="user1")
        # user2 cannot delete user1's session
        assert self.store.delete(session.id, user_id="user2") is False
        # user1 can delete
        assert self.store.delete(session.id, user_id="user1") is True


@pytest.mark.unit
class TestSession:
    def test_add_message(self):
        session = Session(user_id="user1")
        session.add_message("user", "What is e4?")
        session.add_message("assistant", "The King's Pawn opening.")
        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[1].content == "The King's Pawn opening."

    def test_set_board_state(self):
        session = Session(user_id="user1")
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        session.set_board_state(fen)
        assert session.board_state == fen

    def test_set_invalid_board_state(self):
        session = Session(user_id="user1")
        with pytest.raises(ValueError):
            session.set_board_state("not a fen")
