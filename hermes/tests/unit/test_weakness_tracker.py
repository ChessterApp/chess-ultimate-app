"""Unit tests for weakness_tracker tool."""

from unittest.mock import MagicMock, patch

import pytest

from src.tools.weakness_tracker import weakness_tracker, _analyze_game_patterns


SAMPLE_GAMES_MIXED = [
    {"id": 1, "user_id": "user123", "white": "user123", "black": "opp1",
     "result": "1-0", "played_at": "2024-05-01", "eco": "C50",
     "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. d3 Bc5 5. O-O d6 1-0"},
    {"id": 2, "user_id": "user123", "white": "opp2", "black": "user123",
     "result": "1-0", "played_at": "2024-04-28", "eco": "B90",
     "pgn": "1. e4 c5 2. Nf3 d6 1-0"},
    {"id": 3, "user_id": "user123", "white": "user123", "black": "opp3",
     "result": "1-0", "played_at": "2024-04-25", "eco": "C50",
     "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 1-0"},
    {"id": 4, "user_id": "user123", "white": "opp4", "black": "user123",
     "result": "1-0", "played_at": "2024-04-22", "eco": "C50",
     "pgn": "1. e4 e5 2. Nf3 1-0"},
    {"id": 5, "user_id": "user123", "white": "user123", "black": "opp5",
     "result": "1-0", "played_at": "2024-04-20", "eco": "C50",
     "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. d3 d6 5. O-O Nf6 1-0"},
]


@pytest.mark.unit
def test_analyze_patterns():
    """Analyzes game patterns and returns weaknesses/strengths."""
    result = _analyze_game_patterns(SAMPLE_GAMES_MIXED, "user123")
    assert "weaknesses" in result
    assert "strengths" in result
    assert isinstance(result["weaknesses"], list)
    assert isinstance(result["strengths"], list)


@pytest.mark.unit
def test_narrow_repertoire_detected():
    """Using only 1-2 openings in 5+ games flags narrow repertoire."""
    games = [
        {"id": i, "user_id": "u1", "white": "u1", "black": f"opp{i}",
         "result": "1-0", "eco": "C50", "pgn": "1. e4 e5 1-0"}
        for i in range(6)
    ]
    result = _analyze_game_patterns(games, "u1")
    categories = [w["category"] for w in result["weaknesses"]]
    assert "opening_theory" in categories


@pytest.mark.unit
def test_no_games():
    """No games returns empty analysis."""
    with patch("src.tools.weakness_tracker.get_user_games", return_value=[]):
        result = weakness_tracker(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert result["games_analyzed"] == 0
    assert result["weaknesses"] == []
    assert result["strengths"] == []


@pytest.mark.unit
def test_with_games():
    """Returns analysis when games are available."""
    with patch("src.tools.weakness_tracker.get_user_games", return_value=SAMPLE_GAMES_MIXED):
        with patch("src.tools.weakness_tracker._update_profile_weaknesses"):
            result = weakness_tracker(
                user_id="user123",
                supabase_url="https://fake.supabase.co",
                supabase_key="fake-key",
            )

    assert result["games_analyzed"] == 5
    assert "weaknesses" in result
    assert "strengths" in result


@pytest.mark.unit
def test_result_schema():
    """Result has all expected fields."""
    with patch("src.tools.weakness_tracker.get_user_games", return_value=[]):
        result = weakness_tracker(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert "user_id" in result
    assert "games_analyzed" in result
    assert "weaknesses" in result
    assert "strengths" in result
