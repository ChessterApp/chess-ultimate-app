"""Tests for `create_org_self_serve` merging brand fields from pending_onboarding.

Bug B from WHITE_LABEL_SWEEP_TASK.md Phase 0: the initial insert dropped any
brand fields the wizard collected before payment, leaving the org row with
defaults until a separate PUT landed (which sometimes raced or failed).

These tests assert the insert payload now carries logo_url + color fields
when the caller has a pending_onboarding row, and falls back gracefully
when no pending row exists.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


USER_ID = 'user_director_42'
ORG_ID = '52b5682c-8c60-4b66-bd19-6ff2d17214eb'


class FakeTable:
    """Supabase-py table builder mock that records ops + returns canned data."""

    def __init__(self, name, recorder, pending_payload):
        self.name = name
        self._recorder = recorder
        self._pending_payload = pending_payload
        self._select_data = None
        self._is_select = False

    def select(self, *_a, **_kw):
        self._is_select = True
        return self

    def insert(self, data, **_kw):
        self._recorder.append(('insert', self.name, data))
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

    def maybe_single(self):
        return self

    def execute(self):
        # `pending_onboarding` select path
        if self.name == 'pending_onboarding' and self._is_select:
            if self._pending_payload is None:
                return MagicMock(data=None)
            return MagicMock(data={'payload': self._pending_payload})
        # organizations slug-uniqueness select path returns []
        if self.name == 'organizations' and self._is_select and self._select_data is None:
            return MagicMock(data=[])
        return MagicMock(data=self._select_data or [])


class FakeSupabase:
    def __init__(self, pending_payload):
        self.recorder: list[tuple] = []
        self._pending_payload = pending_payload

    def table(self, name):
        return FakeTable(name, self.recorder, self._pending_payload)


@pytest.fixture
def client():
    from flask import Flask
    from routes.onboarding import onboarding_bp
    app = Flask(__name__)
    app.register_blueprint(onboarding_bp)
    return app.test_client()


def _post_create(client, slug='chess-empire', name='Chess Empire'):
    return client.post(
        '/api/onboarding/create-org',
        headers={'X-User-Id': USER_ID},
        json={'slug': slug, 'name': name},
    )


def _build_supa(monkeypatch, pending_payload):
    fake = FakeSupabase(pending_payload)
    monkeypatch.setattr('routes.onboarding._get_supabase', lambda: fake)
    monkeypatch.setattr(
        'routes.super_admin._clerk_sync_org', lambda **_kw: None
    )
    monkeypatch.setattr(
        'routes.super_admin._clerk_sync_membership', lambda *_a, **_kw: None
    )
    import services.lifecycle_emails as lm
    monkeypatch.setattr(lm, 'schedule_for_org', lambda *_a, **_kw: None)
    fake_vc = MagicMock()
    fake_vc.add_domain.return_value = {'id': 'dom', 'verified': True}
    monkeypatch.setattr(
        'services.vercel_client.get_client', lambda: fake_vc
    )
    return fake


def _find_insert(recorder, table):
    for op, t, data in recorder:
        if op == 'insert' and t == table:
            return data
    return None


def test_brand_fields_from_pending_onboarding_are_merged_into_org_insert(
    client, monkeypatch
):
    pending_payload = {
        'logo_url': 'https://x/logo.png',
        'primary_color': '#5e1b2c',
        'secondary_color': '#ffffff',
        'accent_color': '#c2a37f',
        'favicon_url': 'https://x/fav.ico',
        'custom_css': '.foo { color: red; }',
        'landing_page_config': {'hero_headline': 'Welcome'},
        # Non-brand keys should be ignored.
        'tier': 'starter',
    }
    supa = _build_supa(monkeypatch, pending_payload)
    resp = _post_create(client)
    assert resp.status_code == 201

    insert = _find_insert(supa.recorder, 'organizations')
    assert insert is not None
    assert insert['slug'] == 'chess-empire'
    assert insert['name'] == 'Chess Empire'
    assert insert['logo_url'] == 'https://x/logo.png'
    assert insert['primary_color'] == '#5e1b2c'
    assert insert['secondary_color'] == '#ffffff'
    assert insert['accent_color'] == '#c2a37f'
    assert insert['favicon_url'] == 'https://x/fav.ico'
    assert insert['custom_css'] == '.foo { color: red; }'
    assert insert['landing_page_config'] == {'hero_headline': 'Welcome'}
    assert 'tier' not in insert


def test_no_pending_row_falls_back_to_baseline_insert(client, monkeypatch):
    supa = _build_supa(monkeypatch, pending_payload=None)
    resp = _post_create(client)
    assert resp.status_code == 201

    insert = _find_insert(supa.recorder, 'organizations')
    assert insert is not None
    # No brand keys should be present.
    for key in (
        'logo_url',
        'primary_color',
        'secondary_color',
        'accent_color',
        'favicon_url',
        'custom_css',
        'landing_page_config',
    ):
        assert key not in insert


def test_partial_pending_payload_only_persists_set_fields(client, monkeypatch):
    pending_payload = {
        'logo_url': 'https://x/logo.png',
        # other brand fields intentionally absent
    }
    supa = _build_supa(monkeypatch, pending_payload)
    resp = _post_create(client)
    assert resp.status_code == 201

    insert = _find_insert(supa.recorder, 'organizations')
    assert insert is not None
    assert insert['logo_url'] == 'https://x/logo.png'
    assert 'primary_color' not in insert
    assert 'favicon_url' not in insert
