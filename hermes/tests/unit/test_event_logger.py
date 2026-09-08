"""Unit tests for the coach event logger (dual sink, fail-open)."""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from src import event_logger as el


@pytest.fixture
def spool_dir(tmp_path, monkeypatch):
    """Point the spool at a temp dir so tests don't touch the real metrics dir."""
    d = tmp_path / "metrics"
    monkeypatch.setattr(el, "METRICS_DIR", str(d))
    return d


def _read_spool(spool_dir) -> list[dict]:
    files = list(spool_dir.glob("coach-events-*.jsonl"))
    assert len(files) == 1, f"expected 1 spool file, got {files}"
    return [json.loads(line) for line in files[0].read_text().splitlines() if line.strip()]


@pytest.mark.unit
class TestSpoolSink:
    def test_event_written_to_spool(self, spool_dir):
        logger = el._EventLogger()
        logger.log_event(
            "turn_start",
            surface="text",
            user_id="u1",
            session_id="s1",
            turn_id="t1",
            model="gpt",
            payload={"message_length": 5},
        )
        rows = _read_spool(spool_dir)
        assert len(rows) == 1
        row = rows[0]
        assert row["event_type"] == "turn_start"
        assert row["surface"] == "text"
        assert row["user_id"] == "u1"
        assert row["session_id"] == "s1"
        assert row["turn_id"] == "t1"
        assert row["payload"] == {"message_length": 5}
        assert "created_at" in row

    def test_spool_appends_multiple(self, spool_dir):
        logger = el._EventLogger()
        for i in range(3):
            logger.log_event("tool_call", surface="text", tool_name=f"t{i}")
        assert len(_read_spool(spool_dir)) == 3

    def test_default_severity_is_info(self, spool_dir):
        logger = el._EventLogger()
        logger.log_event("turn_end", surface="text")
        assert _read_spool(spool_dir)[0]["severity"] == "info"


@pytest.mark.unit
class TestSupabaseSink:
    def test_queue_drains_to_supabase(self, spool_dir, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        posted = []

        def _fake_post(url, json=None, headers=None, timeout=None):
            posted.append((url, json))
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            return resp

        logger = el._EventLogger()
        with patch.object(el.httpx, "post", side_effect=_fake_post):
            logger.log_event("turn_start", surface="text", session_id="s1")
            # Wait for the background worker to drain the queue.
            logger._queue.join()

        assert len(posted) == 1
        url, body = posted[0]
        assert url.endswith("/rest/v1/coach_events")
        assert body["event_type"] == "turn_start"
        assert body["session_id"] == "s1"

    def test_no_supabase_when_unconfigured(self, spool_dir, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        logger = el._EventLogger()
        with patch.object(el.httpx, "post") as mock_post:
            logger.log_event("turn_start", surface="text")
            time.sleep(0.05)
        mock_post.assert_not_called()
        # Spool still written even with Supabase off.
        assert len(_read_spool(spool_dir)) == 1


@pytest.mark.unit
class TestNeverRaises:
    def test_spool_failure_swallowed(self, spool_dir, monkeypatch):
        logger = el._EventLogger()
        monkeypatch.setattr(logger, "_write_spool", MagicMock(side_effect=OSError("disk full")))
        # Must not raise.
        logger.log_event("turn_start", surface="text")

    def test_supabase_failure_invisible(self, spool_dir, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        logger = el._EventLogger()
        with patch.object(el.httpx, "post", side_effect=RuntimeError("network down")):
            logger.log_event("turn_start", surface="text", session_id="s1")
            logger._queue.join()  # worker swallows the error
        # Spool still has the event — nothing lost locally.
        assert len(_read_spool(spool_dir)) == 1

    def test_module_shim_never_raises(self, spool_dir, monkeypatch):
        # A totally broken payload serialization still must not raise.
        el.log_event("x", surface="text", payload={"o": object()})


@pytest.mark.unit
class TestTruncation:
    def test_long_string_field_truncated(self):
        big = "a" * 5000
        out = el._truncate_payload({"text": big})
        assert out["text"].endswith("…[truncated]")
        assert len(out["text"]) == el._STR_FIELD_MAX + len("…[truncated]")

    def test_short_field_untouched(self):
        out = el._truncate_payload({"text": "hello"})
        assert out == {"text": "hello"}

    def test_oversized_payload_replaced_with_stub(self):
        # Many medium strings, each under the per-field cap but together > 8KB.
        payload = {f"k{i}": "x" * 1000 for i in range(20)}
        out = el._truncate_payload(payload)
        assert out["truncated"] is True
        assert set(out["keys"]) == set(payload.keys())

    def test_none_payload(self):
        assert el._truncate_payload(None) is None


@pytest.mark.unit
class TestTurnId:
    def test_new_turn_id_shape(self):
        tid = el.new_turn_id()
        assert isinstance(tid, str)
        assert len(tid) == 12
        int(tid, 16)  # valid hex

    def test_turn_ids_unique(self):
        assert len({el.new_turn_id() for _ in range(100)}) == 100


@pytest.mark.unit
class TestQueueOverflow:
    def test_drop_oldest_when_full(self, spool_dir, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        logger = el._EventLogger()
        # Shrink the queue and stall the worker so it fills.
        import queue as _q
        logger._queue = _q.Queue(maxsize=2)
        # Never start the drain worker: enqueue directly to test drop-oldest.
        for i in range(5):
            logger._enqueue({"n": i})
        # Bounded at 2 and drops counted.
        assert logger._queue.qsize() == 2
        assert logger._dropped >= 3
