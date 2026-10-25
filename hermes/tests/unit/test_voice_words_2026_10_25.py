"""2026-10-25, Alexander's phone, the voice game (screenshots: «Управление доской так и не работает»):

* «с шесть», «конь за шесть» — the transcription writes a file as a bare Russian letter, or «за» for «це»; nothing
  was played and the model said «отличный ход» (src/move_text._SPOKEN_FILE, src/intent unclear_move);
* «Я хотел не конь за шесть, а с шесть пойти пешкой» — a correction nobody could make by voice: now the game's
  takeback plus the move they meant (src/game_intent.corrects_move / correction_move, game_play «correct»);
* «Я пойду d3» — the coach narrated moves the engine never made: the voice check reads the game from the session
  (VoiceCheckRequest.session_id, src/answer_check._coach_move_issues)."""

import json
import time

import chess
import pytest
from fastapi.testclient import TestClient

from src import game_mode
from src.game_intent import correction_move, game_command, spoken_squares
from src.intent import read_intent
from src.server import app, session_store
from src.tools.game_play import _handle_game_action, _handle_make_game_move, _handle_start_game, live_game_board


class _Engine:
    def move(self, fen, elo):
        board = chess.Board(fen)
        for san in ("d5", "e5", "Nf6", "Nc6"):
            try:
                return board.parse_san(san).uci()
            except ValueError:
                continue
        return next(iter(board.legal_moves)).uci()

    def evaluate(self, fen, pov):
        return 0, None


@pytest.fixture
def engine(monkeypatch):
    eng = _Engine()
    monkeypatch.setattr(game_mode, "_engine_move", eng.move)
    monkeypatch.setattr(game_mode, "_evaluate", eng.evaluate)
    return eng


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


# ── the letters of the board, said quickly ─────────────────────────────────

@pytest.mark.parametrize("said,read", [
    ("с шесть", "c6"), ("конь за шесть", "конь c6"), ("д четыре", "d4"), ("г пять", "g5"), ("б пять", "b5"),
    ("ф три", "f3"), ("х шесть", "h6"), ("я пойду с шесть", "я пойду c6"), ("пешка е четыре", "пешка e4"),
    ("с ума сойти", "с ума сойти"),                                   # no rank after the letter: words
    ("За шесть лет он стал гроссмейстером и выиграл много турниров",   # a long sentence without a move around
     "За шесть лет он стал гроссмейстером и выиграл много турниров"),
])
def test_bare_letters_are_files(said, read):
    assert spoken_squares(said) == read


# ── the move they meant ─────────────────────────────────────────────────────

BEFORE = chess.Board()
for _san in ("e4", "e5", "Nf3"):
    BEFORE.push_san(_san)   # Black to move: both Nc6 and c6 are legal


@pytest.mark.parametrize("said,meant", [
    ("не конь, а пешка на c6", "c6"),
    ("Я хотел не конь за шесть, а с шесть пойти пешкой", "c6"),
    ("я имел в виду конь на f6", "Nf6"),
    ("вместо этого d6", "d6"),
    ("верни ход, я хотел пешкой на c6", "c6"),
    ("не та фигура, пешка c6", "c6"),
    ("не слон, а конь на c6", "Nc6"),
])
def test_a_correction_is_read_as_the_move_meant(said, meant):
    assert game_command(said) == "correct"
    assert correction_move(said, BEFORE) == meant


@pytest.mark.parametrize("said", ["не тот ход, слон", "не конь а пешка", "я хотел не это"])
def test_a_correction_without_a_readable_move_is_a_correction_still(said):
    assert game_command(said) == "correct"
    assert correction_move(said, BEFORE) is None


@pytest.mark.parametrize("said,command", [
    ("я хотел бы сыграть d6", None),             # a move, not a correction
    ("хотел спросить, что это за дебют", None),
    ("я не хотел так ходить", None),
    ("верни ход", "takeback"),
    ("сдаюсь", "resign"),
])
def test_other_words_are_not_corrections(said, command):
    assert game_command(said) == command


def _game(color="white"):
    session = session_store.create("words-user")
    first = json.loads(_handle_start_game({"color": color}, session_id=session.id, user_id="words-user"))
    assert first["ok"]
    return session


