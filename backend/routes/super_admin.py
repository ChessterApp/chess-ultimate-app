"""
Super-Admin API Blueprint (Phase 7A + 7B)

Endpoints — every successful call is appended to platform_admin_audit_log.

Phase 7A:
  - GET    /api/super-admin/me                        verify caller is super_admin
  - GET    /api/super-admin/audit                     read audit log

Phase 7B:
  - GET    /api/super-admin/users                     paginated user search
  - GET    /api/super-admin/users/<clerk_id>          full user detail
  - POST   /api/super-admin/users/<clerk_id>/suspend  suspend account
  - POST   /api/super-admin/users/<clerk_id>/unsuspend  reverse suspend
  - POST   /api/super-admin/users/<clerk_id>/refund   issue Whop refund
  - POST   /api/super-admin/users/<clerk_id>/impersonate    start read-only session
  - DELETE /api/super-admin/users/<clerk_id>/impersonate    end session

Read-only impersonation enforcement (belt-and-braces):
  - Super-admin endpoints reject mutation methods when the caller's request
    carries the impersonation cookie, except for the END-impersonate endpoint
    (which is the only way to clear the cookie).
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import Optional

import requests
from flask import Blueprint, jsonify, make_response, request

from utils.auth import (
    IMPERSONATION_COOKIE_NAME,
    IMPERSONATION_MAX_AGE_SECONDS,
    is_impersonating,
    require_super_admin,
)

logger = logging.getLogger(__name__)

super_admin_bp = Blueprint('super_admin', __name__, url_prefix='/api/super-admin')

CLERK_API_BASE = "https://api.clerk.com/v1"
WHOP_API_BASE = "https://api.whop.com/api/v5"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def _audit(action: str, target_type: str, target_id: str, payload: Optional[dict] = None) -> None:
    """Append a row to platform_admin_audit_log. Best-effort — never raises."""
    try:
        supabase = _get_supabase()
        supabase.table('platform_admin_audit_log').insert({
            'admin_clerk_id': getattr(request, 'user_id', 'unknown'),
            'action': action,
            'target_type': target_type,
            'target_id': target_id,
            'payload': payload or {},
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
        }).execute()
    except Exception as exc:
        logger.warning("Audit log insert failed for action=%s target=%s: %s",
                       action, target_id, exc)


def _block_if_impersonating():
    """Reject mutation methods when an impersonation cookie is present."""
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return None
    if is_impersonating(request):
        return jsonify({
            'error': 'Read-only impersonation: write actions are blocked',
            'reason': 'impersonation_active',
        }), 403
    return None


@super_admin_bp.before_request
def _super_admin_guard():
    block = _block_if_impersonating()
    if block is not None:
        # Allow END-impersonate routes through so admin can exit.
        if request.endpoint in (
            'super_admin.end_impersonation',
            'super_admin.end_active_impersonation',
        ):
            return None
        return block
    return None


def _whop_request(method: str, path: str, json_body: Optional[dict] = None) -> tuple[int, dict]:
    """Call Whop's REST API. Returns (status_code, json_body|{})."""
    api_key = os.environ.get('WHOP_API_KEY', '')
    if not api_key:
        return 503, {'error': 'Whop API not configured'}
    try:
        resp = requests.request(
            method,
            f"{WHOP_API_BASE}{path}",
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=json_body,
            timeout=10,
        )
        body = {}
        if resp.text:
            try:
                body = resp.json()
            except ValueError:
                body = {'raw': resp.text}
        return resp.status_code, body
    except requests.RequestException as exc:
        logger.exception("Whop request failed: %s %s", method, path)
        return 502, {'error': str(exc)}


