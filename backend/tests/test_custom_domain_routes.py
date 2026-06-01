"""Tests for the custom-domain admin endpoints.

Covers the 4 admin routes (POST/GET/POST verify/DELETE on
/api/admin/organizations/<org_id>/custom-domain) plus the public
GET /api/admin/organizations/by-custom-domain/<host>.

The Vercel API is mocked via the `responses` library so tests are deterministic
and never hit the real network.
"""

import os
import pytest
import responses
from unittest.mock import patch

from tests.test_admin_api import (
    FakeQueryBuilder, FakeQueryResult, _make_table_dispatcher,
    ADMIN_USER_ID, STUDENT_USER_ID, ORG_ID, SAMPLE_ORG,
)


VERCEL_PROJECT_ID = 'prj_test_123'
VERCEL_TEAM_ID = 'team_test_456'
VERCEL_TOKEN = 'test-token'


@pytest.fixture(autouse=True)
def _vercel_envs(monkeypatch):
    """Populate Vercel env vars before each test and reset the cached client."""
    monkeypatch.setenv('VERCEL_TOKEN', VERCEL_TOKEN)
    monkeypatch.setenv('VERCEL_PROJECT_ID', VERCEL_PROJECT_ID)
    monkeypatch.setenv('VERCEL_TEAM_ID', VERCEL_TEAM_ID)
    from services import vercel_client
    vercel_client.reset_client()
    yield
    vercel_client.reset_client()


@pytest.fixture
def app():
    from flask import Flask
    from routes.admin import admin_bp
    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(admin_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


# Stateful supabase mock that captures update() calls so tests can assert on them.
class StatefulSupabase:
    def __init__(self, initial_rows: dict):
        self.rows = initial_rows
        self.updates: list[dict] = []

    def table(self, name):
        return StatefulTable(self, name)


class StatefulTable:
    def __init__(self, parent: StatefulSupabase, name: str):
        self.parent = parent
        self.name = name
        self._filters: list[tuple] = []
        self._select_only = None
        self._pending_update: dict | None = None
        self._is_single = False

    def select(self, *args, **kwargs):
        self._select_only = args
        return self

    def update(self, data, **kwargs):
        self._pending_update = data
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def single(self):
        self._is_single = True
        return self

    def execute(self):
        if self._pending_update is not None:
            self.parent.updates.append({
                'table': self.name,
                'data': self._pending_update,
                'filters': list(self._filters),
            })
            for row in self.parent.rows.get(self.name, []):
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._pending_update)
            return FakeQueryResult(data=None, count=0)

        data = self.parent.rows.get(self.name, [])
        for col, val in self._filters:
            data = [r for r in data if r.get(col) == val]
        if self._is_single:
            return FakeQueryResult(data=(data[0] if len(data) == 1 else None),
                                   count=len(data))
        return FakeQueryResult(data=list(data), count=len(data))


def _vercel_url(path: str) -> str:
    return f'https://api.vercel.com{path}'


# ── POST /custom-domain ──────────────────────────────────────────────────────

class TestAddCustomDomain:

    @responses.activate
    def test_add_happy_path(self, client):
        verification = [
            {'type': 'CNAME', 'domain': 'chess.example.com', 'value': 'cname.vercel-dns.com'},
        ]
        responses.add(
            responses.POST,
            _vercel_url(f'/v10/projects/{VERCEL_PROJECT_ID}/domains'),
            json={
                'name': 'chess.example.com',
                'id': 'dom_abc',
                'verified': False,
                'verification': verification,
            },
            status=200,
        )
        rows = {'organizations': [dict(SAMPLE_ORG, custom_domain=None)]}
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'chess.example.com'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['domain'] == 'chess.example.com'
        assert body['status'] == 'pending'
        assert body['verification'] == verification

    def test_add_rejects_chesster_subdomain(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG)]}
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'evil.chesster.io'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 400
        assert 'chesster.io' in resp.get_json()['error']

    def test_add_rejects_invalid_format(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG)]}
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'not a domain!'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 400

    def test_add_normalises_case_and_trailing_dot(self, client):
        # Confirm that "CHESS.Example.COM." is normalised to lowercase no-dot before validation.
        # We cannot complete the call without mocking Vercel — but we *can* check that
        # the request short-circuits to 409 when the same lowercase host is owned elsewhere.
        rows = {'organizations': [
            {'id': 'other-org', 'custom_domain': 'chess.example.com'},
            dict(SAMPLE_ORG, custom_domain=None),
        ]}
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'CHESS.Example.COM.'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 409

    def test_add_forbidden_for_student(self, client):
        from flask import jsonify
        def fake_require(*a, **kw): return (jsonify({'error': 'Forbidden'}), 403)
        with patch('routes.admin._require_admin', side_effect=fake_require):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'ok.example.com'},
                headers={'X-User-Id': STUDENT_USER_ID},
            )
        assert resp.status_code == 403

    @responses.activate
    def test_add_vercel_already_in_use_409(self, client):
        responses.add(
            responses.POST,
            _vercel_url(f'/v10/projects/{VERCEL_PROJECT_ID}/domains'),
            json={'error': {'code': 'domain_already_in_use', 'message': 'taken'}},
            status=409,
        )
        rows = {'organizations': [dict(SAMPLE_ORG, custom_domain=None)]}
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'chess.example.com'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 409
        assert resp.get_json()['code'] == 'domain_already_in_use'

    @responses.activate
    def test_add_vercel_not_authorized_502(self, client):
        responses.add(
            responses.POST,
            _vercel_url(f'/v10/projects/{VERCEL_PROJECT_ID}/domains'),
            json={'error': {'code': 'not_authorized', 'message': 'bad token'}},
            status=403,
        )
        rows = {'organizations': [dict(SAMPLE_ORG, custom_domain=None)]}
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'chess.example.com'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 502


