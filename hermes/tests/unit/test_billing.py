"""Unit tests for Stripe billing integration."""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.billing import (
    create_checkout_session,
    get_subscription_status,
    handle_webhook_event,
    SubscriptionInfo,
    PRICE_IDS,
    _tier_from_price,
    _save_subscription,
)


@pytest.mark.unit
class TestSubscriptionInfo:
    """Tests for the SubscriptionInfo model."""

    def test_default_values(self):
        info = SubscriptionInfo(user_id="u1")
        assert info.tier == "free"
        assert info.status == "none"
        assert info.stripe_customer_id is None

    def test_custom_values(self):
        info = SubscriptionInfo(
            user_id="u1",
            tier="premium",
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_456",
            status="active",
        )
        assert info.tier == "premium"
        assert info.stripe_customer_id == "cus_123"


@pytest.mark.unit
class TestTierFromPrice:
    """Tests for _tier_from_price helper."""

    def test_known_price(self):
        assert _tier_from_price(PRICE_IDS["premium"]) == "premium"
        assert _tier_from_price(PRICE_IDS["pro"]) == "pro"

    def test_unknown_price(self):
        assert _tier_from_price("price_unknown") == "premium"


@pytest.mark.unit
class TestCreateCheckoutSession:
    """Tests for create_checkout_session."""

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": ""})
    def test_no_stripe_key(self):
        result = create_checkout_session("user1", "premium")
        assert "error" in result
        assert "not configured" in result["error"]

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"})
    @patch("src.billing.stripe.checkout.Session.create")
    def test_successful_checkout(self, mock_create):
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/sess_123"
        mock_session.id = "cs_123"
        mock_create.return_value = mock_session

        result = create_checkout_session("user1", "premium")
        assert result["checkout_url"] == "https://checkout.stripe.com/sess_123"
        assert result["session_id"] == "cs_123"

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"})
    def test_unknown_tier(self):
        result = create_checkout_session("user1", "mega")
        assert "error" in result
        assert "Unknown tier" in result["error"]

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"})
    @patch("src.billing.stripe.checkout.Session.create")
    def test_stripe_error(self, mock_create):
        import stripe
        mock_create.side_effect = stripe.StripeError("card declined")
        result = create_checkout_session("user1", "premium")
        assert "error" in result


@pytest.mark.unit
class TestGetSubscriptionStatus:
    """Tests for get_subscription_status."""

    @patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_no_supabase(self):
        info = get_subscription_status("user1")
        assert info.user_id == "user1"
        assert info.tier == "free"

    @patch("src.billing.httpx.get")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    def test_subscription_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{
            "user_id": "user1",
            "tier": "premium",
            "stripe_customer_id": "cus_1",
            "stripe_subscription_id": "sub_1",
            "status": "active",
        }]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = get_subscription_status("user1")
        assert info.tier == "premium"
        assert info.status == "active"

    @patch("src.billing.httpx.get")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    def test_no_subscription_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = get_subscription_status("user1")
        assert info.tier == "free"

    @patch("src.billing.httpx.get")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    def test_supabase_error(self, mock_get):
        mock_get.side_effect = Exception("connection refused")
        info = get_subscription_status("user1")
        assert info.tier == "free"


@pytest.mark.unit
class TestWebhookHandler:
    """Tests for handle_webhook_event."""

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": ""})
    def test_no_stripe_configured(self):
        result = handle_webhook_event(b"{}", "")
        assert "error" in result

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123", "STRIPE_WEBHOOK_SECRET": ""})
    @patch("src.billing._save_subscription")
    def test_checkout_completed(self, mock_save):
        mock_save.return_value = True
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "user1",
                    "customer": "cus_123",
                    "subscription": "sub_456",
                    "metadata": {"tier": "premium"},
                }
            },
        }
        result = handle_webhook_event(json.dumps(event).encode(), "")
        assert result["handled"] is True
        assert result["event"] == "checkout.session.completed"
        assert result["user_id"] == "user1"
        mock_save.assert_called_once()

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123", "STRIPE_WEBHOOK_SECRET": ""})
    @patch("src.billing._save_subscription")
    def test_subscription_updated(self, mock_save):
        mock_save.return_value = True
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_456",
                    "customer": "cus_123",
                    "status": "active",
                    "metadata": {"user_id": "user1"},
                    "items": {"data": [{"price": {"id": PRICE_IDS["pro"]}}]},
                }
            },
        }
        result = handle_webhook_event(json.dumps(event).encode(), "")
        assert result["handled"] is True

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123", "STRIPE_WEBHOOK_SECRET": ""})
    @patch("src.billing._save_subscription")
    def test_subscription_deleted(self, mock_save):
        mock_save.return_value = True
        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_456",
                    "customer": "cus_123",
                    "metadata": {"user_id": "user1"},
                }
            },
        }
        result = handle_webhook_event(json.dumps(event).encode(), "")
        assert result["handled"] is True

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123", "STRIPE_WEBHOOK_SECRET": ""})
    def test_unknown_event(self):
        event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {}},
        }
        result = handle_webhook_event(json.dumps(event).encode(), "")
        assert result["handled"] is False


@pytest.mark.unit
class TestSaveSubscription:
    """Tests for _save_subscription."""

    @patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_no_supabase(self):
        info = SubscriptionInfo(user_id="u1", tier="premium")
        assert _save_subscription(info) is False

    @patch("src.billing.httpx.post")
    @patch.dict("os.environ", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    def test_saves_to_supabase(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        info = SubscriptionInfo(user_id="u1", tier="premium", status="active")
        assert _save_subscription(info) is True
        mock_post.assert_called_once()
