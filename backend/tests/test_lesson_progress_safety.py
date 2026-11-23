"""
Lesson progress safety:
- a completed lesson never goes back to in_progress (both progress endpoints);
- an exercise lesson cannot be completed until all its puzzles are solved (409);
- the per-puzzle solve endpoint rejects an unknown puzzle index.

An in-memory fake Supabase models the PostgREST calls the endpoints make,
including `upsert(..., ignore_duplicates=True)` = INSERT ... ON CONFLICT DO NOTHING.
"""

from unittest.mock import patch

import pytest

USER_ID = 'user_progress_safety'
COURSE = {'id': 'c1', 'slug': 'level-1', 'order_index': 1, 'level': 'beginner'}
THEORY = {'id': 'l-theory', 'lesson_type': 'theory'}
EXERCISE = {'id': 'l-ex', 'lesson_type': 'exercise', 'puzzle_count': 2}


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = []
        self.upsert_args = None
        self.negate = False

    @property
    def not_(self):
        self.negate = True
        return self

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def is_(self, col, val):
        negate, self.negate = self.negate, False
        self.filters.append(lambda r: (r.get(col) is not None) if negate else (r.get(col) is None))
        return self

    def upsert(self, row, on_conflict='', ignore_duplicates=False, **k):
        self.upsert_args = (dict(row), on_conflict.split(','), ignore_duplicates)
        return self

    def execute(self):
        rows = self.db.setdefault(self.table, [])
        if self.upsert_args is None:
            return FakeResult([dict(r) for r in rows if all(f(r) for f in self.filters)])
        row, keys, ignore = self.upsert_args
        existing = next((r for r in rows if all(r.get(k) == row[k] for k in keys)), None)
        if existing is None:
            rows.append(row)
            return FakeResult([dict(row)])
        if ignore:
            return FakeResult([])
        existing.update(row)
        return FakeResult([dict(existing)])


class FakeSupabase:
    def __init__(self, db):
        self.db = db

    def table(self, name):
        return FakeQuery(self.db, name)


@pytest.fixture
def app():
    from flask import Flask
    from api.lessons import lessons_bp
    from api.puzzles import puzzles_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(lessons_bp)
    test_app.register_blueprint(puzzles_bp)
    return test_app


@pytest.fixture
def db():
    return {
        'lessons': [THEORY, EXERCISE],
        'lesson_puzzles': [
            {'id': 'p1', 'lesson_id': 'l-ex', 'order_index': 1},
            {'id': 'p2', 'lesson_id': 'l-ex', 'order_index': 2},
        ],
        'user_progress': [],
        'user_puzzle_progress': [],
    }


@pytest.fixture(autouse=True)
def env(db):
    fake = FakeSupabase(db)
    with patch('utils.auth._decode_clerk_token', return_value={'sub': USER_ID}), \
            patch('api.lessons.supabase', fake), \
            patch('api.puzzles.supabase', fake), \
            patch('api.lessons._capture_lesson_progress'):
        yield


HEADERS = {'Authorization': 'Bearer x'}


def _resolve(lesson):
    return patch('api.lessons.resolve_course_and_lesson', return_value=(COURSE, lesson))


def _post_slug(app, lesson, status):
    with _resolve(lesson):
        return app.test_client().post(
            '/api/learn/level-1/x/progress', json={'status': status}, headers=HEADERS)


def _post_legacy(app, lesson, status):
    return app.test_client().post(
        f"/api/lessons/{lesson['id']}/progress", json={'status': status}, headers=HEADERS)


def _status(db, lesson_id):
    rows = [r for r in db['user_progress'] if r['lesson_id'] == lesson_id]
    assert len(rows) == 1
    return rows[0]['status']


def _solve(db, *puzzle_ids):
    for pid in puzzle_ids:
        db['user_puzzle_progress'].append(
            {'user_id': USER_ID, 'puzzle_id': pid, 'completed_at': '2026-11-23T10:00:00+00:00'})


@pytest.mark.parametrize('post', [_post_slug, _post_legacy])
def test_completed_to_in_progress_is_a_no_op(app, db, post):
    assert post(app, THEORY, 'completed').status_code == 200
    completed_at = db['user_progress'][0]['completed_at']

    resp = post(app, THEORY, 'in_progress')

    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'completed'
    assert _status(db, 'l-theory') == 'completed'
    assert db['user_progress'][0]['completed_at'] == completed_at


@pytest.mark.parametrize('post', [_post_slug, _post_legacy])
def test_first_open_creates_in_progress_row(app, db, post):
    resp = post(app, THEORY, 'in_progress')
    assert resp.status_code == 200
    assert _status(db, 'l-theory') == 'in_progress'
    assert db['user_progress'][0]['started_at'] == 'now()'


def test_first_open_reports_first_start_once(app):
    with patch('api.lessons._capture_lesson_progress') as cap:
        _post_slug(app, THEORY, 'in_progress')
        _post_slug(app, THEORY, 'in_progress')
    assert [c.args[4] for c in cap.call_args_list] == [True, False]


@pytest.mark.parametrize('post', [_post_slug, _post_legacy])
def test_exercise_completion_rejected_without_solved_puzzles(app, db, post):
    _solve(db, 'p1')  # one of two
    resp = post(app, EXERCISE, 'completed')
    assert resp.status_code == 409
    assert resp.get_json()['error'] == 'EXERCISE_NOT_SOLVED'
    assert db['user_progress'] == []


@pytest.mark.parametrize('post', [_post_slug, _post_legacy])
def test_exercise_completion_accepted_with_all_puzzles_solved(app, db, post):
    _solve(db, 'p1', 'p2')
    resp = post(app, EXERCISE, 'completed')
    assert resp.status_code == 200
    assert _status(db, 'l-ex') == 'completed'


def test_exercise_without_puzzle_rows_is_not_blocked(app, db):
    db['lesson_puzzles'] = []
    assert _post_slug(app, EXERCISE, 'completed').status_code == 200


def _solve_via_api(app, index):
    with patch('api.puzzles.resolve_course_and_lesson', return_value=(COURSE, EXERCISE)):
        return app.test_client().post(
            f'/api/learn/level-1/x/puzzles/{index}/complete', json={}, headers=HEADERS)


def test_puzzle_solve_rejects_unknown_index(app, db):
    assert _solve_via_api(app, 3).status_code == 404
    assert _solve_via_api(app, 0).status_code == 404
    assert db['user_puzzle_progress'] == []


def test_lesson_complete_only_when_every_puzzle_is_solved(app, db):
    # Solving the last puzzle first does not complete the lesson.
    assert _solve_via_api(app, 2).get_json()['lesson_complete'] is False
    assert db['user_progress'] == []

    assert _solve_via_api(app, 1).get_json()['lesson_complete'] is True
    assert _status(db, 'l-ex') == 'completed'
