"""
Tests for the Puzzle Rush v2 (instant moves) endpoints:
  • GET  /api/puzzlerush/pack         — stateless deterministic puzzle packs
  • POST /api/puzzlerush/runs/finish  — record a client-played run (Bearer only)

Reuses the fixtures of test_puzzle_rush_api (fixture puzzles DB, in-memory
Supabase, frozen clock, mocked Clerk). The `puzzle_rush_finish_run` RPC is
mocked by a Python mirror of migration 050 over the fake tables; the SQL itself
was exercised against a scratch Postgres 16 cluster (see the phase report).
"""

import logging
import sqlite3
import uuid
from datetime import timedelta

import pytest

from services import puzzle_rush as rush
from services.puzzle_rush_source import target_rating
from tests.test_puzzle_rush_api import (  # noqa: F401 — fixtures
    T0, USER_A, USER_B, auth, client, clock, m, mocks, puzzles_db, sb,
)

SEED = '0123456789abcdef'


# ─── Mock of migration 050 ───────────────────────────────────────────────────

def _finish_rpc(db):
    """Python mirror of puzzle_rush_finish_run(payload) over the fake tables."""
    def fn(payload):
        run, attempts, periods = payload['run'], payload['attempts'], payload['periods']
        runs = db.setdefault(rush.RUNS_TABLE, [])
        bests = db.setdefault(rush.BESTS_TABLE, [])
        existing = next((r for r in runs if r['id'] == run['id']), None)
        if existing and existing['user_id'] != run['user_id']:
            return {'status': 'conflict'}
        status = 'duplicate' if existing else 'created'
        if not existing:
            row = {**run, 'last_activity_at': run['ended_at'], 'move_seq': 0, 'is_new_pb': False,
                   'guest_token_hash': None}
            runs.append(row)
            db.setdefault(rush.ATTEMPTS_TABLE, []).extend({**a, 'run_id': run['id']} for a in attempts)
            best = next((b for b in bests if b['user_id'] == run['user_id'] and b['mode'] == run['mode']), None)
            if row['score'] > 0 and (best is None or row['score'] > best['best_score']):
                new = {'user_id': run['user_id'], 'mode': run['mode'], 'best_score': row['score'],
                       'best_run_id': run['id'], 'display_name': run['display_name'],
                       'achieved_at': run['ended_at']}
                if best:
                    best.update(new)
                else:
                    bests.append(new)
                row['is_new_pb'] = True
            existing = row
        r = existing

        def users_above(since):
            return 1 + len({x['user_id'] for x in runs if x['mode'] == r['mode'] and x['user_id']
                            and x['score'] > r['score'] and x['ended_at'] >= since})
        return {
            'status': status,
            'run': {k: r[k] for k in ('score', 'is_new_pb', 'longest_streak', 'highest_solved_rating',
                                      'avg_ms_per_puzzle', 'duration_ms')},
            'personal_rank': 1 + sum(1 for x in runs if x['user_id'] == r['user_id'] and x['mode'] == r['mode']
                                     and x.get('ended_at') and x['score'] > r['score']),
            'global_rank': {
                'daily': users_above(periods['daily']),
                'weekly': users_above(periods['weekly']),
                'all': 1 + sum(1 for b in bests if b['mode'] == r['mode'] and b['best_score'] > r['score']),
            },
        }
    return fn


@pytest.fixture
def rpc(sb):
    sb.functions[rush.FINISH_RPC] = _finish_rpc(sb.db)
    return sb


def attempt(i, result='solved', rating=None, moves=('d1d8',), ms=3000):
    return {'index': i, 'puzzle_id': f'P{i}', 'rating': rating or target_rating(i), 'result': result,
            'user_moves': list(moves), 'ms': ms}


def finish_body(results=('solved', 'solved', 'failed'), mode='3min', run_id=None, **over):
    body = {
        'run_id': run_id or str(uuid.uuid4()),
        'mode': mode,
        'seed': SEED,
        'started_at': (T0 - timedelta(minutes=3)).isoformat(),
        'ended_at': T0.isoformat(),
        'end_reason': 'timeout',
        'attempts': [attempt(i, r) for i, r in enumerate(results)],
    }
    body.update(over)
    return body


