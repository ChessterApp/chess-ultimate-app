"""
Tests for the Admin API (/api/admin) blueprint.

Tests organization management endpoints with mocked Supabase.
"""

import pytest
from unittest.mock import patch, MagicMock


ADMIN_USER_ID = 'user_admin_123'
STUDENT_USER_ID = 'user_student_456'
ORG_ID = 'org-11111111-1111-1111-1111-111111111111'
ORG_SLUG = 'testschool'

SAMPLE_ORG = {
    'id': ORG_ID,
    'slug': ORG_SLUG,
    'name': 'Test Chess School',
    'logo_url': None,
    'favicon_url': None,
    'primary_color': '#1a73e8',
    'secondary_color': '#ffffff',
    'accent_color': '#ffd700',
    'landing_page_config': {},
    'contact_email': 'admin@test.com',
    'status': 'active',
}

SAMPLE_MEMBERS = [
    {'id': 'mem-1', 'organization_id': ORG_ID, 'user_id': ADMIN_USER_ID, 'role': 'admin', 'joined_at': '2025-01-01'},
    {'id': 'mem-2', 'organization_id': ORG_ID, 'user_id': STUDENT_USER_ID, 'role': 'student', 'joined_at': '2025-01-02'},
]


class FakeQueryResult:
    """Mimics Supabase query result."""
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class FakeQueryBuilder:
    """Chainable mock for Supabase table().select()...execute() pattern."""
    def __init__(self, data=None, count=None):
        self._data = data
        self._count = count

    def select(self, *args, **kwargs):
        return self

    def insert(self, data, **kwargs):
        return self

    def update(self, data, **kwargs):
        return self

    def delete(self, **kwargs):
        return self

    def upsert(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def single(self):
        if isinstance(self._data, list):
            self._data = self._data[0] if self._data else None
        return self

    def execute(self):
        return FakeQueryResult(data=self._data, count=self._count)


def _make_table_dispatcher(table_data: dict):
    """
    Create a supabase.table() mock that returns different data per table name.
    table_data: {'organizations': [...], 'organization_members': [...], ...}
    """
    def table(name):
        data = table_data.get(name, [])
        count = len(data) if isinstance(data, list) else (1 if data else 0)
        return FakeQueryBuilder(data=data, count=count)
    return table


@pytest.fixture
def app():
    """Create a minimal Flask app with the admin blueprint."""
    from flask import Flask
    from routes.admin import admin_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(admin_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


# ─── Organization Lookup ─────────────────────────────────────────────────────

class TestGetOrgBySlug:
    def test_org_found(self, client):
        with patch('routes.admin._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_table_dispatcher({
                'organizations': SAMPLE_ORG,
            })
            resp = client.get(f'/api/admin/organizations/by-slug/{ORG_SLUG}')
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['slug'] == ORG_SLUG
            assert body['name'] == 'Test Chess School'

    def test_org_not_found(self, client):
        with patch('routes.admin._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_table_dispatcher({
                'organizations': None,
            })
            resp = client.get('/api/admin/organizations/by-slug/nonexistent')
            assert resp.status_code == 404


# ─── Members ─────────────────────────────────────────────────────────────────

class TestGetMembers:
    def test_list_members_as_admin(self, client):
        with patch('routes.admin._get_supabase') as mock_sb:
            admin_member = {'role': 'admin'}
            mock_sb.return_value.table = _make_table_dispatcher({
                'organization_members': SAMPLE_MEMBERS,
            })
            # Override _get_caller_role to return admin
            with patch('routes.admin._get_caller_role', return_value='admin'):
                resp = client.get(
                    f'/api/admin/organizations/{ORG_ID}/members',
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 200
                body = resp.get_json()
                assert 'members' in body

    def test_list_members_no_auth(self, client):
        """Missing X-User-Id header should 401."""
        resp = client.get(f'/api/admin/organizations/{ORG_ID}/members')
        assert resp.status_code == 401

    def test_list_members_forbidden_for_student(self, client):
        """Student role should be forbidden."""
        with patch('routes.admin._get_caller_role', return_value='student'):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/members',
                headers={'X-User-Id': STUDENT_USER_ID},
            )
            assert resp.status_code == 403

    def test_list_members_user_id_filter_bypasses_admin_check(self, client):
        """When user_id filter is provided, the endpoint returns data without admin check."""
        with patch('routes.admin._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_table_dispatcher({
                'organization_members': SAMPLE_MEMBERS,
            })
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/members?user_id={STUDENT_USER_ID}',
            )
            assert resp.status_code == 200


# ─── Invite Member ───────────────────────────────────────────────────────────

