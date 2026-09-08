"""Unit tests for the voice-latency metrics ingest (Phase 4.5, Task 2).

Covers the sanitiser (src/voice_metrics.py) and the POST /api/coach/metrics
endpoint: a valid beacon writes one JSONL line and returns 204, and garbage
input never produces a 5xx.
"""

import json

import pytest
from fastapi.testclient import TestClient

from src import voice_metrics
from src.server import app
from src.voice_metrics import record_metric, sanitize_metric

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
