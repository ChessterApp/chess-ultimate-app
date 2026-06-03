"""
Branches API — multi-branch CRUD + branch-admin scoping (PRD §11.3 #2).

Routes:
  GET    /api/admin/organizations/<org_id>/branches
  POST   /api/admin/organizations/<org_id>/branches
  PATCH  /api/admin/organizations/<org_id>/branches/<branch_id>
  DELETE /api/admin/organizations/<org_id>/branches/<branch_id>
  POST   /api/admin/organizations/<org_id>/branches/<branch_id>/members
         — assign a member to a branch (or unassign by setting branch_id=null)
"""

from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request

from services import branches as branches_svc

logger = logging.getLogger(__name__)

branches_bp = Blueprint('branches', __name__, url_prefix='/api/admin')


def _get_supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def _get_caller_role(org_id: str, user_id: str) -> str | None:
    supabase = _get_supabase()
    res = (
        supabase.table('organization_members')
        .select('role')
        .eq('organization_id', org_id)
        .eq('user_id', user_id)
        .single()
        .execute()
    )
    return (res.data or {}).get('role') if getattr(res, 'data', None) else None


def _require_org_admin(org_id: str):
    """Only owner/admin can write to branch metadata."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401, None
    role = _get_caller_role(org_id, user_id)
    if role not in branches_svc.ORG_WIDE_ADMIN_ROLES:
        return jsonify({'error': 'Forbidden'}), 403, None
    return None, None, user_id


@branches_bp.route('/organizations/<org_id>/branches', methods=['GET'])
def list_org_branches(org_id: str):
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    role = _get_caller_role(org_id, user_id)
    if not role:
        return jsonify({'error': 'Forbidden'}), 403
    # Branch admin sees only their own branch entry; org-wide roles see all.
    branches = branches_svc.list_branches(org_id)
    if role == branches_svc.BRANCH_ADMIN_ROLE:
        caller_branch = branches_svc.get_caller_branch_id(org_id, user_id)
        branches = [b for b in branches if b.get('id') == caller_branch]
    return jsonify({'branches': branches})


@branches_bp.route('/organizations/<org_id>/branches', methods=['POST'])
def create_org_branch(org_id: str):
    err, status, _ = _require_org_admin(org_id)
    if err is not None:
        return err, status
    data = request.get_json(silent=True) or {}
    try:
        branch = branches_svc.create_branch(
            org_id,
            name=data.get('name', ''),
            slug=data.get('slug', ''),
            address=data.get('address'),
        )
    except branches_svc.BranchScopeError as exc:
        return jsonify({'error': exc.code, 'message': exc.message}), 400
    except Exception as exc:
        logger.exception('create_org_branch failed: %s', exc)
        return jsonify({'error': 'create_failed'}), 500
    return jsonify({'branch': branch}), 201


@branches_bp.route(
    '/organizations/<org_id>/branches/<branch_id>', methods=['PATCH'],
)
def update_org_branch(org_id: str, branch_id: str):
    err, status, _ = _require_org_admin(org_id)
    if err is not None:
        return err, status
    target = branches_svc.get_branch(branch_id)
    if not target or target.get('organization_id') != org_id:
        return jsonify({'error': 'branch_not_found'}), 404
    data = request.get_json(silent=True) or {}
    try:
        updated = branches_svc.update_branch(branch_id, **data)
    except branches_svc.BranchScopeError as exc:
        return jsonify({'error': exc.code, 'message': exc.message}), 400
    return jsonify({'branch': updated}), 200


@branches_bp.route(
    '/organizations/<org_id>/branches/<branch_id>', methods=['DELETE'],
)
def delete_org_branch(org_id: str, branch_id: str):
    err, status, _ = _require_org_admin(org_id)
    if err is not None:
        return err, status
    target = branches_svc.get_branch(branch_id)
    if not target or target.get('organization_id') != org_id:
        return jsonify({'error': 'branch_not_found'}), 404
    branches_svc.delete_branch(branch_id)
    return jsonify({'status': 'deleted'}), 200


@branches_bp.route(
    '/organizations/<org_id>/branches/<branch_id>/members',
    methods=['POST'],
)
def assign_member_to_branch(org_id: str, branch_id: str):
    """Move a member into the given branch.

    Body: { user_id: str }.

    Org admins can move any member; branch admins can only re-assign within
    their own branch (no-op effectively, but allowed for symmetry).
    """
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    role = _get_caller_role(org_id, user_id)
    if role not in (*branches_svc.ORG_WIDE_ADMIN_ROLES, branches_svc.BRANCH_ADMIN_ROLE):
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json(silent=True) or {}
    target_user_id = data.get('user_id')
    if not target_user_id:
        return jsonify({'error': 'user_id required'}), 400

    target = branches_svc.get_branch(branch_id)
    if not target or target.get('organization_id') != org_id:
        return jsonify({'error': 'branch_not_found'}), 404

    if role == branches_svc.BRANCH_ADMIN_ROLE:
        caller_branch = branches_svc.get_caller_branch_id(org_id, user_id)
        if caller_branch != branch_id:
            return jsonify({'error': 'not_in_branch_scope'}), 403

    _get_supabase().table('organization_members').update(
        {'branch_id': branch_id},
    ).eq('organization_id', org_id).eq('user_id', target_user_id).execute()

    return jsonify({'status': 'assigned', 'branch_id': branch_id}), 200