class TestInviteMember:
    def test_invite_success(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organization_members': [],
                })
                resp = client.post(
                    f'/api/admin/organizations/{ORG_ID}/members/invite',
                    json={'email': 'student@example.com'},
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 201
                body = resp.get_json()
                assert body['email'] == 'student@example.com'

    def test_invite_missing_email(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/members/invite',
                json={},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 400


# ─── Remove Member ───────────────────────────────────────────────────────────

class TestRemoveMember:
    def test_remove_student(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organization_members': {'role': 'student'},
                })
                resp = client.delete(
                    f'/api/admin/organizations/{ORG_ID}/members/{STUDENT_USER_ID}',
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 200

    def test_cannot_remove_owner(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organization_members': {'role': 'owner'},
                })
                resp = client.delete(
                    f'/api/admin/organizations/{ORG_ID}/members/owner_user_id',
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 403


# ─── Settings ────────────────────────────────────────────────────────────────

class TestUpdateSettings:
    def test_update_branding(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organizations': SAMPLE_ORG,
                })
                resp = client.put(
                    f'/api/admin/organizations/{ORG_ID}/settings',
                    json={'primary_color': '#ff0000', 'accent_color': '#00ff00'},
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 200

    def test_update_settings_forbidden_fields_filtered(self, client):
        """Fields not in the allowed list should be silently ignored."""
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organizations': SAMPLE_ORG,
                })
                resp = client.put(
                    f'/api/admin/organizations/{ORG_ID}/settings',
                    json={'id': 'hacked', 'slug': 'hacked', 'primary_color': '#ff0000'},
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 200

    def test_update_no_valid_fields(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            resp = client.put(
                f'/api/admin/organizations/{ORG_ID}/settings',
                json={'id': 'hacked'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 400

    def test_update_settings_student_forbidden(self, client):
        with patch('routes.admin._get_caller_role', return_value='student'):
            resp = client.put(
                f'/api/admin/organizations/{ORG_ID}/settings',
                json={'primary_color': '#ff0000'},
                headers={'X-User-Id': STUDENT_USER_ID},
            )
            assert resp.status_code == 403

    def test_update_favicon_url_accepted(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organizations': SAMPLE_ORG,
                })
                resp = client.put(
                    f'/api/admin/organizations/{ORG_ID}/settings',
                    json={'favicon_url': 'https://cdn.example.com/favicon.ico'},
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 200

    def test_update_custom_css_accepted_when_safe(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organizations': SAMPLE_ORG,
                })
                resp = client.put(
                    f'/api/admin/organizations/{ORG_ID}/settings',
                    json={'custom_css': ':root { --brand-radius: 12px; }'},
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 200

    def test_update_custom_css_rejects_style_breakout(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            resp = client.put(
                f'/api/admin/organizations/{ORG_ID}/settings',
                json={'custom_css': 'body{}</style><script>alert(1)</script>'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 400

    def test_update_custom_css_rejects_script_tag(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            resp = client.put(
                f'/api/admin/organizations/{ORG_ID}/settings',
                json={'custom_css': 'body{} <SCRIPT> bad'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 400

    def test_update_custom_css_rejects_javascript_protocol(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            resp = client.put(
                f'/api/admin/organizations/{ORG_ID}/settings',
                json={'custom_css': '.x { background: url(javascript:alert(1)); }'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 400


# ─── Content ─────────────────────────────────────────────────────────────────

class TestContent:
    def test_get_content(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organization_content': [],
                    'courses': {'title': 'Chess Basics'},
                })
                resp = client.get(
                    f'/api/admin/organizations/{ORG_ID}/content',
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 200
                body = resp.get_json()
                assert 'courses' in body

    def test_update_content(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.table = _make_table_dispatcher({
                    'organization_content': [],
                })
                resp = client.put(
                    f'/api/admin/organizations/{ORG_ID}/content',
                    json={'courses': [
                        {'course_id': 'c1', 'visible': True, 'order_index': 0},
                    ]},
                    headers={'X-User-Id': ADMIN_USER_ID},
                )
                assert resp.status_code == 200


# ─── Stats ───────────────────────────────────────────────────────────────────

class TestStats:
    def test_get_stats(self, client):
        with patch('routes.admin._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_table_dispatcher({
                'organization_members': SAMPLE_MEMBERS,
                'user_progress': [],
            })
            resp = client.get(f'/api/admin/organizations/{ORG_ID}/stats')
            assert resp.status_code == 200
            body = resp.get_json()
            assert 'student_count' in body
            assert 'active_this_week' in body
            assert 'course_completion_rate' in body
