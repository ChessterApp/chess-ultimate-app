"""Unit tests for cost monitoring module."""

from unittest.mock import patch, MagicMock

import pytest

from src.cost_monitor import CostMonitor, TokenUsageRecord, MODEL_COSTS, DEFAULT_COST


@pytest.mark.unit
class TestTokenUsageRecord:
    """Tests for the TokenUsageRecord model."""

    def test_record_creation(self):
        record = TokenUsageRecord(
            user_id="user1",
            session_id="sess1",
            model="google/gemini-2.5-flash",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_usd=0.001,
        )
        assert record.user_id == "user1"
        assert record.total_tokens == 150
        assert record.timestamp > 0

    def test_record_defaults(self):
        record = TokenUsageRecord(
            user_id="u", session_id="s", model="m"
        )
        assert record.prompt_tokens == 0
        assert record.completion_tokens == 0
        assert record.total_tokens == 0
        assert record.estimated_cost_usd == 0.0
        assert record.surface == "text"


@pytest.mark.unit
class TestCostMonitor:
    """Tests for the CostMonitor class."""

    def test_record_usage_calculates_cost(self):
        monitor = CostMonitor()
        with patch.object(monitor, '_persist'):
            record = monitor.record_usage(
                user_id="user1",
                session_id="sess1",
                model="google/gemini-2.5-flash",
                prompt_tokens=1000,
                completion_tokens=500,
            )
        assert record.total_tokens == 1500
        # Cost = (1000/1000 * 0.00015) + (500/1000 * 0.0006)
        expected = 0.00015 + 0.0003
        assert abs(record.estimated_cost_usd - expected) < 0.0001

    def test_record_usage_unknown_model(self):
        monitor = CostMonitor()
        with patch.object(monitor, '_persist'):
            record = monitor.record_usage(
                user_id="user1",
                session_id="sess1",
                model="unknown/model",
                prompt_tokens=1000,
                completion_tokens=1000,
            )
        expected = (1000 / 1000) * DEFAULT_COST["input"] + (1000 / 1000) * DEFAULT_COST["output"]
        assert abs(record.estimated_cost_usd - expected) < 0.0001

    def test_get_user_usage_empty(self):
        monitor = CostMonitor()
        usage = monitor.get_user_usage("nobody")
        assert usage["user_id"] == "nobody"
        assert usage["total_tokens"] == 0
        assert usage["request_count"] == 0
        assert usage["by_model"] == {}

    def test_get_user_usage_aggregated(self):
        monitor = CostMonitor()
        with patch.object(monitor, '_persist'):
            monitor.record_usage("user1", "s1", "google/gemini-2.5-flash", 100, 50)
            monitor.record_usage("user1", "s1", "google/gemini-2.5-flash", 200, 100)
            monitor.record_usage("user2", "s2", "google/gemini-2.5-flash", 300, 150)

        usage = monitor.get_user_usage("user1")
        assert usage["total_prompt_tokens"] == 300
        assert usage["total_completion_tokens"] == 150
        assert usage["request_count"] == 2
        assert "google/gemini-2.5-flash" in usage["by_model"]
        assert usage["by_model"]["google/gemini-2.5-flash"]["request_count"] == 2

    def test_get_user_usage_multiple_models(self):
        monitor = CostMonitor()
        with patch.object(monitor, '_persist'):
            monitor.record_usage("user1", "s1", "google/gemini-2.5-flash", 100, 50)
            monitor.record_usage("user1", "s1", "anthropic/claude-sonnet-4-5", 100, 50)

        usage = monitor.get_user_usage("user1")
        assert len(usage["by_model"]) == 2
        assert usage["request_count"] == 2

    @patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_persist_skipped_without_supabase(self):
        monitor = CostMonitor()
        # Should not raise even without Supabase
        record = monitor.record_usage("user1", "s1", "m", 10, 5)
        assert record is not None

    @patch("src.cost_monitor.httpx.post")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    def test_persist_calls_supabase(self, mock_post):
        monitor = CostMonitor()
        monitor.record_usage("user1", "s1", "m", 10, 5)
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "token_usage" in call_url

    def test_record_usage_carries_surface(self):
        monitor = CostMonitor()
        with patch.object(monitor, "_persist"):
            record = monitor.record_usage(
                "user1", "s1", "google/gemini-2.5-flash", 10, 5, surface="analysis"
            )
        assert record.surface == "analysis"

    @patch("src.cost_monitor.httpx.post")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    def test_persist_payload_includes_surface(self, mock_post):
        monitor = CostMonitor()
        monitor.record_usage("user1", "s1", "m", 10, 5, surface="review")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["surface"] == "review"

    def test_model_costs_defined(self):
        assert "google/gemini-2.5-flash" in MODEL_COSTS
        assert "anthropic/claude-sonnet-4-5" in MODEL_COSTS
        assert "anthropic/claude-opus-4" in MODEL_COSTS


@pytest.mark.unit
class TestVoiceMetering:
    """Task 1: voice rows carry tool_name/duration_ms and surface='voice'."""

    def test_record_usage_with_voice_fields(self):
        monitor = CostMonitor()
        with patch.object(monitor, "_persist"):
            record = monitor.record_usage(
                user_id="u1",
                session_id="s1",
                model="gemini-live-voice",
                prompt_tokens=0,
                completion_tokens=0,
                surface="voice",
                tool_name="analyze_position",
                duration_ms=42000,
            )
        assert record.surface == "voice"
        assert record.tool_name == "analyze_position"
        assert record.duration_ms == 42000

    def test_persist_omits_voice_fields_when_unset(self):
        monitor = CostMonitor()
        with patch("src.cost_monitor.httpx.post") as mock_post, patch.dict(
            "os.environ",
            {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "k"},
        ):
            monitor.record_usage("u1", "s1", "some-model", 10, 5, surface="text")
        sent = mock_post.call_args.kwargs["json"]
        # Text rows never send the voice-only columns (no schema dependency).
        assert "tool_name" not in sent
        assert "duration_ms" not in sent

    def test_persist_includes_voice_fields_when_set(self):
        monitor = CostMonitor()
        with patch("src.cost_monitor.httpx.post") as mock_post, patch.dict(
            "os.environ",
            {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "k"},
        ):
            monitor.record_usage(
                "u1", "s1", "gemini-live-voice", 0, 0,
                surface="voice", tool_name="board_control", duration_ms=1234,
            )
        sent = mock_post.call_args.kwargs["json"]
        assert sent["surface"] == "voice"
        assert sent["tool_name"] == "board_control"
        assert sent["duration_ms"] == 1234

    def test_record_voice_event_persists_voice_row(self):
        from src import cost_monitor as cm

        captured = {}

        def _fake_record(**kwargs):
            captured.update(kwargs)

        with patch.object(cm.cost_monitor, "record_usage", side_effect=_fake_record):
            t = None
            cm.record_voice_event("u1", "s1", tool_name="analyze_position")
            # Helper runs on a daemon thread; give it a moment to complete.
            import time as _t
            _t.sleep(0.2)
        assert captured.get("surface") == "voice"
        assert captured.get("tool_name") == "analyze_position"
        assert captured.get("model") == cm.VOICE_MODEL
