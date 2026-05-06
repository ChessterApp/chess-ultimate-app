"""
Tests for the Super-Admin API (/api/super-admin) blueprint.

Covers Phase 7A + 7B:
  - require_super_admin gate (role + 2FA + impersonation)
  - Audit log INSERT on every successful mutation
  - Read-only impersonation cookie blocks writes (super-admin + global hook)
  - User search, suspend, unsuspend, refund, impersonate flows
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


ADMIN_CLERK_ID = 'user_super_admin_1'
TARGET_CLERK_ID = 'user_target_99'
ADMIN_RECORD = {
    'id': ADMIN_CLERK_ID,
    'public_metadata': {'platform_role': 'super_admin'},
    'two_factor_enabled': True,
    'first_name': 'Alex',
    'last_name': 'Admin',
    'primary_email_address_id': 'email_1',
    'email_addresses': [{'id': 'email_1', 'email_address': 'alex@chesster.io'}],
}
NON_ADMIN_RECORD = {
    'id': 'user_random',
    'public_metadata': {},
    'two_factor_enabled': False,
}


# ─── Fake Supabase ──────────────────────────────────────────────────────────

class _Result:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Query:
    """Recording, chainable Supabase mock that records inserts and updates."""

    def __init__(self, store, table_name):
        self._store = store
        self._table = table_name
        self._filters = []

    def select(self, *args, **kwargs):
        return self

    def insert(self, payload, **kwargs):
        rows = payload if isinstance(payload, list) else [payload]
        for row in rows:
            row.setdefault('id', f'fake-id-{len(self._store.inserts) + 1}')
        self._store.inserts.append((self._table, rows))
        self._store.tables.setdefault(self._table, []).extend(rows)
        return _StaticResult(rows)

    def upsert(self, payload, **kwargs):
        self._store.upserts.append((self._table, payload))
        rows = payload if isinstance(payload, list) else [payload]
        self._store.tables.setdefault(self._table, []).extend(rows)
        return _StaticResult(rows)

    def update(self, payload, **kwargs):
        self._store.updates.append((self._table, payload))
        return self

    def delete(self, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def or_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def single(self):
        return self

    def execute(self):
        rows = self._store.tables.get(self._table, [])
        return _Result(data=rows, count=len(rows))


class _StaticResult:
    """A pre-resolved query result that returns the inserted rows."""

    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return _Result(data=self._rows, count=len(self._rows))


class _SupabaseMock:
    def __init__(self, initial_tables=None):
        self.tables = dict(initial_tables or {})
        self.inserts = []
        self.upserts = []
        self.updates = []

    def table(self, name):
        return _Query(self, name)


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def supabase_store():
    return _SupabaseMock(initial_tables={
        'platform_user_cache': [
            {
                'clerk_id': TARGET_CLERK_ID,
                'email': 'target@example.com',
                'name': 'Target User',
                'subscription_status': 'monthly',
                'whop_membership_id': 'mem_xyz',
                'org_count': 1,
                'total_revenue_cents': 999,
                'signup_at': '2025-12-01T00:00:00Z',
            },
        ],
        'platform_user_status': [],
        'platform_admin_audit_log': [],
        'organization_members': [],
        'impersonation_sessions': [],
    })


@pytest.fixture
def app(supabase_store):
    from flask import Flask
    from routes.super_admin import super_admin_bp
    from utils.auth import install_impersonation_write_block

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(super_admin_bp)
    install_impersonation_write_block(test_app)
    test_app._supabase_store = supabase_store  # type: ignore[attr-defined]
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _patch_supabase(supabase_store):
    """Route the super-admin blueprint's _get_supabase to our in-memory store."""
    with patch('routes.super_admin._get_supabase', return_value=supabase_store):
        yield


@pytest.fixture
def admin_auth():
    """Patch the auth decorator helpers so any token resolves to the super admin."""
    fake_claims = {'sub': ADMIN_CLERK_ID, 'two_factor': True}
    with patch('utils.auth._decode_clerk_token', return_value=fake_claims), \
         patch('utils.auth._fetch_clerk_user', return_value=ADMIN_RECORD):
        yield


@pytest.fixture
def non_admin_auth():
    fake_claims = {'sub': 'user_random'}
    with patch('utils.auth._decode_clerk_token', return_value=fake_claims), \
         patch('utils.auth._fetch_clerk_user', return_value=NON_ADMIN_RECORD):
        yield


