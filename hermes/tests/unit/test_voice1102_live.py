"""Voice 02.11, the three packages together: the live dialogue (student White, move 9) through POST
/api/coach/voice/check, each sentence with the coach's earlier ones as `previous`, written and said aloud.
word_move cuts the queen-to-d1 and d2-d3 proposals, castle_reason the f2 reason; the move facts name the reasons."""
import pytest
from fastapi.testclient import TestClient

from src.server import app

FEN = "r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq - 0 9"
MOVE, CASTLE = "cannot be played on the board now", "the castling reason is wrong: f2 is not on the king's path"
WRITTEN = [
    ("Может, попробуешь пойти ферзём на d1?", MOVE),
    ("Может попробуешь пойти пешкой на d2 на d3? Это позволит перекрыть дорогу слону на d3.", MOVE),
    ("Я не могу сделать рокировку, потому что поле f2 под боем слона.", CASTLE),
    ("Слон на c5 бьёт поле f2, и по правилам проходить через битое поле при рокировке нельзя.", CASTLE),
    ("Давай лучше пешкой на d3 пойдём, чтобы прогнать этого слона.", MOVE),
]
SAID = [
    ("Может, попробуешь пойти ферзём на дэ один?", MOVE),
    ("Может попробуешь пойти пешкой на дэ два на дэ три? Это позволит перекрыть дорогу слону на дэ три.", MOVE),
    ("Я не могу сделать рокировку, потому что поле эф два под боем слона.", CASTLE),
    ("Слон на цэ пять бьёт поле эф два, и по правилам проходить через битое поле при рокировке нельзя.", CASTLE),
    ("Давай лучше пешкой на дэ три пойдём, чтобы прогнать этого слона.", MOVE),
]


@pytest.mark.parametrize("dialogue", [WRITTEN, SAID], ids=["written", "said"])
def test_the_live_dialogue_is_cut_sentence_by_sentence(dialogue):
    client = TestClient(app)
    for i, (text, mark) in enumerate(dialogue):
        resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-1102-live"},
                           json={"text": text, "fen": FEN, "question": "что мне делать?",
                                 "previous": " ".join(t for t, _ in dialogue[:i]), "engine": False})
        assert resp.status_code == 200
        issues = resp.json()["issues"]
        assert any(mark in x for x in issues), (text, issues)


@pytest.mark.parametrize("text", [
    "Может, попробуешь пойти ферзём на цэ два?",
    "Короткая рокировка сейчас невозможна: слон d3 бьёт поле f1.",
    "Давай сыграем пешкой на аш три.",
])
def test_true_sentences_on_the_live_board_pass(text):
    client = TestClient(app)
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-1102-live"},
                       json={"text": text, "fen": FEN, "question": "что мне делать?", "engine": False})
    assert resp.status_code == 200
    assert not any(MOVE in x or "castling reason" in x for x in resp.json()["issues"]), resp.json()["issues"]


def test_the_rule_facts_name_what_the_model_merged():
    import chess

    from src.board_rules import rule_facts

    facts = " ".join(rule_facts(chess.Board(FEN), with_tablebase=False, explicit=True))
    assert "f1, which the black bishop on d3 attacks" in facts and "the pawn f2 does not matter" in facts
    assert "d2 (d3 is taken by the black bishop)" in facts and "Qe2" in facts
