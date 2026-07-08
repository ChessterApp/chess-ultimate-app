"""
Tests for the puzzles API — verifies solution_line is always present in the
response shape (multi-move line when stored, [solution_move] fallback otherwise).
"""

import pytest
from unittest.mock import patch

USER_ID = 'user_puzzle_test'

LESSON = {
    'id': 'lesson-1',
    'title': 'Mate in Two',
    'has_multiple_puzzles': True,
    'puzzle_count': 2,
}

PUZZLE_WITH_LINE = {
    'id': 'puz-1',
    'order_index': 1,
    'fen': '6K1/8/6kq/8/8/8/8/5R2 w - - 0 1',
    'solution_move': 'f1f6',
    'solution_line': ['f1f6', 'g6h5', 'f6h6'],
    'hint_text': None,
}

PUZZLE_NO_LINE = {
    'id': 'puz-2',
    'order_index': 2,
    'fen': '8/8/5k2/5q2/7K/6R1/8/8 w - - 0 1',
    'solution_move': 'g3f3',
    'solution_line': None,
    'hint_text': None,
}


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeBuilder:
    """Chainable Supabase mock that returns preset data for a table."""
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        return FakeResult(list(self._data))


def make_table(table_data):
    """table_data: dict of table_name -> list[row]."""
    def table(name):
        return FakeBuilder(table_data.get(name, []))
    return table


@pytest.fixture
def app():
    from flask import Flask
    from api.puzzles import puzzles_bp
    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(puzzles_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_auth():
    with patch('utils.auth.jwt.decode', return_value={'sub': USER_ID}):
        yield


# ─── ensure_solution_line unit behaviour ──────────────────────────────────────

class TestEnsureSolutionLine:
    def test_keeps_existing_line(self):
        from api.puzzles import ensure_solution_line
        p = ensure_solution_line(dict(PUZZLE_WITH_LINE))
        assert p['solution_line'] == ['f1f6', 'g6h5', 'f6h6']

    def test_falls_back_to_single_move(self):
        from api.puzzles import ensure_solution_line
        p = ensure_solution_line({'solution_move': 'g3f3', 'solution_line': None})
        assert p['solution_line'] == ['g3f3']

    def test_missing_key_falls_back(self):
        from api.puzzles import ensure_solution_line
        p = ensure_solution_line({'solution_move': 'e2e4'})
        assert p['solution_line'] == ['e2e4']

    def test_empty_when_no_move_at_all(self):
        from api.puzzles import ensure_solution_line
        p = ensure_solution_line({'solution_move': None, 'solution_line': None})
        assert p['solution_line'] == []


# ─── list endpoint ────────────────────────────────────────────────────────────

class TestGetLessonPuzzles:
    def test_includes_solution_line_for_all(self, client, auth_headers):
        table_data = {
            'lesson_puzzles': [PUZZLE_WITH_LINE, PUZZLE_NO_LINE],
            'user_puzzle_progress': [],
        }
        with patch('api.puzzles.supabase') as sb, \
                patch('api.puzzles.resolve_course_and_lesson', return_value=(None, LESSON)):
            sb.table = make_table(table_data)
            resp = client.get('/api/learn/course/lesson/puzzles', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            by_id = {p['id']: p for p in body['puzzles']}
            assert by_id['puz-1']['solution_line'] == ['f1f6', 'g6h5', 'f6h6']
            # NULL line falls back to [solution_move]
            assert by_id['puz-2']['solution_line'] == ['g3f3']

    def test_no_auth(self, client):
        resp = client.get('/api/learn/course/lesson/puzzles')
        assert resp.status_code == 401


# ─── single puzzle endpoint ───────────────────────────────────────────────────

class TestGetSinglePuzzle:
    def test_single_puzzle_has_line(self, client, auth_headers):
        table_data = {
            'lesson_puzzles': [PUZZLE_WITH_LINE],
            'user_puzzle_progress': [],
        }
        with patch('api.puzzles.supabase') as sb, \
                patch('api.puzzles.resolve_course_and_lesson', return_value=(None, LESSON)):
            sb.table = make_table(table_data)
            resp = client.get('/api/learn/course/lesson/puzzles/1', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['solution_line'] == ['f1f6', 'g6h5', 'f6h6']

    def test_single_puzzle_fallback(self, client, auth_headers):
        table_data = {
            'lesson_puzzles': [PUZZLE_NO_LINE],
            'user_puzzle_progress': [],
        }
        with patch('api.puzzles.supabase') as sb, \
                patch('api.puzzles.resolve_course_and_lesson', return_value=(None, LESSON)):
            sb.table = make_table(table_data)
            resp = client.get('/api/learn/course/lesson/puzzles/2', headers=auth_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['solution_line'] == ['g3f3']
