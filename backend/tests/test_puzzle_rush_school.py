"""
Tests for Puzzle Rush school / branch ranking (services/puzzle_rush_school.py +
the school hooks in services/puzzle_rush.py and api/puzzle_rush.py).

Reuses the Puzzle Rush fixtures (in-memory Supabase, frozen clock, mocked Clerk,
migration-050 RPC mirror). The Chess Empire students-api is a fake client that
records every call; organization_members links live in the fake Supabase.
"""

import uuid
from unittest.mock import patch

import pytest

from services import puzzle_rush_school as school
from services.chess_empire_client import ChessEmpireAPIError
from tests.test_puzzle_rush_api import (  # noqa: F401 — fixtures
    USER_A, USER_B, auth, client, clock, mocks, move, puzzles_db, sb, start,
)
from tests.test_puzzle_rush_instant import finish, finish_body, rpc  # noqa: F401

S1, S2, S3 = (str(uuid.UUID(int=i)) for i in (1, 2, 3))
BR1 = 'branch-1'


class FakeCE:
    def __init__(self):
        self.enabled = True
        self.bests = {}          # student_id -> {week, month, all}
        self.pushed = {}         # external_ref -> payload (CE dedups on it)
        self.calls = []
        self.fail = False
        self.students = {
            S1: {'id': S1, 'first_name': 'Aru', 'last_name': 'Bek', 'branch_id': BR1},
            S2: {'id': S2, 'first_name': 'Dana', 'last_name': 'Sat', 'branch_id': 'branch-2'},
        }
        self.board_rows = [
            {'rank': 1, 'student_id': S3, 'first_name': 'Timur', 'last_name': 'Ali', 'branch_id': BR1,
             'branch_name': 'Central', 'best_score': 40, 'achieved_at': 'x', 'source': 'chess_empire',
             'total_count': 2, 'is_self': False},
            {'rank': 2, 'student_id': S1, 'first_name': 'Aru', 'last_name': 'Bek', 'branch_id': BR1,
             'branch_name': 'Central', 'best_score': 12, 'achieved_at': 'y', 'source': 'chesster',
             'total_count': 2, 'is_self': True},
        ]

    def _call(self, name, *args):
        self.calls.append((name, *args))
        if self.fail:
            raise ChessEmpireAPIError(502, 'down')

    def write_enabled(self):
        return self.enabled

    def get_students(self, ids):
        self._call('get_students', tuple(ids))
        return [self.students[i] for i in ids if i in self.students]

    def survival_best(self, sid):
        self._call('survival_best', sid)
        return self.bests.get(sid, {'week': None, 'month': None, 'all': None})

    def push_survival_score(self, sid, score, run_id, achieved_at=None):
        self._call('push', sid, score, run_id)
        ref = f'chesster-rush:{run_id}'
        if ref in self.pushed:
            return {'ok': True, 'duplicate': True}
        self.pushed[ref] = {'student_id': sid, 'score': score}
        self.bests[sid] = {'week': score, 'month': score, 'all': score}
        return {'ok': True, 'best': self.bests[sid]}

    def survival_leaderboard(self, scope, period, branch_id, student_id, limit):
        self._call('leaderboard', scope, period, branch_id, student_id)
        return {'ok': True, 'scope': scope, 'period': period, 'window_start': 'ws',
                'total_count': 2, 'rows': self.board_rows}

    def count(self, name):
        return sum(1 for c in self.calls if c[0] == name)


@pytest.fixture
def ce(sb, monkeypatch):
    fake = FakeCE()
    monkeypatch.delenv('PUZZLE_RUSH_SCHOOL_PUSH', raising=False)
    school._board_cache.clear()
    school._info_cache.clear()
    with patch('services.puzzle_rush_school.get_client', return_value=fake), \
            patch('services.puzzle_rush_school.supabase', sb):
        yield fake


def link(sb, user_id, *student_ids, **over):
    for sid in student_ids:
        sb.db.setdefault('organization_members', []).append({
            'id': f'm-{len(sb.rows("organization_members"))}', 'user_id': user_id,
            'external_source': 'chess_empire', 'external_student_id': sid,
            'link_status': 'verified', 'access_expires_at': None, 'role': 'student', **over,
        })


