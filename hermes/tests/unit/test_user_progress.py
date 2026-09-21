"""Unit tests for get_user_progress (user_progress + user_puzzle_progress)."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from src.tools.user_progress import get_user_progress

URL = "https://fake.supabase.co"
KEY = "fake-key"


def _routed(lesson_rows, puzzle_rows):
    calls = []

    def fake_query(table, params, url=None, key=None):
        calls.append((table, params))
        return {"user_progress": lesson_rows, "user_puzzle_progress": puzzle_rows}[table]

    fake_query.calls = calls
    return fake_query


def _day(offset):
    return (date.today() - timedelta(days=offset)).isoformat() + "T12:00:00+00:00"


LESSONS = [
    {"lesson_id": "l1", "status": "completed", "score": 80, "attempts": 1,
     "time_spent_seconds": 300, "completed_at": _day(1), "updated_at": _day(1),
     "lessons": {"title": "Pins", "title_ru": "Связки", "lesson_type": "theory", "module_id": "m1"}},
    {"lesson_id": "l2", "status": "completed", "score": 100, "attempts": 2,
     "time_spent_seconds": 200, "completed_at": _day(2), "updated_at": _day(2),
     "lessons": {"title": "Forks", "title_ru": None, "lesson_type": "exercise", "module_id": "m1"}},
    {"lesson_id": "l3", "status": "in_progress", "score": None, "attempts": 0,
     "time_spent_seconds": 10, "completed_at": None, "updated_at": _day(0), "lessons": None},
]
PUZZLES = [
    {"puzzle_id": "p1", "completed_at": _day(0), "attempts": 1},
    {"puzzle_id": "p2", "completed_at": _day(1), "attempts": 3},
    {"puzzle_id": "p3", "completed_at": None, "attempts": 2},
]


@pytest.mark.unit
def test_reads_real_tables():
    fake = _routed(LESSONS, PUZZLES)
    with patch("src.tools.user_progress._supabase_query", fake):
        get_user_progress("user123", supabase_url=URL, supabase_key=KEY)
    assert [t for t, _ in fake.calls] == ["user_progress", "user_puzzle_progress"]
    assert fake.calls[0][1]["user_id"] == "eq.user123"
    assert "lessons(" in fake.calls[0][1]["select"]


@pytest.mark.unit
def test_counts_and_streak():
    with patch("src.tools.user_progress._supabase_query", _routed(LESSONS, PUZZLES)):
        out = get_user_progress("user123", supabase_url=URL, supabase_key=KEY)

    assert out["lessons_started"] == 3
    assert out["lessons_completed"] == 2
    assert out["lessons_in_progress"] == 1
    assert out["avg_lesson_score"] == 90.0
    assert out["puzzles_attempted"] == 3
    assert out["puzzles_solved"] == 2
    assert out["puzzle_attempts_total"] == 6
    assert out["solve_rate_pct"] == 33.3
    assert out["current_streak"] == 2  # today + yesterday


@pytest.mark.unit
def test_recent_lessons_prefer_russian_title():
    with patch("src.tools.user_progress._supabase_query", _routed(LESSONS, PUZZLES)):
        out = get_user_progress("user123", supabase_url=URL, supabase_key=KEY)
    titles = [l["title"] for l in out["recent_lessons"]]
    assert titles == ["Связки", "Forks", None]


@pytest.mark.unit
def test_no_puzzles():
    with patch("src.tools.user_progress._supabase_query", _routed([], [])):
        out = get_user_progress("user123", supabase_url=URL, supabase_key=KEY)
    assert out["puzzles_solved"] == 0
    assert out["solve_rate_pct"] == 0.0
    assert out["current_streak"] == 0
    assert out["avg_lesson_score"] is None


@pytest.mark.unit
def test_stale_streak_is_zero():
    old = [{"puzzle_id": "p1", "completed_at": _day(5), "attempts": 1}]
    with patch("src.tools.user_progress._supabase_query", _routed([], old)):
        out = get_user_progress("user123", supabase_url=URL, supabase_key=KEY)
    assert out["current_streak"] == 0


@pytest.mark.unit
def test_failure_is_error_not_zero_progress():
    with patch("src.tools.user_progress._supabase_query", lambda *a, **k: None):
        out = get_user_progress("user123", supabase_url=URL, supabase_key=KEY)
    assert "error" in out
