"""Unit tests for get_user_progress tool."""

from unittest.mock import MagicMock, patch

import pytest

from src.tools.user_progress import get_user_progress


def _mock_supabase_get(lesson_data, puzzle_data):
    """Create a mock for _supabase_get that returns different data per table."""
    def mock_get(table, params, url=None, key=None):
        if table == "lesson_progress":
            return lesson_data
        elif table == "puzzle_attempts":
            return puzzle_data
        return []
    return mock_get


@pytest.mark.unit
def test_returns_progress():
    """Returns progress stats for a valid user."""
    lessons = [
        {"course_id": "c1", "completed": True},
        {"course_id": "c1", "completed": True},
        {"course_id": "c2", "completed": False},
    ]
    puzzles = [
        {"solved": True, "solved_at": "2024-05-01T10:00:00"},
        {"solved": True, "solved_at": "2024-05-02T10:00:00"},
        {"solved": False, "solved_at": "2024-05-03T10:00:00"},
    ]

    with patch("src.tools.user_progress._supabase_get", _mock_supabase_get(lessons, puzzles)):
        result = get_user_progress(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert result["courses_completed"] == 1  # Only c1 fully completed
    assert result["lessons_completed"] == 2
    assert result["puzzles_attempted"] == 3
    assert result["puzzles_solved"] == 2
    assert result["accuracy_pct"] == 66.7


@pytest.mark.unit
def test_no_puzzles():
    """Zero puzzles returns 0 accuracy."""
    with patch("src.tools.user_progress._supabase_get", _mock_supabase_get([], [])):
        result = get_user_progress(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    assert result["puzzles_attempted"] == 0
    assert result["accuracy_pct"] == 0
    assert result["current_streak"] == 0


@pytest.mark.unit
def test_no_supabase_config():
    """Missing Supabase config returns error."""
    result = get_user_progress(
        user_id="user123",
        supabase_url="",
        supabase_key="",
    )
    assert "error" in result


@pytest.mark.unit
def test_result_schema():
    """Result has all expected fields."""
    with patch("src.tools.user_progress._supabase_get", _mock_supabase_get([], [])):
        result = get_user_progress(
            user_id="user123",
            supabase_url="https://fake.supabase.co",
            supabase_key="fake-key",
        )

    expected_keys = {
        "user_id", "courses_completed", "lessons_completed",
        "puzzles_attempted", "puzzles_solved", "accuracy_pct", "current_streak",
    }
    assert expected_keys == set(result.keys())
