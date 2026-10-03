"""
Tests for GET /api/courses/progress (per-user course progress aggregation).

Uses a Flask test client with a table-aware mocked Supabase and mocked JWT auth.
Covers: all lessons complete -> 100; partial -> correct rounded %; no progress
rows -> zeros; course with zero lessons -> zeros (no divide-by-zero).
"""

import pytest
from unittest.mock import patch

USER_ID = 'user_progress_test'

# Two courses. Course A has 4 lessons across 2 modules; course B has 0 lessons.
COURSES = [
    {'id': 'course-a', 'title': 'Course A', 'order_index': 1},
    {'id': 'course-b', 'title': 'Course B', 'order_index': 2},
]

MODULES = [
    {'id': 'mod-a1', 'course_id': 'course-a'},
    {'id': 'mod-a2', 'course_id': 'course-a'},
    # course-b intentionally has no modules -> zero lessons
]

LESSONS = [
    {'id': 'lesson-1', 'module_id': 'mod-a1'},
    {'id': 'lesson-2', 'module_id': 'mod-a1'},
    {'id': 'lesson-3', 'module_id': 'mod-a2'},
    {'id': 'lesson-4', 'module_id': 'mod-a2'},
]


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    """Table-aware chainable mock. Filters `.in_()` against the seeded rows."""

    def __init__(self, rows, progress_rows):
        self._rows = rows
        self._progress_rows = progress_rows
        self._name = None
        self._in_filters = {}

    def select(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, column, values):
        self._in_filters[column] = set(values)
        return self

    def execute(self):
        rows = list(self._rows)
        for column, allowed in self._in_filters.items():
            rows = [r for r in rows if r.get(column) in allowed]
        return FakeResult(rows)


def make_supabase(progress_rows):
    """Return a fake supabase whose .table(name) serves the right dataset."""
    datasets = {
        'courses': COURSES,
        'modules': MODULES,
        'lessons': LESSONS,
        'user_progress': progress_rows,
    }

    class FakeSupabase:
        def table(self, name):
            return FakeTable(datasets.get(name, []), progress_rows)

    return FakeSupabase()


@pytest.fixture
def app():
    from flask import Flask
    from api.lessons import lessons_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(lessons_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_jwt():
    with patch('utils.auth._decode_clerk_token', return_value={'sub': USER_ID}):
        yield


@pytest.fixture(autouse=True)
def clear_courses_cache():
    """The endpoint uses get_cached_courses(); reset the module cache each test
    so the patched supabase is actually consulted."""
    import api.lessons as lessons
    lessons._cache['courses'] = None
    lessons._cache['courses_time'] = 0
    yield
    lessons._cache['courses'] = None
    lessons._cache['courses_time'] = 0


def _get_progress(client, auth_headers, progress_rows):
    with patch('api.lessons.supabase', make_supabase(progress_rows)):
        resp = client.get('/api/courses/progress', headers=auth_headers)
    return resp


def test_requires_auth(client):
    resp = client.get('/api/courses/progress')
    assert resp.status_code == 401


def test_all_lessons_complete_is_100(client, auth_headers):
    progress = [{'lesson_id': lid, 'status': 'completed'}
                for lid in ('lesson-1', 'lesson-2', 'lesson-3', 'lesson-4')]
    resp = _get_progress(client, auth_headers, progress)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['course-a']['totalLessons'] == 4
    assert body['course-a']['completedLessons'] == 4
    assert body['course-a']['progress'] == 100


def test_partial_progress_rounded(client, auth_headers):
    # 1 of 4 complete -> 25%
    progress = [{'lesson_id': 'lesson-1', 'status': 'completed'}]
    resp = _get_progress(client, auth_headers, progress)
    body = resp.get_json()
    assert body['course-a']['completedLessons'] == 1
    assert body['course-a']['totalLessons'] == 4
    assert body['course-a']['progress'] == 25


def test_in_progress_status_not_counted(client, auth_headers):
    # Only 'completed' counts; in_progress rows are ignored.
    progress = [
        {'lesson_id': 'lesson-1', 'status': 'completed'},
        {'lesson_id': 'lesson-2', 'status': 'in_progress'},
    ]
    resp = _get_progress(client, auth_headers, progress)
    body = resp.get_json()
    assert body['course-a']['completedLessons'] == 1
    assert body['course-a']['progress'] == 25


def test_no_progress_rows_is_zero(client, auth_headers):
    resp = _get_progress(client, auth_headers, [])
    body = resp.get_json()
    assert body['course-a']['completedLessons'] == 0
    assert body['course-a']['totalLessons'] == 4
    assert body['course-a']['progress'] == 0


def test_course_with_zero_lessons_is_zero(client, auth_headers):
    # course-b has no modules/lessons -> zeros, no divide-by-zero.
    resp = _get_progress(client, auth_headers, [])
    body = resp.get_json()
    assert 'course-b' in body
    assert body['course-b']['totalLessons'] == 0
    assert body['course-b']['completedLessons'] == 0
    assert body['course-b']['progress'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
