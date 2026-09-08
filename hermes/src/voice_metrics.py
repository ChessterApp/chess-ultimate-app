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

# Directory holding the daily JSONL files, relative to the repo root.
METRICS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metrics"
)

# Maximum accepted request body size, in bytes.
MAX_BODY_BYTES = 4096

# ``end`` is the session-lifecycle beacon fired on disconnect; it carries
# ``session_ms`` (the whole session's duration) and is the hook the server uses
# to meter a voice session row.
_VALID_EVENTS = frozenset({"connect", "turn", "tool", "error", "end"})

# Non-negative millisecond timings we accept, clamped to a sane ceiling.
_MS_FIELDS = ("ttfa_ms", "connect_ms", "token_ms", "tool_ms")
_MS_MAX = 600_000  # 10 minutes — anything larger is noise
# Whole-session duration; a Live session can run to the 30-min token expiry, so
# it gets a larger ceiling than the per-turn latency fields above.
_SESSION_MS_MAX = 3_600_000  # 1 hour
_STR_MAX = 200  # cap free-form string fields (sessionId, tool_name)


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
