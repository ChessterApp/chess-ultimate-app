"""
Admin API Blueprint

Endpoints for organization management:
  - GET /api/admin/organizations/by-slug/:slug
  - GET /api/admin/organizations/by-custom-domain/:host
  - GET /api/admin/organizations/:id/members
  - POST /api/admin/organizations/:id/members/invite
  - DELETE /api/admin/organizations/:id/members/:userId
  - PUT /api/admin/organizations/:id/settings
  - POST /api/admin/organizations/:id/branding/upload
  - GET /api/admin/organizations/:id/content
  - PUT /api/admin/organizations/:id/content
  - GET /api/admin/organizations/:id/stats
  - POST/GET/DELETE /api/admin/organizations/:id/custom-domain
  - POST /api/admin/organizations/:id/custom-domain/verify
"""

import logging
import re
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from services.clerk_client import (
    ClerkAPIError,
    get_client as get_clerk_client,
    map_role_to_clerk,
)

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


def _get_clerk_org_id(org_id: str) -> str | None:
    """Return the org's clerk_org_id, or None if missing/unset (best-effort)."""
    try:
        supabase = _get_supabase()
        row = (
            supabase.table('organizations').select('clerk_org_id')
            .eq('id', org_id).single().execute().data or {}
        )
        return row.get('clerk_org_id') or None
    except Exception as exc:
        logger.warning('clerk_org_id lookup failed for org=%s: %s', org_id, exc)
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


@admin_bp.route('/organizations/by-custom-domain/<path:host>', methods=['GET'])
def get_org_by_custom_domain(host: str):
    """Public lookup: resolve an active org by its custom domain (host header).

    Mirrors the by-slug shape. Used by frontend middleware to map a custom
    domain to its org before request handling. Inactive orgs return 404 so
    suspended tenants stop serving content immediately.
    """
    normalized = (host or '').strip().lower().rstrip('.')
    if not normalized:
        return jsonify({'error': 'Not found'}), 404

    supabase = _get_supabase()
    result = (
        supabase.table('organizations')
        .select('*')
        .eq('custom_domain', normalized)
        .eq('status', 'active')
        .single()
        .execute()
    )
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
    """Invite a new member by email. Enforces tier seat cap (PRD §6.3)."""
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

    # Tier enforcement (only counts billable seats — owner role excluded).
    # Teachers and admins are still counted as seats since the PRD's seat
    # cap is "max students" but in practice anyone in the org takes a slot.
    from services.tier_quota import can_invite
    allowed, info = can_invite(org_id, n=1)
    if not allowed:
        return jsonify({
            'error': 'tier_limit_exceeded',
            'code': info.get('code', 'tier_limit_exceeded'),
            'current_count': info.get('current_count'),
            'seat_cap': info.get('seat_cap'),
            'plan': info.get('plan'),
            'upgrade_url': info.get('upgrade_url'),
        }), 402

    user_id = request.headers.get('X-User-Id')

    supabase = _get_supabase()
    invite_user_id = f'invite:{email}'

    supabase.table('organization_members').upsert({
        'organization_id': org_id,
        'user_id': invite_user_id,
        'role': role,
        'invited_by': user_id,
    }, on_conflict='organization_id,user_id').execute()

    # Fail-soft Clerk membership sync. Placeholder rows (user_id "invite:…")
    # are skipped — Clerk requires a real user id. The webhook handler
    # (organizationMembership.created) syncs the real id when the invitee
    # accepts. We still call Clerk here for forward-compat with future
    # real-user-id invites.
    _maybe_sync_membership_to_clerk(org_id, invite_user_id, role)

    # Real invite email (Phase 1 — replaces the previous stub log line).
    try:
        from services.email import send_invite_email
        send_invite_email(org_id=org_id, to_email=email, role=role)
    except Exception as exc:
        logger.warning('invite email send failed for %s: %s', email, exc)

    logger.info(f'Member invited: email={email} org={org_id} role={role} by={user_id}')
    return jsonify({'status': 'invited', 'email': email}), 201


