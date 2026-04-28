"""Whop billing integration — webhooks and checkout sessions.

Handles subscription lifecycle events and provides endpoints for
creating checkout sessions and checking subscription status.
"""

import logging
import os
from typing import Optional
from urllib.parse import quote

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Whop plan IDs (configured via environment)
PLAN_IDS = {
    "weekly": os.environ.get("WHOP_WEEKLY_PLAN", ""),
    "monthly": os.environ.get("WHOP_MONTHLY_PLAN", ""),
    "yearly": os.environ.get("WHOP_YEARLY_PLAN", ""),
}

# Map Whop membership status to internal status
STATUS_MAP = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "completed": "active",
    "expired": "expired",
    "cancelled": "canceled",
}


class SubscriptionInfo(BaseModel):
    user_id: str
    tier: str = "free"
    whop_membership_id: Optional[str] = None
    whop_user_id: Optional[str] = None
    status: str = "none"


def _get_whop_api_key() -> str:
    """Get Whop API key from environment."""
    return os.environ.get("WHOP_API_KEY", "")


def _plan_type_from_id(plan_id: str) -> str:
    """Resolve plan type name from a Whop plan ID."""
    for plan_type, pid in PLAN_IDS.items():
        if pid and pid == plan_id:
            return plan_type
    return "unknown"


def create_checkout_session(
    user_id: str,
    tier: str,
    redirect_url: str = "https://chesster.io/onboarding?step=complete",
) -> dict:
    """Build a Whop checkout URL for a subscription plan."""
    plan_id = PLAN_IDS.get(tier)
    if not plan_id:
        return {"error": f"Unknown tier: {tier}"}

    encoded_redirect = quote(redirect_url, safe="")
    checkout_url = (
        f"https://whop.com/checkout/{plan_id}"
        f"?d={encoded_redirect}"
        f"&metadata[clerk_user_id]={quote(user_id, safe='')}"
    )

    return {"checkout_url": checkout_url}


def get_subscription_status(user_id: str) -> SubscriptionInfo:
    """Get subscription status for a user from Supabase."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        return SubscriptionInfo(user_id=user_id)

    try:
        resp = httpx.get(
            f"{url}/rest/v1/subscriptions",
            params={"clerk_user_id": f"eq.{user_id}", "select": "*"},
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
    plan_type = row.get("plan_type", "unknown")
    status = row.get("status", "none")
    tier = "free" if status in ("expired", "canceled") else plan_type

    return SubscriptionInfo(
        user_id=user_id,
        tier=tier,
        whop_membership_id=row.get("whop_membership_id"),
        whop_user_id=row.get("whop_user_id"),
        status=status,
    )


def _save_subscription(info: SubscriptionInfo, plan_id: str = "", plan_type: str = "") -> bool:
    """Persist subscription info to Supabase."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return False

    payload = {
        "whop_membership_id": info.whop_membership_id,
        "clerk_user_id": info.user_id,
        "whop_user_id": info.whop_user_id,
        "plan_id": plan_id,
        "plan_type": plan_type or info.tier,
        "status": info.status,
    }

    try:
        httpx.post(
            f"{url}/rest/v1/subscriptions",
            json=payload,
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


def handle_webhook_event(payload: bytes) -> dict:
    """Process a Whop webhook event.

    Expects JSON body with:
    - action: event type string
    - data: membership object with id, metadata, plan_id, status, user_id
    """
    import json

    try:
        body = json.loads(payload)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Webhook payload parse error: %s", e)
        return {"error": "Invalid payload"}

    action = body.get("action", body.get("event", "unknown"))
    membership = body.get("data", {})
    membership_id = membership.get("id")

    if not membership_id:
        return {"handled": False, "reason": "No membership ID"}

    clerk_user_id = (
        membership.get("metadata", {}).get("clerk_user_id")
        or membership.get("discord", {}).get("id")
        or "unknown"
    )
    plan_id = membership.get("plan_id", "")
    whop_status = membership.get("status", "")
    whop_user_id = membership.get("user_id", "")

    mapped_status = STATUS_MAP.get(whop_status, whop_status or "inactive")
    plan_type = _plan_type_from_id(plan_id)
    tier = "free" if mapped_status in ("expired", "canceled") else plan_type

    info = SubscriptionInfo(
        user_id=clerk_user_id,
        tier=tier,
        whop_membership_id=membership_id,
        whop_user_id=whop_user_id,
        status=mapped_status,
    )
    _save_subscription(info, plan_id=plan_id, plan_type=plan_type)

    return {
        "handled": True,
        "action": action,
        "membership_id": membership_id,
        "user_id": clerk_user_id,
        "status": mapped_status,
    }
