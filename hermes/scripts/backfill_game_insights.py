#!/usr/bin/env python3
"""Backfill coach_game_insights from a student's existing user_games (CL Phase 1,
Slice 2).

Game reviews are computed on demand and never persisted, so a student's history
has no insights until they re-review each game. This offline job walks the
existing ``user_games`` rows (which already carry the PGN), runs the same backend
Game Review engine pipeline locally, and persists one distilled insight per game
via the shared ``persist_review_insight`` function.

Safe by default: ``--dry-run`` (the default) prints what WOULD be written and
never touches Supabase. Pass ``--execute`` to actually upsert rows. With no
Supabase credentials there are no games to process and the job exits cleanly (0).

Usage:
    python scripts/backfill_game_insights.py [--user-id ID] [--limit N] [--execute]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# The review engine + persist function live in the backend repo (same git repo).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))  # .../chess-app
_BACKEND_DIR = os.path.join(_REPO_ROOT, "backend")


def _fetch_user_games(user_id: str | None, limit: int) -> list[dict]:
    """Fetch user_games rows (optionally for one user), newest first. Fail-open
    → [] when Supabase is not configured or the query fails."""
    from src.tools.user_data import _supabase_get

    params = {
        "select": "*",
        "order": "created_at.desc",  # user_games has no played_at column (only date TEXT / created_at)
        "limit": str(max(1, limit)),
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"
    return _supabase_get("user_games", params)


def _first(row: dict, *keys):
    """Return the first present, non-empty value among ``keys``."""
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


def process_row(row: dict, *, execute: bool) -> dict | None:
    """Review one user_games row and (optionally) persist its insight.

    Returns the distilled insight dict on success, or None if the row has no PGN
    or the review failed. Never raises."""
    # Backend imports are lazy so the no-creds / no-games path never needs the
    # chess engine dependencies (keeps the job importable without Stockfish).
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)
    from services.game_review import analyze_game
    from services.review_insights import distill_insight, persist_review_insight

    pgn = _first(row, "pgn", "moves_pgn")
    user_id = _first(row, "user_id")
    if not pgn or not user_id:
        return None

    game_ref = str(_first(row, "id", "game_id") or "")
    color = _first(row, "color", "user_color")
    result = _first(row, "result")
    played_at = _first(row, "played_at", "created_at")

    try:
        review = analyze_game(pgn)
    except Exception as exc:  # noqa: BLE001 — one bad game must not abort the job
        print(f"  ! review failed for game {game_ref or '?'}: {exc}", file=sys.stderr)
        return None

    insight = distill_insight(
        user_id,
        game_ref,
        review,
        color=color,
        result=result,
        played_at=played_at,
    )

    if execute:
        ok = persist_review_insight(
            user_id,
            game_ref,
            review,
            color=color,
            result=result,
            played_at=played_at,
        )
        print(f"  {'wrote' if ok else 'FAILED'} insight for game {game_ref or '?'}")
    else:
        print(f"  [dry-run] would write insight for game {game_ref or '?'}:")
        print("  " + json.dumps(insight, indent=2, default=str).replace("\n", "\n  "))

    return insight


def run(user_id: str | None, limit: int, execute: bool) -> int:
    """Fetch and process games. Returns the number of insights produced."""
    games = _fetch_user_games(user_id, limit)
    if not games:
        print("No games to process (no Supabase credentials or no matching rows).")
        return 0

    print(
        f"Processing {len(games)} game(s)"
        f"{f' for user {user_id}' if user_id else ''} "
        f"({'EXECUTE' if execute else 'dry-run'})…"
    )
    written = 0
    for row in games:
        if process_row(row, execute=execute):
            written += 1
    print(f"Done. {written}/{len(games)} game(s) produced an insight.")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill coach_game_insights from user_games.")
    parser.add_argument("--user-id", default=None, help="Only backfill this student's games.")
    parser.add_argument("--limit", type=int, default=10, help="Max games to process (default 10).")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually upsert insights (default is a dry-run that writes nothing).",
    )
    args = parser.parse_args(argv)

    run(args.user_id, args.limit, execute=args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
