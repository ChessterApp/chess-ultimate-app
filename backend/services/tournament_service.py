"""
Tournament Service - Business logic for tournament management.

Handles:
- Tournament CRUD
- Player registration with eligibility checks
- Results upload (CSV/JSON)
- Pairings entry
- Standings calculation (Buchholz + Sonneborn-Berger tiebreaks)
- Tournament finalization
"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _get_supabase():
    """Lazy import to avoid circular imports."""
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


# ─── League C eligibility (Chess Empire level gate) ──────────────────────────

LEVEL_TOO_LOW_CODE = 'level_too_low'
LEAGUE_C_MIN_LEVEL = 2


def _get_chess_empire_client():
    """Lazy import the shared Chess Empire client (keeps tests patchable)."""
    from services.chess_empire_client import get_client
    return get_client()


def _get_chess_empire_level(user_id: str) -> Optional[int]:
    """
    Resolve the registering student's Chess Empire ``current_level``.

    Looks up the member's ``external_student_id`` link (source ``chess_empire``)
    and reads the level from the CE student profile. Returns ``None`` when the
    student has no linked profile, no level, or the lookup fails — callers treat
    ``None`` as "do not block" per the League C spec.
    """
    supabase = _get_supabase()
    result = (
        supabase.table('organization_members')
        .select('external_student_id')
        .eq('user_id', user_id)
        .eq('external_source', 'chess_empire')
        .execute()
    )
    student_id = None
    for row in (result.data or []):
        if row.get('external_student_id'):
            student_id = row['external_student_id']
            break
    if not student_id:
        return None

    try:
        profile = _get_chess_empire_client().get_student_profile(student_id)
    except Exception:
        logger.exception('Failed to resolve Chess Empire profile for %s', user_id)
        return None

    level = profile.get('current_level') if isinstance(profile, dict) else None
    if isinstance(level, bool) or not isinstance(level, int):
        return None
    return level


def _league_c_level_error(tournament: Dict[str, Any], user_id: str) -> Optional[Dict[str, str]]:
    """
    Return a structured ``level_too_low`` error for League C tournaments when the
    student is below Level 2, else ``None``.

    Non-League-C tournaments, unlinked students, and unknown levels return
    ``None`` (registration allowed).
    """
    if tournament.get('league') != 'C':
        return None
    level = _get_chess_empire_level(user_id)
    if level is not None and level < LEAGUE_C_MIN_LEVEL:
        return {
            'code': LEVEL_TOO_LOW_CODE,
            'message': (
                'League C tournaments require Level 2 or higher. '
                f'You are currently on Level {level} — complete your Level {level} '
                'lessons to unlock registration.'
            ),
        }
    return None


def get_registration_eligibility(tournament_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Pre-check whether a student may register for a tournament (used by the
    registration page to warn before submit). Returns ``None`` if the tournament
    does not exist, otherwise a dict with ``league``, ``eligible`` and — when
    blocked — the ``code``/``message`` from the structured eligibility error.
    """
    tournament = get_tournament(tournament_id)
    if not tournament:
        return None

    error = _league_c_level_error(tournament, user_id)
    result: Dict[str, Any] = {
        'league': tournament.get('league'),
        'eligible': error is None,
    }
    if error:
        result.update(error)
    return result


