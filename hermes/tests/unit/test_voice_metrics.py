"""Unit tests for the voice-latency metrics ingest (Phase 4.5, Task 2).

Covers the sanitiser (src/voice_metrics.py) and the POST /api/coach/metrics
endpoint: a valid beacon writes one JSONL line and returns 204, and garbage
input never produces a 5xx.
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src import voice_metrics
from src.server import app
from src.voice_metrics import beacon_to_event, record_metric, sanitize_metric

USER_HEADERS = {"X-User-Id": "test-user-123"}


@pytest.fixture(autouse=True)
def _tmp_metrics_dir(tmp_path, monkeypatch):
    """Redirect metric writes to a throwaway directory."""
    monkeypatch.setattr(voice_metrics, "METRICS_DIR", str(tmp_path))
    yield tmp_path


def _read_lines(tmp_path):
    files = list(tmp_path.glob("voice-latency-*.jsonl"))
    if not files:
        return []
    return [json.loads(line) for line in files[0].read_text().splitlines() if line]


@pytest.mark.unit
class TestSanitize:
    def test_drops_non_dict(self):
        assert sanitize_metric(None) is None
        assert sanitize_metric("nope") is None
        assert sanitize_metric([1, 2]) is None

    def test_requires_session_id(self):
        assert sanitize_metric({"event": "connect"}) is None

    def test_requires_valid_event(self):
        assert sanitize_metric({"sessionId": "s1"}) is None
        assert sanitize_metric({"sessionId": "s1", "event": "bogus"}) is None

    def test_clamps_and_keeps_good_fields(self):
        rec = sanitize_metric(
            {
                "sessionId": "s1",
                "event": "tool",
                "turn": 3,
                "ttfa_ms": 812,
                "tool_name": "analyze_position",
                "tool_ms": 5000,
                "prompt_bytes": 1200,
                "ts": 1700000000,
            }
        )
        assert rec["sessionId"] == "s1"
        assert rec["event"] == "tool"
        assert rec["turn"] == 3
        assert rec["ttfa_ms"] == 812
        assert rec["tool_name"] == "analyze_position"
        assert rec["ts"] == 1700000000

    def test_drops_bad_numeric_fields_but_keeps_record(self):
        rec = sanitize_metric(
            {"sessionId": "s1", "event": "turn", "ttfa_ms": "fast", "turn": True}
        )
        assert rec is not None
        assert "ttfa_ms" not in rec  # non-numeric dropped
        assert "turn" not in rec  # bool is not a valid int
        assert "ts" in rec  # server-stamped when missing

    def test_ms_clamped_to_ceiling(self):
        rec = sanitize_metric({"sessionId": "s1", "event": "tool", "tool_ms": 10**9})
        assert rec["tool_ms"] == voice_metrics._MS_MAX


@pytest.mark.unit
class TestRecordMetric:
    def test_writes_one_line(self, _tmp_metrics_dir):
        assert record_metric({"sessionId": "s1", "event": "connect"}) is True
        lines = _read_lines(_tmp_metrics_dir)
        assert len(lines) == 1
        assert lines[0]["sessionId"] == "s1"

    def test_appends(self, _tmp_metrics_dir):
        record_metric({"sessionId": "s1", "event": "connect"})
        record_metric({"sessionId": "s1", "event": "turn"})
        assert len(_read_lines(_tmp_metrics_dir)) == 2

    def test_drops_bad_payload(self, _tmp_metrics_dir):
        assert record_metric({"nope": 1}) is False
        assert _read_lines(_tmp_metrics_dir) == []


@pytest.mark.unit
class TestMetricsEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_valid_beacon_returns_204_and_writes(self, _tmp_metrics_dir):
        resp = self.client.post(
            "/api/coach/metrics",
            headers=USER_HEADERS,
            json={"sessionId": "s1", "event": "turn", "ttfa_ms": 700},
        )
        assert resp.status_code == 204
        lines = _read_lines(_tmp_metrics_dir)
        assert len(lines) == 1
        assert lines[0]["ttfa_ms"] == 700

    def test_garbage_body_no_5xx(self, _tmp_metrics_dir):
        resp = self.client.post(
            "/api/coach/metrics",
            headers=USER_HEADERS,
            content=b"}{ not json at all",
        )
        assert resp.status_code == 204
        assert _read_lines(_tmp_metrics_dir) == []

    def test_missing_required_fields_no_5xx(self, _tmp_metrics_dir):
        resp = self.client.post(
            "/api/coach/metrics",
            headers=USER_HEADERS,
            json={"event": "connect"},  # no sessionId -> dropped
        )
        assert resp.status_code == 204
        assert _read_lines(_tmp_metrics_dir) == []

    def test_oversized_body_dropped_no_5xx(self, _tmp_metrics_dir):
        big = {"sessionId": "s1", "event": "turn", "pad": "x" * 5000}
        resp = self.client.post(
            "/api/coach/metrics", headers=USER_HEADERS, json=big
        )
        assert resp.status_code == 204
        assert _read_lines(_tmp_metrics_dir) == []


@pytest.mark.unit
class TestSessionEndEvent:
    """Task 1: the 'end' lifecycle event + session_ms are accepted and clamped."""

    def test_end_event_accepted_with_session_ms(self):
        record = sanitize_metric(
            {"sessionId": "s1", "event": "end", "session_ms": 42000}
        )
        assert record is not None
        assert record["event"] == "end"
        assert record["session_ms"] == 42000

    def test_session_ms_clamped_to_ceiling(self):
        record = sanitize_metric(
            {"sessionId": "s1", "event": "end", "session_ms": 9_999_999_999}
        )
        assert record is not None
        assert record["session_ms"] == 3_600_000  # 1h ceiling

    def test_end_event_written_to_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.setattr(voice_metrics, "METRICS_DIR", str(tmp_path))
        assert record_metric(
            {"sessionId": "s1", "event": "end", "session_ms": 5000}
        ) is True
        files = list(tmp_path.glob("voice-latency-*.jsonl"))
        assert files
        line = json.loads(files[0].read_text().strip())
        assert line["event"] == "end"
        assert line["session_ms"] == 5000

    def test_negative_session_ms_clamped_to_zero(self):
        record = sanitize_metric({"sessionId": "s1", "event": "end", "session_ms": -5})
        assert record["session_ms"] == 0


@pytest.mark.unit
class TestSanitizePhase2Fields:
    """Task 1: the sanitizer keeps error cause + correlation fields; drops junk."""

    def test_error_cause_retained(self):
        rec = sanitize_metric(
            {"sessionId": "s1", "event": "error", "error": "NotAllowedError: mic blocked"}
        )
        assert rec is not None
        assert rec["error"] == "NotAllowedError: mic blocked"

    def test_error_cause_truncated_to_500(self):
        rec = sanitize_metric(
            {"sessionId": "s1", "event": "error", "error": "x" * 5000}
        )
        assert len(rec["error"]) == 500

    def test_keeps_turn_id_ok_and_error_code(self):
        rec = sanitize_metric(
            {
                "sessionId": "s1",
                "event": "tool",
                "turn_id": "t-abc",
                "ok": False,
                "error_code": "http_429",
                "tool_name": "analyze_position",
            }
        )
        assert rec["turn_id"] == "t-abc"
        assert rec["ok"] is False
        assert rec["error_code"] == "http_429"

    def test_new_events_are_valid(self):
        for event in ("reconnect", "tool_timeout", "barge_in", "session_end", "drop"):
            rec = sanitize_metric({"sessionId": "s1", "event": event})
            assert rec is not None, event
            assert rec["event"] == event

    def test_unknown_fields_still_dropped(self):
        rec = sanitize_metric(
            {"sessionId": "s1", "event": "turn", "evil": "haxx", "nested": {"a": 1}}
        )
        assert "evil" not in rec
        assert "nested" not in rec

    def test_non_bool_ok_dropped(self):
        rec = sanitize_metric({"sessionId": "s1", "event": "tool", "ok": "yes"})
        assert "ok" not in rec


@pytest.mark.unit
class TestBeaconToEvent:
    """Task 2: each beacon type maps to the right coach_events row (or None)."""

    def test_connect(self):
        evt = beacon_to_event(
            {"sessionId": "s1", "event": "connect", "connect_ms": 300, "token_ms": 40},
            "u1",
        )
        assert evt["event_type"] == "voice_connect"
        assert evt["surface"] == "voice"
        assert evt["user_id"] == "u1"
        assert evt["session_id"] == "s1"
        assert evt["duration_ms"] == 300
        assert evt["payload"]["token_ms"] == 40

    def test_reconnect(self):
        evt = beacon_to_event({"sessionId": "s1", "event": "reconnect", "connect_ms": 90}, "u1")
        assert evt["event_type"] == "voice_reconnect"

    def test_error_maps_to_voice_drop_with_cause(self):
        evt = beacon_to_event(
            {"sessionId": "s1", "event": "error", "error": "boom"}, "u1"
        )
        assert evt["event_type"] == "voice_drop"
        assert evt["severity"] == "error"
        assert evt["ok"] is False
        assert evt["payload"]["cause"] == "boom"

    def test_drop_maps_to_voice_drop(self):
        evt = beacon_to_event({"sessionId": "s1", "event": "drop"}, "u1")
        assert evt["event_type"] == "voice_drop"

    def test_failed_tool_beacon_maps_with_source_beacon(self):
        evt = beacon_to_event(
            {
                "sessionId": "s1",
                "event": "tool",
                "ok": False,
                "error_code": "http_429",
                "tool_name": "analyze_position",
                "tool_ms": 12,
            },
            "u1",
        )
        assert evt["event_type"] == "tool_call"
        assert evt["ok"] is False
        assert evt["error_code"] == "http_429"
        assert evt["tool_name"] == "analyze_position"
        assert evt["duration_ms"] == 12
        assert evt["payload"]["source"] == "beacon"

    def test_successful_tool_beacon_is_not_logged(self):
        # Server-side execution already logs the authoritative row.
        evt = beacon_to_event(
            {"sessionId": "s1", "event": "tool", "ok": True, "tool_name": "x"}, "u1"
        )
        assert evt is None

    def test_tool_timeout(self):
        evt = beacon_to_event(
            {"sessionId": "s1", "event": "tool_timeout", "tool_name": "x", "tool_ms": 10000},
            "u1",
        )
        assert evt["event_type"] == "tool_timeout"
        assert evt["error_code"] == "timeout"
        assert evt["ok"] is False
        assert evt["payload"]["source"] == "beacon"

    def test_barge_in(self):
        evt = beacon_to_event(
            {"sessionId": "s1", "event": "barge_in", "turn": 3, "turn_id": "t3"}, "u1"
        )
        assert evt["event_type"] == "barge_in"
        assert evt["turn_id"] == "t3"

    def test_turn_maps_to_turn_end(self):
        evt = beacon_to_event(
            {"sessionId": "s1", "event": "turn", "ttfa_ms": 700, "turn": 2, "turn_id": "t2"},
            "u1",
        )
        assert evt["event_type"] == "turn_end"
        assert evt["duration_ms"] == 700
        assert evt["payload"]["ttfa_ms"] == 700

    def test_session_end(self):
        evt = beacon_to_event(
            {"sessionId": "s1", "event": "session_end", "session_ms": 42000,
             "end_reason": "user_stop"},
            "u1",
        )
        assert evt["event_type"] == "session_end"
        assert evt["duration_ms"] == 42000
        assert evt["payload"]["end_reason"] == "user_stop"

    def test_end_beacon_has_no_coach_event(self):
        # 'end' is metering-only (record_voice_event handles it).
        assert beacon_to_event({"sessionId": "s1", "event": "end", "session_ms": 1}, "u1") is None

    def test_mint_rejected_classification(self):
        for reason, severity in [
            ("quota_exhausted", "warn"),
            ("rate_limited", "warn"),
            ("error", "error"),
        ]:
            evt = beacon_to_event(
                {"event": "mint_rejected", "reason": reason}, "u1"
            )
            assert evt["event_type"] == "mint_rejected"
            assert evt["error_code"] == reason
            assert evt["severity"] == severity
            # No session needed — a mint is rejected before a session exists.
            assert evt["user_id"] == "u1"

    def test_mint_rejected_defaults_reason_to_error(self):
        evt = beacon_to_event({"event": "mint_rejected"}, "u1")
        assert evt["error_code"] == "error"

    def test_unknown_event_returns_none(self):
        assert beacon_to_event({"sessionId": "s1", "event": "bogus"}, "u1") is None
        assert beacon_to_event("not a dict", "u1") is None


@pytest.mark.unit
class TestMetricsEndpointLogsEvents:
    """Task 2: the metrics endpoint maps a beacon to a coach_events row."""

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.log_event")
    def test_beacon_logged_to_coach_events(self, mock_log, _tmp_metrics_dir):
        resp = self.client.post(
            "/api/coach/metrics",
            headers=USER_HEADERS,
            json={"sessionId": "s1", "event": "connect", "connect_ms": 100},
        )
        assert resp.status_code == 204
        assert mock_log.called
        kwargs = mock_log.call_args.kwargs
        assert kwargs["event_type"] == "voice_connect"
        assert kwargs["user_id"] == "test-user-123"
        assert kwargs["surface"] == "voice"

    @patch("src.server.log_event", side_effect=RuntimeError("logger down"))
    def test_event_log_failure_never_500s(self, _mock_log, _tmp_metrics_dir):
        resp = self.client.post(
            "/api/coach/metrics",
            headers=USER_HEADERS,
            json={"sessionId": "s1", "event": "connect"},
        )
        assert resp.status_code == 204
