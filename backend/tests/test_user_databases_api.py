"""
Tests for the User Databases API (/api/databases) blueprint.

A user owns multiple named game databases (collections). Databases are
soft-deleted for recovery; the default one cannot be deleted. Uses a Flask test
client with mocked Supabase and JWT auth, mirroring test_user_games_api.py /
test_collection_share.py.

Supabase is mocked per-table and the mock is filter-agnostic (eq/is_/ilike are
no-ops), so each test seeds exactly the rows the endpoint logic should see. The
endpoint re-checks id/user_id/name/deleted_at in Python, so these mocks exercise
the real ownership, duplicate and soft-delete logic.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import patch

from api.user_databases import (
    DATABASES_TABLE,
    GAMES_TABLE,
    SHARED_DATABASES_TABLE,
    RETENTION_DAYS,
)

USER_A = 'user_a'
USER_B = 'user_b'

DB_DEFAULT = {
    'id': 'db-default-0000',
    'user_id': USER_A,
    'name': 'My Games',
    'is_default': True,
    'created_at': '2025-01-01T10:00:00+00:00',
    'updated_at': '2025-01-01T10:00:00+00:00',
    'deleted_at': None,
}

DB_OPENINGS = {
    'id': 'db-openings-1111',
    'user_id': USER_A,
    'name': 'Openings',
    'is_default': False,
    'created_at': '2025-02-01T10:00:00+00:00',
    'updated_at': '2025-02-01T10:00:00+00:00',
    'deleted_at': None,
}

SHARE_TOKEN = 'share_token_openings_abc'

DB_OPENINGS_SHARED = {**DB_OPENINGS, 'share_token': SHARE_TOKEN}


def _game(idx, database_id=DB_OPENINGS['id'], **overrides):
    row = {
        'id': f'game-{idx}',
        'user_id': USER_A,
        'title': f'Game {idx}',
        'white': 'Player1',
        'black': 'Player2',
        'result': '1-0',
        'pgn': '[Event "x"]\n\n1. e4 e5 1-0\n',
        'notes': 'private notes',
        'database_id': database_id,
        'deleted_at': None,
        'created_at': '2025-02-02T10:00:00+00:00',
        'updated_at': '2025-02-02T10:00:00+00:00',
    }
    row.update(overrides)
    return row


# ─── Per-table mock ──────────────────────────────────────────────────────────

class FakeResult:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class FakeBuilder:
    """Chainable mock for supabase.table(name).select()...execute().

    Filters (eq/is_/ilike/order) are no-ops; insert/update mutate _data so the
    returned row looks like a real write.
    """
    def __init__(self, data=None, count=None):
        self._data = list(data or [])
        self._count = count

    def select(self, *a, **k):
        return self

    def insert(self, data, **k):
        self._data = [{**data, 'id': 'new-db-id'}] if not isinstance(data, list) else data
        return self

    def update(self, data, **k):
        if self._data:
            self._data = [{**self._data[0], **data}]
        return self

    def delete(self, **k):
        return self

    def eq(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    @property
    def not_(self):
        return self

    def lt(self, *a, **k):
        return self

    def ilike(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return FakeResult(data=self._data, count=self._count)


def make_table(tables):
    """tables maps a table name → dict(data=[...], count=N)."""
    def table(name):
        spec = tables.get(name, {})
        return FakeBuilder(data=spec.get('data'), count=spec.get('count'))
    return table


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    from flask import Flask
    from api.user_databases import user_databases_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(user_databases_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_jwt():
    """@verify_clerk_token is applied at import time — mock the decode to USER_A."""
    with patch('utils.auth._decode_clerk_token', return_value={'sub': USER_A}):
        yield


@pytest.fixture(autouse=True)
def mock_owner_name():
    """Owner display name comes from Clerk — stub it out for share tests."""
    with patch('api.user_databases._owner_display_name', return_value='Alice A'):
        yield


# ─── LIST ────────────────────────────────────────────────────────────────────

class TestListDatabases:
    def test_list_empty(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.get('/api/databases', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json() == []

    def test_list_with_game_count(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                DATABASES_TABLE: {'data': [DB_DEFAULT, DB_OPENINGS]},
                GAMES_TABLE: {'count': 4},
            })
            resp = client.get('/api/databases', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert len(body) == 2
            assert all('game_count' in d for d in body)
            assert body[0]['game_count'] == 4

    def test_list_requires_auth(self, client):
        resp = client.get('/api/databases')
        assert resp.status_code == 401


# ─── CREATE ──────────────────────────────────────────────────────────────────

class TestCreateDatabase:
    def test_create_ok(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.post('/api/databases',
                               data=json.dumps({'name': 'Tournaments'}),
                               headers=auth_headers)
            assert resp.status_code == 201
            body = resp.get_json()
            assert body['name'] == 'Tournaments'
            assert body['is_default'] is False
            assert body['game_count'] == 0

    def test_create_trims_name(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.post('/api/databases',
                               data=json.dumps({'name': '  Blitz  '}),
                               headers=auth_headers)
            assert resp.status_code == 201
            assert resp.get_json()['name'] == 'Blitz'

    def test_create_duplicate_409(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_OPENINGS]}})
            # Case-insensitive duplicate of an existing live database.
            resp = client.post('/api/databases',
                               data=json.dumps({'name': 'openings'}),
                               headers=auth_headers)
            assert resp.status_code == 409

    def test_create_empty_name_400(self, client, auth_headers):
        resp = client.post('/api/databases',
                           data=json.dumps({'name': '   '}),
                           headers=auth_headers)
        assert resp.status_code == 400

    def test_create_missing_name_400(self, client, auth_headers):
        resp = client.post('/api/databases',
                           data=json.dumps({}),
                           headers=auth_headers)
        assert resp.status_code == 400

    def test_create_too_long_400(self, client, auth_headers):
        resp = client.post('/api/databases',
                           data=json.dumps({'name': 'x' * 81}),
                           headers=auth_headers)
        assert resp.status_code == 400


# ─── RENAME ──────────────────────────────────────────────────────────────────

class TestRenameDatabase:
    def test_rename_ok(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_OPENINGS]}})
            resp = client.put(f'/api/databases/{DB_OPENINGS["id"]}',
                              data=json.dumps({'name': 'Repertoire'}),
                              headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['name'] == 'Repertoire'

    def test_rename_default_allowed(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_DEFAULT]}})
            resp = client.put(f'/api/databases/{DB_DEFAULT["id"]}',
                              data=json.dumps({'name': 'My Collection'}),
                              headers=auth_headers)
            assert resp.status_code == 200

    def test_rename_duplicate_409(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_OPENINGS, DB_DEFAULT]}})
            # Rename "Openings" to the default's name → collides.
            resp = client.put(f'/api/databases/{DB_OPENINGS["id"]}',
                              data=json.dumps({'name': 'my games'}),
                              headers=auth_headers)
            assert resp.status_code == 409

    def test_rename_to_same_name_ok(self, client, auth_headers):
        """Renaming a db to its own (case-varied) name must not self-collide."""
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_OPENINGS]}})
            resp = client.put(f'/api/databases/{DB_OPENINGS["id"]}',
                              data=json.dumps({'name': 'OPENINGS'}),
                              headers=auth_headers)
            assert resp.status_code == 200

    def test_rename_missing_404(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.put('/api/databases/nonexistent',
                              data=json.dumps({'name': 'X'}),
                              headers=auth_headers)
            assert resp.status_code == 404

    def test_rename_empty_name_400(self, client, auth_headers):
        resp = client.put(f'/api/databases/{DB_OPENINGS["id"]}',
                          data=json.dumps({'name': ''}),
                          headers=auth_headers)
        assert resp.status_code == 400


# ─── DELETE ──────────────────────────────────────────────────────────────────

class TestDeleteDatabase:
    def test_delete_non_default_ok(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_OPENINGS]}})
            resp = client.delete(f'/api/databases/{DB_OPENINGS["id"]}', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['success'] is True

    def test_delete_default_400(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_DEFAULT]}})
            resp = client.delete(f'/api/databases/{DB_DEFAULT["id"]}', headers=auth_headers)
            assert resp.status_code == 400
            assert 'default' in resp.get_json()['error'].lower()

    def test_delete_missing_404(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.delete('/api/databases/nonexistent', headers=auth_headers)
            assert resp.status_code == 404


# ─── RESTORE ─────────────────────────────────────────────────────────────────

class TestRestoreDatabase:
    def test_restore_ok(self, client, auth_headers):
        deleted = {**DB_OPENINGS, 'deleted_at': '2025-03-01T10:00:00+00:00'}
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [deleted]}})
            resp = client.post(f'/api/databases/{deleted["id"]}/restore', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['deleted_at'] is None

    def test_restore_name_collision_409(self, client, auth_headers):
        deleted = {**DB_OPENINGS, 'deleted_at': '2025-03-01T10:00:00+00:00'}
        live_clash = {**DB_OPENINGS, 'id': 'db-live-clash', 'deleted_at': None}
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [deleted, live_clash]}})
            resp = client.post(f'/api/databases/{deleted["id"]}/restore', headers=auth_headers)
            assert resp.status_code == 409

    def test_restore_missing_404(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.post('/api/databases/nonexistent/restore', headers=auth_headers)
            assert resp.status_code == 404


# ─── LIST DELETED (restore panel) ──────────────────────────────────────────────

def _deleted_days_ago(days):
    """A soft-deleted copy of DB_OPENINGS whose deleted_at is `days` days ago."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return {**DB_OPENINGS, 'deleted_at': ts}


