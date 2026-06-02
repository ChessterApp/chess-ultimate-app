"""
Lifecycle email scheduler (PRD §11.2 #6).

After an org activates, schedule three emails:
  * day 1 — welcome + checklist
  * day 3 — nudge unfinished onboarding items
  * day 7 — success story + upgrade prompt if approaching seat cap

The scheduler is dumb: it writes rows to ``lifecycle_emails`` keyed by
(org_id, kind). A Flask CLI command (``flask lifecycle-emails send-due``)
picks them up via cron and sends through Resend.

Templates live in ``backend/templates/emails/lifecycle/*.html`` and accept
the org dict + a small context. The renderer is plain string substitution;
we deliberately avoid Jinja here to keep the dep graph thin.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


KINDS = ('welcome_day1', 'nudge_day3', 'success_day7')


def _supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def _template_path(kind: str) -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'templates', 'emails', 'lifecycle', f'{kind}.html')


def _render_template(kind: str, ctx: dict[str, Any]) -> str:
    """Plain-text template substitution: ``{{name}}`` → ctx['name']."""
    with open(_template_path(kind), encoding='utf-8') as f:
        raw = f.read()
    def repl(m: re.Match[str]) -> str:
        return str(ctx.get(m.group(1).strip(), ''))
    return re.sub(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', repl, raw)


# ─── Scheduling ─────────────────────────────────────────────────────────


def schedule_for_org(org_id: str, *, activated_at: datetime | None = None) -> list[dict]:
    """Schedule the day-1 / day-3 / day-7 lifecycle emails for an org.

    Returns the rows that were *attempted* — duplicates from a re-run are
    silently dropped by the (org_id, kind) unique index.
    """
    base = (activated_at or datetime.now(timezone.utc)).replace(microsecond=0)
    rows = [
        {'org_id': org_id, 'kind': 'welcome_day1',
         'scheduled_for': (base + timedelta(days=1)).isoformat()},
        {'org_id': org_id, 'kind': 'nudge_day3',
         'scheduled_for': (base + timedelta(days=3)).isoformat()},
        {'org_id': org_id, 'kind': 'success_day7',
         'scheduled_for': (base + timedelta(days=7)).isoformat()},
    ]
    supabase = _supabase()
    try:
        supabase.table('lifecycle_emails').upsert(
            rows, on_conflict='org_id,kind', ignore_duplicates=True,
        ).execute()
    except Exception as exc:
        logger.warning('lifecycle schedule_for_org failed for %s: %s', org_id, exc)
    return rows


# ─── Sending ────────────────────────────────────────────────────────────


def fetch_due(now: datetime | None = None, limit: int = 100) -> list[dict]:
    """Return rows with scheduled_for <= now AND sent_at IS NULL."""
    now = now or datetime.now(timezone.utc)
    supabase = _supabase()
    try:
        res = (
            supabase.table('lifecycle_emails')
            .select('*')
            .is_('sent_at', None)
            .lte('scheduled_for', now.isoformat())
            .order('scheduled_for', desc=False)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])
    except Exception as exc:
        logger.warning('fetch_due failed: %s', exc)
        return []


def should_skip(row: dict, org: dict) -> bool:
    """Skip rules — return True when the email should be skipped because
    the underlying action is already done."""
    kind = row.get('kind')
    if kind == 'nudge_day3':
        checklist = org.get('onboarding_checklist') or {}
        if isinstance(checklist, dict) and checklist.get('all_completed'):
            return True
    return False


def mark_sent(row_id: str) -> None:
    _supabase().table('lifecycle_emails').update({
        'sent_at': datetime.now(timezone.utc).isoformat(),
        'error': None,
    }).eq('id', row_id).execute()


def mark_error(row_id: str, message: str) -> None:
    _supabase().table('lifecycle_emails').update({
        'error': message[:1000],
    }).eq('id', row_id).execute()


def send_due(now: datetime | None = None, limit: int = 100) -> dict:
    """Iterate all due rows and try to send each. Returns a summary dict.

    Sender wiring is decoupled via ``_send_one`` so unit tests can replace
    it without monkey-patching Resend's HTTP layer.
    """
    sent = 0
    skipped = 0
    errored = 0
    for row in fetch_due(now=now, limit=limit):
        org = _get_org_with_director(row['org_id'])
        if not org:
            mark_error(row['id'], 'org_not_found')
            errored += 1
            continue
        if should_skip(row, org):
            mark_sent(row['id'])
            skipped += 1
            continue
        ok, reason = _send_one(row, org)
        if ok:
            mark_sent(row['id'])
            sent += 1
        else:
            mark_error(row['id'], reason or 'unknown')
            errored += 1
    return {'sent': sent, 'skipped': skipped, 'errored': errored}


def _get_org_with_director(org_id: str) -> dict | None:
    try:
        supabase = _supabase()
        org_res = (
            supabase.table('organizations')
            .select(
                'id, name, slug, contact_email, logo_url, primary_color, '
                'email_sender_domain, email_sender_status, onboarding_checklist',
            )
            .eq('id', org_id).single().execute()
        )
        if not getattr(org_res, 'data', None):
            return None
        org = dict(org_res.data)
        # Best-effort director-email lookup. Falls back to contact_email.
        director_row = (
            supabase.table('organization_members')
            .select('user_id')
            .eq('organization_id', org_id)
            .eq('role', 'owner')
            .limit(1)
            .execute()
        )
        if director_row.data:
            org['_owner_user_id'] = director_row.data[0].get('user_id')
        return org
    except Exception as exc:
        logger.warning('_get_org_with_director failed for %s: %s', org_id, exc)
        return None


def _send_one(row: dict, org: dict) -> tuple[bool, str | None]:
    from services import email as email_svc
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        return False, 'RESEND_API_KEY not configured'
    to_email = org.get('contact_email') or org.get('_owner_user_id') or ''
    if '@' not in to_email:
        return False, 'no contact_email on org'
    ctx = {
        'school_name': org.get('name') or 'your school',
        'slug': org.get('slug') or '',
        'primary_color': org.get('primary_color') or '#1a73e8',
        'logo_url': org.get('logo_url') or '',
        'dashboard_url': f"https://{org.get('slug') or 'app'}.chesster.io/admin",
        'upgrade_url': 'https://chesster.io/admin/billing?upgrade=pro',
    }
    try:
        html = _render_template(row['kind'], ctx)
    except FileNotFoundError:
        return False, f'template missing: {row["kind"]}'
    body = {
        'from': email_svc.resolve_from_address(org),
        'to': [to_email],
        'subject': _subject_for(row['kind'], org),
        'html': html,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    try:
        email_svc._post_json(email_svc.RESEND_API_URL, headers, body)
        return True, None
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'


def _subject_for(kind: str, org: dict) -> str:
    name = org.get('name') or 'your school'
    if kind == 'welcome_day1':
        return f'Welcome to {name} on Chesster — your first-week checklist'
    if kind == 'nudge_day3':
        return f'A few quick wins for {name}'
    if kind == 'success_day7':
        return f'Tips for growing {name} — week 1 in the books'
    if kind == 'custom_domain_active':
        return f'Your custom domain is live'
    if kind == 'custom_domain_failed':
        return f'Custom domain — DNS verification failed'
    return f'{name} on Chesster'


# ─── Terminal-state hook (custom domain) ────────────────────────────────


def notify_custom_domain_status(domain: str, status: str) -> None:
    """Best-effort notification when a custom domain reaches active/failed.

    Sends immediately (one-shot, not scheduled) so the director sees the
    result in their inbox during the same browser session.
    """
    if status not in ('active', 'failed'):
        return
    supabase = _supabase()
    try:
        org_res = (
            supabase.table('organizations')
            .select(
                'id, name, slug, contact_email, logo_url, primary_color, '
                'custom_domain, email_sender_domain, email_sender_status',
            )
            .eq('custom_domain', domain).single().execute()
        )
    except Exception as exc:
        logger.warning('notify_custom_domain_status fetch failed: %s', exc)
        return
    if not getattr(org_res, 'data', None):
        return
    org = dict(org_res.data)
    kind = 'custom_domain_active' if status == 'active' else 'custom_domain_failed'
    row = {'id': 'inline', 'kind': kind, 'org_id': org['id']}
    ok, reason = _send_one(row, org)
    if not ok:
        logger.warning(
            'custom-domain lifecycle email failed (status=%s domain=%s): %s',
            status, domain, reason,
        )
