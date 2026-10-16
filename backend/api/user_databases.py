"""
User Databases API — CRUD for the "game databases" (collections) feature.

A user owns multiple named databases. Each saved game (user_games) belongs to at
most one via user_games.database_id. Databases are soft-deleted (deleted_at) for
30-day recovery; games ride along and are restored together. The built-in
"Master Database" pill (TWIC) is a frontend concept and is NEVER stored here.

Mirrors the structure/style of api/user_games.py (supabase client, auth,
error handling, logging).
"""

import logging
import re
import secrets
import traceback
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from services.supabase_client import supabase
from services import analytics_posthog as analytics
from utils.auth import verify_clerk_token, get_current_user_id
from api.user_games import _public_game, _owner_display_name, ALLOWED_FIELDS

logger = logging.getLogger(__name__)

user_databases_bp = Blueprint('user_databases', __name__)

DATABASES_TABLE = 'user_databases'
GAMES_TABLE = 'user_games'
SHARED_DATABASES_TABLE = 'user_shared_databases'
VOICE_NOTES_TABLE = 'move_voice_notes'
VOICE_NOTES_BUCKET = 'move-voice-notes'

MAX_NAME_LEN = 80

# Soft-deleted databases are recoverable for this many days, then hard-deleted by
# the cleanup command (commands/cleanup_deleted_databases.py).
RETENTION_DAYS = 30