def _clerk_request(method: str, path: str, json_body: Optional[dict] = None) -> tuple[int, dict]:
    """Call Clerk's REST API. Returns (status_code, json_body|{})."""
    secret = os.environ.get('CLERK_SECRET_KEY', '')
    if not secret:
        return 503, {'error': 'Clerk API not configured'}
    try:
        resp = requests.request(
            method,
            f"{CLERK_API_BASE}{path}",
            headers={
                'Authorization': f'Bearer {secret}',
                'Content-Type': 'application/json',
            },
            json=json_body,
            timeout=10,
        )
        body = {}
        if resp.text:
            try:
                body = resp.json()
            except ValueError:
                body = {'raw': resp.text}
        return resp.status_code, body
    except requests.RequestException as exc:
        logger.exception("Clerk request failed: %s %s", method, path)
        return 502, {'error': str(exc)}


# ─── 7A: identity + audit ───────────────────────────────────────────────────

@super_admin_bp.route('/me', methods=['GET'])
@require_super_admin
def me():
    """Return the calling super-admin's identity. Used by UI to confirm access."""
    user_record = getattr(request, 'clerk_user', None) or {}
    email = None
    primary_id = user_record.get('primary_email_address_id')
    for entry in user_record.get('email_addresses') or []:
        if entry.get('id') == primary_id:
            email = entry.get('email_address')
            break
    return jsonify({
        'clerk_id': request.user_id,
        'email': email,
        'name': ' '.join(filter(None, [user_record.get('first_name'), user_record.get('last_name')])) or None,
        'platform_role': 'super_admin',
    })


@super_admin_bp.route('/audit', methods=['GET'])
@require_super_admin
def list_audit():
    """Return audit log entries (most recent first)."""
    try:
        limit = min(int(request.args.get('limit', 100)), 500)
    except ValueError:
        limit = 100
    target_type = request.args.get('target_type')
    target_id = request.args.get('target_id')

    supabase = _get_supabase()
    query = supabase.table('platform_admin_audit_log').select('*')
    if target_type:
        query = query.eq('target_type', target_type)
    if target_id:
        query = query.eq('target_id', target_id)
    result = query.order('created_at', desc=True).limit(limit).execute()
    return jsonify({'entries': result.data or []})


# ─── 7B: users ──────────────────────────────────────────────────────────────

@super_admin_bp.route('/users', methods=['GET'])
@require_super_admin
def search_users():
    """Search users by email or name (fuzzy via pg_trgm) with optional filters."""
    q = (request.args.get('q') or '').strip()
    status_filter = request.args.get('status')
    plan_filter = request.args.get('plan')
    try:
        limit = min(int(request.args.get('limit', 50)), 200)
    except ValueError:
        limit = 50

    supabase = _get_supabase()
    query = supabase.table('platform_user_cache').select('*')
    if q:
        # Postgrest `or` clause — match on either email or name (case-insensitive substring).
        safe_q = q.replace(',', ' ').replace('(', ' ').replace(')', ' ')
        query = query.or_(f'email.ilike.%{safe_q}%,name.ilike.%{safe_q}%')
    if plan_filter:
        query = query.eq('subscription_status', plan_filter)
    result = query.order('signup_at', desc=True).limit(limit).execute()
    rows = result.data or []

    # Join with platform_user_status for live suspend state.
    if rows:
        ids = [r['clerk_id'] for r in rows]
        status_result = supabase.table('platform_user_status').select(
            'clerk_id, status, suspended_at, suspended_reason'
        ).in_('clerk_id', ids).execute()
        status_by_id = {r['clerk_id']: r for r in (status_result.data or [])}
        for row in rows:
            row['account_status'] = status_by_id.get(row['clerk_id'], {}).get('status', 'active')
            row['suspended_at'] = status_by_id.get(row['clerk_id'], {}).get('suspended_at')
            row['suspended_reason'] = status_by_id.get(row['clerk_id'], {}).get('suspended_reason')

    if status_filter:
        rows = [r for r in rows if r.get('account_status') == status_filter]

    return jsonify({'users': rows, 'count': len(rows), 'query': q})