def finish(client, body, headers=None):
    return client.post('/api/puzzlerush/runs/finish', json=body,
                       headers=auth() if headers is None else headers)


# ─── Pack ────────────────────────────────────────────────────────────────────

def get_pack(client, **params):
    return client.get('/api/puzzlerush/pack', query_string={'seed': SEED, **params})


class TestPack:
    def test_no_auth_full_lines_and_cache_header(self, client, sb):
        resp = get_pack(client)
        assert resp.status_code == 200
        assert resp.headers['Cache-Control'] == 'public, max-age=86400, immutable'
        data = resp.get_json()
        assert data['seed'] == SEED and data['from'] == 0 and data['count'] == rush.PACK_DEFAULT == 40
        p = data['puzzles'][0]
        assert set(p) == {'index', 'id', 'fen', 'moves', 'rating', 'themes', 'color'}
        assert p['moves'] == ['a7a6', 'd1d8'] and p['color'] == 'white' and p['index'] == 0
        assert [q['index'] for q in data['puzzles']] == list(range(40))
        assert sb.db == {}  # stateless: no DB writes

    def test_same_seed_same_ids_other_seed_differs(self, client):
        a = get_pack(client).get_json()
        b = get_pack(client).get_json()
        assert a == b
        other = get_pack(client, seed='fedcba9876543210').get_json()
        assert [p['id'] for p in other['puzzles']] != [p['id'] for p in a['puzzles']]

    def test_follows_the_ramp(self, client):
        for p in get_pack(client).get_json()['puzzles']:
            assert abs(p['rating'] - target_rating(p['index'])) <= 30

    def test_top_up_slices_match_one_big_pack(self, client):
        whole = get_pack(client, count=70).get_json()['puzzles']
        parts = get_pack(client, count=40).get_json()['puzzles'] + \
            get_pack(client, **{'from': 40, 'count': 30}).get_json()['puzzles']
        assert parts == whole

    def test_no_duplicate_ids_within_a_seed(self, client):
        ids = [p['id'] for f in (0, 100, 200) for p in
               get_pack(client, **{'from': f, 'count': 100}).get_json()['puzzles']]
        assert len(ids) == 300 and len(set(ids)) == 300

    def test_themes_are_listed(self, client, puzzles_db):
        puzzles_db([m('T1', 400), m('T2', 446)])
        conn = sqlite3.connect(rush.get_puzzle_source().db_path)
        conn.execute("UPDATE puzzles SET themes = 'mate mateIn1 short'")
        conn.commit()
        conn.close()
        p = get_pack(client, count=1).get_json()['puzzles'][0]
        assert p['themes'] == ['mate', 'mateIn1', 'short']

    def test_capped_at_max_attempts(self, client):
        data = get_pack(client, **{'from': 480, 'count': 50}).get_json()
        assert data['count'] == 20 and data['puzzles'][-1]['index'] == rush.MAX_ATTEMPTS - 1

    @pytest.mark.parametrize('params, code', [
        ({'seed': 'xyz'}, 'invalid_seed'),
        ({'seed': ''}, 'invalid_seed'),
        ({'count': 0}, 'invalid_count'),
        ({'count': 101}, 'invalid_count'),
        ({'count': 'ten'}, 'invalid_count'),
        ({'from': -1}, 'invalid_from'),
        ({'from': 501}, 'invalid_from'),
    ])
    def test_validation(self, client, params, code):
        resp = get_pack(client, **params)
        assert resp.status_code == 400 and resp.get_json()['error'] == code

    def test_exhausted_db_is_503(self, client, puzzles_db):
        puzzles_db([m('only-1', 400), m('only-2', 410)])
        resp = get_pack(client, count=5)
        assert resp.status_code == 503 and resp.get_json()['error'] == 'no_puzzles'


# ─── Finish: auth ────────────────────────────────────────────────────────────

