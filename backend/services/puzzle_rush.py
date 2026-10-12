"""
Puzzle Rush engine — puzzle packs, finished-run recording, personal bests and
leaderboards (spec §1, §5, §7; instant-moves plan v2).

v2 flow (the client owns the run): `pack()` hands out a deterministic puzzle
sequence for a client seed (full solution lines — §7.9 server validation was
dropped, cheating is a non-issue), the client plays the whole run locally, and
`finish_run()` records it in one Postgres RPC round trip. Scores and streaks are
recomputed from the attempts so every stored row is self-consistent.

Legacy v1 flow (kept one release for open tabs, the client no longer calls it):
`create_run` / `submit_move` / `quit_run` with a server-owned clock and
server-validated moves. Every v1 run write is a compare-and-set on `move_seq`.
`started_at` is creation time + COUNTDOWN_SECONDS; `deadline_at = started_at +
mode seconds`; expiry (timeout / 10-minute idle → abandoned) is checked lazily.

State lives in Supabase (puzzle_rush_runs / _attempts / _bests) so any worker
can serve any request.
"""

import hashlib
import logging
import random
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import chess

from services.puzzle_rush_source import NoPuzzleAvailable, get_puzzle_source
from services.supabase_client import supabase

logger = logging.getLogger(__name__)

RUNS_TABLE = 'puzzle_rush_runs'
ATTEMPTS_TABLE = 'puzzle_rush_attempts'
BESTS_TABLE = 'puzzle_rush_bests'

MODE_SECONDS = {'3min': 180, '5min': 300, 'survival': None}
MAX_STRIKES = 3
COUNTDOWN_SECONDS = 3
IDLE_LIMIT = timedelta(minutes=10)
DEFAULT_TZ = 'Asia/Almaty'
PERIODS = ('daily', 'weekly', 'all')
LEADERBOARD_SIZE = 50
PERSONAL_TOP = 10
# Rows scanned to build a daily/weekly board (deduped to best-per-user).
PERIOD_SCAN_LIMIT = 1000

# Packs (plan v2 §Backend 1): default size, per-request cap, and the longest
# run a pack (and a finished run) may cover.
PACK_DEFAULT = 40
PACK_MAX = 100
MAX_ATTEMPTS = 500
FINISH_RPC = 'puzzle_rush_finish_run'
FINISH_END_REASONS = ('strikes', 'timeout', 'quit')
ATTEMPT_RESULTS = ('solved', 'failed', 'unfinished')

_SEED_RE = re.compile(r'^[0-9a-f]{8,64}$')
_UCI_RE = re.compile(r'^[a-h][1-8][a-h][1-8][qrbn]?$')
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class RushError(Exception):
    def __init__(self, code: str, status: int = 400, payload: dict | None = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.payload = payload or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    if isinstance(ts, datetime):
        dt = ts
    else:
        dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _ms(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() * 1000))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        raise RushError('invalid_tz')


def period_start(period: str, tz: ZoneInfo, now: datetime | None = None) -> datetime | None:
    """UTC start of the user's local day / ISO week (Monday), or None for 'all'."""
    if period == 'all':
        return None
    local = (now or _now()).astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'weekly':
        start -= timedelta(days=start.weekday())
    return start.astimezone(timezone.utc)


# ─── Puzzle helpers ──────────────────────────────────────────────────────────

def _rng(run: dict, index: int) -> random.Random:
    return random.Random(f"{run['seed']}:{index}")


def _int_arg(value, default: int, lo: int, hi: int, code: str) -> int:
    if value is None or value == '':
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise RushError(code)
    if not lo <= n <= hi:
        raise RushError(code)
    return n


