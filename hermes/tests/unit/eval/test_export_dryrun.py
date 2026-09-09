"""Task A — corpus export: dry-run safety, join correctness, idempotency.

Uses a mocked Supabase reader — never a live client, never a real credential.
Asserts the dry-run writes nothing and that ``--execute`` is required to write.
"""

import glob
import gzip
import json
import os

import pytest

from scripts import export_training_corpus as exp


class FakeReader:
    """Stand-in for SupabaseReader — returns canned rows, records calls."""

    def __init__(self, tables):
        self.tables = tables
        self.calls = []

    def fetch(self, table, since, until):
        self.calls.append((table, since, until))
        return list(self.tables.get(table, []))


CANNED = {
    "coach_messages": [
        # Turn t1 — a full user+assistant pair.
        {"session_id": "s1", "turn_id": "t1", "role": "user", "content": "What now?",
         "created_at": "2026-07-01T10:00:00Z"},
        {"session_id": "s1", "turn_id": "t1", "role": "assistant", "content": "Play e4.",
         "created_at": "2026-07-01T10:00:01Z", "model": "claude-sonnet-5",
         "prompt_version": "abc1234567", "latency_ms": 800,
         "prompt_tokens": 500, "completion_tokens": 40},
        # Turn t2 — another full pair.
        {"session_id": "s1", "turn_id": "t2", "role": "user", "content": "And here?",
         "created_at": "2026-07-01T10:05:00Z"},
        {"session_id": "s1", "turn_id": "t2", "role": "assistant", "content": "Develop Nf3.",
         "created_at": "2026-07-01T10:05:01Z", "model": "claude-sonnet-5",
         "prompt_version": "abc1234567"},
        # Orphan user turn (no assistant) — must be dropped.
        {"session_id": "s2", "turn_id": "t3", "role": "user", "content": "Hello?",
         "created_at": "2026-07-01T11:00:00Z"},
        # Pre-Phase-1 row with no turn_id — must be dropped.
        {"session_id": "s2", "turn_id": None, "role": "assistant", "content": "legacy",
         "created_at": "2026-06-01T09:00:00Z"},
    ],
    "coach_events": [
        {"session_id": "s1", "turn_id": "t1", "event_type": "tool_call",
         "tool_name": "analyze_position", "ok": True, "duration_ms": 120,
         "payload": {"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"}},
    ],
    "analytics_events": [
        {"session_id": "s1", "event_type": "page_view", "created_at": "2026-07-01T10:00:00Z"},
    ],
}


@pytest.mark.unit
class TestBuildRecords:
    def test_join_and_dedupe(self):
        recs = exp.build_records(CANNED["coach_messages"], CANNED["coach_events"])
        by_turn = {r["turn"]: r for r in recs}
        assert set(by_turn) == {"t1", "t2"}  # orphan + no-turn_id dropped

        t1 = by_turn["t1"]
        assert t1["assistant_text"] == "Play e4."
        assert t1["user_text"] == "What now?"
        assert t1["model"] == "claude-sonnet-5"
        assert t1["fen_context"].startswith("rnbqkbnr")
        assert t1["tool_calls"][0]["tool_name"] == "analyze_position"
        assert t1["tokens"] == {"prompt": 500, "completion": 40}
        assert t1["latency"] == 800

    def test_no_duplicate_rows_on_repeated_turn(self):
        msgs = CANNED["coach_messages"] + [
            {"session_id": "s1", "turn_id": "t1", "role": "assistant",
             "content": "dup", "created_at": "2026-07-01T10:00:02Z"},
        ]
        recs = exp.build_records(msgs, [])
        t1 = [r for r in recs if r["turn"] == "t1"]
        assert len(t1) == 1  # deduped on (session_id, turn)


@pytest.mark.unit
class TestDryRun:
    def test_dry_run_writes_nothing(self, tmp_path):
        reader = FakeReader(CANNED)
        out_root = str(tmp_path / "corpus")
        summary = exp.run_export(reader, out_root, since=None, until=None,
                                 execute=False, version_tag="20260701")
        assert summary["dry_run"] is True
        assert summary["turn_records"] == 2
        assert summary["new_records"] == 2
        assert summary["written"] == 0
        # Nothing on disk.
        assert not os.path.exists(out_root)

    def test_fetch_called_for_all_three_tables(self, tmp_path):
        reader = FakeReader(CANNED)
        exp.run_export(reader, str(tmp_path / "c"), since="2026-06-01", until=None,
                       execute=False, version_tag="20260701")
        fetched = {c[0] for c in reader.calls}
        assert fetched == {"coach_messages", "coach_events", "analytics_events"}


@pytest.mark.unit
class TestExecute:
    def test_execute_writes_shards_and_manifest(self, tmp_path):
        reader = FakeReader(CANNED)
        out_root = str(tmp_path / "corpus")
        summary = exp.run_export(reader, out_root, since=None, until=None,
                                 execute=True, version_tag="20260701")
        assert summary["written"] == 2
        version_dir = os.path.join(out_root, "v20260701")
        shards = glob.glob(os.path.join(version_dir, "shard-*.jsonl.gz"))
        assert len(shards) == 1
        manifest = json.load(open(os.path.join(version_dir, "manifest.json")))
        assert manifest["row_count"] == 2
        assert manifest["date_range"]["min"] and manifest["date_range"]["max"]
        assert "checksum" in manifest

        # Shard content is valid gzip JSONL.
        with gzip.open(shards[0], "rt", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        assert len(rows) == 2

    def test_rerun_is_idempotent(self, tmp_path):
        reader = FakeReader(CANNED)
        out_root = str(tmp_path / "corpus")
        exp.run_export(reader, out_root, since=None, until=None,
                       execute=True, version_tag="20260701")
        second = exp.run_export(reader, out_root, since=None, until=None,
                                execute=True, version_tag="20260701")
        assert second["already_exported"] == 2
        assert second["new_records"] == 0
        assert second["written"] == 0
        # Still exactly one shard, two rows.
        version_dir = os.path.join(out_root, "v20260701")
        manifest = json.load(open(os.path.join(version_dir, "manifest.json")))
        assert manifest["row_count"] == 2


@pytest.mark.unit
class TestMainNoCreds:
    def test_main_exits_cleanly_without_creds(self, monkeypatch, capsys):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        rc = exp.main(["--since", "2026-06-01"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "nothing to export" in out.lower()
