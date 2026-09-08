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

    def test_board_keyword_russian_routes_analysis(self):
        result = route_model("покажи связку на доске", TIERS, DEFAULT)
        assert result == TIERS["analysis"]

    def test_board_keyword_english_routes_analysis(self):
        result = route_model("show me a pin on the board", TIERS, DEFAULT)
        assert result == TIERS["analysis"]

    def test_no_board_keyword_stays_fast(self):
        result = route_model("what is a pin?", TIERS, DEFAULT)
        assert result == TIERS["fast"]

    def test_analysis_keyword_still_works(self):
        result = route_model("analyze this position", TIERS, DEFAULT)
        assert result == TIERS["analysis"]

    def test_deep_takes_priority_over_board(self):
        result = route_model("deep analysis, show me on the board", TIERS, DEFAULT)
        assert result == TIERS["deep"]


@pytest.mark.unit
class TestExplainRoute:
    """explain_route exposes the tier + matched keyword for telemetry."""

    def test_fast_tier_reason(self):
        from src.model_router import explain_route
        out = explain_route("what is a pin?", TIERS, DEFAULT)
        assert out["model"] == TIERS["fast"]
        assert out["tier"] == "fast"
        assert out["reason"] == "default_fast"
        assert out["matched"] is None

    def test_analysis_tier_reports_matched_keyword(self):
        from src.model_router import explain_route
        out = explain_route("analyze this position", TIERS, DEFAULT)
        assert out["tier"] == "analysis"
        assert out["reason"] == "analysis_keyword"
        assert out["matched"]

    def test_deep_tier_reports_matched_keyword(self):
        from src.model_router import explain_route
        out = explain_route("please do a game review", TIERS, DEFAULT)
        assert out["tier"] == "deep"
        assert out["reason"] == "deep_keyword"
        assert out["matched"]

    def test_empty_query_default_reason(self):
        from src.model_router import explain_route
        out = explain_route("", TIERS, DEFAULT)
        assert out["tier"] == "default"
        assert out["reason"] == "no_query_or_tiers"

    def test_route_model_matches_explain_route_model(self):
        from src.model_router import explain_route
        for q in ["hi", "analyze this", "deep analysis", "show me on the board"]:
            assert route_model(q, TIERS, DEFAULT) == explain_route(q, TIERS, DEFAULT)["model"]
