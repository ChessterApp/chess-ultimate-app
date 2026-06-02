"""Tests for /api/subdomains/check — slug availability (PRD §6.5)."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    from flask import Flask
    from routes.subdomains import subdomains_bp
    app = Flask(__name__)
    app.register_blueprint(subdomains_bp)
    return app.test_client()


def _wire_existing(mock_sb, exists: bool):
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.limit.return_value = builder
    builder.execute.return_value = MagicMock(data=[{'id': 'x'}] if exists else [])
    mock_sb.return_value.table.return_value = builder


class TestCheckSubdomain:
    def test_empty_slug_unavailable(self, client):
        resp = client.get('/api/subdomains/check?slug=')
        assert resp.status_code == 200
        assert resp.get_json() == {'available': False, 'reason': 'empty'}

    def test_reserved_slug_blocked(self, client):
        resp = client.get('/api/subdomains/check?slug=admin')
        body = resp.get_json()
        assert resp.status_code == 200
        assert body['available'] is False
        assert body['reason'] == 'reserved'
        assert 'suggestions' in body

    def test_invalid_format_underscores(self, client):
        resp = client.get('/api/subdomains/check?slug=bad_slug')
        body = resp.get_json()
        assert resp.status_code == 200
        assert body['available'] is False
        assert body['reason'] == 'invalid_format'

    def test_invalid_format_leading_hyphen(self, client):
        resp = client.get('/api/subdomains/check?slug=-foo')
        body = resp.get_json()
        assert body['available'] is False
        assert body['reason'] == 'invalid_format'

    def test_invalid_format_too_long(self, client):
        slug = 'a' * 40
        resp = client.get(f'/api/subdomains/check?slug={slug}')
        body = resp.get_json()
        assert body['available'] is False
        assert body['reason'] == 'invalid_format'

    def test_taken_slug(self, client):
        with patch('routes.subdomains._get_supabase') as mock_sb:
            _wire_existing(mock_sb, exists=True)
            resp = client.get('/api/subdomains/check?slug=almaty')
            body = resp.get_json()
            assert resp.status_code == 200
            assert body['available'] is False
            assert body['reason'] == 'taken'
            assert 'suggestions' in body

    def test_available_slug(self, client):
        with patch('routes.subdomains._get_supabase') as mock_sb:
            _wire_existing(mock_sb, exists=False)
            resp = client.get('/api/subdomains/check?slug=newschool')
            body = resp.get_json()
            assert resp.status_code == 200
            assert body == {'available': True}
