"""
Ownership-transfer HTTP routes (PRD §11.3 #3).

Routes:
  POST   /api/admin/organizations/<org_id>/ownership-transfers           — create
  GET    /api/admin/organizations/<org_id>/ownership-transfers           — list
  POST   /api/admin/organizations/<org_id>/ownership-transfers/<id>/revoke
  POST   /api/admin/organizations/<org_id>/ownership-transfers/<id>/confirm
  GET    /api/ownership-transfers/by-token/<token>                       — accept page lookup
  POST   /api/ownership-transfers/by-token/<token>/accept                — invitee accepts

The first four require an owner role. The last two are public (the token
is the auth signal).
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from services import ownership_transfer as svc

logger = logging.getLogger(__name__)

ownership_transfer_bp = Blueprint('ownership_transfer', __name__)


def _get_supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def _require_owner(org_id: str):
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401, None
    res = (
        _get_supabase()
        .table('organization_members')
        .select('role')
        .eq('organization_id', org_id)
        .eq('user_id', user_id)
        .single()
        .execute()
    )
    role = (res.data or {}).get('role') if getattr(res, 'data', None) else None
    if role != 'owner':
        return jsonify({'error': 'Forbidden'}), 403, None
    return None, None, user_id


def _map_error(exc: svc.OwnershipTransferError):
    code = exc.code
    status = {
        'not_found': 404,
        'forbidden': 403,
        'expired': 410,
        'invalid_state': 409,
        'invalid_input': 400,
    }.get(code, 400)
    return jsonify({'error': code, 'message': exc.message}), status


@ownership_transfer_bp.route(
    '/api/admin/organizations/<org_id>/ownership-transfers',
    methods=['POST'],
)
def create_transfer(org_id: str):
    err, status, user_id = _require_owner(org_id)
    if err is not None:
        return err, status
    data = request.get_json(silent=True) or {}
    invitee_email = (data.get('invitee_email') or '').strip()
    if not invitee_email:
        return jsonify({'error': 'invalid_input', 'message': 'invitee_email required'}), 400
    try:
        row = svc.create_transfer(
            org_id, user_id, invitee_email,
            ttl_hours=int(data.get('ttl_hours', 72)),
        )
    except svc.OwnershipTransferError as exc:
        return _map_error(exc)
    except Exception as exc:
        logger.exception('create_transfer failed: %s', exc)
        return jsonify({'error': 'internal'}), 500

    # Best-effort email (silent on failure — token is queryable via the list endpoint)
    try:
        _send_invite_email(row)
    except Exception as exc:  # pragma: no cover
        logger.warning('ownership invite email failed: %s', exc)

    return jsonify({'transfer': row}), 201


@ownership_transfer_bp.route(
    '/api/admin/organizations/<org_id>/ownership-transfers',
    methods=['GET'],
)
def list_transfers(org_id: str):
    err, status, _ = _require_owner(org_id)
    if err is not None:
        return err, status
    return jsonify({'transfers': svc.list_for_org(org_id)})


@ownership_transfer_bp.route(
    '/api/admin/organizations/<org_id>/ownership-transfers/<transfer_id>/revoke',
    methods=['POST'],
)
def revoke(org_id: str, transfer_id: str):
    err, status, user_id = _require_owner(org_id)
    if err is not None:
        return err, status
    try:
        row = svc.revoke_transfer(transfer_id, user_id)
    except svc.OwnershipTransferError as exc:
        return _map_error(exc)
    return jsonify({'transfer': row}), 200


@ownership_transfer_bp.route(
    '/api/admin/organizations/<org_id>/ownership-transfers/<transfer_id>/confirm',
    methods=['POST'],
)
def confirm(org_id: str, transfer_id: str):
    err, status, user_id = _require_owner(org_id)
    if err is not None:
        return err, status
    try:
        row = svc.confirm_transfer(transfer_id, user_id)
    except svc.OwnershipTransferError as exc:
        return _map_error(exc)
    return jsonify({'transfer': row}), 200


# ─── Public token endpoints ─────────────────────────────────────────────────


@ownership_transfer_bp.route(
    '/api/ownership-transfers/by-token/<token>', methods=['GET'],
)
def lookup_by_token(token: str):
    row = svc.get_by_token(token)
    if not row:
        return jsonify({'error': 'not_found'}), 404
    # Hide the internal id from the public surface
    return jsonify({
        'transfer': {
            'organization_id': row['organization_id'],
            'invitee_email': row['invitee_email'],
            'state': row['state'],
            'expires_at': row['expires_at'],
        },
    })


@ownership_transfer_bp.route(
    '/api/ownership-transfers/by-token/<token>/accept', methods=['POST'],
)
def accept_via_token(token: str):
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    try:
        row = svc.accept_transfer(token, user_id)
    except svc.OwnershipTransferError as exc:
        return _map_error(exc)
    return jsonify({'transfer': row}), 200


# ─── Helpers ────────────────────────────────────────────────────────────────


def _send_invite_email(row: dict) -> None:
    """Send the ownership-transfer invite via Resend (best-effort)."""
    import os
    import json
    import urllib.error
    import urllib.request

    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        logger.info('RESEND_API_KEY missing — skipping ownership invite email')
        return

    base = os.getenv('PUBLIC_APP_URL', 'https://chesster.io').rstrip('/')
    link = f'{base}/admin/settings/team/accept-transfer?token={row["token"]}'

    subject = 'Ownership of your chess school'
    text = (
        f'You have been invited to take over ownership of a Chesster school.\n\n'
        f'Click to accept (valid until {row.get("expires_at")}):\n{link}\n\n'
        f'If you did not expect this, ignore this email — the link expires automatically.\n'
    )
    body = {
        'from': os.getenv('RESEND_OPS_FROM', 'ops@chesster.io'),
        'to': [row['invitee_email']],
        'subject': subject,
        'text': text,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    req = urllib.request.Request(
        'https://api.resend.com/emails',
        data=json.dumps(body).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        logger.warning('ownership invite email HTTP error: %s', exc)
