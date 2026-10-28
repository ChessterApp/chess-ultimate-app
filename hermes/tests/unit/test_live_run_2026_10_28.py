"""2026-10-28, the first live Gemini Live run on prod (from Almaty):
* the engine played c6 (a pawn) and the coach said «мой конь на c6» — from the bare SAN it guessed the piece; the
  reply now comes with the piece and squares in words;
* the model played «конь f3» with its own make_game_move, then the site's intent read the same words on the NEW
  position, found no legal Nf3 and told the coach «NOTHING was played» — the just-played move now reads as itself."""

import json

import chess
import pytest
from fastapi.testclient import TestClient

from src import game_mode
from src.intent import read_intent
from src.server import app
from src.sessions import session_store
from src.tools.game_play import _handle_make_game_move, live_game_board
from tests.unit.test_audio_audit_2026_10_27 import USER, _game_with, engine  # noqa: F401 — the fixture


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


@pytest.mark.parametrize("before,san,words", [
    ([], "e4", "pawn from e2 to e4"),
    (["e4"], "c6", "pawn from c7 to c6"),
    (["e4", "e5"], "Nf3", "knight from g1 to f3"),
    (["e4", "d5"], "exd5", "pawn from e4 to d5, takes the pawn on d5"),
    (["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "d5", "exd5", "Nxd5"], "Nxf7", "knight from g5 to f7, takes the pawn on f7"),
    (["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"], "O-O", "castles kingside"),
    (["e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6"], "Qxf7#", "queen from h5 to f7, takes the pawn on f7, check"),
])
def test_a_move_in_words(before, san, words):
    board = chess.Board()
    for m in before:
        board.push_san(m)
    assert game_mode.move_words(board, board.parse_san(san)) == words


def test_the_engines_reply_comes_with_its_piece(engine):
    session = _game_with([])
    r = json.loads(_handle_make_game_move({"move": "e4"}, session_id=session.id, user_id=USER))
    assert r["engine_reply"] == "e5" and r["engine_reply_words"] == "pawn from e7 to e5"
    assert "e5 (pawn from e7 to e5)" in r["note"]


def test_the_already_played_reply_has_the_words_too(engine):
    session = _game_with([])
    json.loads(_handle_make_game_move({"move": "e4"}, session_id=session.id, user_id=USER))
    again = json.loads(_handle_make_game_move({"move": "e4"}, session_id=session.id, user_id=USER))
    assert again.get("already_played") and again["engine_reply_words"] == "pawn from e7 to e5"


def test_the_move_just_played_by_the_model_still_reads_as_that_move():
    before = chess.Board()
    for m in ["e4", "c6"]:
        before.push_san(m)
    after = before.copy()
    for m in ["Nf3", "d5"]:
        after.push_san(m)
    got = read_intent("конь F3", fen=after.fen(), live_game=True, just_played=(before.fen(), "Nf3"))
    assert got == {"kind": "move", "san": "Nf3"}
    # without that context the same words on the new position are unclear, as before
    assert read_intent("конь F3", fen=after.fen(), live_game=True)["kind"] == "unclear_move"


def test_the_voice_intent_route_reads_the_just_played_move(engine):
    session = _game_with(["e4", "Nf3"])   # 1.e4 e5 2.Nf3 Nc6 — the student's Nf3 was just played
    resp = TestClient(app).post("/api/coach/voice/intent", headers={"X-User-Id": USER},
                                json={"text": "конь f3", "session_id": session.id})
    assert resp.status_code == 200 and resp.json() == {"kind": "move", "san": "Nf3"}
    r = json.loads(_handle_make_game_move({"move": "Nf3", "said": "конь f3"}, session_id=session.id, user_id=USER))
    assert r.get("already_played") and live_game_board(session).game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]
