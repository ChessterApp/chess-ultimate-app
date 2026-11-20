"""Tester 20.11: «Лучше было 5.d3: пешка поддерживает центр и открывает дорогу белопольному слону» — d2–d3 opens the
dark-squared bishop (it leaves d2, a dark square). answer_check_rules._pawn_bishop_issues."""

import pytest

from src.answer_check_rules import _pawn_bishop_issues


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "лучше было 5.d3: пешка поддерживает центр и открывает дорогу белопольному слону.",
    "ход e3 открывает чернопольного слона.",
    "5...d6 освобождает чернопольного слона.",
    "d3 opens the light-squared bishop.",
])
def test_the_wrong_bishop_is_caught(text):
    assert _pawn_bishop_issues(text)


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "лучше было 5.d3: пешка поддерживает центр и открывает дорогу чернопольному слону.",
    "ход e3 открывает белопольного слона.",
    "5...d6 освобождает белопольного слона.",
    "сd3 открывает белопольного слона.",          # a bishop's move, not a pawn's
    "ход d3 не открывает белопольного слона.",      # said the other way
    "ход d4 открывает белопольного слона.",         # d2–d4 or d3–d4: not judged
])
def test_right_or_unjudged_claims_pass(text):
    assert not _pawn_bishop_issues(text)


@pytest.mark.unit
def test_the_card_names_the_coach_game_players_in_the_talks_language():
    from src.review_moments import _game

    pgn = '[Event "Game with the coach"]\n[White "Student"]\n[Black "Coach (Stockfish 1200)"]\n[Result "0-1"]\n\n1. e4 0-1'
    assert (_game(pgn, None, "ru")["white"], _game(pgn, None, "ru")["black"]) == ("Ты", "Тренер (1200)")
    assert _game(pgn, None, "en")["black"] == "Coach (1200)"
    assert _game('[White "Carlsen"]\n[Black "Nepo"]\n\n1. e4 *', None, "ru")["white"] == "Carlsen"


@pytest.mark.unit
def test_the_finished_comment_keeps_the_better_move_apart_from_the_resignation():
    from src.game_mode import COMMENT_RULES

    assert "never join it to what happened next" in COMMENT_RULES["finished"]
