"""Unit tests for the enhanced /health endpoint and new API routes."""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.server import app
from src.sessions import session_store


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Clear session store between tests."""
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


USER_HEADERS = {"X-User-Id": "test-user-health"}


@pytest.mark.unit
class TestHealthEndpoint:
    """Tests for the enhanced GET /health endpoint."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_health_returns_ok(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "hermes-chess-coach"

    def test_health_includes_uptime(self):
        resp = self.client.get("/health")
        body = resp.json()
        assert "uptime_seconds" in body
        assert body["uptime_seconds"] >= 0

    def test_health_includes_memory(self):
        resp = self.client.get("/health")
        body = resp.json()
        assert "memory_mb" in body
        assert body["memory_mb"] > 0

    def test_health_includes_stockfish_status(self):
        resp = self.client.get("/health")
        body = resp.json()
        assert "stockfish" in body
        assert "available" in body["stockfish"]
        assert "circuit" in body["stockfish"]

    def test_health_includes_supabase_status(self):
        resp = self.client.get("/health")
        body = resp.json()
        assert "supabase" in body
        assert "configured" in body["supabase"]
        assert "circuit" in body["supabase"]


@pytest.mark.unit
class TestRequestIdMiddleware:
    """Tests for the request ID middleware."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_response_has_request_id(self):
        resp = self.client.get("/health")
        assert "x-request-id" in resp.headers

    def test_custom_request_id_preserved(self):
        resp = self.client.get("/health", headers={"X-Request-Id": "custom-123"})
        assert resp.headers["x-request-id"] == "custom-123"


@pytest.mark.unit
class TestUsageEndpoint:
    """Tests for GET /api/coach/usage."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_usage_requires_user_id(self):
        resp = self.client.get("/api/coach/usage")
        assert resp.status_code == 401

    def test_usage_returns_empty(self):
        resp = self.client.get("/api/coach/usage", headers=USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "test-user-health"
        assert body["total_tokens"] == 0
        assert body["request_count"] == 0


@pytest.mark.unit
class TestAnalyticsEndpoint:
    """Tests for GET /api/coach/analytics."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_analytics_requires_user_id(self):
        resp = self.client.get("/api/coach/analytics")
        assert resp.status_code == 401

    def test_analytics_returns_data(self):
        resp = self.client.get("/api/coach/analytics", headers=USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "total_events" in body
        assert "unique_users" in body
        assert "tool_invocations" in body


@pytest.mark.unit
class TestSubscriptionEndpoint:
    """Tests for GET /api/coach/subscription-status."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_subscription_requires_user_id(self):
        resp = self.client.get("/api/coach/subscription-status")
        assert resp.status_code == 401

    @patch("src.server.get_subscription_status")
    def test_subscription_status(self, mock_status):
        from src.billing import SubscriptionInfo
        mock_status.return_value = SubscriptionInfo(
            user_id="test-user-health",
            tier="premium",
            status="active",
        )
        resp = self.client.get("/api/coach/subscription-status", headers=USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["tier"] == "premium"
        assert body["status"] == "active"


@pytest.mark.unit
class TestCheckoutEndpoint:
    """Tests for POST /api/coach/create-checkout-session."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_checkout_requires_user_id(self):
        resp = self.client.post(
            "/api/coach/create-checkout-session",
            json={"tier": "premium"},
        )
        assert resp.status_code == 401

    @patch("src.server.create_checkout_session")
    def test_checkout_success(self, mock_checkout):
        mock_checkout.return_value = {
            "checkout_url": "https://checkout.stripe.com/test",
            "session_id": "cs_test",
        }
        resp = self.client.post(
            "/api/coach/create-checkout-session",
            headers=USER_HEADERS,
            json={"tier": "premium"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "checkout_url" in body

    @patch("src.server.create_checkout_session")
    def test_checkout_error(self, mock_checkout):
        mock_checkout.return_value = {"error": "Stripe not configured"}
        resp = self.client.post(
            "/api/coach/create-checkout-session",
            headers=USER_HEADERS,
            json={"tier": "premium"},
        )
        assert resp.status_code == 400
