"""Price table for the models the coach can be routed to.

USD per 1M tokens, OpenRouter list prices as of 2026-09-20
(https://openrouter.ai/anthropic, https://openrouter.ai/google,
https://openrouter.ai/openai). Update this file when models change — the
usage dashboard is only as honest as this table. Unknown models fall back to
``DEFAULT_PRICE`` and are logged once so they show up in the logs instead of
silently being billed at a made-up rate.

Cached-input prices are kept for the day prompt caching is verified
(``cache_read`` / ``cache_write`` tokens are not recorded yet).
"""

import logging
import re

logger = logging.getLogger(__name__)

# {model: {"input": $/1M, "output": $/1M, "cache_read": $/1M or None}}
MODEL_PRICES: dict[str, dict] = {
    # ── Google ────────────────────────────────────────────────────────
    "google/gemini-2.5-flash": {"input": 0.30, "output": 2.50, "cache_read": 0.075},   # retires 2026-10-16
    "google/gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cache_read": 0.31},
    "google/gemini-3-flash-preview": {"input": 0.50, "output": 3.00, "cache_read": None},
    "google/gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50, "cache_read": None},
    "google/gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00, "cache_read": None},
    "google/gemini-3.5-flash": {"input": 1.50, "output": 9.00, "cache_read": None},
    "google/gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50, "cache_read": None},
    "google/gemini-3.6-flash": {"input": 0.75, "output": 3.75, "cache_read": None},
    "google/gemini-3.7-flash": {"input": 0.75, "output": 3.75, "cache_read": None},
    "google/gemini-3.8-flash": {"input": 0.75, "output": 3.75, "cache_read": 0.075},
    "google/gemini-pro-latest": {"input": 2.00, "output": 12.00, "cache_read": None},
    "google/gemini-embedding-2": {"input": 0.20, "output": 0.0, "cache_read": None},
    # ── Anthropic ─────────────────────────────────────────────────────
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "anthropic/claude-sonnet-4-5": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "anthropic/claude-sonnet-4.5": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "anthropic/claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "anthropic/claude-sonnet-4.6": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "anthropic/claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20},
    "anthropic/claude-opus-4": {"input": 15.00, "output": 75.00, "cache_read": 1.50},
    "anthropic/claude-opus-4.1": {"input": 15.00, "output": 75.00, "cache_read": 1.50},
    "anthropic/claude-opus-4.5": {"input": 5.00, "output": 25.00, "cache_read": 0.50},
    "anthropic/claude-opus-4.6": {"input": 5.00, "output": 25.00, "cache_read": 0.50},
    "anthropic/claude-opus-4.7": {"input": 5.00, "output": 25.00, "cache_read": 0.50},
    "anthropic/claude-opus-4.8": {"input": 5.00, "output": 25.00, "cache_read": 0.50},
    "anthropic/claude-opus-5": {"input": 5.00, "output": 25.00, "cache_read": 0.50},
    "anthropic/claude-haiku-4.5": {"input": 1.00, "output": 5.00, "cache_read": 0.10},
    "anthropic/claude-fable-5": {"input": 10.00, "output": 50.00, "cache_read": 1.00},
    "anthropic/claude-fable-5.1": {"input": 10.00, "output": 50.00, "cache_read": 0.25},
    # ── DeepSeek / Moonshot / Zhipu (open-weight; OpenRouter list prices 2026-09-23) ──
    "deepseek/deepseek-v4.1-flash": {"input": 0.30, "output": 1.20, "cache_read": 0.006},
    "deepseek/deepseek-v4-flash-0731": {"input": 0.04, "output": 0.16, "cache_read": 0.016},
    "deepseek/deepseek-v4-pro-0813": {"input": 1.32, "output": 3.96, "cache_read": 0.044},
    "moonshotai/kimi-k3": {"input": 1.70, "output": 8.50, "cache_read": 0.17},
    "z-ai/glm-5.3": {"input": 0.91, "output": 2.86, "cache_read": 0.169},
    "z-ai/glm-5.3-flash": {"input": 0.09, "output": 0.30, "cache_read": 0.018},
    "qwen/qwen3.8-flash": {"input": 0.15, "output": 0.47, "cache_read": 0.016},
    # open-weight, self-host candidates (OpenRouter list prices 2026-09-23)
    "qwen/qwen3.8-27b": {"input": 0.20, "output": 2.50, "cache_read": 0.05},
    "google/gemma-4-31b-it": {"input": 0.09, "output": 0.34, "cache_read": None},
    "google/gemma-4-26b-a4b-it": {"input": 0.09, "output": 0.30, "cache_read": None},
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60, "cache_read": None},
    "openai/gpt-oss-20b": {"input": 0.03, "output": 0.13, "cache_read": None},
    "nvidia/nemotron-3-super-120b-a12b": {"input": 0.08, "output": 0.45, "cache_read": None},
    "mistralai/mistral-small-2603": {"input": 0.15, "output": 0.60, "cache_read": None},
    "meta-llama/llama-4-maverick": {"input": 0.20, "output": 0.80, "cache_read": None},
    "qwen/qwen3.8-2.4t-a95b": {"input": 2.00, "output": 6.00, "cache_read": 0.25},
    "minimax/minimax-m3": {"input": 0.30, "output": 1.20, "cache_read": 0.06},
    "nvidia/nemotron-3-ultra-550b-a55b": {"input": 0.60, "output": 2.40, "cache_read": None},
    # ── OpenAI ────────────────────────────────────────────────────────
    "openai/gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cache_read": None},
    "openai/gpt-5.6-sol": {"input": 2.00, "output": 10.00, "cache_read": None},
    "openai/gpt-5.6-terra": {"input": 2.00, "output": 12.00, "cache_read": None},
    "openai/gpt-5.4-nano": {"input": 0.20, "output": 1.25, "cache_read": None},
    "openai/gpt-5.4-mini": {"input": 0.75, "output": 4.50, "cache_read": None},
    "openai/gpt-5.4": {"input": 2.50, "output": 15.00, "cache_read": None},
    "openai/gpt-5-mini": {"input": 0.25, "output": 2.00, "cache_read": None},
    "openai/gpt-5-nano": {"input": 0.05, "output": 0.40, "cache_read": None},
    "openai/text-embedding-3-small": {"input": 0.02, "output": 0.0, "cache_read": None},
    # ── Voice (Gemini Live, billed by Google directly, not via OpenRouter).
    # Audio tokens: ~$3 input / ~$12 output per 1M on the 2.5 Flash Live tier;
    # the 3.1 preview has no published list price yet — treat as an estimate.
    "gemini-3.1-flash-live-preview": {"input": 3.00, "output": 12.00, "cache_read": None},
    "gemini-live-voice": {"input": 3.00, "output": 12.00, "cache_read": None},
}

