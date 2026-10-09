"""Tests for the collection-share endpoints (Collection Share — Phase 1).

A user shares their ENTIRE "My Games" collection with one opaque, revocable
token (table user_game_collection_shares, one row per owner). Recipients must be
signed in to browse the collection; only the OG preview (/meta, /thumbnail.png)
is public. Shared views strip the private `notes` field and never leak user_id.
Revoking deletes the row so the token stops resolving → 404 everywhere.

Supabase is mocked per-table so a request that touches both tables (resolve the
token in user_game_collection_shares, then read user_games) sees the right data.
"""

import pytest
from unittest.mock import patch

# Table names, imported from the module under test to stay in sync.
from api.user_games import COLLECTION_SHARES_TABLE as COLLECTION_TABLE, TABLE as GAMES_TABLE

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

OWNER_ID = 'user_owner'
RECIPIENT_ID = 'user_recipient'
TOKEN = 'collection_share_token_abc'

SHARE_ROW = {
    'id': 'share-1111',
    'user_id': OWNER_ID,
    'token': TOKEN,
    'created_at': '2025-01-15T10:00:00+00:00',
}

SAMPLE_PGN = (
    '[Event "Club Night"]\n'
    '[White "Player1"]\n'
    '[Black "Player2"]\n'
    '[Result "1-0"]\n\n'
    '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 1-0\n'
)


def _game(idx: int, **overrides) -> dict:
    row = {
        'id': f'game-{idx}',
        'user_id': OWNER_ID,
        'title': f'Game {idx}',
        'white': 'Player1',
        'black': 'Player2',
        'result': '1-0',
        'date': '2025.01.15',
        'event': 'Club Night',
        'pgn': SAMPLE_PGN,
        'notes': 'my private notes',
        'tags': [],
        'is_favorite': False,
        'source': 'manual',
        'deleted_at': None,
        'created_at': '2025-01-15T10:00:00+00:00',
        'updated_at': '2025-01-15T10:00:00+00:00',
    }
    row.update(overrides)
    return row


# ─── Per-table mock ──────────────────────────────────────────────────────────

class FakeResult:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class FakeBuilder:
    """Chainable mock for supabase.table(name).select()...execute()."""
    def __init__(self, data=None, count=None):
        self._data = list(data or [])
        self._count = count

    def select(self, *a, **k):
        return self

    def insert(self, data, **k):
        self._data = [data] if not isinstance(data, list) else data
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

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return FakeResult(data=self._data, count=self._count)


def make_table(tables: dict):
    """tables maps a table name → dict(data=[...], count=N)."""
    def table(name):
        spec = tables.get(name, {})
        return FakeBuilder(data=spec.get('data'), count=spec.get('count'))
    return table


# ─── Fixtures ──────────────────────────────────────────────────────────────

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
    """@verify_clerk_token is applied at import time — mock the decode. The
    recipient (not the owner) is signed in, to prove shared reads aren't
    owner-gated."""
    with patch('utils.auth._decode_clerk_token', return_value={'sub': RECIPIENT_ID}):
        yield


@pytest.fixture(autouse=True)
def mock_clerk_user():
    """Owner display name comes from Clerk — stub it out."""
    with patch('api.user_games._fetch_clerk_user',
               return_value={'first_name': 'Magnus', 'last_name': 'C'}):
        yield


# ─── MINT ────────────────────────────────────────────────────────────────────

