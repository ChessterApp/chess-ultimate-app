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
