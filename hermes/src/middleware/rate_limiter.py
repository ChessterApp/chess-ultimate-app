"""Rate limiting middleware — sliding window per-user, per-tier.

Enforces request limits based on subscription tier:
  - free:    30 req/min
  - premium: 60 req/min
  - pro:     120 req/min

Product decision (2026-09-08): TEXT CHAT HAS NO MONTHLY QUOTA. Text messages are
unlimited; these per-minute sliding windows exist purely as an abuse guard and
are set high enough that a normal user never hits them. (Voice Mode, by
contrast, is metered by minutes per calendar month — see src/voice_quota.py.)
"""

import time
import threading
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request

# Tier limits: max requests per 60-second window. Abuse guard only — NOT a
# product quota (text chat is unlimited by the 2026-09-08 product decision).
TIER_LIMITS = {
    "free": 30,
    "premium": 60,
    "pro": 120,
}

DEFAULT_TIER = "free"
WINDOW_SECONDS = 60


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter.

    Tracks per-user request timestamps and enforces tier-based limits.
    """

    def __init__(self, tier_limits: dict[str, int] = None, window: int = WINDOW_SECONDS):
        self._tier_limits = tier_limits or TIER_LIMITS
        self._window = window
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _cleanup(self, user_id: str, now: float) -> None:
        """Remove expired timestamps from the user's window."""
        cutoff = now - self._window
        timestamps = self._requests[user_id]
        # Find first valid index
        idx = 0
        while idx < len(timestamps) and timestamps[idx] < cutoff:
            idx += 1
        self._requests[user_id] = timestamps[idx:]

    def check(self, user_id: str, tier: str = DEFAULT_TIER) -> tuple[bool, dict]:
        """Check if request is allowed. Returns (allowed, info_dict)."""
        limit = self._tier_limits.get(tier, self._tier_limits.get(DEFAULT_TIER, 5))
        now = time.monotonic()

        with self._lock:
            self._cleanup(user_id, now)
            current_count = len(self._requests[user_id])

            if current_count >= limit:
                oldest = self._requests[user_id][0] if self._requests[user_id] else now
                retry_after = int(self._window - (now - oldest)) + 1
                return False, {
                    "limit": limit,
                    "remaining": 0,
                    "retry_after": max(1, retry_after),
                    "tier": tier,
                }

            self._requests[user_id].append(now)
            return True, {
                "limit": limit,
                "remaining": limit - current_count - 1,
                "tier": tier,
            }

    def reset(self, user_id: Optional[str] = None) -> None:
        """Reset rate limit state. If user_id is None, reset all."""
        with self._lock:
            if user_id:
                self._requests.pop(user_id, None)
            else:
                self._requests.clear()


# Global instance — text chat: one request per user message.
rate_limiter = SlidingWindowRateLimiter()

# Voice tool calls fire several times per spoken turn (a single position review
# can chain board_control + analyze_position + search), so the voice tool path
# gets its own limiter with higher per-tier ceilings than text chat. Same
# sliding-window mechanism and free/premium/pro tiers.
VOICE_TOOL_TIER_LIMITS = {
    "free": 60,
    "premium": 120,
    "pro": 400,
}
voice_tool_rate_limiter = SlidingWindowRateLimiter(tier_limits=VOICE_TOOL_TIER_LIMITS)

# Live-token minting: cap how many voice sessions a user can spawn per hour by
# tier so sessions can't be created unboundedly (each mint opens a billable
# Gemini Live channel). Longer window, small per-tier counts.
VOICE_TOKEN_TIER_LIMITS = {
    "free": 10,
    "premium": 40,
    "pro": 120,
}
voice_token_rate_limiter = SlidingWindowRateLimiter(
    tier_limits=VOICE_TOKEN_TIER_LIMITS, window=3600
)


def get_user_tier(request: Request) -> str:
    """Extract subscription tier from request headers or default to 'free'."""
    return request.headers.get("x-subscription-tier", DEFAULT_TIER)


async def enforce_rate_limit(
    request: Request, limiter: Optional[SlidingWindowRateLimiter] = None
) -> dict:
    """Check rate limit for the current request. Raises 429 if exceeded.

    ``limiter`` selects which sliding-window instance to enforce against — the
    default text-chat ``rate_limiter``, or a path-specific one (voice tool /
    voice token). Returns the rate limit info dict on success.
    """
    limiter = limiter or rate_limiter
    user_id = request.headers.get("x-user-id")
    if not user_id:
        return {"limit": 0, "remaining": 0, "tier": "anonymous"}

    tier = get_user_tier(request)
    allowed, info = limiter.check(user_id, tier)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded for {tier} tier. "
                           f"Limit: {info['limit']} requests per minute.",
                "retry_after": info["retry_after"],
                "tier": tier,
            },
            headers={"Retry-After": str(info["retry_after"])},
        )

    return info
