"""
User Games API — CRUD + Import endpoints for My Games feature
"""

import io
import logging
import traceback
from datetime import datetime, timezone

import chess
import chess.pgn
from flask import Blueprint, request, jsonify

from services.supabase_client import supabase
from utils.auth import verify_clerk_token, get_current_user_id

logger = logging.getLogger(__name__)

user_games_bp = Blueprint('user_games', __name__)

TABLE = 'user_games'

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


# ─── LIST ────────────────────────────────────────────────────────────────────

@user_games_bp.route('/api/games', methods=['GET'])
@verify_clerk_token
def list_games():
    """List user's games with pagination and filters.

    Query params:
        page (int): Page number (default 1)
        per_page (int): Items per page (default 20, max 100)
        q (str): Search query (player name, title, opening)
        result (str): Filter by result (1-0, 0-1, 1/2-1/2)
        favorite (bool): Filter favorites only
        tag (str): Filter by tag
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

        result = supabase.table(TABLE).insert(row).execute()
        return jsonify(result.data[0]), 201

    except Exception as e:
        logger.error(f"Error creating game: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ─── READ ────────────────────────────────────────────────────────────────────

@user_games_bp.route('/api/games/<game_id>', methods=['GET'])
@verify_clerk_token
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