def _maybe_sync_membership_to_clerk(org_id: str, user_id: str, role: str) -> None:
    """Best-effort Clerk membership create. No-op for placeholder rows or
    when the org has no clerk_org_id yet."""
    if not user_id or user_id.startswith('invite:'):
        return
    clerk_org_id = _get_clerk_org_id(org_id)
    if not clerk_org_id:
        logger.info(
            'org=%s not synced to Clerk yet, skipping membership sync for user=%s',
            org_id, user_id,
        )
        return
    try:
        get_clerk_client().create_membership(
            clerk_org_id, user_id, map_role_to_clerk(role),
        )
    except ClerkAPIError as exc:
        logger.warning(
            'Clerk create_membership failed (org=%s user=%s role=%s): %s',
            clerk_org_id, user_id, role, exc,
        )


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

    # Fail-soft Clerk membership cleanup. Skip placeholder invite rows.
    if not target_user_id.startswith('invite:'):
        clerk_org_id = _get_clerk_org_id(org_id)
        if clerk_org_id:
            try:
                get_clerk_client().delete_membership(clerk_org_id, target_user_id)
            except ClerkAPIError as exc:
                logger.warning(
                    'Clerk delete_membership failed (org=%s user=%s): %s',
                    clerk_org_id, target_user_id, exc,
                )

    logger.info(f'Member removed: user={target_user_id} org={org_id}')
    return jsonify({'status': 'removed'})


# --- Settings ---

# Reject CSS that could break out of the <style> block or smuggle JS in.
# Case-insensitive. Control chars (other than \t \n \r) also banned to keep
# the injection point clean.
_CSS_REJECT_PATTERNS = (
    re.compile(r'</\s*style', re.IGNORECASE),
    re.compile(r'<\s*script', re.IGNORECASE),
    re.compile(r'javascript\s*:', re.IGNORECASE),
)
_CSS_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _validate_custom_css(css: str) -> str | None:
    """Return None if `css` is safe to inject, otherwise an error message."""
    if css is None or css == '':
        return None
    if not isinstance(css, str):
        return 'custom_css must be a string'
    if len(css) > 50_000:
        return 'custom_css exceeds 50000 characters'
    for pat in _CSS_REJECT_PATTERNS:
        if pat.search(css):
            return 'custom_css contains forbidden content'
    if _CSS_CONTROL_CHAR_RE.search(css):
        return 'custom_css contains forbidden control characters'
    return None


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

    if 'custom_css' in update_data:
        css_err = _validate_custom_css(update_data['custom_css'])
        if css_err:
            return jsonify({'error': css_err}), 400

    supabase = _get_supabase()
    supabase.table('organizations').update(update_data).eq('id', org_id).execute()

    logger.info(f'Organization settings updated: org={org_id} fields={list(update_data.keys())}')
    return jsonify({'status': 'updated'})


# --- Branding asset upload ---

_BRANDING_BUCKET = 'org-branding'
_BRANDING_ALLOWED_MIME = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
    'image/svg+xml': 'svg',
    'image/x-icon': 'ico',
    'image/vnd.microsoft.icon': 'ico',
}
_BRANDING_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB
_BRANDING_KINDS = {'logo', 'favicon'}


@admin_bp.route('/organizations/<org_id>/branding/upload', methods=['POST'])
def upload_branding_asset(org_id: str):
    """Upload a logo or favicon to the `org-branding` Supabase Storage bucket.

    Body: multipart/form-data with:
      * file — the image bytes
      * kind — 'logo' or 'favicon'

    Validates membership (owner/admin), MIME type, and size ≤1 MiB.
    Returns { url: <public_url> } on success.
    """
    error = _require_admin(org_id)
    if error:
        return error

    kind = (request.form.get('kind') or '').strip().lower()
    if kind not in _BRANDING_KINDS:
        return jsonify({'error': 'kind must be logo or favicon'}), 400

    upload = request.files.get('file')
    if upload is None or upload.filename == '':
        return jsonify({'error': 'file is required'}), 400

    mime = (upload.mimetype or '').lower()
    if mime not in _BRANDING_ALLOWED_MIME:
        return jsonify({
            'error': f'Unsupported MIME type: {mime or "unknown"}',
        }), 415

    payload = upload.read()
    if len(payload) > _BRANDING_MAX_BYTES:
        return jsonify({'error': 'File exceeds 1 MiB limit'}), 413
    if not payload:
        return jsonify({'error': 'Empty file'}), 400

    ext = _BRANDING_ALLOWED_MIME[mime]
    object_key = f'{org_id}/{kind}.{ext}'

    supabase = _get_supabase()
    bucket = supabase.storage.from_(_BRANDING_BUCKET)
    try:
        bucket.upload(
            path=object_key,
            file=payload,
            file_options={
                'content-type': mime,
                'upsert': 'true',
                'cache-control': '3600',
            },
        )
    except Exception as e:  # noqa: BLE001 — surface storage errors as 502
        logger.exception(f'Branding upload failed: org={org_id} kind={kind}: {e}')
        return jsonify({'error': 'Upload failed', 'detail': str(e)}), 502

    public_url = bucket.get_public_url(object_key)
    # supabase-py historically appends a trailing `?`; strip it for cleanliness.
    if isinstance(public_url, str):
        public_url = public_url.rstrip('?')

    logger.info(f'Branding asset uploaded: org={org_id} kind={kind} key={object_key}')
    return jsonify({'url': public_url, 'key': object_key, 'kind': kind}), 201


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


