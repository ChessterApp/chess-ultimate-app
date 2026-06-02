"""Tests for backend.services.email — Resend invite emails."""

import os
import pytest
from unittest.mock import patch, MagicMock

from services import email as email_svc


ORG = {
    'id': 'org-1',
    'name': 'Almaty Chess Academy',
    'slug': 'almaty',
    'logo_url': 'https://cdn.example/logo.png',
    'primary_color': '#0066ff',
}


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    yield


class TestSendInviteEmail:
    def test_fails_closed_when_no_api_key(self):
        with patch('services.email._get_org', return_value=ORG), \
             patch('services.email._log_failure') as mock_log:
            ok = email_svc.send_invite_email(
                org_id='org-1', to_email='kid@x.com', role='student'
            )
            assert ok is False
            mock_log.assert_called_once()
            args = mock_log.call_args[0]
            assert 'RESEND_API_KEY' in args[3]

    def test_calls_resend_with_signed_body(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_test_xxx')
        with patch('services.email._get_org', return_value=ORG), \
             patch('services.email._post_json') as mock_post:
            mock_post.return_value = {'id': 'em_123'}
            ok = email_svc.send_invite_email(
                org_id='org-1', to_email='kid@x.com', role='student'
            )
            assert ok is True
            args, _ = mock_post.call_args
            url, headers, body = args
            assert url == email_svc.RESEND_API_URL
            assert headers['Authorization'] == 'Bearer re_test_xxx'
            assert body['to'] == ['kid@x.com']
            assert 'Almaty Chess Academy' in body['subject']
            assert 'kid@x.com' in body['html']

    def test_records_failure_on_http_error(self, monkeypatch):
        import urllib.error
        monkeypatch.setenv('RESEND_API_KEY', 're_test_xxx')

        def raise_http_error(*a, **kw):
            err = urllib.error.HTTPError(
                'https://api.resend.com/emails',
                422, 'Unprocessable', {}, None,
            )
            # The handler does err.read() — patch it.
            err.read = lambda: b'{"name":"validation_error"}'
            raise err

        with patch('services.email._get_org', return_value=ORG), \
             patch('services.email._post_json', side_effect=raise_http_error), \
             patch('services.email._log_failure') as mock_log:
            ok = email_svc.send_invite_email(
                org_id='org-1', to_email='kid@x.com', role='student'
            )
            assert ok is False
            mock_log.assert_called_once()

    def test_invite_link_uses_tenant_subdomain(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_test_xxx')
        captured = {}

        def fake_post(url, headers, body):
            captured['body'] = body
            return {}

        with patch('services.email._get_org', return_value=ORG), \
             patch('services.email._post_json', side_effect=fake_post):
            email_svc.send_invite_email(
                org_id='org-1', to_email='kid@x.com', role='student'
            )
            assert 'almaty.chesster.io/sign-up?invite=kid@x.com' in captured['body']['html']
