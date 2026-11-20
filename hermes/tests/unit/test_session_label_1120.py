"""Tester 20.11: a session with a game against the coach was named by the coach's last comment, renamed on every move,
and «Без названия» while its game had 13 moves. With no question in it, it is named by its game."""

from types import SimpleNamespace as NS

import pytest

from src import server


def _session(messages, boards):
    return NS(id="s", title="", created_at=1.0, messages=messages, boards=boards, board_state=None, active_board_id=None)


@pytest.mark.unit
def test_a_game_session_is_named_by_its_game():
    game = NS(kind="game", pgn="1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *", game_state={"result": "*"}, updated_at=5)
    comment = NS(role="assistant", content="Ход 2...Nc6 хороший.", timestamp=9.0)
    summary = server._session_summary(_session([comment], [game]))
    assert summary["preview"].startswith("1.e4 e5 2.Nf3 Nc6")
    assert server._session_summary(_session([], [game]))["preview"].startswith("1.e4 e5")


@pytest.mark.unit
def test_a_question_still_names_the_session():
    game = NS(kind="game", pgn="1. e4 e5 *", game_state={}, updated_at=5)
    question = NS(role="user", content="Как отвечать на e4?", timestamp=3.0)
    assert server._session_summary(_session([question], [game]))["preview"] == "Как отвечать на e4?"
