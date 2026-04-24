"""Rate limiting middleware — sliding window per-user, per-tier.

Enforces request limits based on subscription tier:
  - free:    5 req/min
  - premium: 30 req/min
  - pro:     100 req/min
"""

import time
import threading
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request

# Tier limits: max requests per 60-second window
TIER_LIMITS = {
    "free": 5,
    "premium": 30,
    "pro": 100,
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


# Global instance
rate_limiter = SlidingWindowRateLimiter()


def get_user_tier(request: Request) -> str:
    """Extract subscription tier from request headers or default to 'free'."""
    return request.headers.get("x-subscription-tier", DEFAULT_TIER)


async def enforce_rate_limit(request: Request) -> dict:
    """Check rate limit for the current request. Raises 429 if exceeded.

    Returns rate limit info dict on success.
    """
    user_id = request.headers.get("x-user-id")
    if not user_id:
        return {"limit": 0, "remaining": 0, "tier": "anonymous"}

    tier = get_user_tier(request)
    allowed, info = rate_limiter.check(user_id, tier)

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
