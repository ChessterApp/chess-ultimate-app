"""
Tier Quota Service — canonical tier map + seat enforcement.

This is the single source of truth for tier names, prices, seat caps, and
feature flags. The frontend fetches it via GET /api/tiers; the backend uses
it to enforce invite caps in routes/admin.py.

Per PRD §3 and §6.0:
- Tier identifiers (`starter`, `growth`, `pro`, `enterprise`) match the DB
  CHECK constraint on `organization_billing.plan`.
- Display names capitalize for UI.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


# ─── Canonical tier map ──────────────────────────────────────────────────────

TIERS: dict[str, dict[str, Any]] = {
    'starter': {
        'id': 'starter',
        'display_name': 'Starter',
        'seat_cap': 25,
        'price_usd_monthly': 49,
        'price_usd_annual': 499,  # ~15% discount, $41.58/mo equiv
        'features': [
            'Up to 25 students',
            'Logo + brand colors',
            'Subdomain (yourschool.chesster.io)',
            'Student management',
            'Course assignments',
        ],
        'best_for': 'Solo coaches, micro-schools',
    },
    'growth': {
        'id': 'growth',
        'display_name': 'Growth',
        'seat_cap': 100,
        'price_usd_monthly': 129,
        'price_usd_annual': 1316,
        'features': [
            'Up to 100 students',
            'Everything in Starter',
            'Custom CSS + favicon',
            'Branded login page',
            'Tournaments + analytics',
        ],
        'best_for': 'Growing schools',
    },
    'pro': {
        'id': 'pro',
        'display_name': 'Pro',
        'seat_cap': 300,
        'price_usd_monthly': 299,
        'price_usd_annual': 3050,
        'features': [
            'Up to 300 students',
            'Everything in Growth',
            'Custom domain (yourdomain.com)',
            'Branded email sender',
            'Landing-page hero',
        ],
        'best_for': 'Established academies',
    },
    'enterprise': {
        'id': 'enterprise',
        'display_name': 'Enterprise',
        'seat_cap': None,  # Unlimited
        'price_usd_monthly': None,  # Custom
        'price_usd_annual': None,
        'features': [
            'Unlimited students',
            'Everything in Pro',
            'SSO',
            'Multi-branch',
            'Dedicated CSM + SLA',
        ],
        'best_for': 'Multi-location franchises',
    },
}


def get_tiers() -> dict[str, dict[str, Any]]:
    """Return the canonical tier map (read-only)."""
    return TIERS


def get_tier(tier_id: str) -> dict[str, Any] | None:
    """Return a single tier's config, or None if unknown."""
    return TIERS.get(tier_id)


def get_seat_limit(tier_id: str) -> int | None:
    """Return seat cap (None = unlimited)."""
    tier = TIERS.get(tier_id)
    return tier['seat_cap'] if tier else None


# ─── Quota enforcement ───────────────────────────────────────────────────────


from utils.supabase_client import get_supabase as _get_supabase


def get_org_plan(org_id: str) -> str:
    """Look up the org's current plan from organization_billing.
    Defaults to 'starter' if no billing row exists yet."""
    try:
        supabase = _get_supabase()
        result = (
            supabase.table('organization_billing')
            .select('plan')
            .eq('organization_id', org_id)
            .single()
            .execute()
        )
        if result.data and result.data.get('plan'):
            return result.data['plan']
    except Exception as exc:
        logger.warning('get_org_plan failed for org=%s: %s', org_id, exc)
    return 'starter'


def get_current_seat_count(org_id: str) -> int:
    """Count active + invited members (excludes owner since owner is the
    director, not a billable student seat)."""
    try:
        supabase = _get_supabase()
        result = (
            supabase.table('organization_members')
            .select('id', count='exact')
            .eq('organization_id', org_id)
            .neq('role', 'owner')
            .execute()
        )
        return result.count or 0
    except Exception as exc:
        logger.warning('get_current_seat_count failed for org=%s: %s', org_id, exc)
        return 0


def can_invite(org_id: str, n: int = 1) -> tuple[bool, dict[str, Any]]:
    """
    Can this org invite `n` more members?

    Returns (allowed, info). When blocked, `info` carries the structured
    payload for the 402 response: code, current_count, seat_cap, upgrade_url.
    """
    plan = get_org_plan(org_id)
    cap = get_seat_limit(plan)
    current = get_current_seat_count(org_id)

    # Unlimited (enterprise)
    if cap is None:
        return True, {'plan': plan, 'current_count': current, 'seat_cap': None}

    if current + n > cap:
        return False, {
            'code': 'tier_limit_exceeded',
            'plan': plan,
            'current_count': current,
            'seat_cap': cap,
            'attempted': n,
            'upgrade_url': _upgrade_url_for(plan),
        }

    return True, {'plan': plan, 'current_count': current, 'seat_cap': cap}


def _upgrade_url_for(current_plan: str) -> str:
    """Suggest the next tier's checkout URL.
    Falls back to /admin/billing if no clear upgrade path."""
    base = os.getenv('PUBLIC_APP_URL', 'https://chesster.io').rstrip('/')
    ladder = ['starter', 'growth', 'pro', 'enterprise']
    try:
        idx = ladder.index(current_plan)
        if idx + 1 < len(ladder):
            return f'{base}/admin/billing?upgrade={ladder[idx + 1]}'
    except ValueError:
        pass
    return f'{base}/admin/billing'
