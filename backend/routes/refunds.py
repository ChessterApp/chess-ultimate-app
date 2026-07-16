"""
Refunds API — owner-facing list endpoint + internal webhook trampoline.

Endpoints:
  GET  /api/admin/organizations/<org_id>/refunds    — list refunds (owner)
  POST /api/webhooks/whop-refund                    — process a refund event

The Whop webhook entry point is in the Next.js layer
(`frontend/src/app/api/whop/webhook/route.ts`) — it verifies the HMAC
signature, then can either:
  (a) write the refund directly via supabase-admin (it already does this
      for `subscription.updated`), OR
  (b) POST the verified payload to this backend route, which calls
      `services.refunds.process_refund_event()`.

The backend route is also useful for replay/manual reprocessing during
support incidents.
"""

from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify, request

from services import refunds as refunds_svc

logger = logging.getLogger(__name__)

refunds_bp = Blueprint('refunds', __name__)


from utils.supabase_client import get_supabase as _get_supabase


@refunds_bp.route(
    '/api/admin/organizations/<org_id>/refunds', methods=['GET'],
)
def list_refunds(org_id: str):
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401

    supabase = _get_supabase()
    try:
        role_res = (
            supabase.table('organization_members')
            .select('role')
            .eq('organization_id', org_id)
            .eq('user_id', user_id)
            .single()
            .execute()
        )
        role = (role_res.data or {}).get('role') if getattr(role_res, 'data', None) else None
    except Exception:
        role = None
    # PRD §3 — billing is owner-only by RLS; mirror at API.
    if role != 'owner':
        return jsonify({'error': 'Forbidden'}), 403

    refunds = refunds_svc.list_refunds_for_org(org_id)
    return jsonify({'refunds': refunds})


@refunds_bp.route('/api/webhooks/whop-refund', methods=['POST'])
def whop_refund_webhook():
    """Internal trampoline — see services.refunds docstring.

    Auth: requires a shared-secret bearer token (``WHOP_REFUND_INTERNAL_SECRET``).
    Production sets this on the Next.js side before forwarding.
    """
    expected_secret = os.getenv('WHOP_REFUND_INTERNAL_SECRET')
    if expected_secret:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer ') or auth.split(' ', 1)[1] != expected_secret:
            return jsonify({'error': 'unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({'error': 'invalid_payload'}), 400

    # Only handle refund events
    event_name = payload.get('action') or payload.get('event') or ''
    if not refunds_svc.is_refund_event(event_name):
        return jsonify({'status': 'ignored', 'event': event_name}), 200

    try:
        result = refunds_svc.process_refund_event(payload)
    except Exception as exc:
        logger.exception('process_refund_event failed: %s', exc)
        return jsonify({'error': 'processing_failed'}), 500

    return jsonify(result), 200
