"""Voice latency metrics ingest.

The voice coach (Gemini Live) client posts small latency beacons — time to
first audio, connect time, per-tool timings — to ``POST /api/coach/metrics``.
This module owns the sanitising + append-to-JSONL logic so the endpoint stays a
thin wrapper.

Best-effort by design: every write is wrapped so a bad payload or a filesystem
hiccup never propagates a 5xx to the client. Bad fields are clamped or dropped.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("hermes.voice_metrics")

# Phase-2 event taxonomy shared with the browser voice client (useGeminiLive) and
# the server-side mint path (live-token/route.ts posts ``mint_rejected`` here).
# ``end`` remains the metering lifecycle beacon (carries session_ms); the
# ``session_end`` beacon is the event-log lifecycle signal (carries end_reason).

# Directory holding the daily JSONL files, relative to the repo root.
METRICS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metrics"
)

# Maximum accepted request body size, in bytes.
MAX_BODY_BYTES = 4096

# ``end`` is the session-lifecycle beacon fired on disconnect; it carries
# ``session_ms`` (the whole session's duration) and is the hook the server uses
# to meter a voice session row.
_VALID_EVENTS = frozenset(
    {
        "connect",
        "turn",
        "tool",
        "error",
        "end",
        # Phase 2 additions.
        "reconnect",
        "tool_timeout",
        "barge_in",
        "drop",
        "session_end",
        "mint_rejected",
    }
)

# Non-negative millisecond timings we accept, clamped to a sane ceiling.
_MS_FIELDS = ("ttfa_ms", "connect_ms", "token_ms", "tool_ms")
_MS_MAX = 600_000  # 10 minutes — anything larger is noise
# Whole-session duration; a Live session can run to the 30-min token expiry, so
# it gets a larger ceiling than the per-turn latency fields above.
_SESSION_MS_MAX = 3_600_000  # 1 hour
_STR_MAX = 200  # cap free-form string fields (sessionId, tool_name)
# Failure cause strings get a larger cap so an ``error`` beacon keeps a usable
# message (DOMException name + text) instead of being clipped to nothing.
_ERR_MAX = 500


def _clamp_int(value: Any, lo: int, hi: int) -> Optional[int]:
    """Coerce *value* to an int in [lo, hi], or None if not numeric."""
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    try:
        return max(lo, min(hi, int(value)))
    except (ValueError, OverflowError):
        return None


def _clamp_str(value: Any) -> Optional[str]:
    """Return a length-capped string, or None if *value* is not a string."""
    if not isinstance(value, str):
        return None
    return value[:_STR_MAX]


def _clamp_err(value: Any) -> Optional[str]:
    """Return a failure-cause string capped at ``_ERR_MAX``, or None."""
    if not isinstance(value, str) or not value:
        return None
    return value[:_ERR_MAX]


def _clamp_bool(value: Any) -> Optional[bool]:
    """Return *value* only when it is a genuine bool, else None."""
    return value if isinstance(value, bool) else None


def _compact(d: dict) -> dict:
    """Drop None-valued keys so events carry only present fields."""
    return {k: v for k, v in d.items() if v is not None}


def sanitize_metric(payload: Any) -> Optional[dict]:
    """Validate and clamp a raw metric payload into a record to persist.

    Returns the sanitised dict, or ``None`` when the payload is unusable
    (not an object, missing sessionId, or an unknown event) — the caller then
    drops it silently.
    """
    if not isinstance(payload, dict):
        return None

    session_id = _clamp_str(payload.get("sessionId"))
    if not session_id:
        return None

    event = payload.get("event")
    if event not in _VALID_EVENTS:
        return None

    record: dict[str, Any] = {"sessionId": session_id, "event": event}

    turn = _clamp_int(payload.get("turn"), 0, 100_000)
    if turn is not None:
        record["turn"] = turn

    for field in _MS_FIELDS:
        ms = _clamp_int(payload.get(field), 0, _MS_MAX)
        if ms is not None:
            record[field] = ms

    session_ms = _clamp_int(payload.get("session_ms"), 0, _SESSION_MS_MAX)
    if session_ms is not None:
        record["session_ms"] = session_ms

    tool_name = _clamp_str(payload.get("tool_name"))
    if tool_name:
        record["tool_name"] = tool_name

    prompt_bytes = _clamp_int(payload.get("prompt_bytes"), 0, 10_000_000)
    if prompt_bytes is not None:
        record["prompt_bytes"] = prompt_bytes

    # Phase-2 correlation + outcome fields. Kept strictly typed so the JSONL
    # spool never turns into an arbitrary-payload passthrough.
    turn_id = _clamp_str(payload.get("turn_id"))
    if turn_id:
        record["turn_id"] = turn_id

    ok = _clamp_bool(payload.get("ok"))
    if ok is not None:
        record["ok"] = ok

    error_code = _clamp_str(payload.get("error_code"))
    if error_code:
        record["error_code"] = error_code

    # An ``error`` beacon's cause string (DOMException name+message) is retained
    # — this is the sanitizer bug Phase 2 fixes (it used to be dropped).
    error = _clamp_err(payload.get("error"))
    if error:
        record["error"] = error

    end_reason = _clamp_str(payload.get("end_reason"))
    if end_reason:
        record["end_reason"] = end_reason

    reason = _clamp_str(payload.get("reason"))
    if reason:
        record["reason"] = reason

    # Client timestamp is passed through when it's a number/string; otherwise
    # we stamp server-side so every record is time-ordered.
    ts = payload.get("ts")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        record["ts"] = ts
    elif isinstance(ts, str) and ts:
        record["ts"] = ts[:_STR_MAX]
    else:
        record["ts"] = datetime.now(timezone.utc).isoformat()

    return record


def beacon_to_event(payload: Any, user_id: Optional[str]) -> Optional[dict]:
    """Map one voice beacon to ``event_logger.log_event`` kwargs (Phase 2, Task 2).

    Returns the kwargs dict for :func:`src.event_logger.log_event`, or ``None``
    when the beacon has no coach-event counterpart (``end`` is metering-only) or
    would double-log a call the server already recorded (a *successful* ``tool``
    beacon — the authoritative row is written server-side in ``tool_bridge``).

    Unlike :func:`sanitize_metric` this does NOT require a ``sessionId`` — the
    server-side ``mint_rejected`` beacon fires before a voice session exists — and
    it stamps the authenticated ``user_id`` from the request, never the browser.
    """
    if not isinstance(payload, dict):
        return None
    event = payload.get("event")
    if event not in _VALID_EVENTS:
        return None

    session_id = _clamp_str(payload.get("sessionId"))
    turn_id = _clamp_str(payload.get("turn_id"))
    tool_name = _clamp_str(payload.get("tool_name"))
    connect_ms = _clamp_int(payload.get("connect_ms"), 0, _MS_MAX)
    token_ms = _clamp_int(payload.get("token_ms"), 0, _MS_MAX)
    ttfa_ms = _clamp_int(payload.get("ttfa_ms"), 0, _MS_MAX)
    tool_ms = _clamp_int(payload.get("tool_ms"), 0, _MS_MAX)
    session_ms = _clamp_int(payload.get("session_ms"), 0, _SESSION_MS_MAX)
    prompt_bytes = _clamp_int(payload.get("prompt_bytes"), 0, 10_000_000)
    turn = _clamp_int(payload.get("turn"), 0, 100_000)
    ok = _clamp_bool(payload.get("ok"))
    error = _clamp_err(payload.get("error"))
    error_code = _clamp_str(payload.get("error_code"))
    end_reason = _clamp_str(payload.get("end_reason"))
    reason = _clamp_str(payload.get("reason"))

    base = {
        "user_id": user_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "surface": "voice",
    }

    if event == "connect":
        return {**base, "event_type": "voice_connect", "duration_ms": connect_ms,
                "payload": _compact({"connect_ms": connect_ms, "token_ms": token_ms,
                                     "prompt_bytes": prompt_bytes})}
    if event == "reconnect":
        return {**base, "event_type": "voice_reconnect", "duration_ms": connect_ms,
                "payload": _compact({"connect_ms": connect_ms, "token_ms": token_ms})}
    if event in ("error", "drop"):
        return {**base, "event_type": "voice_drop", "severity": "error", "ok": False,
                "error_code": error_code or "voice_error",
                "payload": _compact({"cause": error})}
    if event == "tool":
        # Successful voice tool calls are logged authoritatively server-side
        # (tool_bridge). Only surface client-observed FAILURES here — a proxy /
        # rate-limit rejection the server never got to log — marked source=beacon.
        if ok is not False:
            return None
        return {**base, "event_type": "tool_call", "severity": "warn",
                "tool_name": tool_name, "duration_ms": tool_ms, "ok": False,
                "error_code": error_code or "tool_error",
                "payload": _compact({"source": "beacon", "tool_ms": tool_ms})}
    if event == "tool_timeout":
        return {**base, "event_type": "tool_timeout", "severity": "warn",
                "tool_name": tool_name, "duration_ms": tool_ms, "ok": False,
                "error_code": "timeout",
                "payload": _compact({"source": "beacon", "tool_ms": tool_ms})}
    if event == "barge_in":
        return {**base, "event_type": "barge_in",
                "payload": _compact({"turn": turn})}
    if event == "turn":
        return {**base, "event_type": "turn_end", "duration_ms": ttfa_ms,
                "payload": _compact({"ttfa_ms": ttfa_ms, "turn": turn})}
    if event == "session_end":
        return {**base, "event_type": "session_end", "duration_ms": session_ms,
                "payload": _compact({"session_ms": session_ms, "end_reason": end_reason})}
    if event == "mint_rejected":
        r = reason or "error"
        severity = "warn" if r in ("quota_exhausted", "rate_limited") else "error"
        return {**base, "event_type": "mint_rejected", "severity": severity,
                "ok": False, "error_code": r, "payload": _compact({"reason": r})}
    # 'end' is metering-only (record_voice_event handles it) — no coach event.
    return None


def _metrics_path(now: Optional[datetime] = None) -> str:
    """Return today's JSONL file path (UTC date), creating the dir if needed."""
    now = now or datetime.now(timezone.utc)
    os.makedirs(METRICS_DIR, exist_ok=True)
    return os.path.join(METRICS_DIR, f"voice-latency-{now:%Y-%m-%d}.jsonl")


def record_metric(payload: Any) -> bool:
    """Sanitise *payload* and append it as one JSON line. Never raises.

    Returns True when a line was written, False when the payload was dropped or
    the write failed — the endpoint returns 204 either way.
    """
    try:
        record = sanitize_metric(payload)
        if record is None:
            return False
        path = _metrics_path()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:  # pragma: no cover - defensive: metrics must never 5xx
        logger.exception("Failed to record voice metric")
        return False
