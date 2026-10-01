"""review_game — the voice coach's way to a game review."""

from unittest.mock import patch

import pytest

from src.tools.review_game import review_game


@pytest.mark.unit
def test_review_note_carries_the_moments_and_the_side():
    moments = {"critical_moments": [{"move_number": 16, "side": "black", "move": "Bh5", "type": "blunder",
                                     "eval_before": 0.0, "eval_after": 4.9, "best_move": "Be6", "best_line": "Be6 h3",
                                     "fen_before": "r4rk1/pp2qppp/1np5/4N3/3P2b1/1BR5/PPQ2PPP/5RK1 b - - 4 16"}],
               "total_moves": 40, "engine_depth": 12}
    with patch("src.tools.review_game.find_critical_moments", return_value=moments):
        out = review_game("1. d4 d5", side="black")
    assert out["moments"] == moments["critical_moments"]
    assert "16...Bh5" in out["note"] and "Better: Be6" in out["note"]
    assert "The student played black" in out["note"]


@pytest.mark.unit
def test_review_error_is_passed_on():
    with patch("src.tools.review_game.find_critical_moments", return_value={"error": "bad pgn"}):
        assert review_game("1. zz") == {"error": "bad pgn"}
