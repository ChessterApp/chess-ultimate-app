#!/usr/bin/env python3
"""Task A — training-corpus export (beats the 90-day coach_events purge).

Reads ``coach_messages``, ``coach_events`` and ``analytics_events`` from
Supabase, joins them by ``turn_id`` into one record per assistant turn, and
writes a durable, versioned, gzip'd-JSONL corpus with a ``manifest.json``.

Safety (non-negotiable):
  * **Default dry-run.** Prints what it *would* export (counts only) and writes
    nothing. Requires ``--execute`` to write.
  * Reads Supabase creds from the environment (``SUPABASE_URL`` /
    ``SUPABASE_SERVICE_KEY``). If they are missing it exits cleanly with a
    message — it never hardcodes a credential.
  * **Idempotent + incremental.** ``--since`` / ``--until`` bound the window;
    re-runs into an existing version dir dedupe on ``(session_id, turn)`` so
    rows are never duplicated.

Not wired into CI — run manually / by a future cron before the purge.

Examples:
    python scripts/export_training_corpus.py --since 2026-06-01          # dry-run
    python scripts/export_training_corpus.py --since 2026-06-01 --execute
"""

import argparse
import glob
import gzip
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

DEFAULT_OUT_ROOT = "data/corpus/coach"
SHARD_SIZE = 500
_PAGE = 1000  # Supabase default max rows per request
_HTTP_TIMEOUT = 30

# Table -> the source migration that defines its shape, recorded in the manifest
# so a consumer can tell which schema produced the corpus.
SOURCE_TABLE_VERSIONS = {
    "coach_messages": "001+008",
    "coach_events": "007",
    "analytics_events": "analytics",
}


# ── Supabase reader (httpx REST, paginated) ────────────────────────────


