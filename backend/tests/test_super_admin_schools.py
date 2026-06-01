"""
Tests for the Super-Admin Schools dashboard endpoints (Phase 7C).

Covers:
  - GET    /api/super-admin/organizations               list + filter + paginate
  - GET    /api/super-admin/organizations/<id>          full detail
  - POST   /api/super-admin/organizations/<id>/suspend  suspend (idempotent)
  - POST   /api/super-admin/organizations/<id>/unsuspend  unsuspend (idempotent)
  - POST   /api/super-admin/organizations/<id>/promote  promote member to owner

Reuses the fixture pattern from test_super_admin_api.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


ADMIN_CLERK_ID = 'user_super_admin_1'
ORG_A = 'org-aaa'
ORG_B = 'org-bbb'
ADMIN_RECORD = {
    'id': ADMIN_CLERK_ID,
    'public_metadata': {'platform_role': 'super_admin'},
    'two_factor_enabled': True,
    'first_name': 'Alex',
    'last_name': 'Admin',
    'primary_email_address_id': 'email_1',
    'email_addresses': [{'id': 'email_1', 'email_address': 'alex@chesster.io'}],
}


# ─── Fake Supabase (records filters so we can assert pagination math) ───────

class _Result:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, store, table_name):
        self._store = store
        self._table = table_name
        self._eq_filters: list[tuple[str, object]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._or_expressions: list[str] = []
        self._range: tuple[int, int] | None = None
        self._limit: int | None = None
        self._want_count = False

    def select(self, *args, count=None, **kwargs):
        if count == 'exact':
            self._want_count = True
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
        self._store.updates.append((self._table, payload, list(self._eq_filters)))
        # Apply update to matching rows so subsequent reads see the change.
        rows = self._store.tables.get(self._table, [])
        for row in rows:
            if all(row.get(k) == v for k, v in self._eq_filters):
                row.update(payload)
        return self

    def delete(self, **kwargs):
        return self

    def eq(self, column, value):
        self._eq_filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, list(values)))
        return self

    def or_(self, expression):
        self._or_expressions.append(expression)
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def gte(self, *args, **kwargs):
        return self

    def single(self):
        return self

    def execute(self):
        rows = list(self._store.tables.get(self._table, []))

        for col, val in self._eq_filters:
            rows = [r for r in rows if r.get(col) == val]
        for col, vals in self._in_filters:
            allowed = set(vals)
            rows = [r for r in rows if r.get(col) in allowed]
        for expression in self._or_expressions:
            rows = _apply_or(rows, expression)

        total = len(rows)

        if self._range is not None:
            start, end = self._range
            rows = rows[start:end + 1]
        elif self._limit is not None:
            rows = rows[: self._limit]

        return _Result(data=rows, count=total if self._want_count else None)


def _apply_or(rows, expression: str):
    """Apply a postgrest-style `or_` clause: `col1.ilike.%foo%,col2.ilike.%foo%`."""
    matched: list = []
    seen: set = set()
    for clause in expression.split(','):
        clause = clause.strip()
        if '.ilike.' not in clause:
            continue
        col, _, pattern = clause.partition('.ilike.')
        needle = pattern.strip('%').lower()
        for row in rows:
            cell = row.get(col)
            if isinstance(cell, str) and needle in cell.lower():
                row_id = id(row)
                if row_id not in seen:
                    seen.add(row_id)
                    matched.append(row)
    return matched


class _StaticResult:
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

def _seed():
    return {
        'organizations': [
            {
                'id': ORG_A,
                'slug': 'kings-academy',
                'name': "King's Academy",
                'status': 'active',
                'custom_domain': 'play.kings-academy.com',
                'custom_domain_status': 'active',
                'created_at': '2026-04-01T00:00:00Z',
            },
            {
                'id': ORG_B,
                'slug': 'queens-club',
                'name': "Queen's Club",
                'status': 'trial',
                'custom_domain': None,
                'custom_domain_status': None,
                'created_at': '2026-05-15T00:00:00Z',
            },
        ],
        'organization_members': [
            {'id': 'm-1', 'organization_id': ORG_A, 'user_id': 'user_owner_a',
             'role': 'owner', 'joined_at': '2026-04-01T00:00:00Z'},
            {'id': 'm-2', 'organization_id': ORG_A, 'user_id': 'user_member_a',
             'role': 'teacher', 'joined_at': '2026-04-02T00:00:00Z'},
            {'id': 'm-3', 'organization_id': ORG_B, 'user_id': 'user_owner_b',
             'role': 'owner', 'joined_at': '2026-05-15T00:00:00Z'},
        ],
        'organization_billing': [
            {'organization_id': ORG_A, 'plan': 'growth', 'student_count': 42},
        ],
        'platform_admin_audit_log': [],
    }


@pytest.fixture
def supabase_store():
    return _SupabaseMock(initial_tables=_seed())


@pytest.fixture
def app(supabase_store):
    from flask import Flask
    from routes.super_admin import super_admin_bp
    from utils.auth import install_impersonation_write_block

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(super_admin_bp)
    install_impersonation_write_block(test_app)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _patch_supabase(supabase_store):
    with patch('routes.super_admin._get_supabase', return_value=supabase_store):
        yield


@pytest.fixture
def admin_auth():
    fake_claims = {'sub': ADMIN_CLERK_ID, 'two_factor': True}
    with patch('utils.auth._decode_clerk_token', return_value=fake_claims), \
         patch('utils.auth._fetch_clerk_user', return_value=ADMIN_RECORD):
        yield


def _bearer():
    return {'Authorization': 'Bearer fake-jwt'}


# ─── List endpoint ──────────────────────────────────────────────────────────

class TestListOrganizations:
    def test_returns_all_organizations(self, client, admin_auth):
        resp = client.get('/api/super-admin/organizations', headers=_bearer())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['total'] == 2
        slugs = sorted(item['slug'] for item in body['items'])
        assert slugs == ['kings-academy', 'queens-club']

    def test_item_shape_includes_counts_and_billing(self, client, admin_auth):
        resp = client.get('/api/super-admin/organizations', headers=_bearer())
        items = {item['slug']: item for item in resp.get_json()['items']}
        kings = items['kings-academy']
        assert kings['member_count'] == 2
        assert kings['plan'] == 'growth'
        assert kings['student_count'] == 42
        assert kings['custom_domain'] == 'play.kings-academy.com'
        queens = items['queens-club']
        assert queens['member_count'] == 1
        assert queens['plan'] is None
        assert queens['custom_domain'] is None

    def test_status_filter(self, client, admin_auth):
        resp = client.get(
            '/api/super-admin/organizations?status=trial',
            headers=_bearer(),
        )
        body = resp.get_json()
        assert body['total'] == 1
        assert body['items'][0]['slug'] == 'queens-club'

    def test_search_matches_slug_and_name(self, client, admin_auth):
        resp = client.get(
            '/api/super-admin/organizations?q=queen',
            headers=_bearer(),
        )
        body = resp.get_json()
        assert body['total'] == 1
        assert body['items'][0]['slug'] == 'queens-club'

        resp2 = client.get(
            '/api/super-admin/organizations?q=academy',
            headers=_bearer(),
        )
        body2 = resp2.get_json()
        assert body2['total'] == 1
        assert body2['items'][0]['slug'] == 'kings-academy'

    def test_pagination_offset_and_limit(self, client, admin_auth):
        resp = client.get(
            '/api/super-admin/organizations?limit=1&offset=0',
            headers=_bearer(),
        )
        body = resp.get_json()
        assert body['total'] == 2
        assert len(body['items']) == 1

        resp2 = client.get(
            '/api/super-admin/organizations?limit=1&offset=1',
            headers=_bearer(),
        )
        body2 = resp2.get_json()
        assert body2['total'] == 2
        assert len(body2['items']) == 1
        # Different page should return the other org
        assert body['items'][0]['id'] != body2['items'][0]['id']


# ─── Detail endpoint ────────────────────────────────────────────────────────

class TestDetail:
    def test_returns_full_detail(self, client, admin_auth):
        with patch('routes.super_admin._clerk_email_for', return_value='m@example.com'):
            resp = client.get(
                f'/api/super-admin/organizations/{ORG_A}',
                headers=_bearer(),
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['organization']['slug'] == 'kings-academy'
        assert body['billing']['plan'] == 'growth'
        assert len(body['members']) == 2
        assert all(m['email'] == 'm@example.com' for m in body['members'])
        assert body['audit'] == []

    def test_missing_returns_404(self, client, admin_auth):
        resp = client.get(
            '/api/super-admin/organizations/does-not-exist',
            headers=_bearer(),
        )
        assert resp.status_code == 404

    def test_clerk_failure_does_not_break_detail(self, client, admin_auth):
        with patch('routes.super_admin._clerk_email_for', return_value=None):
            resp = client.get(
                f'/api/super-admin/organizations/{ORG_A}',
                headers=_bearer(),
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert all(m['email'] is None for m in body['members'])


# ─── Suspend / unsuspend ────────────────────────────────────────────────────

class TestSuspendUnsuspend:
    def test_suspend_requires_reason(self, client, admin_auth):
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/suspend',
            json={},
            headers=_bearer(),
        )
        assert resp.status_code == 400

    def test_suspend_rejects_short_reason(self, client, admin_auth):
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/suspend',
            json={'reason': 'ab'},
            headers=_bearer(),
        )
        assert resp.status_code == 400

    def test_suspend_writes_status_and_audit(self, client, admin_auth, supabase_store):
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/suspend',
            json={'reason': 'non-payment'},
            headers=_bearer(),
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['status'] == 'suspended'
        assert body['prior_status'] == 'active'
        assert body['idempotent'] is False

        org_row = next(o for o in supabase_store.tables['organizations'] if o['id'] == ORG_A)
        assert org_row['status'] == 'suspended'

        audit_rows = [
            row
            for table, rows in supabase_store.inserts
            if table == 'platform_admin_audit_log'
            for row in rows
        ]
        actions = [r['action'] for r in audit_rows]
        assert 'suspend_org' in actions
        suspend_audit = next(r for r in audit_rows if r['action'] == 'suspend_org')
        assert suspend_audit['payload']['reason'] == 'non-payment'
        assert suspend_audit['payload']['prior_status'] == 'active'
        assert suspend_audit['target_type'] == 'organization'
        assert suspend_audit['target_id'] == ORG_A

    def test_suspend_idempotent(self, client, admin_auth, supabase_store):
        # First suspend.
        client.post(
            f'/api/super-admin/organizations/{ORG_A}/suspend',
            json={'reason': 'non-payment'},
            headers=_bearer(),
        )
        # Second suspend — still 200, but no second write to organizations.
        updates_before = len([u for u in supabase_store.updates if u[0] == 'organizations'])
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/suspend',
            json={'reason': 'still non-payment'},
            headers=_bearer(),
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['status'] == 'suspended'
        assert body['idempotent'] is True
        updates_after = len([u for u in supabase_store.updates if u[0] == 'organizations'])
        # No new write to organizations.
        assert updates_after == updates_before

    def test_unsuspend_resets_status_and_audits(self, client, admin_auth, supabase_store):
        # First suspend, then unsuspend.
        client.post(
            f'/api/super-admin/organizations/{ORG_A}/suspend',
            json={'reason': 'non-payment'},
            headers=_bearer(),
        )
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/unsuspend',
            json={'reason': 'paid in full'},
            headers=_bearer(),
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['status'] == 'active'
        assert body['prior_status'] == 'suspended'

        org_row = next(o for o in supabase_store.tables['organizations'] if o['id'] == ORG_A)
        assert org_row['status'] == 'active'

        actions = [
            row['action']
            for table, rows in supabase_store.inserts
            if table == 'platform_admin_audit_log'
            for row in rows
        ]
        assert 'unsuspend_org' in actions

    def test_unsuspend_requires_reason(self, client, admin_auth):
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/unsuspend',
            json={'reason': 'ok'},
            headers=_bearer(),
        )
        assert resp.status_code == 400

    def test_suspend_missing_org_returns_404(self, client, admin_auth):
        resp = client.post(
            '/api/super-admin/organizations/does-not-exist/suspend',
            json={'reason': 'gone'},
            headers=_bearer(),
        )
        assert resp.status_code == 404


# ─── Promote ────────────────────────────────────────────────────────────────

class TestPromote:
    def test_promote_member_to_owner(self, client, admin_auth, supabase_store):
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/promote',
            json={'user_id': 'user_member_a', 'reason': 'incident handoff'},
            headers=_bearer(),
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['role'] == 'owner'
        assert body['prior_role'] == 'teacher'

        # The member row should now be owner.
        member = next(
            m for m in supabase_store.tables['organization_members']
            if m['user_id'] == 'user_member_a' and m['organization_id'] == ORG_A
        )
        assert member['role'] == 'owner'

        # Existing owner should NOT be demoted.
        prior_owner = next(
            m for m in supabase_store.tables['organization_members']
            if m['user_id'] == 'user_owner_a' and m['organization_id'] == ORG_A
        )
        assert prior_owner['role'] == 'owner'

        actions = [
            row['action']
            for table, rows in supabase_store.inserts
            if table == 'platform_admin_audit_log'
            for row in rows
        ]
        assert 'promote_org_member' in actions

    def test_promote_non_member_returns_400(self, client, admin_auth):
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/promote',
            json={'user_id': 'user_not_a_member', 'reason': 'manual fix'},
            headers=_bearer(),
        )
        assert resp.status_code == 400

    def test_promote_requires_user_id(self, client, admin_auth):
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/promote',
            json={'reason': 'manual fix'},
            headers=_bearer(),
        )
        assert resp.status_code == 400

    def test_promote_requires_reason(self, client, admin_auth):
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/promote',
            json={'user_id': 'user_member_a'},
            headers=_bearer(),
        )
        assert resp.status_code == 400


# ─── Impersonation guard ────────────────────────────────────────────────────

class TestImpersonationGuard:
    def test_writes_blocked_with_impersonation_cookie(self, client, admin_auth):
        """The global before_request hook already covers this — one assertion is enough."""
        client.set_cookie('chesster_impersonation', 'session-id', path='/')
        resp = client.post(
            f'/api/super-admin/organizations/{ORG_A}/suspend',
            json={'reason': 'should not pass'},
            headers=_bearer(),
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body['reason'] == 'impersonation_active'