# --- Custom domain (paid white-label upgrade) ---
# Spec: docs/prd/custom-domain-flow.md §2
# All four endpoints gated on the existing admin-level role check (owner/admin/teacher
# — matches PUT /:id/settings, which the PRD calls out as `can_edit_settings`).

# Lowercase, no trailing dot, no protocol; each label ≤63 chars; ≥2 labels.
_DOMAIN_RE = re.compile(
    r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?'
    r'(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$'
)


def _normalize_domain(raw: str) -> str:
    return (raw or '').strip().lower().rstrip('.')


def _validate_domain(domain: str) -> str | None:
    """Return None if valid, otherwise an error message."""
    if not domain:
        return 'Domain is required'
    if len(domain) > 253:
        return 'Domain exceeds 253 characters'
    if domain.endswith('.chesster.io') or domain == 'chesster.io':
        return 'chesster.io subdomains are not allowed as custom domains'
    if not _DOMAIN_RE.match(domain):
        return 'Domain format is invalid'
    return None


def _get_vercel_client():
    """Lazy import so unit tests can patch this hook."""
    from services.vercel_client import get_client
    return get_client()


def _vercel_error_to_response(err) -> tuple:
    """Translate VercelAPIError into a Flask (json, status) tuple per spec §2."""
    from services.vercel_client import VercelAPIError
    if not isinstance(err, VercelAPIError):
        return jsonify({'error': str(err)}), 500

    if err.code == 'domain_already_in_use':
        return jsonify({
            'error': 'This domain is already in use on Vercel.',
            'code': err.code,
        }), 409
    if err.code == 'not_authorized':
        return jsonify({
            'error': 'Vercel API not authorized — check VERCEL_TOKEN configuration.',
            'code': err.code,
        }), 502
    # Default: forward Vercel's status verbatim (clamped to client/server range)
    status = err.status_code if 400 <= err.status_code < 600 else 502
    return jsonify({'error': err.message, 'code': err.code}), status


