"""Openings asked about by name: slang names, the book line, its alternatives, the turn."""

from unittest.mock import MagicMock, patch

import json
import chess
import pytest
from fastapi.testclient import TestClient

from src.opening_knowledge import mentions_opening, plan_opening
from src.openings_book import TRAPS, _split_moves, get_book, named_opening
from src.server import app
from src.sessions import session_store
from src.tools.openings import get_opening_stats
from src.user_profile import UserProfile

FRIED_LIVER = "Italian Game: Two Knights Defense, Fried Liver Attack"
FRIED_LIVER_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7"
# The quiet Italian that stood on the board when the friend asked (2026-09-30).
PIANISSIMO = "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2PP1N2/PP3PPP/RNBQ1RK1 w - - 2 7"


@pytest.mark.unit
class TestNames:
    @pytest.mark.parametrize("text", [
        "а против жаренной печени", "Что такое жареная печень?", "в жареной печени конь ставит вилку",
        "What is the Fried Liver?", "атака Фегателло",
    ])
    def test_fried_liver_slang(self, text):
        assert named_opening(text) == FRIED_LIVER

    @pytest.mark.parametrize("text, name", [
        ("как защититься от детского мата", "Scholar's Mate"),
        ("мат Легаля", "Légal Trap"),
        ("контратака Траксля", "Italian Game: Two Knights Defense, Traxler Counterattack"),
        ("как играть против сицилианки", "Sicilian Defense"),
        ("планы в испанской партии", "Ruy Lopez"),
        ("лондонская система за белых", "Queen's Pawn Game: London System"),
        ("защита Алехина", "Alekhine Defense"),
        ("сицилиялық қорғаныс", "Sicilian Defense"),
    ])
    def test_named_lines_and_families(self, text, name):
        assert named_opening(text) == name

    @pytest.mark.parametrize("text", [
        "покажи партии Алехина", "ответь на английском языке", "позиция Филидора в ладейном эндшпиле",
        "Что мне изучать дальше?", "легальный ли это ход", "третий ход", "мой коллега играет",
    ])
    def test_not_an_opening(self, text):
        assert named_opening(text) is None
        assert not mentions_opening(text)


@pytest.mark.unit
class TestBook:
    def test_exact_name_ranks_first(self):
        # «Fried Liver» used to find the shorter Anti-Fried Liver Defense (3...h6) first.
        assert get_book().by_name("Fried Liver")[0][1] == FRIED_LIVER
        assert get_book().by_name("жареная печень")[0][1] == FRIED_LIVER

    def test_the_tool_understands_slang(self):
        found = get_opening_stats(opening_name="жареная печень")
        assert found["name"] == FRIED_LIVER and found["main_line"] == FRIED_LIVER_PGN

    @pytest.mark.parametrize("eco, name, pgn", TRAPS)
    def test_traps_are_legal(self, eco, name, pgn):
        board = chess.Board()
        for san in _split_moves(pgn):
            board.push_san(san)
        if "," not in name:  # the trap itself ends in mate; its defences do not
            assert board.is_checkmate()

    def test_branches_are_the_defences(self):
        book = get_book()
        items = book.branches(FRIED_LIVER, FRIED_LIVER_PGN)
        moves = {(i["ply"], i["move"]) for i in items}
        assert (8, "Bc5") not in moves  # ply 8 is White's 5th move
        assert (7, "Bc5") in moves      # 4...Bc5, the Traxler
        assert (9, "Na5") in moves      # 5...Na5, the Polerio Defense
        assert (11, "Kxf7") in moves    # the line goes on: 6...Kxf7 7.Qf3+
        assert all(i["name"].startswith("Italian Game: Two Knights Defense") for i in items)


@pytest.mark.unit
class TestPlan:
    def test_loads_the_line_and_states_the_fork(self):
        plan = plan_opening("Как играть чёрными против жареной печени?", chess.STARTING_FEN)
        assert plan.name == FRIED_LIVER and plan.load and plan.pgn == FRIED_LIVER_PGN
        assert "knight f7" in plan.block and "queen d8" in plan.block and "rook h8" in plan.block
        assert "5...Na5" in plan.block and "4...Bc5" in plan.block
        assert "жареная печень" in plan.block

    def test_board_already_in_the_opening(self):
        final = chess.Board()
        for san in _split_moves(FRIED_LIVER_PGN):
            final.push_san(san)
        assert not plan_opening("а в жареной печени?", final.fen()).load
        # A game on the board that follows the line (the student steps through it).
        assert not plan_opening("жареная печень", chess.STARTING_FEN, FRIED_LIVER_PGN + " Kxf7").load
        # The quiet Italian on the board is an Italian, not the Fried Liver.
        assert not plan_opening("как играть против итальянской партии", PIANISSIMO).load
        assert plan_opening("а против жаренной печени", PIANISSIMO).load

    def test_game_search_is_left_to_the_tools(self):
        assert plan_opening("Найди партии Карлсена в сицилианской защите") is None


@pytest.mark.unit
class TestTurn:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.config.COACH_ENGINE_NOTE", False)
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_the_line_goes_on_the_board_and_into_the_turn(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id="opening-user")
        agent = MagicMock()
        seen = {}

        def _chat(message, stream_callback=None):
            seen["message"] = message
            if stream_callback:
                stream_callback("Жареная печень — это 6.Nxf7.")
            return "Жареная печень — это 6.Nxf7."

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        user = {"X-User-Id": "opening-user"}
        sid = self.client.post("/api/coach/sessions", headers=user).json()["id"]

        resp = self.client.post("/api/coach/chat", headers=user, json={
            "message": "как играть против жаренной печени", "session_id": sid, "fen": PIANISSIMO,
        })
        assert resp.status_code == 200
        frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
        first_board = next(f for f in frames if "board_actions" in f)["board_actions"][0]
        assert first_board["type"] == "load_pgn" and first_board["pgn"] == FRIED_LIVER_PGN
        assert FRIED_LIVER in seen["message"] and "5...Na5" in seen["message"]

        session = session_store.get(sid, "opening-user")
        assert session.board_state.startswith("r1bqkb1r/ppp2Npp/2n5/3np3/2B5")
