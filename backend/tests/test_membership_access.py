"""
Tests for the Phase 3 server-side access gate:

  - `require_active_membership` decorator (utils/auth.py)
  - `resolve_membership_restriction` (frozen/expired + personal-sub override)
  - one guarded content endpoint per touched blueprint (maia, openings,
    opponent, user_games)
  - the Learn ceiling gate `restricted_level_denial` (lessons.py, shared by
    puzzles.py)

Supabase is mocked throughout; nothing hits the network.
"""

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask, jsonify

from utils.auth import (
    require_active_membership,
    resolve_membership_restriction,
)

USER_ID = 'user_access_test'
FUTURE = time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(time.time() + 86400))
PAST = time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(time.time() - 86400))


# ── Fake Supabase ────────────────────────────────────────────────────────────

class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


class FakeSupabase:
    def __init__(self, members=None, subs=None):
        self._members = members or []
        self._subs = subs or []

    def table(self, name):
        if name == 'organization_members':
            return FakeQuery(self._members)
        if name == 'subscriptions':
            return FakeQuery(self._subs)
        return FakeQuery([])


def member_row(link_status='verified', expires=None, ext='stu-1', source='chess_empire'):
    return {
        'external_student_id': ext,
        'link_status': link_status,
        'access_expires_at': expires,
        'external_source': source,
    }


def sub_row(status='active', period_end=None):
    return {'status': status, 'current_period_end': period_end}


# ── resolve_membership_restriction matrix ────────────────────────────────────

@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        with app.test_request_context():
            yield


def _resolve(members, subs):
    with patch('utils.auth._membership_supabase', return_value=FakeSupabase(members, subs)):
        return resolve_membership_restriction(USER_ID)


def test_frozen_without_subscription_is_restricted(app_ctx):
    r = _resolve([member_row('frozen')], [])
    assert r == {'restricted': True, 'reason': 'frozen'}


def test_frozen_with_active_subscription_is_not_restricted(app_ctx):
    r = _resolve([member_row('frozen')], [sub_row('active')])
    assert r['restricted'] is False


def test_expired_without_subscription_is_restricted(app_ctx):
    r = _resolve([member_row('verified', expires=PAST)], [])
    assert r == {'restricted': True, 'reason': 'expired'}


def test_expired_with_trialing_subscription_is_not_restricted(app_ctx):
    r = _resolve([member_row('verified', expires=PAST)], [sub_row('trialing')])
    assert r['restricted'] is False


def test_verified_is_not_restricted(app_ctx):
    r = _resolve([member_row('verified')], [])
    assert r['restricted'] is False


def test_verified_not_yet_expired_is_not_restricted(app_ctx):
    r = _resolve([member_row('verified', expires=FUTURE)], [])
    assert r['restricted'] is False


def test_no_membership_rows_is_not_restricted(app_ctx):
    r = _resolve([], [])
    assert r['restricted'] is False


def test_expired_subscription_does_not_override(app_ctx):
    # An inactive/expired personal sub must NOT lift the restriction.
    r = _resolve([member_row('frozen')], [sub_row('active', period_end=PAST)])
    assert r == {'restricted': True, 'reason': 'frozen'}


def test_canceled_subscription_does_not_override(app_ctx):
    r = _resolve([member_row('frozen')], [sub_row('canceled')])
    assert r['restricted'] is True


def test_family_verified_row_wins_over_frozen(app_ctx):
    # A verified link anywhere in a family account beats a frozen one.
    r = _resolve([member_row('frozen', ext='a'), member_row('verified', ext='b')], [])
    assert r['restricted'] is False


def test_supabase_error_fails_open(app_ctx):
    def boom():
        raise RuntimeError('supabase down')

    with patch('utils.auth._membership_supabase', side_effect=boom):
        r = resolve_membership_restriction(USER_ID)
    assert r == {'restricted': False, 'reason': None}


# ── require_active_membership decorator ──────────────────────────────────────

@pytest.fixture
def dummy_app():
    app = Flask(__name__)
    app.config['TESTING'] = True

    @app.route('/guarded')
    @require_active_membership
    def guarded():
        return jsonify({'ok': True})

    return app


@pytest.fixture
def dummy_client(dummy_app):
    return dummy_app.test_client()


AUTH = {'Authorization': 'Bearer fake-token'}


def _with_supabase(members, subs):
    return patch('utils.auth._membership_supabase', return_value=FakeSupabase(members, subs))


@pytest.fixture(autouse=True)
def mock_jwt():
    with patch('utils.auth.jwt.decode', return_value={'sub': USER_ID}):
        yield


def test_decorator_blocks_restricted_member(dummy_client):
    with _with_supabase([member_row('frozen')], []):
        resp = dummy_client.get('/guarded', headers=AUTH)
    assert resp.status_code == 403
    assert resp.get_json()['error'] == 'MEMBERSHIP_RESTRICTED'
    assert resp.get_json()['reason'] == 'frozen'


