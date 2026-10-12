"""
Tests for the Puzzle Rush API (/api/puzzlerush/*) + engine (services/puzzle_rush.py).

Flask test client over the real blueprint and engine, with:
  • a tiny fixture puzzles SQLite DB (never the real 1.9 GB file),
  • an in-memory Supabase fake that honours the filters the engine uses
    (eq / is_ / not_.is_ / gt / gte / order / limit / count / upsert), so run
    state, bests and leaderboards are exercised for real,
  • a frozen, manually-advanced clock (services.puzzle_rush._now),
  • mocked Clerk JWT decode (token string → user id).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from flask import Flask

from services import puzzle_rush as rush
from services.puzzle_rush_source import PuzzleSource
from services.rate_limiter import RateLimiter
from tests.test_puzzle_rush_source import M1_FEN, make_puzzles_db

# Two-mover: setup a7a6, user e2e4, reply a6a5, user Rd8#.
M2_FEN = '6k1/p4ppp/8/8/8/8/4PPPP/3R2K1 b - - 0 1'
M2_MOVES = 'a7a6 e2e4 a6a5 d1d8'
WRONG = 'g1h1'  # legal, not the solution, not mate — in both templates

USER_A, USER_B = 'user_a', 'user_b'
T0 = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)


# ─── In-memory Supabase ──────────────────────────────────────────────────────

def _key(v):
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            return v
    return v


class FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class FakeQuery:
    def __init__(self, db, table):
        self.rows = db.setdefault(table, [])
        self.op, self.payload, self.conflict = 'select', None, []
        self.filters, self.orders, self._limit, self._count, self._negate = [], [], None, None, False

    def select(self, cols='*', count=None):
        self._count = count
        return self

    def insert(self, data):
        self.op, self.payload = 'insert', data
        return self

    def update(self, data):
        self.op, self.payload = 'update', data
        return self

    def upsert(self, data, on_conflict=''):
        self.op, self.payload, self.conflict = 'upsert', data, on_conflict.split(',')
        return self

    @property
    def not_(self):
        self._negate = True
        return self

    def _filter(self, fn):
        negate, self._negate = self._negate, False
        self.filters.append((lambda r: not fn(r)) if negate else fn)
        return self

    def eq(self, col, val):
        return self._filter(lambda r: r.get(col) == val)

    def is_(self, col, val):
        assert val == 'null'
        return self._filter(lambda r: r.get(col) is None)

    def gt(self, col, val):
        return self._filter(lambda r: r.get(col) is not None and _key(r[col]) > _key(val))

    def gte(self, col, val):
        return self._filter(lambda r: r.get(col) is not None and _key(r[col]) >= _key(val))

    def order(self, col, desc=False):
        self.orders.append((col, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        if self.op == 'insert':
            self.rows.append(dict(self.payload))
            return FakeResult([dict(self.payload)])
        if self.op == 'upsert':
            for r in self.rows:
                if all(r.get(c) == self.payload.get(c) for c in self.conflict):
                    r.update(self.payload)
                    return FakeResult([dict(r)])
            self.rows.append(dict(self.payload))
            return FakeResult([dict(self.payload)])
        matched = [r for r in self.rows if all(f(r) for f in self.filters)]
        if self.op == 'update':
            for r in matched:
                r.update(self.payload)
            return FakeResult([dict(r) for r in matched])
        for col, desc in reversed(self.orders):
            matched.sort(key=lambda r: _key(r.get(col)), reverse=desc)
        count = len(matched)
        if self._limit is not None:
            matched = matched[:self._limit]
        return FakeResult([dict(r) for r in matched], count if self._count else None)


class MissingRpc(Exception):
    """What supabase-py raises (PGRST202) when the function isn't deployed."""


class FakeRpc:
    def __init__(self, fn, params):
        self.fn, self.params = fn, params

    def execute(self):
        return FakeResult(self.fn(**self.params))


