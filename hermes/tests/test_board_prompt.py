"""Tests that board_control instructions are present in SOUL.md and system prompt."""

from pathlib import Path

import pytest

from src.prompt_builder import build_system_prompt

SOUL_PATH = Path(__file__).resolve().parent.parent / "profiles" / "chess-coach" / "SOUL.md"
SOUL_CONTENT = SOUL_PATH.read_text()


@pytest.mark.unit
class TestBoardControlInSoul:
    def test_soul_contains_board_control_section(self):
        assert "## Board Control" in SOUL_CONTENT

    def test_soul_board_control_is_mandatory(self):
        assert "Board Control (MANDATORY)" in SOUL_CONTENT

    def test_soul_show_dont_tell(self):
        assert "Show, don't tell" in SOUL_CONTENT

    def test_soul_set_fen_instruction(self):
        assert "set_fen" in SOUL_CONTENT

    def test_soul_draw_arrows_instruction(self):
        assert "draw_arrows" in SOUL_CONTENT

    def test_soul_load_pgn_instruction(self):
        assert "load_pgn" in SOUL_CONTENT

    def test_soul_highlight_squares_instruction(self):
        assert "highlight_squares" in SOUL_CONTENT


@pytest.mark.unit
class TestBoardControlInPrompt:
    def test_prompt_contains_use_proactively(self):
        prompt = build_system_prompt(soul_content=SOUL_CONTENT)
        assert "USE PROACTIVELY" in prompt

    def test_prompt_contains_golden_rule(self):
        prompt = build_system_prompt(soul_content=SOUL_CONTENT)
        assert "GOLDEN RULE" in prompt

    def test_prompt_contains_primary_teaching_tool(self):
        prompt = build_system_prompt(soul_content=SOUL_CONTENT)
        assert "PRIMARY teaching tool" in prompt

    def test_prompt_board_control_actions_listed(self):
        prompt = build_system_prompt(soul_content=SOUL_CONTENT)
        for action in ["set_fen", "load_pgn", "draw_arrows", "highlight_squares",
                        "set_puzzle", "navigate", "flip_board", "clear_board"]:
            assert action in prompt, f"Missing board_control action: {action}"