def _bearer():
    return {'Authorization': 'Bearer fake-jwt'}


# ─── Auth gate ──────────────────────────────────────────────────────────────

class TestAuthGate:
    def test_no_token_returns_401(self, client):
        resp = client.get('/api/super-admin/me')
        assert resp.status_code == 401

    def test_non_admin_returns_403(self, client, non_admin_auth):
        resp = client.get('/api/super-admin/me', headers=_bearer())
        assert resp.status_code == 403

    def test_super_admin_returns_profile(self, client, admin_auth):
        resp = client.get('/api/super-admin/me', headers=_bearer())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['clerk_id'] == ADMIN_CLERK_ID
        assert body['platform_role'] == 'super_admin'
        assert body['email'] == 'alex@chesster.io'

    def test_2fa_disabled_returns_403(self, client):
        # 2FA must be active at the JWT or user record level.
        no_2fa = {**ADMIN_RECORD, 'two_factor_enabled': False}
        with patch('utils.auth._decode_clerk_token', return_value={'sub': ADMIN_CLERK_ID}), \
             patch('utils.auth._fetch_clerk_user', return_value=no_2fa):
            resp = client.get('/api/super-admin/me', headers=_bearer())
            assert resp.status_code == 403
            assert resp.get_json()['reason'] == 'two_factor_required'


# ─── User search ────────────────────────────────────────────────────────────

class TestSearchUsers:
    def test_search_returns_users(self, client, admin_auth):
        resp = client.get('/api/super-admin/users', headers=_bearer())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['count'] == 1
        assert body['users'][0]['email'] == 'target@example.com'
        # Defaulted account_status when no row in platform_user_status.
        assert body['users'][0]['account_status'] == 'active'


# ─── User detail ────────────────────────────────────────────────────────────

class TestUserDetail:
    def test_detail_returns_aggregated_view(self, client, admin_auth):
        with patch('routes.super_admin._clerk_request', return_value=(200, {'id': TARGET_CLERK_ID})):
            resp = client.get(f'/api/super-admin/users/{TARGET_CLERK_ID}', headers=_bearer())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['clerk_id'] == TARGET_CLERK_ID
        assert body['cache']['email'] == 'target@example.com'
        assert body['memberships'] == []


# ─── Suspend / unsuspend ────────────────────────────────────────────────────

class TestSuspend:
    def test_suspend_requires_reason(self, client, admin_auth):
        resp = client.post(
            f'/api/super-admin/users/{TARGET_CLERK_ID}/suspend',
            json={},
            headers=_bearer(),
        )
        assert resp.status_code == 400

    def test_suspend_writes_status_and_audit(self, client, admin_auth, supabase_store):
        with patch('routes.super_admin._clerk_request', return_value=(200, {})):
            resp = client.post(
                f'/api/super-admin/users/{TARGET_CLERK_ID}/suspend',
                json={'reason': 'spam'},
                headers=_bearer(),
            )
        assert resp.status_code == 200
        # Status row upserted.
        suspends = [u for u in supabase_store.upserts if u[0] == 'platform_user_status']
        assert suspends, 'expected upsert into platform_user_status'
        assert suspends[-1][1]['status'] == 'suspended'
        assert suspends[-1][1]['suspended_reason'] == 'spam'
        # Audit row inserted.
        audits = [i for i in supabase_store.inserts if i[0] == 'platform_admin_audit_log']
        assert audits, 'expected audit log insert'
        actions = [row['action'] for _, rows in audits for row in rows]
        assert 'user.suspend' in actions

    def test_unsuspend_resets_status(self, client, admin_auth, supabase_store):
        with patch('routes.super_admin._clerk_request', return_value=(200, {})):
            resp = client.post(
                f'/api/super-admin/users/{TARGET_CLERK_ID}/unsuspend',
                headers=_bearer(),
            )
        assert resp.status_code == 200
        last = [u for u in supabase_store.upserts if u[0] == 'platform_user_status'][-1]
        assert last[1]['status'] == 'active'
        assert last[1]['suspended_reason'] is None


# ─── Refund ─────────────────────────────────────────────────────────────────

