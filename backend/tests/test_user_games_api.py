"""
Tests for the User Games API (/api/games) blueprint.

Uses Flask test client with mocked Supabase and JWT auth.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

SAMPLE_PGN = (
    '[Event "Test Game"]\n'
    '[White "Player1"]\n'
    '[Black "Player2"]\n'
    '[Result "1-0"]\n'
    '[WhiteElo "2100"]\n'
    '[BlackElo "1900"]\n'
    '[Date "2025.01.15"]\n'
    '[ECO "B01"]\n'
    '\n'
    '1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 1-0'
)

SAMPLE_PGN_MINIMAL = '1. e4 e5 2. Nf3 Nc6 *'

USER_ID = 'user_abc'

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
    'pgn': SAMPLE_PGN,
    'notes': None,
    'tags': [],
    'is_favorite': False,
    'source': 'manual',
    'deleted_at': None,
    'created_at': '2025-01-15T10:00:00+00:00',
    'updated_at': '2025-01-15T10:00:00+00:00',
}


class FakeQueryResult:
    """Mimics Supabase query result."""
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class FakeQueryBuilder:
    """Chainable mock for Supabase table().select()...execute() pattern."""
    def __init__(self, data=None, count=None):
        self._data = data or []
        self._count = count

    def select(self, *args, **kwargs):
        return self

    def insert(self, data, **kwargs):
        if isinstance(data, list):
            self._data = [{**row, 'id': f'new-{i}'} for i, row in enumerate(data)]
        else:
            self._data = [{**data, 'id': 'new-game-id'}]
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

    def or_(self, *args, **kwargs):
        return self

    def contains(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def upsert(self, *args, **kwargs):
        return self

    def execute(self):
        return FakeQueryResult(data=self._data, count=self._count)


def _make_fake_table(data=None, count=None):
    """Create a fake supabase.table() that returns a FakeQueryBuilder."""
    def table(name):
        return FakeQueryBuilder(data=data, count=count)
    return table


@pytest.fixture
def app():
    """Create a minimal Flask app with the user_games blueprint."""
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
    """Provide Authorization header that passes verify_clerk_token."""
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_jwt():
    """Mock JWT decode to always return our test user.
    This is needed because @verify_clerk_token is applied at import time."""
    with patch('utils.auth.jwt.decode', return_value={'sub': USER_ID}):
        yield


# ─── LIST GAMES ──────────────────────────────────────────────────────────────

class TestListGames:
    def test_list_games_success(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[SAMPLE_GAME_ROW], count=1)
            resp = client.get('/api/games', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['total'] == 1
            assert body['page'] == 1
            assert body['per_page'] == 20
            assert len(body['games']) == 1
            assert body['games'][0]['id'] == SAMPLE_GAME_ROW['id']

    def test_list_games_empty(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[], count=0)
            resp = client.get('/api/games', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['total'] == 0
            assert body['games'] == []

    def test_list_games_pagination_params(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[], count=0)
            resp = client.get('/api/games?page=2&per_page=5', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['page'] == 2
            assert body['per_page'] == 5

    def test_list_games_per_page_clamped(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[], count=0)
            resp = client.get('/api/games?per_page=999', headers=auth_headers)
            body = resp.get_json()
            assert body['per_page'] == 100

    def test_list_games_with_search(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[SAMPLE_GAME_ROW], count=1)
            resp = client.get('/api/games?q=Player1', headers=auth_headers)
            assert resp.status_code == 200

    def test_list_games_filter_result(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[SAMPLE_GAME_ROW], count=1)
            resp = client.get('/api/games?result=1-0', headers=auth_headers)
            assert resp.status_code == 200

    def test_list_games_filter_favorite(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[], count=0)
            resp = client.get('/api/games?favorite=true', headers=auth_headers)
            assert resp.status_code == 200

    def test_list_games_filter_tag(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[], count=0)
            resp = client.get('/api/games?tag=blitz', headers=auth_headers)
            assert resp.status_code == 200

    def test_list_games_no_auth(self, client):
        resp = client.get('/api/games')
        assert resp.status_code == 401


# ─── CREATE GAME ─────────────────────────────────────────────────────────────

class TestCreateGame:
    def test_create_game_with_full_pgn(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'id': 'new-game-id'}])
            resp = client.post('/api/games',
                               data=json.dumps({'pgn': SAMPLE_PGN}),
                               headers=auth_headers)
            assert resp.status_code == 201
            body = resp.get_json()
            assert 'id' in body

    def test_create_game_with_metadata_override(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'title': 'Custom Title'}])
            resp = client.post('/api/games',
                               data=json.dumps({'pgn': SAMPLE_PGN, 'title': 'Custom Title'}),
                               headers=auth_headers)
            assert resp.status_code == 201

    def test_create_game_minimal_pgn(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{'id': 'new-game-id', 'pgn': SAMPLE_PGN_MINIMAL}])
            resp = client.post('/api/games',
                               data=json.dumps({'pgn': SAMPLE_PGN_MINIMAL}),
                               headers=auth_headers)
            assert resp.status_code == 201

    def test_create_game_missing_pgn(self, client, auth_headers):
        resp = client.post('/api/games',
                           data=json.dumps({'title': 'No PGN'}),
                           headers=auth_headers)
        assert resp.status_code == 400
        assert 'pgn is required' in resp.get_json()['error']

    def test_create_game_empty_body(self, client, auth_headers):
        resp = client.post('/api/games',
                           data=json.dumps({}),
                           headers=auth_headers)
        assert resp.status_code == 400

    def test_create_game_invalid_pgn(self, client, auth_headers):
        # python-chess reads_game returns a game even for gibberish (with * result)
        # Only truly empty string returns None
        resp = client.post('/api/games',
                           data=json.dumps({'pgn': ''}),
                           headers=auth_headers)
        assert resp.status_code == 400


# ─── GET GAME ────────────────────────────────────────────────────────────────

class TestGetGame:
    def test_get_game_success(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[SAMPLE_GAME_ROW])
            resp = client.get(f'/api/games/{SAMPLE_GAME_ROW["id"]}', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['id'] == SAMPLE_GAME_ROW['id']
            assert body['pgn'] == SAMPLE_PGN

    def test_get_game_not_found(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[])
            resp = client.get('/api/games/nonexistent-id', headers=auth_headers)
            assert resp.status_code == 404


# ─── UPDATE GAME ─────────────────────────────────────────────────────────────

class TestUpdateGame:
    def test_update_game_title(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            updated = {**SAMPLE_GAME_ROW, 'title': 'Updated Title'}
            mock_sb.table = _make_fake_table(data=[updated])
            resp = client.put(f'/api/games/{SAMPLE_GAME_ROW["id"]}',
                              data=json.dumps({'title': 'Updated Title'}),
                              headers=auth_headers)
            assert resp.status_code == 200

    def test_update_game_favorite(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            updated = {**SAMPLE_GAME_ROW, 'is_favorite': True}
            mock_sb.table = _make_fake_table(data=[updated])
            resp = client.put(f'/api/games/{SAMPLE_GAME_ROW["id"]}',
                              data=json.dumps({'is_favorite': True}),
                              headers=auth_headers)
            assert resp.status_code == 200

    def test_update_game_not_found(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[])
            resp = client.put('/api/games/nonexistent-id',
                              data=json.dumps({'title': 'X'}),
                              headers=auth_headers)
            assert resp.status_code == 404

    def test_update_game_no_data(self, client, auth_headers):
        resp = client.put(f'/api/games/{SAMPLE_GAME_ROW["id"]}',
                          data=json.dumps({}),
                          headers=auth_headers)
        assert resp.status_code == 400

    def test_update_game_no_valid_fields(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[SAMPLE_GAME_ROW])
            resp = client.put(f'/api/games/{SAMPLE_GAME_ROW["id"]}',
                              data=json.dumps({'unknown_field': 'value'}),
                              headers=auth_headers)
            assert resp.status_code == 400
            assert 'No valid fields' in resp.get_json()['error']


# ─── DELETE GAME ─────────────────────────────────────────────────────────────

class TestDeleteGame:
    def test_delete_game_success(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[SAMPLE_GAME_ROW])
            resp = client.delete(f'/api/games/{SAMPLE_GAME_ROW["id"]}', headers=auth_headers)
            assert resp.status_code == 200
            assert resp.get_json()['success'] is True

    def test_delete_game_not_found(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[])
            resp = client.delete('/api/games/nonexistent-id', headers=auth_headers)
            assert resp.status_code == 404


# ─── IMPORT LOCAL ────────────────────────────────────────────────────────────

class TestImportLocal:
    def test_import_single_game(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'source': 'local_import'}])
            resp = client.post('/api/games/import-local',
                               data=json.dumps({'games': [{'pgn': SAMPLE_PGN}]}),
                               headers=auth_headers)
            assert resp.status_code == 201
            body = resp.get_json()
            assert body['imported'] == 1
            assert body['errors'] == []

    def test_import_multiple_games(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            rows = [
                {**SAMPLE_GAME_ROW, 'id': f'new-{i}'}
                for i in range(3)
            ]
            mock_sb.table = _make_fake_table(data=rows)
            games = [{'pgn': SAMPLE_PGN} for _ in range(3)]
            resp = client.post('/api/games/import-local',
                               data=json.dumps({'games': games}),
                               headers=auth_headers)
            assert resp.status_code == 201
            body = resp.get_json()
            assert body['imported'] == 3

    def test_import_skips_missing_pgn(self, client, auth_headers):
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = _make_fake_table(data=[{**SAMPLE_GAME_ROW, 'id': 'new-0'}])
            games = [
                {'pgn': SAMPLE_PGN},
                {'title': 'no pgn'},
            ]
            resp = client.post('/api/games/import-local',
                               data=json.dumps({'games': games}),
                               headers=auth_headers)
            assert resp.status_code == 201
            body = resp.get_json()
            assert body['imported'] == 1
            assert len(body['errors']) == 1
            assert body['errors'][0]['index'] == 1
            assert 'missing pgn' in body['errors'][0]['error']

    def test_import_missing_games_array(self, client, auth_headers):
        resp = client.post('/api/games/import-local',
                           data=json.dumps({'data': 'wrong'}),
                           headers=auth_headers)
        assert resp.status_code == 400

    def test_import_empty_games_array(self, client, auth_headers):
        resp = client.post('/api/games/import-local',
                           data=json.dumps({'games': []}),
                           headers=auth_headers)
        assert resp.status_code == 400
        assert 'empty' in resp.get_json()['error']

    def test_import_not_array(self, client, auth_headers):
        resp = client.post('/api/games/import-local',
                           data=json.dumps({'games': 'not an array'}),
                           headers=auth_headers)
        assert resp.status_code == 400


# ─── PGN HEADER EXTRACTION ──────────────────────────────────────────────────

class TestPgnHeaderExtraction:
    def test_extract_headers_from_full_pgn(self):
        from api.user_games import _extract_pgn_headers
        headers = _extract_pgn_headers(SAMPLE_PGN)
        assert headers['white'] == 'Player1'
        assert headers['black'] == 'Player2'
        assert headers['white_elo'] == 2100
        assert headers['black_elo'] == 1900
        assert headers['result'] == '1-0'
        assert headers['date'] == '2025.01.15'
        assert headers['event'] == 'Test Game'
        assert headers['eco'] == 'B01'

    def test_extract_headers_minimal_pgn(self):
        from api.user_games import _extract_pgn_headers
        headers = _extract_pgn_headers(SAMPLE_PGN_MINIMAL)
        # Minimal PGN: python-chess fills in defaults with '?' which we skip
        assert 'white' not in headers

    def test_extract_headers_empty_string(self):
        from api.user_games import _extract_pgn_headers
        headers = _extract_pgn_headers('')
        assert headers == {}

    def test_extract_headers_skips_question_marks(self):
        from api.user_games import _extract_pgn_headers
        pgn = '[White "?"]\n[Black "Carlsen"]\n\n1. e4 *'
        headers = _extract_pgn_headers(pgn)
        assert 'white' not in headers
        assert headers['black'] == 'Carlsen'

    def test_extract_headers_invalid_elo_ignored(self):
        from api.user_games import _extract_pgn_headers
        pgn = '[WhiteElo "abc"]\n[BlackElo "1500"]\n\n1. e4 *'
        headers = _extract_pgn_headers(pgn)
        assert 'white_elo' not in headers
        assert headers['black_elo'] == 1500


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
