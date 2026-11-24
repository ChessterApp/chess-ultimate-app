"""On a finished board nobody moves next (tester 23.11: 7k/5Q2/6K1/8/8/8/8/8 b — «Это пат: ничья… Однако сейчас ход за
тобой, поэтому пат ещё не наступил. Ищи ход, который даст шах»)."""

import pytest

from src.answer_check import CheckContext, check_sentence

STALEMATE = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
MATE = "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"
PLAYING = "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1"


def _issues(sentence, fen):
    return check_sentence(sentence, CheckContext.from_fens([fen], [], question=fen))


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Однако сейчас ход за тобой, поэтому пат ещё не наступил.",
    "Ищи ход, который даст шах и не оставит королю выхода.",
    "Пат ещё не наступил.",
    "It's your move: find a move that gives check.",
])
def test_a_finished_board_has_no_next_move(sentence):
    issues = _issues(sentence, STALEMATE)
    assert issues and "OVER" in issues[0] and "stalemate now" in issues[0]
    assert any("checkmated" in i for i in _issues(sentence, MATE))


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Это пат: ничья.",
    "Сейчас очередь чёрных, ходить им некуда, это пат.",
    "В следующий раз ищи ход, который даёт шах.",
    "На прошлом ходу надо было найти ход с шахом.",
])
def test_true_words_and_advice_for_later_are_left_alone(sentence):
    assert not any("OVER" in i for i in _issues(sentence, STALEMATE))


@pytest.mark.unit
def test_a_game_still_going_is_not_judged():
    assert not any("OVER" in i for i in _issues("Твой ход: ищи ход, который даст шах.", PLAYING))
