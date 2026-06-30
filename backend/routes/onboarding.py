"""
Onboarding API — pending_onboarding CRUD for the school wizard.

Per PRD §6.2 — lets a director save/resume their wizard state before
payment. Promoted to `organizations` + `organization_billing` on success.

Endpoints (all auth via X-User-Id header, which carries the Clerk user id):
  POST   /api/onboarding/save     — upsert payload + step
  GET    /api/onboarding/resume   — fetch the caller's pending row
  DELETE /api/onboarding/complete — clear the row after org creation
"""

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

onboarding_bp = Blueprint('onboarding', __name__, url_prefix='/api/onboarding')


def _get_supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def _require_clerk_user() -> tuple[str | None, tuple | None]:
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None, (jsonify({'error': 'Missing X-User-Id header'}), 401)
    return user_id, None


def _ttl_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()


_VALID_STEPS = ('account', 'school', 'plan', 'payment', 'brand', 'invite', 'done')


@onboarding_bp.route('/save', methods=['POST'])
def save_onboarding():
    """Upsert the wizard state for the calling user."""
    user_id, err = _require_clerk_user()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    step = data.get('step', 'account')
    if step not in _VALID_STEPS:
        return jsonify({'error': 'invalid step', 'step': step}), 400
    payload = data.get('payload', {})
    email = data.get('email')
    if not isinstance(payload, dict):
        return jsonify({'error': 'payload must be an object'}), 400

    row = {
        'clerk_user_id': user_id,
        'step': step,
        'payload': payload,
        'expires_at': _ttl_iso(),
    }
    if email:
        row['email'] = email

    supabase = _get_supabase()
    supabase.table('pending_onboarding').upsert(
        row, on_conflict='clerk_user_id'
    ).execute()

    return jsonify({'status': 'saved', 'step': step}), 200


@onboarding_bp.route('/resume', methods=['GET'])
def resume_onboarding():
    """Return the pending_onboarding row for the calling user, if any."""
    user_id, err = _require_clerk_user()
    if err:
        return err

    supabase = _get_supabase()
    result = (
        supabase.table('pending_onboarding')
        .select('*')
        .eq('clerk_user_id', user_id)
        .maybe_single()
        .execute()
    )
    if not result or not getattr(result, 'data', None):
        return jsonify({'pending': None}), 200

    return jsonify({'pending': result.data}), 200


@onboarding_bp.route('/complete', methods=['DELETE'])
def complete_onboarding():
    """Clear the pending row — called after successful org creation."""
    user_id, err = _require_clerk_user()
    if err:
        return err

    supabase = _get_supabase()
    supabase.table('pending_onboarding').delete().eq(
        'clerk_user_id', user_id
    ).execute()

    return jsonify({'status': 'completed'}), 200


_SLUG_RE = __import__('re').compile(r'^[a-z0-9]([a-z0-9-]{1,28}[a-z0-9])?$')


def _register_subdomain_best_effort(supabase, org_id: str, slug: str) -> None:
    """Register `{slug}.chesster.io` with Vercel and persist status.

    Never raises — Vercel/network failures are logged and recorded on the
    organization row but must not block self-serve signup.
    """
    from services.vercel_client import (
        VercelAPIError,
        get_client,
        subdomain_for_slug,
    )

    domain = subdomain_for_slug(slug)
    update: dict = {}
    try:
        result = get_client().add_domain(domain)
        vercel_id = result.get('id') or result.get('name') or domain
        update['subdomain_vercel_id'] = vercel_id
        if result.get('verified'):
            update['subdomain_status'] = 'active'
            update['subdomain_verified_at'] = datetime.now(timezone.utc).isoformat()
        else:
            update['subdomain_status'] = 'pending'
        update['subdomain_last_error'] = None
        logger.info(
            'subdomain registered: org=%s domain=%s status=%s',
            org_id, domain, update['subdomain_status'],
        )
    except VercelAPIError as exc:
        if exc.code == 'domain_already_in_use':
            # Already on the project — treat as success; verify later.
            update['subdomain_status'] = 'pending'
            update['subdomain_last_error'] = None
            logger.info(
                'subdomain already registered (idempotent): org=%s domain=%s',
                org_id, domain,
            )
        else:
            update['subdomain_status'] = 'failed'
            update['subdomain_last_error'] = str(exc)
            logger.error(
                'subdomain registration FAILED: org=%s domain=%s err=%s',
                org_id, domain, exc,
            )
    except Exception as exc:
        update['subdomain_status'] = 'failed'
        update['subdomain_last_error'] = f'unexpected: {exc}'
        logger.exception(
            'subdomain registration unexpected error: org=%s domain=%s',
            org_id, domain,
        )

    try:
        supabase.table('organizations').update(update).eq('id', org_id).execute()
    except Exception as exc:
        logger.warning('subdomain status persist failed for org=%s: %s', org_id, exc)


