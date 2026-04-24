"""Unit tests for board control tool."""

import json

import chess
import pytest

from src.tools.board_control import build_board_action, _handle_board_control


@pytest.mark.unit
class TestBuildBoardAction:
    def test_set_fen(self):
        result = build_board_action("set_fen", {"fen": chess.STARTING_FEN})
        assert result["action"] == "set_fen"
        assert result["fen"] == chess.STARTING_FEN

    def test_draw_arrows(self):
        result = build_board_action("draw_arrows", {
            "arrows": [{"from": "e2", "to": "e4"}],
        })
        assert result["action"] == "draw_arrows"
        assert len(result["arrows"]) == 1

    def test_navigate(self):
        result = build_board_action("navigate", {"direction": "next"})
        assert result["action"] == "navigate"
        assert result["direction"] == "next"

    def test_clear_board(self):
        result = build_board_action("clear_board", {})
        assert result["action"] == "clear_board"

    def test_flip_board(self):
        result = build_board_action("flip_board", {})
        assert result["action"] == "flip_board"

    def test_unknown_action_type(self):
        result = build_board_action("unknown_action", {})
        assert "error" in result

    def test_invalid_fen_returns_error(self):
        result = build_board_action("set_fen", {"fen": "garbage"})
        assert "error" in result

    def test_highlight_squares(self):
        result = build_board_action("highlight_squares", {
            "squares": ["e4", "d5"],
            "color": "red",
        })
        assert result["action"] == "highlight_squares"
        assert result["squares"] == ["e4", "d5"]
        assert result["color"] == "red"


@pytest.mark.unit
class TestBoardControlHandler:
    def test_handler_returns_json(self):
        result = _handle_board_control({"action_type": "flip_board"})
        parsed = json.loads(result)
        assert parsed["action"] == "flip_board"

    def test_handler_set_fen(self):
        result = _handle_board_control({
            "action_type": "set_fen",
            "fen": chess.STARTING_FEN,
        })
        parsed = json.loads(result)
        assert parsed["action"] == "set_fen"

    def test_handler_error_returns_json(self):
        result = _handle_board_control({"action_type": "bad_type"})
        parsed = json.loads(result)
        assert "error" in parsed
