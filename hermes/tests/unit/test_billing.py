"""Unit tests for Whop billing integration."""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.billing import (
    create_checkout_session,
    get_subscription_status,
    handle_webhook_event,
    SubscriptionInfo,
    PLAN_IDS,
    _plan_type_from_id,
    _save_subscription,
)


@pytest.mark.unit
class TestSubscriptionInfo:
    """Tests for the SubscriptionInfo model."""

    def test_default_values(self):
        info = SubscriptionInfo(user_id="u1")
        assert info.tier == "free"
        assert info.status == "none"
        assert info.whop_membership_id is None
        assert info.whop_user_id is None

    def test_custom_values(self):
        info = SubscriptionInfo(
            user_id="u1",
            tier="monthly",
            whop_membership_id="mem_123",
            whop_user_id="usr_456",
            status="active",
        )
        assert info.tier == "monthly"
        assert info.whop_membership_id == "mem_123"
        assert info.whop_user_id == "usr_456"


@pytest.mark.unit
class TestPlanTypeFromId:
    """Tests for _plan_type_from_id helper."""

    @patch.dict("os.environ", {
        "WHOP_WEEKLY_PLAN": "plan_week",
        "WHOP_MONTHLY_PLAN": "plan_month",
        "WHOP_YEARLY_PLAN": "plan_year",
    })
    def test_known_plans(self):
        # Reload PLAN_IDS by reimporting (env set before import)
        from src import billing
        billing.PLAN_IDS["weekly"] = "plan_week"
        billing.PLAN_IDS["monthly"] = "plan_month"
        billing.PLAN_IDS["yearly"] = "plan_year"

        assert _plan_type_from_id("plan_week") == "weekly"
        assert _plan_type_from_id("plan_month") == "monthly"
        assert _plan_type_from_id("plan_year") == "yearly"

    def test_unknown_plan(self):
        assert _plan_type_from_id("plan_unknown_xyz") == "unknown"


@pytest.mark.unit
class TestCreateCheckoutSession:
    """Tests for create_checkout_session."""

    @patch.dict("os.environ", {
        "WHOP_WEEKLY_PLAN": "plan_week",
        "WHOP_MONTHLY_PLAN": "plan_month",
        "WHOP_YEARLY_PLAN": "plan_year",
    })
    def test_successful_checkout(self):
        from src import billing
        billing.PLAN_IDS["weekly"] = "plan_week"
        billing.PLAN_IDS["monthly"] = "plan_month"
        billing.PLAN_IDS["yearly"] = "plan_year"

        result = create_checkout_session("user_abc", "monthly")
        assert "checkout_url" in result
        assert "plan_month" in result["checkout_url"]
        assert "user_abc" in result["checkout_url"]
        assert "whop.com/checkout/" in result["checkout_url"]

    def test_unknown_tier(self):
        result = create_checkout_session("user1", "mega")
        assert "error" in result
        assert "Unknown tier" in result["error"]

    @patch.dict("os.environ", {
        "WHOP_MONTHLY_PLAN": "plan_month",
    })
    def test_custom_redirect_url(self):
        from src import billing
        billing.PLAN_IDS["monthly"] = "plan_month"

        result = create_checkout_session(
            "user1", "monthly",
            redirect_url="https://chesster.io/billing/success",
        )
        assert "checkout_url" in result
        # redirect URL should be encoded in the d= parameter
        assert "chesster.io" in result["checkout_url"]

    def test_empty_plan_id_tier(self):
        """A tier with empty plan ID should return error."""
        from src import billing
        original = billing.PLAN_IDS.copy()
        billing.PLAN_IDS["weekly"] = ""
        try:
            result = create_checkout_session("user1", "weekly")
            assert "error" in result
        finally:
            billing.PLAN_IDS.update(original)


