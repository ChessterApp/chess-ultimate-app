"""Tracking plan §4 B — lesson_started / lesson_completed / level_completed
captured from POST /api/learn/<course>/<lesson>/progress."""

from unittest.mock import MagicMock, patch

import pytest

USER_ID = 'user_lesson_analytics'
COURSES = [
    {'id': 'c2', 'slug': 'level-2', 'order_index': 2},
    {'id': 'c1', 'slug': 'level-1', 'order_index': 1},
]
COURSE = COURSES[0]


@pytest.fixture(autouse=True)
def _courses():
    with patch('api.lessons.get_cached_courses', return_value=COURSES):
        yield


@pytest.fixture
def cap():
    with patch('api.lessons.analytics.capture') as m:
        yield m


def _run(data, first_start=False, prev=None, progress=None):
    import api.lessons as lessons
    with patch('api.lessons.compute_progress_by_course',
               return_value={'c2': {'progress': progress if progress is not None else 50}}):
        lessons._capture_lesson_progress(USER_ID, COURSE, 'l-9', data, first_start, prev)


def test_first_start_fires_lesson_started(cap):
    _run({'status': 'in_progress'}, first_start=True)
    cap.assert_called_once_with(USER_ID, 'lesson_started',
                                {'course': 'level-2', 'lesson_id': 'l-9', 'level': 2})


def test_repeat_in_progress_fires_nothing(cap):
    _run({'status': 'in_progress'}, first_start=False, prev={'started_at': 'x'})
    cap.assert_not_called()


def test_completion_fires_lesson_completed_with_duration(cap):
    _run({'status': 'completed', 'time_spent_seconds': 120}, prev={'status': 'in_progress'})
    cap.assert_called_once_with(USER_ID, 'lesson_completed', {
        'course': 'level-2', 'lesson_id': 'l-9', 'level': 2,
        'first_completion': True, 'duration_s': 120,
    })


def test_completion_that_finishes_course_fires_level_completed(cap):
    _run({'status': 'completed'}, prev=None, progress=100)
    events = [c.args[1] for c in cap.call_args_list]
    assert events == ['lesson_completed', 'level_completed']
    assert cap.call_args_list[1].args[2] == {'course': 'level-2', 'level': 2}


def test_recompletion_never_fires_level_completed(cap):
    _run({'status': 'completed'}, prev={'status': 'completed'}, progress=100)
    events = [c.args[1] for c in cap.call_args_list]
    assert events == ['lesson_completed']
    assert cap.call_args_list[0].args[2]['first_completion'] is False


def test_analytics_failure_is_swallowed():
    with patch('api.lessons.analytics.capture', side_effect=RuntimeError('boom')):
        _run({'status': 'completed'})  # must not raise


def test_endpoint_wires_capture():
    from flask import Flask
    from api.lessons import lessons_bp

    app = Flask(__name__)
    app.register_blueprint(lessons_bp)

    table = MagicMock()
    for name in ('select', 'eq', 'upsert'):
        getattr(table, name).return_value = table
    table.execute.side_effect = [MagicMock(data=[]), MagicMock(data=[{'ok': True}])]
    sb = MagicMock()
    sb.table.return_value = table

    with patch('utils.auth._decode_clerk_token', return_value={'sub': USER_ID}), \
            patch('api.lessons.resolve_course_and_lesson', return_value=(COURSE, {'id': 'l-9'})), \
            patch('api.lessons.supabase', sb), \
            patch('api.lessons._capture_lesson_progress') as helper:
        resp = app.test_client().post(
            '/api/learn/level-2/l-9/progress', json={'status': 'in_progress'},
            headers={'Authorization': 'Bearer x'},
        )
    assert resp.status_code == 200
    helper.assert_called_once_with(USER_ID, COURSE, 'l-9', {'status': 'in_progress'}, True, None)