@super_admin_bp.route('/users/<clerk_id>', methods=['GET'])
@require_super_admin
def get_user_detail(clerk_id: str):
    """Aggregate full user view from Clerk + Supabase."""
    supabase = _get_supabase()

    cache_row = (
        supabase.table('platform_user_cache').select('*').eq('clerk_id', clerk_id)
        .execute().data or [None]
    )[0]
    status_row = (
        supabase.table('platform_user_status').select('*').eq('clerk_id', clerk_id)
        .execute().data or [None]
    )[0]
    memberships = (
        supabase.table('organization_members').select('*').eq('user_id', clerk_id)
        .execute().data or []
    )

    # Recent audit entries for this user as target.
    recent_audit = (
        supabase.table('platform_admin_audit_log').select('*')
        .eq('target_type', 'user').eq('target_id', clerk_id)
        .order('created_at', desc=True).limit(20).execute().data or []
    )

    # Live Clerk profile (best-effort — never block).
    clerk_status, clerk_profile = _clerk_request('GET', f'/users/{clerk_id}')
    if clerk_status != 200:
        clerk_profile = None

    return jsonify({
        'clerk_id': clerk_id,
        'cache': cache_row,
        'status': status_row or {'status': 'active'},
        'memberships': memberships,
        'audit': recent_audit,
        'clerk': clerk_profile,
    })


@super_admin_bp.route('/users/<clerk_id>/suspend', methods=['POST'])
@require_super_admin
def suspend_user(clerk_id: str):
    body = request.get_json(silent=True) or {}
    reason = (body.get('reason') or '').strip()
    if not reason:
        return jsonify({'error': 'reason is required'}), 400

    supabase = _get_supabase()
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    supabase.table('platform_user_status').upsert({
        'clerk_id': clerk_id,
        'status': 'suspended',
        'suspended_reason': reason,
        'suspended_at': now_iso,
        'suspended_by': request.user_id,
    }, on_conflict='clerk_id').execute()

    # Best-effort: lock Clerk account so user cannot sign in.
    _clerk_request('POST', f'/users/{clerk_id}/lock')

    _audit('user.suspend', 'user', clerk_id, {'reason': reason})
    return jsonify({'status': 'suspended', 'clerk_id': clerk_id, 'reason': reason})


@super_admin_bp.route('/users/<clerk_id>/unsuspend', methods=['POST'])
@require_super_admin
def unsuspend_user(clerk_id: str):
    supabase = _get_supabase()
    supabase.table('platform_user_status').upsert({
        'clerk_id': clerk_id,
        'status': 'active',
        'suspended_reason': None,
        'suspended_at': None,
        'suspended_by': None,
    }, on_conflict='clerk_id').execute()

    _clerk_request('POST', f'/users/{clerk_id}/unlock')

    _audit('user.unsuspend', 'user', clerk_id)
    return jsonify({'status': 'active', 'clerk_id': clerk_id})


@super_admin_bp.route('/users/<clerk_id>/refund', methods=['POST'])
@require_super_admin
def refund_user(clerk_id: str):
    body = request.get_json(silent=True) or {}
    reason = (body.get('reason') or '').strip()
    amount_cents = body.get('amount_cents')
    membership_id = body.get('membership_id')
    if not reason:
        return jsonify({'error': 'reason is required'}), 400

    # Resolve Whop membership id if not supplied.
    if not membership_id:
        supabase = _get_supabase()
        cache = (
            supabase.table('platform_user_cache').select('whop_membership_id')
            .eq('clerk_id', clerk_id).execute().data or [None]
        )[0]
        membership_id = (cache or {}).get('whop_membership_id')

    if not membership_id:
        return jsonify({'error': 'No Whop membership on file for this user'}), 404

    payload = {'reason': reason}
    if amount_cents is not None:
        payload['amount'] = int(amount_cents)
    status, whop_body = _whop_request(
        'POST', f'/memberships/{membership_id}/refund', payload
    )

    success = 200 <= status < 300
    _audit('user.refund', 'user', clerk_id, {
        'reason': reason,
        'amount_cents': amount_cents,
        'membership_id': membership_id,
        'whop_status': status,
        'success': success,
    })

    if not success:
        return jsonify({
            'error': 'Refund failed at Whop',
            'whop_status': status,
            'whop_body': whop_body,
        }), 502

    return jsonify({
        'status': 'refunded',
        'clerk_id': clerk_id,
        'membership_id': membership_id,
        'amount_cents': amount_cents,
        'reason': reason,
        'whop': whop_body,
    })


