"""Tests for the Phase-2 polish on the custom-domain flow (PRD §11.2 #2):

  * Vercel error-code → actionable copy table
  * State-machine transitions on add / verify / failed
"""

from unittest.mock import patch, MagicMock

import pytest


ORG_ID = 'org-cd-1234'
ADMIN = 'user_admin'


@pytest.fixture
def client():
    from flask import Flask
    from routes.admin import admin_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(admin_bp)
    return app.test_client()


class TestVercelErrorMessages:
    def test_known_codes_get_actionable_copy(self):
        from routes.admin import vercel_error_to_actionable_message
        assert 'another project' in vercel_error_to_actionable_message(
            'domain_already_in_use', 'raw',
        )
        assert 'VERCEL_TOKEN' in vercel_error_to_actionable_message(
            'not_authorized', 'raw',
        )
        assert 'NS records' in vercel_error_to_actionable_message(
            'forbidden', 'raw',
        )
        assert 'hostname' in vercel_error_to_actionable_message(
            'invalid_domain', 'raw',
        )
        assert 'DNS records' in vercel_error_to_actionable_message(
            'missing_dns', 'raw',
        )
        assert 'HTTPS' in vercel_error_to_actionable_message(
            'invalid_cert_challenge', 'raw',
        )

    def test_unknown_code_falls_back_to_raw_message(self):
        from routes.admin import vercel_error_to_actionable_message
        msg = vercel_error_to_actionable_message('quantum_overflow', 'raw error')
        assert msg == 'raw error'


class TestVercelErrorResponses:
    def test_domain_already_in_use_returns_409_with_friendly_copy(self, client):
        from services.vercel_client import VercelAPIError
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase') as mock_sb, \
             patch('routes.admin._get_vercel_client') as mock_client:
            # No existing rows
            mock_sb.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_client.return_value.add_domain.side_effect = VercelAPIError(
                409, 'domain_already_in_use', 'Domain in use', {},
            )
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'taken.example.com'},
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 409
            body = resp.get_json()
            assert body['code'] == 'domain_already_in_use'
            assert 'another project' in body['error']

    def test_invalid_domain_returns_400(self, client):
        from services.vercel_client import VercelAPIError
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase') as mock_sb, \
             patch('routes.admin._get_vercel_client') as mock_client:
            mock_sb.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_client.return_value.add_domain.side_effect = VercelAPIError(
                400, 'invalid_domain', 'Bad', {},
            )
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'a.example.com'},
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 400
            body = resp.get_json()
            assert 'fully-qualified' in body['error']

    def test_forbidden_returns_403(self, client):
        from services.vercel_client import VercelAPIError
        with patch('routes.admin._get_caller_role', return_value='admin'), \
             patch('routes.admin._get_supabase') as mock_sb, \
             patch('routes.admin._get_vercel_client') as mock_client:
            mock_sb.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_client.return_value.add_domain.side_effect = VercelAPIError(
                403, 'forbidden', 'Forbidden', {},
            )
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/custom-domain',
                json={'domain': 'a.example.com'},
                headers={'X-User-Id': ADMIN},
            )
            assert resp.status_code == 403
