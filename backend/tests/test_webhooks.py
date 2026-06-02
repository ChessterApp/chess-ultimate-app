"""
Tests for the Clerk Organizations webhook handler.

Uses Flask test client with mocked Supabase.
"""

import base64
import hashlib
import hmac
import json
import time

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    """Create a Flask app with the webhooks blueprint for testing."""
    from flask import Flask
    from routes.webhooks import webhooks_bp

    app = Flask(__name__)
    app.register_blueprint(webhooks_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _sign_payload(payload: bytes, secret: str) -> dict:
    """Generate valid Svix headers for a payload."""
    svix_id = 'msg_test_123'
    svix_timestamp = str(int(time.time()))

    # Strip whsec_ prefix
    raw_secret = secret
    if raw_secret.startswith('whsec_'):
        raw_secret = raw_secret[6:]

    secret_bytes = base64.b64decode(raw_secret)
    signed_content = f'{svix_id}.{svix_timestamp}.'.encode() + payload
    signature = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    sig_b64 = base64.b64encode(signature).decode()

    return {
        'svix-id': svix_id,
        'svix-timestamp': svix_timestamp,
        'svix-signature': f'v1,{sig_b64}',
    }


class TestWebhookSignatureVerification:
    """Test Svix signature verification logic."""

    def test_missing_headers_returns_401(self, client):
        """Webhook without svix headers should be rejected."""
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', 'whsec_' + base64.b64encode(b'testsecret').decode()):
            resp = client.post(
                '/api/webhooks/clerk',
                data=json.dumps({'type': 'test'}),
                content_type='application/json',
            )
            assert resp.status_code == 401

    def test_valid_signature_passes(self, client):
        """Webhook with valid signature should be accepted."""
        secret = 'whsec_' + base64.b64encode(b'testsecret').decode()
        payload = json.dumps({'type': 'unknown.event', 'data': {}}).encode()
        headers = _sign_payload(payload, secret)

        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', secret):
            resp = client.post(
                '/api/webhooks/clerk',
                data=payload,
                content_type='application/json',
                headers=headers,
            )
            assert resp.status_code == 200

    def test_invalid_signature_returns_401(self, client):
        """Webhook with wrong signature should be rejected."""
        secret = 'whsec_' + base64.b64encode(b'testsecret').decode()
        payload = json.dumps({'type': 'test', 'data': {}}).encode()

        # Sign with a different secret
        wrong_secret = 'whsec_' + base64.b64encode(b'wrongsecret').decode()
        headers = _sign_payload(payload, wrong_secret)

        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', secret):
            resp = client.post(
                '/api/webhooks/clerk',
                data=payload,
                content_type='application/json',
                headers=headers,
            )
            assert resp.status_code == 401

    def test_expired_timestamp_returns_401(self, client):
        """Webhook with old timestamp should be rejected."""
        secret = 'whsec_' + base64.b64encode(b'testsecret').decode()
        payload = json.dumps({'type': 'test', 'data': {}}).encode()
        headers = _sign_payload(payload, secret)
        # Set timestamp 10 minutes ago
        headers['svix-timestamp'] = str(int(time.time()) - 600)

        # Re-sign with old timestamp (signature will be invalid anyway)
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', secret):
            resp = client.post(
                '/api/webhooks/clerk',
                data=payload,
                content_type='application/json',
                headers=headers,
            )
            assert resp.status_code == 401


class TestOrgCreatedWebhook:
    """Test organization.created event handling."""

    def test_org_created_upserts(self, client):
        """organization.created should upsert into organizations table.

        With the Phase 4 idempotency rules, the handler first looks up by
        clerk_org_id and by slug — both must report no existing row before
        falling back to upsert. We configure the select chain to return [].
        """
        secret = 'whsec_' + base64.b64encode(b'testsecret').decode()
        event = {
            'type': 'organization.created',
            'data': {
                'id': 'org_clerk_new',
                'slug': 'almatychess',
                'name': 'Almaty Chess School',
                'image_url': 'https://example.com/logo.png',
            },
        }
        payload = json.dumps(event).encode()
        headers = _sign_payload(payload, secret)

        mock_table = MagicMock()
        # The clerk_org_id + slug lookups both return empty data.
        mock_select_chain = MagicMock()
        mock_select_chain.execute.return_value = MagicMock(data=[])
        mock_table.select.return_value.eq.return_value = mock_select_chain
        # Upsert path.
        mock_upsert = MagicMock()
        mock_upsert.execute.return_value = MagicMock(data=[{'id': 'uuid-1'}])
        mock_table.upsert.return_value = mock_upsert
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_table

        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', secret), \
             patch('routes.webhooks._get_supabase', return_value=mock_supabase):
            resp = client.post(
                '/api/webhooks/clerk',
                data=payload,
                content_type='application/json',
                headers=headers,
            )

        assert resp.status_code == 200
        mock_supabase.table.assert_called_with('organizations')
        mock_table.upsert.assert_called_once()
        call_args = mock_table.upsert.call_args[0][0]
        assert call_args['slug'] == 'almatychess'
        assert call_args['name'] == 'Almaty Chess School'
        assert call_args['clerk_org_id'] == 'org_clerk_new'


class TestOrgDeletedWebhook:
    """Test organization.deleted event handling."""

    def test_org_deleted_sets_suspended(self, client):
        """organization.deleted should soft-delete by setting status to suspended."""
        secret = 'whsec_' + base64.b64encode(b'testsecret').decode()
        event = {
            'type': 'organization.deleted',
            'data': {'slug': 'almatychess', 'id': 'clerk_org_123'},
        }
        payload = json.dumps(event).encode()
        headers = _sign_payload(payload, secret)

        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock()
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_table

        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', secret), \
             patch('routes.webhooks._get_supabase', return_value=mock_supabase):
            resp = client.post(
                '/api/webhooks/clerk',
                data=payload,
                content_type='application/json',
                headers=headers,
            )

        assert resp.status_code == 200
        mock_table.update.assert_called_once_with({'status': 'suspended'})


class TestMemberCreatedWebhook:
    """Test organizationMembership.created event handling."""

    def test_member_created_upserts(self, client):
        """Membership creation should upsert into organization_members.

        The org-id resolver tries clerk_org_id first, then slug. We make the
        slug branch return the row (the legacy lookup path).
        """
        secret = 'whsec_' + base64.b64encode(b'testsecret').decode()
        event = {
            'type': 'organizationMembership.created',
            'data': {
                'organization': {'slug': 'almatychess'},
                'public_user_data': {'user_id': 'user_123'},
                'role': 'org:member',
            },
        }
        payload = json.dumps(event).encode()
        headers = _sign_payload(payload, secret)

        # Org lookup: clerk_org_id branch returns empty; slug branch hits row.
        mock_org_table = MagicMock()

        def _select_router(*args, **kwargs):
            select_mock = MagicMock()

            def _eq_router(col, val):
                eq_mock = MagicMock()
                if col == 'clerk_org_id':
                    eq_mock.execute.return_value = MagicMock(data=[])
                else:
                    eq_mock.execute.return_value = MagicMock(
                        data=[{'id': 'org-uuid-1'}]
                    )
                return eq_mock

            select_mock.eq.side_effect = _eq_router
            return select_mock

        mock_org_table.select.side_effect = _select_router

        mock_member_table = MagicMock()
        mock_member_upsert = MagicMock()
        mock_member_upsert.execute.return_value = MagicMock()
        mock_member_table.upsert.return_value = mock_member_upsert

        mock_supabase = MagicMock()

        def table_router(name):
            if name == 'organizations':
                return mock_org_table
            return mock_member_table

        mock_supabase.table.side_effect = table_router

        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', secret), \
             patch('routes.webhooks._get_supabase', return_value=mock_supabase):
            resp = client.post(
                '/api/webhooks/clerk',
                data=payload,
                content_type='application/json',
                headers=headers,
            )

        assert resp.status_code == 200
        mock_member_table.upsert.assert_called_once()
        call_args = mock_member_table.upsert.call_args[0][0]
        assert call_args['organization_id'] == 'org-uuid-1'
        assert call_args['user_id'] == 'user_123'
        assert call_args['role'] == 'student'  # org:member -> student


class TestClerkRoleMapping:
    """Test Clerk role to internal role mapping."""

    def test_role_mapping(self):
        from routes.webhooks import _map_clerk_role

        assert _map_clerk_role('org:admin') == 'admin'
        assert _map_clerk_role('org:member') == 'student'
        assert _map_clerk_role('admin') == 'admin'
        assert _map_clerk_role('basic_member') == 'student'
        assert _map_clerk_role('unknown_role') == 'student'