class FakeSupabase:
    def __init__(self):
        self.db = {}
        self.functions = {}

    def table(self, name):
        return FakeQuery(self.db, name)

    def rpc(self, name, params):
        if name not in self.functions:
            raise MissingRpc(f'Could not find the function public.{name}')
        return FakeRpc(self.functions[name], params)

    def rows(self, name):
        return self.db.get(name, [])


# ─── Fixtures ────────────────────────────────────────────────────────────────

class Clock:
    def __init__(self, now):
        self.now = now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def m(pid, rating, fen=M1_FEN, moves='a7a6 d1d8'):
    return (pid, fen, moves, rating, 70, 90)


def default_puzzles():
    return [m(f'M1-{r}', r) for r in range(300, 3305, 5)]


@pytest.fixture
def puzzles_db(tmp_path):
    """Call with a row list to (re)build the source DB; default is all mate-in-1s."""
    state = {}

    def build(rows=None):
        path = make_puzzles_db(tmp_path / f'p{len(state)}.db', rows or default_puzzles())
        state['source'] = PuzzleSource(path)
        return state['source']

    build()
    with patch('services.puzzle_rush.get_puzzle_source', side_effect=lambda: state['source']):
        yield build


@pytest.fixture
def sb():
    fake = FakeSupabase()
    with patch('services.puzzle_rush.supabase', fake):
        yield fake


@pytest.fixture
def clock():
    c = Clock(T0)
    with patch('services.puzzle_rush._now', side_effect=lambda: c.now):
        yield c


def _decode(token):
    users = {'tok-a': USER_A, 'tok-b': USER_B}
    if token not in users:
        raise jwt.InvalidTokenError('bad token')
    return {'sub': users[token]}


@pytest.fixture(autouse=True)
def mocks():
    with patch('utils.auth._decode_clerk_token', side_effect=_decode), \
            patch('services.puzzle_rush._display_name', side_effect=lambda uid: f'Name {uid}'), \
            patch('api.puzzle_rush.guest_limiter', RateLimiter()):
        yield


@pytest.fixture
def client(puzzles_db, sb, clock):
    from api.puzzle_rush import puzzle_rush_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(puzzle_rush_bp)
    return app.test_client()


def auth(token='tok-a'):
    return {'Authorization': f'Bearer {token}'}


def start(client, mode='3min', headers=None):
    resp = client.post('/api/puzzlerush/runs', json={'mode': mode}, headers=headers or {})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def move(client, run, uci, headers=None):
    headers = dict(headers or {})
    if run.get('guest_token'):
        headers['X-Guest-Token'] = run['guest_token']
    return client.post(f"/api/puzzlerush/runs/{run['run_id']}/move", json={'uci': uci}, headers=headers)


def assert_no_solution(payload, *solution_moves):
    """Active-run payloads never carry the remaining line."""
    text = json.dumps(payload)
    for key in ('"moves"', '"solution"'):
        assert key not in text
    for uci in solution_moves:
        assert uci not in text


# ─── Run creation ────────────────────────────────────────────────────────────

