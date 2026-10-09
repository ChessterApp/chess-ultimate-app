"""
User Games API — CRUD + Import endpoints for My Games feature
"""

import io
import logging
import secrets
import traceback
from datetime import datetime, timezone

import chess
import chess.pgn
from flask import Blueprint, request, jsonify, Response

from services.supabase_client import supabase
from utils.auth import (
    verify_clerk_token,
    get_current_user_id,
    require_active_membership,
    _fetch_clerk_user,
)
from utils.board_image import render_final_position_png, render_logo_card_png

logger = logging.getLogger(__name__)

user_games_bp = Blueprint('user_games', __name__)

TABLE = 'user_games'
COLLECTION_SHARES_TABLE = 'user_game_collection_shares'
DATABASES_TABLE = 'user_databases'

# Columns that clients may set when creating/updating a game
ALLOWED_FIELDS = {
    'title', 'white', 'black', 'white_elo', 'black_elo',
    'result', 'date', 'event', 'eco', 'opening_name',
    'pgn', 'notes', 'tags', 'is_favorite', 'source',
}


def _extract_pgn_headers(pgn_text: str) -> dict:
    """Parse PGN text and extract standard header values."""
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
        if not game:
            return {}
        headers = game.headers
        extracted = {}
        mapping = {
            'White': 'white',
            'Black': 'black',
            'WhiteElo': 'white_elo',
            'BlackElo': 'black_elo',
            'Result': 'result',
            'Date': 'date',
            'Event': 'event',
            'ECO': 'eco',
            'Opening': 'opening_name',
        }
        for pgn_key, db_key in mapping.items():
            val = headers.get(pgn_key)
            if val and val != '?':
                if db_key in ('white_elo', 'black_elo'):
                    try:
                        extracted[db_key] = int(val)
                    except (ValueError, TypeError):
                        pass
                else:
                    extracted[db_key] = val
        return extracted
    except Exception:
        return {}


def _fetch_owned_database(user_id: str, database_id: str):
    """Return the caller-owned, LIVE database row by id, or None.

    The id/user_id/deleted_at match is re-checked in Python so the result is
    correct even under a filter-agnostic Supabase mock.
    """
    result = supabase.table(DATABASES_TABLE) \
        .select('*') \
        .eq('id', database_id) \
        .eq('user_id', user_id) \
        .is_('deleted_at', 'null') \
        .execute()
    for row in result.data or []:
        if (row.get('id') == database_id
                and row.get('user_id') == user_id
                and row.get('deleted_at') is None):
            return row
    return None


def _default_database_id(user_id: str):
    """Return the id of the caller's LIVE default database, or None.

    Post-backfill every user has exactly one; None only if the lookup fails, in
    which case callers leave the game's database_id unset (back-compat).
    """
    result = supabase.table(DATABASES_TABLE) \
        .select('id, is_default, deleted_at, user_id') \
        .eq('user_id', user_id) \
        .eq('is_default', True) \
        .is_('deleted_at', 'null') \
        .execute()
    for row in result.data or []:
        if (row.get('user_id') == user_id
                and row.get('is_default')
                and row.get('deleted_at') is None):
            return row.get('id')
    return None


# ─── LIST ────────────────────────────────────────────────────────────────────

