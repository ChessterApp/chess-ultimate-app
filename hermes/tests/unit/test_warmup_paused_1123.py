"""A warm-up left for something else is said, once, by the server: «Разминка прервана на задаче 2 из 3.» (open since
20.11: a game pasted in the middle of a warm-up ended it without a word)."""

import pytest

from src import warmup
from src.sessions import Session

P1 = {"puzzle_id": "p1", "fen": "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "solution": ["d1d8"]}
P2 = {"puzzle_id": "p2", "fen": "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1", "solution": ["e1e8"]}
P3 = {"puzzle_id": "p3", "fen": "7k/6pp/8/8/8/8/6PP/R5K1 w - - 0 1", "solution": ["a1a8"]}
GAME = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"


def _warm():
    s = Session(id="s", user_id="u")
    assert warmup.start(s, [P1, P2, P3]) == {"n": 1, "of": 3}
    s.set_board_state(P1["fen"])
    warmup.put_up(s, "p1", P1["fen"])
    return s


@pytest.mark.unit
def test_on_its_own_puzzle_the_warm_up_is_not_paused():
    s = _warm()
    assert warmup.paused(s) is None
    s.set_board_state("3R2k1/5ppp/8/8/8/8/5PPP/6K1 b - - 1 1")  # along the solution: still the warm-up
    assert warmup.paused(s) is None


@pytest.mark.unit
def test_another_position_pauses_it_said_once_until_the_student_is_back():
    s = _warm()
    s.set_board_state(GAME)  # a pasted game on the board
    assert warmup.paused(s) == {"n": 1, "of": 3}
    warmup.note_paused_said(s)
    assert warmup.paused(s) is None  # not every turn
    s.set_board_state(P2["fen"])
    warmup.put_up(s, "p2", P2["fen"])  # «дальше»: back at the warm-up
    s.set_board_state(GAME)
    assert warmup.paused(s) == {"n": 2, "of": 3}


@pytest.mark.unit
def test_a_game_pasted_into_the_message_pauses_it_with_the_puzzle_still_on_the_board():
    s = _warm()
    assert warmup.paused(s, game_in_message=True) == {"n": 1, "of": 3}


@pytest.mark.unit
def test_no_warm_up_or_one_over_is_never_paused():
    s = Session(id="s", user_id="u")
    s.set_board_state(GAME)
    assert warmup.paused(s) is None
    w = _warm()
    w.warmup["over"] = True
    w.set_board_state(GAME)
    assert warmup.paused(w) is None


@pytest.mark.unit
@pytest.mark.parametrize("lang, line", [
    ("ru", "Разминка прервана на задаче 2 из 5."),
    ("en", "The warm-up is paused at puzzle 2 of 5."),
    ("kk", "Жаттығу 5 есептің 2-есебінде тоқтатылды."),
    ("kz", "Жаттығу 5 есептің 2-есебінде тоқтатылды."),
])
def test_the_line_is_the_servers_in_the_students_language(lang, line):
    assert warmup.paused_line({"n": 2, "of": 5}, lang) == line
    assert "adds its own closing line" in warmup.paused_note({"n": 2, "of": 5})  # the end of the answer (26.11)
