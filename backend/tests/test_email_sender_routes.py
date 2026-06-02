"""Tests for the branded-sender domain admin endpoints (PRD §11.2 #4)."""

from unittest.mock import patch, MagicMock

import pytest


ORG_ID = 'org-pro-1234'
ADMIN = 'user_admin_director'


@pytest.fixture
def client():
    from flask import Flask
    from routes.admin import admin_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(admin_bp)
    return app.test_client()


def _mock_supabase_org_select(initial: dict):
    """Build a supabase mock whose `.table().select().eq().single().execute()`
    chain returns {'data': initial}."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.single.return_value = builder
    builder.execute.return_value = MagicMock(data=initial)
    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    update_chain.execute.return_value = MagicMock(data=[])
    builder.update.return_value = update_chain

    sb = MagicMock()
    sb.table.return_value = builder
    return sb, builder, update_chain


class TestEmailSenderGating:
    def test_starter_is_blocked_with_403(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('services.tier_quota.get_org_plan', return_value='starter'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/email-sender',
                json={'domain': 'mail.example.com'},
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 403
            body = resp.get_json()
            assert body['code'] == 'pro_only'

    def test_growth_is_blocked_with_403(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('services.tier_quota.get_org_plan', return_value='growth'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/email-sender',
                json={'domain': 'mail.example.com'},
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 403


class TestAddEmailSender:
    def test_creates_domain_and_persists_state(self, client):
        sb, _, _ = _mock_supabase_org_select({})
        fake_resend = MagicMock()
        fake_resend.create_domain.return_value = {
            'id': 'd_abc', 'status': 'not_started',
            'records': [{'record': 'SPF', 'value': 'v=spf1 ...'}],
        }
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('routes.admin._get_resend_client', return_value=fake_resend), \
             patch('services.tier_quota.get_org_plan', return_value='pro'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/email-sender',
                json={'domain': 'mail.example.com'},
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 201
            body = resp.get_json()
            assert body['domain'] == 'mail.example.com'
            assert body['status'] == 'pending'
            assert body['resend_id'] == 'd_abc'
            assert len(body['records']) == 1

    def test_invalid_domain_rejected(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('services.tier_quota.get_org_plan', return_value='pro'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/email-sender',
                json={'domain': 'not a domain'},
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 400


class TestVerifyEmailSender:
    def test_flips_to_active_on_verified(self, client):
        sb, _, update_chain = _mock_supabase_org_select({
            'email_sender_domain': 'mail.example.com',
            'email_sender_resend_id': 'd_abc',
            'email_sender_status': 'verifying',
        })
        fake_resend = MagicMock()
        fake_resend.verify_domain.return_value = {'id': 'd_abc', 'status': 'verified'}
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('routes.admin._get_resend_client', return_value=fake_resend), \
             patch('services.tier_quota.get_org_plan', return_value='pro'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/email-sender/verify',
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['status'] == 'active'
            # ensure we recorded verified_at
            update_chain.execute.assert_called()

    def test_returns_404_when_no_sender(self, client):
        sb, _, _ = _mock_supabase_org_select({})
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('services.tier_quota.get_org_plan', return_value='pro'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/email-sender/verify',
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 404


class TestRemoveEmailSender:
    def test_idempotent_when_nothing_to_remove(self, client):
        sb, _, _ = _mock_supabase_org_select({})
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('services.tier_quota.get_org_plan', return_value='pro'):
            resp = client.delete(
                f'/api/admin/organizations/{ORG_ID}/email-sender',
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 200
            assert resp.get_json()['status'] == 'removed'
