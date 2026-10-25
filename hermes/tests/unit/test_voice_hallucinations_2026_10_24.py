"""2026-10-24, Alexander's phone, a game by voice: «конь на d4 напал на коня на f3 и ещё на пешку на e2. И на слона
на цэ четыре тоже нападает» — no pawn on e2, no black piece attacks c4, and arrows d4→c4 on the board.

* a piece named as attacked must be attacked by something (src/answer_check._unattacked_object_issues) — whoever the
  subject is, even none; «напал», «угрозу пешке» and squares in words («цэ четыре») are read;
* arrows a piece cannot draw are dropped on the voice path too (src/tool_bridge._prune_voice_arrows) and the model
  is told."""

import json

import chess
import pytest
from fastapi.testclient import TestClient

from src.answer_check import CheckContext, check_sentence
from src.game_intent import spoken_squares
from src.server import app, session_store

# Bc4 and Nf3 are White's, the black knight on d4; e2 is empty (the pawn stands on e4).
FEN = "r1bqkb1r/pppp1ppp/5n2/4p3/2BnP3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 0 6"


def _ctx():
    return CheckContext.from_fens([FEN], question="Он напал на одного моего коня?")


@pytest.mark.parametrize("sentence,wrong", [
    ("Да, ты прав, конь на d4 напал на коня на f3 и ещё на пешку на e2.", "no pawn on e2"),
    ("И на слона на цэ четыре тоже нападает.", "bishop on c4 is not attacked"),
    ("Я хотел сказать, что он напал на твоего слона на цэ четыре, на коня на эф три и создал угрозу пешке на е два.",
     "bishop on c4 is not attacked"),
    ("The knight attacks your bishop on c4.", "bishop on c4 is not attacked"),
    ("Конь создал угрозу пешке на e2.", "no pawn on e2"),
])
def test_the_phone_sentences_are_caught(sentence, wrong):
    issues = check_sentence(spoken_squares(sentence), _ctx())
    assert issues and any(wrong in i for i in issues), issues


@pytest.mark.parametrize("sentence", [
    "Конь на d4 напал на коня на f3.",                      # true: the f3 knight is attacked
    "Он нападает на пешку на c2.",                           # the c2 pawn is attacked by the d4 knight
    "Слон на c4 ничем не атакован.",
    "После Nb5 конь нападёт на пешку c7.",                   # a line, not the board as it is
    "Конь на d4 не нападает на слона c4.",
])
def test_true_and_hypothetical_sentences_pass(sentence):
    assert check_sentence(spoken_squares(sentence), _ctx()) == []


def test_the_voice_check_reads_squares_in_words():
    client = TestClient(app)
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-check-user"},
                       json={"text": "И на слона на цэ четыре тоже нападает.", "fen": FEN, "question": "а он напал?"})
    assert resp.status_code == 200
    issues = resp.json()["issues"]
    assert issues and "bishop on c4 is not attacked" in issues[0]


def test_voice_arrows_a_piece_cannot_draw_are_dropped_and_the_model_is_told():
    client = TestClient(app)
    user = {"X-User-Id": "voice-arrows-user"}
    sid = client.post("/api/coach/sessions", headers=user).json()["id"]
    session = session_store.get(sid, "voice-arrows-user")
    board = session.ensure_board()
    session.apply_board_actions([{"type": "set_fen", "fen": FEN}], board_id=board.id)
    resp = client.post("/api/coach/tool/board_control", headers=user, json={
        "args": {"action_type": "draw_arrows", "arrows": [
            {"from": "d4", "to": "c4", "brush": "red"},   # a knight cannot
            {"from": "d4", "to": "f3", "brush": "red"},   # a knight can
            {"from": "d4", "to": "e2", "brush": "red"},   # a knight can (the square is empty — an arrow, not a claim)
        ]}, "session_id": sid})
    assert resp.status_code == 200
    out = resp.json()
    arrows = [(a["from"], a["to"]) for act in out["board_actions"] if act.get("type") == "draw_arrows" for a in act["arrows"]]
    assert arrows == [("d4", "f3"), ("d4", "e2")]
    assert out["result"]["arrows_dropped"] == ["d4c4: a knight cannot go there"]
    assert "NOT drawn" in out["result"]["arrows_note"]
    assert chess.Board(FEN).piece_at(chess.D4).piece_type == chess.KNIGHT
