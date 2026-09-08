"""DB-backed coach analytics — aggregates telemetry straight from Supabase.

Phase 3, Task 1. The legacy :class:`src.analytics.AnalyticsTracker` aggregates
from a process-memory list that resets on every restart. This module replaces
the *read* side of ``GET /api/coach/analytics`` with durable aggregates computed
from the persisted tables:

  * ``coach_events``   — turn / tool / error / barge-in / mint / voice events
  * ``coach_messages`` — enriched per-turn rows (kept for future use)
  * ``token_usage``    — per-turn cost rows by model + surface
  * ``voice_usage``    — voice-minutes ledger

Design notes
------------
* **Bounded fetches, not whole tables.** Every query is time-filtered
  (``created_at >= now-7d``) and column-projected; rows are paged via the
  PostgREST ``Range`` header up to a hard safety cap so one query can never pull
  the whole table.
* **60-second admin cache.** A dashboard refresh loop must not hammer Supabase;
  the admin result is memoised in-process for :data:`_ADMIN_CACHE_TTL_S`.
* **Fail-open.** Any Supabase / network error yields empty aggregates, never an
  exception into the request path — analytics is telemetry, not a hard path.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import httpx

logger = logging.getLogger("hermes.analytics_db")

_HTTP_TIMEOUT = 10
_PAGE_SIZE = 1000          # PostgREST default max-rows; page through with Range.
_MAX_ROWS = 100_000        # hard safety cap per table per window.
_ADMIN_CACHE_TTL_S = 60    # memoise the admin aggregate to survive refresh loops.


# ── Supabase access ────────────────────────────────────────────────────


def _supabase() -> tuple[str, str]:
    return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", "")


def _fetch(table: str, select: str, filters: dict[str, str]) -> list[dict]:
    """Paged, time-filtered, column-projected SELECT. Returns [] on any error.

    ``filters`` maps a column to a PostgREST operator string, e.g.
    ``{"created_at": "gte.2026-09-01T00:00:00+00:00", "event_type": "eq.turn_end"}``.
    Rows are pulled ``_PAGE_SIZE`` at a time via the ``Range`` header until a
    short page is returned or the ``_MAX_ROWS`` safety cap is reached.
    """
    url, key = _supabase()
    if not url or not key:
        return []

    params = {"select": select, **filters}
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    rows: list[dict] = []
    offset = 0
    try:
        while offset < _MAX_ROWS:
            page_headers = {
                **headers,
                "Range-Unit": "items",
                "Range": f"{offset}-{offset + _PAGE_SIZE - 1}",
            }
            resp = httpx.get(
                f"{url}/rest/v1/{table}",
                params=params,
                headers=page_headers,
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            rows.extend(batch)
            if len(batch) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
    except Exception:
        logger.debug("analytics fetch failed for %s", table, exc_info=True)
        return rows  # partial data is fine (fail-open)
    return rows


# ── Aggregation helpers ────────────────────────────────────────────────


def _percentile(values: list[int], pct: float) -> int:
    """Nearest-rank percentile of a list of ints (0 for empty)."""
    if not values:
        return 0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return int(ordered[k])


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def aggregate_events(
    events: Iterable[dict],
    check_moves_rows: Iterable[dict],
    token_rows: Iterable[dict],
    *,
    user_scope: bool = False,
) -> dict:
    """Pure aggregation over already-fetched rows — the testable core.

    ``events`` are ``coach_events`` rows (all types), ``check_moves_rows`` carry
    the ``payload`` for ``tool_call`` events with ``tool_name='check_moves'``,
    and ``token_rows`` are ``token_usage`` rows. No I/O here.
    """
    events = list(events)

    # Turn counts by surface (a completed turn == one ``turn_end`` event).
    turns_by_surface: dict[str, int] = {}
    # Error counts.
    err_by_type: dict[str, int] = {}
    err_by_code: dict[str, int] = {}
    # Per-tool stats.
    tool_calls: dict[str, int] = {}
    tool_ok: dict[str, int] = {}
    tool_durations: dict[str, list[int]] = {}
    # Voice sessions.
    voice_session_durations: list[int] = []
    barge_ins = 0
    # Mint rejections by reason.
    mint_by_reason: dict[str, int] = {}
    active_users: set[str] = set()

    for e in events:
        etype = e.get("event_type")
        surface = e.get("surface") or "unknown"
        uid = e.get("user_id")
        if uid:
            active_users.add(uid)

        if etype == "turn_end":
            turns_by_surface[surface] = turns_by_surface.get(surface, 0) + 1

        if e.get("severity") == "error":
            err_by_type[etype] = err_by_type.get(etype, 0) + 1
            code = e.get("error_code") or "unknown"
            err_by_code[code] = err_by_code.get(code, 0) + 1

        if etype == "tool_call":
            tname = e.get("tool_name") or "unknown"
            tool_calls[tname] = tool_calls.get(tname, 0) + 1
            if e.get("ok") is not False:
                tool_ok[tname] = tool_ok.get(tname, 0) + 1
            dur = e.get("duration_ms")
            if isinstance(dur, int):
                tool_durations.setdefault(tname, []).append(dur)

        if etype == "barge_in":
            barge_ins += 1

        if etype == "session_end" and surface == "voice":
            dur = e.get("duration_ms")
            if isinstance(dur, int) and dur > 0:
                voice_session_durations.append(dur)

        if etype == "mint_rejected":
            reason = e.get("error_code") or "unknown"
            mint_by_reason[reason] = mint_by_reason.get(reason, 0) + 1

    tools: dict[str, dict] = {}
    for tname, calls in tool_calls.items():
        durs = tool_durations.get(tname, [])
        tools[tname] = {
            "calls": calls,
            "success_rate": round(tool_ok.get(tname, 0) / calls, 4) if calls else 0.0,
            "p50_ms": _percentile(durs, 50),
            "p90_ms": _percentile(durs, 90),
        }

    # Illegal-move rate from check_moves payloads.
    total_check = 0
    illegal_check = 0
    for r in check_moves_rows:
        total_check += 1
        payload = r.get("payload") or {}
        verdict = payload.get("check_moves_verdict") if isinstance(payload, dict) else None
        if isinstance(verdict, dict) and (verdict.get("illegal") or 0) > 0:
            illegal_check += 1

    # Token / cost totals by model.
    tokens_by_model: dict[str, dict] = {}
    for t in token_rows:
        model = t.get("model") or "unknown"
        bucket = tokens_by_model.setdefault(
            model, {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "rows": 0}
        )
        bucket["prompt_tokens"] += int(t.get("prompt_tokens") or 0)
        bucket["completion_tokens"] += int(t.get("completion_tokens") or 0)
        try:
            bucket["cost_usd"] += float(t.get("estimated_cost_usd") or 0)
        except (TypeError, ValueError):
            pass
        bucket["rows"] += 1
    for bucket in tokens_by_model.values():
        bucket["cost_usd"] = round(bucket["cost_usd"], 6)

    result: dict[str, Any] = {
        "turn_counts_by_surface": turns_by_surface,
        "tools": tools,
        "illegal_move_rate": {
            "total_check_moves": total_check,
            "illegal_calls": illegal_check,
            "rate": round(illegal_check / total_check, 4) if total_check else 0.0,
        },
        "voice_sessions": {
            "count": len(voice_session_durations),
            "avg_duration_ms": (
                int(sum(voice_session_durations) / len(voice_session_durations))
                if voice_session_durations
                else 0
            ),
        },
    }
    if not user_scope:
        result["error_counts"] = {"by_event_type": err_by_type, "by_error_code": err_by_code}
        result["barge_in_count"] = barge_ins
        result["mint_rejections_by_reason"] = mint_by_reason
        result["active_users"] = len(active_users)
        result["tokens_by_model"] = tokens_by_model
    return result


# ── Windowed orchestration ─────────────────────────────────────────────

# Columns projected per table (never ``*``, keeps fetches lean).
_EVENT_COLS = "created_at,event_type,severity,surface,user_id,tool_name,duration_ms,ok,error_code"
_CHECK_COLS = "created_at,payload"
_TOKEN_COLS = "created_at,model,surface,prompt_tokens,completion_tokens,estimated_cost_usd"


def _within(rows: list[dict], since: datetime) -> list[dict]:
    """Filter already-fetched rows to ``created_at >= since`` (24h subset)."""
    cutoff = since
    out = []
    for r in rows:
        ts = _parse_ts(r.get("created_at"))
        if ts is not None and ts >= cutoff:
            out.append(r)
    return out


def _parse_ts(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, str):
        return None
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def compute_admin_analytics(now: Optional[datetime] = None) -> dict:
    """Aggregate admin analytics for the 7-day and 24-hour windows.

    Fetches the 7-day slice once and derives the 24-hour window by in-memory
    filtering — one round-trip per table, both windows from it.
    """
    now = now or datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    since_24h = now - timedelta(hours=24)
    gte7 = f"gte.{_iso(since_7d)}"

    events = _fetch("coach_events", _EVENT_COLS, {"created_at": gte7})
    check_rows = _fetch(
        "coach_events",
        _CHECK_COLS,
        {"created_at": gte7, "event_type": "eq.tool_call", "tool_name": "eq.check_moves"},
    )
    tokens = _fetch("token_usage", _TOKEN_COLS, {"created_at": gte7})

    def _agg(window_events, window_checks, window_tokens):
        return aggregate_events(window_events, window_checks, window_tokens)

    result = {
        "scope": "admin",
        "generated_at": _iso(now),
        "windows": {
            "7d": _agg(events, check_rows, tokens),
            "24h": _agg(
                _within(events, since_24h),
                _within(check_rows, since_24h),
                _within(tokens, since_24h),
            ),
        },
    }
    return result


def compute_user_analytics(user_id: str, now: Optional[datetime] = None) -> dict:
    """Per-user analytics: own turn counts, tool usage, and voice minutes."""
    now = now or datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    gte7 = f"gte.{_iso(since_7d)}"
    uid = f"eq.{user_id}"

    events = _fetch("coach_events", _EVENT_COLS, {"created_at": gte7, "user_id": uid})
    check_rows = _fetch(
        "coach_events",
        _CHECK_COLS,
        {
            "created_at": gte7,
            "user_id": uid,
            "event_type": "eq.tool_call",
            "tool_name": "eq.check_moves",
        },
    )
    agg = aggregate_events(events, check_rows, [], user_scope=True)

    # Voice minutes: sum the ledger for this user (all-time), minutes rounded.
    voice_rows = _fetch("voice_usage", "seconds", {"user_id": uid})
    total_seconds = sum(int(r.get("seconds") or 0) for r in voice_rows)

    return {
        "scope": "user",
        "user_id": user_id,
        "generated_at": _iso(now),
        "turn_counts_by_surface": agg["turn_counts_by_surface"],
        "tools": agg["tools"],
        "voice_minutes_used": round(total_seconds / 60.0, 2),
    }


# ── 60-second admin cache ──────────────────────────────────────────────


class _AdminCache:
    def __init__(self, ttl_s: float) -> None:
        self._ttl = ttl_s
        self._value: Optional[dict] = None
        self._at = 0.0
        self._lock = threading.Lock()

    def get(self) -> dict:
        now = time.monotonic()
        with self._lock:
            if self._value is not None and (now - self._at) < self._ttl:
                cached = dict(self._value)
                cached["cached"] = True
                return cached
        # Compute outside the lock; last writer wins (cheap, idempotent).
        fresh = compute_admin_analytics()
        with self._lock:
            self._value = fresh
            self._at = time.monotonic()
        result = dict(fresh)
        result["cached"] = False
        return result

    def clear(self) -> None:
        with self._lock:
            self._value = None
            self._at = 0.0


_admin_cache = _AdminCache(_ADMIN_CACHE_TTL_S)


def get_admin_analytics_cached() -> dict:
    """Admin analytics, memoised for 60s across dashboard refreshes."""
    return _admin_cache.get()