def pack(seed, start=None, count=None) -> dict:
    """Puzzles [start, start+count) of the deterministic sequence for `seed`.

    Puzzle i is `pick(i)` with the per-index RNG and every earlier puzzle of the
    seed excluded, exactly like a v1 run, so any (seed, start, count) slice is
    the same no matter how the client splits its top-ups. The prefix is replayed
    on every call (a handful of index seeks per puzzle, well under 1 ms each).
    """
    if not isinstance(seed, str) or not _SEED_RE.match(seed):
        raise RushError('invalid_seed')
    start = _int_arg(start, 0, 0, MAX_ATTEMPTS, 'invalid_from')
    count = _int_arg(count, PACK_DEFAULT, 1, PACK_MAX, 'invalid_count')
    end = min(start + count, MAX_ATTEMPTS)

    source = get_puzzle_source()
    run = {'seed': seed}
    served, out = [], []
    try:
        for i in range(end):
            puzzle = source.pick(i, served, _rng(run, i))
            served.append(puzzle['id'])
            if i >= start:
                out.append(pack_puzzle(puzzle, i))
    except NoPuzzleAvailable as e:
        logger.error('puzzle rush pack exhausted for seed %s at %d: %s', seed, len(served), e)
        raise RushError('no_puzzles', 503)
    return {'seed': seed, 'from': start, 'count': len(out), 'puzzles': out}


def pack_puzzle(puzzle: dict, index: int) -> dict:
    """Client view of a pack puzzle: the full line, moves[0] is the opponent setup."""
    board = chess.Board(puzzle['fen'])
    return {
        'index': index,
        'id': puzzle['id'],
        'fen': puzzle['fen'],
        'moves': puzzle['moves'],
        'rating': puzzle['rating'],
        'themes': puzzle.get('themes') or [],
        'color': 'black' if board.turn == chess.WHITE else 'white',
    }


def public_puzzle(puzzle: dict, index: int) -> dict:
    """Client view of a puzzle: position + setup move only, never the solution."""
    board = chess.Board(puzzle['fen'])
    return {
        'id': puzzle['id'],
        'index': index,
        'fen': puzzle['fen'],
        'setup_move': puzzle['moves'][0],
        'rating': puzzle['rating'],
        # The user plays the side NOT to move in `fen` (the setup move is the opponent's).
        'color': 'black' if board.turn == chess.WHITE else 'white',
    }


def _played_line(puzzle: dict, user_moves: list) -> list:
    """Setup move + each correct user move and the opponent reply it revealed."""
    moves = puzzle['moves']
    return moves[:1 + 2 * len(user_moves)] if user_moves else moves[:1]


# ─── Persistence ─────────────────────────────────────────────────────────────

def load_run(run_id: str) -> dict | None:
    if not isinstance(run_id, str) or not _UUID_RE.match(run_id.lower()):
        return None
    rows = supabase.table(RUNS_TABLE).select('*').eq('id', run_id).limit(1).execute().data
    return rows[0] if rows else None


def _load_attempts(run_id: str) -> list:
    return supabase.table(ATTEMPTS_TABLE).select('*').eq('run_id', run_id).order('idx').execute().data or []


def _commit(run: dict, changes: dict) -> dict:
    """Compare-and-set on move_seq; raises 409 if another request won the race."""
    seq = run.get('move_seq') or 0
    rows = supabase.table(RUNS_TABLE) \
        .update({**changes, 'move_seq': seq + 1}) \
        .eq('id', run['id']) \
        .eq('move_seq', seq) \
        .execute().data
    if not rows:
        raise RushError('conflict', 409)
    return rows[0]


def _insert_attempt(run_id: str, index: int, puzzle: dict, served_at: datetime):
    supabase.table(ATTEMPTS_TABLE).insert({
        'run_id': run_id,
        'idx': index,
        'puzzle_id': puzzle['id'],
        'puzzle_rating': puzzle['rating'],
        'result': 'unfinished',
        'user_moves': '',
        'served_at': _iso(served_at),
    }).execute()


_display_names: dict = {}


def _display_name(user_id: str) -> str | None:
    """Best-effort Clerk name, cached per process, stored on runs/bests so the
    leaderboard never has to call Clerk."""
    if user_id not in _display_names:
        try:
            from api.user_games import _owner_display_name
            _display_names[user_id] = _owner_display_name(user_id)
        except Exception as e:  # never block a run on Clerk
            logger.warning('puzzle rush display name lookup failed: %s', e)
            return None
    return _display_names[user_id]


# ─── Lifecycle ───────────────────────────────────────────────────────────────

