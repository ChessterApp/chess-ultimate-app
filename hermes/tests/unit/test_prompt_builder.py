"""Unit tests for system prompt builder."""

import chess
import pytest

from src.prompt_builder import build_system_prompt
from src.user_profile import UserProfile

MOCK_SOUL = "# Chess Coach\nYou are a chess coach."


@pytest.mark.unit
class TestPromptBuilder:
    def test_soul_only(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "Chess Coach" in prompt
        assert "Student Profile" not in prompt
        assert "Board Control" in prompt

    def test_with_user_profile(self):
        profile = UserProfile(
            user_id="u1",
            rating=1500,
            goals=["Improve tactics"],
            weaknesses=["Endgames"],
        )
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            user_profile=profile,
        )
        assert "Student Profile" in prompt
        assert "1500" in prompt
        assert "Improve tactics" in prompt
        assert "Endgames" in prompt

    def test_with_board_state(self):
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            board_fen=chess.STARTING_FEN,
        )
        assert "Current Board State" in prompt
        assert chess.STARTING_FEN in prompt

    def test_with_move_history(self):
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            board_fen=chess.STARTING_FEN,
            move_history=["e4", "e5", "Nf3", "Nc6"],
        )
        assert "Move history" in prompt
        assert "1. e4 e5" in prompt
        assert "2. Nf3 Nc6" in prompt

    def test_combines_all_sources(self):
        profile = UserProfile(user_id="u1", rating=2000, style="aggressive")
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            user_profile=profile,
            board_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
            move_history=["e4"],
        )
        assert "Chess Coach" in prompt
        assert "Student Profile" in prompt
        assert "2000" in prompt
        assert "aggressive" in prompt
        assert "Current Board State" in prompt
        assert "Board Control" in prompt
