"""
Ownership-transfer state machine (PRD §11.3 #3).

State machine:

    invite_pending ──── owner-revoke ───────────────►  revoked   (terminal)
        │
        │
        ├── invitee-accept ───►  accepted
        │                            │
        │                            ├── owner-confirm ──► completed (terminal)
        │                            │
        │                            └── owner-revoke ──► revoked  (terminal)
        │
        └── TTL elapsed ────►  expired (terminal)

Public API:

    create_transfer(org_id, current_owner_user_id, invitee_email, *, ttl_hours=72)
    get_by_token(token)
    accept_transfer(token, invitee_user_id)
    revoke_transfer(transfer_id, requester_user_id)
    confirm_transfer(transfer_id, current_owner_user_id)
    expire_due()                # bulk-mark expired (called from a cron)
    list_for_org(org_id)

All transitions are guarded — invalid state changes raise
`OwnershipTransferError` with a stable code so the route layer can map
to HTTP status codes.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


STATES = ('invite_pending', 'accepted', 'revoked', 'expired', 'completed')
TERMINAL_STATES = ('revoked', 'expired', 'completed')
PENDING_STATES = ('invite_pending', 'accepted')


class OwnershipTransferError(Exception):
    """Raised on invalid transitions or missing rows.

    Codes:
      * not_found         → 404
      * invalid_state     → 409 (e.g. accepting an already-completed row)
      * forbidden         → 403 (caller not authorized)
      * expired           → 410 (token past expires_at)
      * invalid_input     → 400
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _get_supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Postgres returns ...+00:00 — datetime.fromisoformat handles it
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None


# ─── Token generation ───────────────────────────────────────────────────────


def _generate_token() -> str:
    """URL-safe random token used in the invite email link."""
    return secrets.token_urlsafe(32)


# ─── CRUD ───────────────────────────────────────────────────────────────────


