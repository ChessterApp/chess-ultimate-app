"""Stripe billing integration — webhooks and checkout sessions.

Handles subscription lifecycle events and provides endpoints for
creating checkout sessions and checking subscription status.
"""

import json
import logging
import os
from typing import Optional

import httpx
import stripe
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Stripe price IDs (configured via environment or defaults)
PRICE_IDS = {
    "premium": os.environ.get("STRIPE_PREMIUM_PRICE_ID", "price_premium_monthly"),
    "pro": os.environ.get("STRIPE_PRO_PRICE_ID", "price_pro_monthly"),
}

# Map Stripe status to internal tier
STATUS_TIER_MAP = {
    "active": None,  # Tier comes from the price
    "trialing": None,
    "past_due": "free",
    "canceled": "free",
    "unpaid": "free",
}


class SubscriptionInfo(BaseModel):
    user_id: str
    tier: str = "free"
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    status: str = "none"


def get_stripe_key() -> str:
    """Get Stripe secret key from environment."""
    return os.environ.get("STRIPE_SECRET_KEY", "")


def init_stripe() -> bool:
    """Initialize Stripe with the secret key. Returns True if configured."""
    key = get_stripe_key()
    if key:
        stripe.api_key = key
        return True
    logger.warning("STRIPE_SECRET_KEY not configured")
    return False


def create_checkout_session(
    user_id: str,
    tier: str,
    success_url: str = "https://chesster.io/billing/success",
    cancel_url: str = "https://chesster.io/billing/cancel",
) -> dict:
    """Create a Stripe Checkout Session for a subscription."""
    if not init_stripe():
        return {"error": "Stripe not configured"}

    price_id = PRICE_IDS.get(tier)
    if not price_id:
        return {"error": f"Unknown tier: {tier}"}

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            client_reference_id=user_id,
            metadata={"user_id": user_id, "tier": tier},
        )
        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }
    except stripe.StripeError as e:
        logger.exception("Stripe checkout session creation failed")
        return {"error": str(e)}


def get_subscription_status(user_id: str) -> SubscriptionInfo:
    """Get subscription status for a user.

    In production, this would query Supabase for the user's stored
    Stripe customer/subscription IDs. For now, returns defaults.
    """
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        return SubscriptionInfo(user_id=user_id)

    try:
        resp = httpx.get(
            f"{url}/rest/v1/subscriptions",
            params={"user_id": f"eq.{user_id}", "select": "*"},
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        logger.exception("Failed to load subscription for %s", user_id)
        return SubscriptionInfo(user_id=user_id)

    if not rows:
        return SubscriptionInfo(user_id=user_id)

    row = rows[0]
    return SubscriptionInfo(
        user_id=user_id,
        tier=row.get("tier", "free"),
        stripe_customer_id=row.get("stripe_customer_id"),
        stripe_subscription_id=row.get("stripe_subscription_id"),
        status=row.get("status", "none"),
    )


def _save_subscription(info: SubscriptionInfo) -> bool:
    """Persist subscription info to Supabase."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return False

    try:
        httpx.post(
            f"{url}/rest/v1/subscriptions",
            json={
                "user_id": info.user_id,
                "tier": info.tier,
                "stripe_customer_id": info.stripe_customer_id,
                "stripe_subscription_id": info.stripe_subscription_id,
                "status": info.status,
            },
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            timeout=10,
        )
        return True
    except Exception:
        logger.exception("Failed to save subscription for %s", info.user_id)
        return False


def _tier_from_price(price_id: str) -> str:
    """Resolve tier name from a Stripe price ID."""
    for tier, pid in PRICE_IDS.items():
        if pid == price_id:
            return tier
    return "premium"  # Default if unknown price


def handle_webhook_event(payload: bytes, sig_header: str) -> dict:
    """Process a Stripe webhook event.

    Handles:
    - checkout.session.completed
    - customer.subscription.updated
    - customer.subscription.deleted
    """
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not init_stripe():
        return {"error": "Stripe not configured"}

    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
    except (stripe.SignatureVerificationError, ValueError) as e:
        logger.warning("Webhook signature verification failed: %s", e)
        return {"error": "Invalid signature"}

    # Normalize event to plain dicts (StripeObject doesn't support .get())
    event_dict = json.loads(str(event)) if hasattr(event, '_data') else event
    event_type = event_dict["type"]
    data = event_dict["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id", "")
        tier = data.get("metadata", {}).get("tier", "premium")
        info = SubscriptionInfo(
            user_id=user_id,
            tier=tier,
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=data.get("subscription"),
            status="active",
        )
        _save_subscription(info)
        return {"handled": True, "event": event_type, "user_id": user_id}

    elif event_type == "customer.subscription.updated":
        sub_id = data.get("id")
        status = data.get("status", "active")
        items = data.get("items", {}).get("data", [])
        price_id = items[0]["price"]["id"] if items else ""
        tier = _tier_from_price(price_id) if status in ("active", "trialing") else "free"

        # Find user by subscription ID
        info = SubscriptionInfo(
            user_id=data.get("metadata", {}).get("user_id", ""),
            tier=tier,
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=sub_id,
            status=status,
        )
        _save_subscription(info)
        return {"handled": True, "event": event_type}

    elif event_type == "customer.subscription.deleted":
        sub_id = data.get("id")
        info = SubscriptionInfo(
            user_id=data.get("metadata", {}).get("user_id", ""),
            tier="free",
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=sub_id,
            status="canceled",
        )
        _save_subscription(info)
        return {"handled": True, "event": event_type}

    return {"handled": False, "event": event_type}
