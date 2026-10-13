"""
Puzzle Rush school / branch ranking — push Chesster survival runs to Chess
Empire and proxy CE's school boards (CE `students-api`, P2 backend).

CE `survival_scores` is the single source of truth for school scores. Rules
(locked): only survival runs count; a finished run is pushed iff score > 0 and
it beats the student's CE best this week OR this month OR all-time (a missing
best counts as beaten). Family accounts (>1 active CE link) never push until the
user claims the run for one student (`claim`); the pick is remembered and
pre-selected next time, but every run still needs its own claim.

Everything here is best-effort: CE errors become `{status: 'error'}` and are
logged, never raised into the run flow. The outcome is stored on the run
(`school_*` columns, migration 052) so it can be shown and retried.

Ranks are not computed at finish time (it would cost up to six CE calls on the
results screen); the client fetches the school/branch board instead.
"""

import logging
import os
import time
from datetime import datetime, timezone

from services.chess_empire_client import ChessEmpireAPIError, get_client
from services.supabase_client import supabase
from utils.auth import _member_row_state

logger = logging.getLogger(__name__)

RUNS_TABLE = 'puzzle_rush_runs'
PICKS_TABLE = 'puzzle_rush_school_pick'
MEMBERS_TABLE = 'organization_members'

PERIODS = ('week', 'month', 'all')
PERIOD_ALIASES = {'weekly': 'week', 'monthly': 'month'}
SCOPES = ('school', 'branch')
BOARD_SIZE = 50
CACHE_TTL = 60.0
INFO_TTL = 600.0

_board_cache: dict = {}
_info_cache: dict = {}