class TestCreateRun:
    def test_guest_run_gets_token_clock_and_public_puzzle(self, client, sb):
        data = start(client, '3min')
        assert data['guest_token']
        assert data['started_at'] == (T0 + timedelta(seconds=3)).isoformat()
        assert data['deadline'] == (T0 + timedelta(seconds=183)).isoformat()
        puzzle = data['puzzle']
        assert set(puzzle) == {'id', 'index', 'fen', 'setup_move', 'rating', 'color'}
        assert puzzle['setup_move'] == 'a7a6' and puzzle['color'] == 'white' and puzzle['index'] == 0
        assert abs(puzzle['rating'] - 400) <= 30
        assert_no_solution(data, 'd1d8')
        run = sb.rows(rush.RUNS_TABLE)[0]
        assert run['user_id'] is None
        assert run['guest_token_hash'] == rush.hash_token(data['guest_token'])
        assert data['guest_token'] not in json.dumps(sb.db)

    def test_user_run_has_no_guest_token(self, client, sb):
        data = start(client, '5min', auth())
        assert 'guest_token' not in data
        assert data['deadline'] == (T0 + timedelta(seconds=303)).isoformat()
        assert sb.rows(rush.RUNS_TABLE)[0]['user_id'] == USER_A

    def test_survival_has_no_deadline(self, client):
        assert start(client, 'survival')['deadline'] is None

    def test_invalid_mode(self, client):
        resp = client.post('/api/puzzlerush/runs', json={'mode': '1min'})
        assert resp.status_code == 400 and resp.get_json()['error'] == 'invalid_mode'

    def test_invalid_bearer_token_is_401_not_guest(self, client):
        resp = client.post('/api/puzzlerush/runs', json={'mode': '3min'}, headers=auth('nope'))
        assert resp.status_code == 401

    def test_guest_creation_rate_limited(self, client):
        for _ in range(RateLimiter.TIERS['free'].requests_per_hour):
            start(client)
        resp = client.post('/api/puzzlerush/runs', json={'mode': '3min'})
        assert resp.status_code == 429
        # Signed-in users aren't subject to the guest limiter.
        start(client, headers=auth())


# ─── Moves ───────────────────────────────────────────────────────────────────