def create_run(mode: str, user_id: str | None, now: datetime | None = None) -> tuple:
    """Start a run. Returns (run, guest_token or None, first public puzzle)."""
    if mode not in MODE_SECONDS:
        raise RushError('invalid_mode')
    now = now or _now()
    if user_id:
        _expire_stale_runs(user_id, now)

    started = now + timedelta(seconds=COUNTDOWN_SECONDS)
    seconds = MODE_SECONDS[mode]
    guest_token = None if user_id else secrets.token_urlsafe(24)
    run = {
        'id': str(uuid.uuid4()),
        'user_id': user_id,
        'display_name': _display_name(user_id) if user_id else None,
        'guest_token_hash': hash_token(guest_token) if guest_token else None,
        'mode': mode,
        'seed': secrets.token_hex(8),
        'started_at': _iso(started),
        'deadline_at': _iso(started + timedelta(seconds=seconds)) if seconds else None,
        'last_activity_at': _iso(now),
        'score': 0,
        'strikes': 0,
        'current_streak': 0,
        'longest_streak': 0,
        'puzzle_count': 1,
        'move_seq': 0,
        'is_new_pb': False,
    }
    puzzle = get_puzzle_source().pick(0, rng=_rng(run, 0))
    run = supabase.table(RUNS_TABLE).insert(run).execute().data[0]
    # The first puzzle is "served" when the countdown ends, not during it.
    _insert_attempt(run['id'], 0, puzzle, started)
    return run, guest_token, public_puzzle(puzzle, 0)


def _expire_stale_runs(user_id: str, now: datetime):
    """Lazily close the user's own runs that timed out / went idle, so their
    scores land on the boards when they start a new one."""
    rows = supabase.table(RUNS_TABLE).select('*') \
        .eq('user_id', user_id).is_('ended_at', 'null').execute().data or []
    for run in rows:
        try:
            expire_if_needed(run, now)
        except RushError:
            pass  # lost a race to another request: it's being handled there


def expire_if_needed(run: dict, now: datetime | None = None) -> dict:
    """End a run whose clock ran out (timeout) or that idled > 10 min (abandoned)."""
    if run.get('ended_at'):
        return run
    now = now or _now()
    deadline = _parse(run.get('deadline_at'))
    if deadline and now >= deadline:
        return _finish(run, 'timeout', deadline)
    last = _parse(run.get('last_activity_at'))
    if now - last > IDLE_LIMIT:
        return _finish(run, 'abandoned', last)
    return run


def _end_fields(run: dict, reason: str, ended_at: datetime, attempts: list) -> dict:
    done = [a['ms'] for a in attempts if a.get('result') in ('solved', 'failed') and a.get('ms') is not None]
    score = run.get('score') or 0
    is_new_pb = False
    if run.get('user_id') and score > 0:
        best = _get_best(run['user_id'], run['mode'])
        is_new_pb = best is None or score > (best.get('best_score') or 0)
    return {
        'ended_at': _iso(ended_at),
        'end_reason': reason,
        'duration_ms': _ms(_parse(run['started_at']), ended_at),
        'avg_ms_per_puzzle': round(sum(done) / len(done)) if done else None,
        'is_new_pb': is_new_pb,
    }


def _finish(run: dict, reason: str, ended_at: datetime, changes: dict | None = None,
            attempts: list | None = None) -> dict:
    """Commit the end of a run (plus any pending state changes) and update bests."""
    merged = {**run, **(changes or {})}
    if attempts is None:
        attempts = _load_attempts(run['id'])
    end = _end_fields(merged, reason, ended_at, attempts)
    run = _commit(run, {**(changes or {}), **end})
    if run.get('is_new_pb'):
        supabase.table(BESTS_TABLE).upsert({
            'user_id': run['user_id'],
            'mode': run['mode'],
            'best_score': run['score'],
            'best_run_id': run['id'],
            'display_name': run.get('display_name'),
            'achieved_at': run['ended_at'],
        }, on_conflict='user_id,mode').execute()
    return run


def _over_error(run: dict, tz: ZoneInfo) -> RushError:
    return RushError('run_over', 409, {**run_state(run), 'results': results(run, tz)})