class TestListDeletedDatabases:
    def test_list_deleted_empty(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.get('/api/databases/deleted', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json() == []

    def test_list_deleted_within_window(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                DATABASES_TABLE: {'data': [_deleted_days_ago(5)]},
                GAMES_TABLE: {'count': 3},
            })
            resp = client.get('/api/databases/deleted', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert len(body) == 1
            row = body[0]
            assert row['id'] == DB_OPENINGS['id']
            assert row['name'] == DB_OPENINGS['name']
            assert row['game_count'] == 3
            assert row['days_left'] == RETENTION_DAYS - 5

    def test_list_deleted_excludes_expired(self, client, auth_headers):
        # Deleted longer ago than the window → treated as gone.
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [_deleted_days_ago(RETENTION_DAYS + 10)]}})
            resp = client.get('/api/databases/deleted', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json() == []

    def test_list_deleted_days_left_floor_at_zero(self, client, auth_headers):
        # Exactly at the boundary (RETENTION_DAYS) is excluded; one day short is 1.
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [_deleted_days_ago(RETENTION_DAYS - 1)]}})
            resp = client.get('/api/databases/deleted', headers=auth_headers)
            body = resp.get_json()
            assert len(body) == 1
            assert body[0]['days_left'] == 1

    def test_list_deleted_requires_auth(self, client):
        resp = client.get('/api/databases/deleted')
        assert resp.status_code == 401

    def test_cannot_see_other_users_deleted_db(self, client, auth_headers):
        other = {**_deleted_days_ago(2), 'user_id': USER_B}
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [other]}})
            resp = client.get('/api/databases/deleted', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json() == []


# ─── CROSS-USER ISOLATION ─────────────────────────────────────────────────────
#
# USER_A is signed in (mock_jwt). We simulate USER_B's databases by seeding rows
# owned by USER_B; the endpoint's user_id re-check must reject them for USER_A.

class TestCrossUserIsolation:
    def test_cannot_see_other_users_db(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            # List is user_id-scoped at the DB level; the mock returns only the
            # caller's rows → empty here.
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.get('/api/databases', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json() == []

    def test_cannot_rename_other_users_db(self, client, auth_headers):
        other = {**DB_OPENINGS, 'user_id': USER_B}
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [other]}})
            resp = client.put(f'/api/databases/{other["id"]}',
                              data=json.dumps({'name': 'Hijacked'}),
                              headers=auth_headers)
            assert resp.status_code == 404

    def test_cannot_delete_other_users_db(self, client, auth_headers):
        other = {**DB_OPENINGS, 'user_id': USER_B}
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [other]}})
            resp = client.delete(f'/api/databases/{other["id"]}', headers=auth_headers)
            assert resp.status_code == 404


