"""
Rating System API Blueprint

Endpoints:
  GET  /api/ratings/<userId>                 — Player's Local App Rating
  GET  /api/ratings/<userId>/history         — Rating progression over time
  GET  /api/ratings/leaderboard              — Top players
  POST /api/ratings/recalculate/<tournamentId> — Recalculate from tournament (admin)
  GET  /api/ratings/provisional              — Provisional players listing
"""

import logging
from flask import Blueprint, request, jsonify

from utils.auth import verify_clerk_token

logger = logging.getLogger(__name__)

ratings_bp = Blueprint('ratings', __name__, url_prefix='/api/ratings')


from utils.supabase_client import get_supabase as _get_supabase


def _is_admin(user_id: str, org_id: str = None) -> bool:
    """Check if user has admin/owner role in an organization."""
    supabase = _get_supabase()
    query = supabase.table('organization_members').select('role').eq('user_id', user_id)
    if org_id:
        query = query.eq('organization_id', org_id)
    query = query.in_('role', ['owner', 'admin'])
    result = query.execute()
    return bool(result.data)


@ratings_bp.route('/<user_id>', methods=['GET'])
def get_player_rating(user_id):
    """Get a player's Local App Rating."""
    supabase = _get_supabase()
    org_id = request.args.get('org_id')

    query = supabase.table('player_ratings').select('*').eq('user_id', user_id)
    if org_id:
        query = query.eq('organization_id', org_id)
    result = query.execute()
    rating_data = result.data[0] if result.data else None

    if not rating_data:
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({'rating': rating_data})


@ratings_bp.route('/<user_id>/history', methods=['GET'])
def get_rating_history(user_id):
    """Get a player's rating history, ordered chronologically."""
    supabase = _get_supabase()
    limit = request.args.get('limit', 50, type=int)

    result = (
        supabase.table('rating_history')
        .select('*')
        .eq('user_id', user_id)
        .order('calculated_at', desc=False)
        .limit(limit)
        .execute()
    )

    return jsonify({'history': result.data or []})


@ratings_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """
    Top players sorted by rating.
    Filters: league, org_id. Provisional players excluded by default.
    """
    supabase = _get_supabase()
    league = request.args.get('league')
    org_id = request.args.get('org_id')
    include_provisional = request.args.get('include_provisional', 'false').lower() == 'true'
    limit = request.args.get('limit', 50, type=int)

    query = supabase.table('player_ratings').select('*')

    if not include_provisional:
        query = query.eq('is_provisional', False)
    if league:
        query = query.eq('league', league)
    if org_id:
        query = query.eq('organization_id', org_id)

    result = query.order('rating', desc=True).limit(limit).execute()

    return jsonify({'leaderboard': result.data or []})


@ratings_bp.route('/recalculate/<tournament_id>', methods=['POST'])
@verify_clerk_token
def recalculate_tournament(tournament_id):
    """
    Recalculate ratings from tournament results. Admin only.
    Delegates to rating_service for the actual computation.
    """
    user_id = request.user_id
    if not _is_admin(user_id):
        return jsonify({'error': 'Admin access required'}), 403

    from services.rating_service import recalculate_ratings_for_tournament

    try:
        result = recalculate_ratings_for_tournament(tournament_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404

    if result['games_processed'] == 0 and 'skipped_reason' not in result:
        return jsonify({'error': 'No completed games found for tournament'}), 404

    return jsonify(result)


@ratings_bp.route('/provisional', methods=['GET'])
def get_provisional_players():
    """List provisional players (games_played < 30)."""
    supabase = _get_supabase()
    org_id = request.args.get('org_id')
    limit = request.args.get('limit', 50, type=int)

    query = supabase.table('player_ratings').select('*').eq('is_provisional', True)
    if org_id:
        query = query.eq('organization_id', org_id)

    result = query.order('rating', desc=True).limit(limit).execute()

    return jsonify({'provisional': result.data or []})
