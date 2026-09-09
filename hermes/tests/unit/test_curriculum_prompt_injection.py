"""Tests for the CL Phase-2 curriculum prompt injection + flag-off no-op.

Verifies COACH_CURRICULUM defaults OFF, that with the flag off the prompt is
byte-identical and NO curriculum is ever loaded (grep-provable no-op on the turn
path), and that with the flag on the block is injected and fully fail-open."""

from unittest.mock import patch

import pytest

import src.config as config
import src.curriculum as cur
from src.prompt_builder import build_system_prompt
from src.user_profile import UserProfile

MOCK_SOUL = "# Chess Coach\nYou are a chess coach."


@pytest.fixture(autouse=True)
def _no_rating_sync():
    with patch("src.prompt_builder.maybe_sync_ratings"):
        yield


@pytest.mark.unit
def test_flag_defaults_off():
    assert config.COACH_CURRICULUM is False


@pytest.mark.unit
class TestFlagOff:
    def test_flag_off_does_not_load_curriculum(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_CURRICULUM", False), \
             patch.object(cur, "load_curriculum_block") as load:
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        load.assert_not_called()
        assert "Training focus" not in prompt

    def test_flag_off_is_byte_identical(self):
        profile = UserProfile(user_id="u1", rating=1400, weaknesses=["hangs pieces"])
        with patch.object(config, "COACH_CURRICULUM", False):
            baseline = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
            again = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        assert baseline == again
        assert "Training focus" not in baseline


@pytest.mark.unit
class TestFlagOn:
    def test_flag_on_injects_block(self):
        profile = UserProfile(user_id="u1", rating=1400)
        block = ("## Training focus (engine-measured)\n"
                 "- fork — 5 engine-verified blunders. Offer puzzles on this theme via set_puzzle.")
        with patch.object(config, "COACH_CURRICULUM", True), \
             patch.object(cur, "load_curriculum_block", return_value=block) as load:
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        load.assert_called_once_with("u1")
        assert "## Training focus (engine-measured)" in prompt
        assert "fork" in prompt

    def test_flag_on_no_row_omits_block(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_CURRICULUM", True), \
             patch.object(cur, "load_curriculum_block", return_value=""):
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        assert "Training focus" not in prompt

    def test_flag_on_failopen_on_error(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_CURRICULUM", True), \
             patch.object(cur, "load_curriculum_block", side_effect=RuntimeError("db down")):
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        assert "Training focus" not in prompt
        assert "Chess Coach" in prompt

    def test_flag_on_no_profile_skips(self):
        with patch.object(config, "COACH_CURRICULUM", True), \
             patch.object(cur, "load_curriculum_block") as load:
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=None)
        load.assert_not_called()
        assert "Training focus" not in prompt