# Used when the model is not in the table. Deliberately on the expensive side
# so an unpriced model inflates the dashboard rather than hiding.
DEFAULT_PRICE = {"input": 1.00, "output": 5.00, "cache_read": None}

_warned: set = set()

# OpenRouter routing suffixes / variants that do not change the price.
_VARIANT_RE = re.compile(r"(:[a-z]+|\[1m\]|:online|:extended|:nitro|:floor)+$")


def normalize_model(model: str) -> str:
    """Strip OpenRouter routing variants: ``anthropic/claude-opus-5:nitro`` → ``anthropic/claude-opus-5``."""
    return _VARIANT_RE.sub("", (model or "").strip().lower())


def price_for(model: str) -> dict:
    """Return the price row for *model* (exact, then dotted/dashed twin, then default)."""
    key = normalize_model(model)
    if key in MODEL_PRICES:
        return MODEL_PRICES[key]
    twin = key.replace("-4-", "-4.").replace("-5-", "-5.")  # sonnet-4-5 ↔ sonnet-4.5
    if twin in MODEL_PRICES:
        return MODEL_PRICES[twin]
    if key not in _warned:
        _warned.add(key)
        logger.warning("model_prices: no price for %r, using DEFAULT_PRICE", model)
    return DEFAULT_PRICE


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int,
                      cached_tokens: int = 0) -> float:
    """USD for one call. ``cached_tokens`` are the part of ``prompt_tokens`` read from cache."""
    p = price_for(model)
    cached = min(max(cached_tokens, 0), max(prompt_tokens, 0))
    fresh = max(prompt_tokens, 0) - cached
    cache_rate = p.get("cache_read")
    if cache_rate is None:
        cache_rate = p["input"]
    return (
        fresh * p["input"] / 1_000_000
        + cached * cache_rate / 1_000_000
        + max(completion_tokens, 0) * p["output"] / 1_000_000
    )
