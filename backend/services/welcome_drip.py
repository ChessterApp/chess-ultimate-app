"""
Welcome drip (P4 — sent via Resend).

The Clerk ``user.created`` webhook (``frontend/src/lib/welcome-drip.ts``)
writes five ``welcome_emails`` rows per new user (day 0/1/3/5/7). A Flask CLI
command (``flask welcome-emails send-due``) picks due rows up via cron and
sends them through Resend.

Guards, in order, for each due row:
  * ``WELCOME_DRIP_ENABLED`` must be exactly ``1`` or nothing is sent;
  * the address is in ``email_opt_outs``      → skipped ``opted_out``;
  * the row is more than 48h overdue          → skipped ``stale`` (enabling the
    flag never blasts a backlog);
  * an earlier step for the user is unsent    → deferred ``out_of_order``
    (nothing sent to that user this run; the row stays due);
  * a failed send increments ``attempts``; the third failure is skipped
    ``failed``.

Templates live in ``backend/templates/emails/welcome/<locale>/step<N>.html``
and are wrapped in ``welcome/layout.html``. Rendering is plain ``{{var}}``
substitution, same as ``services/lifecycle_emails.py`` — no Jinja.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)


LOCALES = ('en', 'ru', 'kk')
STEPS = (1, 2, 3, 4, 5)
STALE_AFTER = timedelta(hours=48)
MAX_ATTEMPTS = 3

APP_URL = 'https://chesster.io'
LOGO_URL = 'https://chesster.io/static/images/chesster-logo-v3.png'
UNSUBSCRIBE_URL = 'https://api.chesster.io/api/email/unsubscribe'
DEFAULT_FROM = 'Chesster <noreply@chesster.io>'

SUBJECTS: dict[str, dict[int, str]] = {
    'en': {
        1: 'Welcome to Chesster ♟️',
        2: 'Your first lesson takes about 5 minutes',
        3: 'See what really happened in your last game',
        4: 'Start a learning streak today',
        5: 'One week with Chesster — what to try next',
    },
    'ru': {
        1: 'Добро пожаловать в Chesster ♟️',
        2: 'Первый урок — примерно 5 минут',
        3: 'Разбери свою последнюю партию',
        4: 'Начни серию занятий уже сегодня',
        5: 'Неделя с Chesster — что попробовать дальше',
    },
    'kk': {
        1: 'Chesster-ге қош келдің ♟️',
        2: 'Алғашқы сабақ — шамамен 5 минут',
        3: 'Соңғы ойыныңды талдап көр',
        4: 'Бүгін сабақ сериясын баста',
        5: 'Chesster-мен бір апта — ары қарай не істеуге болады',
    },
}

# (with first name, without first name)
GREETINGS: dict[str, tuple[str, str]] = {
    'en': ('Hi {name},', 'Hi there,'),
    'ru': ('Привет, {name}!', 'Привет!'),
    'kk': ('Сәлем, {name}!', 'Сәлем!'),
}

FOOTER: dict[str, dict[str, str]] = {
    'en': {
        'reason': 'You are getting this email because you signed up for Chesster.',
        'unsubscribe': 'Unsubscribe',
    },
    'ru': {
        'reason': 'Это письмо пришло, потому что у тебя есть аккаунт в Chesster.',
        'unsubscribe': 'Отписаться',
    },
    'kk': {
        'reason': 'Бұл хат саған Chesster-ге тіркелгенің үшін келді.',
        'unsubscribe': 'Жазылымнан бас тарту',
    },
}


def _supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def is_enabled() -> bool:
    return os.getenv('WELCOME_DRIP_ENABLED') == '1'


# ─── Unsubscribe tokens ─────────────────────────────────────────────────


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _unsub_secret() -> bytes:
    secret = os.getenv('EMAIL_UNSUB_SECRET')
    if not secret:
        raise RuntimeError('EMAIL_UNSUB_SECRET not configured')
    return secret.encode('utf-8')


def make_unsubscribe_token(email: str) -> str:
    """``b64url(email).b64url(HMAC-SHA256(secret, email))`` for a lower-cased email."""
    addr = email.strip().lower().encode('utf-8')
    sig = hmac.new(_unsub_secret(), addr, hashlib.sha256).digest()
    return f'{_b64(addr)}.{_b64(sig)}'


def verify_unsubscribe_token(token: str | None) -> str | None:
    """Return the lower-cased email the token was signed for, or None."""
    if not token or token.count('.') != 1:
        return None
    try:
        payload, sig = token.split('.')
        addr = _unb64(payload)
        expected = hmac.new(_unsub_secret(), addr, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig)):
            return None
        email = addr.decode('utf-8')
    except (ValueError, UnicodeDecodeError, RuntimeError):
        return None
    return email if '@' in email else None


def unsubscribe_url(email: str) -> str:
    return f'{UNSUBSCRIBE_URL}?t={quote(make_unsubscribe_token(email))}'


# ─── Rendering ──────────────────────────────────────────────────────────


def _template_dir() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'templates', 'emails', 'welcome')


def _substitute(raw: str, ctx: dict[str, Any]) -> str:
    """Plain-text template substitution: ``{{name}}`` → ctx['name']."""
    def repl(m: re.Match[str]) -> str:
        return str(ctx.get(m.group(1).strip(), ''))
    return re.sub(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', repl, raw)


def _read(*parts: str) -> str:
    with open(os.path.join(_template_dir(), *parts), encoding='utf-8') as f:
        return f.read()


def greeting(locale: str, first_name: str | None) -> str:
    with_name, without = GREETINGS[locale]
    name = (first_name or '').strip()
    return with_name.format(name=html.escape(name)) if name else without


def render_email(step: int, locale: str, first_name: str | None, email: str) -> tuple[str, str, str]:
    """Return ``(subject, html, unsubscribe_url)`` for one step."""
    locale = locale if locale in LOCALES else 'en'
    unsub = unsubscribe_url(email)
    content = _substitute(_read(locale, f'step{step}.html'), {
        'greeting': greeting(locale, first_name),
        'app_url': APP_URL,
    })
    subject = SUBJECTS[locale][step]
    page = _substitute(_read('layout.html'), {
        'lang': locale,
        'subject': html.escape(subject),
        'logo_url': LOGO_URL,
        'app_url': APP_URL,
        'content': content,
        'footer_reason': FOOTER[locale]['reason'],
        'unsubscribe_label': FOOTER[locale]['unsubscribe'],
        'unsubscribe_url': html.escape(unsub),
    })
    return subject, page, unsub


# ─── Sending ────────────────────────────────────────────────────────────


def send_email(to_email: str, subject: str, html_body: str, unsub_url: str) -> str | None:
    """POST one email to Resend; returns the Resend id. Raises on failure."""
    from services import email as email_svc
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        raise RuntimeError('RESEND_API_KEY not configured')
    body = {
        'from': os.getenv('WELCOME_FROM') or DEFAULT_FROM,
        'to': [to_email],
        'subject': subject,
        'html': html_body,
        'headers': {
            'List-Unsubscribe': f'<{unsub_url}>',
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
        },
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    res = email_svc._post_json(email_svc.RESEND_API_URL, headers, body)
    return (res or {}).get('id')


def fetch_due(now: datetime, limit: int) -> list[dict]:
    res = (
        _supabase().table('welcome_emails')
        .select('*')
        .is_('sent_at', None)
        .is_('skipped_reason', None)
        .lte('scheduled_for', now.isoformat())
        .order('scheduled_for', desc=False)
        .order('step', desc=False)
        .limit(limit)
        .execute()
    )
    return list(res.data or [])


def opted_out_emails(emails: list[str]) -> set[str]:
    lowered = sorted({e.strip().lower() for e in emails if e})
    if not lowered:
        return set()
    res = _supabase().table('email_opt_outs').select('email').in_('email', lowered).execute()
    return {r['email'] for r in (res.data or [])}


def has_unsent_earlier_step(user_id: str, step: int) -> bool:
    res = (
        _supabase().table('welcome_emails')
        .select('id')
        .eq('user_id', user_id)
        .lt('step', step)
        .is_('sent_at', None)
        .is_('skipped_reason', None)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def update_row(row_id: str, fields: dict[str, Any]) -> None:
    _supabase().table('welcome_emails').update(fields).eq('id', row_id).execute()


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def send_due(now: datetime | None = None, limit: int = 100) -> dict:
    """Send every due welcome email. Returns a summary dict."""
    if not is_enabled():
        return {'disabled': True}
    for var in ('EMAIL_UNSUB_SECRET', 'RESEND_API_KEY'):
        if not os.getenv(var):
            logger.error('welcome drip: %s not configured, refusing to send', var)
            return {'disabled': False, 'error': f'{var} not configured'}

    now = now or datetime.now(timezone.utc)
    summary = {'sent': 0, 'opted_out': 0, 'stale': 0, 'out_of_order': 0,
               'errored': 0, 'failed': 0}
    rows = fetch_due(now, limit)
    opted_out = opted_out_emails([r['email'] for r in rows])
    held_users: set[str] = set()

    for row in rows:
        user_id = row['user_id']
        if user_id in held_users:
            summary['out_of_order'] += 1
            continue
        if row['email'].strip().lower() in opted_out:
            update_row(row['id'], {'skipped_reason': 'opted_out'})
            summary['opted_out'] += 1
            continue
        if now - _parse_ts(row['scheduled_for']) > STALE_AFTER:
            update_row(row['id'], {'skipped_reason': 'stale'})
            summary['stale'] += 1
            continue
        if has_unsent_earlier_step(user_id, row['step']):
            held_users.add(user_id)
            summary['out_of_order'] += 1
            continue

        try:
            subject, html_body, unsub = render_email(
                row['step'], row.get('locale') or 'en', row.get('first_name'), row['email'],
            )
            resend_id = send_email(row['email'], subject, html_body, unsub)
        except Exception as exc:
            attempts = int(row.get('attempts') or 0) + 1
            fields: dict[str, Any] = {
                'attempts': attempts,
                'error': f'{type(exc).__name__}: {exc}'[:1000],
            }
            if attempts >= MAX_ATTEMPTS:
                fields['skipped_reason'] = 'failed'
                summary['failed'] += 1
            else:
                summary['errored'] += 1
            update_row(row['id'], fields)
            # Later steps for this user wait until this one is resolved.
            held_users.add(user_id)
            continue

        update_row(row['id'], {
            'sent_at': datetime.now(timezone.utc).isoformat(),
            'resend_id': resend_id,
            'error': None,
        })
        summary['sent'] += 1
    return summary


# ─── Opt-out ────────────────────────────────────────────────────────────


def unsubscribe(email: str) -> None:
    """Record the opt-out and skip the address's remaining welcome emails."""
    email = email.strip().lower()
    supabase = _supabase()
    owner = (
        supabase.table('welcome_emails').select('user_id')
        .eq('email', email).limit(1).execute()
    )
    user_id = owner.data[0]['user_id'] if owner.data else None
    supabase.table('email_opt_outs').upsert(
        {'email': email, 'user_id': user_id}, on_conflict='email',
    ).execute()
    (
        supabase.table('welcome_emails')
        .update({'skipped_reason': 'opted_out'})
        .eq('email', email)
        .is_('sent_at', None)
        .is_('skipped_reason', None)
        .execute()
    )