class TestMoves:
    def test_correct_solves_and_serves_next(self, client, sb):
        run = start(client)
        data = move(client, run, 'd1d8').get_json()
        assert data['result'] == 'solved'
        assert (data['score'], data['strikes'], data['streak'], data['run_over']) == (1, 0, 1, False)
        assert data['next_puzzle']['index'] == 1
        assert abs(data['next_puzzle']['rating'] - 446) <= 30
        assert_no_solution(data, 'd1d8')
        first = sb.rows(rush.ATTEMPTS_TABLE)[0]
        assert first['result'] == 'solved' and first['user_moves'] == 'd1d8'

    def test_wrong_move_strikes_resets_streak_and_advances_ramp(self, client, sb):
        run = start(client)
        move(client, run, 'd1d8')
        data = move(client, run, WRONG).get_json()
        assert data['result'] == 'wrong'
        assert (data['score'], data['strikes'], data['streak']) == (1, 1, 0)
        assert data['next_puzzle']['index'] == 2
        assert abs(data['next_puzzle']['rating'] - target(2)) <= 30
        assert_no_solution(data, 'd1d8')
        assert sb.rows(rush.ATTEMPTS_TABLE)[1]['result'] == 'failed'

    def test_alternate_checkmate_is_accepted(self, client):
        run = start(client)
        assert move(client, run, 'e1e8').get_json()['result'] == 'solved'

    def test_multi_move_puzzle(self, client, puzzles_db):
        puzzles_db([m('M2-only', 400, M2_FEN, M2_MOVES)] + [m(f'M1-{r}', r) for r in range(700, 3300, 5)])
        run = start(client)
        assert run['puzzle']['id'] == 'M2-only'
        data = move(client, run, 'e2e4').get_json()
        assert data['result'] == 'correct' and data['reply'] == 'a6a5'
        assert 'next_puzzle' not in data and data['score'] == 0
        assert_no_solution(data, 'd1d8')
        data = move(client, run, 'd1d8').get_json()
        assert data['result'] == 'solved' and data['score'] == 1 and data['next_puzzle']['index'] == 1

    def test_multi_move_wrong_at_second_ply_fails(self, client, puzzles_db):
        puzzles_db([m('M2-only', 400, M2_FEN, M2_MOVES)] + [m(f'M1-{r}', r) for r in range(700, 3300, 5)])
        run = start(client)
        move(client, run, 'e2e4')
        data = move(client, run, WRONG).get_json()
        assert data['result'] == 'wrong' and data['strikes'] == 1

    def test_multi_move_early_mate_counts(self, client, puzzles_db):
        puzzles_db([m('M2-only', 400, M2_FEN, M2_MOVES)] + [m(f'M1-{r}', r) for r in range(700, 3300, 5)])
        run = start(client)
        assert move(client, run, 'd1d8').get_json()['result'] == 'solved'

    def test_illegal_move_is_rejected_without_strike(self, client):
        run = start(client)
        for uci in ('d1d9', 'e2e4', 'zzz'):
            resp = move(client, run, uci)
            assert resp.status_code == 400
        assert move(client, run, WRONG).get_json()['strikes'] == 1

    def test_missing_uci(self, client):
        run = start(client)
        resp = client.post(f"/api/puzzlerush/runs/{run['run_id']}/move", json={},
                           headers={'X-Guest-Token': run['guest_token']})
        assert resp.status_code == 400

    def test_no_puzzle_repeats_in_run(self, client, puzzles_db):
        # One puzzle per 10 points: bands are tiny, so repeats would show up fast.
        puzzles_db([m(f'M1-{r}', r) for r in range(380, 1200, 10)])
        run = start(client, 'survival')
        seen = [run['puzzle']['id']]
        for i in range(12):
            data = move(client, run, 'd1d8').get_json()
            seen.append(data['next_puzzle']['id'])
        assert len(seen) == len(set(seen))

    def test_three_strikes_end_run(self, client):
        run = start(client, headers=auth())
        move(client, run, 'd1d8', auth())
        move(client, run, WRONG, auth())
        move(client, run, WRONG, auth())
        data = move(client, run, WRONG, auth()).get_json()
        assert data['run_over'] and data['end_reason'] == 'strikes'
        assert data['strikes'] == 3 and data['score'] == 1 and 'next_puzzle' not in data
        assert data['results']['score'] == 1 and data['results']['longest_streak'] == 1
        resp = move(client, run, 'd1d8', auth())
        assert resp.status_code == 409 and resp.get_json()['end_reason'] == 'strikes'

    def test_stats_tracked(self, client, clock, sb):
        run = start(client, headers=auth())
        clock.advance(seconds=5)          # 2 s into the run (3 s countdown)
        move(client, run, 'd1d8', auth())
        clock.advance(seconds=4)
        move(client, run, 'd1d8', auth())
        clock.advance(seconds=6)
        move(client, run, WRONG, auth())
        clock.advance(seconds=3)
        data = client.post(f"/api/puzzlerush/runs/{run['run_id']}/quit", headers=auth()).get_json()
        results = data['results']
        assert results['longest_streak'] == 2
        assert results['highest_solved_rating'] == sb.rows(rush.ATTEMPTS_TABLE)[1]['puzzle_rating']
        assert results['avg_ms_per_puzzle'] == 4000  # (2000 + 4000 + 6000) / 3
        assert results['duration_ms'] == 15000


def target(i):
    from services.puzzle_rush_source import target_rating
    return target_rating(i)


# ─── Clock, quit, abandon ────────────────────────────────────────────────────

