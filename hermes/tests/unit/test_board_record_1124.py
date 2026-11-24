"""The model is given the record of the game on the student's board (prod 24.11: a .pgn file's game reached it as the
final position alone whenever the review step's scan did not fit in the turn's wait — «send me the moves»), and what
the answer tells of a finished game's moves is checked against that record («жертва ферзя на d8», tester 23.11)."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src import answer_check_db as acd
from src import board_record as br
from src import server
from src.answer_check import CheckContext, check_sentence
from src.server import UserProfile, app

OPERA = ('[White "Paul Morphy"]\n[Black "Duke Karl / Count Isouard"]\n[Result "1-0"]\n\n1.e4 e5 2.Nf3 d6 3.d4 Bg4 '
         '4.dxe5 Bxf3 5.Qxf3 dxe5 6.Bc4 Nf6 7.Qb3 Qe7 8.Nc3 c6 9.Bg5 b5 10.Nxb5 cxb5 11.Bxb5+ Nbd7 12.O-O-O Rd8 '
         '13.Rxd7 Rxd7 14.Rd1 Qe6 15.Bxd7+ Nxd7 16.Qb8+ Nxb8 17.Rd8# 1-0')
FINAL = "1n1Rkb1r/p4ppp/4q3/4p1B1/4P3/8/PPP2PPP/2K5 b k - 1 17"
LINE = "1.e4 e5 2.Nf3 Nc6 3.Bc4 *"


@pytest.mark.unit
def test_the_block_is_the_exact_record_and_the_move_shown():
    text = br.block(OPERA, 33)
    assert text.startswith(br.HEADER)
    assert "White Paul Morphy, Black Duke Karl / Count Isouard, result 1-0" in text
    assert "15.Bxd7+ Nxd7 16.Qb8+ Nxb8 17.Rd8#" in text
    assert "33 plies. The board shows the position after 17.Rd8# — the game's last move (ply 33 of 33)." in text
    assert "after 10...cxb5 (ply 20 of 33)" in br.block(OPERA, 20)
    assert "the start position" in br.block(OPERA, 0)
    assert br.block("not a game", 0) == "" and br.block("", None) == ""


@pytest.mark.unit
def test_a_line_from_a_position_starts_with_blacks_move_numbered():
    pgn = '[SetUp "1"]\n[FEN "6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1"]\n\n1...h6 2.Rd8+ Kh7 *'
    assert "1...h6 2.Rd8+ Kh7" in br.block(pgn)


@pytest.mark.unit
def test_a_finished_game_is_told_from_an_open_line():
    assert br.finished(OPERA) is True
    assert br.finished(LINE) is False
    assert br.finished("1.e4 e5 2.Nf3 Nc6 1/2-1/2") is True
    assert br.finished("") is False


def _turn(message, pgn, fen, fits=True):
    client = TestClient(app)
    user = {"X-User-Id": f"board-record-{fits}"}
    seen = {}
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile, \
            patch("src.server._board_review_fits", return_value=(fits, {})):
        mock_profile.return_value = UserProfile(user_id=user["X-User-Id"])
        agent = MagicMock()

        def _chat(text, stream_callback=None):
            seen["message"] = text
            if stream_callback:
                stream_callback("ok")
            return "ok"

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        client.post("/api/coach/chat", headers=user, json={"message": message, "fen": fen, "board_pgn": pgn, "locale": "en"})
    return seen["message"]


@pytest.mark.unit
def test_the_model_has_the_record_when_the_review_scan_does_not_fit():
    """Prod 24.11: the scan of a game that arrived with the question did not fit — the model saw the mate alone."""
    message = _turn("Review this game", OPERA, FINAL, fits=False)
    assert "Critical moments of the student's game" not in message
    assert br.HEADER in message and "16.Qb8+ Nxb8 17.Rd8#" in message
    assert "call find_critical_moments with this record as its PGN" in message


@pytest.mark.unit
def test_any_question_about_the_game_comes_with_its_record():
    message = _turn("Which sacrifice decided the game?", OPERA, FINAL)
    assert br.HEADER in message and "16.Qb8+ Nxb8" in message
    # …and the record is one of the board's blocks: forgotten once a tool puts another position up.
    assert any(b.startswith(br.HEADER) for b in server.turn_board_blocks_of(message))


@pytest.mark.unit
def test_a_finished_page_game_checks_the_sacrifice_told_of_it():
    ctx = CheckContext.from_fens([FINAL], [OPERA], question="Разбери")
    acd.note_page_game(ctx, OPERA)
    assert getattr(ctx, "loaded_game", None) is None  # not a master game: the database checks do not read it
    assert any("16.Qb8+" in i for i in check_sentence("Решающая жертва ферзя на d8 отвлекла коня чёрных.", ctx))
    assert acd.sacrifice_issues("Решающая жертва ферзя на b8 отвлекла коня.", ctx) == []
    acd.forget_board_game(ctx)
    assert acd.sacrifice_issues("Решающая жертва ферзя на d8.", ctx) == []


@pytest.mark.unit
def test_an_open_line_on_the_board_is_no_record_to_check_against():
    ctx = CheckContext.from_fens(["r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"], [LINE], question="")
    acd.note_page_game(ctx, LINE)
    assert acd.sacrifice_issues("Белые иногда жертвуют слона на f7.", ctx) == []
