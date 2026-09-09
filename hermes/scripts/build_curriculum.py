#!/usr/bin/env python3
"""Build the automatic curriculum (CL Phase 2, Slice 2 — engine-measured).

Computes each student's training curriculum OFFLINE (never inline in a chat
turn) from two engine-verified signals only:

  * ``coach_game_insights.blunders`` — where the engine says the student
    blunders most (theme + centipawn loss).
  * ``puzzle_attempts``             — objective solve outcomes → the ~50%
    solve-rate learnability frontier.

Pure, deterministic aggregation + scoring — NO LLM calls (Design rule 4), so it
is cheap and fully auditable. Safe by default: ``--dry-run`` (the default)
prints each student's would-be focus and writes nothing. Pass ``--execute`` to
upsert the current row + append an audit row per student. Per-user fail-open —
one bad student never kills the run.

Usage:
    python scripts/build_curriculum.py                        # dry-run, all users
    python scripts/build_curriculum.py --execute --limit 50
    python scripts/build_curriculum.py --user u1,u2 --execute
    python scripts/build_curriculum.py --since 2026-06-01T00:00:00Z
"""

from __future__ import annotations

import argparse
import os
import sys

# Make ``src`` importable when run as a script from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import curriculum  # noqa: E402


def _target_users(args, since: str) -> list[str]:
    if args.user:
        return [u.strip() for u in args.user.split(",") if u.strip()]
    return curriculum.list_users(since, limit=args.limit)


def _print_focus(user_id: str, result: dict) -> None:
    focus = result.get("focus") or []
    cf = result.get("computed_from") or {}
    print(
        f"\n{user_id}: {len(focus)} focus theme(s) from "
        f"{cf.get('blunders', 0)} blunder(s) across {cf.get('games', 0)} game(s), "
        f"{cf.get('attempts', 0)} attempt(s); target={cf.get('target_difficulty')}"
    )
    for f in focus:
        print(f"  - {f['theme']} (score {f['score']}): {f['rationale']}")
    if not focus:
        print("  (no engine-verified blunders in window — nothing to key on)")


def run(args) -> dict:
    """Run the curriculum builder. Returns a summary dict."""
    since = args.since or curriculum.default_since()
    users = _target_users(args, since)[: args.limit]
    summary = {"users": len(users), "written": 0, "empty": 0, "failed": 0}
    if not users:
        print("No users (no Supabase credentials, or no insights in window).")
        return summary

    print(
        f"Computing curriculum for {len(users)} user(s) since {since} "
        f"({'EXECUTE' if args.execute else 'dry-run'})…"
    )
    for user_id in users:
        try:
            insights = curriculum.fetch_insights(user_id, since)
            attempts = curriculum.fetch_attempts(user_id, since)
            result = curriculum.compute_curriculum(insights, attempts, since=since)
        except Exception as exc:  # noqa: BLE001 — fail-open per user
            print(f"  ! compute failed for {user_id}: {exc}", file=sys.stderr)
            summary["failed"] += 1
            continue

        _print_focus(user_id, result)
        if not result.get("focus"):
            summary["empty"] += 1
            continue
        if args.execute:
            try:
                if curriculum.persist_curriculum(user_id, result):
                    summary["written"] += 1
                else:
                    summary["failed"] += 1
            except Exception as exc:  # noqa: BLE001 — fail-open per user
                print(f"  ! persist failed for {user_id}: {exc}", file=sys.stderr)
                summary["failed"] += 1

    print(
        f"\nDone. {summary['written']} written, {summary['empty']} empty, "
        f"{summary['failed']} failed across {summary['users']} user(s)."
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the automatic curriculum (engine-measured).")
    parser.add_argument("--since", default=None,
                        help="Window start (ISO). Default: 90 days ago.")
    parser.add_argument("--user", default=None,
                        help="Restrict to a comma-separated set of user ids.")
    parser.add_argument("--limit", type=int, default=500,
                        help="Max users to process (default 500).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="Print what would be written, write nothing (default).")
    group.add_argument("--execute", action="store_true",
                       help="Actually upsert curricula + append audit rows.")
    args = parser.parse_args(argv)
    if args.execute:
        args.dry_run = False

    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