class TestClock:
    def test_move_before_deadline_accepted(self, client, clock):
        run = start(client, '3min')
        clock.advance(seconds=182, milliseconds=999)
        assert move(client, run, 'd1d8').status_code == 200

    def test_move_after_deadline_rejected_and_times_out(self, client, clock, sb):
        run = start(client, '3min')
        move(client, run, 'd1d8')
        clock.advance(seconds=200)
        resp = move(client, run, 'd1d8')
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['error'] == 'run_over' and data['end_reason'] == 'timeout' and data['score'] == 1
        stored = sb.rows(rush.RUNS_TABLE)[0]
        assert stored['ended_at'] == (T0 + timedelta(seconds=183)).isoformat()
        assert stored['duration_ms'] == 180000
        # The rejected move was not recorded.
        assert sb.rows(rush.ATTEMPTS_TABLE)[1]['user_moves'] == ''

    def test_get_lazily_times_out(self, client, clock):
        run = start(client, '5min')
        clock.advance(minutes=6)
        data = client.get(f"/api/puzzlerush/runs/{run['run_id']}",
                          headers={'X-Guest-Token': run['guest_token']}).get_json()
        assert data['run_over'] and data['end_reason'] == 'timeout'

    def test_survival_idle_becomes_abandoned(self, client, clock):
        run = start(client, 'survival')
        move(client, run, 'd1d8')
        clock.advance(minutes=9)
        assert move(client, run, 'd1d8').status_code == 200  # 9 min idle is fine
        clock.advance(minutes=10, seconds=1)
        data = client.get(f"/api/puzzlerush/runs/{run['run_id']}",
                          headers={'X-Guest-Token': run['guest_token']}).get_json()
        assert data['end_reason'] == 'abandoned' and data['score'] == 2

    def test_stale_runs_closed_when_user_starts_new_one(self, client, clock, sb):
        run = start(client, 'survival', auth())
        move(client, run, 'd1d8', auth())
        clock.advance(minutes=11)
        start(client, 'survival', auth())
        old = next(r for r in sb.rows(rush.RUNS_TABLE) if r['id'] == run['run_id'])
        assert old['end_reason'] == 'abandoned'
        assert sb.rows(rush.BESTS_TABLE)[0]['best_score'] == 1

    def test_quit_records_score_and_is_idempotent(self, client):
        run = start(client, headers=auth())
        move(client, run, 'd1d8', auth())
        url = f"/api/puzzlerush/runs/{run['run_id']}/quit"
        data = client.post(url, headers=auth()).get_json()
        assert data['run_over'] and data['end_reason'] == 'quit' and data['score'] == 1
        again = client.post(url, headers=auth()).get_json()
        assert again['end_reason'] == 'quit' and again['score'] == 1


# ─── Summary / solution exposure ─────────────────────────────────────────────

class TestSummary:
    def test_active_summary_hides_solutions(self, client, puzzles_db):
        puzzles_db([m('M2-only', 400, M2_FEN, M2_MOVES)] + [m(f'M1-{r}', r) for r in range(700, 3300, 5)])
        run = start(client)
        move(client, run, 'e2e4')
        data = client.get(f"/api/puzzlerush/runs/{run['run_id']}",
                          headers={'X-Guest-Token': run['guest_token']}).get_json()
        assert not data['run_over']
        assert_no_solution(data, 'd1d8')
        # Resume info: only what was already revealed.
        assert data['current_puzzle']['played'] == ['a7a6', 'e2e4', 'a6a5']

    def test_ended_summary_exposes_solutions(self, client):
        run = start(client, headers=auth())
        move(client, run, WRONG, auth())
        client.post(f"/api/puzzlerush/runs/{run['run_id']}/quit", headers=auth())
        data = client.get(f"/api/puzzlerush/runs/{run['run_id']}", headers=auth()).get_json()
        assert data['run_over']
        first = data['attempts'][0]
        assert first['result'] == 'failed' and first['user_moves'] == [WRONG]
        assert first['solution'] == ['a7a6', 'd1d8'] and first['fen'] == M1_FEN
        assert 'results' in data


# ─── Access control ──────────────────────────────────────────────────────────