class TestFinishAuth:
    def test_bearer_token_records_the_run_as_that_user(self, client, rpc):
        resp = finish(client, finish_body(), auth('tok-b'))
        assert resp.status_code == 200, resp.get_json()
        assert rpc.rows(rush.RUNS_TABLE)[0]['user_id'] == USER_B

    def test_unauthenticated_is_rejected(self, client, rpc):
        resp = finish(client, finish_body(), headers={})
        assert resp.status_code == 401 and resp.get_json()['error'] == 'auth_required'
        assert rpc.rows(rush.RUNS_TABLE) == []

    def test_guest_token_is_not_auth(self, client, rpc):
        resp = finish(client, finish_body(), headers={'X-Guest-Token': 'whatever'})
        assert resp.status_code == 401

    def test_invalid_bearer_is_401(self, client, rpc):
        resp = finish(client, finish_body(), auth('nope'))
        assert resp.status_code == 401 and resp.get_json()['error'] == 'invalid_token'


# ─── Finish: recording ───────────────────────────────────────────────────────

class TestFinish:
    def test_score_and_streaks_recomputed_from_attempts(self, client, rpc):
        results = ('solved', 'failed', 'solved', 'solved', 'solved', 'failed', 'solved', 'unfinished')
        body = finish_body(results, score=99, strikes=0, longest_streak=50)  # client totals are ignored
        body['attempts'][3]['rating'] = 1234
        data = finish(client, body).get_json()
        assert data['score'] == 5
        assert data['longest_streak'] == 3
        assert data['highest_solved_rating'] == 1234
        assert data['avg_ms_per_puzzle'] == 3000
        assert data['duration_ms'] == 180_000
        assert data['duplicate'] is False

        row = rpc.rows(rush.RUNS_TABLE)[0]
        assert (row['score'], row['strikes'], row['current_streak'], row['longest_streak']) == (5, 2, 1, 3)
        assert row['puzzle_count'] == 8 and row['end_reason'] == 'timeout' and row['seed'] == SEED
        assert row['deadline_at'] == (T0 - timedelta(minutes=3) + timedelta(seconds=180)).isoformat()
        assert row['display_name'] == f'Name {USER_A}'

        attempts = rpc.rows(rush.ATTEMPTS_TABLE)
        assert [a['idx'] for a in attempts] == list(range(8))
        assert attempts[0]['user_moves'] == 'd1d8'
        # served_at is reconstructed from the per-puzzle times.
        started = T0 - timedelta(minutes=3)
        assert attempts[2]['served_at'] == (started + timedelta(seconds=6)).isoformat()
        assert attempts[2]['answered_at'] == (started + timedelta(seconds=9)).isoformat()
        assert attempts[7]['result'] == 'unfinished' and attempts[7]['answered_at'] is None

    def test_idempotent_on_run_id(self, client, rpc):
        body = finish_body()
        first = finish(client, body).get_json()
        again = finish(client, {**body, 'attempts': body['attempts'][:1]}).get_json()
        assert again['duplicate'] is True
        assert {**again, 'duplicate': False} == first  # the stored result, not the retry body
        assert len(rpc.rows(rush.RUNS_TABLE)) == 1
        assert len(rpc.rows(rush.ATTEMPTS_TABLE)) == 3

    def test_run_id_owned_by_someone_else_is_409(self, client, rpc):
        body = finish_body()
        finish(client, body, auth('tok-a'))
        resp = finish(client, body, auth('tok-b'))
        assert resp.status_code == 409 and resp.get_json()['error'] == 'conflict'

    def test_personal_best_upsert(self, client, rpc):
        def best():
            return [(b['best_score'], b['best_run_id']) for b in rpc.rows(rush.BESTS_TABLE)]

        first = finish_body(('solved',) * 3)
        assert finish(client, first).get_json()['is_new_pb'] is True
        assert best() == [(3, first['run_id'])]

        lower, tie = finish_body(('solved',) * 2), finish_body(('solved',) * 3)
        assert finish(client, lower).get_json()['is_new_pb'] is False
        assert finish(client, tie).get_json()['is_new_pb'] is False
        assert best() == [(3, first['run_id'])]  # ties keep the earlier run

        higher = finish_body(('solved',) * 5)
        data = finish(client, higher).get_json()
        assert data['is_new_pb'] is True and data['personal_rank'] == 1
        assert best() == [(5, higher['run_id'])]
        # Other modes have their own best.
        assert finish(client, finish_body(('solved',), mode='survival')).get_json()['is_new_pb'] is True

    def test_zero_score_is_never_a_pb(self, client, rpc):
        assert finish(client, finish_body(('failed',) * 3, end_reason='strikes')).get_json()['is_new_pb'] is False
        assert rpc.rows(rush.BESTS_TABLE) == []

    def test_ranks(self, client, rpc):
        finish(client, finish_body(('solved',) * 8), auth('tok-b'))
        data = finish(client, finish_body(('solved',) * 4)).get_json()
        assert data['personal_rank'] == 1
        assert data['global_rank'] == {'daily': 2, 'weekly': 2, 'all': 2}

    def test_finished_run_feeds_bests_leaderboard_and_summary(self, client, rpc):
        body = finish_body(('solved', 'failed'))
        finish(client, body)
        bests = client.get('/api/puzzlerush/bests', headers=auth()).get_json()
        assert bests['3min']['top_score'] == 1 and bests['3min']['best_today'] == 1
        board = client.get('/api/puzzlerush/leaderboard?mode=3min&period=daily').get_json()
        assert [(e['user_id'], e['score']) for e in board['entries']] == [(USER_A, 1)]
        # GET /runs/<id> deep link still works for the owner (and only the owner).
        assert client.get(f"/api/puzzlerush/runs/{body['run_id']}", headers=auth('tok-b')).status_code == 403
        summary = client.get(f"/api/puzzlerush/runs/{body['run_id']}", headers=auth()).get_json()
        assert summary['run_over'] is True and [a['result'] for a in summary['attempts']] == ['solved', 'failed']


