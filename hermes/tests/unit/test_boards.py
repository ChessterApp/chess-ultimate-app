"""Boards as session entities: model, coach actions, API, restart survival."""

from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src.boards import Board, new_board
from src.server import app
from src.sessions import Session, SessionStore, session_store
from src.user_profile import UserProfile

USER = {"X-User-Id": "boards-user"}
PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"


@pytest.mark.unit
class TestBoardModel:
    def test_load_pgn_navigate_and_flip(self):
        b = new_board("s1", pgn=PGN)
        assert b.ply == 6 and "1B2p3" in b.fen
        b.navigate("first")
        assert b.ply == 0 and b.fen == chess.STARTING_FEN
        b.navigate("next"); b.navigate("next")
        assert b.ply == 2 and chess.Board(b.fen).turn == chess.WHITE
        b.navigate("prev"); b.navigate("last")
        assert b.ply == 6
        assert b.apply_action({"type": "flip_board"}) and b.orientation == "black"

    def test_actions_update_the_record(self):
        b = new_board("s1")
        assert b.apply_action({"type": "load_pgn", "pgn": PGN}) and b.ply == 6
        assert b.apply_action({"type": "draw_arrows", "arrows": [{"from": "e2", "to": "e4", "brush": "green"}]})
        assert b.annotations["arrows"][0]["to"] == "e4"
        assert b.apply_action({"type": "set_puzzle", "fen": chess.STARTING_FEN, "solution": ["e4"], "puzzle_id": "p1"})
        assert b.kind == "puzzle" and b.puzzle["puzzle_id"] == "p1" and b.annotations == {}
        assert b.apply_action({"type": "set_fen", "fen": chess.STARTING_FEN})
        assert b.kind == "study" and b.puzzle is None
        assert not b.apply_action({"type": "load_pgn", "pgn": "1. zz"})
        assert not b.apply_action({"type": "unknown"})

    def test_new_board_validation(self):
        with pytest.raises(ValueError):
            new_board("s1", kind="wat")
        with pytest.raises(ValueError):
            new_board("s1", orientation="sideways")


@pytest.mark.unit
class TestSessionBoards:
    def test_default_board_and_active_switching(self):
        s = Session(user_id="u")
        first = s.ensure_board()
        assert s.active_board_id == first.id and first.kind == "study"
        second = s.add_board(kind="master_game", title="Carlsen–Caruana", pgn=PGN, source={"twic_game_id": 1})
        assert s.active_board_id == second.id and s.board_state == second.fen
        s.set_active_board(first.id)
        assert s.board_state == chess.STARTING_FEN
        assert s.remove_board(second.id) and s.get_board(second.id) is None
        # Removing the last board recreates a default one.
        assert s.remove_board(first.id) and len(s.boards) == 1 and s.active_board_id

    def test_apply_actions_targets_named_or_active_board(self):
        s = Session(user_id="u")
        a = s.ensure_board()
        b = s.add_board(kind="study", title="second", activate=False)
        changed = s.apply_board_actions([{"type": "load_pgn", "pgn": PGN, "board_id": b.id}])
        assert changed is b and b.ply == 6 and a.pgn == ""
        s.apply_board_actions([{"type": "flip_board"}])
        assert a.orientation == "black"  # active board (a) took the unaddressed action

    def test_set_board_state_navigates_inside_loaded_game(self):
        s = Session(user_id="u")
        b = s.ensure_board()
        b.load_pgn(PGN)
        after_e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        s.set_board_state(after_e4)
        assert b.ply == 1 and b.pgn == PGN  # a position inside the game keeps the history
        s.set_board_state("8/8/8/4k3/8/8/8/4K2R w - - 0 1")
        assert b.pgn == "" and b.ply == 0  # an unrelated position replaces it


class _Persist:
    """Minimal in-memory persistence with the board methods."""

    def __init__(self):
        self.sessions, self.boards, self.messages = {}, {}, {}
        self.enabled = True

    def persist_session(self, sid, uid, fen):
        self.sessions[sid] = {"id": sid, "user_id": uid, "board_state": fen}

    def persist_message(self, sid, role, content, source, extra=None, evt=None):
        self.messages.setdefault(sid, []).append({"role": role, "content": content, "source": source})

    def update_board_state(self, sid, fen):
        self.sessions[sid]["board_state"] = fen

    def update_session_fields(self, sid, **f):
        self.sessions[sid].update(f)

    def persist_board(self, board):
        self.boards[board["id"]] = dict(board)

    def delete_board(self, bid):
        self.boards.pop(bid, None)

    def delete_session(self, sid):
        self.sessions.pop(sid, None)

    def load_session(self, sid):
        return self.sessions.get(sid)

    def load_user_sessions(self, uid):
        return [r for r in self.sessions.values() if r["user_id"] == uid]

    def load_messages(self, sid):
        return self.messages.get(sid, [])

    def load_boards(self, sid):
        return [b for b in self.boards.values() if b["session_id"] == sid]