class SupabaseReader:
    """Read-only, paginated Supabase REST reader. Never writes."""

    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def _headers(self, offset: int, limit: int) -> dict:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Range-Unit": "items",
            "Range": f"{offset}-{offset + limit - 1}",
        }

    def fetch(self, table: str, since: Optional[str], until: Optional[str]) -> list[dict]:
        import httpx

        rows: list[dict] = []
        offset = 0
        params: list[tuple[str, str]] = [("select", "*"), ("order", "created_at.asc")]
        if since:
            params.append(("created_at", f"gte.{since}"))
        if until:
            params.append(("created_at", f"lte.{until}"))
        while True:
            resp = httpx.get(
                f"{self.url}/rest/v1/{table}",
                params=params,
                headers=self._headers(offset, _PAGE),
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            rows.extend(batch)
            if len(batch) < _PAGE:
                break
            offset += _PAGE
        return rows


# ── Join: messages + events -> one record per assistant turn ───────────


def _fen_from_events(events: list[dict]) -> Optional[str]:
    """Best-effort FEN for a turn, scraped from coach_events payloads."""
    for e in events:
        payload = e.get("payload") or {}
        if isinstance(payload, dict):
            fen = payload.get("fen") or payload.get("board_fen")
            if fen:
                return fen
    return None


def _tool_calls_from_events(events: list[dict]) -> list[dict]:
    calls = []
    for e in events:
        if e.get("tool_name"):
            calls.append({
                "tool_name": e["tool_name"],
                "ok": e.get("ok"),
                "duration_ms": e.get("duration_ms"),
            })
    return calls


def build_records(messages: list[dict], events: list[dict]) -> list[dict]:
    """Join user+assistant messages and events by turn_id → per-turn records.

    Rows lacking a ``turn_id`` (pre-Phase-1) are skipped — they can't be
    correlated into a turn. Dedupe on ``(session_id, turn)``.
    """
    msgs_by_turn: dict[str, dict] = defaultdict(dict)
    for m in messages:
        turn = m.get("turn_id")
        if not turn:
            continue
        role = m.get("role")
        if role in ("user", "assistant"):
            msgs_by_turn[turn][role] = m

    events_by_turn: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        turn = e.get("turn_id")
        if turn:
            events_by_turn[turn].append(e)

    records: list[dict] = []
    seen: set[tuple] = set()
    for turn, roles in msgs_by_turn.items():
        assistant = roles.get("assistant")
        if not assistant:
            continue  # no assistant reply for this turn — nothing to learn from
        user = roles.get("user", {})
        session_id = assistant.get("session_id")
        key = (session_id, turn)
        if key in seen:
            continue
        seen.add(key)
        turn_events = events_by_turn.get(turn, [])
        records.append({
            "session_id": session_id,
            "turn": turn,
            "ts": assistant.get("created_at"),
            "user_text": user.get("content"),
            "assistant_text": assistant.get("content"),
            "model": assistant.get("model"),
            "prompt_version": assistant.get("prompt_version"),
            "fen_context": _fen_from_events(turn_events),
            "tool_calls": _tool_calls_from_events(turn_events),
            "events": [
                {"event_type": e.get("event_type"), "ok": e.get("ok"),
                 "duration_ms": e.get("duration_ms"), "error_code": e.get("error_code")}
                for e in turn_events
            ],
            "tokens": {
                "prompt": assistant.get("prompt_tokens"),
                "completion": assistant.get("completion_tokens"),
            },
            "latency": assistant.get("latency_ms"),
        })
    return records


# ── Corpus writing (sharded gzip JSONL + manifest) ─────────────────────


def _existing_keys(version_dir: str) -> set[tuple]:
    """(session_id, turn) already present in a version dir (incremental re-runs)."""
    keys: set[tuple] = set()
    for path in sorted(glob.glob(os.path.join(version_dir, "shard-*.jsonl.gz"))):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                keys.add((rec.get("session_id"), rec.get("turn")))
    return keys


def _next_shard_index(version_dir: str) -> int:
    existing = glob.glob(os.path.join(version_dir, "shard-*.jsonl.gz"))
    return len(existing)


def write_corpus(records: list[dict], version_dir: str) -> dict:
    """Write records to sharded gzip JSONL + manifest. Returns a summary."""
    os.makedirs(version_dir, exist_ok=True)
    start_idx = _next_shard_index(version_dir)
    shard_meta = []
    written = 0
    for shard_i, chunk_start in enumerate(range(0, len(records), SHARD_SIZE), start=start_idx):
        chunk = records[chunk_start:chunk_start + SHARD_SIZE]
        name = f"shard-{shard_i:04d}.jsonl.gz"
        path = os.path.join(version_dir, name)
        h = hashlib.sha256()
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for rec in chunk:
                line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
                f.write(line + "\n")
                h.update(line.encode("utf-8"))
        shard_meta.append({"shard": name, "rows": len(chunk), "sha256": h.hexdigest()})
        written += len(chunk)

    manifest = _write_manifest(version_dir, shard_meta)
    return {"written": written, "shards": len(shard_meta), "manifest": manifest}


def _write_manifest(version_dir: str, new_shards: list[dict]) -> str:
    """Merge new shard metadata into the version manifest and rewrite it."""
    manifest_path = os.path.join(version_dir, "manifest.json")
    shards: list[dict] = []
    date_min = date_max = None
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            prev = json.load(f)
        shards = prev.get("shards", [])
        date_min = prev.get("date_range", {}).get("min")
        date_max = prev.get("date_range", {}).get("max")
    shards = shards + new_shards

    # Recompute the date range + total from every shard on disk.
    total = 0
    for s in shards:
        total += s["rows"]
    for path in sorted(glob.glob(os.path.join(version_dir, "shard-*.jsonl.gz"))):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ts = json.loads(line).get("ts")
                if ts:
                    date_min = ts if date_min is None or ts < date_min else date_min
                    date_max = ts if date_max is None or ts > date_max else date_max

    checksum = hashlib.sha256(
        "".join(s["sha256"] for s in shards).encode("utf-8")
    ).hexdigest()
    manifest = {
        "row_count": total,
        "date_range": {"min": date_min, "max": date_max},
        "source_table_versions": SOURCE_TABLE_VERSIONS,
        "shards": shards,
        "checksum": checksum,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path


# ── Orchestration ──────────────────────────────────────────────────────


def run_export(
    reader,
    out_root: str,
    since: Optional[str],
    until: Optional[str],
    execute: bool,
    version_tag: str,
) -> dict:
    """Fetch, join, dedupe and (only with execute) write. Returns a summary."""
    messages = reader.fetch("coach_messages", since, until)
    events = reader.fetch("coach_events", since, until)
    analytics = reader.fetch("analytics_events", since, until)

    records = build_records(messages, events)

    version_dir = os.path.join(out_root, f"v{version_tag}")
    already = _existing_keys(version_dir) if os.path.isdir(version_dir) else set()
    new_records = [r for r in records if (r["session_id"], r["turn"]) not in already]

    summary = {
        "coach_messages": len(messages),
        "coach_events": len(events),
        "analytics_events": len(analytics),
        "turn_records": len(records),
        "already_exported": len(records) - len(new_records),
        "new_records": len(new_records),
        "version_dir": version_dir,
        "dry_run": not execute,
        "written": 0,
    }

    if not execute:
        return summary

    write_summary = write_corpus(new_records, version_dir)
    summary["written"] = write_summary["written"]
    summary["manifest"] = write_summary["manifest"]
    return summary


def _print_summary(s: dict) -> None:
    mode = "DRY-RUN (nothing written)" if s["dry_run"] else "EXECUTE"
    print(f"Corpus export — {mode}")
    print(f"  source rows: coach_messages={s['coach_messages']} "
          f"coach_events={s['coach_events']} analytics_events={s['analytics_events']}")
    print(f"  turn records: {s['turn_records']}  "
          f"(already exported: {s['already_exported']}, new: {s['new_records']})")
    print(f"  target: {s['version_dir']}")
    if not s["dry_run"]:
        print(f"  written: {s['written']} rows  manifest: {s.get('manifest')}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export the coach training corpus (Task A).")
    parser.add_argument("--since", help="ISO datetime lower bound (created_at >=)")
    parser.add_argument("--until", help="ISO datetime upper bound (created_at <=)")
    parser.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    parser.add_argument("--version-tag", help="Corpus version tag (default: UTC YYYYMMDD)")
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually write. Without this the script is a dry-run.",
    )
    args = parser.parse_args(argv)

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — nothing to export. "
              "Exiting cleanly (no creds, no write).")
        return 0

    version_tag = args.version_tag or datetime.now(timezone.utc).strftime("%Y%m%d")
    reader = SupabaseReader(url, key)
    summary = run_export(
        reader=reader,
        out_root=args.out_root,
        since=args.since,
        until=args.until,
        execute=args.execute,
        version_tag=version_tag,
    )
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
