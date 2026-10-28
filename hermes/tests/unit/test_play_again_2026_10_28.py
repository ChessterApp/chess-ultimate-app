"""Stand run 28.10 (text): «Сдаюсь», then «Давай ещё раз, я белыми» — the colour after «ещё раз» broke the command,
no game started, the coach said «Новая партия, ты белыми» anyway, and to «d4» it answered «соперник ответил
3...exd4» for a game that did not exist. Now the wish after the command is part of it, and a move written with no
game on is said to be nothing played."""

import chess
import pytest

from src import game_mode
from src.game_intent import game_command
from src.sessions import session_store


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    def move(fen, elo):
        board = chess.Board(fen)
        for san in ("e4", "e5", "Nf3", "Nc6", "d4", "d5", "Nf6"):
            try:
                return board.parse_san(san).uci()
            except ValueError:
                continue
        return next(iter(board.legal_moves)).uci()

    monkeypatch.setattr(game_mode, "_engine_move", move)
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


@pytest.mark.unit
@pytest.mark.parametrize("text", ["Давай ещё раз, я белыми", "Ещё раз, посложнее", "давай еще раз — за чёрных",
                                  "Ещё раз, только я чёрными", "сыграем ещё", "Давай ещё раз"])
def test_play_again_with_a_wish_is_a_new_game(text):
    assert game_command(text) == "restart"


@pytest.mark.unit
@pytest.mark.parametrize("text", ["ещё раз объясни", "Покажи ещё раз", "Давай ещё раз попробуем этот вариант"])
def test_again_about_something_else_is_no_new_game(text):
    assert game_command(text) is None


def _games(session):
    return [b for b in session.boards if b.kind == "game"]


@pytest.mark.unit
def test_after_a_resignation_a_move_is_nothing_played_and_play_again_starts_one():
    from src.server import _game_prestep

    session = session_store.create("u")
    board, _ = game_mode.start_game(session, "black", 1200, "quiet")
    _game_prestep(session, session.get_board(session.active_board_id), "e5")
    _game_prestep(session, session.get_board(session.active_board_id), "Сдаюсь")
    assert [g.game_state["status"] for g in _games(session)] == ["finished"]

    step = _game_prestep(session, session.get_board(session.active_board_id), "d4")
    assert step["view"] is None and "No game is on — nothing was played" in step["block"]
    assert [g.game_state["status"] for g in _games(session)] == ["finished"]

    step = _game_prestep(session, session.get_board(session.active_board_id), "Давай ещё раз, я белыми")
    assert step["view"]["status"] == "playing" and step["view"]["student_color"] == "white"
    step = _game_prestep(session, session.get_board(session.active_board_id), "d4")
    assert step["view"]["moves"][:1] == ["d4"]