# ─── SHARE (mint / revoke) ─────────────────────────────────────────────────────

class TestShareDatabase:
    def test_mint_token(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_OPENINGS]}})
            resp = client.post(f'/api/databases/{DB_OPENINGS["id"]}/share', headers=auth_headers)
            assert resp.status_code == 200
            token = resp.get_json()['share_token']
            assert isinstance(token, str)
            assert len(token) >= 16

    def test_mint_is_idempotent(self, client, auth_headers):
        """A database that already has a token gets the same one back."""
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_OPENINGS_SHARED]}})
            resp = client.post(f'/api/databases/{DB_OPENINGS["id"]}/share', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['share_token'] == SHARE_TOKEN

    def test_cannot_share_default_400(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_DEFAULT]}})
            resp = client.post(f'/api/databases/{DB_DEFAULT["id"]}/share', headers=auth_headers)
            assert resp.status_code == 400
            assert 'default' in resp.get_json()['error'].lower()

    def test_share_missing_404(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.post('/api/databases/nope/share', headers=auth_headers)
            assert resp.status_code == 404

    def test_cannot_share_other_users_db_404(self, client, auth_headers):
        other = {**DB_OPENINGS, 'user_id': USER_B}
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [other]}})
            resp = client.post(f'/api/databases/{other["id"]}/share', headers=auth_headers)
            assert resp.status_code == 404

    def test_share_requires_auth(self, client):
        resp = client.post(f'/api/databases/{DB_OPENINGS["id"]}/share')
        assert resp.status_code == 401


