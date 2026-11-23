"""
Tests for GET /api/gamification/derived-profile (lesson-completion signal for
deriving XP / rank / streak for non-linked users).

Uses a Flask test client with a mocked Supabase and mocked JWT auth. Covers:
completed rows are counted and their dates returned; non-completed rows are
ignored; completed rows without completed_at are counted but omitted from dates;
no rows -> zeros; lesson_xp sums lesson_xp() over completed lessons.
"""

import pytest
from unittest.mock import patch

USER_ID = 'user_derived_test'


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def execute(self):
        return FakeResult(list(self._rows))


def make_supabase(progress_rows):
    class FakeSupabase:
        def table(self, name):
            return FakeTable(progress_rows if name == 'user_progress' else [])

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


COURSES = [
    {'id': 'c-beg', 'level': 'beginner'},
    {'id': 'c-gm', 'level': 'grandmaster'},
]
LESSONS = {
    'c-beg': [{'id': 'beg-theory', 'lesson_type': 'theory'},
              {'id': 'beg-ex', 'lesson_type': 'exercise'}],
    'c-gm': [{'id': 'gm-theory', 'lesson_type': 'theory'},
             {'id': 'gm-ex', 'lesson_type': 'exercise'}],
}


def _get(client, auth_headers, progress_rows):
    with patch('api.lessons.supabase', make_supabase(progress_rows)), \
            patch('api.lessons.get_cached_courses', return_value=COURSES), \
            patch('api.lessons.get_cached_lessons_for_course', side_effect=lambda cid: LESSONS[cid]):
        return client.get('/api/gamification/derived-profile', headers=auth_headers)


def test_requires_auth(client):
    resp = client.get('/api/gamification/derived-profile')
    assert resp.status_code == 401


def test_counts_completed_rows_and_returns_dates(client, auth_headers):
    progress = [
        {'status': 'completed', 'completed_at': '2026-09-13T10:00:00+00:00'},
        {'status': 'completed', 'completed_at': '2026-09-14T22:30:00+00:00'},
        {'status': 'completed', 'completed_at': '2026-09-15T08:00:00.123456+00:00'},
    ]
    resp = _get(client, auth_headers, progress)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['total_completions'] == 3
    assert body['completion_dates'] == ['2026-09-13', '2026-09-14', '2026-09-15']


def test_ignores_non_completed_rows(client, auth_headers):
    progress = [
        {'status': 'completed', 'completed_at': '2026-09-15T08:00:00+00:00'},
        {'status': 'in_progress', 'completed_at': None},
        {'status': 'not_started', 'completed_at': None},
    ]
    resp = _get(client, auth_headers, progress)
    body = resp.get_json()
    assert body['total_completions'] == 1
    assert body['completion_dates'] == ['2026-09-15']


def test_completed_without_timestamp_counts_but_omits_date(client, auth_headers):
    progress = [
        {'status': 'completed', 'completed_at': None},
        {'status': 'completed', 'completed_at': '2026-09-15T08:00:00+00:00'},
    ]
    resp = _get(client, auth_headers, progress)
    body = resp.get_json()
    assert body['total_completions'] == 2
    assert body['completion_dates'] == ['2026-09-15']


def test_no_rows_is_zero(client, auth_headers):
    resp = _get(client, auth_headers, [])
    body = resp.get_json()
    assert body['total_completions'] == 0
    assert body['completion_dates'] == []
    assert body['lesson_xp'] == 0


def test_lesson_xp_sums_completed_lessons_by_type_and_level(client, auth_headers):
    progress = [
        {'lesson_id': 'beg-theory', 'status': 'completed', 'completed_at': None},  # 10
        {'lesson_id': 'beg-ex', 'status': 'completed', 'completed_at': None},      # 15
        {'lesson_id': 'gm-ex', 'status': 'completed', 'completed_at': None},       # 50
        {'lesson_id': 'gm-theory', 'status': 'in_progress', 'completed_at': None}, # not counted
        {'lesson_id': 'deleted-lesson', 'status': 'completed', 'completed_at': None},  # unknown → 0
    ]
    body = _get(client, auth_headers, progress).get_json()
    assert body['total_completions'] == 4
    assert body['lesson_xp'] == 75


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