class TestAccess:
    def test_guest_token_required_and_must_match(self, client):
        run = start(client)
        url = f"/api/puzzlerush/runs/{run['run_id']}/move"
        assert client.post(url, json={'uci': 'd1d8'}).status_code == 403
        assert client.post(url, json={'uci': 'd1d8'}, headers={'X-Guest-Token': 'x' * 32}).status_code == 403
        assert client.get(f"/api/puzzlerush/runs/{run['run_id']}").status_code == 403
        # Body token works too.
        resp = client.post(url, json={'uci': 'd1d8', 'guest_token': run['guest_token']})
        assert resp.status_code == 200

    def test_other_user_cannot_touch_run(self, client):
        run = start(client, headers=auth('tok-a'))
        base = f"/api/puzzlerush/runs/{run['run_id']}"
        assert client.post(f'{base}/move', json={'uci': 'd1d8'}, headers=auth('tok-b')).status_code == 403
        assert client.post(f'{base}/quit', headers=auth('tok-b')).status_code == 403
        assert client.get(base, headers=auth('tok-b')).status_code == 403
        assert client.post(f'{base}/move', json={'uci': 'd1d8'}).status_code == 403  # anonymous

    def test_user_run_cannot_be_hijacked_with_guest_token(self, client):
        guest = start(client)
        mine = start(client, headers=auth())
        resp = client.post(f"/api/puzzlerush/runs/{mine['run_id']}/move", json={'uci': 'd1d8'},
                           headers={'X-Guest-Token': guest['guest_token']})
        assert resp.status_code == 403

    def test_unknown_and_malformed_run_ids(self, client):
        assert client.get('/api/puzzlerush/runs/not-a-uuid').status_code == 404
        assert client.get('/api/puzzlerush/runs/00000000-0000-0000-0000-000000000000').status_code == 404

    def test_concurrent_write_conflict(self, client, sb):
        start(client, headers=auth())
        stale = dict(sb.rows(rush.RUNS_TABLE)[0])
        sb.rows(rush.RUNS_TABLE)[0]['move_seq'] += 1  # another request committed meanwhile
        with pytest.raises(rush.RushError) as e:
            rush.submit_move(stale, 'd1d8', rush.resolve_tz(None))
        assert e.value.status == 409
        assert sb.rows(rush.RUNS_TABLE)[0]['score'] == 0
        assert len(sb.rows(rush.ATTEMPTS_TABLE)) == 1


# ─── Bests ───────────────────────────────────────────────────────────────────

def seed_run(sb, user_id, mode, score, ended_at, run_id=None):
    run_id = run_id or f'00000000-0000-0000-0000-{len(sb.rows(rush.RUNS_TABLE)):012d}'
    sb.table(rush.RUNS_TABLE).insert({
        'id': run_id, 'user_id': user_id, 'display_name': f'Name {user_id}', 'mode': mode,
        'score': score, 'ended_at': ended_at.isoformat(), 'end_reason': 'quit',
    }).execute()
    if user_id:
        best = next((b for b in sb.rows(rush.BESTS_TABLE) if b['user_id'] == user_id and b['mode'] == mode), None)
        if not best or score > best['best_score']:
            sb.table(rush.BESTS_TABLE).upsert({
                'user_id': user_id, 'mode': mode, 'best_score': score, 'best_run_id': run_id,
                'display_name': f'Name {user_id}', 'achieved_at': ended_at.isoformat(),
            }, on_conflict='user_id,mode').execute()
    return run_id


