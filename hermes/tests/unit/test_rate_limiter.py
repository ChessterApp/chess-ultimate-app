"""Unit tests for rate limiting middleware."""

import time
from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi import HTTPException

from src.middleware.rate_limiter import (
    SlidingWindowRateLimiter,
    TIER_LIMITS,
    DEFAULT_TIER,
    enforce_rate_limit,
    rate_limiter,
)


@pytest.mark.unit
class TestSlidingWindowRateLimiter:
    """Tests for the SlidingWindowRateLimiter class."""

    def test_allows_requests_under_limit(self):
        rl = SlidingWindowRateLimiter(tier_limits={"free": 3}, window=60)
        allowed, info = rl.check("user1", "free")
        assert allowed is True
        assert info["remaining"] == 2
        assert info["tier"] == "free"
        assert info["limit"] == 3

    def test_blocks_after_limit_exceeded(self):
        rl = SlidingWindowRateLimiter(tier_limits={"free": 2}, window=60)
        rl.check("user1", "free")
        rl.check("user1", "free")
        allowed, info = rl.check("user1", "free")
        assert allowed is False
        assert info["remaining"] == 0
        assert "retry_after" in info

    def test_different_users_independent(self):
        rl = SlidingWindowRateLimiter(tier_limits={"free": 1}, window=60)
        allowed1, _ = rl.check("user1", "free")
        allowed2, _ = rl.check("user2", "free")
        assert allowed1 is True
        assert allowed2 is True

    def test_tier_limits_respected(self):
        rl = SlidingWindowRateLimiter(
            tier_limits={"free": 2, "premium": 5, "pro": 10},
            window=60,
        )
        # Free user blocked after 2
        rl.check("free_user", "free")
        rl.check("free_user", "free")
        allowed, _ = rl.check("free_user", "free")
        assert allowed is False

        # Premium user still allowed after 2
        rl.check("prem_user", "premium")
        rl.check("prem_user", "premium")
        allowed, _ = rl.check("prem_user", "premium")
        assert allowed is True

    def test_window_expiry(self):
        rl = SlidingWindowRateLimiter(tier_limits={"free": 1}, window=1)
        rl.check("user1", "free")
        # Should be blocked
        allowed, _ = rl.check("user1", "free")
        assert allowed is False

        # Wait for window to expire
        time.sleep(1.1)
        allowed, _ = rl.check("user1", "free")
        assert allowed is True

    def test_reset_single_user(self):
        rl = SlidingWindowRateLimiter(tier_limits={"free": 1}, window=60)
        rl.check("user1", "free")
        rl.reset("user1")
        allowed, _ = rl.check("user1", "free")
        assert allowed is True

    def test_reset_all(self):
        rl = SlidingWindowRateLimiter(tier_limits={"free": 1}, window=60)
        rl.check("user1", "free")
        rl.check("user2", "free")
        rl.reset()
        allowed1, _ = rl.check("user1", "free")
        allowed2, _ = rl.check("user2", "free")
        assert allowed1 is True
        assert allowed2 is True

    def test_unknown_tier_uses_default(self):
        rl = SlidingWindowRateLimiter(tier_limits={"free": 2}, window=60)
        # Unknown tier falls back to free limit
        allowed, info = rl.check("user1", "nonexistent")
        assert allowed is True
        assert info["limit"] == 2

    def test_remaining_decrements(self):
        rl = SlidingWindowRateLimiter(tier_limits={"free": 3}, window=60)
        _, info1 = rl.check("user1", "free")
        assert info1["remaining"] == 2
        _, info2 = rl.check("user1", "free")
        assert info2["remaining"] == 1
        _, info3 = rl.check("user1", "free")
        assert info3["remaining"] == 0

    def test_default_tier_limits(self):
        assert TIER_LIMITS["free"] == 5
        assert TIER_LIMITS["premium"] == 30
        assert TIER_LIMITS["pro"] == 100
        assert DEFAULT_TIER == "free"


@pytest.mark.unit
class TestEnforceRateLimit:
    """Tests for the enforce_rate_limit async function."""

    @pytest.mark.asyncio
    async def test_anonymous_user_skipped(self):
        request = MagicMock()
        request.headers = {}  # No X-User-Id
        result = await enforce_rate_limit(request)
        assert result["tier"] == "anonymous"

    @pytest.mark.asyncio
    async def test_rate_limit_raises_429(self):
        # Create a fresh limiter with limit=1
        from src.middleware import rate_limiter as rl_module
        original = rl_module.rate_limiter
        rl_module.rate_limiter = SlidingWindowRateLimiter(tier_limits={"free": 1}, window=60)
        try:
            request = MagicMock()
            request.headers = {"x-user-id": "test-429", "x-subscription-tier": "free"}

            # First request should succeed
            await enforce_rate_limit(request)

            # Second should raise 429
            with pytest.raises(HTTPException) as exc_info:
                await enforce_rate_limit(request)
            assert exc_info.value.status_code == 429
            assert "rate_limit_exceeded" in str(exc_info.value.detail)
        finally:
            rl_module.rate_limiter = original
