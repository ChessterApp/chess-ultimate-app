"""Cost monitoring — tracks LLM token usage per user per session.

Stores usage data in Supabase (token_usage table) and provides
a GET /api/coach/usage endpoint for spend breakdown.
"""

import logging
import os
import time
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Approximate cost per 1K tokens (USD) by model tier
MODEL_COSTS = {
    "google/gemini-2.5-flash": {"input": 0.00015, "output": 0.0006},
    "anthropic/claude-sonnet-4-5": {"input": 0.003, "output": 0.015},
    "anthropic/claude-opus-4": {"input": 0.015, "output": 0.075},
}

DEFAULT_COST = {"input": 0.001, "output": 0.005}


class TokenUsageRecord(BaseModel):
    user_id: str
    session_id: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
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
    ) -> TokenUsageRecord:
        """Record a token usage event and persist to Supabase."""
        total = prompt_tokens + completion_tokens
        cost_rates = MODEL_COSTS.get(model, DEFAULT_COST)
        cost = (
            (prompt_tokens / 1000) * cost_rates["input"]
            + (completion_tokens / 1000) * cost_rates["output"]
        )

        record = TokenUsageRecord(
            user_id=user_id,
            session_id=session_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost_usd=round(cost, 6),
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

        try:
            httpx.post(
                f"{url}/rest/v1/token_usage",
                json={
                    "user_id": record.user_id,
                    "session_id": record.session_id,
                    "model": record.model,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "total_tokens": record.total_tokens,
                    "estimated_cost_usd": record.estimated_cost_usd,
                },
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                timeout=5,
            )
        except Exception:
            logger.exception("Failed to persist token usage")


# Global instance
cost_monitor = CostMonitor()
