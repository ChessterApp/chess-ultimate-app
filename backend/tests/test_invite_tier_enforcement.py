"""Test tier-quota enforcement on the invite endpoint (PRD §6.3 / §6.4)."""

import pytest
from unittest.mock import patch, MagicMock


ORG_ID = 'org-aaaa-1111'
ADMIN_USER_ID = 'user_admin_director'


@pytest.fixture
def client():
    from flask import Flask
    from routes.admin import admin_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(admin_bp)
    return app.test_client()


class TestInviteTierEnforcement:
    def test_invite_blocked_with_402_when_over_cap(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase'), \
             patch('services.tier_quota.can_invite',
                   return_value=(False, {
                       'code': 'tier_limit_exceeded',
                       'current_count': 100,
                       'seat_cap': 100,
                       'plan': 'growth',
                       'upgrade_url': 'https://chesster.io/admin/billing?upgrade=pro',
                   })):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/members/invite',
                json={'email': 'newkid@example.com', 'role': 'student'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 402
            body = resp.get_json()
            assert body['error'] == 'tier_limit_exceeded'
            assert body['seat_cap'] == 100
            assert body['current_count'] == 100
            assert body['plan'] == 'growth'
            assert 'upgrade_url' in body

    def test_invite_succeeds_when_under_cap(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase') as mock_sb, \
             patch('services.tier_quota.can_invite',
                   return_value=(True, {'plan': 'growth', 'current_count': 50, 'seat_cap': 100})), \
             patch('services.email.send_invite_email', return_value=True):
            # Wire upsert so it doesn't blow up
            builder = MagicMock()
            builder.upsert.return_value = builder
            builder.execute.return_value = MagicMock(data=[])
            mock_sb.return_value.table.return_value = builder

            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/members/invite',
                json={'email': 'kid@example.com', 'role': 'student'},
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 201
            body = resp.get_json()
            assert body['email'] == 'kid@example.com'