def _parse_ts(value):
    """Parse an ISO timestamp (tolerating a trailing 'Z') into an aware datetime,
    or None if it can't be parsed."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _validate_name(data):
    """Return (name, error_response_tuple). name is the trimmed value on success."""
    if not data or not isinstance(data.get('name'), str):
        return None, (jsonify({'error': 'name is required'}), 400)
    name = data['name'].strip()
    if not name:
        return None, (jsonify({'error': 'name is required'}), 400)
    if len(name) > MAX_NAME_LEN:
        return None, (jsonify({'error': f'name must be {MAX_NAME_LEN} characters or fewer'}), 400)
    return name, None


def _live_name_taken(user_id, name, exclude_id=None):
    """True if a LIVE database with the same (case-insensitive) name already exists."""
    result = supabase.table(DATABASES_TABLE) \
        .select('id, name, deleted_at') \
        .eq('user_id', user_id) \
        .is_('deleted_at', 'null') \
        .ilike('name', name) \
        .execute()
    target = name.lower()
    for row in result.data or []:
        if row.get('deleted_at') is not None:
            continue
        if exclude_id is not None and row.get('id') == exclude_id:
            continue
        if (row.get('name') or '').strip().lower() == target:
            return True
    return False


def _game_count(database_id):
    """Count of live user_games stamped with this database_id."""
    result = supabase.table(GAMES_TABLE) \
        .select('id', count='exact') \
        .eq('database_id', database_id) \
        .is_('deleted_at', 'null') \
        .execute()
    return result.count or 0


def _fetch_owned(database_id, user_id, include_deleted=False):
    """Return the caller-owned database row by id, or None.

    include_deleted=False restricts to live rows (deleted_at IS NULL); True allows
    a soft-deleted row (used by restore). The id/user_id match is also re-checked
    in Python so the result is correct even under a filter-agnostic mock.
    """
    query = supabase.table(DATABASES_TABLE) \
        .select('*') \
        .eq('id', database_id) \
        .eq('user_id', user_id)
    if not include_deleted:
        query = query.is_('deleted_at', 'null')
    result = query.execute()
    for row in result.data or []:
        if row.get('id') != database_id or row.get('user_id') != user_id:
            continue
        is_deleted = row.get('deleted_at') is not None
        if is_deleted and not include_deleted:
            continue
        if not is_deleted and include_deleted:
            # restore target must actually be deleted
            continue
        return row
    return None


# ─── LIST ────────────────────────────────────────────────────────────────────

@user_databases_bp.route('/api/databases', methods=['GET'])
@verify_clerk_token
def list_databases():
    """List the caller's live databases, each with a live game_count.

    Ordered default-first, then created_at ascending. Returns [] if none.
    """
    user_id = get_current_user_id()
    try:
        result = supabase.table(DATABASES_TABLE) \
            .select('*') \
            .eq('user_id', user_id) \
            .is_('deleted_at', 'null') \
            .order('is_default', desc=True) \
            .order('created_at', desc=False) \
            .execute()

        databases = []
        for row in result.data or []:
            row = dict(row)
            row['game_count'] = _game_count(row['id'])
            databases.append(row)

        return jsonify(databases), 200

    except Exception as e:
        logger.error(f"Error listing databases: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── LIST DELETED (restore panel) ──────────────────────────────────────────────

@user_databases_bp.route('/api/databases/deleted', methods=['GET'])
@verify_clerk_token
def list_deleted_databases():
    """List the caller's soft-deleted databases still within the recovery window.

    Each row carries a live game_count and days_left (30 minus days since
    deletion, floored at 0). Rows already past RETENTION_DAYS are omitted — the
    cleanup command treats them as gone. Ordered most-recently-deleted first.
    """
    user_id = get_current_user_id()
    try:
        result = supabase.table(DATABASES_TABLE) \
            .select('*') \
            .eq('user_id', user_id) \
            .not_.is_('deleted_at', 'null') \
            .order('deleted_at', desc=True) \
            .execute()

        now = datetime.now(timezone.utc)
        deleted = []
        for row in result.data or []:
            if row.get('user_id') != user_id:
                continue
            deleted_at = _parse_ts(row.get('deleted_at'))
            if deleted_at is None:
                continue
            days_since = (now - deleted_at).days
            if days_since >= RETENTION_DAYS:
                continue  # past the window — treated as gone
            deleted.append({
                'id': row['id'],
                'name': row.get('name'),
                'deleted_at': row.get('deleted_at'),
                'game_count': _game_count(row['id']),
                'days_left': max(0, RETENTION_DAYS - days_since),
            })

        return jsonify(deleted), 200

    except Exception as e:
        logger.error(f"Error listing deleted databases: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── CREATE ──────────────────────────────────────────────────────────────────

@user_databases_bp.route('/api/databases', methods=['POST'])
@verify_clerk_token
def create_database():
    """Create a new NON-default database. 400 on bad name, 409 on duplicate."""
    user_id = get_current_user_id()
    data = request.get_json(silent=True)

    name, err = _validate_name(data)
    if err:
        return err

    try:
        if _live_name_taken(user_id, name):
            return jsonify({'error': 'A database with that name already exists.'}), 409

        result = supabase.table(DATABASES_TABLE) \
            .insert({'user_id': user_id, 'name': name, 'is_default': False}) \
            .execute()

        row = dict(result.data[0])
        row['game_count'] = 0
        analytics.capture(user_id, analytics.DATABASE_CREATED)
        return jsonify(row), 201

    except Exception as e:
        logger.error(f"Error creating database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── RENAME ──────────────────────────────────────────────────────────────────

@user_databases_bp.route('/api/databases/<database_id>', methods=['PUT'])
@verify_clerk_token
def rename_database(database_id):
    """Rename an owned database (default included). 400 bad name, 404 missing,
    409 duplicate."""
    user_id = get_current_user_id()
    data = request.get_json(silent=True)

    name, err = _validate_name(data)
    if err:
        return err

    try:
        existing = _fetch_owned(database_id, user_id)
        if not existing:
            return jsonify({'error': 'Database not found'}), 404

        if _live_name_taken(user_id, name, exclude_id=database_id):
            return jsonify({'error': 'A database with that name already exists.'}), 409

        now = datetime.now(timezone.utc).isoformat()
        result = supabase.table(DATABASES_TABLE) \
            .update({'name': name, 'updated_at': now}) \
            .eq('id', database_id) \
            .eq('user_id', user_id) \
            .execute()

        return jsonify(result.data[0]), 200

    except Exception as e:
        logger.error(f"Error renaming database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── DELETE (soft) ───────────────────────────────────────────────────────────

@user_databases_bp.route('/api/databases/<database_id>', methods=['DELETE'])
@verify_clerk_token
def delete_database(database_id):
    """Soft-delete an owned database. 404 missing, 400 if it's the default."""
    user_id = get_current_user_id()
    try:
        existing = _fetch_owned(database_id, user_id)
        if not existing:
            return jsonify({'error': 'Database not found'}), 404

        if existing.get('is_default'):
            return jsonify({'error': "Can't delete your default database."}), 400

        now = datetime.now(timezone.utc).isoformat()
        supabase.table(DATABASES_TABLE) \
            .update({'deleted_at': now, 'updated_at': now}) \
            .eq('id', database_id) \
            .eq('user_id', user_id) \
            .execute()

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error deleting database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── RESTORE ─────────────────────────────────────────────────────────────────

