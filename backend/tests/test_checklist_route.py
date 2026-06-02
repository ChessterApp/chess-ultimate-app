"""Test for the org checklist endpoint (PRD §11.2 #5)."""

from unittest.mock import patch, MagicMock

import pytest


ORG_ID = 'org-chk-1234'
ADMIN = 'user_admin'


@pytest.fixture
def client():
    from flask import Flask
    from routes.admin import admin_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(admin_bp)
    return app.test_client()


class TestChecklistRoute:
    def test_returns_snapshot_shape(self, client):
        org_row = {
            'id': ORG_ID, 'slug': 'almaty',
            'logo_url': 'https://x', 'primary_color': '#0066ff',
            'secondary_color': '#fff', 'accent_color': '#ffd',
            'custom_domain_status': None, 'email_sender_status': 'active',
            'landing_page_config': {'hero_title': 'Hi'},
            'created_at': '2026-06-01T00:00:00Z',
        }
        members = [
            {'role': 'student'}, {'role': 'student'}, {'role': 'student'},
            {'role': 'teacher'}, {'role': 'owner'},
        ]

        select_chain = MagicMock()
        select_chain.select.return_value = select_chain
        select_chain.eq.return_value = select_chain
        select_chain.single.return_value = select_chain

        org_exec = MagicMock(data=org_row)
        members_exec = MagicMock(data=members)
        # The route calls .single().execute() for org, .execute() for members.
        # Use a side-effect on execute that distinguishes by call order.
        execs = [org_exec, members_exec]
        select_chain.execute = MagicMock(side_effect=execs)
        sb = MagicMock()
        sb.table.return_value = select_chain

        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase', return_value=sb), \
             patch('services.tier_quota.get_org_plan', return_value='pro'):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/checklist',
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['org']['logoUrl'] == 'https://x'
            assert body['org']['emailSenderStatus'] == 'active'
            assert body['org']['plan'] == 'pro'
            assert body['studentCount'] == 3
            assert body['teacherCount'] == 1

    def test_requires_admin(self, client):
        with patch('routes.admin._get_caller_role', return_value='student'), \
             patch('routes.admin._get_supabase'):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/checklist',
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 403
