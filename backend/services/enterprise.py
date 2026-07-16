"""
Enterprise tier helpers — self-serve checkout, uncapped seats, SSO stub
(PRD §11.3 #1).

The enterprise tier is now a first-class self-serve option (was previously
"talk to sales" only). The sales-assist Calendly remains as an alternate
CTA on the tier card.

Key invariants:
  * `is_enterprise(plan)`           — tier-id check
  * `enforce_uncapped(plan, n)`     — confirms the tier-quota service
                                      returns unlimited seats for enterprise
  * `activate_enterprise(org_id, ...)` — writes the activation flags after
                                          Whop checkout success
  * `configure_sso(org_id, provider, metadata)` — stores the director's
                                                    SSO intent (stub — real
                                                    SAML/OIDC wiring is a
                                                    future PRD)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


SSO_PROVIDERS = ('saml', 'oidc')


class EnterpriseConfigError(Exception):
    """Raised by configure_sso when input is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


from utils.supabase_client import get_supabase as _get_supabase


def is_enterprise(plan: str | None) -> bool:
    return (plan or '').strip().lower() == 'enterprise'


def enforce_uncapped(plan: str, n: int = 1) -> bool:
    """Return True if the plan permits the next `n` invites.

    For enterprise, seat_cap is None (unlimited) — so any n is allowed.
    For other plans, this is a thin wrapper over tier_quota.get_seat_limit.
    """
    from services.tier_quota import get_seat_limit
    cap = get_seat_limit(plan)
    if cap is None:
        return True
    return n <= cap


def activate_enterprise(
    org_id: str,
    *,
    sso_enabled: bool = False,
    activated_at: str | None = None,
) -> dict[str, Any]:
    """Stamp the enterprise activation flags on the org.

    Called from the Whop webhook (subscription.went_valid) when
    metadata.kind=='org_subscription' and metadata.tier=='enterprise'.
    """
    payload: dict[str, Any] = {
        'sso_enabled': bool(sso_enabled),
        'enterprise_activated_at': activated_at
            or datetime.now(timezone.utc).isoformat(),
    }
    res = (
        _get_supabase()
        .table('organizations')
        .update(payload)
        .eq('id', org_id)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else payload


def configure_sso(
    org_id: str,
    *,
    provider: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store the SSO config on the org. Stub for the real SAML/OIDC flow.

    Raises EnterpriseConfigError on bad input. Does not validate the
    metadata blob — that's the upstream provider's job.
    """
    p = (provider or '').strip().lower()
    if p not in SSO_PROVIDERS:
        raise EnterpriseConfigError(
            'invalid_provider',
            f'provider must be one of {SSO_PROVIDERS}',
        )
    payload: dict[str, Any] = {
        'sso_enabled': True,
        'sso_provider': p,
        'sso_metadata': metadata or {},
    }
    res = (
        _get_supabase()
        .table('organizations')
        .update(payload)
        .eq('id', org_id)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else payload


def disable_sso(org_id: str) -> bool:
    """Clear SSO config without disturbing other enterprise flags."""
    (
        _get_supabase()
        .table('organizations')
        .update({
            'sso_enabled': False,
            'sso_provider': None,
            'sso_metadata': None,
        })
        .eq('id', org_id)
        .execute()
    )
    return True