def submit_move(run: dict, uci: str, tz: ZoneInfo, now: datetime | None = None) -> dict:
    now = now or _now()
    run = expire_if_needed(run, now)
    if run.get('ended_at'):
        raise _over_error(run, tz)

    attempts = _load_attempts(run['id'])
    index = run['puzzle_count'] - 1
    attempt = next(a for a in attempts if a['idx'] == index)
    source = get_puzzle_source()
    puzzle = source.get(attempt['puzzle_id'])
    moves = puzzle['moves']
    made = (attempt.get('user_moves') or '').split()

    board = chess.Board(puzzle['fen'])
    for m in _played_line(puzzle, made):
        board.push_uci(m)
    ply = 1 + 2 * len(made)

    try:
        move = chess.Move.from_uci(uci or '')
    except ValueError:
        raise RushError('invalid_move')
    if move not in board.legal_moves:
        raise RushError('illegal_move')
    board.push(move)

    # §7.4: any mating move is correct even if it isn't the stored one.
    correct = uci == moves[ply] or board.is_checkmate()
    solved = correct and (ply >= len(moves) - 1 or board.is_checkmate())
    if not correct:
        result = 'wrong'
    elif solved:
        result = 'solved'
    else:
        result = 'correct'

    attempt_changes = {'user_moves': ' '.join(made + [uci])}
    changes = {'last_activity_at': _iso(now)}
    if result != 'correct':
        attempt_changes.update({
            'result': 'solved' if solved else 'failed',
            'answered_at': _iso(now),
            'ms': _ms(_parse(attempt['served_at']), now),
        })
    if solved:
        streak = (run.get('current_streak') or 0) + 1
        changes.update({
            'score': (run.get('score') or 0) + 1,
            'current_streak': streak,
            'longest_streak': max(run.get('longest_streak') or 0, streak),
            'highest_solved_rating': max(run.get('highest_solved_rating') or 0, puzzle['rating']),
        })
    elif result == 'wrong':
        changes.update({'strikes': (run.get('strikes') or 0) + 1, 'current_streak': 0})

    response = {'result': result}
    next_puzzle = None
    if result == 'correct':
        response['reply'] = moves[ply + 1]
        run = _commit(run, changes)
    elif changes.get('strikes', 0) >= MAX_STRIKES:
        attempts = [{**a, **attempt_changes} if a['idx'] == index else a for a in attempts]
        run = _finish(run, 'strikes', now, changes, attempts)
    else:
        next_index = index + 1
        next_puzzle = source.pick(next_index, [a['puzzle_id'] for a in attempts], _rng(run, next_index))
        changes['puzzle_count'] = next_index + 1
        run = _commit(run, changes)
        _insert_attempt(run['id'], next_index, next_puzzle, now)

    supabase.table(ATTEMPTS_TABLE).update(attempt_changes) \
        .eq('run_id', run['id']).eq('idx', index).execute()

    response.update(run_state(run))
    if next_puzzle:
        response['next_puzzle'] = public_puzzle(next_puzzle, index + 1)
    if run.get('ended_at'):
        response['results'] = results(run, tz)
    return response


def quit_run(run: dict, tz: ZoneInfo, now: datetime | None = None) -> dict:
    """End the run and keep its score (§1 end condition c). Idempotent."""
    now = now or _now()
    run = expire_if_needed(run, now)
    if not run.get('ended_at'):
        run = _finish(run, 'quit', now)
    return {**run_state(run), 'results': results(run, tz)}


def run_state(run: dict) -> dict:
    over = bool(run.get('ended_at'))
    state = {
        'run_id': run['id'],
        'mode': run['mode'],
        'score': run.get('score') or 0,
        'strikes': run.get('strikes') or 0,
        'streak': run.get('current_streak') or 0,
        'started_at': run.get('started_at'),
        'deadline': run.get('deadline_at'),
        'server_now': _iso(_now()),
        'run_over': over,
    }
    if over:
        state['end_reason'] = run.get('end_reason')
    return state


def get_summary(run: dict, tz: ZoneInfo, now: datetime | None = None) -> dict:
    """Run summary. Solution lines appear only once the run has ended (§7.9)."""
    run = expire_if_needed(run, now)
    over = bool(run.get('ended_at'))
    source = get_puzzle_source()
    out = []
    current = None
    for a in _load_attempts(run['id']):
        item = {
            'index': a['idx'],
            'puzzle_id': a['puzzle_id'],
            'rating': a['puzzle_rating'],
            'result': a['result'],
            'user_moves': (a.get('user_moves') or '').split(),
            'ms': a.get('ms'),
        }
        if over:
            puzzle = source.get(a['puzzle_id'])
            if puzzle:
                item.update({'fen': puzzle['fen'], 'solution': puzzle['moves']})
        elif a['result'] == 'unfinished':
            # Resume support: the position plus only what was already revealed.
            puzzle = source.get(a['puzzle_id'])
            current = {**public_puzzle(puzzle, a['idx']), 'played': _played_line(puzzle, item['user_moves'])}
        out.append(item)

    summary = {
        **run_state(run),
        'longest_streak': run.get('longest_streak') or 0,
        'highest_solved_rating': run.get('highest_solved_rating'),
        'avg_ms_per_puzzle': run.get('avg_ms_per_puzzle'),
        'duration_ms': run.get('duration_ms'),
        'ended_at': run.get('ended_at'),
        'attempts': out,
    }
    if over:
        summary['results'] = results(run, tz)
    else:
        summary['current_puzzle'] = current
    return summary