@super_admin_bp.route('/users/<clerk_id>/impersonate', methods=['POST'])
@require_super_admin
def start_impersonation(clerk_id: str):
    body = request.get_json(silent=True) or {}
    reason = (body.get('reason') or 'support').strip()

    supabase = _get_supabase()
    inserted = supabase.table('impersonation_sessions').insert({
        'admin_clerk_id': request.user_id,
        'target_clerk_id': clerk_id,
        'reason': reason,
        'ip_address': request.remote_addr,
    }).execute()

    session_row = (inserted.data or [None])[0] or {}
    session_id = session_row.get('id')

    _audit('impersonate.start', 'user', clerk_id, {
        'reason': reason,
        'session_id': session_id,
    })

    response = make_response(jsonify({
        'status': 'started',
        'session_id': session_id,
        'target_clerk_id': clerk_id,
        'expires_in_seconds': IMPERSONATION_MAX_AGE_SECONDS,
    }))
    response.set_cookie(
        IMPERSONATION_COOKIE_NAME,
        value=str(session_id) if session_id else 'active',
        max_age=IMPERSONATION_MAX_AGE_SECONDS,
        httponly=False,            # frontend must read to render banner
        secure=request.is_secure,
        samesite='Lax',
        path='/',
    )
    return response


@super_admin_bp.route('/users/<clerk_id>/impersonate', methods=['DELETE'])
@require_super_admin
def end_impersonation(clerk_id: str):
    """End the impersonation session and clear the cookie."""
    return _end_impersonation_response(clerk_id)


@super_admin_bp.route('/impersonation', methods=['DELETE'])
@require_super_admin
def end_active_impersonation():
    """
    Convenience endpoint for the global ImpersonationBanner — ends whatever
    session the cookie identifies without requiring the caller to know the
    target clerk id.
    """
    cookie_session_id = request.cookies.get(IMPERSONATION_COOKIE_NAME)
    target_clerk_id = 'unknown'
    if cookie_session_id and cookie_session_id != 'active':
        try:
            supabase = _get_supabase()
            row = (
                supabase.table('impersonation_sessions').select('target_clerk_id')
                .eq('id', cookie_session_id).execute().data or [None]
            )[0]
            if row:
                target_clerk_id = row.get('target_clerk_id') or 'unknown'
        except Exception as exc:
            logger.warning("Failed to look up impersonation target: %s", exc)
    return _end_impersonation_response(target_clerk_id)


def _end_impersonation_response(target_clerk_id: str):
    cookie_session_id = request.cookies.get(IMPERSONATION_COOKIE_NAME)
    if cookie_session_id and cookie_session_id != 'active':
        try:
            supabase = _get_supabase()
            supabase.table('impersonation_sessions').update({
                'ended_at': _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }).eq('id', cookie_session_id).execute()
        except Exception as exc:
            logger.warning("Failed to mark impersonation session ended: %s", exc)

    _audit('impersonate.end', 'user', target_clerk_id, {'session_id': cookie_session_id})

    response = make_response(jsonify({'status': 'ended', 'clerk_id': target_clerk_id}))
    response.delete_cookie(IMPERSONATION_COOKIE_NAME, path='/')
    return response


# ─── 7C: organizations ──────────────────────────────────────────────────────

_ORG_LIST_COLUMNS = (
    'id, slug, name, status, created_at, '
    'custom_domain, custom_domain_status'
)


