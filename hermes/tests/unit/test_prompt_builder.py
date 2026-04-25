"""Unit tests for system prompt builder."""

import chess
import pytest

from src.prompt_builder import build_system_prompt, LOCALE_TO_LANGUAGE
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

    def test_locale_russian_injects_directive(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="ru")
        assert "CRITICAL LANGUAGE RULE" in prompt
        assert "Russian" in prompt
        # Language directive must come before SOUL content
        lang_pos = prompt.index("CRITICAL LANGUAGE RULE")
        soul_pos = prompt.index("Chess Coach")
        assert lang_pos < soul_pos

    def test_locale_kazakh_injects_directive(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="kz")
        assert "CRITICAL LANGUAGE RULE" in prompt
        assert "Kazakh" in prompt

    def test_locale_english_no_directive(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="en")
        assert "CRITICAL LANGUAGE RULE" not in prompt

    def test_locale_none_no_directive(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale=None)
        assert "CRITICAL LANGUAGE RULE" not in prompt

    def test_locale_unknown_uses_code(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="fr")
        assert "CRITICAL LANGUAGE RULE" in prompt
        assert "fr" in prompt

    def test_locale_to_language_mapping(self):
        assert LOCALE_TO_LANGUAGE["ru"] == "Russian"
        assert LOCALE_TO_LANGUAGE["kz"] == "Kazakh"
        assert LOCALE_TO_LANGUAGE["en"] == "English"

    def test_prompt_contains_set_fen_example(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "set_fen" in prompt
        assert "draw_arrows" in prompt
        assert "Scholar's Mate" in prompt

    def test_prompt_contains_example_fen(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4" in prompt