# ─── Finished runs (v2) ──────────────────────────────────────────────────────

def _finish_attempts(raw) -> list:
    if not isinstance(raw, list) or len(raw) > MAX_ATTEMPTS:
        raise RushError('invalid_attempts')
    out = []
    for i, a in enumerate(raw):
        if not isinstance(a, dict):
            raise RushError('invalid_attempts')
        moves = a.get('user_moves') or []
        if isinstance(moves, str):
            moves = moves.split()
        ms = a.get('ms')
        rating = a.get('rating')
        valid = (
            a.get('index') == i
            and isinstance(a.get('puzzle_id'), str) and 0 < len(a['puzzle_id']) <= 16
            and isinstance(rating, int) and not isinstance(rating, bool) and 0 <= rating <= 4000
            and a.get('result') in ATTEMPT_RESULTS
            and (a['result'] != 'unfinished' or i == len(raw) - 1)
            and isinstance(moves, list) and len(moves) <= 64
            and all(isinstance(m, str) and _UCI_RE.match(m) for m in moves)
            and (ms is None or (isinstance(ms, int) and not isinstance(ms, bool) and 0 <= ms <= 86_400_000))
        )
        if not valid:
            raise RushError('invalid_attempts', 400, {'index': i})
        out.append({'idx': i, 'puzzle_id': a['puzzle_id'], 'puzzle_rating': rating,
                    'result': a['result'], 'user_moves': ' '.join(moves), 'ms': ms})
    return out


def run_stats(attempts: list) -> dict:
    """Score / strikes / streaks / averages, recomputed from the attempt list."""
    score = strikes = streak = longest = 0
    highest = None
    timed = []
    for a in attempts:
        if a['result'] == 'solved':
            score += 1
            streak += 1
            longest = max(longest, streak)
            highest = max(highest or 0, a['puzzle_rating'])
        elif a['result'] == 'failed':
            strikes += 1
            streak = 0
        if a['result'] != 'unfinished' and a.get('ms') is not None:
            timed.append(a['ms'])
    return {
        'score': score,
        'strikes': strikes,
        'current_streak': streak,
        'longest_streak': longest,
        'highest_solved_rating': highest,
        'avg_ms_per_puzzle': round(sum(timed) / len(timed)) if timed else None,
        'puzzle_count': len(attempts),
    }


