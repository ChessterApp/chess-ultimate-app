"""2026-10-16: the engine's strength in words, a level change during the game, a new game asked for while one
is on (voice, 2026-10-15: «с самым сильным ботом 2500» got «A game is already on», «играй сильнее» was nothing)."""

import json

import chess
import pytest

from src.game_intent import game_command, game_request, game_wish, strength_in_words
from src.intent import read_intent

GAME = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"


@pytest.mark.parametrize("text,current,elo", [
    ("на 2500", None, 2500),
    ("играй на 1300", None, 1200),                   # the nearest of the site's steps
    ("с самым сильным ботом", None, 2500),
    ("играй как гроссмейстер", None, 2500),
    ("играй слабо", None, 800),
    ("как новичок", None, 600),
    ("играй сильнее", 1200, 1500),                   # a step up from the game's level
    ("сделай посложнее", 2200, 2500),
    ("посложнее", 2500, 2500),                       # the top already
    ("полегче, пожалуйста", 1500, 1200),
    ("play harder", 1000, 1200),
    ("средний уровень", None, 1500),
    ("привет", None, None),
])
def test_strength_in_words(text, current, elo):
    assert strength_in_words(text, current) == elo


def test_a_request_for_a_game_names_the_strength_in_words_or_numbers():
    assert game_request("Я хочу сыграть партию с самым сильным ботом 2500.") == {"color": "white", "elo": 2500}
    assert game_request("Давай сыграем, играй как гроссмейстер") == {"color": "white", "elo": 2500}
    assert game_request("Сыграем партию? Я за белых, играй слабо") == {"color": "white", "elo": 800}
    assert game_wish("сыграем ещё раз чёрными, посложнее", 1500) == {"color": "black", "elo": 1800}


@pytest.mark.parametrize("text,command", [
    ("Играй сильнее", "level"),
    ("Сделай посложнее", "level"),
    ("Поставь уровень 2500", "level"),
    ("Полегче", "level"),
    ("Можешь играть слабее?", "level"),
    ("Play harder", "level"),
    ("Сыграем ещё раз, посложнее", "restart"),       # a new game, with the strength — not a level change
    ("Сдаюсь", "resign"),
    ("Верни ход", "takeback"),
    ("Хорошо, e4", None),
    ("А сильнее ли слон коня?", None),
])
def test_the_level_is_a_game_command(text, command):
    assert game_command(text) == command


def test_in_a_game_the_words_ask_for_a_level_or_a_new_game():
    assert read_intent("Играй сильнее", fen=GAME, live_game=True) == {"kind": "game_command", "command": "level", "elo": 1500}
    out = read_intent("Я хочу сыграть партию с самым сильным ботом 2500.", fen=GAME, live_game=True)
    assert out == {"kind": "game_command", "command": "restart", "elo": 2500}   # the colour: the last game's
    assert read_intent("Играй сильнее", fen=GAME)["kind"] == "none"   # no game: nothing to change


def _session(monkeypatch, elo=1200):
    from src import game_mode
    from src.sessions import session_store

    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))
    session = session_store.create(user_id="strength-2026-10-16")
    game_mode.start_game(session, "white", elo, "quiet")
    return session


def test_the_level_changes_for_the_rest_of_the_game(monkeypatch):
    from src.tools.game_play import _handle_game_action, _handle_make_game_move, live_game_board

    session = _session(monkeypatch)
    out = json.loads(_handle_game_action({"said": "играй посложнее"}, session_id=session.id))
    assert out["ok"] and out["action"] == "level" and out["engine_elo"] == 1500
    assert "1500" in out["note"]
    assert live_game_board(session).game_state["moves"] == []           # the game goes on from the same position
    out = json.loads(_handle_game_action({"said": "уровень 2500"}, session_id=session.id))
    assert out["engine_elo"] == 2500
    played = json.loads(_handle_make_game_move({"move": "e4"}, session_id=session.id, utterance="e4"))
    assert played["ok"] and played["board_actions"][0]["game"]["engine_elo"] == 2500
    out = json.loads(_handle_game_action({"said": "поставь уровень"}, session_id=session.id))
    assert out["done"] is False and "which level" in out["note"]


def test_a_new_game_asked_for_while_one_is_on_restarts_it(monkeypatch):
    from src.tools.game_play import _handle_start_game, live_game_board

    session = _session(monkeypatch)
    out = json.loads(_handle_start_game({"said": "Я хочу сыграть партию с самым сильным ботом 2500."},
                                        session_id=session.id))
    assert out["ok"] and out["restarted"] and out["engine_elo"] == 2500 and out["student_color"] == "white"
    assert "resigned" in out["note"] and "new game" in out["note"]
    games = [b for b in session.boards if b.kind == "game"]
    assert [b.game_state["status"] for b in games] == ["finished", "playing"]
    assert live_game_board(session).game_state["engine_elo"] == 2500
    # The model's own start_game while a game is on: the same restart, with its arguments.
    out = json.loads(_handle_start_game({"color": "black", "elo": 800}, session_id=session.id))
    assert out["ok"] and out["restarted"] and out["student_color"] == "black" and out["engine_elo"] == 800


def test_the_text_coach_restarts_too(monkeypatch):
    from src.server import _game_prestep
    from src.tools.game_play import live_game_board

    session = _session(monkeypatch)
    live = live_game_board(session)
    step = _game_prestep(session, live, "Давай сыграем партию, играй как гроссмейстер")
    assert step and step["view"]["engine_elo"] == 2500 and "new game has started" in step["block"]
    step = _game_prestep(session, live_game_board(session), "сделай полегче")
    assert step and step["view"]["engine_elo"] == 2200 and "strength was changed" in step["block"]


def test_a_game_asked_for_in_words_while_one_is_on_restarts_through_game_action_too(monkeypatch):
    """The voice path: intent says restart, the hook calls game_action with the words — the same reading."""
    from src.tools.game_play import _handle_game_action, live_game_board

    session = _session(monkeypatch)
    out = json.loads(_handle_game_action({"said": "Давай сыграем, играй как гроссмейстер"}, session_id=session.id))
    assert out["ok"] and out["action"] == "restart" and out["done"]
    assert live_game_board(session).game_state["engine_elo"] == 2500
    assert [b.game_state["status"] for b in session.boards if b.kind == "game"] == ["finished", "playing"]
