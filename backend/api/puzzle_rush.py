"""
Puzzle Rush API — thin HTTP layer over services/puzzle_rush.py.

v2 (instant moves): `GET /pack` is public and stateless; the client plays the
run locally and signed-in players record it with `POST /runs/finish`
(`Authorization: Bearer <Clerk JWT>` — no cookies, so mobile clients work the
same way). Guests never call the server during or after a run.

Legacy v1 routes (`POST /runs`, `/runs/<id>/move`, `/runs/<id>/quit`) stay one
release for open tabs. Auth there is optional (§7.6): a valid Clerk bearer
token makes the run the user's; without one the run is a guest run and the
returned `guest_token` must be sent on every later call (header
`X-Guest-Token`, or `guest_token` in the body/query). Ownership: a user's run is
only reachable by that user; a guest run only with its token. Guest run
creation is rate-limited per client IP.
"""

import hmac
import logging

from flask import Blueprint, jsonify, request

from services import puzzle_rush as rush
from services.rate_limiter import RateLimiter
from utils.auth import _caller_user_id

logger = logging.getLogger(__name__)

puzzle_rush_bp = Blueprint('puzzle_rush', __name__)

# Dedicated instance: guest IPs must not share buckets with the LLM limiter.
guest_limiter = RateLimiter()


def _client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    return forwarded.split(',')[0].strip() or request.remote_addr or 'unknown'


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _guest_token() -> str | None:
    return (request.headers.get('X-Guest-Token')
            or _body().get('guest_token')
            or request.args.get('guest_token'))


def _tz():
    return rush.resolve_tz(request.args.get('tz') or _body().get('tz'))


def _error(e: rush.RushError):
    return jsonify({'error': e.code, **e.payload}), e.status


def _optional_user() -> str | None:
    """Clerk user id if a bearer token is sent, None if anonymous. A token that
    is sent but invalid is a 401, never a silent downgrade to a guest run."""
    if not request.headers.get('Authorization', '').startswith('Bearer '):
        return None
    user_id = _caller_user_id()
    if not user_id:
        raise rush.RushError('invalid_token', 401)
    return user_id


def _owned_run(run_id: str):
    """Load a run the caller may act on, or raise a 404/403 RushError."""
    run = rush.load_run(run_id)
    if not run:
        raise rush.RushError('not_found', 404)
    if run.get('user_id'):
        if _optional_user() != run['user_id']:
            raise rush.RushError('forbidden', 403)
    else:
        token = _guest_token()
        if not token or not hmac.compare_digest(rush.hash_token(token), run.get('guest_token_hash') or ''):
            raise rush.RushError('forbidden', 403)
    return run


@puzzle_rush_bp.errorhandler(rush.RushError)
def _handle_rush_error(e):
    return _error(e)


# Packs are a pure function of (seed, from, count) and the static puzzles DB.
PACK_CACHE_CONTROL = 'public, max-age=86400, immutable'


@puzzle_rush_bp.route('/api/puzzlerush/pack', methods=['GET'])
def get_pack():
    resp = jsonify(rush.pack(request.args.get('seed'), request.args.get('from'), request.args.get('count')))
    resp.headers['Cache-Control'] = PACK_CACHE_CONTROL
    return resp


@puzzle_rush_bp.route('/api/puzzlerush/runs/finish', methods=['POST'])
def finish_run():
    user_id = _optional_user()
    if not user_id:
        raise rush.RushError('auth_required', 401)
    return jsonify(rush.finish_run(user_id, _body(), _tz()))


@puzzle_rush_bp.route('/api/puzzlerush/runs', methods=['POST'])
def create_run():
    user_id = _optional_user()
    if not user_id:
        key = f'puzzlerush-guest:{_client_ip()}'
        allowed, reason = guest_limiter.check_rate_limit(key)
        if not allowed:
            return jsonify({'error': 'rate_limited', 'message': reason}), 429
        guest_limiter.track_request(key)

    run, guest_token, puzzle = rush.create_run(_body().get('mode'), user_id)
    payload = {
        'run_id': run['id'],
        'mode': run['mode'],
        'started_at': run['started_at'],
        'deadline': run.get('deadline_at'),
        'server_now': rush.run_state(run)['server_now'],
        'puzzle': puzzle,
    }
    if guest_token:
        payload['guest_token'] = guest_token
    return jsonify(payload), 201


@puzzle_rush_bp.route('/api/puzzlerush/runs/<run_id>/move', methods=['POST'])
def submit_move(run_id):
    run = _owned_run(run_id)
    uci = _body().get('uci')
    if not isinstance(uci, str):
        return jsonify({'error': 'uci is required'}), 400
    return jsonify(rush.submit_move(run, uci.strip(), _tz()))


@puzzle_rush_bp.route('/api/puzzlerush/runs/<run_id>/quit', methods=['POST'])
def quit_run(run_id):
    run = _owned_run(run_id)
    return jsonify(rush.quit_run(run, _tz()))


@puzzle_rush_bp.route('/api/puzzlerush/runs/<run_id>', methods=['GET'])
def get_run(run_id):
    run = _owned_run(run_id)
    return jsonify(rush.get_summary(run, _tz()))


@puzzle_rush_bp.route('/api/puzzlerush/bests', methods=['GET'])
def get_bests():
    # Not @verify_clerk_token: its catch-all would turn our 4xx errors into 500s.
    user_id = _optional_user()
    if not user_id:
        raise rush.RushError('auth_required', 401)
    return jsonify(rush.get_bests(user_id, _tz()))


@puzzle_rush_bp.route('/api/puzzlerush/leaderboard', methods=['GET'])
def get_leaderboard():
    return jsonify(rush.leaderboard(
        request.args.get('mode', '5min'),
        request.args.get('period', 'daily'),
        request.args.get('scope', 'global'),
        _optional_user(),
        _tz(),
    ))