def test_the_correction_replaces_the_move_on_the_board(engine):
    session = _game()
    played = json.loads(_handle_make_game_move({"move": "Nc3"}, session_id=session.id, user_id="words-user"))
    assert played["ok"] and played["student_move"] == "Nc3"
    reply = json.loads(_handle_game_action({"said": "не конь, а пешка на c3"}, session_id=session.id, user_id="words-user"))
    assert reply["ok"] and reply["action"] == "correct" and reply["done"], reply
    state = live_game_board(session).game_state
    assert state["moves"][0] == "c3" and len(state["moves"]) == 2, state["moves"]   # c3 and the engine's reply
    assert "c3 is played instead" in reply["note"] and "undone" in reply["note"]


def test_a_correction_nobody_can_read_changes_nothing(engine):
    session = _game()
    _handle_make_game_move({"move": "Nc3"}, session_id=session.id, user_id="words-user")
    reply = json.loads(_handle_game_action({"said": "не тот ход, слон"}, session_id=session.id, user_id="words-user"))
    assert not reply["ok"] and reply["action"] == "correct" and not reply["done"]
    assert "name the move plainly" in reply["note"] and "last move stays on the board" in reply["note"]
    assert live_game_board(session).game_state["moves"][0] == "Nc3"


def test_a_correction_before_any_move_asks_for_the_move(engine):
    session = _game()
    reply = json.loads(_handle_game_action({"said": "я имел в виду e4"}, session_id=session.id, user_id="words-user"))
    assert not reply["ok"] and not reply["done"] and "say the move they want to play" in reply["note"]
    assert live_game_board(session).game_state["moves"] == []


# ── the intent reader: a move, a correction, or «not understood» ───────────

PGN = "1. e4 e5 2. Nf3"


@pytest.mark.parametrize("said,intent", [
    ("с шесть", {"kind": "move", "san": "c6"}),
    ("конь за шесть.", {"kind": "move", "san": "Nc6"}),
    ("ну, с шесть", {"kind": "move", "san": "c6"}),
    ("я пойду с шесть", {"kind": "move", "san": "c6"}),
    ("не конь, а пешка на c6", {"kind": "game_command", "command": "correct"}),
    ("конь на f3", {"kind": "unclear_move", "text": "конь на f3"}),       # not legal for Black: nothing is played
    ("е пять", {"kind": "unclear_move", "text": "е пять"}),
    ("ладно", {"kind": "none"}),
    ("конечно", {"kind": "none"}),
    ("что делает конь на f3", {"kind": "none"}),                           # a question: the model answers
    ("дай два варианта", {"kind": "none"}),
    ("а что думаешь про позицию", {"kind": "none"}),
])
def test_the_intent_reader_in_a_live_game(said, intent):
    assert read_intent(said, fen=BEFORE.fen(), pgn=PGN, live_game=True) == intent


# ── the voice check knows the game ─────────────────────────────────────────

def test_the_voice_check_reads_the_coach_s_moves_against_the_game(engine):
    session = _game()
    played = json.loads(_handle_make_game_move({"move": "e4"}, session_id=session.id, user_id="words-user"))
    assert played["engine_reply"] == "d5"
    client = TestClient(app)
    fen = live_game_board(session).game_state and played["fen"]

    def check(text):
        resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "words-user"},
                           json={"text": text, "fen": fen, "pgn": "1. e4 d5", "question": "мой ход e4", "session_id": session.id})
        assert resp.status_code == 200
        return resp.json()["issues"]

    issues = check("Хорошо. Я пойду d3.")
    assert issues and "did not play d3" in issues[0] and "its last move was d5" in issues[0], issues
    assert check("Я отвечаю d5.") == []
    # without the session the sentence cannot be judged — and is not
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "words-user"},
                       json={"text": "Я пойду d3.", "fen": fen, "pgn": "1. e4 d5", "question": "мой ход e4"})
    assert resp.json()["issues"] == []


# ── the voice pipeline says the move itself: the model is told not to repeat it ───

def test_the_played_move_block_for_a_spoken_answer_tells_the_model_not_to_restate(engine):
    from src.server import _game_prestep

    session = _game()
    board_rec = live_game_board(session)
    step = _game_prestep(session, board_rec, "e4", spoken=True)
    assert step and step["view"]["student"]["san"] == "e4"
    assert "ALREADY SAID ALOUD" in step["block"] and "do NOT repeat the moves" in step["block"]
    assert "e4, and your reply d5" in step["block"]
    plain = _game_prestep(session, live_game_board(session), "Nf3")
    assert plain and "Tell them the engine's reply" in plain["block"]