@user_databases_bp.route('/api/databases/<database_id>/restore', methods=['POST'])
@verify_clerk_token
def restore_database(database_id):
    """Restore a soft-deleted database. 404 missing, 409 on name collision with a
    live database."""
    user_id = get_current_user_id()
    try:
        existing = _fetch_owned(database_id, user_id, include_deleted=True)
        if not existing:
            return jsonify({'error': 'Database not found'}), 404

        if _live_name_taken(user_id, existing.get('name') or '', exclude_id=database_id):
            return jsonify({'error': 'A live database with that name already exists.'}), 409

        now = datetime.now(timezone.utc).isoformat()
        result = supabase.table(DATABASES_TABLE) \
            .update({'deleted_at': None, 'updated_at': now}) \
            .eq('id', database_id) \
            .eq('user_id', user_id) \
            .execute()

        return jsonify(result.data[0]), 200

    except Exception as e:
        logger.error(f"Error restoring database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── SHARING ───────────────────────────────────────────────────────────────────
#
# A user database (except the default/Master) can be shared read-only via one
# opaque, revocable token. The token resolves to the database's meta and its
# games (scoped by database_id), sanitized with the same _public_game helper used
# by the whole-collection (gc=) share path. Revoking sets share_token back to
# NULL so the token stops resolving → 404 everywhere. Mirrors the per-game and
# per-collection share semantics.


def _db_games(database_id, sanitized=False):
    """Return live games under a database, newest first. Sanitized strips the
    private fields for a share recipient."""
    result = supabase.table(GAMES_TABLE) \
        .select('*') \
        .eq('database_id', database_id) \
        .is_('deleted_at', 'null') \
        .order('created_at', desc=True) \
        .execute()
    rows = [r for r in (result.data or []) if r.get('database_id') == database_id]
    return [_public_game(r) for r in rows] if sanitized else rows


def _fetch_db_by_share_token(token):
    """Return the LIVE database row for a share token, or None.

    The share_token/deleted_at match is re-checked in Python so an unknown or
    revoked token resolves to None even under a filter-agnostic mock.
    """
    if not token:
        return None
    result = supabase.table(DATABASES_TABLE) \
        .select('*') \
        .eq('share_token', token) \
        .is_('deleted_at', 'null') \
        .execute()
    for row in result.data or []:
        if row.get('share_token') == token and row.get('deleted_at') is None:
            return row
    return None


@user_databases_bp.route('/api/databases/<database_id>/share', methods=['POST'])
@verify_clerk_token
def share_database(database_id):
    """Mint (or return the existing) share token for an owned database.

    Idempotent — a database that already has a token gets it back unchanged.
    400 if it's the default/Master database (never shareable), 404 if missing.
    """
    user_id = get_current_user_id()
    try:
        existing = _fetch_owned(database_id, user_id)
        if not existing:
            return jsonify({'error': 'Database not found'}), 404

        if existing.get('is_default'):
            return jsonify({'error': "Your default database can't be shared."}), 400

        if existing.get('share_token'):
            return jsonify({'share_token': existing['share_token']}), 200

        token = secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc).isoformat()
        supabase.table(DATABASES_TABLE) \
            .update({'share_token': token, 'updated_at': now}) \
            .eq('id', database_id) \
            .eq('user_id', user_id) \
            .execute()

        analytics.capture(user_id, analytics.DATABASE_SHARED)
        return jsonify({'share_token': token}), 200

    except Exception as e:
        logger.error(f"Error sharing database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_databases_bp.route('/api/databases/<database_id>/share', methods=['DELETE'])
@verify_clerk_token
def revoke_database_share(database_id):
    """Revoke an owned database's share token (set it NULL). Owner-scoped.

    Idempotent: revoking when nothing is shared still succeeds. After this the
    token no longer resolves → the shared view 404s.
    """
    user_id = get_current_user_id()
    try:
        existing = _fetch_owned(database_id, user_id)
        if not existing:
            return jsonify({'error': 'Database not found'}), 404

        now = datetime.now(timezone.utc).isoformat()
        supabase.table(DATABASES_TABLE) \
            .update({'share_token': None, 'updated_at': now}) \
            .eq('id', database_id) \
            .eq('user_id', user_id) \
            .execute()

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error revoking database share: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_databases_bp.route('/api/databases/shared/<token>', methods=['GET'])
@verify_clerk_token
def get_shared_database(token):
    """Resolve a share token → the database meta + its games, READ-ONLY.

    Any signed-in user may read it. Games are scoped by database_id and
    sanitized (private `notes`/`user_id` stripped) with the same _public_game
    helper used by the collection-share path. Unknown/revoked token → 404.
    """
    try:
        db = _fetch_db_by_share_token(token)
        if not db:
            return jsonify({'error': 'Shared database not found'}), 404

        games = _db_games(db['id'], sanitized=True)
        return jsonify({
            'database': {
                'id': db['id'],
                'name': db.get('name'),
                'game_count': len(games),
            },
            'owner_name': _owner_display_name(db['user_id']),
            'games': games,
        }), 200

    except Exception as e:
        logger.error(f"Error reading shared database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── "SHARED WITH ME" SUBSCRIPTIONS ────────────────────────────────────────────
#
# Opening a share link records a subscription so the shared database persists as
# a read-only pill. The subscription is keyed by (subscriber_id, source_token);
# deleting one removes only the subscriber's own row and never touches the
# owner's data. A revoked/unknown token simply stops resolving.


def _shared_db_meta(token):
    """Resolve a share token to a compact meta dict for a subscriber view, or
    None if the token no longer resolves (revoked/unknown)."""
    db = _fetch_db_by_share_token(token)
    if not db:
        return None
    return {
        'source_token': token,
        'database_id': db['id'],
        'name': db.get('name'),
        'owner_name': _owner_display_name(db['user_id']),
        'game_count': _game_count(db['id']),
    }


@user_databases_bp.route('/api/databases/shared/<token>/subscribe', methods=['POST'])
@verify_clerk_token
def subscribe_shared_database(token):
    """Record (idempotently) the caller's subscription to a shared database.

    404 if the token doesn't resolve. Returns the shared-db meta so the caller
    can render the pill immediately.
    """
    user_id = get_current_user_id()
    try:
        meta = _shared_db_meta(token)
        if not meta:
            return jsonify({'error': 'Shared database not found'}), 404

        existing = supabase.table(SHARED_DATABASES_TABLE) \
            .select('id') \
            .eq('subscriber_id', user_id) \
            .eq('source_token', token) \
            .execute()

        if not (existing.data or []):
            supabase.table(SHARED_DATABASES_TABLE) \
                .insert({'subscriber_id': user_id, 'source_token': token}) \
                .execute()

        return jsonify(meta), 200

    except Exception as e:
        logger.error(f"Error subscribing to shared database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_databases_bp.route('/api/databases/shared', methods=['GET'])
@verify_clerk_token
def list_shared_databases():
    """List the caller's shared-database subscriptions, resolved to live meta.

    Each row carries an `available` flag: a subscription whose token the owner
    has since revoked still appears (so the user can remove it) but with
    available=false and no game data.
    """
    user_id = get_current_user_id()
    try:
        result = supabase.table(SHARED_DATABASES_TABLE) \
            .select('*') \
            .eq('subscriber_id', user_id) \
            .order('added_at', desc=True) \
            .execute()

        items = []
        for row in result.data or []:
            if row.get('subscriber_id') != user_id:
                continue
            token = row.get('source_token')
            meta = _shared_db_meta(token)
            if meta:
                items.append({**meta, 'added_at': row.get('added_at'), 'available': True})
            else:
                items.append({
                    'source_token': token,
                    'database_id': None,
                    'name': None,
                    'owner_name': None,
                    'game_count': 0,
                    'added_at': row.get('added_at'),
                    'available': False,
                })

        return jsonify(items), 200

    except Exception as e:
        logger.error(f"Error listing shared databases: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_databases_bp.route('/api/databases/shared/subscription/<token>', methods=['DELETE'])
@verify_clerk_token
def unsubscribe_shared_database(token):
    """Remove ONLY the caller's subscription row for a token. Owner data is never
    touched. Idempotent: removing a missing subscription still succeeds."""
    user_id = get_current_user_id()
    try:
        supabase.table(SHARED_DATABASES_TABLE) \
            .delete() \
            .eq('subscriber_id', user_id) \
            .eq('source_token', token) \
            .execute()
        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error unsubscribing from shared database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── COPY TO MY WORKSPACE (deep copy) ───────────────────────────────────────────
#
# Resolve a share token, create a new database owned by the requester, and
# deep-copy every source game under it with fresh ids. The copy is a NORMAL owned
# database afterwards — edit/share/delete all flow through the existing endpoints.

# Game content to carry over on a deep copy. The owner's private `notes` are
# intentionally dropped (they're stripped from the shared view too).
_COPY_FIELDS = ALLOWED_FIELDS - {'notes'}

# Batch size for inserting copied games (large collections).
_COPY_BATCH = 500


def _free_copy_name(user_id, source_name):
    """Pick an un-taken '<name> (copy)' / '(copy 2)'… name, trimmed to fit."""
    source_name = (source_name or 'Database').strip()

    def _fit(suffix):
        room = MAX_NAME_LEN - len(suffix)
        base = source_name[:room].rstrip() if room < len(source_name) else source_name
        return f"{base}{suffix}"

    candidate = _fit(' (copy)')
    if not _live_name_taken(user_id, candidate):
        return candidate
    n = 2
    while n <= 1000:
        candidate = _fit(f' (copy {n})')
        if not _live_name_taken(user_id, candidate):
            return candidate
        n += 1
    return _fit(f' (copy {secrets.token_hex(3)})')


@user_databases_bp.route('/api/databases/shared/<token>/copy', methods=['POST'])
@verify_clerk_token
def copy_shared_database(token):
    """Deep-copy a shared database into the caller's workspace.

    Creates a new owned database named '<name> (copy)' (deduped) and copies every
    source game with a fresh id, the caller's user_id, the new database_id, and no
    share_token. 404 on unknown/revoked token. Returns the new db meta.
    """
    user_id = get_current_user_id()
    try:
        source = _fetch_db_by_share_token(token)
        if not source:
            return jsonify({'error': 'Shared database not found'}), 404

        name = _free_copy_name(user_id, source.get('name'))
        created = supabase.table(DATABASES_TABLE) \
            .insert({'user_id': user_id, 'name': name, 'is_default': False}) \
            .execute()
        new_db = dict(created.data[0])
        new_db_id = new_db['id']

        try:
            source_games = _db_games(source['id'], sanitized=False)
            copies = []
            # Fresh ids are minted here (not by the DB) so each source game's
            # voice notes can be re-attached to its copy.
            game_id_map = {}
            for g in source_games:
                new_game_id = str(uuid.uuid4())
                game_id_map[g['id']] = new_game_id
                row = {'id': new_game_id, 'user_id': user_id, 'database_id': new_db_id, 'share_token': None}
                for field in _COPY_FIELDS:
                    if field in g:
                        row[field] = g[field]
                copies.append(row)

            for i in range(0, len(copies), _COPY_BATCH):
                batch = copies[i:i + _COPY_BATCH]
                if batch:
                    supabase.table(GAMES_TABLE).insert(batch).execute()

            _copy_voice_notes(game_id_map, user_id)
        except Exception:
            # No cross-statement transaction available — roll back the empty db so
            # a failed copy doesn't leave an orphan.
            supabase.table(DATABASES_TABLE).delete().eq('id', new_db_id).eq('user_id', user_id).execute()
            raise

        new_db['game_count'] = len(source_games)
        return jsonify(new_db), 201

    except Exception as e:
        logger.error(f"Error copying shared database: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── MOVE VOICE NOTES ──────────────────────────────────────────────────────────
#
# A short audio clip attached to ONE move of a saved game. The PGN is untouched:
# a note maps to its move by node_path, the move's SAN path from the start
# position joined by single spaces ('e4 e5 Nf3'). Audio sits in a private bucket
# under {owner_user_id}/{game_id}/{uuid}.{ext} and is only served through
# short-lived signed URLs. The owner may upload/delete; a viewer holding a valid
# share token for the game's database may list and play, never write.

VOICE_NOTE_MAX_BYTES = 5 * 1024 * 1024
VOICE_NOTE_MAX_MS = 120_000
# MediaRecorder keeps flushing for a moment after the 2-minute auto-stop.
VOICE_NOTE_DURATION_GRACE_MS = 2_000
VOICE_NOTE_URL_TTL_SECONDS = 300
MAX_NODE_PATH_LEN = 4000

_AUDIO_EXT = {
    'audio/webm': 'webm',
    'audio/ogg': 'ogg',
    'audio/mp4': 'm4a',
    'audio/x-m4a': 'm4a',
    'audio/aac': 'aac',
    'audio/mpeg': 'mp3',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
}


def _audio_ext(mime):
    ext = _AUDIO_EXT.get(mime)
    if ext:
        return ext
    return re.sub(r'[^a-z0-9]', '', mime.split('/', 1)[1])[:8] or 'audio'


def _public_note(row):
    """A note as returned to clients: no storage key, no owner id."""
    return {
        'id': row['id'],
        'game_id': row.get('game_id'),
        'node_path': row.get('node_path'),
        'mime_type': row.get('mime_type'),
        'duration_ms': row.get('duration_ms'),
        'created_at': row.get('created_at'),
    }


def _live_game(game_id, **match):
    """Return the live user_games row with this id whose columns equal `match`,
    re-checked in Python (filter-agnostic mocks), or None."""
    query = supabase.table(GAMES_TABLE) \
        .select('id, user_id, database_id, deleted_at') \
        .eq('id', game_id)
    for column, value in match.items():
        query = query.eq(column, value)
    result = query.is_('deleted_at', 'null').execute()
    for row in result.data or []:
        if row.get('id') != game_id or row.get('deleted_at') is not None:
            continue
        if all(row.get(column) == value for column, value in match.items()):
            return row
    return None


def _readable_game(game_id, user_id):
    """The game if the caller owns it, or holds a live share token (?share_token=)
    for the database it belongs to; else None."""
    game = _live_game(game_id, user_id=user_id)
    if game:
        return game
    token = request.args.get('share_token')
    db = _fetch_db_by_share_token(token) if token else None
    if db:
        return _live_game(game_id, database_id=db['id'])
    return None


def _game_notes(game_id):
    result = supabase.table(VOICE_NOTES_TABLE) \
        .select('*') \
        .eq('game_id', game_id) \
        .order('created_at', desc=False) \
        .execute()
    return [r for r in (result.data or []) if r.get('game_id') == game_id]


def _path_covers(prefix, node_path):
    """True if node_path is the move at `prefix` or any move after it in its line."""
    return node_path == prefix or (node_path or '').startswith(prefix + ' ')


def _remove_voice_notes(rows, client=None):
    """Delete note rows and their audio objects. Storage removal is best-effort:
    an orphaned object is invisible, a dangling row would show a dead 🔊."""
    client = client or supabase
    rows = [r for r in rows if r.get('id')]
    if not rows:
        return 0
    paths = [r['storage_path'] for r in rows if r.get('storage_path')]
    if paths:
        try:
            client.storage.from_(VOICE_NOTES_BUCKET).remove(paths)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Voice note storage removal failed for {len(paths)} objects: {e}")
    client.table(VOICE_NOTES_TABLE) \
        .delete() \
        .in_('id', [r['id'] for r in rows]) \
        .execute()
    return len(rows)


def purge_game_voice_notes(game_ids, client=None):
    """Remove every voice note (rows + audio) of the given games. Used when a game
    is deleted and when soft-deleted databases are hard-deleted; callers in other
    modules pass their own client."""
    client = client or supabase
    game_ids = [g for g in game_ids if g]
    if not game_ids:
        return 0
    result = client.table(VOICE_NOTES_TABLE) \
        .select('*') \
        .in_('game_id', game_ids) \
        .execute()
    wanted = set(game_ids)
    return _remove_voice_notes([r for r in (result.data or []) if r.get('game_id') in wanted], client)


def _copy_voice_notes(game_id_map, owner_user_id):
    """Duplicate the voice notes of copied games — rows AND audio objects, under
    the new owner's prefix — so the copy keeps working if the source goes away.
    A note whose object can't be copied is skipped (logged), not fatal."""
    if not game_id_map:
        return 0
    result = supabase.table(VOICE_NOTES_TABLE) \
        .select('*') \
        .in_('game_id', list(game_id_map)) \
        .execute()
    bucket = supabase.storage.from_(VOICE_NOTES_BUCKET)
    copies = []
    for note in result.data or []:
        new_game_id = game_id_map.get(note.get('game_id'))
        if not new_game_id or not note.get('storage_path'):
            continue
        ext = note['storage_path'].rsplit('.', 1)[-1]
        new_path = f"{owner_user_id}/{new_game_id}/{uuid.uuid4().hex}.{ext}"
        try:
            bucket.copy(note['storage_path'], new_path)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Voice note copy failed for {note.get('id')}: {e}")
            continue
        copies.append({
            'game_id': new_game_id,
            'owner_user_id': owner_user_id,
            'node_path': note.get('node_path'),
            'storage_path': new_path,
            'mime_type': note.get('mime_type'),
            'duration_ms': note.get('duration_ms'),
        })
    for i in range(0, len(copies), _COPY_BATCH):
        supabase.table(VOICE_NOTES_TABLE).insert(copies[i:i + _COPY_BATCH]).execute()
    return len(copies)


@user_databases_bp.route('/api/games/<game_id>/voice-notes', methods=['GET'])
@verify_clerk_token
def list_voice_notes(game_id):
    """List a game's voice notes. Owner, or a viewer with ?share_token=."""
    user_id = get_current_user_id()
    try:
        if not _readable_game(game_id, user_id):
            return jsonify({'error': 'Game not found'}), 404
        return jsonify([_public_note(r) for r in _game_notes(game_id)]), 200

    except Exception as e:
        logger.error(f"Error listing voice notes: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_databases_bp.route('/api/games/<game_id>/voice-notes', methods=['POST'])
@verify_clerk_token
def upload_voice_note(game_id):
    """Attach a voice note to a move (owner only). Re-recording replaces it.

    multipart/form-data: file (audio/*, <= 5 MB), node_path, duration_ms (<= 2 min).
    """
    user_id = get_current_user_id()
    try:
        if not _live_game(game_id, user_id=user_id):
            return jsonify({'error': 'Game not found'}), 404

        node_path = (request.form.get('node_path') or '').strip()
        if not node_path or len(node_path) > MAX_NODE_PATH_LEN:
            return jsonify({'error': 'node_path is required'}), 400

        try:
            duration_ms = int(request.form.get('duration_ms') or 0)
        except ValueError:
            duration_ms = 0
        if duration_ms <= 0:
            return jsonify({'error': 'duration_ms is required'}), 400
        if duration_ms > VOICE_NOTE_MAX_MS + VOICE_NOTE_DURATION_GRACE_MS:
            return jsonify({'error': 'Voice notes are limited to 2 minutes'}), 400

        upload = request.files.get('file')
        if upload is None:
            return jsonify({'error': 'file is required'}), 400
        mime = (upload.mimetype or '').split(';', 1)[0].strip().lower()
        if not mime.startswith('audio/') or mime == 'audio/':
            return jsonify({'error': 'Only audio files are allowed'}), 415
        payload = upload.read(VOICE_NOTE_MAX_BYTES + 1)
        if len(payload) > VOICE_NOTE_MAX_BYTES:
            return jsonify({'error': 'Voice notes are limited to 5 MB'}), 413
        if not payload:
            return jsonify({'error': 'Empty file'}), 400

        storage_path = f"{user_id}/{game_id}/{uuid.uuid4().hex}.{_audio_ext(mime)}"
        bucket = supabase.storage.from_(VOICE_NOTES_BUCKET)
        try:
            bucket.upload(path=storage_path, file=payload, file_options={'content-type': mime})
        except Exception as e:  # noqa: BLE001 — surface storage errors as 502
            logger.error(f"Voice note upload failed: game={game_id}: {e}")
            return jsonify({'error': 'Upload failed'}), 502

        replaced = [r for r in _game_notes(game_id) if r.get('node_path') == node_path]
        try:
            result = supabase.table(VOICE_NOTES_TABLE).insert({
                'game_id': game_id,
                'owner_user_id': user_id,
                'node_path': node_path,
                'storage_path': storage_path,
                'mime_type': mime,
                'duration_ms': min(duration_ms, VOICE_NOTE_MAX_MS),
            }).execute()
        except Exception:
            bucket.remove([storage_path])
            raise
        _remove_voice_notes(replaced)

        return jsonify(_public_note(result.data[0])), 201

    except Exception as e:
        logger.error(f"Error uploading voice note: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_databases_bp.route('/api/games/<game_id>/voice-notes/<note_id>/url', methods=['GET'])
@verify_clerk_token
def voice_note_url(game_id, note_id):
    """Short-lived signed playback URL. Owner, or a viewer with ?share_token=."""
    user_id = get_current_user_id()
    try:
        if not _readable_game(game_id, user_id):
            return jsonify({'error': 'Game not found'}), 404
        note = next((r for r in _game_notes(game_id) if r.get('id') == note_id), None)
        if not note:
            return jsonify({'error': 'Voice note not found'}), 404

        signed = supabase.storage.from_(VOICE_NOTES_BUCKET) \
            .create_signed_url(note['storage_path'], VOICE_NOTE_URL_TTL_SECONDS)
        url = (signed or {}).get('signedURL') or (signed or {}).get('signedUrl')
        if not url:
            return jsonify({'error': 'Voice note unavailable'}), 502
        return jsonify({'url': url, 'expires_in': VOICE_NOTE_URL_TTL_SECONDS}), 200

    except Exception as e:
        logger.error(f"Error signing voice note URL: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_databases_bp.route('/api/games/<game_id>/voice-notes/<note_id>', methods=['DELETE'])
@verify_clerk_token
def delete_voice_note(game_id, note_id):
    """Delete one voice note and its audio (owner only)."""
    user_id = get_current_user_id()
    try:
        if not _live_game(game_id, user_id=user_id):
            return jsonify({'error': 'Game not found'}), 404
        note = next((r for r in _game_notes(game_id) if r.get('id') == note_id), None)
        if not note:
            return jsonify({'error': 'Voice note not found'}), 404
        _remove_voice_notes([note])
        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error deleting voice note: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_databases_bp.route('/api/games/<game_id>/voice-notes', methods=['DELETE'])
@verify_clerk_token
def delete_voice_notes_from_move(game_id):
    """Delete the notes on a deleted move and every move after it in its line
    (?node_path=). Owner only; idempotent."""
    user_id = get_current_user_id()
    try:
        if not _live_game(game_id, user_id=user_id):
            return jsonify({'error': 'Game not found'}), 404
        node_path = (request.args.get('node_path') or '').strip()
        if not node_path:
            return jsonify({'error': 'node_path is required'}), 400
        doomed = [r for r in _game_notes(game_id) if _path_covers(node_path, r.get('node_path'))]
        return jsonify({'deleted': _remove_voice_notes(doomed)}), 200

    except Exception as e:
        logger.error(f"Error deleting voice notes: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500
