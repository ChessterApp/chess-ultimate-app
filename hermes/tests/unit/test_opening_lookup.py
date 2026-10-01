"""lookup_opening — the voice coach's way to the opening book."""

import json

import chess
import pytest

from src.tools.opening_lookup import lookup_opening, _handle_lookup_opening


@pytest.mark.unit
class TestLookupOpening:
    def test_named_opening_goes_on_the_board(self):
        out = lookup_opening("Что такое жареная печень?", chess.STARTING_FEN)
        assert out["found"] and out["name"].endswith("Fried Liver Attack") and out["loaded"]
        assert out["board_actions"] == [{"type": "load_pgn", "pgn": out["line"]}]
        assert "5...Na5" in out["note"]

    def test_question_about_the_board_keeps_it(self):
        board = chess.Board()
        for san in "e4 e5 Nf3 Nc6 Bc4 Bc5".split():
            board.push_san(san)
        out = lookup_opening("как из этой позиции перейти в защиту двух коней?", board.fen(),
                             "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5")
        assert out["found"] and not out["loaded"] and out["about_the_board"]
        assert "board_actions" not in out and "left the line at 3...Bc5" in out["note"]

    def test_nothing_named(self):
        assert lookup_opening("объясни, что такое связка") == {"found": False}
        assert json.loads(_handle_lookup_opening({"question": "привет"})) == {"found": False}
