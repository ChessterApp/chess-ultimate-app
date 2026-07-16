"""
Email service — Resend integration for transactional emails.

Phase 1 scope: school onboarding invite emails (PRD §6.4). Branded senders
deferred to Phase 2.

The single public helper is `send_invite_email(org_id, to_email, role)`.
On failure we write a row to `invite_email_failures` for retry visibility
and never raise — invite-create flow must not block on email send.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
import json
from typing import Any

logger = logging.getLogger(__name__)


RESEND_API_URL = 'https://api.resend.com/emails'
DEFAULT_INVITE_FROM = os.getenv('RESEND_INVITE_FROM', 'invites@chesster.io')


from utils.supabase_client import get_supabase as _get_supabase


def _public_app_url() -> str:
    return os.getenv('PUBLIC_APP_URL', 'https://chesster.io').rstrip('/')


def _get_org(org_id: str) -> dict[str, Any] | None:
    try:
        supabase = _get_supabase()
        res = (
            supabase.table('organizations')
            .select(
                'id, name, slug, logo_url, primary_color, '
                'email_sender_domain, email_sender_status'
            )
            .eq('id', org_id)
            .single()
            .execute()
        )
        return res.data if getattr(res, 'data', None) else None
    except Exception as exc:
        logger.warning('email._get_org failed for org=%s: %s', org_id, exc)
        return None


def resolve_from_address(org: dict[str, Any] | None) -> str:
    """Pick the from-address for an outbound email.

    If the org has an *active* branded sender domain, use
    ``invites@<that-domain>``. Otherwise fall back to ``DEFAULT_INVITE_FROM``.
    """
    if not org:
        return DEFAULT_INVITE_FROM
    domain = (org.get('email_sender_domain') or '').strip().lower()
    status = (org.get('email_sender_status') or '').lower()
    if domain and status == 'active':
        return f'invites@{domain}'
    return DEFAULT_INVITE_FROM


def _build_invite_link(org: dict[str, Any], to_email: str) -> str:
    slug = org.get('slug') or ''
    base = _public_app_url()
    # Use the tenant subdomain when possible — falls back to apex if slug
    # missing (which shouldn't happen post-creation).
    if slug:
        return f'https://{slug}.chesster.io/sign-up?invite={to_email}'
    return f'{base}/sign-up?invite={to_email}'


def _render_html(org: dict[str, Any], invite_link: str, role: str) -> str:
    name = org.get('name') or 'your chess school'
    color = org.get('primary_color') or '#1a73e8'
    logo = org.get('logo_url') or ''
    logo_html = (
        f'<img src="{logo}" alt="{name}" '
        f'style="max-height:48px;margin-bottom:16px"/>'
        if logo else ''
    )
    return f"""<!doctype html>
<html><body style="font-family:Inter,Arial,sans-serif;background:#f8fafc;padding:24px">
  <table cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:32px">
    <tr><td>
      {logo_html}
      <h1 style="font-size:22px;margin:0 0 12px 0;color:#0f172a">You're invited to join {name} on Chesster.</h1>
      <p style="font-size:15px;line-height:1.5;color:#334155">
        Your coach has invited you as a <strong>{role}</strong>. Click the button below to set up your account and start playing.
      </p>
      <p style="margin:24px 0">
        <a href="{invite_link}"
           style="display:inline-block;background:{color};color:#fff;text-decoration:none;
                  padding:12px 20px;border-radius:8px;font-weight:600">
          Accept your invite
        </a>
      </p>
      <p style="font-size:13px;color:#64748b">If the button doesn't work, copy this link:<br/>
        <a href="{invite_link}" style="color:{color};word-break:break-all">{invite_link}</a></p>
    </td></tr>
  </table>
</body></html>"""


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


def _log_failure(org_id: str | None, to_email: str, role: str, message: str) -> None:
    try:
        supabase = _get_supabase()
        supabase.table('invite_email_failures').insert({
            'organization_id': org_id,
            'to_email': to_email,
            'role': role,
            'error_message': message[:1000],
        }).execute()
    except Exception as exc:
        # Don't recurse — just log
        logger.error('invite_email_failures insert failed: %s', exc)


def send_invite_email(
    org_id: str,
    to_email: str,
    role: str = 'student',
    *,
    invite_link: str | None = None,
) -> bool:
    """
    Send an invite email via Resend. Returns True on send-success, False
    otherwise. Never raises — failures are recorded in invite_email_failures.
    """
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        msg = 'RESEND_API_KEY not configured'
        logger.warning('send_invite_email: %s', msg)
        _log_failure(org_id, to_email, role, msg)
        return False

    org = _get_org(org_id) or {'id': org_id, 'name': 'Chesster', 'slug': ''}
    link = invite_link or _build_invite_link(org, to_email)
    subject = f'You\'re invited to join {org.get("name", "Chesster")}'

    body = {
        'from': resolve_from_address(org),
        'to': [to_email],
        'subject': subject,
        'html': _render_html(org, link, role),
    }

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    try:
        _post_json(RESEND_API_URL, headers, body)
        logger.info('invite email sent: org=%s to=%s', org_id, to_email)
        return True
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode('utf-8')
        except Exception:
            err_body = ''
        msg = f'HTTP {exc.code}: {err_body[:500]}'
        logger.error('Resend HTTPError sending invite: %s', msg)
        _log_failure(org_id, to_email, role, msg)
        return False
    except Exception as exc:
        msg = f'{type(exc).__name__}: {exc}'
        logger.error('Resend send failed: %s', msg)
        _log_failure(org_id, to_email, role, msg)
        return False