@admin_bp.route('/organizations/<org_id>/custom-domain', methods=['POST'])
def add_custom_domain(org_id: str):
    """Register a custom domain for the org with Vercel + persist Vercel-id + status='pending'."""
    error = _require_admin(org_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    domain = _normalize_domain(data.get('domain', ''))
    validation_err = _validate_domain(domain)
    if validation_err:
        return jsonify({'error': validation_err}), 400

    # Pre-check DB uniqueness to surface the friendlier 409 before hitting Vercel.
    supabase = _get_supabase()
    existing = (
        supabase.table('organizations').select('id')
        .eq('custom_domain', domain).execute()
    )
    if existing.data:
        # If the row exists *and* belongs to this org we still want to refresh
        # it via Vercel — only treat as conflict if owned by another org.
        for row in existing.data:
            if row.get('id') != org_id:
                return jsonify({
                    'error': 'This domain is already in use by another organization.',
                    'code': 'domain_already_in_use',
                }), 409

    from services.vercel_client import VercelAPIError
    try:
        result = _get_vercel_client().add_domain(domain)
    except VercelAPIError as e:
        return _vercel_error_to_response(e)

    vercel_id = result.get('id') or result.get('name') or domain
    verification = result.get('verification') or []
    initial_status = 'active' if result.get('verified') else 'pending'

    update = {
        'custom_domain': domain,
        'custom_domain_status': initial_status,
        'custom_domain_vercel_id': vercel_id,
    }
    if initial_status == 'active':
        update['custom_domain_verified_at'] = datetime.now(timezone.utc).isoformat()

    supabase.table('organizations').update(update).eq('id', org_id).execute()

    logger.info(f'Custom domain registered: org={org_id} domain={domain} status={initial_status}')
    return jsonify({
        'domain': domain,
        'status': initial_status,
        'verification': verification,
        'vercel_id': vercel_id,
    }), 201


@admin_bp.route('/organizations/<org_id>/custom-domain', methods=['GET'])
def get_custom_domain(org_id: str):
    """Return current custom-domain state, refreshing status from Vercel when possible."""
    error = _require_admin(org_id)
    if error:
        return error

    supabase = _get_supabase()
    org = supabase.table('organizations').select(
        'custom_domain,custom_domain_status,custom_domain_verified_at,custom_domain_vercel_id'
    ).eq('id', org_id).single().execute()

    if not org.data or not org.data.get('custom_domain'):
        return jsonify({'domain': None, 'status': None}), 200

    domain = org.data['custom_domain']
    state = {
        'domain': domain,
        'status': org.data.get('custom_domain_status'),
        'verified_at': org.data.get('custom_domain_verified_at'),
        'vercel_id': org.data.get('custom_domain_vercel_id'),
        'verification': [],
    }

    from services.vercel_client import VercelAPIError
    try:
        live = _get_vercel_client().get_domain(domain)
    except VercelAPIError as e:
        logger.warning(f'Vercel get_domain failed for org={org_id}: {e}')
        return jsonify(state), 200

    state['verification'] = live.get('verification') or []
    live_verified = bool(live.get('verified'))
    new_status = 'active' if live_verified else (state['status'] or 'pending')

    # Persist transitions: pending → active when Vercel reports verified.
    if new_status != state['status']:
        update: dict = {'custom_domain_status': new_status}
        if new_status == 'active':
            update['custom_domain_verified_at'] = datetime.now(timezone.utc).isoformat()
        supabase.table('organizations').update(update).eq('id', org_id).execute()
        state['status'] = new_status
        if new_status == 'active':
            state['verified_at'] = update['custom_domain_verified_at']

    return jsonify(state), 200


@admin_bp.route('/organizations/<org_id>/custom-domain/verify', methods=['POST'])
def verify_custom_domain(org_id: str):
    """Trigger Vercel's verify call and persist active/failed status."""
    error = _require_admin(org_id)
    if error:
        return error

    supabase = _get_supabase()
    org = supabase.table('organizations').select('custom_domain').eq('id', org_id).single().execute()
    if not org.data or not org.data.get('custom_domain'):
        return jsonify({'error': 'No custom domain configured'}), 404
    domain = org.data['custom_domain']

    from services.vercel_client import VercelAPIError
    try:
        result = _get_vercel_client().verify_domain(domain)
    except VercelAPIError as e:
        if e.status_code == 409:
            supabase.table('organizations').update({
                'custom_domain_status': 'failed',
            }).eq('id', org_id).execute()
            return jsonify({
                'domain': domain,
                'status': 'failed',
                'error': e.message,
                'code': e.code,
            }), 409
        return _vercel_error_to_response(e)

    verified = bool(result.get('verified'))
    new_status = 'active' if verified else 'verifying'
    update: dict = {'custom_domain_status': new_status}
    if verified:
        update['custom_domain_verified_at'] = datetime.now(timezone.utc).isoformat()
    supabase.table('organizations').update(update).eq('id', org_id).execute()

    logger.info(f'Custom domain verify: org={org_id} domain={domain} status={new_status}')
    return jsonify({
        'domain': domain,
        'status': new_status,
        'verified': verified,
        'verification': result.get('verification') or [],
    }), 200


@admin_bp.route('/organizations/<org_id>/custom-domain', methods=['DELETE'])
def remove_custom_domain(org_id: str):
    """Detach the custom domain on Vercel and clear all four columns."""
    error = _require_admin(org_id)
    if error:
        return error

    supabase = _get_supabase()
    org = supabase.table('organizations').select('custom_domain').eq('id', org_id).single().execute()
    if not org.data or not org.data.get('custom_domain'):
        return jsonify({'status': 'removed'}), 200  # idempotent
    domain = org.data['custom_domain']

    from services.vercel_client import VercelAPIError
    try:
        _get_vercel_client().remove_domain(domain)
    except VercelAPIError as e:
        # 404 from Vercel means the domain was already gone there — treat as success.
        if e.status_code != 404:
            return _vercel_error_to_response(e)

    supabase.table('organizations').update({
        'custom_domain': None,
        'custom_domain_status': None,
        'custom_domain_verified_at': None,
        'custom_domain_vercel_id': None,
    }).eq('id', org_id).execute()

    logger.info(f'Custom domain removed: org={org_id} domain={domain}')
    return jsonify({'status': 'removed', 'domain': domain}), 200