def finish_run(user_id: str, body: dict, tz: ZoneInfo, now: datetime | None = None) -> dict:
    """Record a run the client played locally (plan v2). Idempotent on run_id.

    Data hygiene only, not anti-cheat: the row must be self-consistent, so the
    score and streaks come from `attempts`, never from the client's totals.
    """
    now = now or _now()
    run_id = body.get('run_id')
    if not isinstance(run_id, str) or not _UUID_RE.match(run_id.lower()):
        raise RushError('invalid_run_id')
    mode = body.get('mode')
    if mode not in MODE_SECONDS:
        raise RushError('invalid_mode')
    seed = body.get('seed')
    if not isinstance(seed, str) or not _SEED_RE.match(seed):
        raise RushError('invalid_seed')
    if body.get('end_reason') not in FINISH_END_REASONS:
        raise RushError('invalid_end_reason')
    try:
        started, ended = _parse(body.get('started_at')), _parse(body.get('ended_at'))
    except (TypeError, ValueError):
        raise RushError('invalid_time')
    if not started or not ended or ended < started or ended > now + timedelta(minutes=5):
        raise RushError('invalid_time')

    attempts = _finish_attempts(body.get('attempts'))
    stats = run_stats(attempts)
    if stats['strikes'] > MAX_STRIKES:
        raise RushError('invalid_attempts')

    # served_at is reconstructed from the per-puzzle times: a puzzle's ms runs
    # from the previous answer (or Go!) to its own answer.
    served = started
    for a in attempts:
        a['served_at'] = _iso(served)
        if a['ms'] is not None and a['result'] != 'unfinished':
            served += timedelta(milliseconds=a['ms'])
            a['answered_at'] = _iso(served)
        else:
            a['answered_at'] = None

    seconds = MODE_SECONDS[mode]
    run = {
        'id': run_id,
        'user_id': user_id,
        'display_name': _display_name(user_id),
        'mode': mode,
        'seed': seed,
        'started_at': _iso(started),
        'deadline_at': _iso(started + timedelta(seconds=seconds)) if seconds else None,
        'ended_at': _iso(ended),
        'end_reason': body['end_reason'],
        'duration_ms': _ms(started, ended),
        **stats,
    }
    periods = {p: _iso(period_start(p, tz, now)) for p in PERIODS if p != 'all'}
    try:
        res = supabase.rpc(FINISH_RPC, {'payload': {
            'run': run, 'attempts': attempts, 'periods': periods,
        }}).execute().data
    except Exception as e:
        logger.error('puzzle rush finish RPC %s failed for run %s: %s', FINISH_RPC, run_id, e)
        raise RushError('finish_unavailable', 503)
    if not isinstance(res, dict) or 'status' not in res:
        logger.error('puzzle rush finish RPC returned %r for run %s', res, run_id)
        raise RushError('finish_unavailable', 503)
    if res['status'] == 'conflict':
        raise RushError('conflict', 409)

    stored = res.get('run') or {}
    return {
        'run_id': run_id,
        'duplicate': res['status'] == 'duplicate',
        'score': stored.get('score', stats['score']),
        'is_new_pb': bool(stored.get('is_new_pb')),
        'longest_streak': stored.get('longest_streak', stats['longest_streak']),
        'highest_solved_rating': stored.get('highest_solved_rating', stats['highest_solved_rating']),
        'avg_ms_per_puzzle': stored.get('avg_ms_per_puzzle', stats['avg_ms_per_puzzle']),
        'duration_ms': stored.get('duration_ms', run['duration_ms']),
        'personal_rank': res.get('personal_rank'),
        'global_rank': res.get('global_rank'),
    }


# ─── Bests, ranks, leaderboards ──────────────────────────────────────────────

def _get_best(user_id: str, mode: str) -> dict | None:
    rows = supabase.table(BESTS_TABLE).select('*') \
        .eq('user_id', user_id).eq('mode', mode).limit(1).execute().data
    return rows[0] if rows else None


def _ended_runs(mode: str, since: datetime | None):
    q = supabase.table(RUNS_TABLE).select('id, user_id, display_name, score, ended_at') \
        .eq('mode', mode).not_.is_('ended_at', 'null')
    if since:
        q = q.gte('ended_at', _iso(since))
    return q


def global_rank(mode: str, score: int, period: str, tz: ZoneInfo, now: datetime | None = None) -> int:
    """Competition rank of `score` among registered players' bests in the period."""
    since = period_start(period, tz, now)
    if since is None:
        res = supabase.table(BESTS_TABLE).select('user_id', count='exact') \
            .eq('mode', mode).gt('best_score', score).execute()
        return 1 + (res.count or 0)
    rows = _ended_runs(mode, since).gt('score', score).not_.is_('user_id', 'null').execute().data or []
    return 1 + len({r['user_id'] for r in rows})


def personal_rank(run: dict) -> int:
    res = supabase.table(RUNS_TABLE).select('id', count='exact') \
        .eq('user_id', run['user_id']).eq('mode', run['mode']) \
        .not_.is_('ended_at', 'null').gt('score', run.get('score') or 0).execute()
    return 1 + (res.count or 0)