def survival(results=('solved', 'solved', 'failed'), **over):
    return finish_body(results, mode='survival', end_reason='strikes', **over)


def run_row(sb, run_id):
    return next(r for r in sb.rows('puzzle_rush_runs') if r['id'] == run_id)


def claim(client, run_id, student_id, token='tok-a'):
    return client.post(f'/api/puzzlerush/runs/{run_id}/school-claim',
                       json={'student_id': student_id}, headers=auth(token))


def board(client, token='tok-a', **params):
    headers = auth(token) if token else {}
    return client.get('/api/puzzlerush/leaderboard', query_string=params, headers=headers)


# ─── Mapping: links → push / needs_student ───────────────────────────────────

class TestMapping:
    def test_unlinked_user_never_pushes(self, client, rpc, ce):
        data = finish(client, survival()).get_json()
        assert data['school'] == {'status': 'unlinked'}
        assert ce.count('push') == 0

    def test_single_link_pushes_and_persists(self, client, rpc, ce, sb):
        link(sb, USER_A, S1)
        body = survival()
        data = finish(client, body).get_json()
        assert data['school']['status'] == 'pushed'
        assert data['school']['student_id'] == S1
        assert data['school']['beaten'] == ['week', 'month', 'all']
        assert ce.pushed == {f"chesster-rush:{body['run_id']}": {'student_id': S1, 'score': 2}}
        row = run_row(sb, body['run_id'])
        assert row['school_push_status'] == 'pushed' and row['school_student_id'] == S1
        assert row['school_pushed_at']

    def test_inactive_links_are_ignored(self, client, rpc, ce, sb):
        link(sb, USER_A, S1, link_status='frozen')
        link(sb, USER_A, S2, access_expires_at='2000-01-01T00:00:00Z')
        link(sb, USER_A, S3, role='coach')
        assert finish(client, survival()).get_json()['school'] == {'status': 'unlinked'}

    def test_family_needs_student_and_does_not_push(self, client, rpc, ce, sb):
        link(sb, USER_A, S1, S2)
        sb.db['puzzle_rush_school_pick'] = [{'user_id': USER_A, 'external_student_id': S2}]
        body = survival()
        res = finish(client, body).get_json()['school']
        assert res['status'] == 'needs_student'
        assert res['last_student_id'] == S2
        assert [c['student_id'] for c in res['candidates']] == [S1, S2]
        assert res['candidates'][0]['first_name'] == 'Aru' and res['candidates'][1]['branch_id'] == 'branch-2'
        assert ce.count('push') == 0 and ce.count('survival_best') == 0
        assert run_row(sb, body['run_id'])['school_push_status'] == 'needs_student'

    def test_claim_pushes_for_the_pick_and_remembers_it(self, client, rpc, ce, sb):
        link(sb, USER_A, S1, S2)
        body = survival()
        finish(client, body)
        resp = claim(client, body['run_id'], S2)
        assert resp.status_code == 200
        assert resp.get_json()['school']['status'] == 'pushed'
        assert ce.pushed[f"chesster-rush:{body['run_id']}"]['student_id'] == S2
        assert sb.rows('puzzle_rush_school_pick')[0]['external_student_id'] == S2
        # Next run: the pick is pre-selected but there is still no push.
        res = finish(client, survival()).get_json()['school']
        assert res['status'] == 'needs_student' and res['last_student_id'] == S2
        assert len(ce.pushed) == 1

    def test_claim_with_foreign_student_is_403(self, client, rpc, ce, sb):
        link(sb, USER_A, S1, S2)
        link(sb, USER_B, S3)
        body = survival()
        finish(client, body)
        resp = claim(client, body['run_id'], S3)
        assert resp.status_code == 403
        assert resp.get_json()['error'] == 'student_not_linked'
        assert ce.count('push') == 0 and sb.rows('puzzle_rush_school_pick') == []

    def test_claim_validation(self, client, rpc, ce, sb):
        link(sb, USER_A, S1, S2)
        link(sb, USER_B, S1)
        body = survival()
        finish(client, body)
        assert claim(client, body['run_id'], S1, token='tok-b').status_code == 403  # not the owner
        assert client.post(f"/api/puzzlerush/runs/{body['run_id']}/school-claim",
                           json={'student_id': S1}).status_code == 401
        assert claim(client, str(uuid.uuid4()), S1).status_code == 404
        timed = finish_body()
        finish(client, timed)
        resp = claim(client, timed['run_id'], S1)
        assert resp.status_code == 400 and resp.get_json()['error'] == 'not_survival'


