"""Tests for the atomic bulk-invite endpoint (PRD §11.2 #7 — Phase 2).

POST /api/admin/organizations/<id>/invites/bulk
"""

import pytest
from unittest.mock import patch, MagicMock


ORG_ID = 'org-bulk-1234'
ADMIN_USER_ID = 'user_admin_director'


@pytest.fixture
def client():
    from flask import Flask
    from routes.admin import admin_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(admin_bp)
    return app.test_client()


def _make_supabase_mock(existing_invite_emails: list[str] | None = None):
    """Build a mock supabase client that:
       1) returns the given existing invite rows on a SELECT against
          organization_members,
       2) records all upsert() calls on a list we return alongside.
    """
    existing_invite_emails = existing_invite_emails or []
    upsert_calls: list[list[dict]] = []

    select_builder = MagicMock()
    select_builder.select.return_value = select_builder
    select_builder.eq.return_value = select_builder
    select_builder.execute.return_value = MagicMock(
        data=[{'user_id': f'invite:{e}'} for e in existing_invite_emails],
    )

    upsert_builder = MagicMock()

    def fake_upsert(rows, **_kwargs):
        upsert_calls.append(rows)
        return upsert_builder
    upsert_builder.execute.return_value = MagicMock(data=[])

    table_calls = []

    def fake_table(_name):
        table_calls.append(_name)
        # Return a fresh chained mock per call but only the first one is the
        # SELECT path; later calls (upsert) need the upsert mock.
        m = MagicMock()
        m.select = select_builder.select
        m.upsert = MagicMock(side_effect=fake_upsert)
        return m

    sb = MagicMock()
    sb.table.side_effect = fake_table
    return sb, upsert_calls


class TestBulkInvite:
    def test_rejects_when_invites_missing(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/invites/bulk',
                json={'invites': []},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 400

    def test_accepts_under_cap_atomic_upsert(self, client):
        sb, upserts = _make_supabase_mock()
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('services.tier_quota.get_org_plan', return_value='growth'), \
             patch('services.tier_quota.get_seat_limit', return_value=100), \
             patch('services.tier_quota.get_current_seat_count', return_value=10), \
             patch('services.email.send_invite_email', return_value=True):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/invites/bulk',
                json={'invites': [
                    {'email': 'a@x.com', 'role': 'student'},
                    {'email': 'b@x.com', 'role': 'student'},
                ]},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 201
            body = resp.get_json()
            assert len(body['accepted']) == 2
            assert body['rejected'] == []
            assert body['remaining_seats'] == 88
            # All accepted rows go through a single upsert call (atomic).
            assert len(upserts) == 1
            assert len(upserts[0]) == 2

    def test_partial_import_on_tier_cap(self, client):
        sb, upserts = _make_supabase_mock()
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('services.tier_quota.get_org_plan', return_value='starter'), \
             patch('services.tier_quota.get_seat_limit', return_value=25), \
             patch('services.tier_quota.get_current_seat_count', return_value=23), \
             patch('services.email.send_invite_email', return_value=True):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/invites/bulk',
                json={'invites': [
                    {'email': f'kid{i}@x.com'} for i in range(10)
                ]},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            # Never 402 — partial success.
            assert resp.status_code == 201
            body = resp.get_json()
            assert len(body['accepted']) == 2  # remaining = 25-23 = 2
            assert len(body['rejected']) == 8
            assert all(r['reason'] == 'tier_cap' for r in body['rejected'])
            assert body['remaining_seats'] == 0

    def test_rejects_invalid_emails_and_dedupes(self, client):
        sb, upserts = _make_supabase_mock(existing_invite_emails=['EXISTING@X.COM'])
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('services.tier_quota.get_org_plan', return_value='growth'), \
             patch('services.tier_quota.get_seat_limit', return_value=100), \
             patch('services.tier_quota.get_current_seat_count', return_value=0), \
             patch('services.email.send_invite_email', return_value=True):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/invites/bulk',
                json={'invites': [
                    {'email': 'not-an-email'},
                    {'email': 'fine@x.com'},
                    {'email': 'FINE@X.COM'},       # in-payload dupe
                    {'email': 'existing@x.com'},   # pre-existing
                ]},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 201
            body = resp.get_json()
            assert len(body['accepted']) == 1
            reasons = {r['reason'] for r in body['rejected']}
            assert 'invalid_email' in reasons
            assert 'duplicate' in reasons
            assert 'already_member' in reasons

    def test_enterprise_unlimited_seats(self, client):
        sb, upserts = _make_supabase_mock()
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('services.tier_quota.get_org_plan', return_value='enterprise'), \
             patch('services.tier_quota.get_seat_limit', return_value=None), \
             patch('services.tier_quota.get_current_seat_count', return_value=10_000), \
             patch('services.email.send_invite_email', return_value=True):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/invites/bulk',
                json={'invites': [
                    {'email': f'k{i}@x.com'} for i in range(5)
                ]},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 201
            body = resp.get_json()
            assert len(body['accepted']) == 5
            assert body['remaining_seats'] is None

    def test_invalid_role_rejected(self, client):
        sb, upserts = _make_supabase_mock()
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('services.tier_quota.get_org_plan', return_value='growth'), \
             patch('services.tier_quota.get_seat_limit', return_value=100), \
             patch('services.tier_quota.get_current_seat_count', return_value=0), \
             patch('services.email.send_invite_email', return_value=True):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/invites/bulk',
                json={'invites': [
                    {'email': 'kid@x.com', 'role': 'overlord'},
                ]},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['accepted'] == []
            assert body['rejected'][0]['reason'] == 'invalid_role'
