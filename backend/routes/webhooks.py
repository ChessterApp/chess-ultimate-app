"""
Clerk Organizations Webhook Handler

Syncs Clerk organization events to Supabase:
  - organization.created
  - organization.updated
  - organization.deleted
  - organizationMembership.created
  - organizationMembership.updated
  - organizationMembership.deleted

Webhook signing: Clerk signs webhooks with Svix. We verify using the
CLERK_WEBHOOK_SECRET environment variable.
"""

import hashlib
import hmac
import json
import logging
import os
import time

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/api/webhooks')

CLERK_WEBHOOK_SECRET = os.getenv('CLERK_WEBHOOK_SECRET', '')
VERCEL_WEBHOOK_SECRET = os.getenv('VERCEL_WEBHOOK_SECRET', '')


def _get_supabase():
    """Lazy import to avoid circular imports at module level."""
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


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
        else:
            logger.info(f'Ignoring unhandled event type: {event_type}')
    except Exception as e:
        logger.error(f'Error handling webhook {event_type}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

    return jsonify({'status': 'ok'}), 200


def _handle_org_created(data: dict):
    """Sync new Clerk organization to Supabase."""
    supabase = _get_supabase()
    slug = data.get('slug', '')
    name = data.get('name', '')
    logo_url = data.get('image_url')

    if not slug or not name:
        logger.error(f'Missing slug or name in org.created: {data}')
        return

    supabase.table('organizations').upsert({
        'slug': slug,
        'name': name,
        'logo_url': logo_url,
        'status': 'active',
    }, on_conflict='slug').execute()

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
    """Sync new Clerk org membership to Supabase."""
    supabase = _get_supabase()

    org_data = data.get('organization', {})
    user_data = data.get('public_user_data', {})
    slug = org_data.get('slug', '')
    user_id = user_data.get('user_id', data.get('public_user_data', {}).get('user_id', ''))
    role = _map_clerk_role(data.get('role', 'basic_member'))

    if not slug or not user_id:
        logger.error(f'Missing slug or user_id in membership.created: {data}')
        return

    # Lookup org ID by slug
    org_result = supabase.table('organizations').select('id').eq('slug', slug).single().execute()
    if not org_result.data:
        logger.error(f'Organization not found for slug: {slug}')
        return

    org_id = org_result.data['id']

    supabase.table('organization_members').upsert({
        'organization_id': org_id,
        'user_id': user_id,
        'role': role,
    }, on_conflict='organization_id,user_id').execute()

    logger.info(f'Member added: user={user_id} org={slug} role={role}')


def _handle_member_updated(data: dict):
    """Sync Clerk org membership role changes to Supabase."""
    supabase = _get_supabase()

    org_data = data.get('organization', {})
    user_data = data.get('public_user_data', {})
    slug = org_data.get('slug', '')
    user_id = user_data.get('user_id', '')
    role = _map_clerk_role(data.get('role', 'basic_member'))

    if not slug or not user_id:
        logger.error(f'Missing slug or user_id in membership.updated: {data}')
        return

    org_result = supabase.table('organizations').select('id').eq('slug', slug).single().execute()
    if not org_result.data:
        logger.error(f'Organization not found for slug: {slug}')
        return

    org_id = org_result.data['id']

    supabase.table('organization_members').update({
        'role': role,
    }).eq('organization_id', org_id).eq('user_id', user_id).execute()

    logger.info(f'Member updated: user={user_id} org={slug} role={role}')


def _handle_member_deleted(data: dict):
    """Remove Clerk org membership from Supabase."""
    supabase = _get_supabase()

    org_data = data.get('organization', {})
    user_data = data.get('public_user_data', {})
    slug = org_data.get('slug', '')
    user_id = user_data.get('user_id', '')

    if not slug or not user_id:
        logger.error(f'Missing slug or user_id in membership.deleted: {data}')
        return

    org_result = supabase.table('organizations').select('id').eq('slug', slug).single().execute()
    if not org_result.data:
        logger.error(f'Organization not found for slug: {slug}')
        return

    org_id = org_result.data['id']

    supabase.table('organization_members').delete().eq(
        'organization_id', org_id
    ).eq('user_id', user_id).execute()

    logger.info(f'Member removed: user={user_id} org={slug}')


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