class TestBests:
    def play(self, client, solves, mode='3min', headers=None):
        headers = headers if headers is not None else auth()
        run = start(client, mode, headers)
        for _ in range(solves):
            move(client, run, 'd1d8', headers)
        return client.post(f"/api/puzzlerush/runs/{run['run_id']}/quit",
                           headers={**headers, **({'X-Guest-Token': run['guest_token']}
                                                  if run.get('guest_token') else {})}).get_json()

    def test_pb_updates_only_on_strictly_higher_score(self, client, sb):
        assert self.play(client, 2)['results']['is_new_pb'] is True
        assert self.play(client, 1)['results']['is_new_pb'] is False
        assert self.play(client, 2)['results']['is_new_pb'] is False  # tie keeps earlier run
        bests = sb.rows(rush.BESTS_TABLE)
        assert len(bests) == 1 and bests[0]['best_score'] == 2
        first_run = sb.rows(rush.RUNS_TABLE)[0]['id']
        assert bests[0]['best_run_id'] == first_run
        assert self.play(client, 3)['results']['is_new_pb'] is True
        assert sb.rows(rush.BESTS_TABLE)[0]['best_score'] == 3

    def test_zero_score_is_never_a_pb(self, client, sb):
        assert self.play(client, 0)['results']['is_new_pb'] is False
        assert sb.rows(rush.BESTS_TABLE) == []

    def test_guest_runs_never_touch_bests_or_ranks(self, client, sb):
        results = self.play(client, 3, headers={})['results']
        assert results['is_new_pb'] is False
        assert results['personal_rank'] is None and results['global_rank'] is None
        assert sb.rows(rush.BESTS_TABLE) == []

    def test_bests_endpoint_requires_auth(self, client):
        assert client.get('/api/puzzlerush/bests').status_code == 401

    def test_bests_top_score_and_best_today(self, client, sb, clock):
        clock.now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        seed_run(sb, USER_A, '3min', 20, datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))
        seed_run(sb, USER_A, '3min', 7, datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc))
        seed_run(sb, USER_A, '3min', 9, datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc))
        seed_run(sb, USER_B, '3min', 30, datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc))
        data = client.get('/api/puzzlerush/bests', headers=auth()).get_json()
        assert data['3min']['top_score'] == 20 and data['3min']['best_today'] == 9
        assert data['5min'] == {'top_score': None, 'top_run_id': None, 'achieved_at': None, 'best_today': None}
        assert set(data) == {'3min', '5min', 'survival'}

    def test_best_today_uses_local_day_boundary(self, client, sb, clock):
        # 18:30Z on Oct 12 is 23:30 in Almaty (UTC+5); 19:30Z is already Oct 13 there.
        seed_run(sb, USER_A, '5min', 12, datetime(2026, 10, 12, 18, 30, tzinfo=timezone.utc))
        clock.now = datetime(2026, 10, 12, 19, 30, tzinfo=timezone.utc)
        almaty = client.get('/api/puzzlerush/bests', headers=auth()).get_json()
        assert almaty['5min']['best_today'] is None and almaty['5min']['top_score'] == 12
        utc = client.get('/api/puzzlerush/bests?tz=UTC', headers=auth()).get_json()
        assert utc['5min']['best_today'] == 12
        clock.now = datetime(2026, 10, 12, 18, 45, tzinfo=timezone.utc)  # 23:45 Almaty, same day
        assert client.get('/api/puzzlerush/bests', headers=auth()).get_json()['5min']['best_today'] == 12

    def test_invalid_tz(self, client):
        assert client.get('/api/puzzlerush/bests?tz=Mars/Base', headers=auth()).status_code == 400


# ─── Leaderboard ─────────────────────────────────────────────────────────────