@pytest.mark.unit
def test_boards_survive_a_restart():
    backend = _Persist()
    store = SessionStore(persistence=backend)
    s = store.create(user_id="u1")
    s.set_title("Разбор партии")
    game = s.add_board(kind="master_game", pgn=PGN, title="Carlsen–Caruana")
    game.navigate("prev")
    s.save_board(game)
    s.apply_board_actions([{"type": "draw_arrows", "arrows": [{"from": "b5", "to": "c6", "brush": "red"}]}])

    fresh = SessionStore(persistence=backend)  # simulated restart
    loaded = fresh.get(s.id, "u1")
    assert loaded.title == "Разбор партии"
    assert {b.id for b in loaded.boards} == {b.id for b in s.boards}
    active = loaded.active_board()
    assert active.id == game.id and active.ply == 5 and active.pgn == PGN
    assert active.annotations["arrows"][0]["to"] == "c6"
    assert loaded.board_state == active.fen


@pytest.mark.unit
class TestBoardRoutes:
    def setup_method(self):
        self.client = TestClient(app)

    def test_board_crud_and_session_title(self):
        created = self.client.post("/api/coach/sessions", headers=USER, json={"title": "Урок 1"}).json()
        sid = created["id"]
        assert created["title"] == "Урок 1" and created["board_count"] == 1

        boards = self.client.get(f"/api/coach/sessions/{sid}/boards", headers=USER).json()
        default_id = boards["active_board_id"]
        assert len(boards["boards"]) == 1

        r = self.client.post(f"/api/coach/sessions/{sid}/boards", headers=USER,
                             json={"kind": "master_game", "pgn": PGN, "title": "Ruy", "source": {"twic_game_id": 7}})
        assert r.status_code == 200
        bid = r.json()["id"]
        assert r.json()["ply"] == 6

        r = self.client.patch(f"/api/coach/sessions/{sid}/boards/{bid}", headers=USER,
                              json={"ply": 2, "orientation": "black", "title": "Ruy Lopez"})
        assert r.json()["ply"] == 2 and r.json()["orientation"] == "black"

        r = self.client.patch(f"/api/coach/sessions/{sid}", headers=USER, json={"active_board_id": default_id, "title": "Урок 1а"})
        assert r.json()["active_board_id"] == default_id and r.json()["title"] == "Урок 1а"

        assert self.client.patch(f"/api/coach/sessions/{sid}/boards/{bid}", headers=USER,
                                 json={"orientation": "up"}).status_code == 400
        assert self.client.post(f"/api/coach/sessions/{sid}/boards", headers=USER,
                                json={"kind": "nope"}).status_code == 400

        r = self.client.delete(f"/api/coach/sessions/{sid}/boards/{bid}", headers=USER)
        assert r.json()["deleted"] == bid
        assert self.client.delete(f"/api/coach/sessions/{sid}/boards/{bid}", headers=USER).status_code == 404

        listed = self.client.get("/api/coach/sessions", headers=USER).json()
        assert any(x["id"] == sid and x["title"] == "Урок 1а" for x in listed)
        assert self.client.delete(f"/api/coach/sessions/{sid}", headers=USER).json()["deleted"] == sid
        assert self.client.get(f"/api/coach/sessions/{sid}/boards", headers=USER).status_code == 404

    def test_other_users_cannot_touch_my_boards(self):
        sid = self.client.post("/api/coach/sessions", headers=USER).json()["id"]
        other = {"X-User-Id": "someone-else"}
        assert self.client.get(f"/api/coach/sessions/{sid}/boards", headers=other).status_code == 404
        assert self.client.delete(f"/api/coach/sessions/{sid}", headers=other).status_code == 404

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_chat_applies_coach_actions_to_the_board(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="boards-user")
        agent = MagicMock()
        agent.chat.return_value = "Look at the Ruy Lopez."
        mock_agent.return_value = agent

        sid = self.client.post("/api/coach/sessions", headers=USER).json()["id"]
        bid = self.client.get(f"/api/coach/sessions/{sid}/boards", headers=USER).json()["active_board_id"]

        with patch("src.server.wrap_response", return_value={
            "message": "Look at the Ruy Lopez.",
            "board_actions": [{"type": "load_pgn", "pgn": PGN}, {"type": "flip_board"}],
            "game_results": [],
        }):
            resp = self.client.post("/api/coach/chat", headers=USER,
                                    json={"message": "покажи испанку", "session_id": sid, "board_id": bid})
        assert resp.status_code == 200
        body = resp.text
        assert f'"board_id": "{bid}"' in body and '"active_board_id"' in body

        board = self.client.get(f"/api/coach/sessions/{sid}/boards", headers=USER).json()["boards"][0]
        assert board["pgn"] == PGN and board["ply"] == 6 and board["orientation"] == "black"
        session = session_store.get(sid, "boards-user")
        assert session.board_state == board["fen"]