class TestRevokeDatabaseShare:
    def test_revoke_ok(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': [DB_OPENINGS_SHARED]}})
            resp = client.delete(f'/api/databases/{DB_OPENINGS["id"]}/share', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['success'] is True

    def test_revoke_missing_404(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.delete('/api/databases/nope/share', headers=auth_headers)
            assert resp.status_code == 404

    def test_revoke_requires_auth(self, client):
        resp = client.delete(f'/api/databases/{DB_OPENINGS["id"]}/share')
        assert resp.status_code == 401


# ─── SHARED VIEW (recipient) ────────────────────────────────────────────────────

class TestGetSharedDatabase:
    def test_resolves_meta_and_games(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                DATABASES_TABLE: {'data': [DB_OPENINGS_SHARED]},
                GAMES_TABLE: {'data': [_game(1), _game(2)]},
            })
            resp = client.get(f'/api/databases/shared/{SHARE_TOKEN}', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['database']['id'] == DB_OPENINGS['id']
            assert body['database']['name'] == 'Openings'
            assert body['database']['game_count'] == 2
            assert body['owner_name'] == 'Alice A'
            assert len(body['games']) == 2

    def test_games_are_sanitized(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                DATABASES_TABLE: {'data': [DB_OPENINGS_SHARED]},
                GAMES_TABLE: {'data': [_game(1)]},
            })
            resp = client.get(f'/api/databases/shared/{SHARE_TOKEN}', headers=auth_headers)
            game = resp.get_json()['games'][0]
            assert 'notes' not in game
            assert 'user_id' not in game
            assert game['pgn']  # non-private fields survive

    def test_only_this_databases_games(self, client, auth_headers):
        """A game tagged to a different database is not leaked under this token."""
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                DATABASES_TABLE: {'data': [DB_OPENINGS_SHARED]},
                GAMES_TABLE: {'data': [_game(1), _game(9, database_id='db-other')]},
            })
            resp = client.get(f'/api/databases/shared/{SHARE_TOKEN}', headers=auth_headers)
            body = resp.get_json()
            assert body['database']['game_count'] == 1
            assert [g['id'] for g in body['games']] == ['game-1']

    def test_unknown_token_404(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.get('/api/databases/shared/nope', headers=auth_headers)
            assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get(f'/api/databases/shared/{SHARE_TOKEN}')
        assert resp.status_code == 401


# ─── SUBSCRIPTIONS ("Shared with me") ───────────────────────────────────────────

SUB_ROW = {
    'id': 'sub-1',
    'subscriber_id': USER_A,
    'source_token': SHARE_TOKEN,
    'added_at': '2025-03-01T10:00:00+00:00',
}


class TestSubscribeSharedDatabase:
    def test_subscribe_ok(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                DATABASES_TABLE: {'data': [DB_OPENINGS_SHARED]},
                GAMES_TABLE: {'count': 3},
                SHARED_DATABASES_TABLE: {'data': []},
            })
            resp = client.post(f'/api/databases/shared/{SHARE_TOKEN}/subscribe', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['source_token'] == SHARE_TOKEN
            assert body['database_id'] == DB_OPENINGS['id']
            assert body['name'] == 'Openings'
            assert body['game_count'] == 3
            assert body['owner_name'] == 'Alice A'

    def test_subscribe_idempotent(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                DATABASES_TABLE: {'data': [DB_OPENINGS_SHARED]},
                GAMES_TABLE: {'count': 3},
                SHARED_DATABASES_TABLE: {'data': [SUB_ROW]},
            })
            resp = client.post(f'/api/databases/shared/{SHARE_TOKEN}/subscribe', headers=auth_headers)
            assert resp.status_code == 200

    def test_subscribe_unknown_token_404(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({DATABASES_TABLE: {'data': []}})
            resp = client.post('/api/databases/shared/nope/subscribe', headers=auth_headers)
            assert resp.status_code == 404

    def test_subscribe_requires_auth(self, client):
        resp = client.post(f'/api/databases/shared/{SHARE_TOKEN}/subscribe')
        assert resp.status_code == 401


class TestListSharedDatabases:
    def test_list_resolves_meta(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                SHARED_DATABASES_TABLE: {'data': [SUB_ROW]},
                DATABASES_TABLE: {'data': [DB_OPENINGS_SHARED]},
                GAMES_TABLE: {'count': 2},
            })
            resp = client.get('/api/databases/shared', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert len(body) == 1
            assert body[0]['available'] is True
            assert body[0]['name'] == 'Openings'
            assert body[0]['database_id'] == DB_OPENINGS['id']
            assert body[0]['game_count'] == 2

    def test_list_marks_revoked_unavailable(self, client, auth_headers):
        # Subscription exists but the token no longer resolves (owner revoked).
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({
                SHARED_DATABASES_TABLE: {'data': [SUB_ROW]},
                DATABASES_TABLE: {'data': []},
            })
            resp = client.get('/api/databases/shared', headers=auth_headers)
            body = resp.get_json()
            assert len(body) == 1
            assert body[0]['available'] is False
            assert body[0]['source_token'] == SHARE_TOKEN
            assert body[0]['name'] is None

    def test_list_only_own_subscriptions(self, client, auth_headers):
        other = {**SUB_ROW, 'subscriber_id': USER_B}
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({SHARED_DATABASES_TABLE: {'data': [other]}})
            resp = client.get('/api/databases/shared', headers=auth_headers)
            assert resp.get_json() == []

    def test_list_requires_auth(self, client):
        resp = client.get('/api/databases/shared')
        assert resp.status_code == 401


class TestUnsubscribeSharedDatabase:
    def test_unsubscribe_ok(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({SHARED_DATABASES_TABLE: {'data': [SUB_ROW]}})
            resp = client.delete(f'/api/databases/shared/subscription/{SHARE_TOKEN}', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['success'] is True

    def test_unsubscribe_idempotent(self, client, auth_headers):
        with patch('api.user_databases.supabase') as mock_sb:
            mock_sb.table = make_table({SHARED_DATABASES_TABLE: {'data': []}})
            resp = client.delete(f'/api/databases/shared/subscription/{SHARE_TOKEN}', headers=auth_headers)
            assert resp.status_code == 200

    def test_unsubscribe_requires_auth(self, client):
        resp = client.delete(f'/api/databases/shared/subscription/{SHARE_TOKEN}')
        assert resp.status_code == 401


# ─── MIGRATION SHAPE ──────────────────────────────────────────────────────────

MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations',
    '018_create_user_databases.sql',
)


class TestMigrationShape:
    @pytest.fixture
    def sql(self):
        with open(MIGRATION_PATH, 'r') as f:
            return f.read()

    def test_file_exists(self):
        assert os.path.exists(MIGRATION_PATH)

    def test_creates_user_databases_table(self, sql):
        assert 'CREATE TABLE IF NOT EXISTS user_databases' in sql

    def test_user_id_is_text(self, sql):
        assert re.search(r'user_id\s+TEXT\s+NOT NULL', sql)

    def test_has_soft_delete_and_default_columns(self, sql):
        assert re.search(r'deleted_at\s+TIMESTAMPTZ', sql)
        assert re.search(r'is_default\s+BOOLEAN', sql)

    def test_unique_live_name_index(self, sql):
        assert 'idx_user_databases_user_name_live' in sql
        assert re.search(r'lower\(name\)', sql)
        assert re.search(r'WHERE\s+deleted_at\s+IS\s+NULL', sql, re.IGNORECASE)

    def test_one_default_index(self, sql):
        assert 'idx_user_databases_one_default' in sql

    def test_rls_enabled(self, sql):
        assert re.search(
            r'ALTER\s+TABLE\s+user_databases\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY',
            sql, re.IGNORECASE,
        )

    def test_adds_database_id_to_user_games(self, sql):
        assert re.search(
            r'ALTER\s+TABLE\s+user_games\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+database_id\s+UUID',
            sql, re.IGNORECASE,
        )

    def test_idempotent_backfill(self, sql):
        assert 'NOT EXISTS' in sql
        assert 'INSERT INTO user_databases' in sql


SHARE_MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations',
    '019_add_user_databases_share_token.sql',
)


class TestShareTokenMigrationShape:
    @pytest.fixture
    def sql(self):
        with open(SHARE_MIGRATION_PATH, 'r') as f:
            return f.read()

    def test_file_exists(self):
        assert os.path.exists(SHARE_MIGRATION_PATH)

    def test_adds_share_token_column(self, sql):
        assert re.search(
            r'ALTER\s+TABLE\s+user_databases\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+share_token\s+TEXT',
            sql, re.IGNORECASE,
        )

    def test_unique_partial_index(self, sql):
        assert 'user_databases_share_token_idx' in sql
        assert re.search(r'WHERE\s+share_token\s+IS\s+NOT\s+NULL', sql, re.IGNORECASE)


SUBS_MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations',
    '020_create_user_shared_databases.sql',
)


class TestSubscriptionsMigrationShape:
    @pytest.fixture
    def sql(self):
        with open(SUBS_MIGRATION_PATH, 'r') as f:
            return f.read()

    def test_file_exists(self):
        assert os.path.exists(SUBS_MIGRATION_PATH)

    def test_creates_table(self, sql):
        assert 'CREATE TABLE IF NOT EXISTS user_shared_databases' in sql

    def test_subscriber_and_token_columns(self, sql):
        assert re.search(r'subscriber_id\s+TEXT\s+NOT NULL', sql)
        assert re.search(r'source_token\s+TEXT\s+NOT NULL', sql)

    def test_unique_subscription(self, sql):
        assert re.search(r'UNIQUE\s*\(\s*subscriber_id\s*,\s*source_token\s*\)', sql, re.IGNORECASE)

    def test_rls_enabled(self, sql):
        assert re.search(
            r'ALTER\s+TABLE\s+user_shared_databases\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY',
            sql, re.IGNORECASE,
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
