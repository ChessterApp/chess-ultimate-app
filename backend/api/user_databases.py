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
import secrets
import traceback
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from services.supabase_client import supabase
from utils.auth import verify_clerk_token, get_current_user_id
from api.user_games import _public_game, _owner_display_name

logger = logging.getLogger(__name__)

user_databases_bp = Blueprint('user_databases', __name__)

DATABASES_TABLE = 'user_databases'
GAMES_TABLE = 'user_games'
SHARED_DATABASES_TABLE = 'user_shared_databases'

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
