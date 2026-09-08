#!/usr/bin/env python3
"""daily_digest — a compact markdown summary of the last N hours of coach usage.

Phase 3, Task 4. Queries Supabase directly (reusing the analytics aggregation
core) and prints a human-readable digest the operator can pipe into email/Slack
via cron. Standalone:

    python scripts/daily_digest.py            # last 24h
    python scripts/daily_digest.py --hours 6  # last 6h

Exits 0 even on partial data — missing sections print a warning line rather than
failing, so a Supabase hiccup never breaks the cron.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make ``src`` importable whether run from the repo root or elsewhere.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.config import load_env  # noqa: E402
from src import analytics_db as adb  # noqa: E402


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _top(counter: dict, n: int) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda kv: -kv[1])[:n]


def build_digest(hours: int, now: datetime | None = None) -> str:
    """Fetch the window and render the markdown digest. Never raises."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    gte = f"gte.{adb._iso(since)}"

    lines: list[str] = []
    warnings: list[str] = []

    lines.append(f"# Coach digest — last {hours}h")
    lines.append(f"_generated {adb._iso(now)}_")
    lines.append("")

    try:
        events = adb._fetch("coach_events", adb._EVENT_COLS, {"created_at": gte})
        check_rows = adb._fetch(
            "coach_events",
            adb._CHECK_COLS,
            {"created_at": gte, "event_type": "eq.tool_call", "tool_name": "eq.check_moves"},
        )
        tokens = adb._fetch("token_usage", adb._TOKEN_COLS, {"created_at": gte})
        agg = adb.aggregate_events(events, check_rows, tokens)
    except Exception as exc:  # pragma: no cover - fail-open
        lines.append(f"> ⚠️  analytics fetch failed: {exc}")
        return "\n".join(lines)

    # Turns by surface.
    turns = agg.get("turn_counts_by_surface", {})
    total_turns = sum(turns.values())
    lines.append(
        f"**Turns:** {total_turns} total "
        f"(text {turns.get('text', 0)}, voice {turns.get('voice', 0)})"
    )

    # Errors (top 5 by type).
    errs = agg.get("error_counts", {}).get("by_event_type", {})
    if errs:
        top = ", ".join(f"{k} ({v})" for k, v in _top(errs, 5))
        lines.append(f"**Errors:** {sum(errs.values())} total — {top}")
    else:
        lines.append("**Errors:** none")

    # Tools p50/p90 + failure rate (top tools by call volume).
    tools = agg.get("tools", {})
    if tools:
        lines.append("")
        lines.append("**Tools (top by volume):**")
        lines.append("")
        lines.append("| tool | calls | fail rate | p50 ms | p90 ms |")
        lines.append("|------|------:|----------:|-------:|-------:|")
        for name, s in sorted(tools.items(), key=lambda kv: -kv[1]["calls"])[:8]:
            fail = 1.0 - s["success_rate"]
            lines.append(
                f"| {name} | {s['calls']} | {_fmt_pct(fail)} | {s['p50_ms']} | {s['p90_ms']} |"
            )
    else:
        warnings.append("no tool calls in window")

    lines.append("")

    # Illegal-move rate.
    imr = agg.get("illegal_move_rate", {})
    if imr.get("total_check_moves"):
        lines.append(
            f"**Illegal-move rate:** {_fmt_pct(imr['rate'])} "
            f"({imr['illegal_calls']}/{imr['total_check_moves']} check_moves calls)"
        )
    else:
        warnings.append("no check_moves calls in window")

    # Barge-ins.
    lines.append(f"**Barge-ins:** {agg.get('barge_in_count', 0)}")

    # Voice minutes consumed (sum of voice session durations in window).
    vs = agg.get("voice_sessions", {})
    voice_ms = vs.get("count", 0) * vs.get("avg_duration_ms", 0)
    lines.append(
        f"**Voice:** {vs.get('count', 0)} sessions, "
        f"~{voice_ms / 60000:.1f} min consumed"
    )

    # Mint rejections.
    mints = agg.get("mint_rejections_by_reason", {})
    if mints:
        top = ", ".join(f"{k} ({v})" for k, v in _top(mints, 5))
        lines.append(f"**Mint rejections:** {sum(mints.values())} — {top}")
    else:
        lines.append("**Mint rejections:** none")

    # New-user count — users whose FIRST-EVER coach event falls in the window.
    new_users = _new_user_count(agg.get("active_users", 0), events, since)
    if new_users is None:
        warnings.append("new-user count skipped (too many active users)")
    else:
        lines.append(f"**New users:** {new_users}")

    # Cost by model.
    tbm = agg.get("tokens_by_model", {})
    if tbm:
        lines.append("")
        lines.append("**Cost by model:**")
        for model, b in sorted(tbm.items(), key=lambda kv: -kv[1]["cost_usd"]):
            lines.append(
                f"- {model}: ${b['cost_usd']:.4f} "
                f"({b['prompt_tokens']}p + {b['completion_tokens']}c tokens)"
            )
    else:
        warnings.append("no token/cost rows in window")

    if warnings:
        lines.append("")
        lines.append("---")
        for w in warnings:
            lines.append(f"> ⚠️  {w}")

    return "\n".join(lines)


def _new_user_count(active_users: int, events: list[dict], since: datetime):
    """Users active in the window with no coach_events before it.

    One extra query bounded by the active-user id list. Returns ``None`` (skip)
    when there are too many active users to fit a single ``in.(...)`` filter.
    """
    active_ids = {e.get("user_id") for e in events if e.get("user_id")}
    if not active_ids:
        return 0
    if len(active_ids) > 300:
        return None
    id_list = ",".join(str(i) for i in active_ids)
    prior = adb._fetch(
        "coach_events",
        "user_id",
        {"created_at": f"lt.{adb._iso(since)}", "user_id": f"in.({id_list})"},
    )
    seen_before = {r.get("user_id") for r in prior if r.get("user_id")}
    return len(active_ids - seen_before)


def main() -> int:
    ap = argparse.ArgumentParser(description="Print a coach usage digest.")
    ap.add_argument("--hours", type=int, default=24, help="window size in hours (default 24)")
    args = ap.parse_args()

    load_env()  # pull SUPABASE_* from the hermes .env, same as other scripts.

    hours = args.hours if args.hours and args.hours > 0 else 24
    try:
        print(build_digest(hours))
    except Exception as exc:  # pragma: no cover - never fail the cron
        print(f"# Coach digest\n> ⚠️  digest failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
