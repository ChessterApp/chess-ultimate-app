"""
Tournament Calendar API Blueprint

Public endpoints:
- GET /api/tournaments - List with filters
- GET /api/tournaments/calendar - Calendar view
- GET /api/tournaments/:id - Detail
- GET /api/tournaments/:id/participants - Registered players
- GET /api/tournaments/:id/results - Standings
- GET /api/tournaments/:id/games - Games by round

Authenticated endpoints:
- POST /api/tournaments/:id/register - Register player
- DELETE /api/tournaments/:id/register - Cancel registration

Admin endpoints:
- POST /api/tournaments - Create
- PUT /api/tournaments/:id - Update
- DELETE /api/tournaments/:id - Cancel
- POST /api/tournaments/:id/results - Upload results
- POST /api/tournaments/:id/pairings - Enter pairings
- POST /api/tournaments/:id/finalize - Lock results
"""

import logging

from flask import Blueprint, request, jsonify

from utils.auth import verify_clerk_token

logger = logging.getLogger(__name__)

tournaments_bp = Blueprint('tournaments', __name__, url_prefix='/api/tournaments')


def _get_supabase():
    """Lazy import to avoid circular imports."""
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def _get_service():
    """Lazy import tournament service."""
    from services import tournament_service
    return tournament_service


def _check_org_admin(user_id: str, org_id: str) -> bool:
    """Check if user is an admin/owner of the given organization."""
    supabase = _get_supabase()
    result = (
        supabase.table('organization_members')
        .select('role')
        .eq('organization_id', org_id)
        .eq('user_id', user_id)
        .execute()
    )
    if not result.data:
        return False
    role = result.data[0].get('role')
    return role in ('owner', 'admin')


def _check_tournament_admin(user_id: str, tournament_id: str) -> bool:
    """Check if user is admin for the tournament's organization or the creator."""
    service = _get_service()
    tournament = service.get_tournament(tournament_id)
    if not tournament:
        return False
    # Creator always has access
    if tournament.get('created_by') == user_id:
        return True
    # Org admin has access
    org_id = tournament.get('organizer_org_id')
    if org_id:
        return _check_org_admin(user_id, org_id)
    return False


# ─── PUBLIC ENDPOINTS ────────────────────────────────────────────────────────


@tournaments_bp.route('', methods=['GET'])
def list_tournaments():
    """List tournaments with filters and pagination."""
    service = _get_service()

    city = request.args.get('city')
    country = request.args.get('country')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    rating_category = request.args.get('rating_category')
    age_category = request.args.get('age_category')
    status = request.args.get('status')
    org_id = request.args.get('org_id')
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    tournaments, total = service.list_tournaments(
        city=city,
        country=country,
        date_from=date_from,
        date_to=date_to,
        rating_category=rating_category,
        age_category=age_category,
        status=status,
        org_id=org_id,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        'tournaments': tournaments,
        'total': total,
        'page': page,
        'per_page': per_page,
    }), 200


@tournaments_bp.route('/calendar', methods=['GET'])
def calendar_view():
    """Get tournaments for calendar view (month/week)."""
    service = _get_service()

    from datetime import datetime as dt
    year = int(request.args.get('year', dt.now().year))
    month = int(request.args.get('month', dt.now().month))

    tournaments = service.get_calendar(year, month)

    return jsonify({
        'year': year,
        'month': month,
        'tournaments': tournaments,
    }), 200


@tournaments_bp.route('/<tournament_id>', methods=['GET'])
def get_tournament(tournament_id):
    """Get tournament details."""
    service = _get_service()
    tournament = service.get_tournament(tournament_id)

    if not tournament:
        return jsonify({'error': 'Tournament not found'}), 404

    return jsonify(tournament), 200


@tournaments_bp.route('/<tournament_id>/participants', methods=['GET'])
def get_participants(tournament_id):
    """Get registered participants."""
    service = _get_service()
    participants = service.get_participants(tournament_id)
    return jsonify({'participants': participants}), 200


@tournaments_bp.route('/<tournament_id>/results', methods=['GET'])
def get_results(tournament_id):
    """Get tournament standings/results."""
    service = _get_service()
    standings = service.get_standings(tournament_id)
    return jsonify({'standings': standings}), 200


@tournaments_bp.route('/<tournament_id>/games', methods=['GET'])
def get_games(tournament_id):
    """Get games, optionally filtered by round."""
    service = _get_service()
    round_num = request.args.get('round', type=int)
    games = service.get_games(tournament_id, round_num=round_num)
    return jsonify({'games': games}), 200


# ─── AUTHENTICATED ENDPOINTS ─────────────────────────────────────────────────


@tournaments_bp.route('/<tournament_id>/register', methods=['POST'])
@verify_clerk_token
def register_player(tournament_id):
    """Register current user for a tournament."""
    service = _get_service()
    user_id = request.user_id
    data = request.get_json() or {}

    player_name = data.get('player_name')
    if not player_name:
        return jsonify({'error': 'player_name is required'}), 400

    age_category = data.get('age_category')
    rating = data.get('rating')

    registration, error = service.register_player(
        tournament_id=tournament_id,
        user_id=user_id,
        player_name=player_name,
        age_category=age_category,
        rating=rating,
    )

    if error:
        return jsonify({'error': error}), 400

    return jsonify(registration), 201


