"""
Integration test: create game via PGN import → verify it appears in list.

Tests the full backend flow:
1. POST /api/games with PGN → game is created with auto-extracted headers
2. GET /api/games → newly created game appears in the list
3. GET /api/games/<id> → game can be fetched individually
4. Metadata from PGN headers is correctly populated
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from copy import deepcopy

USER_ID = 'user_pgn_import_test'

FULL_PGN = (
    '[Event "Candidates 2024"]\n'
    '[White "Gukesh D"]\n'
    '[Black "Nakamura, Hikaru"]\n'
    '[Result "1-0"]\n'
    '[Date "2024.04.05"]\n'
    '[WhiteElo "2758"]\n'
    '[BlackElo "2794"]\n'
    '[ECO "C48"]\n'
    '[Opening "Four Knights Game"]\n'
    '\n'
    '1. e4 e5 2. Nf3 Nc6 3. Nc3 Nf6 4. Bb5 Nd4 1-0'
)

MINIMAL_PGN = '1. e4 e5 2. Nf3 Nc6 *'


class FakeQueryResult:
    """Mimics Supabase query result."""
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class StatefulFakeTable:
    """A stateful fake Supabase table that remembers inserted rows,
    enabling create-then-list integration tests."""

    def __init__(self):
        self._rows = []
        self._next_id = 1
        self._filter_user_id = None
        self._filter_result = None
        self._search_query = None
        self._mode = None  # 'select', 'insert', 'update', 'delete'
        self._target_id = None
        self._update_data = None

    def _reset_filters(self):
        self._filter_user_id = None
        self._filter_result = None
        self._search_query = None
        self._mode = None
        self._target_id = None
        self._update_data = None

    def select(self, *args, **kwargs):
        self._mode = 'select'
        return self

    def insert(self, data, **kwargs):
        self._mode = 'insert'
        if isinstance(data, list):
            new_rows = []
            for row in data:
                row_copy = dict(row)
                row_copy['id'] = f'gen-{self._next_id}'
                self._next_id += 1
                self._rows.append(row_copy)
                new_rows.append(row_copy)
            self._insert_data = new_rows
        else:
            row_copy = dict(data)
            row_copy['id'] = f'gen-{self._next_id}'
            self._next_id += 1
            self._rows.append(row_copy)
            self._insert_data = [row_copy]
        return self

    def update(self, data, **kwargs):
        self._mode = 'update'
        self._update_data = data
        return self

    def delete(self, **kwargs):
        self._mode = 'delete'
        return self

    def eq(self, field, value):
        if field == 'user_id':
            self._filter_user_id = value
        elif field == 'id':
            self._target_id = value
        elif field == 'result':
            self._filter_result = value
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

    def execute(self):
        if self._mode == 'insert':
            result = FakeQueryResult(data=self._insert_data)
            self._reset_filters()
            return result

        if self._mode == 'select':
            rows = list(self._rows)
            if self._filter_user_id:
                rows = [r for r in rows if r.get('user_id') == self._filter_user_id]
            if self._target_id:
                rows = [r for r in rows if r.get('id') == self._target_id]
            if self._filter_result:
                rows = [r for r in rows if r.get('result') == self._filter_result]
            # Filter out soft-deleted
            rows = [r for r in rows if not r.get('deleted_at')]
            result = FakeQueryResult(data=rows, count=len(rows))
            self._reset_filters()
            return result

        if self._mode == 'update':
            for row in self._rows:
                if self._target_id and row.get('id') == self._target_id:
                    row.update(self._update_data)
                    result = FakeQueryResult(data=[row])
                    self._reset_filters()
                    return result
            result = FakeQueryResult(data=[])
            self._reset_filters()
            return result

        if self._mode == 'delete':
            result = FakeQueryResult(data=[])
            self._reset_filters()
            return result

        self._reset_filters()
        return FakeQueryResult(data=[])


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
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_jwt():
    with patch('utils.auth.jwt.decode', return_value={'sub': USER_ID}):
        yield


@pytest.fixture
def fake_table():
    """Provides a stateful fake table for integration testing."""
    return StatefulFakeTable()


class TestPgnImportThenListFlow:
    """Integration: create a game via PGN import, then verify it appears in the list."""

    def test_create_and_list(self, client, auth_headers, fake_table):
        """Full flow: POST game with PGN, then GET games list, verify it's there."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            # Step 1: Create game via PGN import
            resp = client.post('/api/games',
                               data=json.dumps({'pgn': FULL_PGN, 'source': 'pgn_import'}),
                               headers=auth_headers)
            assert resp.status_code == 201
            created = resp.get_json()
            assert 'id' in created
            game_id = created['id']

            # Step 2: List all games — should contain the newly created game
            resp = client.get('/api/games', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['total'] >= 1

            game_ids = [g['id'] for g in body['games']]
            assert game_id in game_ids

    def test_created_game_has_extracted_headers(self, client, auth_headers, fake_table):
        """Verify that PGN headers are auto-extracted into game metadata."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            resp = client.post('/api/games',
                               data=json.dumps({'pgn': FULL_PGN, 'source': 'pgn_import'}),
                               headers=auth_headers)
            assert resp.status_code == 201
            game = resp.get_json()

            # Verify auto-extracted fields from PGN headers
            assert game.get('white') == 'Gukesh D'
            assert game.get('black') == 'Nakamura, Hikaru'
            assert game.get('white_elo') == 2758
            assert game.get('black_elo') == 2794
            assert game.get('result') == '1-0'
            assert game.get('date') == '2024.04.05'
            assert game.get('event') == 'Candidates 2024'
            assert game.get('eco') == 'C48'

    def test_created_game_retrievable_by_id(self, client, auth_headers, fake_table):
        """After PGN import, the game should be fetchable by its ID."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            # Create
            resp = client.post('/api/games',
                               data=json.dumps({'pgn': FULL_PGN}),
                               headers=auth_headers)
            assert resp.status_code == 201
            game_id = resp.get_json()['id']

            # Fetch by ID
            resp = client.get(f'/api/games/{game_id}', headers=auth_headers)
            assert resp.status_code == 200
            game = resp.get_json()
            assert game['id'] == game_id
            assert game['pgn'] == FULL_PGN

    def test_multiple_pgn_imports_all_appear_in_list(self, client, auth_headers, fake_table):
        """Import multiple games via PGN, verify all appear in the list."""
        pgns = [
            FULL_PGN,
            '[White "Carlsen"]\n[Black "Ding"]\n[Result "1/2-1/2"]\n\n1. d4 d5 *',
            MINIMAL_PGN,
        ]

        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            created_ids = []
            for pgn in pgns:
                resp = client.post('/api/games',
                                   data=json.dumps({'pgn': pgn, 'source': 'pgn_import'}),
                                   headers=auth_headers)
                assert resp.status_code == 201
                created_ids.append(resp.get_json()['id'])

            # List all games
            resp = client.get('/api/games', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['total'] >= 3

            listed_ids = [g['id'] for g in body['games']]
            for cid in created_ids:
                assert cid in listed_ids

    def test_minimal_pgn_import(self, client, auth_headers, fake_table):
        """A minimal PGN (no headers) should still create a valid game."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            resp = client.post('/api/games',
                               data=json.dumps({'pgn': MINIMAL_PGN, 'source': 'pgn_import'}),
                               headers=auth_headers)
            assert resp.status_code == 201
            game = resp.get_json()
            assert game['pgn'] == MINIMAL_PGN
            assert game['source'] == 'pgn_import'

    def test_metadata_override_takes_precedence(self, client, auth_headers, fake_table):
        """User-provided metadata should override PGN-extracted headers."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            resp = client.post('/api/games',
                               data=json.dumps({
                                   'pgn': FULL_PGN,
                                   'source': 'pgn_import',
                                   'white': 'Custom White Name',
                                   'title': 'My Title',
                               }),
                               headers=auth_headers)
            assert resp.status_code == 201
            game = resp.get_json()
            # User-provided values should be present
            assert game.get('white') == 'Custom White Name'
            assert game.get('title') == 'My Title'

    def test_imported_game_not_in_list_after_delete(self, client, auth_headers, fake_table):
        """After deleting an imported game, it should not appear in the list."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            # Create
            resp = client.post('/api/games',
                               data=json.dumps({'pgn': FULL_PGN, 'source': 'pgn_import'}),
                               headers=auth_headers)
            assert resp.status_code == 201
            game_id = resp.get_json()['id']

            # Delete
            resp = client.delete(f'/api/games/{game_id}', headers=auth_headers)
            assert resp.status_code == 200

            # List should be empty (soft-deleted game excluded)
            resp = client.get('/api/games', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            listed_ids = [g['id'] for g in body['games']]
            assert game_id not in listed_ids

    def test_empty_pgn_rejected(self, client, auth_headers, fake_table):
        """Empty PGN should be rejected with 400."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            resp = client.post('/api/games',
                               data=json.dumps({'pgn': '', 'source': 'pgn_import'}),
                               headers=auth_headers)
            assert resp.status_code == 400

    def test_missing_pgn_rejected(self, client, auth_headers, fake_table):
        """Missing PGN field should be rejected with 400."""
        with patch('api.user_games.supabase') as mock_sb:
            mock_sb.table = lambda name: fake_table

            resp = client.post('/api/games',
                               data=json.dumps({'source': 'pgn_import', 'title': 'No PGN'}),
                               headers=auth_headers)
            assert resp.status_code == 400


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
