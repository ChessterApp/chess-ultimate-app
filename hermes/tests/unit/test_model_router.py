"""Unit tests for model router."""

import pytest

from src.model_router import route_model

TIERS = {
    "fast": "google/gemini-2.5-flash",
    "analysis": "anthropic/claude-sonnet-4-5",
    "deep": "anthropic/claude-opus-4",
}
DEFAULT = "google/gemini-2.5-flash"


@pytest.mark.unit
class TestModelRouter:
    def test_simple_question_routes_fast(self):
        result = route_model("What is the Italian Game?", TIERS, DEFAULT)
        assert result == TIERS["fast"]

    def test_analysis_keyword_routes_analysis(self):
        result = route_model("Analyze this position for me", TIERS, DEFAULT)
        assert result == TIERS["analysis"]

    def test_evaluate_routes_analysis(self):
        result = route_model("Can you evaluate my last move?", TIERS, DEFAULT)
        assert result == TIERS["analysis"]

    def test_deep_keyword_routes_deep(self):
        result = route_model("I need a deep analysis of my pawn structure", TIERS, DEFAULT)
        assert result == TIERS["deep"]

    def test_game_review_routes_deep(self):
        result = route_model("Can you do a game review of this PGN?", TIERS, DEFAULT)
        assert result == TIERS["deep"]

    def test_empty_query_returns_default(self):
        result = route_model("", TIERS, DEFAULT)
        assert result == DEFAULT

    def test_empty_tiers_returns_default(self):
        result = route_model("Analyze this", {}, DEFAULT)
        assert result == DEFAULT