def _clerk_email_for(clerk_id: str) -> Optional[str]:
    """Best-effort Clerk email lookup. Returns None if Clerk is unreachable."""
    status, body = _clerk_request('GET', f'/users/{clerk_id}')
    if status != 200 or not isinstance(body, dict):
        return None
    primary_id = body.get('primary_email_address_id')
    for entry in body.get('email_addresses') or []:
        if entry.get('id') == primary_id:
            return entry.get('email_address')
    return None


@super_admin_bp.route('/organizations', methods=['GET'])
@require_super_admin
def list_organizations():
    """Search/list partner organizations with member + billing counts."""
    q = (request.args.get('q') or '').strip()
    status_filter = (request.args.get('status') or '').strip()
    try:
        limit = min(int(request.args.get('limit', 50)), 200)
    except ValueError:
        limit = 50
    try:
        offset = max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        offset = 0

    try:
        supabase = _get_supabase()
        query = supabase.table('organizations').select(_ORG_LIST_COLUMNS, count='exact')
        if status_filter in ('active', 'suspended', 'trial'):
            query = query.eq('status', status_filter)
        if q:
            safe_q = q.replace(',', ' ').replace('(', ' ').replace(')', ' ')
            query = query.or_(f'slug.ilike.%{safe_q}%,name.ilike.%{safe_q}%')
        result = (
            query.order('created_at', desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        rows = result.data or []
        total = getattr(result, 'count', None)
        if total is None:
            total = len(rows)

        org_ids = [r['id'] for r in rows if r.get('id')]

        # member_count per org
        member_counts: dict[str, int] = {}
        if org_ids:
            members_result = (
                supabase.table('organization_members')
                .select('organization_id')
                .in_('organization_id', org_ids)
                .execute()
            )
            for m in (members_result.data or []):
                oid = m.get('organization_id')
                if oid:
                    member_counts[oid] = member_counts.get(oid, 0) + 1

        # billing rows per org
        billing_by_org: dict[str, dict] = {}
        if org_ids:
            billing_result = (
                supabase.table('organization_billing')
                .select('organization_id, plan, student_count')
                .in_('organization_id', org_ids)
                .execute()
            )
            for b in (billing_result.data or []):
                oid = b.get('organization_id')
                if oid:
                    billing_by_org[oid] = b

        items = []
        for row in rows:
            oid = row.get('id')
            billing = billing_by_org.get(oid, {}) if oid else {}
            items.append({
                'id': oid,
                'slug': row.get('slug'),
                'name': row.get('name'),
                'status': row.get('status'),
                'plan': billing.get('plan'),
                'member_count': member_counts.get(oid, 0),
                'student_count': billing.get('student_count'),
                'custom_domain': row.get('custom_domain'),
                'custom_domain_status': row.get('custom_domain_status'),
                'created_at': row.get('created_at'),
            })

        return jsonify({'items': items, 'total': total})
    except Exception as exc:
        logger.exception("list_organizations failed: %s", exc)
        return jsonify({'error': 'Failed to list organizations'}), 500


@super_admin_bp.route('/organizations/<org_id>', methods=['GET'])
@require_super_admin
def get_organization_detail(org_id: str):
    """Full detail for one org: row + billing + members (+ best-effort emails) + audit."""
    try:
        supabase = _get_supabase()
        org_rows = (
            supabase.table('organizations').select('*').eq('id', org_id)
            .execute().data or []
        )
        if not org_rows:
            return jsonify({'error': 'Organization not found'}), 404
        org = org_rows[0]

        billing = (
            supabase.table('organization_billing').select('*')
            .eq('organization_id', org_id).execute().data or [None]
        )[0]

        members = (
            supabase.table('organization_members').select('*')
            .eq('organization_id', org_id).order('joined_at', desc=True)
            .execute().data or []
        )

        # Best-effort Clerk email lookup per member.
        for m in members:
            user_id = m.get('user_id')
            if user_id:
                try:
                    m['email'] = _clerk_email_for(user_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Clerk email lookup failed for %s: %s", user_id, exc)
                    m['email'] = None
            else:
                m['email'] = None

        audit = (
            supabase.table('platform_admin_audit_log').select('*')
            .eq('target_type', 'organization').eq('target_id', org_id)
            .order('created_at', desc=True).limit(50)
            .execute().data or []
        )

        return jsonify({
            'organization': org,
            'billing': billing,
            'members': members,
            'audit': audit,
        })
    except Exception as exc:
        logger.exception("get_organization_detail failed: %s", exc)
        return jsonify({'error': 'Failed to load organization'}), 500


def _require_reason(body: Optional[dict]) -> tuple[Optional[str], Optional[tuple]]:
    """Extract a ≥3-char reason from the body. Returns (reason, error_response)."""
    reason = ((body or {}).get('reason') or '').strip()
    if len(reason) < 3:
        return None, (jsonify({'error': 'reason is required (min 3 chars)'}), 400)
    return reason, None


def _set_org_status(org_id: str, new_status: str, action: str, reason: str):
    """Shared implementation for suspend/unsuspend. Idempotent."""
    try:
        supabase = _get_supabase()
        existing = (
            supabase.table('organizations').select('id, status').eq('id', org_id)
            .execute().data or []
        )
        if not existing:
            return jsonify({'error': 'Organization not found'}), 404
        prior_status = existing[0].get('status')

        if prior_status != new_status:
            supabase.table('organizations').update({
                'status': new_status,
            }).eq('id', org_id).execute()

        _audit(action, 'organization', org_id, {
            'reason': reason,
            'prior_status': prior_status,
        })
        return jsonify({
            'status': new_status,
            'organization_id': org_id,
            'prior_status': prior_status,
            'idempotent': prior_status == new_status,
        })
    except Exception as exc:
        logger.exception("%s failed: %s", action, exc)
        return jsonify({'error': f'Failed to {action}'}), 500


@super_admin_bp.route('/organizations/<org_id>/suspend', methods=['POST'])
@require_super_admin
def suspend_organization(org_id: str):
    reason, err = _require_reason(request.get_json(silent=True))
    if err is not None:
        return err
    return _set_org_status(org_id, 'suspended', 'suspend_org', reason)


@super_admin_bp.route('/organizations/<org_id>/unsuspend', methods=['POST'])
@require_super_admin
def unsuspend_organization(org_id: str):
    reason, err = _require_reason(request.get_json(silent=True))
    if err is not None:
        return err
    return _set_org_status(org_id, 'active', 'unsuspend_org', reason)


@super_admin_bp.route('/organizations/<org_id>/promote', methods=['POST'])
@require_super_admin
def promote_organization_member(org_id: str):
    body = request.get_json(silent=True) or {}
    reason, err = _require_reason(body)
    if err is not None:
        return err
    user_id = (body.get('user_id') or '').strip()
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400

    try:
        supabase = _get_supabase()
        members = (
            supabase.table('organization_members').select('id, role')
            .eq('organization_id', org_id).eq('user_id', user_id)
            .execute().data or []
        )
        if not members:
            return jsonify({
                'error': 'User is not a member of this organization',
            }), 400
        prior_role = members[0].get('role')

        if prior_role != 'owner':
            supabase.table('organization_members').update({
                'role': 'owner',
            }).eq('organization_id', org_id).eq('user_id', user_id).execute()

        _audit('promote_org_member', 'organization', org_id, {
            'user_id': user_id,
            'prior_role': prior_role,
            'reason': reason,
        })
        return jsonify({
            'organization_id': org_id,
            'user_id': user_id,
            'role': 'owner',
            'prior_role': prior_role,
        })
    except Exception as exc:
        logger.exception("promote_organization_member failed: %s", exc)
        return jsonify({'error': 'Failed to promote member'}), 500
