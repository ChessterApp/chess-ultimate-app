"""Unit tests for training_recommender tool."""

from unittest.mock import patch

import pytest

from src.tools.training_recommender import training_recommender


@pytest.mark.unit
def test_with_weaknesses():
    """Returns targeted recommendations for detected weaknesses."""
    weaknesses = [
        {"category": "opening_theory", "description": "Losses in opening", "frequency": 5},
        {"category": "endgame", "description": "Losses in endgame", "frequency": 3},
    ]
    result = training_recommender(user_id="user123", _weaknesses=weaknesses)

    assert result["user_id"] == "user123"
    assert len(result["recommendations"]) >= 2
    categories = {r["weakness_addressed"] for r in result["recommendations"]}
    assert "opening_theory" in categories
    assert "endgame" in categories


@pytest.mark.unit
def test_no_weaknesses():
    """No weaknesses returns default recommendations."""
    result = training_recommender(user_id="user123", _weaknesses=[])

    assert len(result["recommendations"]) >= 1
    assert any(r["weakness_addressed"] == "general" for r in result["recommendations"])


@pytest.mark.unit
def test_recommendation_fields():
    """Each recommendation has expected fields."""
    weaknesses = [{"category": "tactics", "frequency": 3}]
    result = training_recommender(user_id="user123", _weaknesses=weaknesses)

    for rec in result["recommendations"]:
        assert "type" in rec
        assert "title" in rec
        assert "description" in rec
        assert "priority" in rec
        assert "weakness_addressed" in rec


@pytest.mark.unit
def test_recommendation_types():
    """Recommendations include valid types."""
    weaknesses = [{"category": "tactics", "frequency": 3}]
    result = training_recommender(user_id="user123", _weaknesses=weaknesses)

    valid_types = {"puzzle", "course", "practice"}
    for rec in result["recommendations"]:
        assert rec["type"] in valid_types


@pytest.mark.unit
def test_no_duplicate_titles():
    """No duplicate recommendation titles."""
    weaknesses = [
        {"category": "opening_theory", "frequency": 5},
        {"category": "opening_theory", "frequency": 3},
    ]
    result = training_recommender(user_id="user123", _weaknesses=weaknesses)

    titles = [r["title"] for r in result["recommendations"]]
    assert len(titles) == len(set(titles))


@pytest.mark.unit
def test_fetches_from_supabase():
    """Falls back to Supabase when no _weaknesses provided."""
    mock_profile = [{"weaknesses": [{"category": "tactics", "frequency": 2}]}]

    with patch("src.tools.training_recommender.httpx.get") as mock_get:
        mock_resp = mock_get.return_value
        mock_resp.json.return_value = mock_profile
        mock_resp.raise_for_status = lambda: None

        result = training_recommender(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert len(result["recommendations"]) >= 1
