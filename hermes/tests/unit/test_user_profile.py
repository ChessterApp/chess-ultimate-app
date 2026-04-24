"""Unit tests for user chess profile."""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.user_profile import UserProfile, load_user_profile


@pytest.mark.unit
class TestUserProfile:
    def test_default_profile(self):
        profile = UserProfile(user_id="user1")
        assert profile.rating == 1200
        assert profile.goals == []
        assert profile.preferred_openings == []
        assert profile.weaknesses == []
        assert profile.style == "unknown"

    def test_profile_with_data(self):
        profile = UserProfile(
            user_id="user1",
            rating=1800,
            goals=["Reach 2000", "Improve endgame"],
            preferred_openings=["Sicilian Najdorf", "Queen's Gambit"],
            weaknesses=["Time management", "Endgames"],
            style="aggressive",
        )
        assert profile.rating == 1800
        assert len(profile.goals) == 2
        assert profile.style == "aggressive"

    def test_to_prompt_context(self):
        profile = UserProfile(
            user_id="user1",
            rating=1600,
            goals=["Improve tactics"],
            preferred_openings=["Italian Game"],
            weaknesses=["Calculation"],
            style="positional",
        )
        ctx = profile.to_prompt_context()
        assert "1600" in ctx
        assert "Improve tactics" in ctx
        assert "Italian Game" in ctx
        assert "Calculation" in ctx
        assert "positional" in ctx

    def test_to_prompt_context_minimal(self):
        profile = UserProfile(user_id="user1")
        ctx = profile.to_prompt_context()
        assert "1200" in ctx
        assert "Goals" not in ctx  # No goals set


@pytest.mark.unit
class TestLoadUserProfile:
    def test_load_returns_default_without_supabase(self):
        """Without Supabase config, returns default profile."""
        profile = load_user_profile("user1", supabase_url="", supabase_key="")
        assert profile.user_id == "user1"
        assert profile.rating == 1200

    def test_load_from_supabase(self):
        """Loads profile data from Supabase response."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "rating": 1900,
                "goals": ["GM norm"],
                "preferred_openings": ["KID"],
                "weaknesses": ["Rook endgames"],
                "style": "tactical",
            }
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch("src.user_profile.httpx.get", return_value=mock_resp):
            profile = load_user_profile(
                "user1",
                supabase_url="https://test.supabase.co",
                supabase_key="test-key",
            )
        assert profile.rating == 1900
        assert profile.style == "tactical"

    def test_load_handles_empty_result(self):
        """Returns default profile when Supabase returns empty."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with patch("src.user_profile.httpx.get", return_value=mock_resp):
            profile = load_user_profile(
                "user1",
                supabase_url="https://test.supabase.co",
                supabase_key="test-key",
            )
        assert profile.user_id == "user1"
        assert profile.rating == 1200

    def test_load_handles_network_error(self):
        """Returns default profile on network failure."""
        with patch("src.user_profile.httpx.get", side_effect=Exception("timeout")):
            profile = load_user_profile(
                "user1",
                supabase_url="https://test.supabase.co",
                supabase_key="test-key",
            )
        assert profile.user_id == "user1"
        assert profile.rating == 1200
