"""Tests for tenant-subdomain CORS coverage.

Verifies that Flask-CORS, configured with the apex whitelist + a regex covering
every `{slug}.chesster.io`, accepts preflight requests from any tenant subdomain
(including ones we've never seen) while still rejecting hostile origins and
suffix-spoofing attempts.

We rebuild a minimal Flask app per test using the same regex from app.py rather
than importing app.py (which would drag in Supabase, Anthropic, etc.) — this
keeps the test focused on the CORS contract.
"""

import re

import pytest
from flask import Flask, jsonify
from flask_cors import CORS


# Must stay in sync with the regex in backend/app.py.
TENANT_SUBDOMAIN_REGEX = re.compile(
    r'^https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.chesster\.io$'
)
APEX_ORIGINS = ['https://chesster.io', 'https://www.chesster.io']


@pytest.fixture
def client():
    app = Flask(__name__)
    cors_origins = list(APEX_ORIGINS) + [TENANT_SUBDOMAIN_REGEX]
    CORS(app, origins=cors_origins, supports_credentials=True)

    @app.route('/api/courses', methods=['GET', 'OPTIONS'])
    def courses():
        return jsonify({'ok': True})

    return app.test_client()


def _preflight(client, origin):
    return client.options(
        '/api/courses',
        headers={
            'Origin': origin,
            'Access-Control-Request-Method': 'GET',
            'Access-Control-Request-Headers': 'authorization,content-type',
        },
    )


def test_tenant_subdomain_chess_empire_is_allowed(client):
    resp = _preflight(client, 'https://chess-empire.chesster.io')
    assert resp.headers.get('Access-Control-Allow-Origin') == 'https://chess-empire.chesster.io'
    assert resp.headers.get('Access-Control-Allow-Credentials') == 'true'


def test_arbitrary_tenant_subdomain_is_allowed(client):
    """Regex covers tenants we've never seen before — that's the whole point."""
    resp = _preflight(client, 'https://random-tenant-7.chesster.io')
    assert resp.headers.get('Access-Control-Allow-Origin') == 'https://random-tenant-7.chesster.io'


def test_apex_origin_is_allowed(client):
    """The apex is in the explicit whitelist, not the regex."""
    resp = _preflight(client, 'https://chesster.io')
    assert resp.headers.get('Access-Control-Allow-Origin') == 'https://chesster.io'


def test_hostile_origin_is_rejected(client):
    resp = _preflight(client, 'https://evil.example.com')
    assert 'Access-Control-Allow-Origin' not in resp.headers


def test_suffix_spoofing_origin_is_rejected(client):
    """`chesster.io.evil.com` must NOT match — anchoring on `\\.chesster\\.io$` blocks it."""
    resp = _preflight(client, 'https://chesster.io.evil.com')
    assert 'Access-Control-Allow-Origin' not in resp.headers


def test_subdomain_with_leading_hyphen_is_rejected(client):
    """RFC says labels must start with alphanumeric — keeps the regex tight."""
    resp = _preflight(client, 'https://-bad.chesster.io')
    assert 'Access-Control-Allow-Origin' not in resp.headers


def test_http_scheme_tenant_is_rejected(client):
    """Regex requires https:// — prevents downgrade attacks."""
    resp = _preflight(client, 'http://chess-empire.chesster.io')
    assert 'Access-Control-Allow-Origin' not in resp.headers
