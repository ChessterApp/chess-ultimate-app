"""Tests for `create_org_self_serve` → Vercel subdomain registration wire-in.

Covers the four branches of the best-effort registration:
- add_domain returns verified=True → status=active
- add_domain returns verified=False → status=pending
- add_domain raises VercelAPIError(domain_already_in_use) → status=pending
- add_domain raises generic VercelAPIError → status=failed but signup still 201
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


USER_ID = 'user_director_42'
ORG_ID = '52b5682c-8c60-4b66-bd19-6ff2d17214eb'


class FakeTable:
    """Minimal supabase-py table builder mock for the onboarding routes path."""

    def __init__(self, name, recorder):
        self.name = name
        self._recorder = recorder
        self._select_data = None

    def select(self, *_a, **_kw):
        return self

    def insert(self, data, **_kw):
        self._recorder.append(('insert', self.name, data))
        # Return the inserted row + id so onboarding.org_id resolves.
        self._select_data = [{**data, 'id': ORG_ID}]
        return self

    def upsert(self, data, **_kw):
        self._recorder.append(('upsert', self.name, data))
        return self

    def update(self, data, **_kw):
        self._recorder.append(('update', self.name, data))
        return self

    def delete(self, **_kw):
        self._recorder.append(('delete', self.name))
        return self

    def eq(self, *_a, **_kw):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return MagicMock(data=self._select_data or [])


class FakeSupabase:
    def __init__(self):
        self.recorder: list[tuple] = []

    def table(self, name):
        return FakeTable(name, self.recorder)


@pytest.fixture
def client():
    from flask import Flask
    from routes.onboarding import onboarding_bp
    app = Flask(__name__)
    app.register_blueprint(onboarding_bp)
    return app.test_client()


@pytest.fixture
def supa(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr('routes.onboarding._get_supabase', lambda: fake)
    # Stub side-effect helpers so the test isolates the Vercel registration path.
    monkeypatch.setattr(
        'routes.super_admin._clerk_sync_org',
        lambda **_kw: None,
    )
    monkeypatch.setattr(
        'routes.super_admin._clerk_sync_membership',
        lambda *_a, **_kw: None,
    )
    import services.lifecycle_emails as lm
    monkeypatch.setattr(lm, 'schedule_for_org', lambda *_a, **_kw: None)
    return fake


def _post_create(client, slug='test-school-1', name='Test School'):
    return client.post(
        '/api/onboarding/create-org',
        headers={'X-User-Id': USER_ID},
        json={'slug': slug, 'name': name},
    )


def _find_update(recorder, expected_keys):
    for op, table, data in recorder:
        if op == 'update' and table == 'organizations' and expected_keys.issubset(set(data.keys())):
            return data
    return None


def test_subdomain_active_when_vercel_returns_verified(client, supa):
    """add_domain returns verified=True → DB shows subdomain_status='active'."""
    fake_client = MagicMock()
    fake_client.add_domain.return_value = {
        'id': 'dom_abc', 'name': 'test-school-1.chesster.io', 'verified': True,
    }
    with patch('services.vercel_client.get_client', return_value=fake_client):
        resp = _post_create(client)

    assert resp.status_code == 201
    fake_client.add_domain.assert_called_once_with('test-school-1.chesster.io')
    upd = _find_update(supa.recorder, {'subdomain_status'})
    assert upd is not None
    assert upd['subdomain_status'] == 'active'
    assert upd['subdomain_vercel_id'] == 'dom_abc'
    assert 'subdomain_verified_at' in upd


def test_subdomain_pending_when_vercel_unverified(client, supa):
    fake_client = MagicMock()
    fake_client.add_domain.return_value = {
        'id': 'dom_pending', 'verified': False,
    }
    with patch('services.vercel_client.get_client', return_value=fake_client):
        resp = _post_create(client)

    assert resp.status_code == 201
    upd = _find_update(supa.recorder, {'subdomain_status'})
    assert upd is not None
    assert upd['subdomain_status'] == 'pending'
    assert upd['subdomain_vercel_id'] == 'dom_pending'
    assert 'subdomain_verified_at' not in upd


def test_subdomain_pending_when_domain_already_in_use(client, supa):
    """`domain_already_in_use` is the idempotent-retry path → status=pending, no error stamped."""
    from services.vercel_client import VercelAPIError
    fake_client = MagicMock()
    fake_client.add_domain.side_effect = VercelAPIError(
        409, 'domain_already_in_use', 'Domain already in use',
    )
    with patch('services.vercel_client.get_client', return_value=fake_client):
        resp = _post_create(client)

    assert resp.status_code == 201
    upd = _find_update(supa.recorder, {'subdomain_status'})
    assert upd is not None
    assert upd['subdomain_status'] == 'pending'
    assert upd.get('subdomain_last_error') is None


def test_subdomain_failed_on_generic_vercel_error_but_signup_succeeds(client, supa):
    """Generic Vercel failure → signup still returns 201; status stamped 'failed' with error text."""
    from services.vercel_client import VercelAPIError
    fake_client = MagicMock()
    fake_client.add_domain.side_effect = VercelAPIError(
        502, 'not_authorized', 'token expired',
    )
    with patch('services.vercel_client.get_client', return_value=fake_client):
        resp = _post_create(client)

    # Signup MUST succeed even though Vercel failed.
    assert resp.status_code == 201
    upd = _find_update(supa.recorder, {'subdomain_status'})
    assert upd is not None
    assert upd['subdomain_status'] == 'failed'
    assert 'not_authorized' in (upd.get('subdomain_last_error') or '')


def test_subdomain_failed_on_unexpected_exception(client, supa):
    """Non-VercelAPIError exception (e.g. network) → status=failed, signup still succeeds."""
    fake_client = MagicMock()
    fake_client.add_domain.side_effect = RuntimeError('boom')
    with patch('services.vercel_client.get_client', return_value=fake_client):
        resp = _post_create(client)

    assert resp.status_code == 201
    upd = _find_update(supa.recorder, {'subdomain_status'})
    assert upd is not None
    assert upd['subdomain_status'] == 'failed'
    assert 'boom' in (upd.get('subdomain_last_error') or '')


def test_subdomain_for_slug_helper():
    from services.vercel_client import APEX_DOMAIN, subdomain_for_slug
    assert APEX_DOMAIN == 'chesster.io'
    assert subdomain_for_slug('chess-empire') == 'chess-empire.chesster.io'
