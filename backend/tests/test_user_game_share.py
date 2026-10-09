"""Tests for the My Games share-token endpoints (Phase 3a).

A saved game becomes sharable only when its owner mints a token. The owner can
revoke it; recipients must be signed in to fetch the game itself. Only the OG
preview metadata endpoint is public — and it must never leak pgn/moves/user_id.

Supabase is mocked the same way as test_user_games_api.py.
"""

import json
import pytest
from unittest.mock import patch

USER_ID = 'user_owner'
TOKEN = 'abc123_share_token'

SAMPLE_GAME_ROW = {
    'id': '11111111-1111-1111-1111-111111111111',
    'user_id': USER_ID,
    'title': 'My Scandinavian',
    'white': 'Player1',
    'black': 'Player2',
    'white_elo': 2100,
    'black_elo': 1900,
    'result': '1-0',
    'date': '2025.01.15',
    'event': 'Test Game',
    'eco': 'B01',
    'opening_name': None,
    'pgn': '[White "Player1"]\n\n1. e4 e5 1-0',
    'notes': None,
    'tags': [],
    'is_favorite': False,
    'source': 'manual',
    'share_token': None,
    'deleted_at': None,
    'created_at': '2025-01-15T10:00:00+00:00',
    'updated_at': '2025-01-15T10:00:00+00:00',
}


class FakeQueryResult:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class FakeQueryBuilder:
    """Chainable mock for supabase table().select()...execute()."""
    def __init__(self, data=None, count=None):
        self._data = data or []
        self._count = count

    def select(self, *args, **kwargs):
        return self

    def insert(self, data, **kwargs):
        self._data = [data] if not isinstance(data, list) else data
        return self

    def update(self, data, **kwargs):
        if self._data:
            self._data = [{**self._data[0], **data}]
        return self

    def delete(self, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def is_(self, *args, **kwargs):
        return self

    def execute(self):
        return FakeQueryResult(data=self._data, count=self._count)


def _make_fake_table(data=None, count=None):
    def table(name):
        return FakeQueryBuilder(data=data, count=count)
    return table


@pytest.fixture
def app():
    from flask import Flask
    from api.user_games import user_games_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(user_games_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_jwt():
    """@verify_clerk_token is applied at import time — mock the decode."""
    with patch('utils.auth._decode_clerk_token', return_value={'sub': USER_ID}):
        yield


# ─── CREATE TOKEN ────────────────────────────────────────────────────────────

class TestCreateShareToken:
    def test_owner_mints_token(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': None}])
            resp = client.post(f'/api/games/{SAMPLE_GAME_ROW["id"]}/share', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['share_token']
            assert isinstance(body['share_token'], str)
            assert len(body['share_token']) >= 16

    def test_create_is_idempotent(self, client, auth_headers):
        """A row that already has a token returns the same token unchanged."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': TOKEN}])
            resp = client.post(f'/api/games/{SAMPLE_GAME_ROW["id"]}/share', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['share_token'] == TOKEN

    def test_non_owner_gets_404(self, client, auth_headers):
        """Ownership filter finds nothing → 404 (same as update/delete)."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[])
            resp = client.post(f'/api/games/{SAMPLE_GAME_ROW["id"]}/share', headers=auth_headers)
            assert resp.status_code == 404

    def test_create_requires_auth(self, client):
        resp = client.post(f'/api/games/{SAMPLE_GAME_ROW["id"]}/share')
        assert resp.status_code == 401


# ─── REVOKE TOKEN ────────────────────────────────────────────────────────────

class TestRevokeShareToken:
    def test_owner_revokes(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': TOKEN}])
            resp = client.delete(f'/api/games/{SAMPLE_GAME_ROW["id"]}/share', headers=auth_headers)
            assert resp.status_code == 204
            assert resp.data == b''

    def test_revoke_non_owner_404(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[])
            resp = client.delete(f'/api/games/{SAMPLE_GAME_ROW["id"]}/share', headers=auth_headers)
            assert resp.status_code == 404

    def test_revoke_requires_auth(self, client):
        resp = client.delete(f'/api/games/{SAMPLE_GAME_ROW["id"]}/share')
        assert resp.status_code == 401

    def test_revoke_then_shared_get_404(self, client, auth_headers):
        """After revoke the token no longer resolves (lookup returns nothing)."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': TOKEN}])
            assert client.delete(
                f'/api/games/{SAMPLE_GAME_ROW["id"]}/share', headers=auth_headers
            ).status_code == 204
        # A revoked token no longer matches any row.
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[])
            resp = client.get(f'/api/games/shared/{TOKEN}', headers=auth_headers)
            assert resp.status_code == 404


# ─── SHARED GET (recipient view) ─────────────────────────────────────────────

class TestGetSharedGame:
    def test_signed_in_recipient_gets_game(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': TOKEN}])
            resp = client.get(f'/api/games/shared/{TOKEN}', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['pgn'] == SAMPLE_GAME_ROW['pgn']
            assert body['white'] == 'Player1'

    def test_shared_get_requires_auth(self, client):
        resp = client.get(f'/api/games/shared/{TOKEN}')
        assert resp.status_code == 401

    def test_shared_get_never_contains_user_id(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': TOKEN}])
            resp = client.get(f'/api/games/shared/{TOKEN}', headers=auth_headers)
            assert resp.status_code == 200
            assert 'user_id' not in resp.get_json()

    def test_shared_get_unknown_token_404(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[])
            resp = client.get('/api/games/shared/does-not-exist', headers=auth_headers)
            assert resp.status_code == 404


# ─── PUBLIC META ─────────────────────────────────────────────────────────────

class TestSharedGameMeta:
    def test_meta_is_public(self, client):
        """No Authorization header → still 200."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': TOKEN}])
            resp = client.get(f'/api/games/shared/{TOKEN}/meta')
            assert resp.status_code == 200
            assert 'WWW-Authenticate' not in resp.headers

    def test_meta_returns_header_fields(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': TOKEN}])
            data = client.get(f'/api/games/shared/{TOKEN}/meta').get_json()
            assert data['white'] == 'Player1'
            assert data['black'] == 'Player2'
            assert data['result'] == '1-0'
            assert data['event'] == 'Test Game'
            assert data['date'] == '2025.01.15'

    def test_meta_falls_back_to_title_when_no_event(self, client):
        row = {**SAMPLE_GAME_ROW, 'share_token': TOKEN, 'event': None, 'title': 'Club Night'}
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[row])
            data = client.get(f'/api/games/shared/{TOKEN}/meta').get_json()
            assert data['event'] == 'Club Night'

    def test_meta_never_leaks_pgn_moves_user_id_or_id(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'share_token': TOKEN}])
            data = client.get(f'/api/games/shared/{TOKEN}/meta').get_json()
            assert 'pgn' not in data
            assert 'moves' not in data
            assert 'user_id' not in data
            assert 'id' not in data

    def test_meta_unknown_token_404(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[])
            resp = client.get('/api/games/shared/nope/meta')
            assert resp.status_code == 404
            assert resp.is_json


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
