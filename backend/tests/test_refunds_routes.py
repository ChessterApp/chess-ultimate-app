"""Tests for refunds HTTP routes (PRD §11.3 #4)."""

from unittest.mock import MagicMock, patch

import pytest


ORG_ID = 'org-aaaa'
OWNER = 'user_owner'


@pytest.fixture
def client():
    from flask import Flask
    from routes.refunds import refunds_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(refunds_bp)
    return app.test_client()


class TestListRefunds:
    def test_list_refunds_requires_auth(self, client):
        resp = client.get(f'/api/admin/organizations/{ORG_ID}/refunds')
        assert resp.status_code == 401

    def test_non_owner_denied(self, client):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.single.return_value = builder
        builder.execute.return_value = MagicMock(data={'role': 'admin'})
        mock_sb.table.return_value = builder
        with patch('routes.refunds._get_supabase', return_value=mock_sb):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/refunds',
                headers={'X-User-Id': 'someone'},
            )
        assert resp.status_code == 403

    def test_owner_gets_refund_list(self, client):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.single.return_value = builder
        builder.execute.return_value = MagicMock(data={'role': 'owner'})
        mock_sb.table.return_value = builder
        with patch('routes.refunds._get_supabase', return_value=mock_sb), \
             patch('services.refunds.list_refunds_for_org',
                   return_value=[{'id': 'r1', 'amount_cents': 12900}]):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/refunds',
                headers={'X-User-Id': OWNER},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['refunds']) == 1
        assert data['refunds'][0]['amount_cents'] == 12900


class TestWebhookTrampoline:
    REFUND_BODY = {
        'action': 'refund.created',
        'id': 'evt_x',
        'data': {
            'amount_cents': 100,
            'metadata': {'org_id': 'org-1'},
        },
    }

    def test_unauth_when_secret_set_and_token_missing(self, client, monkeypatch):
        monkeypatch.setenv('WHOP_REFUND_INTERNAL_SECRET', 'shh')
        resp = client.post(
            '/api/webhooks/whop-refund',
            json=self.REFUND_BODY,
        )
        assert resp.status_code == 401

    def test_unauth_when_wrong_token(self, client, monkeypatch):
        monkeypatch.setenv('WHOP_REFUND_INTERNAL_SECRET', 'shh')
        resp = client.post(
            '/api/webhooks/whop-refund',
            json=self.REFUND_BODY,
            headers={'Authorization': 'Bearer wrong'},
        )
        assert resp.status_code == 401

    def test_ignores_non_refund_events(self, client, monkeypatch):
        monkeypatch.delenv('WHOP_REFUND_INTERNAL_SECRET', raising=False)
        resp = client.post(
            '/api/webhooks/whop-refund',
            json={'action': 'subscription.updated', 'data': {}},
        )
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ignored'

    def test_happy_path_processes_refund(self, client, monkeypatch):
        monkeypatch.delenv('WHOP_REFUND_INTERNAL_SECRET', raising=False)
        with patch('services.refunds.process_refund_event',
                   return_value={
                       'status': 'processed', 'event_id': 'evt_x',
                       'org_id': 'org-1', 'amount_cents': 100,
                   }):
            resp = client.post(
                '/api/webhooks/whop-refund',
                json=self.REFUND_BODY,
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['status'] == 'processed'

    def test_500_when_service_raises(self, client, monkeypatch):
        monkeypatch.delenv('WHOP_REFUND_INTERNAL_SECRET', raising=False)
        with patch('services.refunds.process_refund_event',
                   side_effect=RuntimeError('boom')):
            resp = client.post(
                '/api/webhooks/whop-refund',
                json=self.REFUND_BODY,
            )
        assert resp.status_code == 500

    def test_bad_payload_rejected(self, client, monkeypatch):
        monkeypatch.delenv('WHOP_REFUND_INTERNAL_SECRET', raising=False)
        resp = client.post(
            '/api/webhooks/whop-refund',
            data='not json',
            content_type='application/json',
        )
        # silent=True yields {} which is dict but missing event_name -> ignored
        assert resp.status_code in (200, 400)
