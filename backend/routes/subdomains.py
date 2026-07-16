"""
Subdomain API — slug availability checks for the school onboarding wizard.

GET /api/subdomains/check?slug=foo
  → { available: bool, reason?: string, suggestions?: string[] }

Per PRD §6.5. Reserved slugs are blocked; otherwise we hit the
organizations table for a uniqueness check.
"""

from __future__ import annotations

import logging
import re

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

subdomains_bp = Blueprint('subdomains', __name__, url_prefix='/api/subdomains')


# Reserved slugs — these collide with platform routes / middleware behaviour
# (`admin`, `super-admin`) or are likely to confuse parents (`auth`, etc).
RESERVED_SLUGS: frozenset[str] = frozenset({
    'admin', 'api', 'www', 'app', 'super-admin', 'onboarding',
    'auth', 'signin', 'signup', 'sign-in', 'sign-up',
    'for-schools', 'support', 'help', 'docs', 'blog', 'about',
    'login', 'logout', 'register', 'home', 'dashboard', 'settings',
    'mail', 'email', 'static', 'assets', 'cdn', 'media',
    'chesster', 'whop', 'stripe', 'clerk', 'supabase',
})


_SLUG_RE = re.compile(r'^[a-z0-9]([a-z0-9-]{1,28}[a-z0-9])?$')


from utils.supabase_client import get_supabase as _get_supabase


def _is_well_formed(slug: str) -> bool:
    """Slug rules: lowercase alphanumeric + hyphens, 1-30 chars, no leading/trailing hyphen."""
    if not slug or len(slug) > 30:
        return False
    return bool(_SLUG_RE.match(slug))


def _suggestions_for(slug: str) -> list[str]:
    base = re.sub(r'-+', '-', slug.strip('-')) or 'school'
    return [f'{base}-school', f'{base}-chess', f'my-{base}']


@subdomains_bp.route('/check', methods=['GET'])
def check_subdomain():
    raw = (request.args.get('slug') or '').strip().lower()
    if not raw:
        return jsonify({'available': False, 'reason': 'empty'}), 200

    if not _is_well_formed(raw):
        return jsonify({
            'available': False,
            'reason': 'invalid_format',
            'message': 'Use lowercase letters, numbers, and hyphens (2-30 chars).',
        }), 200

    if raw in RESERVED_SLUGS:
        return jsonify({
            'available': False,
            'reason': 'reserved',
            'suggestions': _suggestions_for(raw),
        }), 200

    # DB lookup
    try:
        supabase = _get_supabase()
        res = (
            supabase.table('organizations')
            .select('id')
            .eq('slug', raw)
            .limit(1)
            .execute()
        )
        rows = getattr(res, 'data', None) or []
        if rows:
            return jsonify({
                'available': False,
                'reason': 'taken',
                'suggestions': _suggestions_for(raw),
            }), 200
    except Exception as exc:
        logger.warning('subdomain check db error for slug=%s: %s', raw, exc)
        # On DB error, treat as not-available to fail closed; the wizard will
        # show a retry message rather than letting a director progress with
        # an unverified slug.
        return jsonify({'available': False, 'reason': 'db_error'}), 503

    return jsonify({'available': True}), 200