@tournaments_bp.route('/<tournament_id>/register', methods=['DELETE'])
@verify_clerk_token
def cancel_registration(tournament_id):
    """Cancel current user's registration."""
    service = _get_service()
    user_id = request.user_id

    success, error = service.cancel_registration(tournament_id, user_id)

    if error:
        return jsonify({'error': error}), 400

    return jsonify({'status': 'cancelled'}), 200


# ─── ADMIN ENDPOINTS ─────────────────────────────────────────────────────────


@tournaments_bp.route('', methods=['POST'])
@verify_clerk_token
def create_tournament():
    """Create a new tournament (admin only)."""
    service = _get_service()
    user_id = request.user_id
    data = request.get_json() or {}

    # Validate required fields
    required = ['name', 'location', 'start_date', 'end_date', 'registration_deadline', 'time_control']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400

    org_id = data.get('organizer_org_id')

    # Check admin permission if org specified
    if org_id and not _check_org_admin(user_id, org_id):
        return jsonify({'error': 'Not authorized to create tournaments for this organization'}), 403

    tournament = service.create_tournament(data, user_id, org_id)
    return jsonify(tournament), 201


@tournaments_bp.route('/<tournament_id>', methods=['PUT'])
@verify_clerk_token
def update_tournament(tournament_id):
    """Update a tournament (admin only)."""
    service = _get_service()
    user_id = request.user_id

    if not _check_tournament_admin(user_id, tournament_id):
        return jsonify({'error': 'Not authorized'}), 403

    data = request.get_json() or {}
    tournament = service.update_tournament(tournament_id, data)

    if not tournament:
        return jsonify({'error': 'Tournament not found'}), 404

    return jsonify(tournament), 200


@tournaments_bp.route('/<tournament_id>', methods=['DELETE'])
@verify_clerk_token
def delete_tournament(tournament_id):
    """Cancel a tournament (admin only)."""
    service = _get_service()
    user_id = request.user_id

    if not _check_tournament_admin(user_id, tournament_id):
        return jsonify({'error': 'Not authorized'}), 403

    tournament = service.cancel_tournament(tournament_id)
    return jsonify(tournament), 200


@tournaments_bp.route('/<tournament_id>/results', methods=['POST'])
@verify_clerk_token
def upload_results(tournament_id):
    """Upload tournament results via CSV or JSON (admin only)."""
    service = _get_service()
    user_id = request.user_id

    if not _check_tournament_admin(user_id, tournament_id):
        return jsonify({'error': 'Not authorized'}), 403

    content_type = request.content_type or ''

    if 'multipart/form-data' in content_type:
        # CSV file upload
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400
        csv_text = file.read().decode('utf-8')
        results, error = service.upload_results(tournament_id, csv_text, fmt="csv")
    else:
        # JSON body
        data = request.get_json() or {}
        results_data = data.get('results', [])
        fmt = data.get('format', 'json')
        if fmt == 'csv':
            csv_text = data.get('csv', '')
            results, error = service.upload_results(tournament_id, csv_text, fmt="csv")
        else:
            results, error = service.upload_results(tournament_id, results_data, fmt="json")

    if error:
        return jsonify({'error': error}), 400

    return jsonify({'results': results, 'count': len(results)}), 200


@tournaments_bp.route('/<tournament_id>/pairings', methods=['POST'])
@verify_clerk_token
def enter_pairings(tournament_id):
    """Enter pairings for a round (admin only)."""
    service = _get_service()
    user_id = request.user_id

    if not _check_tournament_admin(user_id, tournament_id):
        return jsonify({'error': 'Not authorized'}), 403

    data = request.get_json() or {}
    round_num = data.get('round')
    pairings = data.get('pairings', [])

    if not round_num:
        return jsonify({'error': 'round is required'}), 400
    if not pairings:
        return jsonify({'error': 'pairings list is required'}), 400

    # Validate pairing structure
    for p in pairings:
        if not p.get('white_player_id') or not p.get('black_player_id'):
            return jsonify({'error': 'Each pairing must have white_player_id and black_player_id'}), 400

    games = service.enter_pairings(tournament_id, int(round_num), pairings)
    return jsonify({'games': games, 'count': len(games)}), 201


@tournaments_bp.route('/<tournament_id>/finalize', methods=['POST'])
@verify_clerk_token
def finalize_tournament(tournament_id):
    """Finalize tournament: lock results and trigger rating calculation (admin only)."""
    service = _get_service()
    user_id = request.user_id

    if not _check_tournament_admin(user_id, tournament_id):
        return jsonify({'error': 'Not authorized'}), 403

    success, error = service.finalize_tournament(tournament_id)

    if error:
        return jsonify({'error': error}), 400

    return jsonify({'status': 'finalized', 'tournament_id': tournament_id}), 200