class TestCreateCollectionShare:
    def test_owner_mints_token(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({COLLECTION_TABLE: {'data': []}})
            resp = client.post('/api/games/collection/share', headers=auth_headers)
            assert resp.status_code == 200
            token = resp.get_json()['token']
            assert isinstance(token, str)
            assert len(token) >= 16

    def test_mint_is_idempotent(self, client, auth_headers):
        """A user who already has a share row gets the same token back."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({COLLECTION_TABLE: {'data': [SHARE_ROW]}})
            resp = client.post('/api/games/collection/share', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['token'] == TOKEN

    def test_mint_requires_auth(self, client):
        resp = client.post('/api/games/collection/share')
        assert resp.status_code == 401


# ─── REVOKE ────────────────────────────────────────────────────────────────

class TestRevokeCollectionShare:
    def test_owner_revokes(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({COLLECTION_TABLE: {'data': [SHARE_ROW]}})
            resp = client.delete('/api/games/collection/share', headers=auth_headers)
            assert resp.status_code == 204
            assert resp.data == b''

    def test_revoke_requires_auth(self, client):
        resp = client.delete('/api/games/collection/share')
        assert resp.status_code == 401

    def test_revoke_then_list_404(self, client, auth_headers):
        """After revoke the token no longer resolves (no row) → 404."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({COLLECTION_TABLE: {'data': []}})
            resp = client.get(f'/api/games/collection/shared/{TOKEN}', headers=auth_headers)
            assert resp.status_code == 404


# ─── SHARED LIST (recipient view) ────────────────────────────────────────────

class TestSharedCollectionList:
    def test_signed_in_recipient_lists_games(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [_game(1), _game(2)], 'count': 2},
            })
            resp = client.get(f'/api/games/collection/shared/{TOKEN}', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert len(body['games']) == 2
            assert body['total'] == 2
            assert body['owner_name'] == 'Magnus C'

    def test_list_requires_auth(self, client):
        resp = client.get(f'/api/games/collection/shared/{TOKEN}')
        assert resp.status_code == 401

    def test_list_strips_notes_and_user_id(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [_game(1)], 'count': 1},
            })
            resp = client.get(f'/api/games/collection/shared/{TOKEN}', headers=auth_headers)
            game = resp.get_json()['games'][0]
            assert 'notes' not in game
            assert 'user_id' not in game
            assert game['pgn'] == SAMPLE_PGN  # non-private fields survive

    def test_list_unknown_token_404(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({COLLECTION_TABLE: {'data': []}})
            resp = client.get('/api/games/collection/shared/nope', headers=auth_headers)
            assert resp.status_code == 404

    def test_list_pagination_params_echoed(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [_game(3)], 'count': 25},
            })
            resp = client.get(
                f'/api/games/collection/shared/{TOKEN}?page=2&per_page=10',
                headers=auth_headers,
            )
            body = resp.get_json()
            assert body['page'] == 2
            assert body['per_page'] == 10
            assert body['total'] == 25

    def test_empty_collection_lists_ok(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [], 'count': 0},
            })
            resp = client.get(f'/api/games/collection/shared/{TOKEN}', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['games'] == []


# ─── SHARED SINGLE GAME ──────────────────────────────────────────────────────

class TestSharedCollectionGame:
    def test_fetch_owner_game(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [_game(1)]},
            })
            resp = client.get(
                f'/api/games/collection/shared/{TOKEN}/games/game-1',
                headers=auth_headers,
            )
            assert resp.status_code == 200
            game = resp.get_json()
            assert game['pgn'] == SAMPLE_PGN
            assert 'notes' not in game
            assert 'user_id' not in game

    def test_single_game_requires_auth(self, client):
        resp = client.get(f'/api/games/collection/shared/{TOKEN}/games/game-1')
        assert resp.status_code == 401

    def test_cross_user_game_id_404(self, client, auth_headers):
        """A game id that doesn't belong to the token owner → 404.

        The ownership filter (user_id == owner) matches nothing, so the games
        table resolves empty even though the token is valid.
        """
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': []},
            })
            resp = client.get(
                f'/api/games/collection/shared/{TOKEN}/games/someone-elses-game',
                headers=auth_headers,
            )
            assert resp.status_code == 404

    def test_single_game_unknown_token_404(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({COLLECTION_TABLE: {'data': []}})
            resp = client.get(
                '/api/games/collection/shared/nope/games/game-1',
                headers=auth_headers,
            )
            assert resp.status_code == 404


# ─── PUBLIC META ─────────────────────────────────────────────────────────────

class TestSharedCollectionMeta:
    def test_meta_is_public(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [], 'count': 7},
            })
            resp = client.get(f'/api/games/collection/shared/{TOKEN}/meta')
            assert resp.status_code == 200
            assert 'WWW-Authenticate' not in resp.headers

    def test_meta_returns_owner_and_count(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [], 'count': 7},
            })
            data = client.get(f'/api/games/collection/shared/{TOKEN}/meta').get_json()
            assert data['owner_name'] == 'Magnus C'
            assert data['game_count'] == 7

    def test_meta_never_leaks_game_data(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [], 'count': 7},
            })
            data = client.get(f'/api/games/collection/shared/{TOKEN}/meta').get_json()
            assert 'games' not in data
            assert 'pgn' not in data
            assert 'user_id' not in data

    def test_meta_empty_collection_ok(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [], 'count': 0},
            })
            data = client.get(f'/api/games/collection/shared/{TOKEN}/meta').get_json()
            assert data['game_count'] == 0

    def test_meta_unknown_token_404(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({COLLECTION_TABLE: {'data': []}})
            resp = client.get('/api/games/collection/shared/nope/meta')
            assert resp.status_code == 404
            assert resp.is_json


# ─── PUBLIC THUMBNAIL ────────────────────────────────────────────────────────

class TestSharedCollectionThumbnail:
    def test_thumbnail_renders_most_recent_game(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [_game(1)]},
            })
            resp = client.get(f'/api/games/collection/shared/{TOKEN}/thumbnail.png')
            assert resp.status_code == 200
            assert resp.mimetype == 'image/png'
            assert resp.data.startswith(PNG_MAGIC)
            assert 'WWW-Authenticate' not in resp.headers

    def test_thumbnail_sets_immutable_cache(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': [_game(1)]},
            })
            resp = client.get(f'/api/games/collection/shared/{TOKEN}/thumbnail.png')
            assert resp.headers['Cache-Control'] == 'public, max-age=86400'

    def test_thumbnail_empty_collection_falls_back_to_logo_card(self, client):
        """Empty collection → branded logo card, still a valid PNG (not 404)."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({
                COLLECTION_TABLE: {'data': [SHARE_ROW]},
                GAMES_TABLE: {'data': []},
            })
            resp = client.get(f'/api/games/collection/shared/{TOKEN}/thumbnail.png')
            assert resp.status_code == 200
            assert resp.data.startswith(PNG_MAGIC)

    def test_thumbnail_unknown_token_404(self, client):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = make_table({COLLECTION_TABLE: {'data': []}})
            resp = client.get('/api/games/collection/shared/nope/thumbnail.png')
            assert resp.status_code == 404
            assert resp.is_json


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