# ─── Finish: validation / degraded ───────────────────────────────────────────

def _bad_attempts(*patches):
    body = finish_body()
    for i, patch in patches:
        body['attempts'][i] = {**body['attempts'][i], **patch}
    return body


class TestFinishValidation:
    @pytest.mark.parametrize('over, code', [
        ({'mode': '1min'}, 'invalid_mode'),
        ({'run_id': 'not-a-uuid'}, 'invalid_run_id'),
        ({'seed': 'zz'}, 'invalid_seed'),
        ({'end_reason': 'abandoned'}, 'invalid_end_reason'),
        ({'started_at': 'yesterday'}, 'invalid_time'),
        ({'ended_at': (T0 - timedelta(hours=1)).isoformat()}, 'invalid_time'),  # before start
        ({'ended_at': (T0 + timedelta(hours=1)).isoformat()}, 'invalid_time'),  # in the future
        ({'attempts': 'many'}, 'invalid_attempts'),
        ({'attempts': [attempt(i) for i in range(501)]}, 'invalid_attempts'),
        ({'attempts': [attempt(0, 'failed'), attempt(1, 'failed'), attempt(2, 'failed'), attempt(3, 'failed')]},
         'invalid_attempts'),
    ])
    def test_rejected(self, client, rpc, over, code):
        resp = finish(client, finish_body(**over))
        assert resp.status_code == 400 and resp.get_json()['error'] == code
        assert rpc.rows(rush.RUNS_TABLE) == []

    @pytest.mark.parametrize('patch', [
        (1, {'index': 5}),
        (0, {'result': 'won'}),
        (0, {'result': 'unfinished'}),  # only the last puzzle may be unfinished
        (0, {'rating': '400'}),
        (0, {'puzzle_id': ''}),
        (0, {'user_moves': ['e2e4', 'castle']}),
        (0, {'ms': -1}),
    ])
    def test_bad_attempt(self, client, rpc, patch):
        resp = finish(client, _bad_attempts(patch))
        assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_attempts'

    def test_500_attempts_is_allowed(self, client, rpc):
        body = finish_body(mode='survival', attempts=[attempt(i, rating=1500) for i in range(500)], end_reason='quit')
        assert finish(client, body).get_json()['score'] == 500

    def test_missing_rpc_is_a_logged_503(self, client, sb, caplog):
        with caplog.at_level(logging.ERROR, logger='services.puzzle_rush'):
            resp = finish(client, finish_body())
        assert resp.status_code == 503 and resp.get_json()['error'] == 'finish_unavailable'
        assert 'puzzle_rush_finish_run' in caplog.text
