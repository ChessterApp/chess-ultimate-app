"""Tests for backend.services.resend_client — Resend Domains API wrapper.

Covers the state-machine helpers and the URL-fopen plumbing of the client.
HTTP calls are patched at ``urllib.request.urlopen`` so we can simulate
2xx/4xx/5xx responses without hitting Resend.
"""

import io
import json
from unittest.mock import patch, MagicMock

import pytest

from services import resend_client as rc


@pytest.fixture(autouse=True)
def reset_default_client():
    rc.reset_client()
    yield
    rc.reset_client()


class TestMapResendStatus:
    def test_verified_maps_to_active(self):
        assert rc.map_resend_status('verified') == 'active'
        assert rc.map_resend_status('success') == 'active'

    def test_failed_maps_to_failed(self):
        assert rc.map_resend_status('failed') == 'failed'
        assert rc.map_resend_status('error') == 'failed'

    def test_in_progress_maps_to_verifying(self):
        assert rc.map_resend_status('in_progress') == 'verifying'
        assert rc.map_resend_status('verifying') == 'verifying'

    def test_unknown_or_pending_defaults_to_pending(self):
        assert rc.map_resend_status('not_started') == 'pending'
        assert rc.map_resend_status('unknown') == 'pending'
        assert rc.map_resend_status(None) == 'pending'

    def test_is_terminal(self):
        assert rc.is_terminal('active') is True
        assert rc.is_terminal('failed') is True
        assert rc.is_terminal('pending') is False
        assert rc.is_terminal('verifying') is False


def _resp(status: int, payload: dict):
    """Helper to build a urlopen()-like response object."""
    body = json.dumps(payload).encode('utf-8')
    m = MagicMock()
    m.__enter__ = MagicMock(return_value=m)
    m.__exit__ = MagicMock(return_value=False)
    m.read = MagicMock(return_value=body)
    m.status = status
    return m


class TestResendClientCRUD:
    def test_create_domain_returns_payload(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_key')
        with patch('urllib.request.urlopen', return_value=_resp(200, {
            'id': 'd_123', 'name': 'mail.example.com', 'status': 'not_started',
            'records': [{'record': 'SPF'}],
        })):
            out = rc.get_client().create_domain('mail.example.com')
            assert out['id'] == 'd_123'
            assert out['records'][0]['record'] == 'SPF'

    def test_get_domain(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_key')
        with patch('urllib.request.urlopen', return_value=_resp(200, {
            'id': 'd_123', 'status': 'verified',
        })):
            out = rc.get_client().get_domain('d_123')
            assert out['status'] == 'verified'

    def test_verify_domain(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_key')
        with patch('urllib.request.urlopen', return_value=_resp(200, {
            'id': 'd_123', 'status': 'in_progress',
        })):
            out = rc.get_client().verify_domain('d_123')
            assert out['status'] == 'in_progress'

    def test_remove_domain(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_key')
        with patch('urllib.request.urlopen', return_value=_resp(200, {'deleted': True})):
            out = rc.get_client().remove_domain('d_123')
            assert out['deleted'] is True

    def test_no_api_key_raises_misconfigured(self, monkeypatch):
        monkeypatch.delenv('RESEND_API_KEY', raising=False)
        with pytest.raises(rc.ResendAPIError) as exc:
            rc.get_client().create_domain('x.example.com')
        assert exc.value.status_code == 500
        assert exc.value.code == 'misconfigured'

    def test_http_error_translates_to_resend_api_error(self, monkeypatch):
        import urllib.error
        monkeypatch.setenv('RESEND_API_KEY', 're_key')

        def boom(*a, **kw):
            err = urllib.error.HTTPError(
                'https://api.resend.com/domains', 422, 'Unprocessable', {}, None,
            )
            err.read = lambda: json.dumps({
                'name': 'validation_error', 'message': 'domain already exists',
            }).encode('utf-8')
            raise err

        with patch('urllib.request.urlopen', side_effect=boom):
            with pytest.raises(rc.ResendAPIError) as exc:
                rc.get_client().create_domain('x.example.com')
            assert exc.value.status_code == 422
            assert exc.value.code == 'validation_error'
            assert 'already exists' in exc.value.message
