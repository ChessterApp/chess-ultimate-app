"""
Org deletion service — PRD §7 (Delete School).

Self-serve deletion request flow:
  1. Owner confirms "Delete school" (frontend modal, type-name confirm).
  2. Route validates auth + owner + confirm_name match.
  3. ``request_deletion`` stamps ``organizations.deletion_requested_at = now()``
     (only if NULL — re-requests are a no-op) and notifies Alex via Resend.

Email failure does NOT block the timestamp write. The timestamp is the source
of truth for the ops-side hard-delete job (separate concern, not in this file).
We deliberately do NOT reuse ``invite_email_failures``: that queue is
invite-specific and a deletion notification is not retryable in the same way.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


RESEND_API_URL = 'https://api.resend.com/emails'
DEFAULT_FROM = os.getenv('RESEND_OPS_FROM', 'ops@chesster.io')
ALEX_EMAIL = os.getenv('CHESSTER_OPS_EMAIL', 'alex@chesster.io')


class OrgDeletionError(Exception):
    """Base error for self-serve deletion. ``code`` maps to a HTTP status."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


from utils.supabase_client import get_supabase as _get_supabase


def _get_org(org_id: str) -> dict[str, Any] | None:
    try:
        res = (
            _get_supabase()
            .table('organizations')
            .select('id, name, slug, deletion_requested_at')
            .eq('id', org_id)
            .single()
            .execute()
        )
        return res.data if getattr(res, 'data', None) else None
    except Exception as exc:
        logger.warning('org_deletion._get_org failed for org=%s: %s', org_id, exc)
        return None


def _get_caller_role(org_id: str, user_id: str) -> str | None:
    try:
        res = (
            _get_supabase()
            .table('organization_members')
            .select('role')
            .eq('organization_id', org_id)
            .eq('user_id', user_id)
            .single()
            .execute()
        )
        return res.data.get('role') if res.data else None
    except Exception as exc:
        logger.warning(
            'org_deletion._get_caller_role failed (org=%s user=%s): %s',
            org_id, user_id, exc,
        )
        return None


def _post_json(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw else {}


def _notify_ops(org: dict[str, Any], requester_user_id: str, requester_email: str | None,
                timestamp: str) -> bool:
    """Email Alex that a deletion was requested. Never raises."""
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        logger.warning('org_deletion: RESEND_API_KEY missing — skipping ops email')
        return False

    slug = org.get('slug') or '(unknown)'
    name = org.get('name') or '(unnamed)'
    requester = requester_email or requester_user_id

    subject = f'[Chesster] School deletion requested: {slug}'
    text = (
        f'A school has requested self-serve deletion.\n\n'
        f'Org name:   {name}\n'
        f'Org slug:   {slug}\n'
        f'Org id:     {org.get("id")}\n'
        f'Requester:  {requester}\n'
        f'Timestamp:  {timestamp}\n\n'
        f'Hard-delete is scheduled ~30 days from this timestamp. '
        f'Reply to the school to cancel if needed.\n'
    )
    html = (
        '<p>A school has requested self-serve deletion.</p>'
        f'<ul>'
        f'<li><strong>Org name:</strong> {name}</li>'
        f'<li><strong>Org slug:</strong> {slug}</li>'
        f'<li><strong>Org id:</strong> {org.get("id")}</li>'
        f'<li><strong>Requester:</strong> {requester}</li>'
        f'<li><strong>Timestamp:</strong> {timestamp}</li>'
        f'</ul>'
        '<p>Hard-delete is scheduled ~30 days from this timestamp. '
        'Reply to the school to cancel if needed.</p>'
    )
    body = {
        'from': DEFAULT_FROM,
        'to': [ALEX_EMAIL],
        'subject': subject,
        'text': text,
        'html': html,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    try:
        _post_json(RESEND_API_URL, headers, body)
        logger.info('org_deletion notification sent: org=%s slug=%s', org.get('id'), slug)
        return True
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode('utf-8')
        except Exception:
            err_body = ''
        logger.error(
            'org_deletion ops email HTTPError: status=%s body=%s', exc.code, err_body[:500],
        )
        return False
    except Exception as exc:
        logger.error('org_deletion ops email failed: %s', exc)
        return False


def request_deletion(
    org_id: str,
    requester_user_id: str,
    *,
    requester_email: str | None = None,
) -> dict[str, Any]:
    """Stamp ``deletion_requested_at`` and notify ops.

    Raises :class:`OrgDeletionError` for the caller-fault paths so the route
    can map them to HTTP status codes:

    - ``org_not_found``   → 404
    - ``forbidden``       → 403 (caller is not the org owner)

    Re-requests (timestamp already set) are a no-op — we return the existing
    timestamp and skip the notification email.
    """
    org = _get_org(org_id)
    if not org:
        raise OrgDeletionError('org_not_found', f'Organization {org_id} not found')

    role = _get_caller_role(org_id, requester_user_id)
    if role != 'owner':
        raise OrgDeletionError(
            'forbidden',
            'Only the org owner can request school deletion',
        )

    existing = org.get('deletion_requested_at')
    if existing:
        return {'ok': True, 'deletion_requested_at': existing, 'already_requested': True}

    now = datetime.now(timezone.utc).isoformat()
    supabase = _get_supabase()
    supabase.table('organizations').update(
        {'deletion_requested_at': now},
    ).eq('id', org_id).execute()

    # Email is best-effort: timestamp persistence is the source of truth.
    _notify_ops(org, requester_user_id, requester_email, now)

    return {'ok': True, 'deletion_requested_at': now, 'already_requested': False}


def finalize_hard_delete(org_id: str) -> dict[str, Any]:
    """Ops-side hard-delete finalizer.

    Releases the org's `{slug}.chesster.io` registration on Vercel (so the
    Vercel project domain list doesn't grow unbounded as schools come and go)
    and then drops the organization row. Vercel failure is best-effort — it
    logs but does NOT block the row drop, mirroring the pattern in
    ``admin.remove_custom_domain``.

    Idempotent: missing org returns ``{ok: True, already_gone: True}``.
    """
    org = _get_org(org_id)
    if not org:
        return {'ok': True, 'already_gone': True}

    slug = org.get('slug')
    if slug:
        try:
            from services.vercel_client import (
                VercelAPIError,
                get_client,
                subdomain_for_slug,
            )
            domain = subdomain_for_slug(slug)
            try:
                get_client().remove_domain(domain)
                logger.info('hard-delete: vercel removed %s', domain)
            except VercelAPIError as exc:
                if exc.status_code != 404:
                    logger.warning(
                        'hard-delete: vercel remove_domain failed for %s: %s',
                        domain, exc,
                    )
        except Exception as exc:
            logger.warning('hard-delete: vercel cleanup unexpected error: %s', exc)

    supabase = _get_supabase()
    supabase.table('organizations').delete().eq('id', org_id).execute()
    logger.info('hard-delete: org row dropped id=%s slug=%s', org_id, slug)
    return {'ok': True, 'org_id': org_id, 'slug': slug}