# ─── Push rule ───────────────────────────────────────────────────────────────

class TestPushRule:
    @pytest.mark.parametrize('best, beaten', [
        ({'week': 1, 'month': 5, 'all': 9}, ['week']),
        ({'week': 5, 'month': 1, 'all': 9}, ['month']),
        ({'week': 5, 'month': 5, 'all': 1}, ['all']),
        ({'week': None, 'month': 5, 'all': 9}, ['week']),
    ])
    def test_beats_one_period(self, client, rpc, ce, sb, best, beaten):
        link(sb, USER_A, S1)
        ce.bests[S1] = best
        res = finish(client, survival()).get_json()['school']
        assert res['status'] == 'pushed' and res['beaten'] == beaten
        assert ce.count('push') == 1

    def test_beats_nothing_is_not_best(self, client, rpc, ce, sb):
        link(sb, USER_A, S1)
        ce.bests[S1] = {'week': 2, 'month': 3, 'all': 9}  # a tie is not a beat
        body = survival()
        res = finish(client, body).get_json()['school']
        assert res['status'] == 'not_best'
        assert ce.count('push') == 0
        assert run_row(sb, body['run_id'])['school_push_status'] == 'not_best'

    def test_zero_score_never_pushes(self, client, rpc, ce, sb):
        link(sb, USER_A, S1)
        res = finish(client, survival(('failed', 'failed', 'failed'))).get_json()['school']
        assert res['status'] == 'not_best'
        assert ce.calls == []

    def test_zero_score_family_is_not_asked_to_pick(self, client, rpc, ce, sb):
        link(sb, USER_A, S1, S2)
        res = finish(client, survival(('failed', 'failed', 'failed'))).get_json()['school']
        assert res['status'] == 'not_best'

    @pytest.mark.parametrize('mode', ['3min', '5min'])
    def test_timed_modes_never_push(self, client, rpc, ce, sb, mode):
        link(sb, USER_A, S1)
        data = finish(client, finish_body(mode=mode)).get_json()
        assert data['school'] is None
        assert ce.calls == []

    def test_guest_run_never_pushes(self, client, ce, sb):
        link(sb, USER_A, S1)
        run = start(client, 'survival')
        assert run.get('guest_token')
        resp = client.post(f"/api/puzzlerush/runs/{run['run_id']}/quit",
                           headers={'X-Guest-Token': run['guest_token']})
        assert resp.get_json()['results']['school'] is None
        assert ce.calls == []

    def test_maybe_push_ignores_guest_and_unfinished(self, ce):
        assert school.maybe_push({'id': 'r', 'mode': 'survival', 'user_id': None, 'ended_at': 'x', 'score': 5}) is None
        assert school.maybe_push({'id': 'r', 'mode': 'survival', 'user_id': 'u', 'ended_at': None, 'score': 5}) is None
        assert ce.calls == []

    def test_v1_server_run_pushes_on_finish(self, client, ce, sb):
        link(sb, USER_A, S1)
        run = start(client, 'survival', headers=auth())
        assert move(client, run, 'd1d8', auth()).get_json()['result'] == 'solved'
        res = client.post(f"/api/puzzlerush/runs/{run['run_id']}/quit", headers=auth()).get_json()
        assert res['results']['school']['status'] == 'pushed'
        assert ce.pushed[f"chesster-rush:{run['run_id']}"] == {'student_id': S1, 'score': 1}
        # Later summaries show the stored outcome without calling CE again.
        calls = len(ce.calls)
        summary = client.get(f"/api/puzzlerush/runs/{run['run_id']}", headers=auth()).get_json()
        assert summary['results']['school'] == {'status': 'pushed', 'student_id': S1}
        assert len(ce.calls) == calls


