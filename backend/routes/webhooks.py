"""
Clerk Organizations Webhook Handler

Syncs Clerk organization events to Supabase:
  - organization.created
  - organization.updated
  - organization.deleted
  - organizationMembership.created
  - organizationMembership.updated
  - organizationMembership.deleted
  - user.created (Phase 5 — Chess Empire onboarding completion)

Webhook signing: Clerk signs webhooks with Svix. We verify using the
CLERK_WEBHOOK_SECRET environment variable.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/api/webhooks')

CLERK_WEBHOOK_SECRET = os.getenv('CLERK_WEBHOOK_SECRET', '')
VERCEL_WEBHOOK_SECRET = os.getenv('VERCEL_WEBHOOK_SECRET', '')


from utils.supabase_client import get_supabase as _get_supabase


def verify_svix_signature(payload: bytes, headers: dict) -> bool:
    """
    Verify Clerk/Svix webhook signature.
    Clerk uses Svix for webhook delivery. The signature is in the
    svix-signature header, using HMAC-SHA256 with the webhook secret.
    """
    if not CLERK_WEBHOOK_SECRET:
        logger.warning('CLERK_WEBHOOK_SECRET not set, skipping signature verification')
        return True

    svix_id = headers.get('svix-id', '')
    svix_timestamp = headers.get('svix-timestamp', '')
    svix_signature = headers.get('svix-signature', '')

    if not svix_id or not svix_timestamp or not svix_signature:
        logger.error('Missing Svix headers')
        return False

    # Check timestamp is within 5 minutes
    try:
        ts = int(svix_timestamp)
        if abs(time.time() - ts) > 300:
            logger.error('Svix timestamp too old')
            return False
    except ValueError:
        logger.error('Invalid Svix timestamp')
        return False

    # Build the signed content: "{svix_id}.{svix_timestamp}.{body}"
    signed_content = f'{svix_id}.{svix_timestamp}.'.encode() + payload

    # The secret is base64-encoded with a "whsec_" prefix
    secret = CLERK_WEBHOOK_SECRET
    if secret.startswith('whsec_'):
        secret = secret[6:]

    import base64
    secret_bytes = base64.b64decode(secret)

    expected = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()

    # svix-signature can have multiple signatures separated by spaces
    # Each prefixed with "v1,"
    for sig in svix_signature.split(' '):
        if sig.startswith('v1,'):
            sig_value = sig[3:]
            if hmac.compare_digest(expected_b64, sig_value):
                return True

    logger.error('Svix signature verification failed')
    return False


@webhooks_bp.route('/clerk', methods=['POST'])
def clerk_webhook():
    """
    Handle Clerk organization webhook events.
    Syncs org create/update/delete and member events to Supabase.
    """
    payload = request.get_data()
    headers = {
        'svix-id': request.headers.get('svix-id', ''),
        'svix-timestamp': request.headers.get('svix-timestamp', ''),
        'svix-signature': request.headers.get('svix-signature', ''),
    }

    if not verify_svix_signature(payload, headers):
        return jsonify({'error': 'Invalid signature'}), 401

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON'}), 400

    event_type = event.get('type', '')
    data = event.get('data', {})

    logger.info(f'Clerk webhook received: {event_type}')

    try:
        if event_type == 'organization.created':
            _handle_org_created(data)
        elif event_type == 'organization.updated':
            _handle_org_updated(data)
        elif event_type == 'organization.deleted':
            _handle_org_deleted(data)
        elif event_type == 'organizationMembership.created':
            _handle_member_created(data)
        elif event_type == 'organizationMembership.updated':
            _handle_member_updated(data)
        elif event_type == 'organizationMembership.deleted':
            _handle_member_deleted(data)
        elif event_type == 'user.created':
            _handle_user_created(event)
        else:
            logger.info(f'Ignoring unhandled event type: {event_type}')
    except Exception as e:
        logger.error(f'Error handling webhook {event_type}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

    return jsonify({'status': 'ok'}), 200


def _handle_org_created(data: dict):
    """Sync new Clerk organization to Supabase.

    Idempotency order (PRD §6):
      1. Match by clerk_org_id — confirmation echo, update in-place.
      2. Match by slug — adopt the Clerk id onto the existing row.
      3. Neither — insert a new row keyed on slug.
    """
    supabase = _get_supabase()
    slug = data.get('slug', '')
    name = data.get('name', '')
    logo_url = data.get('image_url')
    clerk_org_id = data.get('id', '')

    if not slug or not name:
        logger.error(f'Missing slug or name in org.created: {data}')
        return

    # 1) Already linked to this Clerk id? Treat as echo, refresh fields only.
    if clerk_org_id:
        existing_by_clerk = (
            supabase.table('organizations').select('id')
            .eq('clerk_org_id', clerk_org_id).execute().data or []
        )
        if existing_by_clerk:
            update_payload = {'name': name}
            if logo_url is not None:
                update_payload['logo_url'] = logo_url
            supabase.table('organizations').update(update_payload).eq(
                'clerk_org_id', clerk_org_id
            ).execute()
            logger.info(f'Organization confirmation echo for clerk_org_id={clerk_org_id}')
            return

    # 2) Existing slug-row without clerk_org_id — adopt the Clerk id.
    existing_by_slug = (
        supabase.table('organizations').select('id, clerk_org_id')
        .eq('slug', slug).execute().data or []
    )
    if existing_by_slug:
        row = existing_by_slug[0]
        update_payload = {'name': name}
        if logo_url is not None:
            update_payload['logo_url'] = logo_url
        if clerk_org_id and not row.get('clerk_org_id'):
            update_payload['clerk_org_id'] = clerk_org_id
        supabase.table('organizations').update(update_payload).eq(
            'slug', slug
        ).execute()
        logger.info(f'Organization adopted Clerk id for slug={slug}')
        return

    # 3) Fall back to the original upsert path (Clerk-admin-created-first).
    payload = {
        'slug': slug,
        'name': name,
        'logo_url': logo_url,
        'status': 'active',
    }
    if clerk_org_id:
        payload['clerk_org_id'] = clerk_org_id
    supabase.table('organizations').upsert(payload, on_conflict='slug').execute()
    logger.info(f'Organization created/upserted: {slug}')


def _handle_org_updated(data: dict):
    """Sync Clerk organization updates to Supabase."""
    supabase = _get_supabase()
    slug = data.get('slug', '')
    name = data.get('name', '')
    logo_url = data.get('image_url')

    if not slug:
        logger.error(f'Missing slug in org.updated: {data}')
        return

    update_data = {'name': name}
    if logo_url is not None:
        update_data['logo_url'] = logo_url

    supabase.table('organizations').update(update_data).eq('slug', slug).execute()

    logger.info(f'Organization updated: {slug}')


def _handle_org_deleted(data: dict):
    """Mark Clerk organization as suspended in Supabase (soft delete)."""
    supabase = _get_supabase()
    slug = data.get('slug', '')

    if not slug:
        # Try by ID lookup
        clerk_org_id = data.get('id', '')
        logger.warning(f'org.deleted without slug, clerk_id={clerk_org_id}')
        return

    supabase.table('organizations').update({
        'status': 'suspended',
    }).eq('slug', slug).execute()

    logger.info(f'Organization soft-deleted (suspended): {slug}')


def _map_clerk_role(clerk_role: str) -> str:
    """Map Clerk organization role to our role enum."""
    role_map = {
        'org:admin': 'admin',
        'org:member': 'student',
        'admin': 'admin',
        'basic_member': 'student',
    }
    return role_map.get(clerk_role, 'student')


def _handle_member_created(data: dict):
    """Sync new Clerk org membership to Supabase.

    Idempotency: match the parent org by clerk_org_id first, falling back to
    slug. Member is upserted on (organization_id, user_id) — repeated webhook
    deliveries are no-ops.
    """
    supabase = _get_supabase()

    org_data = data.get('organization', {})
    user_data = data.get('public_user_data', {})
    slug = org_data.get('slug', '')
    clerk_org_id = org_data.get('id', '')
    user_id = user_data.get('user_id', data.get('public_user_data', {}).get('user_id', ''))
    role = _map_clerk_role(data.get('role', 'basic_member'))

    if not user_id or not (slug or clerk_org_id):
        logger.error(f'Missing identifiers in membership.created: {data}')
        return

    org_id = _resolve_org_id(supabase, clerk_org_id=clerk_org_id, slug=slug)
    if not org_id:
        logger.error(f'Organization not found for clerk_org_id={clerk_org_id} slug={slug}')
        return

    supabase.table('organization_members').upsert({
        'organization_id': org_id,
        'user_id': user_id,
        'role': role,
    }, on_conflict='organization_id,user_id').execute()

    logger.info(f'Member added: user={user_id} org={slug or clerk_org_id} role={role}')


def _resolve_org_id(supabase, clerk_org_id: str = '', slug: str = '') -> str | None:
    """Find the Supabase org row id, preferring clerk_org_id over slug."""
    if clerk_org_id:
        rows = (
            supabase.table('organizations').select('id')
            .eq('clerk_org_id', clerk_org_id).execute().data or []
        )
        if rows:
            return rows[0].get('id')
    if slug:
        rows = (
            supabase.table('organizations').select('id')
            .eq('slug', slug).execute().data or []
        )
        if rows:
            return rows[0].get('id')
    return None


def _handle_member_updated(data: dict):
    """Sync Clerk org membership role changes to Supabase."""
    supabase = _get_supabase()

    org_data = data.get('organization', {})
    user_data = data.get('public_user_data', {})
    slug = org_data.get('slug', '')
    clerk_org_id = org_data.get('id', '')
    user_id = user_data.get('user_id', '')
    role = _map_clerk_role(data.get('role', 'basic_member'))

    if not user_id or not (slug or clerk_org_id):
        logger.error(f'Missing identifiers in membership.updated: {data}')
        return

    org_id = _resolve_org_id(supabase, clerk_org_id=clerk_org_id, slug=slug)
    if not org_id:
        logger.error(f'Organization not found for clerk_org_id={clerk_org_id} slug={slug}')
        return

    supabase.table('organization_members').update({
        'role': role,
    }).eq('organization_id', org_id).eq('user_id', user_id).execute()

    logger.info(f'Member updated: user={user_id} org={slug or clerk_org_id} role={role}')


def _handle_member_deleted(data: dict):
    """Remove Clerk org membership from Supabase."""
    supabase = _get_supabase()

    org_data = data.get('organization', {})
    user_data = data.get('public_user_data', {})
    slug = org_data.get('slug', '')
    clerk_org_id = org_data.get('id', '')
    user_id = user_data.get('user_id', '')

    if not user_id or not (slug or clerk_org_id):
        logger.error(f'Missing identifiers in membership.deleted: {data}')
        return

    org_id = _resolve_org_id(supabase, clerk_org_id=clerk_org_id, slug=slug)
    if not org_id:
        logger.error(f'Organization not found for clerk_org_id={clerk_org_id} slug={slug}')
        return

    supabase.table('organization_members').delete().eq(
        'organization_id', org_id
    ).eq('user_id', user_id).execute()

    logger.info(f'Member removed: user={user_id} org={slug or clerk_org_id}')


# =====================================================================
# user.created — Chess Empire onboarding completion (Phase 5)
# =====================================================================
#
# When a parent finishes Clerk sign-up, the SignUp page attaches the invite
# JWT to `unsafeMetadata.inviteJwt`. This handler verifies the JWT, upserts
# `external_student_id` onto the freshly-created organization_members row,
# adds the Clerk org membership, and records the JWT hash so a replayed
# webhook (or leaked JWT) cannot double-link the same student.
#
# Retry story (Svix does exponential backoff on non-2xx):
#   1. Verify JWT signature/expiry/required claims
#   2. Short-circuit if the JWT hash is already in invite_jwts_consumed
#   3. Confirm branch_invite_tokens row is not revoked
#   4. Look up the Chesster org (need clerk_org_id for Clerk API call)
#   5. Upsert organization_members (safe on retry via unique constraint)
#   6. Call clerk.create_membership (skip 422 already-member)
#   7. Insert invite_jwts_consumed row LAST — if 6 fails, 7 doesn't run and
#      the whole webhook is safe to retry
#
# Non-CE signups (no `inviteJwt` in unsafe_metadata) are silently skipped.


def _extract_primary_email(data: dict) -> str | None:
    """Pull the primary email from a Clerk user payload, else the first."""
    emails = data.get('email_addresses') or []
    if not isinstance(emails, list) or not emails:
        return None
    primary_id = data.get('primary_email_address_id')
    if primary_id:
        for entry in emails:
            if isinstance(entry, dict) and entry.get('id') == primary_id:
                addr = entry.get('email_address')
                if isinstance(addr, str) and addr:
                    return addr
    first = emails[0]
    if isinstance(first, dict):
        addr = first.get('email_address')
        if isinstance(addr, str) and addr:
            return addr
    return None


def _extract_name(data: dict) -> str | None:
    """Compose 'First Last' from a Clerk user payload, or None if neither set."""
    first = (data.get('first_name') or '').strip()
    last = (data.get('last_name') or '').strip()
    full = f'{first} {last}'.strip()
    return full or None


def _handle_user_created(event: dict) -> None:
    """Complete Chess Empire signup: verify invite JWT, link student, join org."""
    from services.invite_jwt import (
        InviteJwtError,
        jwt_jti_hash,
        verify_invite_jwt,
    )

    data = event.get('data', {}) or {}
    clerk_user_id = data.get('id')
    if not clerk_user_id:
        logger.warning('user.created without user id, skipping')
        return

    unsafe = data.get('unsafe_metadata') or {}
    raw_jwt = unsafe.get('inviteJwt')
    if not raw_jwt or not isinstance(raw_jwt, str):
        logger.info(
            'user.created for %s without inviteJwt metadata, skipping (non-CE signup)',
            clerk_user_id,
        )
        return

    try:
        claims = verify_invite_jwt(raw_jwt)
    except InviteJwtError as exc:
        logger.warning('user.created for %s with invalid invite JWT: %s', clerk_user_id, exc)
        return

    jti_hash = jwt_jti_hash(raw_jwt)
    supabase = _get_supabase()

    # 2) Single-use guard — replay is a no-op.
    existing = (
        supabase.table('invite_jwts_consumed')
        .select('jti_hash').eq('jti_hash', jti_hash).limit(1).execute()
    )
    if existing.data:
        logger.info(
            'Invite JWT already consumed for user %s, treating as replay',
            clerk_user_id,
        )
        return

    # 3) Refuse if the branch invite token has been revoked.
    tok = (
        supabase.table('branch_invite_tokens')
        .select('id, revoked_at')
        .eq('id', claims['branch_token_id']).limit(1).execute()
    )
    tok_row = (tok.data or [None])[0]
    if not tok_row or tok_row.get('revoked_at'):
        logger.warning(
            'Branch token %s revoked or missing; refusing to complete user %s',
            claims['branch_token_id'], clerk_user_id,
        )
        return

    # 4) Look up Chesster org row for clerk_org_id.
    org = (
        supabase.table('organizations')
        .select('id, clerk_org_id')
        .eq('id', claims['org_id']).limit(1).execute()
    )
    org_row = (org.data or [None])[0]
    if not org_row:
        logger.error(
            'Invite JWT for user %s references unknown org %s',
            clerk_user_id, claims['org_id'],
        )
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    email = _extract_primary_email(data)
    name = _extract_name(data)

    # 5) Upsert organization_members with the external linkage. Safe on retry:
    # the (organization_id, external_student_id, external_source) unique
    # constraint turns re-runs into idempotent no-ops.
    # Coaches share the external_student_id column, discriminated by role.
    # verify_invite_jwt normalizes a missing member_type to 'student'.
    member_role = 'coach' if claims.get('member_type') == 'coach' else 'student'
    member_payload = {
        'organization_id': claims['org_id'],
        'user_id': clerk_user_id,
        'role': member_role,
        'joined_at': now_iso,
        'external_student_id': claims['student_id'],
        'external_source': 'chess_empire',
        'link_status': 'verified',
        'link_verified_at': now_iso,
    }
    if email:
        member_payload['email'] = email
    if name:
        member_payload['name'] = name
    supabase.table('organization_members').upsert(
        member_payload,
        on_conflict='organization_id,external_student_id,external_source',
    ).execute()

    # 6) Add Clerk org membership. 422 = already-member is fine; other errors
    # bubble so Svix retries and the JWT stays unconsumed for the next attempt.
    clerk_org_id = org_row.get('clerk_org_id')
    if clerk_org_id:
        try:
            from services.clerk_client import ClerkAPIError, get_client
            get_client().create_membership(clerk_org_id, clerk_user_id, 'basic_member')
        except ClerkAPIError as exc:
            if exc.status_code != 422:
                logger.error(
                    'create_membership failed for user %s org %s: %s',
                    clerk_user_id, clerk_org_id, exc,
                )
                raise
            logger.info(
                'Clerk reports user %s is already a member of org %s',
                clerk_user_id, clerk_org_id,
            )
    else:
        logger.warning(
            'Chesster org %s has no clerk_org_id; skipping Clerk membership call',
            claims['org_id'],
        )

    # 7) Record JWT consumption LAST. If steps 5/6 failed the row is not
    # written and the webhook can safely retry.
    supabase.table('invite_jwts_consumed').insert({
        'jti_hash': jti_hash,
        'organization_id': claims['org_id'],
        'branch_token_id': claims['branch_token_id'],
        'external_student_id': claims['student_id'],
        'clerk_user_id': clerk_user_id,
    }).execute()

    logger.info(
        'user.created linked user=%s student=%s org=%s',
        clerk_user_id, claims['student_id'], claims['org_id'],
    )


# =====================================================================
# Vercel webhook — domain events (custom-domain flow, PRD §4)
# =====================================================================
#
# Vercel signs webhook bodies with HMAC-SHA1 over the raw body using the
# project's webhook secret, and includes the unix timestamp in a separate
# header. We reject requests older than 5 minutes to prevent replay.

VERCEL_TIMESTAMP_TOLERANCE_SEC = 300


def verify_vercel_signature(payload: bytes, headers: dict) -> bool:
    """Verify a Vercel webhook signature.

    Vercel sends `x-vercel-signature` (HMAC-SHA1 hexdigest of the raw body
    using the project secret) and `x-vercel-signature-timestamp` (unix ms or
    seconds — we accept either by clamping the absolute delta).
    """
    if not VERCEL_WEBHOOK_SECRET:
        logger.warning('VERCEL_WEBHOOK_SECRET not set — refusing webhook')
        return False

    signature = headers.get('x-vercel-signature', '')
    ts_raw = headers.get('x-vercel-signature-timestamp', '')
    if not signature or not ts_raw:
        logger.error('Missing Vercel signature headers')
        return False

    try:
        ts = int(ts_raw)
    except ValueError:
        logger.error('Invalid Vercel timestamp')
        return False
    # Accept both seconds and milliseconds.
    now = time.time()
    if ts > 1e12:
        ts = ts / 1000.0
    if abs(now - ts) > VERCEL_TIMESTAMP_TOLERANCE_SEC:
        logger.error(f'Vercel webhook timestamp out of tolerance: dt={now - ts:.0f}s')
        return False

    expected = hmac.new(
        VERCEL_WEBHOOK_SECRET.encode(), payload, hashlib.sha1,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.error('Vercel signature verification failed')
        return False
    return True


@webhooks_bp.route('/vercel', methods=['POST'])
def vercel_webhook():
    """Receive Vercel domain-lifecycle events and sync to organizations."""
    payload = request.get_data()
    headers = {
        'x-vercel-signature': request.headers.get('x-vercel-signature', ''),
        'x-vercel-signature-timestamp': request.headers.get('x-vercel-signature-timestamp', ''),
    }
    if not verify_vercel_signature(payload, headers):
        return jsonify({'error': 'Invalid signature'}), 401

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON'}), 400

    event_type = event.get('type', '')
    payload_data = event.get('payload') or event.get('data') or {}
    domain = _extract_vercel_domain(payload_data)
    logger.info(f'Vercel webhook received: type={event_type} domain={domain}')

    try:
        if event_type in ('domain.created',):
            pass  # Already inserted via REST when admin added the domain.
        elif event_type in ('domain.verified', 'domain.cert.issued'):
            _vercel_set_status(domain, 'active', verified=True)
        elif event_type == 'domain.cert.failed':
            _vercel_set_status(domain, 'failed', verified=False, payload=payload_data)
        else:
            logger.info(f'Ignoring Vercel event type: {event_type}')
    except Exception as e:
        logger.error(f'Error handling Vercel webhook {event_type}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

    return jsonify({'status': 'ok'}), 200


def _extract_vercel_domain(payload_data: dict) -> str | None:
    """Vercel nests the domain under varied keys depending on event shape."""
    if not payload_data:
        return None
    if isinstance(payload_data, dict):
        # domain.* events use {"domain": {"name": "..."}} or {"name": "..."}
        domain_field = payload_data.get('domain')
        if isinstance(domain_field, dict):
            name = domain_field.get('name')
            if name:
                return str(name).strip().lower().rstrip('.')
        if isinstance(domain_field, str) and domain_field:
            return domain_field.strip().lower().rstrip('.')
        name = payload_data.get('name')
        if isinstance(name, str) and name:
            return name.strip().lower().rstrip('.')
    return None


def _vercel_set_status(domain: str | None, status: str, verified: bool,
                       payload: dict | None = None) -> None:
    """Update the org row matching this domain. Idempotent — re-emitting the
    same event for the same domain leaves the row in the same state."""
    if not domain:
        logger.warning('Vercel webhook missing domain name; skipping update')
        return

    supabase = _get_supabase()
    update: dict = {'custom_domain_status': status}
    if verified:
        from datetime import datetime, timezone
        update['custom_domain_verified_at'] = datetime.now(timezone.utc).isoformat()
    elif status == 'failed' and payload is not None:
        # Log the failure payload for ops triage; no schema column for it.
        logger.warning(f'Vercel domain.cert.failed for {domain}: {payload}')

    supabase.table('organizations').update(update).eq('custom_domain', domain).execute()
    logger.info(f'Vercel webhook applied: domain={domain} status={status}')

    # Notify director on terminal-state transitions (PRD §11.2 #2 — Phase 2).
    if status in ('active', 'failed'):
        try:
            from services.lifecycle_emails import notify_custom_domain_status
            notify_custom_domain_status(domain, status)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning('lifecycle email notify failed: %s', exc)
