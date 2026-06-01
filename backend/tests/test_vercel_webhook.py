"""Tests for the Vercel webhook handler (POST /api/webhooks/vercel).

Covers:
  * Signature verification (valid / invalid / expired timestamp / missing headers).
  * Each event type (domain.verified, domain.cert.issued, domain.cert.failed,
    domain.created, unknown).
  * Idempotency — replaying the same event twice produces the same state.
"""

import hashlib
import hmac
import json
import time

import pytest
from unittest.mock import patch, MagicMock


SECRET = 'super-secret-vercel-key'


@pytest.fixture
def app():
    from flask import Flask
    from routes.webhooks import webhooks_bp
    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(webhooks_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


def _sign(payload: bytes, secret: str = SECRET, ts: int | None = None) -> dict:
    ts = ts if ts is not None else int(time.time())
    sig = hmac.new(secret.encode(), payload, hashlib.sha1).hexdigest()
    return {
        'x-vercel-signature': sig,
        'x-vercel-signature-timestamp': str(ts),
    }


# ── Signature verification ──────────────────────────────────────────────────

class TestVercelSignatureVerification:

    def test_missing_headers_401(self, client):
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET):
            resp = client.post('/api/webhooks/vercel',
                               data=b'{}', content_type='application/json')
        assert resp.status_code == 401

    def test_missing_secret_refuses(self, client):
        payload = json.dumps({'type': 'domain.verified'}).encode()
        headers = _sign(payload)
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', ''):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=headers)
        assert resp.status_code == 401

    def test_invalid_signature_401(self, client):
        payload = json.dumps({'type': 'domain.verified'}).encode()
        # Sign with wrong secret
        wrong = _sign(payload, secret='wrong')
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=wrong)
        assert resp.status_code == 401

    def test_expired_timestamp_401(self, client):
        payload = json.dumps({'type': 'domain.verified'}).encode()
        # 10 min ago
        old = int(time.time()) - 600
        headers = _sign(payload, ts=old)
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=headers)
        assert resp.status_code == 401

    def test_valid_signature_passes(self, client):
        payload = json.dumps({'type': 'unknown.event', 'payload': {}}).encode()
        headers = _sign(payload)
        mock_sb = MagicMock()
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET), \
             patch('routes.webhooks._get_supabase', return_value=mock_sb):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=headers)
        assert resp.status_code == 200


# ── Event handling ──────────────────────────────────────────────────────────

def _build_mock_supabase():
    """A MagicMock that records update() invocations under .table('organizations')."""
    sb = MagicMock()
    table = sb.table.return_value
    upd = table.update.return_value
    upd.eq.return_value.execute.return_value = MagicMock()
    return sb


class TestVercelEvents:

    def test_domain_verified_sets_active(self, client):
        payload = json.dumps({
            'type': 'domain.verified',
            'payload': {'domain': {'name': 'chess.example.com'}},
        }).encode()
        headers = _sign(payload)
        sb = _build_mock_supabase()
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET), \
             patch('routes.webhooks._get_supabase', return_value=sb):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=headers)
        assert resp.status_code == 200
        update_call = sb.table.return_value.update.call_args[0][0]
        assert update_call['custom_domain_status'] == 'active'
        assert 'custom_domain_verified_at' in update_call

    def test_cert_issued_sets_active(self, client):
        payload = json.dumps({
            'type': 'domain.cert.issued',
            'payload': {'domain': {'name': 'chess.example.com'}},
        }).encode()
        headers = _sign(payload)
        sb = _build_mock_supabase()
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET), \
             patch('routes.webhooks._get_supabase', return_value=sb):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=headers)
        assert resp.status_code == 200
        update_call = sb.table.return_value.update.call_args[0][0]
        assert update_call['custom_domain_status'] == 'active'

    def test_cert_failed_sets_failed(self, client):
        payload = json.dumps({
            'type': 'domain.cert.failed',
            'payload': {'domain': {'name': 'chess.example.com'}, 'error': 'foo'},
        }).encode()
        headers = _sign(payload)
        sb = _build_mock_supabase()
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET), \
             patch('routes.webhooks._get_supabase', return_value=sb):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=headers)
        assert resp.status_code == 200
        update_call = sb.table.return_value.update.call_args[0][0]
        assert update_call['custom_domain_status'] == 'failed'
        # Failed events must not stamp verified_at
        assert 'custom_domain_verified_at' not in update_call

    def test_domain_created_is_noop(self, client):
        payload = json.dumps({
            'type': 'domain.created',
            'payload': {'domain': {'name': 'chess.example.com'}},
        }).encode()
        headers = _sign(payload)
        sb = _build_mock_supabase()
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET), \
             patch('routes.webhooks._get_supabase', return_value=sb):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=headers)
        assert resp.status_code == 200
        sb.table.return_value.update.assert_not_called()

    def test_unknown_event_logs_200(self, client):
        payload = json.dumps({
            'type': 'project.deployment.created',
            'payload': {},
        }).encode()
        headers = _sign(payload)
        sb = _build_mock_supabase()
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET), \
             patch('routes.webhooks._get_supabase', return_value=sb):
            resp = client.post('/api/webhooks/vercel',
                               data=payload, content_type='application/json',
                               headers=headers)
        assert resp.status_code == 200
        sb.table.return_value.update.assert_not_called()


class TestVercelIdempotency:

    def test_replayed_verified_event_yields_same_state(self, client):
        payload = json.dumps({
            'type': 'domain.verified',
            'payload': {'domain': {'name': 'chess.example.com'}},
        }).encode()
        headers = _sign(payload)
        sb = _build_mock_supabase()
        with patch('routes.webhooks.VERCEL_WEBHOOK_SECRET', SECRET), \
             patch('routes.webhooks._get_supabase', return_value=sb):
            r1 = client.post('/api/webhooks/vercel',
                             data=payload, content_type='application/json',
                             headers=headers)
            r2 = client.post('/api/webhooks/vercel',
                             data=payload, content_type='application/json',
                             headers=headers)
        assert r1.status_code == 200 and r2.status_code == 200
        # Each call issues the same status update — the row converges to active.
        for call in sb.table.return_value.update.call_args_list:
            assert call[0][0]['custom_domain_status'] == 'active'
