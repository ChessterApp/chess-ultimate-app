"""
Rating Service - Business logic for rating recalculation.

Extracted from routes/ratings.py to allow calling from both
API endpoints and tournament finalization.
"""

import logging
from typing import Any, Dict

from services.elo_calculator import (
    assign_league,
    get_k_factor,
    is_provisional,
    update_ratings_batch,
)

logger = logging.getLogger(__name__)


def _get_supabase():
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def recalculate_ratings_for_tournament(tournament_id: str) -> Dict[str, Any]:
    """
    Recalculate ratings from tournament results.

    Hard-gates on the tournament being:
      - found,
      - flagged is_rated=true,
      - tournament_mode='offline'.

    If any gate fails, returns early with a 'skipped_reason' and no DB writes.
    Otherwise reads tournament_games, computes rating changes via elo_calculator,
    updates player_ratings, and writes rating_history entries.

    Returns:
        Dict with tournament_id, games_processed, players_updated, changes
        (and 'skipped_reason' when gated).

    Raises:
        ValueError if the tournament does not exist.
    """
    supabase = _get_supabase()

    # Hard gate: fetch the tournament and check rated/offline status.
    tournament_result = (
        supabase.table('tournaments')
        .select('*')
        .eq('id', tournament_id)
        .execute()
    )
    tournament_rows = tournament_result.data or []
    if not tournament_rows:
        raise ValueError(f"Tournament not found: {tournament_id}")

    tournament = tournament_rows[0]
    if not tournament.get('is_rated'):
        return {
            'tournament_id': tournament_id,
            'games_processed': 0,
            'players_updated': 0,
            'changes': [],
            'skipped_reason': 'not_rated',
        }
    if tournament.get('tournament_mode') != 'offline':
        return {
            'tournament_id': tournament_id,
            'games_processed': 0,
            'players_updated': 0,
            'changes': [],
            'skipped_reason': 'not_offline',
        }

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
        return {
            'tournament_id': tournament_id,
            'games_processed': 0,
            'players_updated': 0,
            'changes': [],
        }

    # Map result strings to numeric scores
    result_map = {
        '1-0': 1.0,
        '0-1': 0.0,
        '1/2-1/2': 0.5,
    }

    # Collect all player IDs
    player_ids = set()
    for g in games_rows:
        player_ids.add(g['white_player_id'])
        player_ids.add(g['black_player_id'])

    # Fetch current ratings
    ratings_result = (
        supabase.table('player_ratings')
        .select('*')
        .in_('user_id', list(player_ids))
        .execute()
    )
    ratings_map = {r['user_id']: r for r in (ratings_result.data or [])}

    # Build game list for batch processing
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

    # Aggregate changes per player
    player_changes: Dict[str, Dict[str, Any]] = {}
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

    # Write rating_history entries
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

    logger.info(
        f'Recalculated ratings for tournament {tournament_id}: '
        f'{len(changes)} changes across {len(player_changes)} players'
    )

    return {
        'tournament_id': tournament_id,
        'games_processed': len(batch_games),
        'players_updated': len(player_changes),
        'changes': changes,
    }
