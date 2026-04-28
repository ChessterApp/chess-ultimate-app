"""
Rating System API Blueprint

Endpoints:
  GET  /api/ratings/<userId>                 — Player rating (internal + FIDE)
  GET  /api/ratings/<userId>/history         — Rating progression over time
  GET  /api/ratings/leaderboard              — Top players
  POST /api/ratings/recalculate/<tournamentId> — Recalculate from tournament (admin)
  POST /api/ratings/fide/link/<userId>       — Link FIDE ID (admin)
  GET  /api/ratings/provisional              — Provisional players listing
"""

import logging
from flask import Blueprint, request, jsonify

from utils.auth import verify_clerk_token

logger = logging.getLogger(__name__)

ratings_bp = Blueprint('ratings', __name__, url_prefix='/api/ratings')


def _get_supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


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
    """Get a player's internal rating and FIDE rating if linked."""
    supabase = _get_supabase()
    org_id = request.args.get('org_id')

    query = supabase.table('player_ratings').select('*').eq('user_id', user_id)
    if org_id:
        query = query.eq('organization_id', org_id)
    result = query.execute()
    rating_data = result.data[0] if result.data else None

    fide_result = supabase.table('player_fide_ratings').select('*').eq('user_id', user_id).execute()
    fide_data = fide_result.data[0] if fide_result.data else None

    if not rating_data and not fide_data:
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({
        'rating': rating_data,
        'fide': fide_data,
    })


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
    Reads tournament_games, computes rating changes via elo_calculator,
    updates player_ratings, and writes rating_history entries.
    """
    user_id = request.user_id
    if not _is_admin(user_id):
        return jsonify({'error': 'Admin access required'}), 403

    supabase = _get_supabase()

    # Fetch tournament games
    games_result = (
        supabase.table('tournament_games')
        .select('*')
        .eq('tournament_id', tournament_id)
        .neq('result', '*')
        .execute()
    )
    games_rows = games_result.data or []
    if not games_rows:
        return jsonify({'error': 'No completed games found for tournament'}), 404

    # Map result strings to numeric scores
    result_map = {
        '1-0': 1.0,
        '0-1': 0.0,
        '1/2-1/2': 0.5,
    }

    from services.elo_calculator import update_ratings_batch, assign_league, is_provisional, get_k_factor

    # Build game list for batch processing
    # First, fetch current ratings for all players involved
    player_ids = set()
    for g in games_rows:
        player_ids.add(g['white_player_id'])
        player_ids.add(g['black_player_id'])

    ratings_result = (
        supabase.table('player_ratings')
        .select('*')
        .in_('user_id', list(player_ids))
        .execute()
    )
    ratings_map = {r['user_id']: r for r in (ratings_result.data or [])}

    batch_games = []
    for g in games_rows:
        result_str = g['result']
        if result_str not in result_map:
            continue

        w_id = g['white_player_id']
        b_id = g['black_player_id']
        w_data = ratings_map.get(w_id, {'rating': 1200, 'games_played': 0})
        b_data = ratings_map.get(b_id, {'rating': 1200, 'games_played': 0})

        batch_games.append({
            'white_id': w_id,
            'black_id': b_id,
            'white_rating': w_data['rating'],
            'black_rating': b_data['rating'],
            'result': result_map[result_str],
            'white_games_played': w_data['games_played'],
            'black_games_played': b_data['games_played'],
        })

    changes = update_ratings_batch(batch_games)

    # Aggregate changes per player (a player may have multiple games)
    player_changes = {}
    for c in changes:
        pid = c['player_id']
        if pid not in player_changes:
            player_changes[pid] = {
                'first_rating': c['rating_before'],
                'current_rating': c['rating_after'],
                'total_change': 0,
                'games': 0,
                'last_k': c['k_factor_used'],
            }
        player_changes[pid]['current_rating'] = c['rating_after']
        player_changes[pid]['total_change'] += c['change']
        player_changes[pid]['games'] += 1
        player_changes[pid]['last_k'] = c['k_factor_used']

    # Write rating_history entries and update player_ratings
    history_rows = []
    for c in changes:
        history_rows.append({
            'user_id': c['player_id'],
            'source_type': 'tournament',
            'source_id': tournament_id,
            'rating_before': c['rating_before'],
            'rating_after': c['rating_after'],
            'change': c['change'],
            'k_factor_used': c['k_factor_used'],
        })

    if history_rows:
        supabase.table('rating_history').insert(history_rows).execute()

    # Update player_ratings for each player
    for pid, pc in player_changes.items():
        existing = ratings_map.get(pid)
        new_rating = pc['current_rating']
        new_games = (existing['games_played'] if existing else 0) + pc['games']
        new_peak = max(new_rating, existing['peak_rating'] if existing else 1200)

        update_data = {
            'rating': new_rating,
            'peak_rating': new_peak,
            'games_played': new_games,
            'k_factor': get_k_factor(new_games, new_rating),
            'league': assign_league(new_rating),
            'is_provisional': is_provisional(new_games),
        }

        if existing:
            supabase.table('player_ratings').update(update_data).eq('user_id', pid).execute()
        else:
            update_data['user_id'] = pid
            supabase.table('player_ratings').insert(update_data).execute()

    logger.info(f'Recalculated ratings for tournament {tournament_id}: {len(changes)} changes across {len(player_changes)} players')

    return jsonify({
        'tournament_id': tournament_id,
        'games_processed': len(batch_games),
        'players_updated': len(player_changes),
        'changes': changes,
    })


@ratings_bp.route('/fide/link/<user_id>', methods=['POST'])
@verify_clerk_token
def link_fide_id(user_id):
    """Link a FIDE ID to a user. Admin only."""
    admin_user_id = request.user_id
    if not _is_admin(admin_user_id):
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json()
    if not data or not data.get('fide_id'):
        return jsonify({'error': 'fide_id is required'}), 400

    from services.fide_sync import link_fide_id as do_link

    try:
        result = do_link(user_id, data['fide_id'])
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


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