# ── GET /custom-domain ───────────────────────────────────────────────────────

class TestGetCustomDomain:

    def test_get_no_domain(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG, custom_domain=None,
                                        custom_domain_status=None,
                                        custom_domain_verified_at=None,
                                        custom_domain_vercel_id=None)]}
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 200
        assert resp.get_json()['domain'] is None

    @responses.activate
    def test_get_promotes_pending_to_active_when_vercel_verifies(self, client):
        responses.add(
            responses.GET,
            _vercel_url(f'/v9/projects/{VERCEL_PROJECT_ID}/domains/chess.example.com'),
            json={'name': 'chess.example.com', 'verified': True, 'verification': []},
            status=200,
        )
        sb = StatefulSupabase({'organizations': [dict(
            SAMPLE_ORG,
            custom_domain='chess.example.com',
            custom_domain_status='pending',
            custom_domain_verified_at=None,
            custom_domain_vercel_id='dom_abc',
        )]})
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=sb):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['status'] == 'active'
        # Update was persisted
        assert any(u['data'].get('custom_domain_status') == 'active' for u in sb.updates)


# ── POST /custom-domain/verify ───────────────────────────────────────────────

class TestVerifyCustomDomain:

    @responses.activate
    def test_verify_success(self, client):
        responses.add(
            responses.POST,
            _vercel_url(f'/v9/projects/{VERCEL_PROJECT_ID}/domains/chess.example.com/verify'),
            json={'name': 'chess.example.com', 'verified': True, 'verification': []},
            status=200,
        )
        sb = StatefulSupabase({'organizations': [dict(
            SAMPLE_ORG,
            custom_domain='chess.example.com',
            custom_domain_status='pending',
        )]})
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=sb):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain/verify',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'active'

    @responses.activate
    def test_verify_409_sets_failed(self, client):
        responses.add(
            responses.POST,
            _vercel_url(f'/v9/projects/{VERCEL_PROJECT_ID}/domains/chess.example.com/verify'),
            json={'error': {'code': 'verification_failed', 'message': 'DNS not propagated'}},
            status=409,
        )
        sb = StatefulSupabase({'organizations': [dict(
            SAMPLE_ORG,
            custom_domain='chess.example.com',
            custom_domain_status='pending',
        )]})
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=sb):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain/verify',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 409
        assert resp.get_json()['status'] == 'failed'
        assert any(u['data'].get('custom_domain_status') == 'failed' for u in sb.updates)

    def test_verify_404_when_no_domain(self, client):
        sb = StatefulSupabase({'organizations': [dict(SAMPLE_ORG, custom_domain=None)]})
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=sb):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain/verify',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 404


# ── DELETE /custom-domain ────────────────────────────────────────────────────

class TestRemoveCustomDomain:

    @responses.activate
    def test_remove_clears_columns(self, client):
        responses.add(
            responses.DELETE,
            _vercel_url(f'/v9/projects/{VERCEL_PROJECT_ID}/domains/chess.example.com'),
            json={'uid': 'dom_abc'},
            status=200,
        )
        sb = StatefulSupabase({'organizations': [dict(
            SAMPLE_ORG,
            custom_domain='chess.example.com',
            custom_domain_status='active',
            custom_domain_vercel_id='dom_abc',
        )]})
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=sb):
            resp = client.delete(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 200
        last_update = sb.updates[-1]['data']
        assert last_update == {
            'custom_domain': None,
            'custom_domain_status': None,
            'custom_domain_verified_at': None,
            'custom_domain_vercel_id': None,
        }

    @responses.activate
    def test_remove_idempotent_when_vercel_404(self, client):
        responses.add(
            responses.DELETE,
            _vercel_url(f'/v9/projects/{VERCEL_PROJECT_ID}/domains/chess.example.com'),
            json={'error': {'code': 'not_found', 'message': 'gone'}},
            status=404,
        )
        sb = StatefulSupabase({'organizations': [dict(
            SAMPLE_ORG,
            custom_domain='chess.example.com',
            custom_domain_status='active',
        )]})
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=sb):
            resp = client.delete(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        # 404 from Vercel is treated as already-removed (idempotent).
        assert resp.status_code == 200

    def test_remove_when_no_domain_succeeds(self, client):
        sb = StatefulSupabase({'organizations': [dict(SAMPLE_ORG, custom_domain=None)]})
        with patch('routes.admin._require_admin', return_value=None), \
             patch('routes.admin._get_supabase', return_value=sb):
            resp = client.delete(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
        assert resp.status_code == 200


# ── Public GET /by-custom-domain/<host> ─────────────────────────────────────

class TestPublicByCustomDomain:

    def test_returns_active_org(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG,
                                        custom_domain='chess.example.com',
                                        status='active')]}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/chess.example.com')
        assert resp.status_code == 200
        assert resp.get_json()['custom_domain'] == 'chess.example.com'

    def test_404_for_unknown_host(self, client):
        rows = {'organizations': []}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/unknown.example.com')
        assert resp.status_code == 404

    def test_ignores_inactive_orgs(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG,
                                        custom_domain='chess.example.com',
                                        status='suspended')]}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/chess.example.com')
        assert resp.status_code == 404

    def test_normalises_case(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG,
                                        custom_domain='chess.example.com',
                                        status='active')]}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/CHESS.Example.COM')
        assert resp.status_code == 200
