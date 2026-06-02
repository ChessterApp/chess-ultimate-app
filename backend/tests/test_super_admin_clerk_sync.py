"""
Tests for the Phase-4 Clerk-sync endpoints on the super-admin blueprint.

Covers:
  - POST /api/super-admin/organizations           — create + Clerk sync
  - POST /api/super-admin/schools/<id>/sync-clerk — manual backfill

Verifies fail-soft behavior when Clerk returns 5xx.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.clerk_client import ClerkAPIError


ADMIN_CLERK_ID = 'user_super_admin_1'
ADMIN_RECORD = {
    'id': ADMIN_CLERK_ID,
    'public_metadata': {'platform_role': 'super_admin'},
    'two_factor_enabled': True,
    'first_name': 'Alex',
    'last_name': 'Admin',
    'primary_email_address_id': 'email_1',
    'email_addresses': [{'id': 'email_1', 'email_address': 'alex@chesster.io'}],
}

ORG_UNSYNCED_ID = 'org-unsynced'
ORG_SYNCED_ID = 'org-synced'


# ─── Recording Supabase mock ────────────────────────────────────────────────

class _Result:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, store, table_name):
        self._store = store
        self._table = table_name
        self._eq_filters: list[tuple[str, object]] = []

    def select(self, *args, count=None, **kwargs):
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

    def in_(self, *args, **kwargs):
        return self

    def or_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def single(self):
        return self

    def execute(self):
        rows = list(self._store.tables.get(self._table, []))
        for col, val in self._eq_filters:
            rows = [r for r in rows if r.get(col) == val]
        return _Result(data=rows, count=len(rows))


class _StaticResult:
    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return _Result(data=self._rows, count=len(self._rows))


class _SupabaseMock:
    def __init__(self, initial=None):
        self.tables = dict(initial or {})
        self.inserts = []
        self.upserts = []
        self.updates = []

    def table(self, name):
        return _Query(self, name)


def _seed():
    return {
        'organizations': [
            {
                'id': ORG_UNSYNCED_ID,
                'slug': 'unsynced-org',
                'name': 'Unsynced Org',
                'status': 'trial',
                'clerk_org_id': None,
            },
            {
                'id': ORG_SYNCED_ID,
                'slug': 'synced-org',
                'name': 'Synced Org',
                'status': 'active',
                'clerk_org_id': 'org_existing_clerk',
            },
        ],
        'organization_members': [
            {'id': 'm-1', 'organization_id': ORG_UNSYNCED_ID,
             'user_id': 'user_owner_x', 'role': 'owner'},
            {'id': 'm-2', 'organization_id': ORG_UNSYNCED_ID,
             'user_id': 'invite:bob@example.com', 'role': 'student'},
            {'id': 'm-3', 'organization_id': ORG_UNSYNCED_ID,
             'user_id': 'user_teacher_x', 'role': 'teacher'},
        ],
        'platform_admin_audit_log': [],
    }


@pytest.fixture
def supabase_store():
    return _SupabaseMock(initial=_seed())


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


# ─── POST /organizations (create + Clerk sync) ──────────────────────────────

class TestCreateOrganization:
    def test_create_calls_clerk_and_persists_id(self, client, admin_auth, supabase_store):
        mock_clerk = patch(
            'routes.super_admin.get_clerk_client',
            return_value=_FakeClerk(
                create_org_result={'id': 'org_brand_new'},
            ),
        )
        with mock_clerk:
            resp = client.post(
                '/api/super-admin/organizations',
                json={'name': 'New School', 'slug': 'new-school',
                      'owner_user_id': 'user_owner_new'},
                headers=_bearer(),
            )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['clerk_synced'] is True
        assert body['organization']['clerk_org_id'] == 'org_brand_new'

        new_org = next(
            r for r in supabase_store.tables['organizations']
            if r['slug'] == 'new-school'
        )
        assert new_org['clerk_org_id'] == 'org_brand_new'

    def test_create_fail_soft_when_clerk_500s(self, client, admin_auth, supabase_store):
        mock_clerk = patch(
            'routes.super_admin.get_clerk_client',
            return_value=_FakeClerk(
                create_org_error=ClerkAPIError(500, {'error': 'boom'}),
            ),
        )
        with mock_clerk:
            resp = client.post(
                '/api/super-admin/organizations',
                json={'name': 'Hiccup', 'slug': 'hiccup'},
                headers=_bearer(),
            )
        # Org still created, just unsynced.
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['clerk_synced'] is False
        new_org = next(
            r for r in supabase_store.tables['organizations']
            if r['slug'] == 'hiccup'
        )
        # Either NULL or never set is acceptable.
        assert not new_org.get('clerk_org_id')

    def test_requires_name_and_slug(self, client, admin_auth):
        resp = client.post(
            '/api/super-admin/organizations',
            json={'name': 'Only name'},
            headers=_bearer(),
        )
        assert resp.status_code == 400


# ─── POST /schools/<id>/sync-clerk (manual backfill) ────────────────────────

class TestSyncOrgToClerk:
    def test_sync_creates_clerk_org_for_unsynced_row(self, client, admin_auth, supabase_store):
        fake = _FakeClerk(
            create_org_result={'id': 'org_freshly_synced'},
        )
        with patch('routes.super_admin.get_clerk_client', return_value=fake):
            resp = client.post(
                f'/api/super-admin/schools/{ORG_UNSYNCED_ID}/sync-clerk',
                headers=_bearer(),
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['already_synced'] is False
        assert body['clerk_org_id'] == 'org_freshly_synced'
        assert body['members_synced'] == 2  # owner + teacher; invite:* skipped
        assert body['failed_memberships'] == []

        # Org row now has the id.
        org_row = next(r for r in supabase_store.tables['organizations']
                       if r['id'] == ORG_UNSYNCED_ID)
        assert org_row['clerk_org_id'] == 'org_freshly_synced'

        # Memberships were forwarded with mapped roles.
        sent = fake.create_membership_calls
        roles_by_user = {c['user_id']: c['role'] for c in sent}
        assert roles_by_user['user_owner_x'] == 'admin'  # owner → admin
        assert roles_by_user['user_teacher_x'] == 'basic_member'
        # Placeholder row was skipped.
        assert 'invite:bob@example.com' not in roles_by_user

    def test_sync_is_idempotent_on_already_synced(self, client, admin_auth):
        # No need to mock Clerk — sync should short-circuit.
        with patch('routes.super_admin.get_clerk_client',
                   return_value=_FakeClerk()):
            resp = client.post(
                f'/api/super-admin/schools/{ORG_SYNCED_ID}/sync-clerk',
                headers=_bearer(),
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['already_synced'] is True
        assert body['clerk_org_id'] == 'org_existing_clerk'

    def test_sync_returns_502_when_clerk_500s(self, client, admin_auth):
        fake = _FakeClerk(create_org_error=ClerkAPIError(500, {'error': 'down'}))
        with patch('routes.super_admin.get_clerk_client', return_value=fake):
            resp = client.post(
                f'/api/super-admin/schools/{ORG_UNSYNCED_ID}/sync-clerk',
                headers=_bearer(),
            )
        assert resp.status_code == 502
        body = resp.get_json()
        assert body['clerk_synced'] is False

    def test_sync_404_on_missing_org(self, client, admin_auth):
        with patch('routes.super_admin.get_clerk_client',
                   return_value=_FakeClerk()):
            resp = client.post(
                '/api/super-admin/schools/does-not-exist/sync-clerk',
                headers=_bearer(),
            )
        assert resp.status_code == 404

    def test_sync_reports_failed_memberships(self, client, admin_auth, supabase_store):
        fake = _FakeClerk(
            create_org_result={'id': 'org_partially_synced'},
            membership_errors={'user_teacher_x': ClerkAPIError(500, 'boom')},
        )
        with patch('routes.super_admin.get_clerk_client', return_value=fake):
            resp = client.post(
                f'/api/super-admin/schools/{ORG_UNSYNCED_ID}/sync-clerk',
                headers=_bearer(),
            )
        assert resp.status_code == 200
        body = resp.get_json()
        # clerk_org_id stored even though one member failed.
        assert body['clerk_org_id'] == 'org_partially_synced'
        assert body['members_synced'] == 1
        failed_ids = [m['user_id'] for m in body['failed_memberships']]
        assert failed_ids == ['user_teacher_x']

        org_row = next(r for r in supabase_store.tables['organizations']
                       if r['id'] == ORG_UNSYNCED_ID)
        assert org_row['clerk_org_id'] == 'org_partially_synced'


# ─── Helpers ────────────────────────────────────────────────────────────────

class _FakeClerk:
    """Stand-in for ClerkClient with configurable success/error paths."""

    def __init__(
        self,
        create_org_result: dict | None = None,
        create_org_error: ClerkAPIError | None = None,
        membership_errors: dict | None = None,
    ):
        self._create_org_result = create_org_result or {}
        self._create_org_error = create_org_error
        self._membership_errors = membership_errors or {}
        self.create_membership_calls: list[dict] = []

    def create_organization(self, name, slug, created_by_user_id):
        if self._create_org_error:
            raise self._create_org_error
        return self._create_org_result

    def create_membership(self, clerk_org_id, user_id, role):
        self.create_membership_calls.append({
            'clerk_org_id': clerk_org_id, 'user_id': user_id, 'role': role,
        })
        err = self._membership_errors.get(user_id)
        if err:
            raise err
        return {'id': f'omem-{user_id}'}

    def delete_organization(self, clerk_org_id):
        return None

    def delete_membership(self, clerk_org_id, user_id):
        return None

    def update_membership_role(self, clerk_org_id, user_id, role):
        return {}
