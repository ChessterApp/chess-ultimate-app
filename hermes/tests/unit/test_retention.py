"""Unit tests for the retention purge job (Phase 3, Task 2)."""

import os
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src import retention


@pytest.mark.unit
class TestConfig:
    def test_default_retention_days(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COACH_EVENTS_RETENTION_DAYS", None)
            assert retention.coach_events_retention_days() == 90

    def test_custom_retention_days(self):
        with patch.dict(os.environ, {"COACH_EVENTS_RETENTION_DAYS": "30"}):
            assert retention.coach_events_retention_days() == 30

    def test_invalid_retention_days_falls_back(self):
        with patch.dict(os.environ, {"COACH_EVENTS_RETENTION_DAYS": "notanumber"}):
            assert retention.coach_events_retention_days() == 90

    def test_kill_switch_default_enabled(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RETENTION_ENABLED", None)
            assert retention.retention_enabled() is True

    def test_kill_switch_disabled(self):
        with patch.dict(os.environ, {"RETENTION_ENABLED": "false"}):
            assert retention.retention_enabled() is False


@pytest.mark.unit
class TestPurgeTable:
    @patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_no_supabase_returns_zero(self):
        assert retention._purge_table("coach_events", datetime.now(timezone.utc)) == 0

    @patch("src.retention.httpx.delete")
    @patch("src.retention.httpx.get")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://x.co", "SUPABASE_SERVICE_KEY": "k"})
    def test_single_batch(self, mock_get, mock_delete):
        get_resp = MagicMock()
        get_resp.raise_for_status.return_value = None
        get_resp.json.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
        mock_get.return_value = get_resp
        del_resp = MagicMock()
        del_resp.raise_for_status.return_value = None
        mock_delete.return_value = del_resp

        deleted = retention._purge_table("coach_events", datetime.now(timezone.utc))
        assert deleted == 3
        # One get + one delete; short page stops the loop.
        assert mock_get.call_count == 1
        assert mock_delete.call_count == 1
        # The delete targeted exactly the ids returned.
        _, kwargs = mock_delete.call_args
        assert kwargs["params"]["id"] == "in.(1,2,3)"

    @patch("src.retention.httpx.delete")
    @patch("src.retention.httpx.get")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://x.co", "SUPABASE_SERVICE_KEY": "k"})
    def test_multiple_batches(self, mock_get, mock_delete):
        full = [{"id": i} for i in range(retention._BATCH)]
        tail = [{"id": 99999}]
        r1, r2 = MagicMock(), MagicMock()
        r1.raise_for_status.return_value = None
        r1.json.return_value = full
        r2.raise_for_status.return_value = None
        r2.json.return_value = tail
        mock_get.side_effect = [r1, r2]
        del_resp = MagicMock()
        del_resp.raise_for_status.return_value = None
        mock_delete.return_value = del_resp

        deleted = retention._purge_table("coach_events", datetime.now(timezone.utc))
        assert deleted == retention._BATCH + 1
        assert mock_get.call_count == 2
        assert mock_delete.call_count == 2

    @patch("src.retention.httpx.get", side_effect=RuntimeError("boom"))
    @patch.dict("os.environ", {"SUPABASE_URL": "https://x.co", "SUPABASE_SERVICE_KEY": "k"})
    def test_error_is_swallowed(self, mock_get):
        # Fail-open: no exception, returns count so far (0).
        assert retention._purge_table("coach_events", datetime.now(timezone.utc)) == 0


@pytest.mark.unit
class TestPurgeSpool:
    def test_deletes_old_beacons_keeps_recent(self, tmp_path):
        old_evt = tmp_path / "coach-events-20200101.jsonl"
        old_voice = tmp_path / "voice-latency-2020-01-01.jsonl"
        recent = tmp_path / "coach-events-20990101.jsonl"
        unrelated = tmp_path / "keep.txt"
        for f in (old_evt, old_voice, recent, unrelated):
            f.write_text("{}\n")

        # Age the two "old" files well past the cutoff.
        old_epoch = time.time() - 100 * 86400
        os.utime(old_evt, (old_epoch, old_epoch))
        os.utime(old_voice, (old_epoch, old_epoch))

        cutoff = time.time() - retention.SPOOL_RETENTION_DAYS * 86400
        with patch.object(retention, "METRICS_DIR", str(tmp_path)):
            deleted = retention._purge_spool(cutoff)

        assert deleted == 2
        assert not old_evt.exists()
        assert not old_voice.exists()
        assert recent.exists()
        assert unrelated.exists()

    def test_missing_dir_returns_zero(self, tmp_path):
        missing = str(tmp_path / "nope")
        with patch.object(retention, "METRICS_DIR", missing):
            assert retention._purge_spool(time.time()) == 0


@pytest.mark.unit
class TestRunPurge:
    @patch("src.retention.log_event")
    @patch("src.retention._purge_spool", return_value=1)
    @patch("src.retention._purge_table")
    def test_summary_and_event_logged(self, mock_table, mock_spool, mock_log):
        mock_table.side_effect = [5, 7]  # coach_events, analytics_events
        summary = retention.run_purge(now=datetime(2026, 9, 8, tzinfo=timezone.utc))
        assert summary == {"coach_events": 5, "analytics_events": 7, "spool_files": 1}
        # Correct tables + cutoffs.
        called_tables = [c.args[0] for c in mock_table.call_args_list]
        assert called_tables == ["coach_events", "analytics_events"]
        # Summary event logged through event_logger.
        mock_log.assert_called_once()
        assert mock_log.call_args.args[0] == "retention_purge"
        assert mock_log.call_args.kwargs["payload"] == summary
