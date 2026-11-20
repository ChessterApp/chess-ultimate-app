"""Tester 20.11: after «Реванш», the chip «Главная ошибка» — the coach asked for the game's record, its own review of
that game just above. A review asked during a game in progress is the session's latest finished game."""

from types import SimpleNamespace as NS

import pytest

from src import server
from src.intent import asks_game_review

PGN = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"
LONG = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7 Kxf7 1-0"


def _game(bid, status, pgn, at):
    return NS(id=bid, kind="game", game_state={"status": status}, pgn=pgn, updated_at=at)


@pytest.mark.unit
def test_the_chip_asks_for_the_review():
    assert asks_game_review("Главная ошибка") and asks_game_review("The biggest mistake") and asks_game_review("Басты қате")


@pytest.mark.unit
def test_during_the_rematch_the_game_just_finished_is_reviewed():
    old = _game("g1", "finished", LONG, 10)
    older = _game("g0", "finished", PGN, 5)
    live = _game("g2", "playing", "", 20)
    session = NS(boards=[older, old, live])
    assert server._board_review_pgn(live, "Главная ошибка", session) == LONG
    assert server._board_review_pgn(live, "Какой здесь план?", session) is None
    assert server._board_review_pgn(live, "Главная ошибка", NS(boards=[live])) is None