# ─── Kill switch / disabled / failures ───────────────────────────────────────

class TestBestEffort:
    def test_missing_key_disables(self, client, rpc, ce, sb):
        link(sb, USER_A, S1)
        ce.enabled = False
        data = finish(client, survival()).get_json()
        assert data['school'] == {'status': 'disabled'}
        assert ce.calls == []

    def test_kill_switch_stops_push(self, client, rpc, ce, sb, monkeypatch):
        link(sb, USER_A, S1)
        monkeypatch.setenv('PUZZLE_RUSH_SCHOOL_PUSH', '0')
        data = finish(client, survival()).get_json()
        assert data['school'] == {'status': 'disabled', 'student_id': S1}
        assert ce.calls == []

    def test_ce_failure_still_finishes_the_run(self, client, rpc, ce, sb):
        link(sb, USER_A, S1)
        ce.fail = True
        body = survival()
        resp = finish(client, body)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['score'] == 2 and data['school'] == {'status': 'error', 'student_id': S1}
        assert run_row(sb, body['run_id'])['school_push_status'] == 'error'

    def test_unexpected_error_is_swallowed(self, client, rpc, ce, sb):
        link(sb, USER_A, S1)
        with patch('services.puzzle_rush_school.linked_student_ids', side_effect=RuntimeError('boom')):
            resp = finish(client, survival())
        assert resp.status_code == 200
        assert resp.get_json()['school']['status'] == 'error'

    def test_retry_after_error_pushes(self, client, rpc, ce, sb):
        link(sb, USER_A, S1)
        ce.fail = True
        body = survival()
        finish(client, body)
        ce.fail = False
        data = finish(client, body).get_json()
        assert data['duplicate'] is True and data['school']['status'] == 'pushed'


# ─── Idempotency ─────────────────────────────────────────────────────────────

class TestIdempotency:
    def test_duplicate_finish_is_a_single_push(self, client, rpc, ce, sb):
        link(sb, USER_A, S1)
        body = survival()
        first = finish(client, body).get_json()['school']
        second = finish(client, body).get_json()['school']
        assert first['status'] == second['status'] == 'pushed'
        assert ce.count('push') == 1 and len(ce.pushed) == 1

    def test_retried_claim_is_a_single_push(self, client, rpc, ce, sb):
        link(sb, USER_A, S1, S2)
        body = survival()
        finish(client, body)
        a = claim(client, body['run_id'], S1).get_json()['school']
        b = claim(client, body['run_id'], S1).get_json()['school']
        c = claim(client, body['run_id'], S2).get_json()['school']  # already pushed for S1
        assert a['status'] == b['status'] == c['status'] == 'pushed'
        assert b['student_id'] == c['student_id'] == S1
        assert ce.count('push') == 1

    def test_same_external_ref_on_every_push(self, ce, sb):
        link(sb, USER_A, S1)
        run = {'id': 'run-1', 'mode': 'survival', 'user_id': USER_A, 'ended_at': 'x', 'score': 3}
        school.maybe_push(dict(run))
        ce.bests.clear()  # a lost response: the rule passes again and the push is resent
        assert school.maybe_push(dict(run))['status'] == 'pushed'
        pushes = [c for c in ce.calls if c[0] == 'push']
        assert pushes == [('push', S1, 3, 'run-1')] * 2
        assert list(ce.pushed) == ['chesster-rush:run-1']


# ─── School / branch boards ──────────────────────────────────────────────────

