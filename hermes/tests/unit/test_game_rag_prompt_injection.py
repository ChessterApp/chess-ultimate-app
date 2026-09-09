"""Tests for the CL Phase-1 Slice-2 'Recent games' prompt digest + flag default.

Verifies COACH_GAME_RAG defaults OFF, that with the flag off the prompt is
byte-identical and NO insights are ever loaded, and that with the flag on the
digest is injected and fully fail-open."""

from unittest.mock import patch

import pytest

import src.config as config
import src.tools.game_insights as gi
from src.prompt_builder import build_system_prompt
from src.user_profile import UserProfile

MOCK_SOUL = "# Chess Coach\nYou are a chess coach."


@pytest.fixture(autouse=True)
def _no_rating_sync():
    with patch("src.prompt_builder.maybe_sync_ratings"):
        yield


@pytest.mark.unit
def test_flag_defaults_off():
    """The safety default for this slice is OFF."""
    assert config.COACH_GAME_RAG is False


@pytest.mark.unit
class TestFlagOff:
    def test_flag_off_does_not_load_insights(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_GAME_RAG", False), \
             patch.object(gi, "load_recent_insights") as load:
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        load.assert_not_called()
        assert "Recent games" not in prompt

    def test_flag_off_is_byte_identical(self):
        profile = UserProfile(user_id="u1", rating=1400, weaknesses=["hangs pieces"])
        with patch.object(config, "COACH_GAME_RAG", False):
            baseline = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
            again = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        assert baseline == again
        assert "Recent games" not in baseline


@pytest.mark.unit
class TestFlagOn:
    def test_flag_on_injects_block(self):
        profile = UserProfile(user_id="u1", rating=1400)
        insights = [{
            "opening": "Sicilian Defense",
            "result": "0-1",
            "blunders": [{"classification": "blunder", "theme": "middlegame"}],
        }]
        with patch.object(config, "COACH_GAME_RAG", True), \
             patch.object(gi, "load_recent_insights", return_value=insights) as load:
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        load.assert_called_once_with("u1", limit=3)
        assert "## Recent games" in prompt
        assert "Sicilian Defense" in prompt

    def test_flag_on_no_insights_omits_block(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_GAME_RAG", True), \
             patch.object(gi, "load_recent_insights", return_value=[]):
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        assert "Recent games" not in prompt

    def test_flag_on_failopen_on_load_error(self):
        profile = UserProfile(user_id="u1", rating=1400)
        with patch.object(config, "COACH_GAME_RAG", True), \
             patch.object(gi, "load_recent_insights", side_effect=RuntimeError("db down")):
            prompt = build_system_prompt(soul_content=MOCK_SOUL, user_profile=profile)
        assert "Recent games" not in prompt
        assert "Chess Coach" in prompt
