"""Tests for the public GET /api/admin/organizations/by-custom-domain/<host>.

This is the backend endpoint the frontend middleware calls to map a custom
domain to its org. It mirrors the by-slug shape so the middleware cache and
response handling can be uniform.
"""

import pytest
from unittest.mock import patch

from tests.test_admin_api import (
    FakeQueryBuilder, FakeQueryResult, ORG_ID, SAMPLE_ORG,
)
from tests.test_custom_domain_routes import StatefulSupabase


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


class TestMiddlewareCustomDomainLookup:

    def test_returns_active_org_shape(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG,
                                        custom_domain='chess.example.com',
                                        status='active')]}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/chess.example.com')
        assert resp.status_code == 200
        body = resp.get_json()
        # Mirror by-slug shape: id + slug + branding fields.
        assert body['id'] == ORG_ID
        assert body['slug'] == SAMPLE_ORG['slug']
        assert body['custom_domain'] == 'chess.example.com'

    def test_404_on_unknown_host(self, client):
        rows = {'organizations': []}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/unknown.example.com')
        assert resp.status_code == 404

    def test_ignores_suspended_orgs(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG,
                                        custom_domain='chess.example.com',
                                        status='suspended')]}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/chess.example.com')
        assert resp.status_code == 404

    def test_empty_host_404(self, client):
        # The Flask path converter normally rejects empty path segments, but a
        # whitespace-only host should still 404 (defence in depth).
        rows = {'organizations': []}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/%20')
        assert resp.status_code == 404

    def test_strips_trailing_dot(self, client):
        rows = {'organizations': [dict(SAMPLE_ORG,
                                        custom_domain='chess.example.com',
                                        status='active')]}
        with patch('routes.admin._get_supabase', return_value=StatefulSupabase(rows)):
            resp = client.get('/api/admin/organizations/by-custom-domain/chess.example.com.')
        assert resp.status_code == 200
