"""Unit tests for usage analytics tracking."""

import time
from unittest.mock import patch, MagicMock

import pytest

from src.analytics import AnalyticsTracker, AnalyticsEvent


@pytest.mark.unit
class TestAnalyticsEvent:
    """Tests for the AnalyticsEvent model."""

    def test_event_creation(self):
        event = AnalyticsEvent(
            user_id="u1",
            event_type="tool_invocation",
            tool_name="analyze_position",
        )
        assert event.user_id == "u1"
        assert event.event_type == "tool_invocation"
        assert event.timestamp > 0

    def test_event_defaults(self):
        event = AnalyticsEvent(user_id="u1", event_type="chat")
        assert event.tool_name is None
        assert event.session_id is None
        assert event.metadata == {}


@pytest.mark.unit
class TestAnalyticsTracker:
    """Tests for the AnalyticsTracker class."""

    def test_track_tool_invocation(self):
        tracker = AnalyticsTracker()
        with patch.object(tracker, '_persist'):
            tracker.track_tool_invocation("u1", "analyze_position", "s1")
        analytics = tracker.get_analytics("u1")
        assert analytics["tool_invocations"]["analyze_position"] == 1

    def test_track_multiple_tools(self):
        tracker = AnalyticsTracker()
        with patch.object(tracker, '_persist'):
            tracker.track_tool_invocation("u1", "analyze_position")
            tracker.track_tool_invocation("u1", "analyze_position")
            tracker.track_tool_invocation("u1", "get_openings")

        analytics = tracker.get_analytics("u1")
        assert analytics["tool_invocations"]["analyze_position"] == 2
        assert analytics["tool_invocations"]["get_openings"] == 1
        assert analytics["popular_tools"][0] == "analyze_position"

    def test_track_session(self):
        tracker = AnalyticsTracker()
        with patch.object(tracker, '_persist'):
            tracker.track_session_start("u1", "s1")
            time.sleep(0.1)
            tracker.track_session_end("u1", "s1")

        analytics = tracker.get_analytics("u1")
        assert analytics["total_sessions"] == 1
        assert analytics["avg_session_duration_seconds"] > 0

    def test_track_chat(self):
        tracker = AnalyticsTracker()
        with patch.object(tracker, '_persist'):
            tracker.track_chat("u1", "s1")
            tracker.track_chat("u1", "s1")

        analytics = tracker.get_analytics("u1")
        assert analytics["event_breakdown"]["chat"] == 2

    def test_global_analytics(self):
        tracker = AnalyticsTracker()
        with patch.object(tracker, '_persist'):
            tracker.track_chat("u1")
            tracker.track_chat("u2")
            tracker.track_tool_invocation("u1", "stockfish")

        analytics = tracker.get_analytics()
        assert analytics["unique_users"] == 2
        assert analytics["total_events"] == 3

    def test_user_filtered_analytics(self):
        tracker = AnalyticsTracker()
        with patch.object(tracker, '_persist'):
            tracker.track_chat("u1")
            tracker.track_chat("u2")

        analytics = tracker.get_analytics("u1")
        assert analytics["unique_users"] == 1
        assert analytics["total_events"] == 1

    def test_empty_analytics(self):
        tracker = AnalyticsTracker()
        analytics = tracker.get_analytics()
        assert analytics["total_events"] == 0
        assert analytics["unique_users"] == 0
        assert analytics["tool_invocations"] == {}
        assert analytics["popular_tools"] == []
        assert analytics["avg_session_duration_seconds"] == 0

    @patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_persist_skipped_without_supabase(self):
        tracker = AnalyticsTracker()
        # Should not raise
        tracker.track_chat("u1")

    @patch("src.analytics.httpx.post")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    def test_persist_calls_supabase(self, mock_post):
        tracker = AnalyticsTracker()
        tracker.track_chat("u1")
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "analytics_events" in call_url
