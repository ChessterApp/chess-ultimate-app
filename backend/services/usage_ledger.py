"""Token-usage ledger for the Flask side (vision calls).

Hermes records every coach turn into Supabase ``token_usage``; the Flask
vision endpoints (photo→FEN, scoresheet→PGN) only logged their usage, so the
most expensive single calls in the system never reached the dashboard. This
writes the same row shape Hermes does, fire-and-forget, never raising.

Prices: USD per 1M tokens, OpenRouter list prices as of 2026-09-20. The
authoritative table is hermes/src/model_prices.py; keep the vision models
here in step with it.
"""

import logging
import os
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MODEL_PRICES = {
    "google/gemini-3-flash-preview": {"input": 0.50, "output": 3.00},
    "google/gemini-3.8-flash": {"input": 0.75, "output": 3.75},
    "google/gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
    "google/gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    "google/gemini-pro-latest": {"input": 2.00, "output": 12.00},
    "google/gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "openai/gpt-5.4-mini": {"input": 0.75, "output": 4.50},
}
DEFAULT_PRICE = {"input": 1.00, "output": 5.00}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = MODEL_PRICES.get((model or "").split(":")[0].lower(), DEFAULT_PRICE)
    return (
        max(prompt_tokens, 0) * price["input"] / 1_000_000
        + max(completion_tokens, 0) * price["output"] / 1_000_000
    )


def record_openrouter_usage(
    response_data: dict,
    *,
    model: str,
    surface: str,
    user_id: Optional[str] = None,
    session_id: str = "",
) -> None:
    """Record the ``usage`` block of one OpenRouter response into token_usage.

    Runs on a daemon thread; a missing Supabase config or a rejected insert is
    logged and otherwise ignored — accounting must never break the request.
    """
    try:
        usage = (response_data or {}).get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    except Exception:
        return
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return

    row = {
        "user_id": user_id or "anonymous",
        "session_id": session_id or "",
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": round(estimate_cost_usd(model, prompt_tokens, completion_tokens), 6),
        "surface": surface,
    }
    if cached:
        row["cached_tokens"] = cached

    def _run() -> None:
        try:
            resp = requests.post(
                f"{url}/rest/v1/token_usage",
                json=row,
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                timeout=5,
            )
            if resp.status_code >= 400:
                logger.error("token_usage insert rejected: %s %s", resp.status_code, resp.text[:300])
        except Exception:
            logger.exception("token usage recording failed")

    threading.Thread(target=_run, daemon=True).start()
