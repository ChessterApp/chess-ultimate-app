"""
Branches service — multi-branch support (PRD §11.3 #2).

Schema: organizations → organization_branches (1:N), with
organization_members.branch_id linking a member to a branch (nullable —
org-wide admins and owner have no branch).

Roles:
  - owner       : full org, full branches
  - admin       : full org, full branches
  - teacher     : org-wide visibility (unchanged)
  - branch_admin: scoped to their own branch — cannot read/write rows in
                  sibling branches
  - student     : member, no admin rights

The RLS migration enforces scoping at the DB level. This service layer
provides the matching API surface and the helpers used by routes/admin.py
to scope its calls when the caller is a branch_admin.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ─── Role constants ──────────────────────────────────────────────────────────

ORG_WIDE_ADMIN_ROLES = ('owner', 'admin')
BRANCH_ADMIN_ROLE = 'branch_admin'
VALID_MEMBER_ROLES = (
    'owner', 'admin', 'teacher', 'student', BRANCH_ADMIN_ROLE,
)


_SLUG_RE = re.compile(r'^[a-z0-9]([a-z0-9-]{0,40}[a-z0-9])?$')


class BranchScopeError(Exception):
    """Raised when a caller is denied access to a branch row.

    `code` maps to the HTTP status used by the route handler:
      - ``not_in_branch_scope``  → 403 (caller is branch_admin elsewhere)
      - ``branch_not_found``     → 404
      - ``invalid_branch``       → 400
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


from utils.supabase_client import get_supabase as _get_supabase


# ─── CRUD ────────────────────────────────────────────────────────────────────

def list_branches(org_id: str) -> list[dict[str, Any]]:
    try:
        res = (
            _get_supabase()
            .table('organization_branches')
            .select('*')
            .eq('organization_id', org_id)
            .order('name')
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning('list_branches failed for org=%s: %s', org_id, exc)
        return []


def get_branch(branch_id: str) -> dict[str, Any] | None:
    try:
        res = (
            _get_supabase()
            .table('organization_branches')
            .select('*')
            .eq('id', branch_id)
            .single()
            .execute()
        )
        return res.data if getattr(res, 'data', None) else None
    except Exception as exc:
        logger.warning('get_branch failed for branch=%s: %s', branch_id, exc)
        return None


def create_branch(
    org_id: str,
    *,
    name: str,
    slug: str,
    address: str | None = None,
) -> dict[str, Any]:
    name = (name or '').strip()
    slug = (slug or '').strip().lower()
    if not name:
        raise BranchScopeError('invalid_branch', 'name is required')
    if not slug or not _SLUG_RE.match(slug):
        raise BranchScopeError('invalid_branch', 'invalid slug format')

    payload: dict[str, Any] = {
        'organization_id': org_id,
        'name': name,
        'slug': slug,
    }
    if address:
        payload['address'] = address.strip()

    res = (
        _get_supabase()
        .table('organization_branches')
        .insert(payload)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise BranchScopeError('invalid_branch', 'insert returned no row')
    return rows[0]


def update_branch(branch_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {'name', 'slug', 'address'}
    payload = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not payload:
        raise BranchScopeError('invalid_branch', 'no allowed fields supplied')
    if 'slug' in payload:
        s = str(payload['slug']).strip().lower()
        if not _SLUG_RE.match(s):
            raise BranchScopeError('invalid_branch', 'invalid slug format')
        payload['slug'] = s
    res = (
        _get_supabase()
        .table('organization_branches')
        .update(payload)
        .eq('id', branch_id)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def delete_branch(branch_id: str) -> bool:
    """Deleting a branch unsets ``branch_id`` on its members (ON DELETE SET NULL)."""
    (
        _get_supabase()
        .table('organization_branches')
        .delete()
        .eq('id', branch_id)
        .execute()
    )
    return True


# ─── Scoping helpers ─────────────────────────────────────────────────────────


def get_caller_branch_id(org_id: str, user_id: str) -> str | None:
    """Return the caller's `branch_id` membership row, if any."""
    try:
        res = (
            _get_supabase()
            .table('organization_members')
            .select('branch_id')
            .eq('organization_id', org_id)
            .eq('user_id', user_id)
            .single()
            .execute()
        )
        return (res.data or {}).get('branch_id')
    except Exception as exc:
        logger.warning('get_caller_branch_id failed: %s', exc)
        return None


def assert_branch_access(
    *,
    caller_role: str,
    caller_branch_id: str | None,
    target_branch_id: str | None,
) -> None:
    """Raise BranchScopeError if the caller can't touch a target row.

    Rules:
      - owner/admin: unrestricted (target may be None or any branch).
      - teacher: read-only via routes (not enforced here — routes guard
        teacher writes separately).
      - branch_admin: target_branch_id MUST equal caller_branch_id.
        Cross-branch access is denied.
    """
    if caller_role in ORG_WIDE_ADMIN_ROLES:
        return
    if caller_role == BRANCH_ADMIN_ROLE:
        if caller_branch_id is None:
            raise BranchScopeError(
                'not_in_branch_scope',
                'branch_admin without an assigned branch cannot act',
            )
        if target_branch_id != caller_branch_id:
            raise BranchScopeError(
                'not_in_branch_scope',
                'branch_admin cannot access rows outside their branch',
            )
        return
    # teacher / student / unknown — denied for admin actions
    raise BranchScopeError(
        'not_in_branch_scope',
        f'role {caller_role!r} cannot perform branch-scoped admin actions',
    )


def list_members_for_caller(
    org_id: str,
    *,
    caller_role: str,
    caller_branch_id: str | None,
) -> list[dict[str, Any]]:
    """Return members scoped to the caller's visibility.

    Branch admins see only their own branch. Org-wide admins see everything.
    """
    builder = (
        _get_supabase()
        .table('organization_members')
        .select('*')
        .eq('organization_id', org_id)
    )
    if caller_role == BRANCH_ADMIN_ROLE and caller_branch_id:
        builder = builder.eq('branch_id', caller_branch_id)
    elif caller_role == BRANCH_ADMIN_ROLE and not caller_branch_id:
        return []
    try:
        return builder.execute().data or []
    except Exception as exc:
        logger.warning('list_members_for_caller failed: %s', exc)
        return []


def get_member_branch_id(org_id: str, target_user_id: str) -> str | None:
    """Return the target row's branch_id (or None)."""
    try:
        res = (
            _get_supabase()
            .table('organization_members')
            .select('branch_id')
            .eq('organization_id', org_id)
            .eq('user_id', target_user_id)
            .single()
            .execute()
        )
        return (res.data or {}).get('branch_id')
    except Exception as exc:
        logger.warning('get_member_branch_id failed: %s', exc)
        return None