def results(run: dict, tz: ZoneInfo) -> dict:
    """End-of-run payload for the results modal (§2 S9, §7.5)."""
    out = {
        'score': run.get('score') or 0,
        'is_new_pb': bool(run.get('is_new_pb')),
        'longest_streak': run.get('longest_streak') or 0,
        'highest_solved_rating': run.get('highest_solved_rating'),
        'avg_ms_per_puzzle': run.get('avg_ms_per_puzzle'),
        'duration_ms': run.get('duration_ms'),
        'personal_rank': None,
        'global_rank': None,
    }
    if run.get('user_id'):  # guests never touch ranks (§7.6)
        out['personal_rank'] = personal_rank(run)
        out['global_rank'] = {p: global_rank(run['mode'], out['score'], p, tz) for p in PERIODS}
    return out


def get_bests(user_id: str, tz: ZoneInfo, now: datetime | None = None) -> dict:
    """Per-mode Top Score + Best Today (user's local day)."""
    bests = {b['mode']: b for b in
             supabase.table(BESTS_TABLE).select('*').eq('user_id', user_id).execute().data or []}
    today = supabase.table(RUNS_TABLE).select('mode, score') \
        .eq('user_id', user_id).not_.is_('ended_at', 'null') \
        .gte('ended_at', _iso(period_start('daily', tz, now))).execute().data or []
    out = {}
    for mode in MODE_SECONDS:
        best = bests.get(mode)
        today_scores = [r['score'] for r in today if r['mode'] == mode]
        out[mode] = {
            'top_score': best['best_score'] if best else None,
            'top_run_id': best['best_run_id'] if best else None,
            'achieved_at': best['achieved_at'] if best else None,
            'best_today': max(today_scores) if today_scores else None,
        }
    return out


def _ranked(entries: list) -> list:
    prev_score, rank = None, 0
    for i, e in enumerate(entries):
        if e['score'] != prev_score:
            rank, prev_score = i + 1, e['score']
        e['rank'] = rank
    return entries


def leaderboard(mode: str, period: str, scope: str, user_id: str | None, tz: ZoneInfo,
                now: datetime | None = None) -> dict:
    if mode not in MODE_SECONDS:
        raise RushError('invalid_mode')
    if period not in PERIODS:
        raise RushError('invalid_period')
    if scope not in ('global', 'personal'):
        raise RushError('invalid_scope')
    since = period_start(period, tz, now)

    if scope == 'personal':
        if not user_id:
            raise RushError('auth_required', 401)
        q = _ended_runs(mode, since).eq('user_id', user_id)
        rows = q.order('score', desc=True).order('ended_at').limit(PERSONAL_TOP).execute().data or []
        entries = [{'run_id': r['id'], 'score': r['score'], 'ended_at': r['ended_at']} for r in rows]
        return {'mode': mode, 'period': period, 'scope': scope, 'entries': _ranked(entries)}

    if since is None:
        rows = supabase.table(BESTS_TABLE).select('*').eq('mode', mode) \
            .order('best_score', desc=True).order('achieved_at') \
            .limit(LEADERBOARD_SIZE).execute().data or []
        entries = [{'user_id': r['user_id'], 'display_name': r.get('display_name'),
                    'score': r['best_score'], 'run_id': r['best_run_id'], 'ended_at': r['achieved_at']}
                   for r in rows]
    else:
        rows = _ended_runs(mode, since).not_.is_('user_id', 'null') \
            .order('score', desc=True).order('ended_at') \
            .limit(PERIOD_SCAN_LIMIT).execute().data or []
        seen, entries = set(), []
        for r in rows:  # best run per user; ties go to the earlier run
            if r['user_id'] in seen:
                continue
            seen.add(r['user_id'])
            entries.append({'user_id': r['user_id'], 'display_name': r.get('display_name'),
                            'score': r['score'], 'run_id': r['id'], 'ended_at': r['ended_at']})
            if len(entries) == LEADERBOARD_SIZE:
                break

    me = None
    if user_id:
        my_score = _my_best_in_period(user_id, mode, since)
        if my_score is not None:
            me = {'score': my_score, 'rank': global_rank(mode, my_score, period, tz, now)}
    return {'mode': mode, 'period': period, 'scope': scope, 'entries': _ranked(entries), 'me': me}


def _my_best_in_period(user_id: str, mode: str, since: datetime | None) -> int | None:
    if since is None:
        best = _get_best(user_id, mode)
        return best['best_score'] if best else None
    rows = _ended_runs(mode, since).eq('user_id', user_id) \
        .order('score', desc=True).limit(1).execute().data
    return rows[0]['score'] if rows else None
