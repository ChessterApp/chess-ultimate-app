"""Tests for GET|POST /api/email/unsubscribe (welcome drip, P4)."""

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from services import welcome_drip as svc


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('EMAIL_UNSUB_SECRET', 'unsub-secret')


@pytest.fixture
def client():
    from routes.email_unsubscribe import email_unsubscribe_bp
    app = Flask(__name__)
    app.register_blueprint(email_unsubscribe_bp)
    return app.test_client()


@pytest.fixture
def sb():
    """Fake Supabase client recording upserts / updates per table."""
    calls = {'upsert': [], 'update': []}
    tables = {}

    def table(name):
        if name in tables:
            return tables[name]
        t = MagicMock(name=name)
        chain = MagicMock()
        chain.eq.return_value = chain
        chain.is_.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = MagicMock(
            data=[{'user_id': 'user_1'}] if name == 'welcome_emails' else [],
        )
        t.select.return_value = chain

        def upsert(payload, **kw):
            calls['upsert'].append((name, payload, kw))
            return chain

        def update(payload):
            calls['update'].append((name, payload, chain))
            return chain

        t.upsert.side_effect = upsert
        t.update.side_effect = update
        tables[name] = t
        return t

    client = MagicMock()
    client.table.side_effect = table
    with patch.object(svc, '_supabase', return_value=client):
        yield calls


def test_get_good_token_unsubscribes_and_marks_rows(client, sb):
    token = svc.make_unsubscribe_token('Kid@X.io')
    res = client.get(f'/api/email/unsubscribe?t={token}')
    assert res.status_code == 200
    assert 'text/html' in res.content_type
    assert "You're unsubscribed" in res.get_data(as_text=True)

    assert sb['upsert'] == [
        ('email_opt_outs', {'email': 'kid@x.io', 'user_id': 'user_1'}, {'on_conflict': 'email'}),
    ]
    (table, payload, chain), = sb['update']
    assert table == 'welcome_emails'
    assert payload == {'skipped_reason': 'opted_out'}
    chain.eq.assert_any_call('email', 'kid@x.io')
    chain.is_.assert_any_call('sent_at', None)
    chain.is_.assert_any_call('skipped_reason', None)


def test_post_one_click_returns_200(client, sb):
    token = svc.make_unsubscribe_token('kid@x.io')
    res = client.post(f'/api/email/unsubscribe?t={token}', data='List-Unsubscribe=One-Click')
    assert res.status_code == 200
    assert len(sb['upsert']) == 1
    assert len(sb['update']) == 1


@pytest.mark.parametrize('qs', ['', '?t=', '?t=garbage', '?t=a.b'])
def test_bad_token_400_and_no_writes(client, sb, qs):
    res = client.get(f'/api/email/unsubscribe{qs}')
    assert res.status_code == 400
    assert sb['upsert'] == [] and sb['update'] == []


def test_token_signed_with_other_secret_rejected(client, sb, monkeypatch):
    token = svc.make_unsubscribe_token('kid@x.io')
    monkeypatch.setenv('EMAIL_UNSUB_SECRET', 'rotated')
    assert client.post(f'/api/email/unsubscribe?t={token}').status_code == 400
    assert sb['upsert'] == []
