"""Tests for POST /api/admin/organizations/<org_id>/delete-request (PRD §7)."""

from unittest.mock import MagicMock, patch

import pytest


ORG_ID = 'org-11111111-1111-1111-1111-111111111111'
ORG_NAME = 'Almaty Chess Academy'
OWNER_USER_ID = 'user_owner_123'


def _supabase_with_org(name: str = ORG_NAME):
    """Build a tiny supabase mock whose table('organizations').select(..).single().execute()
    returns the org row."""
    def table(_name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.execute.return_value = MagicMock(data={'id': ORG_ID, 'name': name})
        return chain
    sb = MagicMock()
    sb.table.side_effect = table
    return sb


def _supabase_with_no_org():
    def table(_name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.execute.return_value = MagicMock(data=None)
        return chain
    sb = MagicMock()
    sb.table.side_effect = table
    return sb


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


class TestDeleteRequestRoute:
    def test_missing_user_header_401(self, client):
        resp = client.post(
            f'/api/admin/organizations/{ORG_ID}/delete-request',
            json={'confirm_name': ORG_NAME},
        )
        assert resp.status_code == 401

    def test_missing_confirm_name_400(self, client):
        resp = client.post(
            f'/api/admin/organizations/{ORG_ID}/delete-request',
            json={},
            headers={'X-User-Id': OWNER_USER_ID},
        )
        assert resp.status_code == 400

    def test_confirm_name_mismatch_400(self, client):
        with patch('routes.admin._get_supabase', return_value=_supabase_with_org()):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/delete-request',
                json={'confirm_name': 'Wrong School Name'},
                headers={'X-User-Id': OWNER_USER_ID},
            )
            assert resp.status_code == 400
            assert resp.get_json().get('code') == 'confirm_mismatch'

    def test_org_not_found_404(self, client):
        with patch('routes.admin._get_supabase', return_value=_supabase_with_no_org()):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/delete-request',
                json={'confirm_name': ORG_NAME},
                headers={'X-User-Id': OWNER_USER_ID},
            )
            assert resp.status_code == 404

    def test_non_owner_403(self, client):
        with patch('routes.admin._get_supabase', return_value=_supabase_with_org()), \
             patch('services.org_deletion.request_deletion') as mock_req:
            from services.org_deletion import OrgDeletionError
            mock_req.side_effect = OrgDeletionError('forbidden', 'Only owner')
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/delete-request',
                json={'confirm_name': ORG_NAME},
                headers={'X-User-Id': 'user-admin-not-owner'},
            )
            assert resp.status_code == 403
            assert resp.get_json().get('code') == 'forbidden'

    def test_happy_path_200(self, client):
        ts = '2026-06-02T10:00:00+00:00'
        with patch('routes.admin._get_supabase', return_value=_supabase_with_org()), \
             patch('services.org_deletion.request_deletion') as mock_req:
            mock_req.return_value = {
                'ok': True,
                'deletion_requested_at': ts,
                'already_requested': False,
            }
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/delete-request',
                json={'confirm_name': ORG_NAME},
                headers={'X-User-Id': OWNER_USER_ID},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['ok'] is True
            assert body['deletion_requested_at'] == ts
            # Service was called with the route's args
            assert mock_req.called
            kwargs = mock_req.call_args.kwargs
            assert kwargs['org_id'] == ORG_ID
            assert kwargs['requester_user_id'] == OWNER_USER_ID

    def test_requester_email_forwarded_to_service(self, client):
        with patch('routes.admin._get_supabase', return_value=_supabase_with_org()), \
             patch('services.org_deletion.request_deletion') as mock_req:
            mock_req.return_value = {
                'ok': True, 'deletion_requested_at': 'ts', 'already_requested': False,
            }
            client.post(
                f'/api/admin/organizations/{ORG_ID}/delete-request',
                json={'confirm_name': ORG_NAME, 'requester_email': 'who@school.com'},
                headers={'X-User-Id': OWNER_USER_ID},
            )
            assert mock_req.call_args.kwargs['requester_email'] == 'who@school.com'
