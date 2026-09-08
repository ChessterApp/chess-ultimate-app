"""Unit tests for the DB-backed coach analytics aggregation (Phase 3)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src import analytics_db as adb


@pytest.mark.unit
class TestPercentile:
    def test_empty(self):
        assert adb._percentile([], 50) == 0

    def test_p50_p90(self):
        vals = list(range(1, 101))  # 1..100
        assert adb._percentile(vals, 50) == 50 or adb._percentile(vals, 50) == 51
        assert adb._percentile(vals, 90) >= 90

    def test_single(self):
        assert adb._percentile([42], 90) == 42


@pytest.mark.unit
class TestAggregateEvents:
    def _events(self):
        return [
            {"event_type": "turn_end", "surface": "text", "user_id": "u1"},
            {"event_type": "turn_end", "surface": "text", "user_id": "u2"},
            {"event_type": "turn_end", "surface": "voice", "user_id": "u1"},
            {
                "event_type": "tool_call",
                "surface": "text",
                "user_id": "u1",
                "tool_name": "check_moves",
                "ok": True,
                "duration_ms": 100,
            },
            {
                "event_type": "tool_call",
                "surface": "text",
                "user_id": "u2",
                "tool_name": "check_moves",
                "ok": False,
                "duration_ms": 300,
                "severity": "warn",
            },
            {
                "event_type": "llm_error",
                "surface": "text",
                "user_id": "u1",
                "severity": "error",
                "error_code": "timeout",
            },
            {"event_type": "barge_in", "surface": "voice", "user_id": "u1"},
            {"event_type": "barge_in", "surface": "voice", "user_id": "u2"},
            {
                "event_type": "session_end",
                "surface": "voice",
                "user_id": "u1",
                "duration_ms": 60000,
            },
            {
                "event_type": "mint_rejected",
                "surface": "voice",
                "user_id": "u2",
                "error_code": "quota_exhausted",
                "severity": "warn",
            },
        ]

    def test_turn_counts_by_surface(self):
        agg = adb.aggregate_events(self._events(), [], [])
        assert agg["turn_counts_by_surface"] == {"text": 2, "voice": 1}

    def test_tools_success_rate_and_percentiles(self):
        agg = adb.aggregate_events(self._events(), [], [])
        cm = agg["tools"]["check_moves"]
        assert cm["calls"] == 2
        assert cm["success_rate"] == 0.5
        assert cm["p50_ms"] in (100, 300)
        assert cm["p90_ms"] == 300

    def test_error_counts(self):
        agg = adb.aggregate_events(self._events(), [], [])
        assert agg["error_counts"]["by_event_type"]["llm_error"] == 1
        assert agg["error_counts"]["by_error_code"]["timeout"] == 1

    def test_barge_in_and_voice_sessions(self):
        agg = adb.aggregate_events(self._events(), [], [])
        assert agg["barge_in_count"] == 2
        assert agg["voice_sessions"]["count"] == 1
        assert agg["voice_sessions"]["avg_duration_ms"] == 60000

    def test_mint_rejections_and_active_users(self):
        agg = adb.aggregate_events(self._events(), [], [])
        assert agg["mint_rejections_by_reason"] == {"quota_exhausted": 1}
        assert agg["active_users"] == 2

    def test_illegal_move_rate(self):
        check_rows = [
            {"payload": {"check_moves_verdict": {"candidates": 2, "legal": 2, "illegal": 0}}},
            {"payload": {"check_moves_verdict": {"candidates": 2, "legal": 1, "illegal": 1}}},
            {"payload": {"check_moves_verdict": {"candidates": 3, "legal": 0, "illegal": 3}}},
        ]
        agg = adb.aggregate_events([], check_rows, [])
        imr = agg["illegal_move_rate"]
        assert imr["total_check_moves"] == 3
        assert imr["illegal_calls"] == 2
        assert imr["rate"] == round(2 / 3, 4)

    def test_tokens_by_model(self):
        token_rows = [
            {"model": "gemini-flash", "prompt_tokens": 100, "completion_tokens": 50, "estimated_cost_usd": 0.001},
            {"model": "gemini-flash", "prompt_tokens": 200, "completion_tokens": 20, "estimated_cost_usd": 0.002},
            {"model": "gpt-4", "prompt_tokens": 10, "completion_tokens": 5, "estimated_cost_usd": 0.01},
        ]
        agg = adb.aggregate_events([], [], token_rows)
        tbm = agg["tokens_by_model"]
        assert tbm["gemini-flash"]["prompt_tokens"] == 300
        assert tbm["gemini-flash"]["completion_tokens"] == 70
        assert tbm["gemini-flash"]["cost_usd"] == 0.003
        assert tbm["gpt-4"]["rows"] == 1

    def test_user_scope_hides_admin_fields(self):
        agg = adb.aggregate_events(self._events(), [], [], user_scope=True)
        assert "active_users" not in agg
        assert "tokens_by_model" not in agg
        assert "error_counts" not in agg
        assert "turn_counts_by_surface" in agg
        assert "tools" in agg

    def test_empty(self):
        agg = adb.aggregate_events([], [], [])
        assert agg["turn_counts_by_surface"] == {}
        assert agg["tools"] == {}
        assert agg["illegal_move_rate"]["rate"] == 0.0
        assert agg["barge_in_count"] == 0


@pytest.mark.unit
class TestFetch:
    @patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_no_supabase_returns_empty(self):
        assert adb._fetch("coach_events", "id", {}) == []

    @patch("src.analytics_db.httpx.get")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://x.co", "SUPABASE_SERVICE_KEY": "k"})
    def test_single_page(self, mock_get):
        resp = mock_get.return_value
        resp.raise_for_status.return_value = None
        resp.json.return_value = [{"id": 1}, {"id": 2}]
        rows = adb._fetch("coach_events", "id", {"created_at": "gte.x"})
        assert rows == [{"id": 1}, {"id": 2}]
        assert mock_get.call_count == 1

    @patch("src.analytics_db.httpx.get")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://x.co", "SUPABASE_SERVICE_KEY": "k"})
    def test_paginates_until_short_page(self, mock_get):
        full_page = [{"id": i} for i in range(adb._PAGE_SIZE)]
        short_page = [{"id": 9999}]
        responses = []
        for batch in (full_page, short_page):
            r = type("R", (), {})()
            r.raise_for_status = lambda: None
            r.json = lambda b=batch: b
            responses.append(r)
        mock_get.side_effect = responses
        rows = adb._fetch("coach_events", "id", {})
        assert len(rows) == adb._PAGE_SIZE + 1
        assert mock_get.call_count == 2

    @patch("src.analytics_db.httpx.get", side_effect=RuntimeError("boom"))
    @patch.dict("os.environ", {"SUPABASE_URL": "https://x.co", "SUPABASE_SERVICE_KEY": "k"})
    def test_error_is_swallowed(self, mock_get):
        assert adb._fetch("coach_events", "id", {}) == []


@pytest.mark.unit
class TestComputeOrchestration:
    @patch("src.analytics_db._fetch")
    def test_admin_windows(self, mock_fetch):
        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        recent = (now - timedelta(hours=1)).isoformat()
        old = (now - timedelta(days=3)).isoformat()

        def fake(table, select, filters):
            if table == "token_usage":
                return []
            if "tool_name" in filters:
                return []
            return [
                {"event_type": "turn_end", "surface": "text", "user_id": "u1", "created_at": recent},
                {"event_type": "turn_end", "surface": "text", "user_id": "u1", "created_at": old},
            ]

        mock_fetch.side_effect = fake
        res = adb.compute_admin_analytics(now=now)
        assert res["scope"] == "admin"
        # 7d window sees both turns; 24h window sees only the recent one.
        assert res["windows"]["7d"]["turn_counts_by_surface"]["text"] == 2
        assert res["windows"]["24h"]["turn_counts_by_surface"]["text"] == 1

    @patch("src.analytics_db._fetch")
    def test_user_scope(self, mock_fetch):
        def fake(table, select, filters):
            if table == "voice_usage":
                return [{"seconds": 90}, {"seconds": 30}]
            if "tool_name" in filters:
                return []
            return [{"event_type": "turn_end", "surface": "voice", "user_id": "u1"}]

        mock_fetch.side_effect = fake
        res = adb.compute_user_analytics("u1")
        assert res["scope"] == "user"
        assert res["turn_counts_by_surface"]["voice"] == 1
        assert res["voice_minutes_used"] == 2.0  # 120s -> 2 min
        assert "tokens_by_model" not in res


@pytest.mark.unit
class TestAdminCache:
    def test_memoises_within_ttl(self):
        cache = adb._AdminCache(ttl_s=60)
        calls = {"n": 0}

        def fake_compute():
            calls["n"] += 1
            return {"scope": "admin", "n": calls["n"]}

        with patch("src.analytics_db.compute_admin_analytics", side_effect=fake_compute):
            first = cache.get()
            second = cache.get()
        assert calls["n"] == 1
        assert first["cached"] is False
        assert second["cached"] is True

    def test_clear_forces_recompute(self):
        cache = adb._AdminCache(ttl_s=60)
        with patch("src.analytics_db.compute_admin_analytics", return_value={"scope": "admin"}):
            cache.get()
            cache.clear()
            result = cache.get()
        assert result["cached"] is False