class TestLeaderboard:
    def test_school_board_shape(self, client, ce, sb):
        link(sb, USER_A, S1)
        resp = board(client, scope='school', period='week')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['mode'] == 'survival' and data['scope'] == 'school' and data['period'] == 'week'
        assert data['entries'][0] == {'rank': 1, 'name': 'Timur A.', 'branch_name': 'Central', 'score': 40,
                                      'achieved_at': 'x', 'is_self': False, 'source': 'chess_empire'}
        assert data['entries'][1]['is_self'] is True
        assert data['me'] == {'score': 12, 'rank': 2}
        assert ('leaderboard', 'school', 'week', None, S1) in ce.calls

    def test_branch_uses_the_students_branch(self, client, ce, sb):
        link(sb, USER_A, S2)
        data = board(client, scope='branch', period='month').get_json()
        assert data['branch_id'] == 'branch-2'
        assert ('leaderboard', 'branch', 'month', 'branch-2', S2) in ce.calls

    def test_branch_unknown_is_503(self, client, ce, sb):
        link(sb, USER_A, S3)  # CE returns no row for S3
        resp = board(client, scope='branch', period='week')
        assert resp.status_code == 503 and resp.get_json()['error'] == 'branch_unavailable'

    @pytest.mark.parametrize('period, expected', [('weekly', 'week'), ('monthly', 'month'), ('all', 'all')])
    def test_period_aliases(self, client, ce, sb, period, expected):
        link(sb, USER_A, S1)
        assert board(client, scope='school', period=period).get_json()['period'] == expected

    @pytest.mark.parametrize('params, status, code', [
        ({'scope': 'school', 'period': 'daily'}, 400, 'invalid_period'),
        ({'scope': 'school', 'period': 'year'}, 400, 'invalid_period'),
        ({'scope': 'school', 'period': 'week', 'mode': '3min'}, 400, 'invalid_mode'),
    ])
    def test_validation(self, client, ce, sb, params, status, code):
        link(sb, USER_A, S1)
        resp = board(client, **params)
        assert resp.status_code == status and resp.get_json()['error'] == code

    def test_auth_and_link_required(self, client, ce, sb):
        assert board(client, token=None, scope='school').status_code == 401
        resp = board(client, scope='school')
        assert resp.status_code == 403 and resp.get_json()['error'] == 'not_linked'

    def test_disabled_is_503(self, client, ce, sb):
        link(sb, USER_A, S1)
        ce.enabled = False
        assert board(client, scope='school').status_code == 503

    def test_ce_failure_is_502(self, client, ce, sb):
        link(sb, USER_A, S1)
        ce.fail = True
        resp = board(client, scope='school')
        assert resp.status_code == 502 and resp.get_json()['error'] == 'school_unavailable'

    def test_family_student_param(self, client, ce, sb):
        link(sb, USER_A, S1, S2)
        resp = board(client, scope='school')
        assert resp.status_code == 400 and resp.get_json()['error'] == 'student_required'
        assert len(resp.get_json()['candidates']) == 2
        assert board(client, scope='school', student_id=S3).status_code == 403
        assert board(client, scope='school', student_id=S2).get_json()['student_id'] == S2

    def test_family_defaults_to_remembered_pick(self, client, ce, sb):
        link(sb, USER_A, S1, S2)
        sb.db['puzzle_rush_school_pick'] = [{'user_id': USER_A, 'external_student_id': S2}]
        assert board(client, scope='school').get_json()['student_id'] == S2

    def test_cached_for_60_seconds(self, client, ce, sb):
        link(sb, USER_A, S1)
        with patch('services.puzzle_rush_school.time.monotonic', return_value=1000.0):
            board(client, scope='school', period='week')
            board(client, scope='school', period='week')
            assert ce.count('leaderboard') == 1
            board(client, scope='school', period='month')  # different key
            assert ce.count('leaderboard') == 2
        with patch('services.puzzle_rush_school.time.monotonic', return_value=1061.0):
            board(client, scope='school', period='week')
        assert ce.count('leaderboard') == 3

    def test_global_scope_unchanged(self, client, ce, sb):
        resp = board(client, scope='global', mode='survival', period='daily')
        assert resp.status_code == 200 and resp.get_json()['scope'] == 'global'
        assert ce.calls == []
