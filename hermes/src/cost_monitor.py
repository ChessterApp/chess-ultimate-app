"""Cost monitoring — tracks LLM token usage per user per session.

Stores usage data in Supabase (token_usage table) and provides
a GET /api/coach/usage endpoint for spend breakdown.
"""

import logging
import os
import threading
import time
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from src.model_prices import DEFAULT_PRICE, estimate_cost_usd, price_for

# Kept for callers/tests that import the old names: $ per 1K tokens, derived
# from the per-1M table in src/model_prices.py (the single place to edit).
DEFAULT_COST = {"input": DEFAULT_PRICE["input"] / 1000, "output": DEFAULT_PRICE["output"] / 1000}

# Synthetic model label for voice (Gemini Live) rows. Exact audio token counts
# aren't available server-side, so voice rows carry 0 tokens and record the
# tool name / session duration instead so spend can be estimated downstream.
VOICE_MODEL = "gemini-live-voice"


class TokenUsageRecord(BaseModel):
    user_id: str
    session_id: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    surface: str = "text"
    # Voice-only metering fields (nullable; omitted from the text insert):
    #   tool_name    — the tool a voice tool-call row is for
    #   duration_ms  — a voice session's length, on the session-end row
    tool_name: Optional[str] = None
    duration_ms: Optional[int] = None
    # Joins the row to coach_messages / coach_events for the same turn.
    turn_id: Optional[str] = None
    # Part of prompt_tokens served from the provider's prompt cache.
    cached_tokens: int = 0
    timestamp: float = Field(default_factory=time.time)


class CostMonitor:
    """Tracks token usage per user and persists to Supabase."""

    def __init__(self):
        self._records: list[TokenUsageRecord] = []

    def record_usage(
        self,
        user_id: str,
        session_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        surface: str = "text",
        tool_name: Optional[str] = None,
        duration_ms: Optional[int] = None,
        turn_id: Optional[str] = None,
        cached_tokens: int = 0,
    ) -> TokenUsageRecord:
        """Record a token usage event and persist to Supabase.

        ``surface`` is the coach surface the turn came from (``text`` chat,
        ``analysis``, ``review``, or ``voice``) so spend can be broken down per
        feature. ``tool_name`` / ``duration_ms`` are voice-only metering fields
        (a voice tool-call row names the tool; a voice session-end row carries
        the session length) and are omitted from the persisted row when unset.
        """
        total = prompt_tokens + completion_tokens
        cost = estimate_cost_usd(model, prompt_tokens, completion_tokens, cached_tokens)

        record = TokenUsageRecord(
            user_id=user_id,
            session_id=session_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost_usd=round(cost, 6),
            surface=surface,
            tool_name=tool_name,
            duration_ms=duration_ms,
            turn_id=turn_id,
            cached_tokens=cached_tokens,
        )
        self._records.append(record)
        self._persist(record)
        return record

    def get_user_usage(self, user_id: str) -> dict:
        """Get aggregated usage for a user from in-memory records."""
        user_records = [r for r in self._records if r.user_id == user_id]
        total_prompt = sum(r.prompt_tokens for r in user_records)
        total_completion = sum(r.completion_tokens for r in user_records)
        total_cost = sum(r.estimated_cost_usd for r in user_records)

        by_model: dict[str, dict] = {}
        for r in user_records:
            if r.model not in by_model:
                by_model[r.model] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "request_count": 0,
                }
            by_model[r.model]["prompt_tokens"] += r.prompt_tokens
            by_model[r.model]["completion_tokens"] += r.completion_tokens
            by_model[r.model]["total_tokens"] += r.total_tokens
            by_model[r.model]["estimated_cost_usd"] += r.estimated_cost_usd
            by_model[r.model]["request_count"] += 1

        # Round costs
        for model_data in by_model.values():
            model_data["estimated_cost_usd"] = round(model_data["estimated_cost_usd"], 6)

        return {
            "user_id": user_id,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "total_estimated_cost_usd": round(total_cost, 6),
            "request_count": len(user_records),
            "by_model": by_model,
        }

    def _persist(self, record: TokenUsageRecord) -> None:
        """Persist a usage record to Supabase (fire-and-forget)."""
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return

        payload = {
            "user_id": record.user_id,
            "session_id": record.session_id,
            "model": record.model,
            "prompt_tokens": record.prompt_tokens,
            "completion_tokens": record.completion_tokens,
            "total_tokens": record.total_tokens,
            "estimated_cost_usd": record.estimated_cost_usd,
            "surface": record.surface,
        }
        # Voice-only columns are sent only when set, so the text/analysis insert
        # is byte-identical to before (and needs no schema change).
        if record.tool_name is not None:
            payload["tool_name"] = record.tool_name
        if record.duration_ms is not None:
            payload["duration_ms"] = record.duration_ms
        if record.turn_id:
            payload["turn_id"] = record.turn_id
        if record.cached_tokens:
            payload["cached_tokens"] = record.cached_tokens

        try:
            resp = httpx.post(
                f"{url}/rest/v1/token_usage",
                json=payload,
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                timeout=5,
            )
            if resp.status_code >= 400:
                # A rejected row (e.g. a column the migration hasn't added yet)
                # used to vanish without a trace; the dashboard then under-reports.
                logger.error(
                    "token_usage insert rejected: %s %s", resp.status_code, resp.text[:300]
                )
        except Exception:
            logger.exception("Failed to persist token usage")


# Global instance
cost_monitor = CostMonitor()


def record_voice_event(
    user_id: str,
    session_id: Optional[str],
    *,
    tool_name: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Fire-and-forget: record one voice metering row (``surface="voice"``).

    Used for both a voice tool-call row (pass ``tool_name``) and a voice
    session-end row (pass ``duration_ms``). Runs the persist on a daemon thread
    so the blocking Supabase write never slows the request path, and swallows
    any failure — metering must never break the voice session.
    """

    def _run() -> None:
        try:
            cost_monitor.record_usage(
                user_id=user_id,
                session_id=session_id or "",
                model=VOICE_MODEL,
                prompt_tokens=0,
                completion_tokens=0,
                surface="voice",
                tool_name=tool_name,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.exception("voice usage recording failed")

    threading.Thread(target=_run, daemon=True).start()
