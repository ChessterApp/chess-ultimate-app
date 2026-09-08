"""Unit tests for the daily digest script (Phase 3, Task 4)."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from scripts import daily_digest as dd


def _sample_events():
    return [
        {"event_type": "turn_end", "surface": "text", "user_id": "u1"},
        {"event_type": "turn_end", "surface": "voice", "user_id": "u2"},
        {
            "event_type": "tool_call",
            "surface": "text",
            "user_id": "u1",
            "tool_name": "analyze_position",
            "ok": True,
            "duration_ms": 50,
        },
        {
            "event_type": "llm_error",
            "surface": "text",
            "user_id": "u1",
            "severity": "error",
            "error_code": "timeout",
        },
        {"event_type": "barge_in", "surface": "voice", "user_id": "u2"},
        {
            "event_type": "session_end",
            "surface": "voice",
            "user_id": "u2",
            "duration_ms": 120000,
        },
        {
            "event_type": "mint_rejected",
            "surface": "voice",
            "user_id": "u2",
            "error_code": "quota_exhausted",
            "severity": "warn",
        },
    ]


@pytest.mark.unit
class TestBuildDigest:
    def _fetch_factory(self, events, tokens=None):
        tokens = tokens or []

        def fake(table, select, filters):
            if table == "token_usage":
                return tokens
            if "tool_name" in filters:  # check_moves rows
                return []
            if filters.get("created_at", "").startswith("lt."):  # prior-window lookup
                return []
            return events

        return fake

    def test_headline_sections_present(self):
        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        tokens = [
            {"model": "gemini-flash", "prompt_tokens": 100, "completion_tokens": 20, "estimated_cost_usd": 0.001},
        ]
        with patch("src.analytics_db._fetch", side_effect=self._fetch_factory(_sample_events(), tokens)):
            out = dd.build_digest(24, now=now)

        assert "# Coach digest — last 24h" in out
        assert "**Turns:** 2 total" in out
        assert "text 1" in out and "voice 1" in out
        assert "**Errors:** 1 total" in out
        assert "llm_error" in out
        assert "analyze_position" in out
        assert "**Barge-ins:** 1" in out
        assert "**Voice:** 1 sessions" in out
        assert "quota_exhausted" in out
        assert "gemini-flash" in out
        assert "**New users:** 2" in out

    def test_empty_window_warnings(self):
        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        with patch("src.analytics_db._fetch", side_effect=self._fetch_factory([], [])):
            out = dd.build_digest(24, now=now)
        assert "**Turns:** 0 total" in out
        assert "**Errors:** none" in out
        assert "no tool calls in window" in out
        assert "no check_moves calls in window" in out
        assert "no token/cost rows in window" in out

    def test_fetch_failure_is_graceful(self):
        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        with patch("src.analytics_db._fetch", side_effect=RuntimeError("db down")):
            out = dd.build_digest(24, now=now)
        assert "analytics fetch failed" in out


@pytest.mark.unit
class TestNewUserCount:
    def test_all_new(self):
        events = [{"user_id": "u1"}, {"user_id": "u2"}]
        with patch("src.analytics_db._fetch", return_value=[]):
            n = dd._new_user_count(2, events, datetime(2026, 9, 8, tzinfo=timezone.utc))
        assert n == 2

    def test_returning_excluded(self):
        events = [{"user_id": "u1"}, {"user_id": "u2"}]
        with patch("src.analytics_db._fetch", return_value=[{"user_id": "u1"}]):
            n = dd._new_user_count(2, events, datetime(2026, 9, 8, tzinfo=timezone.utc))
        assert n == 1

    def test_skips_when_too_many(self):
        events = [{"user_id": f"u{i}"} for i in range(301)]
        n = dd._new_user_count(301, events, datetime(2026, 9, 8, tzinfo=timezone.utc))
        assert n is None

    def test_no_active_users(self):
        assert dd._new_user_count(0, [], datetime(2026, 9, 8, tzinfo=timezone.utc)) == 0


@pytest.mark.unit
class TestMain:
    def test_main_exits_zero(self):
        with patch("scripts.daily_digest.load_env"), patch(
            "scripts.daily_digest.build_digest", return_value="# digest"
        ):
            with patch("sys.argv", ["daily_digest.py", "--hours", "6"]):
                assert dd.main() == 0
