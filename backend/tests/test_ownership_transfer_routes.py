"""Tests for ownership-transfer HTTP routes."""

from unittest.mock import MagicMock, patch

import pytest


ORG_ID = 'org-aaaa'
OWNER = 'owner-uid'


@pytest.fixture
def client(monkeypatch):
    from flask import Flask
    from routes.ownership_transfer import ownership_transfer_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(ownership_transfer_bp)
    # Block real email sends in route tests
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    return app.test_client()


def _wire_owner_check(role='owner'):
    """Build a supabase mock that returns the given role for the auth check."""
    mock_sb = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.single.return_value = builder
    builder.execute.return_value = MagicMock(data={'role': role} if role else None)
    mock_sb.table.return_value = builder
    return mock_sb


class TestCreateRoute:
    def test_auth_required(self, client):
        resp = client.post(
            f'/api/admin/organizations/{ORG_ID}/ownership-transfers',
            json={'invitee_email': 'a@b.com'},
        )
        assert resp.status_code == 401

    def test_forbidden_for_non_owner(self, client):
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('admin')):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers',
                json={'invitee_email': 'a@b.com'},
                headers={'X-User-Id': 'someone'},
            )
        assert resp.status_code == 403

    def test_missing_email_rejected(self, client):
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('owner')):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers',
                json={},
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 400

    def test_happy_path(self, client):
        fake_row = {
            'id': 't1', 'state': 'invite_pending',
            'token': 'tok-xyz', 'invitee_email': 'a@b.com',
            'expires_at': '2026-06-30T00:00:00+00:00',
            'organization_id': ORG_ID,
        }
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('owner')), \
             patch('services.ownership_transfer.create_transfer',
                   return_value=fake_row):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers',
                json={'invitee_email': 'a@b.com'},
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 201
        assert resp.get_json()['transfer']['state'] == 'invite_pending'


class TestRevokeRoute:
    def test_409_when_already_terminal(self, client):
        from services.ownership_transfer import OwnershipTransferError
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('owner')), \
             patch('services.ownership_transfer.revoke_transfer',
                   side_effect=OwnershipTransferError('invalid_state', 'bad')):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers/t1/revoke',
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 409

    def test_403_forbidden(self, client):
        from services.ownership_transfer import OwnershipTransferError
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('owner')), \
             patch('services.ownership_transfer.revoke_transfer',
                   side_effect=OwnershipTransferError('forbidden', 'no')):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers/t1/revoke',
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 403

    def test_happy_path(self, client):
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('owner')), \
             patch('services.ownership_transfer.revoke_transfer',
                   return_value={'id': 't1', 'state': 'revoked'}):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers/t1/revoke',
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 200
        assert resp.get_json()['transfer']['state'] == 'revoked'


class TestConfirmRoute:
    def test_happy_path(self, client):
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('owner')), \
             patch('services.ownership_transfer.confirm_transfer',
                   return_value={'id': 't1', 'state': 'completed'}):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers/t1/confirm',
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 200
        assert resp.get_json()['transfer']['state'] == 'completed'

    def test_410_when_expired(self, client):
        from services.ownership_transfer import OwnershipTransferError
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('owner')), \
             patch('services.ownership_transfer.confirm_transfer',
                   side_effect=OwnershipTransferError('expired', 'too late')):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers/t1/confirm',
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 410


class TestPublicTokenRoutes:
    def test_lookup_unknown_token_404(self, client):
        with patch('services.ownership_transfer.get_by_token', return_value=None):
            resp = client.get('/api/ownership-transfers/by-token/missing')
        assert resp.status_code == 404

    def test_lookup_hides_internal_id(self, client):
        with patch('services.ownership_transfer.get_by_token',
                   return_value={
                       'id': 'private-id',
                       'organization_id': ORG_ID,
                       'invitee_email': 'a@b.com',
                       'state': 'invite_pending',
                       'expires_at': '2026-07-01T00:00:00+00:00',
                       'token': 'should-not-leak',
                   }):
            resp = client.get('/api/ownership-transfers/by-token/tok-xyz')
        assert resp.status_code == 200
        body = resp.get_json()['transfer']
        assert 'id' not in body
        assert 'token' not in body
        assert body['invitee_email'] == 'a@b.com'

    def test_accept_requires_auth(self, client):
        resp = client.post('/api/ownership-transfers/by-token/tok/accept')
        assert resp.status_code == 401

    def test_accept_happy_path(self, client):
        with patch('services.ownership_transfer.accept_transfer',
                   return_value={'state': 'accepted', 'invitee_user_id': 'u'}):
            resp = client.post(
                '/api/ownership-transfers/by-token/tok/accept',
                headers={'X-User-Id': 'invitee-uid'},
            )
        assert resp.status_code == 200
        assert resp.get_json()['transfer']['state'] == 'accepted'

    def test_accept_expired_returns_410(self, client):
        from services.ownership_transfer import OwnershipTransferError
        with patch('services.ownership_transfer.accept_transfer',
                   side_effect=OwnershipTransferError('expired', 'gone')):
            resp = client.post(
                '/api/ownership-transfers/by-token/tok/accept',
                headers={'X-User-Id': 'invitee-uid'},
            )
        assert resp.status_code == 410

    def test_accept_invalid_state_returns_409(self, client):
        from services.ownership_transfer import OwnershipTransferError
        with patch('services.ownership_transfer.accept_transfer',
                   side_effect=OwnershipTransferError('invalid_state', 'no')):
            resp = client.post(
                '/api/ownership-transfers/by-token/tok/accept',
                headers={'X-User-Id': 'invitee-uid'},
            )
        assert resp.status_code == 409


class TestListRoute:
    def test_returns_list(self, client):
        with patch('routes.ownership_transfer._get_supabase',
                   return_value=_wire_owner_check('owner')), \
             patch('services.ownership_transfer.list_for_org',
                   return_value=[{'id': 't1'}, {'id': 't2'}]):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/ownership-transfers',
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 200
        assert len(resp.get_json()['transfers']) == 2
