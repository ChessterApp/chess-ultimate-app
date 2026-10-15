"""2026-10-14: a legal move said by voice in the game was «not accepted by the system».

The model passed Bc4 to make_game_move and the server refused it as a question because the student's
words had «хорошо», «лучше», «можно» or a «?» (speech recognition adds one); squares said aloud («си
четыре») were no move at all. Then the coach drew an arrow, «будем считать, что сыграно», and answered
with a move of its own.
"""

import json

import chess
import pytest
from tools.registry import registry

from src import game_mode
from src.sessions import session_store
from src.tools import discover_and_register


@pytest.fixture(autouse=True)
def _engine(monkeypatch):
    discover_and_register()
    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))


def _call(name, args, session, **kw):
    return json.loads(registry.dispatch(name, args, session_id=session.id, **kw))


@pytest.mark.parametrize("words", ["Хорошо, слон c4", "Слон c4?", "Давай лучше слон c4", "Можно слон c4?",
                                   "слон си четыре", "сичи"])
def test_the_move_the_model_passes_is_played_whatever_the_words_around_it(words):
    session = session_store.create(user_id=f"voice-move-{words}")
    _call("start_game", {"color": "white"}, session)
    _call("make_game_move", {"move": "e4"}, session)
    out = _call("make_game_move", {"move": "Bc4"}, session, utterance=words)
    assert out.get("ok") and out["student_move"] == "Bc4", out


def test_an_if_is_still_an_idea_and_the_refusal_says_nothing_changed():
    session = session_store.create(user_id="voice-move-if")
    _call("start_game", {"color": "white"}, session)
    _call("make_game_move", {"move": "e4"}, session)
    out = _call("make_game_move", {"move": "Bc4"}, session, utterance="А если слон c4?")
    assert "did not play it" in out["error"] and "Nothing was played" in out["board"]
    assert "never answer with a move of yours" in out["board"]


@pytest.mark.parametrize("said,san", [("слон си четыре", "Bc4"), ("слон це 4", "Bc4"), ("Хорошо, слон c4", "Bc4"),
                                      ("Слон, c4", "Bc4"), ("Давай лучше слон c4", "Bc4")])
def test_squares_said_aloud_are_moves(said, san):
    from src.game_intent import bare_move

    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    assert bare_move(said, board) == san


def test_a_move_said_from_square_to_square():
    from src.game_intent import bare_move, spoken_squares

    assert spoken_squares("е два е четыре") == "e2e4"
    assert bare_move("е два е четыре", chess.Board()) == "e4"
    assert bare_move("Слон c4?", chess.Board()) is None   # the server does not play a question on its own