def create_transfer(
    org_id: str,
    current_owner_user_id: str,
    invitee_email: str,
    *,
    ttl_hours: int = 72,
) -> dict[str, Any]:
    """Create a new transfer in state `invite_pending`."""
    invitee_email = (invitee_email or '').strip().lower()
    if not invitee_email or '@' not in invitee_email:
        raise OwnershipTransferError('invalid_input', 'invalid invitee_email')
    if not current_owner_user_id:
        raise OwnershipTransferError('invalid_input', 'missing owner user id')
    if ttl_hours <= 0:
        raise OwnershipTransferError('invalid_input', 'ttl_hours must be > 0')

    expires_at = (_now_dt() + timedelta(hours=ttl_hours)).isoformat()
    payload = {
        'organization_id': org_id,
        'current_owner_user_id': current_owner_user_id,
        'invitee_email': invitee_email,
        'token': _generate_token(),
        'state': 'invite_pending',
        'expires_at': expires_at,
    }
    res = (
        _get_supabase()
        .table('organization_ownership_transfers')
        .insert(payload)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise OwnershipTransferError('invalid_input', 'insert returned no row')
    return rows[0]


def get_by_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        res = (
            _get_supabase()
            .table('organization_ownership_transfers')
            .select('*')
            .eq('token', token)
            .maybe_single()
            .execute()
        )
        return res.data if (res and getattr(res, 'data', None)) else None
    except Exception as exc:
        logger.warning('get_by_token failed: %s', exc)
        return None


def get_by_id(transfer_id: str) -> dict[str, Any] | None:
    try:
        res = (
            _get_supabase()
            .table('organization_ownership_transfers')
            .select('*')
            .eq('id', transfer_id)
            .maybe_single()
            .execute()
        )
        return res.data if (res and getattr(res, 'data', None)) else None
    except Exception as exc:
        logger.warning('get_by_id failed: %s', exc)
        return None


def list_for_org(org_id: str) -> list[dict[str, Any]]:
    try:
        res = (
            _get_supabase()
            .table('organization_ownership_transfers')
            .select('*')
            .eq('organization_id', org_id)
            .order('created_at', desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning('list_for_org failed: %s', exc)
        return []


# ─── State transitions ──────────────────────────────────────────────────────


def _is_expired(row: dict[str, Any]) -> bool:
    expires = _parse_iso(row.get('expires_at'))
    return bool(expires and expires <= _now_dt())


def _update_state(transfer_id: str, **fields: Any) -> dict[str, Any]:
    payload = {**fields, 'updated_at': _now_iso()}
    res = (
        _get_supabase()
        .table('organization_ownership_transfers')
        .update(payload)
        .eq('id', transfer_id)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else payload


def accept_transfer(token: str, invitee_user_id: str) -> dict[str, Any]:
    """Transition invite_pending → accepted.

    Called by the accept-page when the invitee clicks the link and signs in.
    """
    if not invitee_user_id:
        raise OwnershipTransferError('invalid_input', 'missing invitee user id')

    row = get_by_token(token)
    if not row:
        raise OwnershipTransferError('not_found', 'transfer not found')

    if _is_expired(row) and row['state'] == 'invite_pending':
        # Auto-expire on read
        _update_state(row['id'], state='expired')
        raise OwnershipTransferError('expired', 'transfer token expired')

    if row['state'] != 'invite_pending':
        raise OwnershipTransferError(
            'invalid_state',
            f'cannot accept from state {row["state"]!r}',
        )

    updated = _update_state(
        row['id'],
        state='accepted',
        invitee_user_id=invitee_user_id,
        accepted_at=_now_iso(),
    )
    return {**row, **updated}


def revoke_transfer(
    transfer_id: str,
    requester_user_id: str,
) -> dict[str, Any]:
    """Transition any non-terminal state → revoked.

    Only the current owner can revoke.
    """
    row = get_by_id(transfer_id)
    if not row:
        raise OwnershipTransferError('not_found', 'transfer not found')

    if row.get('current_owner_user_id') != requester_user_id:
        raise OwnershipTransferError(
            'forbidden',
            'only the current owner can revoke a transfer',
        )

    if row['state'] in TERMINAL_STATES:
        raise OwnershipTransferError(
            'invalid_state',
            f'cannot revoke from terminal state {row["state"]!r}',
        )

    updated = _update_state(transfer_id, state='revoked', revoked_at=_now_iso())
    return {**row, **updated}


def confirm_transfer(
    transfer_id: str,
    current_owner_user_id: str,
) -> dict[str, Any]:
    """Transition accepted → completed and swap roles.

    The current owner re-confirms after the invitee has accepted. We then:
      * demote current owner to 'admin' (audit-friendly — they stay in org)
      * promote invitee to 'owner'
      * stamp completed_at
    """
    row = get_by_id(transfer_id)
    if not row:
        raise OwnershipTransferError('not_found', 'transfer not found')

    if row.get('current_owner_user_id') != current_owner_user_id:
        raise OwnershipTransferError(
            'forbidden',
            'only the current owner can confirm',
        )

    if row['state'] != 'accepted':
        raise OwnershipTransferError(
            'invalid_state',
            f'cannot confirm from state {row["state"]!r}',
        )

    if _is_expired(row):
        _update_state(row['id'], state='expired')
        raise OwnershipTransferError('expired', 'transfer token expired')

    new_owner_user_id = row.get('invitee_user_id')
    if not new_owner_user_id:
        raise OwnershipTransferError(
            'invalid_state',
            'invitee_user_id not set — accept must run first',
        )

    org_id = row['organization_id']
    supabase = _get_supabase()
    # Demote current owner
    supabase.table('organization_members').update({'role': 'admin'}).eq(
        'organization_id', org_id,
    ).eq('user_id', current_owner_user_id).execute()
    # Promote invitee (upsert so the row exists even if they were not already
    # a member when invited — covers the assistant-handoff edge case)
    supabase.table('organization_members').upsert(
        {
            'organization_id': org_id,
            'user_id': new_owner_user_id,
            'role': 'owner',
            'invited_by': current_owner_user_id,
        },
        on_conflict='organization_id,user_id',
    ).execute()

    updated = _update_state(
        transfer_id, state='completed', completed_at=_now_iso(),
    )
    return {**row, **updated}


def expire_due() -> int:
    """Bulk-mark all expired-by-time invite_pending rows as expired.

    Called by a cron / lifecycle CLI. Returns the number of rows touched.
    """
    now = _now_iso()
    supabase = _get_supabase()
    res = (
        supabase.table('organization_ownership_transfers')
        .update({'state': 'expired', 'updated_at': now})
        .lt('expires_at', now)
        .in_('state', list(PENDING_STATES))
        .execute()
    )
    return len(res.data or [])