@onboarding_bp.route('/create-org', methods=['POST'])
def create_org_self_serve():
    """
    Self-serve org creation called by the wizard's "create org" step.

    Wraps the super-admin org-creation logic but runs under the caller's
    authenticated session (X-User-Id). The caller becomes the owner.

    Body: { name, slug, contact_email? }
    Returns: { organization, clerk_synced }
    """
    user_id, err = _require_clerk_user()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    slug = (body.get('slug') or '').strip().lower()
    contact_email = (body.get('contact_email') or '').strip() or None

    if not name or not slug:
        return jsonify({'error': 'name and slug are required'}), 400
    if not _SLUG_RE.match(slug):
        return jsonify({'error': 'invalid slug format'}), 400

    supabase = _get_supabase()

    # Defensive: re-check slug uniqueness server-side. The wizard already
    # debounce-checked, but races happen.
    try:
        existing = (
            supabase.table('organizations')
            .select('id')
            .eq('slug', slug)
            .limit(1)
            .execute()
        )
        if existing.data:
            return jsonify({'error': 'slug_taken', 'slug': slug}), 409
    except Exception as exc:
        logger.warning('slug uniqueness check failed: %s', exc)

    # Best-effort: pull the caller's pending_onboarding row so any brand
    # fields they already chose in the wizard get persisted at insert time
    # (rather than landing via a follow-up PUT that can race or silently fail).
    pending_payload: dict = {}
    try:
        pending = (
            supabase.table('pending_onboarding')
            .select('payload')
            .eq('clerk_user_id', user_id)
            .maybe_single()
            .execute()
        )
        if pending and getattr(pending, 'data', None):
            pending_payload = pending.data.get('payload') or {}
    except Exception as exc:
        logger.warning('pending_onboarding lookup failed for %s: %s', user_id, exc)

    try:
        insert_payload = {
            'slug': slug,
            'name': name,
            'status': 'trial',  # Promoted to 'active' by the Whop webhook.
        }
        if contact_email:
            insert_payload['contact_email'] = contact_email
        for brand_key in (
            'logo_url',
            'primary_color',
            'secondary_color',
            'accent_color',
            'favicon_url',
            'custom_css',
            'landing_page_config',
        ):
            value = pending_payload.get(brand_key)
            if value is not None:
                insert_payload[brand_key] = value
        inserted = supabase.table('organizations').insert(insert_payload).execute()
        rows = inserted.data or []
        if not rows:
            return jsonify({'error': 'insert_failed'}), 500
        org_row = rows[0]
        org_id = org_row['id']
    except Exception as exc:
        logger.exception('self-serve org insert failed: %s', exc)
        return jsonify({'error': 'create_failed'}), 500

    # Best-effort: register {slug}.chesster.io with Vercel so Let's Encrypt
    # issues a per-subdomain cert. Failure must NEVER block signup.
    _register_subdomain_best_effort(supabase, org_id, slug)

    # Caller becomes the owner
    try:
        supabase.table('organization_members').upsert({
            'organization_id': org_id,
            'user_id': user_id,
            'role': 'owner',
            'invited_by': user_id,
        }, on_conflict='organization_id,user_id').execute()
    except Exception as exc:
        logger.warning('owner membership insert failed: %s', exc)

    # Best-effort Clerk sync (won't block on failure)
    clerk_org_id = None
    try:
        from routes.super_admin import _clerk_sync_org, _clerk_sync_membership
        clerk_org_id = _clerk_sync_org(name=name, slug=slug, created_by_user_id=user_id)
        if clerk_org_id:
            supabase.table('organizations').update(
                {'clerk_org_id': clerk_org_id}
            ).eq('id', org_id).execute()
            org_row['clerk_org_id'] = clerk_org_id
            _clerk_sync_membership(clerk_org_id, user_id, 'owner')
    except Exception as exc:
        logger.warning('clerk sync (self-serve) failed: %s', exc)

    # Schedule day-1 / day-3 / day-7 lifecycle emails (PRD §11.2 #6).
    try:
        from services.lifecycle_emails import schedule_for_org
        schedule_for_org(org_id)
    except Exception as exc:
        logger.warning('lifecycle schedule failed for org=%s: %s', org_id, exc)

    return jsonify({
        'organization': org_row,
        'clerk_synced': bool(clerk_org_id),
    }), 201