class TestLeaderboard:
    @pytest.fixture
    def seeded(self, sb, clock):
        # Wednesday 2026-10-14, 12:00 Almaty. Week starts Mon 00:00 Almaty = Sun 19:00Z.
        clock.now = datetime(2026, 10, 14, 7, 0, tzinfo=timezone.utc)
        d = lambda *a: datetime(*a, tzinfo=timezone.utc)  # noqa: E731
        seed_run(sb, USER_A, '3min', 15, d(2026, 9, 1, 10))      # all-time only
        seed_run(sb, USER_A, '3min', 8, d(2026, 10, 14, 5))      # today
        seed_run(sb, USER_A, '3min', 6, d(2026, 10, 14, 6))      # today
        seed_run(sb, USER_B, '3min', 10, d(2026, 10, 11, 20))    # this week (Mon 01:00 Almaty)
        seed_run(sb, USER_B, '3min', 4, d(2026, 10, 11, 18))     # last week (Sun 23:00 Almaty)
        seed_run(sb, 'user_c', '3min', 12, d(2026, 10, 14, 6, 30))
        seed_run(sb, 'user_c', '3min', 12, d(2026, 10, 14, 6, 45))
        seed_run(sb, None, '3min', 99, d(2026, 10, 14, 6))       # guest: never ranked
        seed_run(sb, USER_A, '5min', 50, d(2026, 10, 14, 6))     # other mode

    def board(self, client, headers=None, **params):
        qs = '&'.join(f'{k}={v}' for k, v in {'mode': '3min', **params}.items())
        resp = client.get(f'/api/puzzlerush/leaderboard?{qs}', headers=headers or {})
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()

    def test_daily(self, client, seeded):
        data = self.board(client, auth(), period='daily')
        assert [(e['user_id'], e['score'], e['rank']) for e in data['entries']] == [('user_c', 12, 1), (USER_A, 8, 2)]
        assert data['entries'][0]['display_name'] == 'Name user_c'
        assert data['me'] == {'score': 8, 'rank': 2}

    def test_weekly(self, client, seeded):
        data = self.board(client, auth('tok-b'), period='weekly')
        assert [(e['user_id'], e['score']) for e in data['entries']] == [
            ('user_c', 12), (USER_B, 10), (USER_A, 8)]
        assert data['me'] == {'score': 10, 'rank': 2}

    def test_all_time(self, client, seeded):
        data = self.board(client, period='all')
        assert [(e['user_id'], e['score']) for e in data['entries']] == [
            (USER_A, 15), ('user_c', 12), (USER_B, 10)]
        assert data['me'] is None

    def test_ties_share_rank(self, client, seeded, sb):
        seed_run(sb, 'user_d', '3min', 12, datetime(2026, 10, 14, 6, 50, tzinfo=timezone.utc))
        data = self.board(client, period='daily')
        assert [(e['user_id'], e['rank']) for e in data['entries']] == [
            ('user_c', 1), ('user_d', 1), (USER_A, 3)]

    def test_personal_scope(self, client, seeded):
        data = self.board(client, auth(), period='all', scope='personal')
        assert [e['score'] for e in data['entries']] == [15, 8, 6]
        assert [e['rank'] for e in data['entries']] == [1, 2, 3]
        assert [e['score'] for e in self.board(client, auth(), period='daily', scope='personal')['entries']] == [8, 6]

    def test_personal_requires_auth(self, client, seeded):
        assert client.get('/api/puzzlerush/leaderboard?mode=3min&scope=personal').status_code == 401

    @pytest.mark.parametrize('params', ['mode=1min', 'period=hourly', 'scope=friends'])
    def test_invalid_params(self, client, params):
        assert client.get(f'/api/puzzlerush/leaderboard?{params}').status_code == 400

    def test_results_payload_ranks(self, client, seeded, clock):
        run = start(client, '3min', auth('tok-b'))
        for _ in range(11):
            move(client, run, 'd1d8', auth('tok-b'))
        data = client.post(f"/api/puzzlerush/runs/{run['run_id']}/quit", headers=auth('tok-b')).get_json()
        results = data['results']
        assert results['is_new_pb'] is True
        assert results['personal_rank'] == 1
        # Daily: user_c 12 beats 11 → #2. Weekly same. All-time: A 15, c 12 → #3.
        assert results['global_rank'] == {'daily': 2, 'weekly': 2, 'all': 3}


# ─── Registration ────────────────────────────────────────────────────────────

def test_blueprint_registered_in_app():
    """Import the real app.py in a subprocess (it has import-time side effects)
    and check the routes are on its url_map."""
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import app; print('\\n'.join(r.rule for r in app.app.url_map.iter_rules() "
            "if r.rule.startswith('/api/puzzlerush')))")
    out = subprocess.run([sys.executable, '-c', code], cwd=backend, capture_output=True, text=True, timeout=90)
    rules = set(out.stdout.split())
    assert {
        '/api/puzzlerush/runs', '/api/puzzlerush/runs/<run_id>/move', '/api/puzzlerush/runs/<run_id>/quit',
        '/api/puzzlerush/runs/<run_id>', '/api/puzzlerush/bests', '/api/puzzlerush/leaderboard',
        '/api/puzzlerush/pack', '/api/puzzlerush/runs/finish',
    } <= rules, out.stderr[-2000:]
