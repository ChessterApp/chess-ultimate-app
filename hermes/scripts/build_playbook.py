#!/usr/bin/env python3
"""Build the engine-verified coaching playbook (CL Phase 2, Slice 1).

The ACE curation loop, run OFFLINE over stored transcripts (never inline in a
chat turn):

  Generator  — select candidate coach turns from ``coach_messages`` (or a local
               JSONL spool when Supabase is unconfigured).
  Reflector  — one cheap-tier LLM call per candidate batch → strict JSON entries,
               gated on shape / caps / generalizability / confidence.
  Curator    — engine-verify each surviving entry, dedupe against active entries,
               enforce the size cap, and accept / reject / merge with an audit row.

Safe by default: ``--dry-run`` (the default) prints what WOULD be written and
never touches Supabase. Pass ``--execute`` to actually persist. Per-candidate
fail-open — one bad candidate never kills the run. ``--max-llm-calls`` caps the
Reflector budget.

Usage:
    python scripts/build_playbook.py                       # dry-run over recent turns
    python scripts/build_playbook.py --execute --limit 100
    python scripts/build_playbook.py --spool data/playbook_spool.jsonl --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Make ``src`` importable when run as a script from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import playbook  # noqa: E402

BATCH_SIZE = 5  # candidate turns per Reflector call


def _load_spool(path: str) -> list[dict]:
    """Load candidate turns from a local JSONL spool (fallback source)."""
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! failed to read spool {path}: {exc}", file=sys.stderr)
    return rows


def _gather_candidates(args) -> list[dict]:
    if args.spool:
        cands = playbook.build_candidates(_load_spool(args.spool))
    else:
        cands = playbook.select_candidates(since=args.since, limit=args.limit, user=args.user)
    return cands[: args.limit]


def run(args) -> dict:
    """Run the curation loop. Returns a summary dict."""
    candidates = _gather_candidates(args)
    summary = {"candidates": len(candidates), "llm_calls": 0,
               "accept": 0, "reject": 0, "merge": 0, "gated_out": 0}
    if not candidates:
        print("No candidate turns (no Supabase credentials / spool, or no matching rows).")
        return summary

    print(
        f"Curating from {len(candidates)} candidate turn(s) "
        f"({'EXECUTE' if args.execute else 'dry-run'}), "
        f"max_llm_calls={args.max_llm_calls}…"
    )
    active = playbook.load_active_entries()
    model = playbook._cheap_model()

    for i in range(0, len(candidates), BATCH_SIZE):
        if summary["llm_calls"] >= args.max_llm_calls:
            print(f"  reached --max-llm-calls={args.max_llm_calls}; stopping.")
            break
        batch = candidates[i:i + BATCH_SIZE]
        try:
            prompt = playbook.build_reflection_prompt(batch)
            raw = playbook.call_reflector_llm(prompt, model)
            summary["llm_calls"] += 1
        except Exception as exc:  # noqa: BLE001 — one bad batch never kills the run
            print(f"  ! reflector call failed for batch {i // BATCH_SIZE}: {exc}", file=sys.stderr)
            continue

        turn_ids = [c.get("turn_id") for c in batch if c.get("turn_id")]
        for raw_entry in playbook.parse_entries(raw):
            entry = playbook.gate_entry(raw_entry)
            if entry is None:
                summary["gated_out"] += 1
                continue
            try:
                result = playbook.curate_entry(
                    entry, active, turn_ids, execute=args.execute
                )
            except Exception as exc:  # noqa: BLE001 — fail-open per candidate
                print(f"  ! curation failed for '{entry.get('title')}': {exc}", file=sys.stderr)
                continue
            action = result["action"]
            summary[action] = summary.get(action, 0) + 1
            verb = {"accept": "accept", "merge": "merge", "reject": "reject"}[action]
            reason = f" ({result['reason']})" if result.get("reason") else ""
            verified = " verified" if result.get("verified") else ""
            print(f"  [{verb}]{verified}{reason}: {entry['title']}")

    print(
        "Done. "
        f"{summary['accept']} accepted, {summary['merge']} merged, "
        f"{summary['reject']} rejected, {summary['gated_out']} gated out "
        f"across {summary['llm_calls']} LLM call(s)."
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the engine-verified coaching playbook.")
    parser.add_argument("--since", default=None, help="Only mine turns created at/after this ISO timestamp.")
    parser.add_argument("--limit", type=int, default=50, help="Max candidate turns to consider (default 50).")
    parser.add_argument("--user", default=None, help="Restrict to a comma-separated set of session ids.")
    parser.add_argument("--spool", default=None, help="Local JSONL of candidate turns (fallback source).")
    parser.add_argument("--max-llm-calls", type=int, default=10, help="Reflector call budget (default 10).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="Print what would be written, write nothing (default).")
    group.add_argument("--execute", action="store_true", help="Actually persist accepted entries + audit rows.")
    args = parser.parse_args(argv)
    if args.execute:
        args.dry_run = False

    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