class SchoolError(Exception):
    def __init__(self, code: str, status: int = 400, payload: dict | None = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.payload = payload or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def push_enabled() -> bool:
    """Kill switch: PUZZLE_RUSH_SCHOOL_PUSH=0 stops pushes (boards keep working)."""
    return os.getenv('PUZZLE_RUSH_SCHOOL_PUSH', '1') != '0'


# ─── Links ───────────────────────────────────────────────────────────────────

def linked_student_ids(user_id: str) -> list:
    """The user's active CE student links (verified, not expired), oldest first."""
    rows = supabase.table(MEMBERS_TABLE) \
        .select('id, external_student_id, link_status, access_expires_at, role') \
        .eq('user_id', user_id).eq('external_source', 'chess_empire') \
        .order('id').execute().data or []
    ids = []
    for r in rows:
        sid = r.get('external_student_id')
        if r.get('role') != 'coach' and _member_row_state(r) == 'verified' and sid not in ids:
            ids.append(sid)
    return ids


def student_info(student_ids: list) -> dict:
    """{student_id: {first_name, last_name, branch_id}}, cached; {} on CE failure."""
    now = time.monotonic()
    missing = [s for s in student_ids if s not in _info_cache or _info_cache[s][0] < now]
    if missing:
        try:
            for row in get_client().get_students(missing) or []:
                _info_cache[row['id']] = (now + INFO_TTL, {
                    'first_name': row.get('first_name'),
                    'last_name': row.get('last_name'),
                    'branch_id': row.get('branch_id'),
                })
        except (ChessEmpireAPIError, KeyError, TypeError) as e:
            logger.warning('puzzle rush school: CE student lookup failed: %s', e)
    return {s: _info_cache[s][1] for s in student_ids if s in _info_cache}


def linked_students(user_id: str) -> list:
    """Active links with names / branch where CE returns them."""
    ids = linked_student_ids(user_id)
    info = student_info(ids)
    return [{'student_id': s, **info.get(s, {'first_name': None, 'last_name': None, 'branch_id': None})}
            for s in ids]


def get_pick(user_id: str) -> str | None:
    try:
        rows = supabase.table(PICKS_TABLE).select('external_student_id') \
            .eq('user_id', user_id).limit(1).execute().data
    except Exception as e:  # table missing before migration 052
        logger.warning('puzzle rush school: pick lookup failed: %s', e)
        return None
    return rows[0]['external_student_id'] if rows else None


def save_pick(user_id: str, student_id: str):
    try:
        supabase.table(PICKS_TABLE).upsert({
            'user_id': user_id,
            'external_student_id': student_id,
            'updated_at': _now().isoformat(),
        }, on_conflict='user_id').execute()
    except Exception as e:
        logger.warning('puzzle rush school: saving pick failed: %s', e)


# ─── Push ────────────────────────────────────────────────────────────────────

def stored(run: dict) -> dict | None:
    """The outcome persisted on a run (no network), or None if there is none."""
    if not run.get('school_push_status'):
        return None
    return {'status': run['school_push_status'], 'student_id': run.get('school_student_id')}


def _save(run: dict, result: dict):
    changes = {'school_push_status': result['status'], 'school_student_id': result.get('student_id')}
    if result['status'] == 'pushed':
        changes['school_pushed_at'] = _now().isoformat()
    try:
        supabase.table(RUNS_TABLE).update(changes).eq('id', run['id']).execute()
    except Exception as e:  # columns missing before migration 052
        logger.warning('puzzle rush school: saving outcome of run %s failed: %s', run['id'], e)


def maybe_push(run: dict, student_id: str | None = None) -> dict | None:
    """Push a finished survival run to CE if it qualifies. None for runs that
    can never count (non-survival, guest, unfinished). Never raises."""
    if run.get('mode') != 'survival' or not run.get('user_id') or not run.get('ended_at'):
        return None
    try:
        return _maybe_push(run, student_id)
    except Exception:
        logger.exception('puzzle rush school: push of run %s failed', run.get('id'))
        return {'status': 'error', 'student_id': student_id}


def _maybe_push(run: dict, student_id: str | None) -> dict:
    if not get_client().write_enabled():
        return {'status': 'disabled'}
    if run.get('school_push_status') == 'pushed':  # retried finish / claim
        return stored(run)

    if student_id is None:
        links = linked_student_ids(run['user_id'])
        if not links:
            result = {'status': 'unlinked'}
        elif (run.get('score') or 0) <= 0:
            result = {'status': 'not_best', 'student_id': links[0] if len(links) == 1 else None}
        elif len(links) > 1:
            result = {
                'status': 'needs_student',
                'candidates': linked_students(run['user_id']),
                'last_student_id': get_pick(run['user_id']),
            }
        else:
            student_id = links[0]
        if student_id is None:
            _save(run, result)
            return result

    if not push_enabled():
        return {'status': 'disabled', 'student_id': student_id}
    result = _push(run, student_id)
    _save(run, result)
    return result


def _push(run: dict, student_id: str) -> dict:
    score = run.get('score') or 0
    if score <= 0:
        return {'status': 'not_best', 'student_id': student_id}
    client = get_client()
    try:
        best = client.survival_best(student_id)
        beaten = [p for p in PERIODS if best.get(p) is None or score > best[p]]
        if not beaten:
            return {'status': 'not_best', 'student_id': student_id, 'best': best}
        res = client.push_survival_score(student_id, score, run['id'], run.get('ended_at'))
    except ChessEmpireAPIError as e:
        logger.warning('puzzle rush school: CE push of run %s for %s failed: %s', run['id'], student_id, e)
        return {'status': 'error', 'student_id': student_id}
    return {'status': 'pushed', 'student_id': student_id, 'beaten': beaten, 'best': res.get('best')}


def claim(run: dict, user_id: str, student_id) -> dict:
    """Family pick: push `run` for one of the user's linked students. Idempotent."""
    if run.get('user_id') != user_id:
        raise SchoolError('forbidden', 403)
    if run.get('mode') != 'survival':
        raise SchoolError('not_survival')
    if not run.get('ended_at'):
        raise SchoolError('run_not_ended', 409)
    if not isinstance(student_id, str) or student_id not in linked_student_ids(user_id):
        raise SchoolError('student_not_linked', 403)
    save_pick(user_id, student_id)
    return maybe_push(run, student_id)


# ─── Boards ──────────────────────────────────────────────────────────────────

def _display(row: dict) -> str:
    """First name + last initial: school boards are seen by other families."""
    first = (row.get('first_name') or '').strip()
    last = (row.get('last_name') or '').strip()
    return f'{first} {last[0]}.' if first and last else first or last


def leaderboard(scope: str, period: str, user_id: str | None, student_id: str | None) -> dict:
    """CE school / branch survival board for one of the caller's students."""
    period = PERIOD_ALIASES.get(period, period)
    if scope not in SCOPES:
        raise SchoolError('invalid_scope')
    if period not in PERIODS:
        raise SchoolError('invalid_period')
    if not user_id:
        raise SchoolError('auth_required', 401)
    if not get_client().write_enabled():
        raise SchoolError('school_unavailable', 503)

    links = linked_student_ids(user_id)
    if not links:
        raise SchoolError('not_linked', 403)
    if student_id:
        if student_id not in links:
            raise SchoolError('student_not_linked', 403)
    elif len(links) == 1:
        student_id = links[0]
    else:
        pick = get_pick(user_id)
        if pick not in links:
            raise SchoolError('student_required', 400, {'candidates': linked_students(user_id)})
        student_id = pick

    branch_id = None
    if scope == 'branch':
        branch_id = (student_info([student_id]).get(student_id) or {}).get('branch_id')
        if not branch_id:
            raise SchoolError('branch_unavailable', 503)

    key = (scope, period, branch_id, student_id)
    hit = _board_cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        res = get_client().survival_leaderboard(scope, period, branch_id, student_id, BOARD_SIZE)
    except ChessEmpireAPIError as e:
        logger.warning('puzzle rush school: CE leaderboard %s failed: %s', key, e)
        raise SchoolError('school_unavailable', 502)

    entries = [{
        'rank': r.get('rank'),
        'name': _display(r),
        'branch_name': r.get('branch_name'),
        'score': r.get('best_score'),
        'achieved_at': r.get('achieved_at'),
        'is_self': bool(r.get('is_self')) or r.get('student_id') == student_id,
        'source': r.get('source'),
    } for r in res.get('rows') or []]
    me = next(({'score': e['score'], 'rank': e['rank']} for e in entries if e['is_self']), None)
    out = {
        'mode': 'survival', 'period': period, 'scope': scope,
        'student_id': student_id, 'branch_id': branch_id,
        'window_start': res.get('window_start'), 'total_count': res.get('total_count'),
        'entries': entries, 'me': me,
    }
    _board_cache[key] = (time.monotonic() + CACHE_TTL, out)
    return out
