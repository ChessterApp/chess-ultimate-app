"""
Admin API Blueprint

Endpoints for organization management:
  - GET /api/admin/organizations/by-slug/:slug
  - GET /api/admin/organizations/:id/members
  - POST /api/admin/organizations/:id/members/invite
  - DELETE /api/admin/organizations/:id/members/:userId
  - PUT /api/admin/organizations/:id/settings
  - GET /api/admin/organizations/:id/content
  - PUT /api/admin/organizations/:id/content
  - GET /api/admin/organizations/:id/stats
"""

import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

ADMIN_ROLES = ('owner', 'admin', 'teacher')


def _get_supabase():
    """Lazy import to avoid circular imports."""
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def _get_caller_role(org_id: str, user_id: str) -> str | None:
    """Get the caller's role in the given organization. Returns None if not a member."""
    supabase = _get_supabase()
    result = supabase.table('organization_members').select('role').eq(
        'organization_id', org_id
    ).eq('user_id', user_id).single().execute()
    return result.data.get('role') if result.data else None


def _require_admin(org_id: str) -> tuple | None:
    """Check that X-User-Id header has admin-level access. Returns error tuple or None."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401

    role = _get_caller_role(org_id, user_id)
    if not role or role not in ADMIN_ROLES:
        return jsonify({'error': 'Forbidden'}), 403

    return None


# --- Organization lookup ---

@admin_bp.route('/organizations/by-slug/<slug>', methods=['GET'])
def get_org_by_slug(slug: str):
    """Get organization details by subdomain slug."""
    supabase = _get_supabase()
    result = supabase.table('organizations').select('*').eq('slug', slug).eq('status', 'active').single().execute()
    if not result.data:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(result.data)


# --- Members ---

@admin_bp.route('/organizations/<org_id>/members', methods=['GET'])
def get_org_members(org_id: str):
    """List all members of an organization."""
    # Allow user_id filter for role checks (no admin guard for this case)
    user_id_filter = request.args.get('user_id')
    if user_id_filter:
        # Simple role lookup — no admin check needed (used by layout guard)
        supabase = _get_supabase()
        result = supabase.table('organization_members').select('*').eq(
            'organization_id', org_id
        ).execute()
        return jsonify({'members': result.data or []})

    error = _require_admin(org_id)
    if error:
        return error

    supabase = _get_supabase()
    result = supabase.table('organization_members').select('*').eq(
        'organization_id', org_id
    ).order('joined_at', desc=False).execute()
    return jsonify({'members': result.data or []})


@admin_bp.route('/organizations/<org_id>/members/invite', methods=['POST'])
def invite_member(org_id: str):
    """Invite a new member by email."""
    error = _require_admin(org_id)
    if error:
        return error

    data = request.get_json()
    email = data.get('email')
    role = data.get('role', 'student')

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    if role not in ('student', 'teacher', 'admin'):
        return jsonify({'error': 'Invalid role'}), 400

    user_id = request.headers.get('X-User-Id')

    # Store invite in organization_members with a placeholder user_id
    # In production, this would trigger an email invitation via Clerk
    supabase = _get_supabase()
    invite_user_id = f'invite:{email}'

    supabase.table('organization_members').upsert({
        'organization_id': org_id,
        'user_id': invite_user_id,
        'role': role,
        'invited_by': user_id,
    }, on_conflict='organization_id,user_id').execute()

    logger.info(f'Member invited: email={email} org={org_id} role={role} by={user_id}')
    return jsonify({'status': 'invited', 'email': email}), 201


@admin_bp.route('/organizations/<org_id>/members/<target_user_id>', methods=['DELETE'])
def remove_member(org_id: str, target_user_id: str):
    """Remove a member from the organization."""
    error = _require_admin(org_id)
    if error:
        return error

    # Prevent removing the owner
    supabase = _get_supabase()
    target = supabase.table('organization_members').select('role').eq(
        'organization_id', org_id
    ).eq('user_id', target_user_id).single().execute()

    if target.data and target.data.get('role') == 'owner':
        return jsonify({'error': 'Cannot remove the owner'}), 403

    supabase.table('organization_members').delete().eq(
        'organization_id', org_id
    ).eq('user_id', target_user_id).execute()

    logger.info(f'Member removed: user={target_user_id} org={org_id}')
    return jsonify({'status': 'removed'})


# --- Settings ---

@admin_bp.route('/organizations/<org_id>/settings', methods=['PUT'])
def update_settings(org_id: str):
    """Update organization branding/settings."""
    error = _require_admin(org_id)
    if error:
        return error

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Only allow updating specific branding fields
    allowed_fields = {
        'logo_url', 'favicon_url', 'primary_color', 'secondary_color',
        'accent_color', 'landing_page_config', 'custom_css', 'contact_email',
    }
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        return jsonify({'error': 'No valid fields to update'}), 400

    supabase = _get_supabase()
    supabase.table('organizations').update(update_data).eq('id', org_id).execute()

    logger.info(f'Organization settings updated: org={org_id} fields={list(update_data.keys())}')
    return jsonify({'status': 'updated'})


# --- Content (Courses) ---

@admin_bp.route('/organizations/<org_id>/content', methods=['GET'])
def get_org_content(org_id: str):
    """Get curated course list for the organization."""
    error = _require_admin(org_id)
    if error:
        return error

    supabase = _get_supabase()

    # Get org content entries joined with course titles
    result = supabase.table('organization_content').select(
        'id, course_id, visible, order_index'
    ).eq('organization_id', org_id).order('order_index').execute()

    courses = []
    for item in (result.data or []):
        # Fetch course title
        course = supabase.table('courses').select('title').eq(
            'id', item['course_id']
        ).single().execute()
        courses.append({
            'id': item['id'],
            'course_id': item['course_id'],
            'title': course.data.get('title', 'Unknown') if course.data else 'Unknown',
            'visible': item['visible'],
            'order_index': item['order_index'],
        })

    return jsonify({'courses': courses})


@admin_bp.route('/organizations/<org_id>/content', methods=['PUT'])
def update_org_content(org_id: str):
    """Update course visibility and ordering."""
    error = _require_admin(org_id)
    if error:
        return error

    data = request.get_json()
    courses = data.get('courses', [])

    supabase = _get_supabase()

    for course in courses:
        course_id = course.get('course_id')
        if not course_id:
            continue
        supabase.table('organization_content').upsert({
            'organization_id': org_id,
            'course_id': course_id,
            'visible': course.get('visible', True),
            'order_index': course.get('order_index', 0),
        }, on_conflict='organization_id,course_id').execute()

    logger.info(f'Organization content updated: org={org_id} courses={len(courses)}')
    return jsonify({'status': 'updated'})


# --- Stats ---

@admin_bp.route('/organizations/<org_id>/stats', methods=['GET'])
def get_org_stats(org_id: str):
    """Get overview stats for the admin dashboard."""
    supabase = _get_supabase()

    # Student count
    members_result = supabase.table('organization_members').select(
        'id', count='exact'
    ).eq('organization_id', org_id).eq('role', 'student').execute()
    student_count = members_result.count or 0

    # Active this week (members with progress in last 7 days)
    # Simplified: count unique user_ids in user_progress for this org in last 7 days
    from datetime import datetime, timedelta, timezone
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    try:
        progress_result = supabase.table('user_progress').select(
            'user_id'
        ).eq('organization_id', org_id).gte('updated_at', week_ago).execute()
        active_users = set()
        for row in (progress_result.data or []):
            active_users.add(row['user_id'])
        active_this_week = len(active_users)
    except Exception:
        active_this_week = 0

    # Course completion rate
    try:
        completed = supabase.table('user_progress').select(
            'id', count='exact'
        ).eq('organization_id', org_id).eq('status', 'completed').execute()
        total = supabase.table('user_progress').select(
            'id', count='exact'
        ).eq('organization_id', org_id).execute()
        if total.count and total.count > 0:
            course_completion_rate = round((completed.count or 0) / total.count * 100)
        else:
            course_completion_rate = 0
    except Exception:
        course_completion_rate = 0

    return jsonify({
        'student_count': student_count,
        'active_this_week': active_this_week,
        'course_completion_rate': course_completion_rate,
    })
