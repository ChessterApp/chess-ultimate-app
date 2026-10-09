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
import traceback
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from services.supabase_client import supabase
from utils.auth import verify_clerk_token, get_current_user_id

logger = logging.getLogger(__name__)

user_databases_bp = Blueprint('user_databases', __name__)

DATABASES_TABLE = 'user_databases'
GAMES_TABLE = 'user_games'

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
