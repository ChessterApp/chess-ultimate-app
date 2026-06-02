"""
Tests for the Phase-4 idempotency rules in routes/webhooks.py.

Cover three cases for organization.created:
  1. A row with the same clerk_org_id already exists → confirmation echo,
     no duplicate insert, fields refreshed in-place.
  2. A row with the same slug exists but no clerk_org_id → Clerk id is
     adopted onto the row.
  3. Neither match → fall back to the original upsert path.

And the same matching contract for organizationMembership.created.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from unittest.mock import patch


@pytest.fixture
def app():
    from flask import Flask
    from routes.webhooks import webhooks_bp
    test_app = Flask(__name__)
    test_app.register_blueprint(webhooks_bp)
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


def _sign_payload(payload: bytes, secret: str) -> dict:
    svix_id = 'msg_test_idempotent'
    svix_timestamp = str(int(time.time()))
    raw = secret[6:] if secret.startswith('whsec_') else secret
    secret_bytes = base64.b64decode(raw)
    signed = f'{svix_id}.{svix_timestamp}.'.encode() + payload
    sig = hmac.new(secret_bytes, signed, hashlib.sha256).digest()
    return {
        'svix-id': svix_id,
        'svix-timestamp': svix_timestamp,
        'svix-signature': 'v1,' + base64.b64encode(sig).decode(),
    }


SECRET = 'whsec_' + base64.b64encode(b'testsecret').decode()


# ─── In-memory Supabase mock ────────────────────────────────────────────────

class _Result:
    def __init__(self, data=None):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._eq: list[tuple[str, object]] = []
        self._pending_action = None
        self._pending_payload = None

    def select(self, *args, **kwargs):
        return self

    def insert(self, payload, **kwargs):
        rows = payload if isinstance(payload, list) else [payload]
        for row in rows:
            row.setdefault('id', f'fake-{len(self._store.tables.get(self._table, []))}')
            self._store.tables.setdefault(self._table, []).append(row)
        self._store.inserts.append((self._table, rows))
        return _StaticResult(rows)

    def upsert(self, payload, on_conflict=None, **kwargs):
        rows = payload if isinstance(payload, list) else [payload]
        self._store.upserts.append((self._table, rows))
        conflict_cols = (on_conflict or '').split(',')
        existing = self._store.tables.setdefault(self._table, [])
        for row in rows:
            match = None
            for cand in existing:
                if all(cand.get(c) == row.get(c) for c in conflict_cols if c):
                    match = cand
                    break
            if match:
                match.update(row)
            else:
                row.setdefault('id', f'fake-{len(existing)}')
                existing.append(row)
        return _StaticResult(rows)

    def update(self, payload, **kwargs):
        self._pending_action = 'update'
        self._pending_payload = payload
        return self

    def delete(self, **kwargs):
        self._pending_action = 'delete'
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def single(self):
        return self

    def execute(self):
        rows = list(self._store.tables.get(self._table, []))
        for col, val in self._eq:
            rows = [r for r in rows if r.get(col) == val]

        if self._pending_action == 'update':
            for row in rows:
                row.update(self._pending_payload or {})
            self._store.updates.append((self._table, self._pending_payload, list(self._eq)))
            return _Result(data=rows)

        if self._pending_action == 'delete':
            table_rows = self._store.tables.get(self._table, [])
            self._store.tables[self._table] = [r for r in table_rows if r not in rows]
            return _Result(data=[])

        return _Result(data=rows)


class _StaticResult:
    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return _Result(data=self._rows)


class _SupabaseMock:
    def __init__(self, initial=None):
        self.tables = dict(initial or {})
        self.inserts = []
        self.upserts = []
        self.updates = []

    def table(self, name):
        return _Query(self, name)


def _post(client, event: dict, mock_supabase: _SupabaseMock):
    payload = json.dumps(event).encode()
    headers = _sign_payload(payload, SECRET)
    with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', SECRET), \
         patch('routes.webhooks._get_supabase', return_value=mock_supabase):
        return client.post(
            '/api/webhooks/clerk',
            data=payload,
            content_type='application/json',
            headers=headers,
        )


# ─── Organization idempotency ───────────────────────────────────────────────

class TestOrganizationCreatedIdempotency:
    def test_existing_clerk_org_id_is_confirmation_echo(self, client):
        supabase = _SupabaseMock(initial={
            'organizations': [
                {'id': 'row-1', 'slug': 'acme', 'name': 'Old name',
                 'clerk_org_id': 'org_existing', 'status': 'active'},
            ],
        })
        event = {
            'type': 'organization.created',
            'data': {
                'id': 'org_existing',
                'slug': 'acme',
                'name': 'New name',
                'image_url': 'https://example.com/new.png',
            },
        }
        resp = _post(client, event, supabase)
        assert resp.status_code == 200
        # No new row was inserted.
        rows = supabase.tables['organizations']
        assert len(rows) == 1
        # Fields refreshed in-place.
        assert rows[0]['name'] == 'New name'
        assert rows[0]['logo_url'] == 'https://example.com/new.png'
        assert rows[0]['clerk_org_id'] == 'org_existing'
        # No upsert was called.
        assert not supabase.upserts

    def test_match_by_slug_adopts_clerk_id(self, client):
        supabase = _SupabaseMock(initial={
            'organizations': [
                {'id': 'row-1', 'slug': 'acme', 'name': 'Acme',
                 'clerk_org_id': None, 'status': 'active'},
            ],
        })
        event = {
            'type': 'organization.created',
            'data': {
                'id': 'org_fresh',
                'slug': 'acme',
                'name': 'Acme',
                'image_url': None,
            },
        }
        resp = _post(client, event, supabase)
        assert resp.status_code == 200
        rows = supabase.tables['organizations']
        assert len(rows) == 1
        assert rows[0]['clerk_org_id'] == 'org_fresh'
        # No upsert was called — adoption used UPDATE.
        assert not supabase.upserts

    def test_no_match_falls_back_to_upsert(self, client):
        supabase = _SupabaseMock(initial={'organizations': []})
        event = {
            'type': 'organization.created',
            'data': {
                'id': 'org_new',
                'slug': 'brand-new',
                'name': 'Brand New',
                'image_url': None,
            },
        }
        resp = _post(client, event, supabase)
        assert resp.status_code == 200
        assert supabase.upserts
        upserted = supabase.upserts[0][1]
        # Single dict or list; normalize.
        if isinstance(upserted, list):
            upserted = upserted[0]
        assert upserted['slug'] == 'brand-new'
        assert upserted['clerk_org_id'] == 'org_new'


# ─── Membership idempotency ────────────────────────────────────────────────

class TestMembershipCreatedIdempotency:
    def test_resolves_org_by_clerk_id_first(self, client):
        supabase = _SupabaseMock(initial={
            'organizations': [
                {'id': 'row-by-clerk', 'slug': 'wrong-slug',
                 'clerk_org_id': 'org_target', 'status': 'active'},
                {'id': 'row-by-slug', 'slug': 'right-slug',
                 'clerk_org_id': None, 'status': 'active'},
            ],
            'organization_members': [],
        })
        event = {
            'type': 'organizationMembership.created',
            'data': {
                'organization': {'id': 'org_target', 'slug': 'right-slug'},
                'public_user_data': {'user_id': 'user_42'},
                'role': 'basic_member',
            },
        }
        resp = _post(client, event, supabase)
        assert resp.status_code == 200
        # The member should be attached to the clerk-id match, not the slug.
        assert supabase.upserts
        upserted = supabase.upserts[0][1]
        if isinstance(upserted, list):
            upserted = upserted[0]
        assert upserted['organization_id'] == 'row-by-clerk'

    def test_falls_back_to_slug_match(self, client):
        supabase = _SupabaseMock(initial={
            'organizations': [
                {'id': 'row-by-slug', 'slug': 'only-slug',
                 'clerk_org_id': None, 'status': 'active'},
            ],
            'organization_members': [],
        })
        event = {
            'type': 'organizationMembership.created',
            'data': {
                # No id this time
                'organization': {'slug': 'only-slug'},
                'public_user_data': {'user_id': 'user_77'},
                'role': 'org:admin',
            },
        }
        resp = _post(client, event, supabase)
        assert resp.status_code == 200
        assert supabase.upserts
        upserted = supabase.upserts[0][1]
        if isinstance(upserted, list):
            upserted = upserted[0]
        assert upserted['organization_id'] == 'row-by-slug'
        assert upserted['user_id'] == 'user_77'
        assert upserted['role'] == 'admin'

    def test_repeated_membership_webhook_is_noop(self, client):
        """Same (org, user) twice should leave a single member row."""
        supabase = _SupabaseMock(initial={
            'organizations': [
                {'id': 'org-row', 'slug': 'school',
                 'clerk_org_id': 'org_clerk', 'status': 'active'},
            ],
            'organization_members': [
                {'id': 'existing-membership',
                 'organization_id': 'org-row',
                 'user_id': 'user_repeat',
                 'role': 'student'},
            ],
        })
        event = {
            'type': 'organizationMembership.created',
            'data': {
                'organization': {'id': 'org_clerk', 'slug': 'school'},
                'public_user_data': {'user_id': 'user_repeat'},
                'role': 'basic_member',
            },
        }
        resp = _post(client, event, supabase)
        assert resp.status_code == 200
        # Still one row for (org, user).
        members = [
            m for m in supabase.tables['organization_members']
            if m['organization_id'] == 'org-row' and m['user_id'] == 'user_repeat'
        ]
        assert len(members) == 1