@user_games_bp.route('/api/games', methods=['GET'])
@verify_clerk_token
@require_active_membership
def list_games():
    """List user's games with pagination and filters.

    Query params:
        page (int): Page number (default 1)
        per_page (int): Items per page (default 20, max 100)
        q (str): Search query (player name, title, opening)
        result (str): Filter by result (1-0, 0-1, 1/2-1/2)
        favorite (bool): Filter favorites only
        tag (str): Filter by tag
        database_id (str): Scope to one owned database. Omit for all games
            (back-compat — the default before the UI passes a database).
    """
    user_id = get_current_user_id()
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(100, max(1, int(request.args.get('per_page', 20))))
        offset = (page - 1) * per_page

        query = supabase.table(TABLE) \
            .select('*', count='exact') \
            .eq('user_id', user_id) \
            .is_('deleted_at', 'null') \
            .order('created_at', desc=True)

        # Text search across player names, title, and opening
        search = request.args.get('q', '').strip()
        if search:
            query = query.or_(
                f"white.ilike.%{search}%,"
                f"black.ilike.%{search}%,"
                f"title.ilike.%{search}%,"
                f"opening_name.ilike.%{search}%"
            )

        # Filter by result
        result_filter = request.args.get('result', '').strip()
        if result_filter:
            query = query.eq('result', result_filter)

        # Filter favorites
        if request.args.get('favorite', '').lower() in ('true', '1'):
            query = query.eq('is_favorite', True)

        # Filter by tag
        tag_filter = request.args.get('tag', '').strip()
        if tag_filter:
            query = query.contains('tags', [tag_filter])

        # Scope to one database. The query is already user-scoped, so a
        # database_id the caller doesn't own simply returns no rows.
        database_id = request.args.get('database_id', '').strip()
        if database_id:
            query = query.eq('database_id', database_id)

        # Pagination
        query = query.range(offset, offset + per_page - 1)

        result = query.execute()

        return jsonify({
            'games': result.data,
            'total': result.count,
            'page': page,
            'per_page': per_page,
        }), 200

    except Exception as e:
        logger.error(f"Error listing games: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── CREATE ──────────────────────────────────────────────────────────────────

@user_games_bp.route('/api/games', methods=['POST'])
@verify_clerk_token
def create_game():
    """Create a new game.

    Request body:
        pgn (str, required): PGN notation
        database_id (str, optional): Owned database to file this game under.
            Falls back to the caller's default database so games are never orphaned.
        title, white, black, etc.: optional metadata
    """
    user_id = get_current_user_id()
    data = request.get_json()

    if not data or not data.get('pgn'):
        return jsonify({'error': 'pgn is required'}), 400

    try:
        # Validate PGN
        game = chess.pgn.read_game(io.StringIO(data['pgn']))
        if not game:
            return jsonify({'error': 'Invalid PGN'}), 400

        # Resolve the target database: an explicit one must be owned; otherwise
        # fall back to the caller's default so the game is never orphaned.
        requested_db = data.get('database_id')
        if requested_db:
            if not _fetch_owned_database(user_id, requested_db):
                return jsonify({'error': 'Database not found'}), 404
            database_id = requested_db
        else:
            database_id = _default_database_id(user_id)

        # Auto-extract headers as defaults
        extracted = _extract_pgn_headers(data['pgn'])

        row = {'user_id': user_id}
        for field in ALLOWED_FIELDS:
            if field in data:
                row[field] = data[field]
            elif field in extracted:
                row[field] = extracted[field]

        # pgn is always from the request
        row['pgn'] = data['pgn']
        if database_id:
            row['database_id'] = database_id

        result = supabase.table(TABLE).insert(row).execute()
        return jsonify(result.data[0]), 201

    except Exception as e:
        logger.error(f"Error creating game: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── READ ────────────────────────────────────────────────────────────────────

@user_games_bp.route('/api/games/<game_id>', methods=['GET'])
@verify_clerk_token
@require_active_membership
def get_game(game_id):
    """Get a single game by ID."""
    user_id = get_current_user_id()
    try:
        result = supabase.table(TABLE) \
            .select('*') \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .is_('deleted_at', 'null') \
            .execute()

        if not result.data:
            return jsonify({'error': 'Game not found'}), 404

        return jsonify(result.data[0]), 200

    except Exception as e:
        logger.error(f"Error fetching game: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── UPDATE ──────────────────────────────────────────────────────────────────

@user_games_bp.route('/api/games/<game_id>', methods=['PUT'])
@verify_clerk_token
def update_game(game_id):
    """Update game metadata, notes, tags, or favorite status."""
    user_id = get_current_user_id()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        # Verify ownership
        existing = supabase.table(TABLE) \
            .select('id') \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .is_('deleted_at', 'null') \
            .execute()

        if not existing.data:
            return jsonify({'error': 'Game not found'}), 404

        update_data = {}
        for field in ALLOWED_FIELDS:
            if field in data:
                update_data[field] = data[field]

        if not update_data:
            return jsonify({'error': 'No valid fields to update'}), 400

        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()

        result = supabase.table(TABLE) \
            .update(update_data) \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .execute()

        return jsonify(result.data[0]), 200

    except Exception as e:
        logger.error(f"Error updating game: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── DELETE (soft) ───────────────────────────────────────────────────────────

@user_games_bp.route('/api/games/<game_id>', methods=['DELETE'])
@verify_clerk_token
def delete_game(game_id):
    """Soft-delete a game by setting deleted_at."""
    user_id = get_current_user_id()
    try:
        # Verify ownership
        existing = supabase.table(TABLE) \
            .select('id') \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .is_('deleted_at', 'null') \
            .execute()

        if not existing.data:
            return jsonify({'error': 'Game not found'}), 404

        now = datetime.now(timezone.utc).isoformat()
        supabase.table(TABLE) \
            .update({'deleted_at': now, 'updated_at': now}) \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .execute()

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error deleting game: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── BULK IMPORT (localStorage migration) ───────────────────────────────────

@user_games_bp.route('/api/games/import-local', methods=['POST'])
@verify_clerk_token
def import_local():
    """Bulk import games from localStorage format.

    Request body:
        games (list, required): Array of game objects, each with at least a 'pgn' field
    """
    user_id = get_current_user_id()
    data = request.get_json()

    if not data or not isinstance(data.get('games'), list):
        return jsonify({'error': 'games array is required'}), 400

    games = data['games']
    if not games:
        return jsonify({'error': 'games array is empty'}), 400

    try:
        rows = []
        errors = []

        # Resolve the default database once so imported games aren't orphaned.
        default_db_id = _default_database_id(user_id)

        for idx, game_data in enumerate(games):
            pgn = game_data.get('pgn')
            if not pgn:
                errors.append({'index': idx, 'error': 'missing pgn'})
                continue

            # Validate PGN
            parsed = chess.pgn.read_game(io.StringIO(pgn))
            if not parsed:
                errors.append({'index': idx, 'error': 'invalid pgn'})
                continue

            extracted = _extract_pgn_headers(pgn)

            row = {'user_id': user_id, 'source': 'local_import'}
            for field in ALLOWED_FIELDS:
                if field in game_data:
                    row[field] = game_data[field]
                elif field in extracted:
                    row[field] = extracted[field]

            row['pgn'] = pgn
            # Preserve source override if provided
            if 'source' in game_data:
                row['source'] = game_data['source']
            if default_db_id:
                row['database_id'] = default_db_id

            rows.append(row)

        imported = []
        if rows:
            result = supabase.table(TABLE).insert(rows).execute()
            imported = result.data

        return jsonify({
            'imported': len(imported),
            'errors': errors,
            'games': imported,
        }), 201

    except Exception as e:
        logger.error(f"Error importing games: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── SHARE TOKENS (Phase 3a) ─────────────────────────────────────────────────
#
# A saved game is sharable only because its owner explicitly minted a token.
# The owner can revoke it (DELETE), which immediately kills the recipient view.
# Recipients must be signed in to fetch the game itself; only the OG preview
# metadata (/shared/<token>/meta) is public.


@user_games_bp.route('/api/games/<game_id>/share', methods=['POST'])
@verify_clerk_token
def create_share_token(game_id):
    """Mint (or return the existing) share token for an owned game.

    Owner-only. Idempotent: if the row already has a token, return it unchanged
    so repeated shares produce the same stable link.
    """
    user_id = get_current_user_id()
    try:
        existing = supabase.table(TABLE) \
            .select('id, share_token') \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .is_('deleted_at', 'null') \
            .execute()

        if not existing.data:
            return jsonify({'error': 'Game not found'}), 404

        token = existing.data[0].get('share_token')
        if token:
            return jsonify({'share_token': token}), 200

        token = secrets.token_urlsafe(16)
        supabase.table(TABLE) \
            .update({'share_token': token, 'updated_at': datetime.now(timezone.utc).isoformat()}) \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .execute()

        return jsonify({'share_token': token}), 200

    except Exception as e:
        logger.error(f"Error creating share token: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/<game_id>/share', methods=['DELETE'])
@verify_clerk_token
def revoke_share_token(game_id):
    """Revoke an owned game's share link by clearing its token. Owner-only."""
    user_id = get_current_user_id()
    try:
        existing = supabase.table(TABLE) \
            .select('id') \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .is_('deleted_at', 'null') \
            .execute()

        if not existing.data:
            return jsonify({'error': 'Game not found'}), 404

        supabase.table(TABLE) \
            .update({'share_token': None, 'updated_at': datetime.now(timezone.utc).isoformat()}) \
            .eq('id', game_id) \
            .eq('user_id', user_id) \
            .execute()

        return '', 204

    except Exception as e:
        logger.error(f"Error revoking share token: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/shared/<token>', methods=['GET'])
@verify_clerk_token
def get_shared_game(token):
    """Fetch a shared game by token — the recipient view.

    ANY signed-in user may read it (not just the owner). Returns the full game
    row (pgn + metadata) but NEVER user_id. Unknown or revoked token → 404.
    """
    try:
        result = supabase.table(TABLE) \
            .select('*') \
            .eq('share_token', token) \
            .is_('deleted_at', 'null') \
            .execute()

        if not result.data:
            return jsonify({'error': 'Game not found'}), 404

        row = dict(result.data[0])
        row.pop('user_id', None)
        return jsonify(row), 200

    except Exception as e:
        logger.error(f"Error fetching shared game: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/shared/<token>/meta', methods=['GET'])
def get_shared_game_meta(token):
    """Public metadata for a shared game's Open Graph link preview.

    PUBLIC — no Clerk auth. Powers the `/g/u/<token>` short-link OG cards.
    Returns ONLY header fields (players, result, event, date) — never the PGN,
    moves, user_id, or game id. Unknown token → 404.
    """
    try:
        result = supabase.table(TABLE) \
            .select('white, black, result, event, title, date') \
            .eq('share_token', token) \
            .is_('deleted_at', 'null') \
            .execute()

        if not result.data:
            return jsonify({'error': 'Game not found'}), 404

        row = result.data[0]
        return jsonify({
            'white': row.get('white'),
            'black': row.get('black'),
            'result': row.get('result'),
            'event': row.get('event') or row.get('title'),
            'date': row.get('date'),
        }), 200

    except Exception as e:
        logger.error(f"Error fetching shared game meta: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/shared/<token>/thumbnail.png', methods=['GET'])
def get_shared_game_thumbnail(token):
    """Public board-image thumbnail for a shared game's Open Graph preview.

    PUBLIC — no Clerk auth. Renders ONLY the game's FINAL position as a PNG so
    the `/g/u/<token>` short link unfurls with an actual chessboard. Never
    exposes the PGN, move list, user_id, or game id. Unknown/revoked token or
    an unrenderable PGN → 404.
    """
    try:
        result = supabase.table(TABLE) \
            .select('pgn') \
            .eq('share_token', token) \
            .is_('deleted_at', 'null') \
            .execute()

        if not result.data:
            return jsonify({'error': 'Game not found'}), 404

        png = render_final_position_png(result.data[0].get('pgn'))
        if png is None:
            return jsonify({'error': 'Game not found'}), 404

        resp = Response(png, mimetype='image/png')
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp

    except Exception as e:
        logger.error(f"Error rendering shared game thumbnail: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── COLLECTION SHARE (Phase 1) ──────────────────────────────────────────────
#
# A user may share their ENTIRE "My Games" collection via one opaque, revocable
# token — mirroring the per-game share above but at the collection level (one
# row per owner in user_game_collection_shares). Recipients must be signed in to
# browse the collection; only the OG preview (/meta, /thumbnail.png) is public.
# Revoking deletes the row, so the token stops resolving — exactly like clearing
# a per-game share_token. Shared views strip the private `notes` field.


def _owner_display_name(user_id: str):
    """Best-effort human name for a collection owner, resolved from Clerk."""
    record = _fetch_clerk_user(user_id)
    if not record:
        return None
    name = ' '.join(
        part for part in (record.get('first_name'), record.get('last_name')) if part
    ).strip()
    return name or record.get('username') or None


def _public_game(row: dict) -> dict:
    """Shape a game row for a collection-share recipient: drop private fields."""
    game = dict(row)
    game.pop('user_id', None)
    game.pop('notes', None)
    return game


def _resolve_collection_owner(token: str):
    """Return the owner user_id for a live collection-share token, else None.

    An unknown or revoked token has no matching row → None → caller 404s.
    """
    result = supabase.table(COLLECTION_SHARES_TABLE) \
        .select('user_id') \
        .eq('token', token) \
        .execute()
    if not result.data:
        return None
    return result.data[0].get('user_id')


@user_games_bp.route('/api/games/collection/share', methods=['POST'])
@verify_clerk_token
def create_collection_share_token():
    """Mint (or return the existing) share token for the caller's collection.

    Owner-only, idempotent: a user who already has a token gets it back unchanged
    so repeated shares produce the same stable link.
    """
    user_id = get_current_user_id()
    try:
        existing = supabase.table(COLLECTION_SHARES_TABLE) \
            .select('token') \
            .eq('user_id', user_id) \
            .execute()

        if existing.data:
            return jsonify({'token': existing.data[0]['token']}), 200

        token = secrets.token_urlsafe(16)
        supabase.table(COLLECTION_SHARES_TABLE) \
            .insert({'user_id': user_id, 'token': token}) \
            .execute()

        return jsonify({'token': token}), 200

    except Exception as e:
        logger.error(f"Error creating collection share token: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/collection/share', methods=['DELETE'])
@verify_clerk_token
def revoke_collection_share_token():
    """Revoke the caller's collection share link by deleting its row. Owner-only.

    Idempotent: revoking when nothing is shared still succeeds. After this the
    token no longer resolves, so every shared/* route 404s.
    """
    user_id = get_current_user_id()
    try:
        supabase.table(COLLECTION_SHARES_TABLE) \
            .delete() \
            .eq('user_id', user_id) \
            .execute()
        return '', 204

    except Exception as e:
        logger.error(f"Error revoking collection share token: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/collection/shared/<token>', methods=['GET'])
@verify_clerk_token
def get_shared_collection(token):
    """List a shared collection's games — the recipient view.

    ANY signed-in user may read it. Same paginated shape as GET /api/games, but
    the private `notes` field is stripped from every game and `user_id` is never
    returned. Also includes the owner display name. Unknown/revoked token → 404.
    """
    try:
        owner_id = _resolve_collection_owner(token)
        if not owner_id:
            return jsonify({'error': 'Collection not found'}), 404

        page = max(1, int(request.args.get('page', 1)))
        per_page = min(100, max(1, int(request.args.get('per_page', 20))))
        offset = (page - 1) * per_page

        result = supabase.table(TABLE) \
            .select('*', count='exact') \
            .eq('user_id', owner_id) \
            .is_('deleted_at', 'null') \
            .order('created_at', desc=True) \
            .range(offset, offset + per_page - 1) \
            .execute()

        return jsonify({
            'games': [_public_game(g) for g in result.data],
            'total': result.count,
            'page': page,
            'per_page': per_page,
            'owner_name': _owner_display_name(owner_id),
        }), 200

    except Exception as e:
        logger.error(f"Error listing shared collection: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/collection/shared/<token>/games/<game_id>', methods=['GET'])
@verify_clerk_token
def get_shared_collection_game(token, game_id):
    """Fetch a single game from a shared collection — signed-in recipients only.

    Returns the game only if it belongs to the token owner (404 otherwise). The
    private `notes` field and `user_id` are stripped. Unknown/revoked token → 404.
    """
    try:
        owner_id = _resolve_collection_owner(token)
        if not owner_id:
            return jsonify({'error': 'Collection not found'}), 404

        result = supabase.table(TABLE) \
            .select('*') \
            .eq('id', game_id) \
            .eq('user_id', owner_id) \
            .is_('deleted_at', 'null') \
            .execute()

        if not result.data:
            return jsonify({'error': 'Game not found'}), 404

        return jsonify(_public_game(result.data[0])), 200

    except Exception as e:
        logger.error(f"Error fetching shared collection game: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/collection/shared/<token>/meta', methods=['GET'])
def get_shared_collection_meta(token):
    """Public metadata for a shared collection's Open Graph link preview.

    PUBLIC — no Clerk auth. Returns ONLY the owner display name and game count —
    never any game data. Unknown/revoked token → 404.
    """
    try:
        owner_id = _resolve_collection_owner(token)
        if not owner_id:
            return jsonify({'error': 'Collection not found'}), 404

        count_result = supabase.table(TABLE) \
            .select('id', count='exact') \
            .eq('user_id', owner_id) \
            .is_('deleted_at', 'null') \
            .execute()

        return jsonify({
            'owner_name': _owner_display_name(owner_id),
            'game_count': count_result.count or 0,
        }), 200

    except Exception as e:
        logger.error(f"Error fetching shared collection meta: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@user_games_bp.route('/api/games/collection/shared/<token>/thumbnail.png', methods=['GET'])
def get_shared_collection_thumbnail(token):
    """Public board-image thumbnail for a shared collection's OG preview.

    PUBLIC — no Clerk auth. Renders the FINAL position of the owner's most recent
    game. Falls back to the branded logo card when the collection is empty (or
    the newest game won't render). Unknown/revoked token → 404.
    """
    try:
        owner_id = _resolve_collection_owner(token)
        if not owner_id:
            return jsonify({'error': 'Collection not found'}), 404

        result = supabase.table(TABLE) \
            .select('pgn') \
            .eq('user_id', owner_id) \
            .is_('deleted_at', 'null') \
            .order('created_at', desc=True) \
            .limit(1) \
            .execute()

        png = None
        if result.data:
            png = render_final_position_png(result.data[0].get('pgn'))
        if png is None:
            png = render_logo_card_png()
        if png is None:
            return jsonify({'error': 'Collection not found'}), 404

        resp = Response(png, mimetype='image/png')
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp

    except Exception as e:
        logger.error(f"Error rendering shared collection thumbnail: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500
