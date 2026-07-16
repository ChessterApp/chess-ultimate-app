"""
Refunds service — Whop refund webhook handler with idempotency (PRD §11.3 #4).

The Whop webhook may deliver the same refund event multiple times (network
retries, reprocessing). We treat ``whop_event_id`` as the idempotency key:

  * `process_refund_event()` checks for an existing row; if present, returns
    ``already_processed=True`` and writes nothing.
  * Otherwise it inserts the refund row AND a matching billing-audit row
    inside the same logical step. Both tables use UNIQUE constraints on
    the idempotency key, so concurrent inserts are safe at the DB level too.

This service is invoked from `routes/refunds.py` (verified webhook) and
from `frontend/src/app/api/whop/webhook/route.ts` (which forwards
refund.* events). Both paths must produce identical DB state.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


REFUND_EVENT_PREFIXES = ('refund.', 'payment.refunded')


from utils.supabase_client import get_supabase as _get_supabase


def is_refund_event(event_name: str | None) -> bool:
    """True if the event is one of the refund events we care about."""
    if not event_name:
        return False
    return any(event_name.startswith(p) for p in REFUND_EVENT_PREFIXES)


def _extract_event_id(payload: dict[str, Any]) -> str | None:
    """Pull the canonical event id from a Whop refund webhook payload.

    Whop sends an outer ``id`` (event id) AND an inner ``data.id`` (refund
    id). The event id is what we want for idempotency — the same refund
    can be retried multiple times under different event ids if the consumer
    NACKs; in that case we'd want both rows, since each is a distinct
    notification. We prefer ``event_id`` if present, else fall back to
    the outer id.
    """
    if not isinstance(payload, dict):
        return None
    eid = (
        payload.get('event_id')
        or payload.get('id')
        or (payload.get('data') or {}).get('event_id')
    )
    if isinstance(eid, str) and eid.strip():
        return eid.strip()
    return None


def _extract_org_id(payload: dict[str, Any]) -> str | None:
    """Pull organization_id from a Whop refund webhook payload.

    Looks at data.metadata.org_id (our convention from org-checkout) and
    falls back to top-level metadata for legacy events.
    """
    data = payload.get('data') if isinstance(payload, dict) else None
    if isinstance(data, dict):
        meta = data.get('metadata')
        if isinstance(meta, dict):
            for key in ('org_id', 'organization_id'):
                v = meta.get(key)
                if isinstance(v, str) and v:
                    return v
    meta = payload.get('metadata') if isinstance(payload, dict) else None
    if isinstance(meta, dict):
        for key in ('org_id', 'organization_id'):
            v = meta.get(key)
            if isinstance(v, str) and v:
                return v
    return None


def _extract_amount_cents(payload: dict[str, Any]) -> int:
    """Extract refunded amount in cents. Defaults to 0 if missing/malformed."""
    data = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return 0
    for key in (
        'amount_cents', 'refund_amount_cents',
        'amount_refunded_cents', 'amount_refunded',
    ):
        raw = data.get(key)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            try:
                return int(raw)
            except ValueError:
                continue
    # Whop sometimes sends an `amount` field in dollars
    raw_amount = data.get('amount')
    if isinstance(raw_amount, (int, float)) and 'amount_cents' not in data:
        return int(round(float(raw_amount) * 100))
    return 0


def _fetch_existing(event_id: str) -> dict[str, Any] | None:
    try:
        res = (
            _get_supabase()
            .table('organization_refunds')
            .select('id, organization_id, whop_event_id, amount_cents')
            .eq('whop_event_id', event_id)
            .maybe_single()
            .execute()
        )
        return res.data if (res and getattr(res, 'data', None)) else None
    except Exception as exc:
        logger.warning('refund existence check failed for event=%s: %s', event_id, exc)
        return None


def process_refund_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Process a Whop refund webhook payload.

    Returns a dict with:
      * status: 'processed' | 'already_processed' | 'skipped'
      * event_id, org_id, amount_cents

    Idempotency contract: calling this function twice with the same
    ``whop_event_id`` must result in exactly one DB row in
    ``organization_refunds`` and exactly one row in
    ``organization_billing_audit`` for that key.
    """
    event_id = _extract_event_id(payload)
    if not event_id:
        return {
            'status': 'skipped',
            'reason': 'missing_event_id',
            'event_id': None,
            'org_id': None,
            'amount_cents': 0,
        }

    org_id = _extract_org_id(payload)
    amount_cents = _extract_amount_cents(payload)

    existing = _fetch_existing(event_id)
    if existing:
        return {
            'status': 'already_processed',
            'event_id': event_id,
            'org_id': existing.get('organization_id') or org_id,
            'amount_cents': existing.get('amount_cents', amount_cents),
        }

    if not org_id:
        # Without an org id we can't write the row, but the event is otherwise
        # valid — surface a skipped status so the webhook returns 200 and Whop
        # doesn't retry forever.
        return {
            'status': 'skipped',
            'reason': 'missing_org_id',
            'event_id': event_id,
            'org_id': None,
            'amount_cents': amount_cents,
        }

    data = (payload.get('data') or {}) if isinstance(payload, dict) else {}
    membership_id = data.get('membership_id') or data.get('whop_membership_id')
    currency = (data.get('currency') or 'usd').lower()
    reason = data.get('reason')

    supabase = _get_supabase()

    # Upsert by whop_event_id — unique constraint guarantees idempotency at DB.
    # We deliberately use insert with ignore_duplicates so concurrent writers
    # can race safely (the loser becomes a no-op).
    try:
        supabase.table('organization_refunds').upsert(
            {
                'organization_id': org_id,
                'whop_event_id': event_id,
                'whop_membership_id': membership_id,
                'amount_cents': amount_cents,
                'currency': currency,
                'reason': reason,
                'status': 'processed',
                'raw_payload': payload,
            },
            on_conflict='whop_event_id',
            ignore_duplicates=True,
        ).execute()
    except TypeError:
        # Older supabase-py without `ignore_duplicates` — fall back to upsert.
        supabase.table('organization_refunds').upsert(
            {
                'organization_id': org_id,
                'whop_event_id': event_id,
                'whop_membership_id': membership_id,
                'amount_cents': amount_cents,
                'currency': currency,
                'reason': reason,
                'status': 'processed',
                'raw_payload': payload,
            },
            on_conflict='whop_event_id',
        ).execute()

    # Audit log entry — same idempotency key.
    try:
        supabase.table('organization_billing_audit').upsert(
            {
                'organization_id': org_id,
                'event_kind': 'refund',
                'event_source_id': event_id,
                'payload': {
                    'amount_cents': amount_cents,
                    'currency': currency,
                    'reason': reason,
                    'membership_id': membership_id,
                },
            },
            on_conflict='event_kind,event_source_id',
            ignore_duplicates=True,
        ).execute()
    except TypeError:
        supabase.table('organization_billing_audit').upsert(
            {
                'organization_id': org_id,
                'event_kind': 'refund',
                'event_source_id': event_id,
                'payload': {
                    'amount_cents': amount_cents,
                    'currency': currency,
                    'reason': reason,
                    'membership_id': membership_id,
                },
            },
            on_conflict='event_kind,event_source_id',
        ).execute()

    # Bump organization_billing — record the latest refund timestamp so the
    # owner-facing billing page can show "refunded on ...".
    from datetime import datetime, timezone
    refunded_at = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table('organization_billing').upsert(
            {
                'organization_id': org_id,
                'last_refund_at': refunded_at,
                'last_refund_amount_cents': amount_cents,
            },
            on_conflict='organization_id',
        ).execute()
    except Exception as exc:
        logger.warning('organization_billing refund-stamp failed: %s', exc)

    return {
        'status': 'processed',
        'event_id': event_id,
        'org_id': org_id,
        'amount_cents': amount_cents,
    }


def list_refunds_for_org(org_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    try:
        res = (
            _get_supabase()
            .table('organization_refunds')
            .select('*')
            .eq('organization_id', org_id)
            .order('created_at', desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning('list_refunds_for_org failed: %s', exc)
        return []