@pytest.mark.unit
class TestGetSubscriptionStatus:
    """Tests for get_subscription_status."""

    @patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_no_supabase(self):
        info = get_subscription_status("user1")
        assert info.user_id == "user1"
        assert info.tier == "free"

    @patch("src.billing.httpx.get")
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_KEY": "key",
    })
    def test_subscription_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{
            "clerk_user_id": "user1",
            "plan_type": "monthly",
            "whop_membership_id": "mem_1",
            "whop_user_id": "usr_1",
            "status": "active",
        }]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = get_subscription_status("user1")
        assert info.tier == "monthly"
        assert info.status == "active"
        assert info.whop_membership_id == "mem_1"

    @patch("src.billing.httpx.get")
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_KEY": "key",
    })
    def test_expired_subscription_returns_free(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{
            "clerk_user_id": "user1",
            "plan_type": "monthly",
            "whop_membership_id": "mem_1",
            "whop_user_id": "usr_1",
            "status": "expired",
        }]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = get_subscription_status("user1")
        assert info.tier == "free"
        assert info.status == "expired"

    @patch("src.billing.httpx.get")
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_KEY": "key",
    })
    def test_no_subscription_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        info = get_subscription_status("user1")
        assert info.tier == "free"

    @patch("src.billing.httpx.get")
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_KEY": "key",
    })
    def test_supabase_error(self, mock_get):
        mock_get.side_effect = Exception("connection refused")
        info = get_subscription_status("user1")
        assert info.tier == "free"

    @patch("src.billing.httpx.get")
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_KEY": "key",
    })
    def test_queries_by_clerk_user_id(self, mock_get):
        """Verify the Supabase query uses clerk_user_id, not user_id."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        get_subscription_status("user_abc")
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs["params"]["clerk_user_id"] == "eq.user_abc"


@pytest.mark.unit
class TestWebhookHandler:
    """Tests for handle_webhook_event."""

    def test_invalid_json(self):
        result = handle_webhook_event(b"not json")
        assert "error" in result

    def test_no_membership_id(self):
        body = {"action": "membership.went_valid", "data": {}}
        result = handle_webhook_event(json.dumps(body).encode())
        assert result["handled"] is False

    @patch("src.billing._save_subscription")
    def test_membership_went_valid(self, mock_save):
        mock_save.return_value = True
        body = {
            "action": "membership.went_valid",
            "data": {
                "id": "mem_123",
                "metadata": {"clerk_user_id": "user1"},
                "plan_id": "plan_month",
                "status": "active",
                "user_id": "whop_usr_1",
            },
        }
        result = handle_webhook_event(json.dumps(body).encode())
        assert result["handled"] is True
        assert result["action"] == "membership.went_valid"
        assert result["user_id"] == "user1"
        assert result["status"] == "active"
        mock_save.assert_called_once()

    @patch("src.billing._save_subscription")
    def test_membership_cancelled(self, mock_save):
        mock_save.return_value = True
        body = {
            "action": "membership.went_invalid",
            "data": {
                "id": "mem_123",
                "metadata": {"clerk_user_id": "user1"},
                "plan_id": "plan_month",
                "status": "cancelled",
                "user_id": "whop_usr_1",
            },
        }
        result = handle_webhook_event(json.dumps(body).encode())
        assert result["handled"] is True
        assert result["status"] == "canceled"  # mapped from 'cancelled'

    @patch("src.billing._save_subscription")
    def test_membership_expired(self, mock_save):
        mock_save.return_value = True
        body = {
            "action": "membership.went_invalid",
            "data": {
                "id": "mem_456",
                "metadata": {"clerk_user_id": "user2"},
                "plan_id": "plan_year",
                "status": "expired",
                "user_id": "whop_usr_2",
            },
        }
        result = handle_webhook_event(json.dumps(body).encode())
        assert result["handled"] is True
        assert result["status"] == "expired"

    @patch("src.billing._save_subscription")
    def test_status_completed_maps_to_active(self, mock_save):
        mock_save.return_value = True
        body = {
            "action": "membership.went_valid",
            "data": {
                "id": "mem_789",
                "metadata": {"clerk_user_id": "user3"},
                "plan_id": "plan_week",
                "status": "completed",
                "user_id": "whop_usr_3",
            },
        }
        result = handle_webhook_event(json.dumps(body).encode())
        assert result["status"] == "active"

    @patch("src.billing._save_subscription")
    def test_fallback_to_discord_id(self, mock_save):
        """When clerk_user_id is missing, falls back to discord.id."""
        mock_save.return_value = True
        body = {
            "action": "membership.went_valid",
            "data": {
                "id": "mem_abc",
                "metadata": {},
                "discord": {"id": "discord_user_99"},
                "plan_id": "plan_month",
                "status": "active",
                "user_id": "whop_usr_4",
            },
        }
        result = handle_webhook_event(json.dumps(body).encode())
        assert result["user_id"] == "discord_user_99"

    @patch("src.billing._save_subscription")
    def test_save_called_with_correct_info(self, mock_save):
        mock_save.return_value = True
        from src import billing
        billing.PLAN_IDS["monthly"] = "plan_month"

        body = {
            "action": "membership.went_valid",
            "data": {
                "id": "mem_100",
                "metadata": {"clerk_user_id": "user_x"},
                "plan_id": "plan_month",
                "status": "active",
                "user_id": "whop_usr_x",
            },
        }
        handle_webhook_event(json.dumps(body).encode())
        call_args = mock_save.call_args
        info = call_args[0][0]
        assert isinstance(info, SubscriptionInfo)
        assert info.user_id == "user_x"
        assert info.whop_membership_id == "mem_100"
        assert info.whop_user_id == "whop_usr_x"
        assert info.status == "active"
        assert call_args[1]["plan_id"] == "plan_month"


@pytest.mark.unit
class TestSaveSubscription:
    """Tests for _save_subscription."""

    @patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_no_supabase(self):
        info = SubscriptionInfo(user_id="u1", tier="monthly")
        assert _save_subscription(info) is False

    @patch("src.billing.httpx.post")
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_KEY": "key",
    })
    def test_saves_to_supabase(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        info = SubscriptionInfo(
            user_id="u1",
            tier="monthly",
            whop_membership_id="mem_1",
            whop_user_id="usr_1",
            status="active",
        )
        assert _save_subscription(info, plan_id="plan_month", plan_type="monthly") is True
        mock_post.assert_called_once()

        # Verify the payload has Whop fields
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["whop_membership_id"] == "mem_1"
        assert payload["clerk_user_id"] == "u1"
        assert payload["whop_user_id"] == "usr_1"
        assert payload["plan_id"] == "plan_month"
        assert payload["status"] == "active"

    @patch("src.billing.httpx.post")
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_KEY": "key",
    })
    def test_save_failure(self, mock_post):
        mock_post.side_effect = Exception("network error")
        info = SubscriptionInfo(user_id="u1", tier="monthly")
        assert _save_subscription(info) is False