def test_decorator_allows_member_with_personal_sub(dummy_client):
    with _with_supabase([member_row('frozen')], [sub_row('active')]):
        resp = dummy_client.get('/guarded', headers=AUTH)
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True}


def test_decorator_allows_verified_member(dummy_client):
    with _with_supabase([member_row('verified')], []):
        resp = dummy_client.get('/guarded', headers=AUTH)
    assert resp.status_code == 200


def test_decorator_allows_anonymous_caller(dummy_client):
    # No Authorization header → cannot identify → allow (nothing to enforce).
    with _with_supabase([member_row('frozen')], []):
        resp = dummy_client.get('/guarded')
    assert resp.status_code == 200


def test_decorator_fails_open_on_supabase_error(dummy_client):
    with patch('utils.auth._membership_supabase', side_effect=RuntimeError('down')):
        resp = dummy_client.get('/guarded', headers=AUTH)
    assert resp.status_code == 200


# ── Guarded content endpoints (403 for a restricted member) ──────────────────

def _frozen_supabase():
    return _with_supabase([member_row('frozen')], [])


def test_maia_move_blocked_for_restricted(mock_jwt):
    from api.maia import maia_bp
    app = Flask(__name__)
    app.register_blueprint(maia_bp)
    with _frozen_supabase():
        resp = app.test_client().post('/api/maia/move', json={'fen': 'x'}, headers=AUTH)
    assert resp.status_code == 403
    assert resp.get_json()['error'] == 'MEMBERSHIP_RESTRICTED'


def test_openings_by_position_blocked_for_restricted(mock_jwt):
    from api.openings import openings_bp
    app = Flask(__name__)
    app.register_blueprint(openings_bp)
    with _frozen_supabase():
        resp = app.test_client().get('/api/openings/games/by-position?fen=x', headers=AUTH)
    assert resp.status_code == 403


def test_opponent_search_blocked_for_restricted(mock_jwt):
    from api.opponent_analysis import opponent_bp
    app = Flask(__name__)
    app.register_blueprint(opponent_bp)
    with _frozen_supabase():
        resp = app.test_client().get('/api/opponent/search?q=carlsen', headers=AUTH)
    assert resp.status_code == 403


def test_user_games_list_blocked_for_restricted(mock_jwt):
    from api.user_games import user_games_bp
    app = Flask(__name__)
    app.register_blueprint(user_games_bp)
    with _frozen_supabase():
        resp = app.test_client().get('/api/games', headers=AUTH)
    assert resp.status_code == 403


# ── Learn ceiling gate (lessons.py, shared by puzzles.py) ────────────────────

CEIL_COURSES = [
    {'id': 'c1', 'title': 'Level 1', 'order_index': 3},
    {'id': 'c2', 'title': 'Level 2', 'order_index': 5},
    {'id': 'c3', 'title': 'Level 3', 'order_index': 8},
]


def _progress(*complete_ids):
    return {c['id']: {'progress': 100 if c['id'] in complete_ids else 0}
            for c in CEIL_COURSES}


def _denial(course_id, restricted, progress):
    """Invoke restricted_level_denial with all Supabase-touching pieces mocked."""
    import api.lessons as lessons
    app = Flask(__name__)
    with app.test_request_context():
        with patch.object(lessons, 'get_current_user_id', return_value=USER_ID), \
             patch.object(lessons, 'resolve_membership_restriction',
                          return_value={'restricted': restricted,
                                        'reason': 'frozen' if restricted else None}), \
             patch.object(lessons, 'get_cached_courses', return_value=CEIL_COURSES), \
             patch.object(lessons, 'compute_progress_by_course', return_value=progress):
            return lessons.restricted_level_denial(course_id)


def test_ceiling_full_access_allows_any_level():
    # Non-restricted member: no ceiling at all.
    assert _denial('c3', restricted=False, progress=_progress()) is None


def test_ceiling_blocks_course_above_current_level():
    # Nothing complete → ceiling is level 1 (c1). c2/c3 are above → 403.
    denial = _denial('c2', restricted=True, progress=_progress())
    assert denial is not None
    body, status = denial
    assert status == 403
    assert body.get_json() == {'error': 'MEMBERSHIP_RESTRICTED', 'scope': 'level'}


def test_ceiling_allows_current_level():
    # Nothing complete → ceiling level 1 → c1 (own level) allowed.
    assert _denial('c1', restricted=True, progress=_progress()) is None


def test_ceiling_advances_when_previous_complete():
    # c1 complete → ceiling is c2; c2 allowed, c3 still blocked.
    assert _denial('c2', restricted=True, progress=_progress('c1')) is None
    assert _denial('c3', restricted=True, progress=_progress('c1')) is not None


def test_ceiling_own_complete_always_allowed():
    # Even above the ceiling, a fully-completed course is never locked.
    assert _denial('c3', restricted=True, progress=_progress('c3')) is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
