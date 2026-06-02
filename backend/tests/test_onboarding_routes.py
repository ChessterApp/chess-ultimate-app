"""Tests for /api/onboarding/* — pending_onboarding CRUD."""

import pytest
from unittest.mock import patch, MagicMock


USER_ID = 'user_director_42'


class FakeBuilder:
    def __init__(self, data=None):
        self._data = data
        self.last_args = None

    def select(self, *a, **kw): return self
    def insert(self, data, **kw): self.last_args = ('insert', data); return self
    def upsert(self, data, **kw):
        self.last_args = ('upsert', data, kw)
        return self
    def update(self, data, **kw): self.last_args = ('update', data); return self
    def delete(self, **kw): self.last_args = ('delete', kw); return self
    def eq(self, *a, **kw): return self
    def maybe_single(self): return self
    def single(self): return self

    def execute(self):
        return MagicMock(data=self._data)


@pytest.fixture
def client():
    from flask import Flask
    from routes.onboarding import onboarding_bp
    app = Flask(__name__)
    app.register_blueprint(onboarding_bp)
    return app.test_client()


class TestSave:
    def test_save_requires_user_header(self, client):
        resp = client.post('/api/onboarding/save', json={'step': 'school'})
        assert resp.status_code == 401

    def test_save_rejects_invalid_step(self, client):
        with patch('routes.onboarding._get_supabase'):
            resp = client.post(
                '/api/onboarding/save',
                json={'step': 'bogus_step'},
                headers={'X-User-Id': USER_ID},
            )
            assert resp.status_code == 400

    def test_save_rejects_non_object_payload(self, client):
        with patch('routes.onboarding._get_supabase'):
            resp = client.post(
                '/api/onboarding/save',
                json={'step': 'school', 'payload': 'not an object'},
                headers={'X-User-Id': USER_ID},
            )
            assert resp.status_code == 400

    def test_save_upserts(self, client):
        builder = FakeBuilder()
        with patch('routes.onboarding._get_supabase') as mock_sb:
            mock_sb.return_value.table.return_value = builder
            resp = client.post(
                '/api/onboarding/save',
                json={
                    'step': 'plan',
                    'email': 'dir@example.com',
                    'payload': {'school_name': 'Almaty Chess'},
                },
                headers={'X-User-Id': USER_ID},
            )
            assert resp.status_code == 200
            assert builder.last_args[0] == 'upsert'
            row = builder.last_args[1]
            assert row['clerk_user_id'] == USER_ID
            assert row['step'] == 'plan'
            assert row['payload'] == {'school_name': 'Almaty Chess'}
            assert row['email'] == 'dir@example.com'
            assert 'expires_at' in row


class TestResume:
    def test_resume_requires_user_header(self, client):
        resp = client.get('/api/onboarding/resume')
        assert resp.status_code == 401

    def test_resume_returns_null_when_no_row(self, client):
        builder = FakeBuilder(data=None)
        with patch('routes.onboarding._get_supabase') as mock_sb:
            mock_sb.return_value.table.return_value = builder
            resp = client.get(
                '/api/onboarding/resume', headers={'X-User-Id': USER_ID}
            )
            assert resp.status_code == 200
            assert resp.get_json() == {'pending': None}

    def test_resume_returns_row(self, client):
        row = {'clerk_user_id': USER_ID, 'step': 'brand', 'payload': {}}
        builder = FakeBuilder(data=row)
        with patch('routes.onboarding._get_supabase') as mock_sb:
            mock_sb.return_value.table.return_value = builder
            resp = client.get(
                '/api/onboarding/resume', headers={'X-User-Id': USER_ID}
            )
            assert resp.status_code == 200
            assert resp.get_json()['pending']['step'] == 'brand'


class TestComplete:
    def test_complete_requires_user_header(self, client):
        resp = client.delete('/api/onboarding/complete')
        assert resp.status_code == 401

    def test_complete_deletes_row(self, client):
        builder = FakeBuilder()
        with patch('routes.onboarding._get_supabase') as mock_sb:
            mock_sb.return_value.table.return_value = builder
            resp = client.delete(
                '/api/onboarding/complete', headers={'X-User-Id': USER_ID}
            )
            assert resp.status_code == 200
            assert builder.last_args[0] == 'delete'