def create_tournament(data: Dict[str, Any], user_id: str, org_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a new tournament.

    Args:
        data: Tournament fields (name, location, dates, etc.)
        user_id: Clerk user ID of the creator
        org_id: Organization ID (if created by an org admin)

    Returns:
        Created tournament record
    """
    supabase = _get_supabase()

    record = {
        'name': data['name'],
        'description': data.get('description'),
        'location': data['location'],
        'city': data.get('city'),
        'country': data.get('country', 'KZ'),
        'start_date': data['start_date'],
        'end_date': data['end_date'],
        'registration_deadline': data['registration_deadline'],
        'time_control': data['time_control'],
        'format': data.get('format'),
        'max_participants': data.get('max_participants'),
        'entry_fee': data.get('entry_fee', 0),
        'currency': data.get('currency', 'KZT'),
        'prize_fund': data.get('prize_fund'),
        'prize_distribution': data.get('prize_distribution'),
        'age_categories': data.get('age_categories'),
        'rating_category': data.get('rating_category'),
        'min_rating': data.get('min_rating'),
        'max_rating': data.get('max_rating'),
        'league': data.get('league') or None,
        'is_rated': data.get('is_rated', False),
        'tournament_mode': data.get('tournament_mode', 'offline'),
        'organizer_org_id': org_id,
        'created_by': user_id,
        'status': data.get('status', 'upcoming'),
        'rules_url': data.get('rules_url'),
        'image_url': data.get('image_url'),
    }

    result = supabase.table('tournaments').insert(record).execute()
    return result.data[0] if result.data else {}


def update_tournament(tournament_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing tournament.

    Args:
        tournament_id: UUID of the tournament
        data: Fields to update

    Returns:
        Updated tournament record
    """
    supabase = _get_supabase()

    allowed_fields = {
        'name', 'description', 'location', 'city', 'country',
        'start_date', 'end_date', 'registration_deadline', 'time_control',
        'format', 'max_participants', 'entry_fee', 'currency',
        'prize_fund', 'prize_distribution', 'age_categories',
        'rating_category', 'min_rating', 'max_rating', 'is_rated',
        'tournament_mode', 'status', 'rules_url', 'image_url', 'league',
    }

    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    # Empty-string league from the admin form's "None" option means "no league".
    if update_data.get('league') == '':
        update_data['league'] = None
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()

    result = supabase.table('tournaments').update(update_data).eq('id', tournament_id).execute()
    return result.data[0] if result.data else {}


def cancel_tournament(tournament_id: str) -> Dict[str, Any]:
    """Cancel a tournament by setting status to 'cancelled'."""
    return update_tournament(tournament_id, {'status': 'cancelled'})


def get_tournament(tournament_id: str) -> Optional[Dict[str, Any]]:
    """Get a single tournament by ID."""
    supabase = _get_supabase()
    result = supabase.table('tournaments').select('*').eq('id', tournament_id).execute()
    return result.data[0] if result.data else None


def list_tournaments(
    city: Optional[str] = None,
    country: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    rating_category: Optional[str] = None,
    age_category: Optional[str] = None,
    status: Optional[str] = None,
    org_id: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    List tournaments with filters and pagination.

    Returns:
        Tuple of (tournaments list, total count)
    """
    supabase = _get_supabase()

    query = supabase.table('tournaments').select('*', count='exact')

    if city:
        query = query.eq('city', city)
    if country:
        query = query.eq('country', country)
    if date_from:
        query = query.gte('start_date', date_from)
    if date_to:
        query = query.lte('end_date', date_to)
    if rating_category:
        query = query.eq('rating_category', rating_category)
    if age_category:
        query = query.contains('age_categories', [age_category])
    if status:
        query = query.eq('status', status)
    if org_id:
        query = query.eq('organizer_org_id', org_id)

    # Exclude cancelled by default unless specifically requested
    if not status:
        query = query.neq('status', 'cancelled')

    offset = (page - 1) * per_page
    query = query.order('start_date', desc=False).range(offset, offset + per_page - 1)

    result = query.execute()
    total = result.count if result.count is not None else len(result.data or [])
    return result.data or [], total


def get_calendar(year: int, month: int) -> List[Dict[str, Any]]:
    """
    Get tournaments for a calendar month view.

    Returns tournaments that overlap with the given month.
    """
    supabase = _get_supabase()

    # Calculate month boundaries
    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year + 1}-01-01"
    else:
        month_end = f"{year}-{month + 1:02d}-01"

    result = (
        supabase.table('tournaments')
        .select('id, name, start_date, end_date, city, country, status, format, entry_fee, currency')
        .neq('status', 'cancelled')
        .lt('start_date', month_end)
        .gte('end_date', month_start)
        .order('start_date', desc=False)
        .execute()
    )

    return result.data or []


def register_player(
    tournament_id: str,
    user_id: str,
    player_name: str,
    age_category: Optional[str] = None,
    rating: Optional[int] = None,
) -> Tuple[Dict[str, Any], Optional[Any]]:
    """
    Register a player for a tournament.

    Checks eligibility:
    - Registration deadline not passed
    - Max participants not exceeded
    - Rating within allowed range
    - League C requires Chess Empire Level 2+

    Returns:
        Tuple of (registration record, error or None). The error is a plain
        string for simple rejections, or a structured dict
        ``{'code': ..., 'message': ...}`` for the League C level gate.
    """
    supabase = _get_supabase()

    # Get tournament details
    tournament = get_tournament(tournament_id)
    if not tournament:
        return {}, "Tournament not found"

    # Check registration deadline
    deadline = tournament.get('registration_deadline')
    if deadline:
        deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > deadline_dt:
            return {}, "Registration deadline has passed"

    # Check max participants
    max_participants = tournament.get('max_participants')
    if max_participants:
        reg_count = (
            supabase.table('tournament_registrations')
            .select('id', count='exact')
            .eq('tournament_id', tournament_id)
            .neq('registration_status', 'cancelled')
            .execute()
        )
        current_count = reg_count.count if reg_count.count is not None else 0
        if current_count >= max_participants:
            return {}, "Tournament is full"

    # Check rating eligibility
    min_rating = tournament.get('min_rating')
    max_rating = tournament.get('max_rating')
    if rating is not None:
        if min_rating and rating < min_rating:
            return {}, f"Rating {rating} is below minimum {min_rating}"
        if max_rating and rating > max_rating:
            return {}, f"Rating {rating} is above maximum {max_rating}"

    # Check tournament status allows registration
    allowed_statuses = ('upcoming', 'registration_open')
    if tournament.get('status') not in allowed_statuses:
        return {}, "Tournament is not accepting registrations"

    # Check League C level gate (Chess Empire Level 2+)
    league_error = _league_c_level_error(tournament, user_id)
    if league_error:
        return {}, league_error

    # Determine registration status
    entry_fee = float(tournament.get('entry_fee') or 0)
    if entry_fee > 0:
        reg_status = 'pending'
        payment_status = 'pending'
    else:
        reg_status = 'confirmed'
        payment_status = 'waived'

    record = {
        'tournament_id': tournament_id,
        'user_id': user_id,
        'player_name': player_name,
        'rating_at_registration': rating,
        'age_category': age_category,
        'registration_status': reg_status,
        'payment_status': payment_status,
    }

    result = supabase.table('tournament_registrations').insert(record).execute()
    return (result.data[0] if result.data else {}), None


def cancel_registration(tournament_id: str, user_id: str) -> Tuple[bool, Optional[str]]:
    """
    Cancel a player's registration.

    Only allowed before the registration deadline.

    Returns:
        Tuple of (success, error message or None)
    """
    supabase = _get_supabase()

    tournament = get_tournament(tournament_id)
    if not tournament:
        return False, "Tournament not found"

    deadline = tournament.get('registration_deadline')
    if deadline:
        deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > deadline_dt:
            return False, "Cannot cancel after registration deadline"

    supabase.table('tournament_registrations').update({
        'registration_status': 'cancelled',
    }).eq('tournament_id', tournament_id).eq('user_id', user_id).execute()

    return True, None


def get_participants(tournament_id: str) -> List[Dict[str, Any]]:
    """Get all registered participants for a tournament."""
    supabase = _get_supabase()
    result = (
        supabase.table('tournament_registrations')
        .select('*')
        .eq('tournament_id', tournament_id)
        .neq('registration_status', 'cancelled')
        .order('registered_at', desc=False)
        .execute()
    )
    return result.data or []


def get_games(tournament_id: str, round_num: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get games for a tournament, optionally filtered by round."""
    supabase = _get_supabase()
    query = (
        supabase.table('tournament_games')
        .select('*')
        .eq('tournament_id', tournament_id)
    )
    if round_num is not None:
        query = query.eq('round', round_num)
    query = query.order('round', desc=False).order('board', desc=False)
    result = query.execute()
    return result.data or []


def enter_pairings(tournament_id: str, round_num: int, pairings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enter pairings for a specific round.

    Each pairing dict should have: white_player_id, black_player_id, board (optional)

    Returns:
        List of created game records
    """
    supabase = _get_supabase()

    records = []
    for i, pairing in enumerate(pairings):
        record = {
            'tournament_id': tournament_id,
            'round': round_num,
            'board': pairing.get('board', i + 1),
            'white_player_id': pairing['white_player_id'],
            'black_player_id': pairing['black_player_id'],
            'result': '*',  # Not yet played
        }
        if 'white_rating_before' in pairing:
            record['white_rating_before'] = pairing['white_rating_before']
        if 'black_rating_before' in pairing:
            record['black_rating_before'] = pairing['black_rating_before']
        records.append(record)

    result = supabase.table('tournament_games').upsert(records).execute()
    return result.data or []


def upload_results(tournament_id: str, results_data: Any, fmt: str = "json") -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Upload tournament results.

    Supports CSV and JSON formats.
    CSV columns: round, board, white_player_id, black_player_id, result
    JSON: list of dicts with same fields

    Returns:
        Tuple of (upserted records, error message or None)
    """
    supabase = _get_supabase()

    if fmt == "csv":
        games, error = _parse_csv_results(results_data, tournament_id)
        if error:
            return [], error
    elif fmt == "json":
        games = []
        for row in results_data:
            games.append({
                'tournament_id': tournament_id,
                'round': int(row['round']),
                'board': int(row.get('board', 0)) or None,
                'white_player_id': row['white_player_id'],
                'black_player_id': row['black_player_id'],
                'result': row['result'],
                'pgn': row.get('pgn'),
            })
    else:
        return [], f"Unsupported format: {fmt}"

    # Validate results
    valid_results = {'1-0', '0-1', '1/2-1/2', '*', '+/-', '-/+'}
    for game in games:
        if game.get('result') not in valid_results:
            return [], f"Invalid result: {game.get('result')}"

    result = supabase.table('tournament_games').upsert(games).execute()
    return result.data or [], None


def _parse_csv_results(csv_text: str, tournament_id: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Parse CSV results text into game records.

    Expected columns: round, board, white_player_id, black_player_id, result
    """
    games = []
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            if not row.get('round') or not row.get('white_player_id') or not row.get('black_player_id'):
                continue
            games.append({
                'tournament_id': tournament_id,
                'round': int(row['round']),
                'board': int(row['board']) if row.get('board') else None,
                'white_player_id': row['white_player_id'].strip(),
                'black_player_id': row['black_player_id'].strip(),
                'result': row.get('result', '*').strip(),
                'pgn': row.get('pgn'),
            })
    except Exception as e:
        return [], f"CSV parsing error: {str(e)}"

    return games, None


def get_standings(tournament_id: str) -> List[Dict[str, Any]]:
    """
    Get tournament standings with Buchholz and Sonneborn-Berger tiebreaks.

    If standings exist in the database, return them.
    Otherwise, calculate from games.
    """
    supabase = _get_supabase()

    # Check if pre-calculated standings exist
    result = (
        supabase.table('tournament_standings')
        .select('*')
        .eq('tournament_id', tournament_id)
        .order('rank', desc=False)
        .execute()
    )
    if result.data:
        return result.data

    # Calculate from games
    return calculate_standings(tournament_id)


def calculate_standings(tournament_id: str) -> List[Dict[str, Any]]:
    """
    Calculate standings from game results.

    Computes:
    - Score (1 for win, 0.5 for draw, 0 for loss)
    - Buchholz (sum of opponents' scores)
    - Sonneborn-Berger (sum of defeated opponents' scores + half of drawn opponents' scores)
    """
    games = get_games(tournament_id)
    if not games:
        return []

    # Gather all players and their results
    player_scores: Dict[str, float] = {}
    player_wins: Dict[str, int] = {}
    player_draws: Dict[str, int] = {}
    player_losses: Dict[str, int] = {}
    # opponents[player] = list of (opponent_id, score_against_opponent)
    opponents: Dict[str, List[Tuple[str, float]]] = {}

    for game in games:
        if game['result'] == '*':
            continue  # Skip unplayed games

        white = game['white_player_id']
        black = game['black_player_id']
        result = game['result']

        # Initialize
        for p in (white, black):
            if p not in player_scores:
                player_scores[p] = 0.0
                player_wins[p] = 0
                player_draws[p] = 0
                player_losses[p] = 0
                opponents[p] = []

        if result == '1-0':
            player_scores[white] += 1.0
            player_wins[white] += 1
            player_losses[black] += 1
            opponents[white].append((black, 1.0))
            opponents[black].append((white, 0.0))
        elif result == '0-1':
            player_scores[black] += 1.0
            player_wins[black] += 1
            player_losses[white] += 1
            opponents[black].append((white, 1.0))
            opponents[white].append((black, 0.0))
        elif result == '1/2-1/2':
            player_scores[white] += 0.5
            player_scores[black] += 0.5
            player_draws[white] += 1
            player_draws[black] += 1
            opponents[white].append((black, 0.5))
            opponents[black].append((white, 0.5))
        elif result == '+/-':
            # White wins by forfeit
            player_scores[white] += 1.0
            player_wins[white] += 1
            player_losses[black] += 1
            opponents[white].append((black, 1.0))
            opponents[black].append((white, 0.0))
        elif result == '-/+':
            # Black wins by forfeit
            player_scores[black] += 1.0
            player_wins[black] += 1
            player_losses[white] += 1
            opponents[black].append((white, 1.0))
            opponents[white].append((black, 0.0))

    # Calculate Buchholz: sum of all opponents' scores
    buchholz: Dict[str, float] = {}
    for player, opp_list in opponents.items():
        buchholz[player] = sum(player_scores.get(opp_id, 0.0) for opp_id, _ in opp_list)

    # Calculate Sonneborn-Berger: sum of (score_against_opp * opp_total_score)
    sonneborn_berger: Dict[str, float] = {}
    for player, opp_list in opponents.items():
        sb = 0.0
        for opp_id, score_against in opp_list:
            sb += score_against * player_scores.get(opp_id, 0.0)
        sonneborn_berger[player] = sb

    # Build standings sorted by: score desc, buchholz desc, sonneborn-berger desc
    standings = []
    for player in player_scores:
        standings.append({
            'tournament_id': tournament_id,
            'user_id': player,
            'score': player_scores[player],
            'buchholz': buchholz.get(player, 0.0),
            'sonneborn_berger': sonneborn_berger.get(player, 0.0),
            'wins': player_wins.get(player, 0),
            'draws': player_draws.get(player, 0),
            'losses': player_losses.get(player, 0),
        })

    standings.sort(key=lambda x: (-x['score'], -x['buchholz'], -x['sonneborn_berger']))

    # Assign ranks
    for i, s in enumerate(standings):
        s['rank'] = i + 1

    return standings


def finalize_tournament(tournament_id: str) -> Tuple[bool, Optional[str]]:
    """
    Finalize a tournament:
    1. Calculate and store standings
    2. Lock tournament status to 'completed'
    3. Placeholder for rating calculation trigger

    Returns:
        Tuple of (success, error message or None)
    """
    supabase = _get_supabase()

    tournament = get_tournament(tournament_id)
    if not tournament:
        return False, "Tournament not found"

    if tournament.get('status') == 'completed':
        return False, "Tournament is already finalized"

    # Calculate standings
    standings = calculate_standings(tournament_id)
    if not standings:
        return False, "No games found to finalize"

    # Store standings in database (upsert to handle re-finalization)
    supabase.table('tournament_standings').upsert(standings).execute()

    # Update tournament status
    supabase.table('tournaments').update({
        'status': 'completed',
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }).eq('id', tournament_id).execute()

    # Trigger rating calculation
    try:
        from services.rating_service import recalculate_ratings_for_tournament
        result = recalculate_ratings_for_tournament(tournament_id)
        logger.info(f"Tournament {tournament_id} finalized. Ratings updated: {result['players_updated']} players, {result['games_processed']} games.")
    except Exception as e:
        logger.error(f"Tournament {tournament_id} finalized but rating calculation failed: {e}")

    return True, None
