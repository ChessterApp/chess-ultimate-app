"""The turn carries the game on the page's study board (prod 24.11: the Opera Game from a .pgn file in a new session
reached the server as its final position only — the coach reviewed the mate and asked for the moves)."""

import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src.server import UserProfile, app
from src.sessions import Session, session_store

OPERA = ('[White "Paul Morphy"]\n[Black "Duke Karl / Count Isouard"]\n[Result "1-0"]\n\n1.e4 e5 2.Nf3 d6 3.d4 Bg4 '
         '4.dxe5 Bxf3 5.Qxf3 dxe5 6.Bc4 Nf6 7.Qb3 Qe7 8.Nc3 c6 9.Bg5 b5 10.Nxb5 cxb5 11.Bxb5+ Nbd7 12.O-O-O Rd8 '
         '13.Rxd7 Rxd7 14.Rd1 Qe6 15.Bxd7+ Nxd7 16.Qb8+ Nxb8 17.Rd8# 1-0')
FINAL = "1n1Rkb1r/p4ppp/4q3/4p1B1/4P3/8/PPP2PPP/2K5 b k - 1 17"


@pytest.mark.unit
def test_a_session_takes_the_pages_game_once():
    s = Session(id="s", user_id="u")
    assert s.take_page_game(OPERA) is True
    board = s.active_board()
    assert board.pgn == OPERA and board.fen.split()[0] == FINAL.split()[0]
    board.annotations = {"arrows": [{"from": "g5", "to": "d8"}]}
    # The same game again (another spelling of the moves): kept as it is, the arrows too.
    assert s.take_page_game(OPERA.replace("1.e4 e5", "1. e4 e5")) is False
    assert board.annotations["arrows"]


@pytest.mark.unit
def test_not_a_game_or_a_game_against_the_coach_is_left_alone():
    s = Session(id="s2", user_id="u")
    assert s.take_page_game("hello") is False
    game = s.add_board(kind="game", pgn="1.e4 e5")
    assert s.take_page_game(OPERA, board_id=game.id) is False and game.pgn == "1.e4 e5"


@pytest.mark.unit
def test_a_turn_in_a_new_session_sees_the_games_moves():
    client = TestClient(app)
    user = {"X-User-Id": "board-pgn-user"}
    seen = {}
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
        mock_profile.return_value = UserProfile(user_id=user["X-User-Id"])
        agent = MagicMock()

        def _chat(message, stream_callback=None):
            seen["message"] = message
            if stream_callback:
                stream_callback("Разберём партию.")
            return "Разберём партию."

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        resp = client.post("/api/coach/chat", headers=user, json={
            "message": "Разбери эту партию", "fen": FINAL, "board_pgn": OPERA, "locale": "ru"})
    frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    sid = next(f["session_id"] for f in frames if f.get("session_id"))
    board = session_store.get(sid).active_board()
    assert board.pgn == OPERA and board.ply == len(list(chess.pgn.read_game(__import__("io").StringIO(OPERA)).mainline_moves()))
    # The model is given the game's review, not a bare final position.
    assert "Moves in the game: 33" in seen["message"] and "Critical moments" in seen["message"]