class TestRefund:
    def test_refund_requires_reason(self, client, admin_auth):
        resp = client.post(
            f'/api/super-admin/users/{TARGET_CLERK_ID}/refund',
            json={'amount_cents': 999},
            headers=_bearer(),
        )
        assert resp.status_code == 400

    def test_refund_calls_whop_and_audits(self, client, admin_auth, supabase_store):
        with patch('routes.super_admin._whop_request', return_value=(200, {'id': 'refund_1'})):
            resp = client.post(
                f'/api/super-admin/users/{TARGET_CLERK_ID}/refund',
                json={'reason': 'duplicate charge', 'amount_cents': 999},
                headers=_bearer(),
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['status'] == 'refunded'
        assert body['membership_id'] == 'mem_xyz'
        actions = [
            row['action']
            for table, rows in supabase_store.inserts
            if table == 'platform_admin_audit_log'
            for row in rows
        ]
        assert 'user.refund' in actions

    def test_refund_returns_502_when_whop_fails(self, client, admin_auth):
        with patch('routes.super_admin._whop_request', return_value=(500, {'error': 'boom'})):
            resp = client.post(
                f'/api/super-admin/users/{TARGET_CLERK_ID}/refund',
                json={'reason': 'test'},
                headers=_bearer(),
            )
        assert resp.status_code == 502


# ─── Impersonation lifecycle + write-block ──────────────────────────────────

class TestImpersonation:
    def test_start_impersonation_sets_cookie(self, client, admin_auth, supabase_store):
        resp = client.post(
            f'/api/super-admin/users/{TARGET_CLERK_ID}/impersonate',
            json={'reason': 'support'},
            headers=_bearer(),
        )
        assert resp.status_code == 200
        # Cookie set on the response.
        cookies = resp.headers.getlist('Set-Cookie')
        assert any('chesster_impersonation=' in c for c in cookies)
        # Session row inserted.
        assert any(
            t == 'impersonation_sessions' for t, _ in supabase_store.inserts
        )

    def test_write_blocked_with_impersonation_cookie(self, client, admin_auth):
        """Even a super-admin cannot perform a non-end mutation while the cookie is set."""
        client.set_cookie('chesster_impersonation', 'session-uuid', path='/')
        resp = client.post(
            f'/api/super-admin/users/{TARGET_CLERK_ID}/suspend',
            json={'reason': 'should not pass'},
            headers=_bearer(),
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body['reason'] == 'impersonation_active'

    def test_end_impersonation_works_with_cookie(self, client, admin_auth):
        client.set_cookie('chesster_impersonation', 'session-uuid', path='/')
        resp = client.delete('/api/super-admin/impersonation', headers=_bearer())
        assert resp.status_code == 200
        # Set-Cookie clears the impersonation cookie (max-age=0 / past expiry).
        clear_headers = resp.headers.getlist('Set-Cookie')
        assert any('chesster_impersonation=' in c and ('Expires=' in c or 'Max-Age=0' in c)
                   for c in clear_headers)

    def test_global_write_block_for_non_super_admin_routes(self):
        """An arbitrary blueprint registered alongside the hook is also blocked."""
        from flask import Blueprint, Flask, jsonify
        from utils.auth import install_impersonation_write_block

        bp = Blueprint('demo', __name__, url_prefix='/api/demo')

        @bp.route('/write', methods=['POST'])
        def write():
            return jsonify({'ok': True})

        @bp.route('/read', methods=['GET'])
        def read():
            return jsonify({'ok': True})

        app = Flask(__name__)
        app.register_blueprint(bp)
        install_impersonation_write_block(app)
        c = app.test_client()
        c.set_cookie('chesster_impersonation', 'sess', path='/')
        # Reads succeed
        assert c.get('/api/demo/read').status_code == 200
        # Writes blocked
        blocked = c.post('/api/demo/write')
        assert blocked.status_code == 403
        assert blocked.get_json()['reason'] == 'impersonation_active'


# ─── Audit log read ─────────────────────────────────────────────────────────

class TestAuditList:
    def test_audit_endpoint_returns_entries(self, client, admin_auth, supabase_store):
        supabase_store.tables['platform_admin_audit_log'] = [
            {'id': 'a1', 'action': 'user.suspend', 'target_type': 'user',
             'target_id': TARGET_CLERK_ID, 'created_at': '2026-05-06T00:00:00Z'},
        ]
        resp = client.get('/api/super-admin/audit', headers=_bearer())
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body['entries']) == 1
        assert body['entries'][0]['action'] == 'user.suspend'
