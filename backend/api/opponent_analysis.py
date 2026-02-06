"""
Opponent Analysis API Blueprint

Provides endpoints for searching and analyzing chess players from the TWIC database.
Supports player search, profile stats, game filtering, and opening analysis.

Endpoints:
    GET /api/opponent/search - Search players by name (autocomplete)
    GET /api/opponent/<name>/profile - Get player profile and stats
    GET /api/opponent/<name>/games - Get filtered game list
    GET /api/opponent/<name>/openings - Get opening statistics
    GET /api/opponent/<name>/opponents - Get frequent opponents
    GET /api/opponent/game/<id>/pgn - Get full PGN for a game
"""

import os
import sqlite3
from typing import Optional, List, Dict, Any, Tuple
from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)

opponent_bp = Blueprint('opponent', __name__, url_prefix='/api/opponent')

# Database path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "data/twic/games_index.db")
PGN_PATH = os.path.join(BACKEND_DIR, "data/twic/twic_master_database.pgn")


def get_db_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def check_database_exists() -> bool:
    """Check if the indexed database exists."""
    return os.path.exists(DB_PATH)


def normalize_name(name: str) -> str:
    """Normalize player name for searching."""
    import unicodedata
    if not name:
        return ""
    normalized = unicodedata.normalize('NFKD', name)
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
    normalized = normalized.lower().replace(",", " ").replace("  ", " ").strip()
    return normalized


@opponent_bp.route('/status', methods=['GET'])
def database_status():
    """Check database indexing status."""
    if not check_database_exists():
        return jsonify({
            'indexed': False,
            'message': 'Database not indexed. Run: python scripts/index_pgn_database.py'
        }), 503

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get metadata
        cursor.execute("SELECT key, value FROM metadata")
        metadata = {row['key']: row['value'] for row in cursor.fetchall()}

        conn.close()

        return jsonify({
            'indexed': True,
            'game_count': int(metadata.get('game_count', 0)),
            'player_count': int(metadata.get('player_count', 0)),
            'indexed_at': metadata.get('indexed_at', 'unknown')
        })
    except Exception as e:
        logger.error(f"Error checking database status: {e}")
        return jsonify({'error': str(e)}), 500


@opponent_bp.route('/search', methods=['GET'])
def search_players():
    """
    Search for players by name (autocomplete).

    Query params:
        q: Search query (required, min 2 chars)
        limit: Max results (default 20, max 100)

    Returns:
        List of matching players with basic stats
    """
    if not check_database_exists():
        return jsonify({'error': 'Database not indexed'}), 503

    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 100)

    if len(query) < 2:
        return jsonify({'error': 'Query must be at least 2 characters'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Normalize search query
        search_term = normalize_name(query)

        # Use FTS for full-text search if available, otherwise LIKE
        try:
            cursor.execute('''
                SELECT p.id, p.name, p.fide_id, p.title, p.highest_elo,
                       p.latest_elo, p.total_games,
                       (p.wins_white + p.wins_black) as wins,
                       (p.losses_white + p.losses_black) as losses,
                       p.draws
                FROM players p
                JOIN players_fts fts ON p.id = fts.rowid
                WHERE players_fts MATCH ?
                ORDER BY p.total_games DESC
                LIMIT ?
            ''', (f'{search_term}*', limit))
        except sqlite3.OperationalError:
            # Fallback to LIKE if FTS not available
            cursor.execute('''
                SELECT id, name, fide_id, title, highest_elo, latest_elo,
                       total_games,
                       (wins_white + wins_black) as wins,
                       (losses_white + losses_black) as losses,
                       draws
                FROM players
                WHERE name_normalized LIKE ?
                ORDER BY total_games DESC
                LIMIT ?
            ''', (f'%{search_term}%', limit))

        results = []
        for row in cursor.fetchall():
            total = row['wins'] + row['losses'] + row['draws']
            win_rate = (row['wins'] / total * 100) if total > 0 else 0

            results.append({
                'id': row['id'],
                'name': row['name'],
                'fide_id': row['fide_id'],
                'title': row['title'],
                'highest_elo': row['highest_elo'],
                'latest_elo': row['latest_elo'],
                'total_games': row['total_games'],
                'wins': row['wins'],
                'losses': row['losses'],
                'draws': row['draws'],
                'win_rate': round(win_rate, 1)
            })

        conn.close()
        return jsonify(results)

    except Exception as e:
        logger.error(f"Error searching players: {e}")
        return jsonify({'error': str(e)}), 500


@opponent_bp.route('/<player_name>/profile', methods=['GET'])
def get_player_profile(player_name: str):
    """
    Get player profile with aggregated statistics.

    Returns:
        Player profile including ELO history, win rates, and game counts
    """
    if not check_database_exists():
        return jsonify({'error': 'Database not indexed'}), 503

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Find player by name (exact or normalized match)
        cursor.execute('''
            SELECT * FROM players
            WHERE name = ? OR name_normalized = ?
            LIMIT 1
        ''', (player_name, normalize_name(player_name)))

        player = cursor.fetchone()

        if not player:
            conn.close()
            return jsonify({'error': 'Player not found'}), 404

        # Calculate statistics
        total_games = player['total_games']
        wins = player['wins_white'] + player['wins_black']
        losses = player['losses_white'] + player['losses_black']
        draws = player['draws']

        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        draw_rate = (draws / total_games * 100) if total_games > 0 else 0

        # Get ELO progression (sample of games over time)
        cursor.execute('''
            SELECT date,
                   CASE WHEN white_name = ? THEN white_elo ELSE black_elo END as elo
            FROM games
            WHERE (white_name = ? OR black_name = ?)
                  AND date IS NOT NULL AND date != ''
            ORDER BY date
        ''', (player['name'], player['name'], player['name']))

        elo_history = []
        last_date = None
        for row in cursor.fetchall():
            # Sample every 10th game to reduce data
            if row['elo'] and row['date']:
                if last_date is None or row['date'] != last_date:
                    elo_history.append({
                        'date': row['date'],
                        'elo': row['elo']
                    })
                    last_date = row['date']

        # Limit ELO history to last 100 data points
        if len(elo_history) > 100:
            step = len(elo_history) // 100
            elo_history = elo_history[::step][-100:]

        conn.close()

        return jsonify({
            'name': player['name'],
            'fide_id': player['fide_id'],
            'title': player['title'],
            'highest_elo': player['highest_elo'],
            'latest_elo': player['latest_elo'],
            'total_games': total_games,
            'stats': {
                'wins': wins,
                'losses': losses,
                'draws': draws,
                'win_rate': round(win_rate, 1),
                'draw_rate': round(draw_rate, 1),
                'wins_white': player['wins_white'],
                'wins_black': player['wins_black'],
                'losses_white': player['losses_white'],
                'losses_black': player['losses_black']
            },
            'first_game': player['first_game_date'],
            'last_game': player['last_game_date'],
            'elo_history': elo_history
        })

    except Exception as e:
        logger.error(f"Error getting player profile: {e}")
        return jsonify({'error': str(e)}), 500


@opponent_bp.route('/<player_name>/games', methods=['GET'])
def get_player_games(player_name: str):
    """
    Get filtered games for a player.

    Query params:
        page: Page number (default 1)
        limit: Results per page (default 20, max 100)
        color: 'white', 'black', or 'both' (default 'both')
        result: 'win', 'loss', 'draw', or 'all' (default 'all')
        min_elo: Minimum player ELO
        max_elo: Maximum player ELO
        min_opp_elo: Minimum opponent ELO
        max_opp_elo: Maximum opponent ELO
        eco: ECO code filter (e.g., 'B90')
        from_date: Start date (YYYY.MM.DD)
        to_date: End date (YYYY.MM.DD)
        event: Event name filter

    Returns:
        Paginated list of games with metadata
    """
    if not check_database_exists():
        return jsonify({'error': 'Database not indexed'}), 503

    try:
        # Parse query parameters
        page = max(1, int(request.args.get('page', 1)))
        limit = min(int(request.args.get('limit', 20)), 100)
        offset = (page - 1) * limit

        color = request.args.get('color', 'both')
        result_filter = request.args.get('result', 'all')
        min_elo = request.args.get('min_elo', type=int)
        max_elo = request.args.get('max_elo', type=int)
        min_opp_elo = request.args.get('min_opp_elo', type=int)
        max_opp_elo = request.args.get('max_opp_elo', type=int)
        eco = request.args.get('eco', '').upper()
        from_date = request.args.get('from_date', '')
        to_date = request.args.get('to_date', '')
        event = request.args.get('event', '')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Build query
        conditions = []
        params = []

        # Player name condition
        normalized_name = normalize_name(player_name)

        if color == 'white':
            conditions.append("white_name_normalized = ?")
            params.append(normalized_name)
        elif color == 'black':
            conditions.append("black_name_normalized = ?")
            params.append(normalized_name)
        else:
            conditions.append("(white_name_normalized = ? OR black_name_normalized = ?)")
            params.extend([normalized_name, normalized_name])

        # Result filter
        if result_filter == 'win':
            conditions.append('''
                ((white_name_normalized = ? AND result = '1-0') OR
                 (black_name_normalized = ? AND result = '0-1'))
            ''')
            params.extend([normalized_name, normalized_name])
        elif result_filter == 'loss':
            conditions.append('''
                ((white_name_normalized = ? AND result = '0-1') OR
                 (black_name_normalized = ? AND result = '1-0'))
            ''')
            params.extend([normalized_name, normalized_name])
        elif result_filter == 'draw':
            conditions.append("result = '1/2-1/2'")

        # ELO filters
        if min_elo:
            conditions.append('''
                (CASE WHEN white_name_normalized = ? THEN white_elo ELSE black_elo END) >= ?
            ''')
            params.extend([normalized_name, min_elo])
        if max_elo:
            conditions.append('''
                (CASE WHEN white_name_normalized = ? THEN white_elo ELSE black_elo END) <= ?
            ''')
            params.extend([normalized_name, max_elo])
        if min_opp_elo:
            conditions.append('''
                (CASE WHEN white_name_normalized = ? THEN black_elo ELSE white_elo END) >= ?
            ''')
            params.extend([normalized_name, min_opp_elo])
        if max_opp_elo:
            conditions.append('''
                (CASE WHEN white_name_normalized = ? THEN black_elo ELSE white_elo END) <= ?
            ''')
            params.extend([normalized_name, max_opp_elo])

        # ECO filter
        if eco:
            if len(eco) <= 3:
                conditions.append("eco LIKE ?")
                params.append(f"{eco}%")
            else:
                conditions.append("eco = ?")
                params.append(eco)

        # Date filters
        if from_date:
            conditions.append("date >= ?")
            params.append(from_date)
        if to_date:
            conditions.append("date <= ?")
            params.append(to_date)

        # Event filter
        if event:
            conditions.append("event LIKE ?")
            params.append(f"%{event}%")

        where_clause = " AND ".join(conditions)

        # Get total count
        count_query = f"SELECT COUNT(*) FROM games WHERE {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # Get games
        query = f'''
            SELECT id, white_name, black_name, white_elo, black_elo,
                   white_title, black_title, result, date, eco, opening,
                   variation, event, site, round, pgn_offset, pgn_length
            FROM games
            WHERE {where_clause}
            ORDER BY date DESC
            LIMIT ? OFFSET ?
        '''
        cursor.execute(query, params + [limit, offset])

        games = []
        for row in cursor.fetchall():
            # Determine if player is white or black
            is_white = normalize_name(row['white_name']) == normalized_name

            games.append({
                'id': row['id'],
                'white': {
                    'name': row['white_name'],
                    'elo': row['white_elo'],
                    'title': row['white_title']
                },
                'black': {
                    'name': row['black_name'],
                    'elo': row['black_elo'],
                    'title': row['black_title']
                },
                'result': row['result'],
                'player_color': 'white' if is_white else 'black',
                'player_result': get_player_result(row['result'], is_white),
                'date': row['date'],
                'eco': row['eco'],
                'opening': row['opening'],
                'variation': row['variation'],
                'event': row['event'],
                'site': row['site'],
                'round': row['round']
            })

        conn.close()

        total_pages = (total + limit - 1) // limit

        return jsonify({
            'games': games,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        })

    except Exception as e:
        logger.error(f"Error getting player games: {e}")
        return jsonify({'error': str(e)}), 500


def get_player_result(result: str, is_white: bool) -> str:
    """Convert game result to player perspective."""
    if result == '1-0':
        return 'win' if is_white else 'loss'
    elif result == '0-1':
        return 'loss' if is_white else 'win'
    elif result == '1/2-1/2':
        return 'draw'
    return 'unknown'


@opponent_bp.route('/<player_name>/openings', methods=['GET'])
def get_player_openings(player_name: str):
    """
    Get opening statistics for a player.

    Query params:
        color: 'white', 'black', or 'both' (default 'both')
        min_games: Minimum games for opening to be included (default 5)
        limit: Max openings to return (default 50)

    Returns:
        List of openings with win/draw/loss statistics
    """
    if not check_database_exists():
        return jsonify({'error': 'Database not indexed'}), 503

    try:
        color = request.args.get('color', 'both')
        min_games = int(request.args.get('min_games', 5))
        limit = min(int(request.args.get('limit', 50)), 200)

        conn = get_db_connection()
        cursor = conn.cursor()

        normalized_name = normalize_name(player_name)

        # Build color condition
        if color == 'white':
            color_condition = "white_name_normalized = ?"
            win_result = "'1-0'"
            loss_result = "'0-1'"
        elif color == 'black':
            color_condition = "black_name_normalized = ?"
            win_result = "'0-1'"
            loss_result = "'1-0'"
        else:
            color_condition = "(white_name_normalized = ? OR black_name_normalized = ?)"
            # For 'both', we need a more complex query
            win_result = None
            loss_result = None

        if color in ('white', 'black'):
            cursor.execute(f'''
                SELECT eco, opening,
                       COUNT(*) as games,
                       SUM(CASE WHEN result = {win_result} THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN result = {loss_result} THEN 1 ELSE 0 END) as losses,
                       SUM(CASE WHEN result = '1/2-1/2' THEN 1 ELSE 0 END) as draws
                FROM games
                WHERE {color_condition} AND eco IS NOT NULL AND eco != ''
                GROUP BY eco, opening
                HAVING COUNT(*) >= ?
                ORDER BY games DESC
                LIMIT ?
            ''', (normalized_name, min_games, limit))
        else:
            # Combined query for both colors
            cursor.execute('''
                SELECT eco, opening,
                       COUNT(*) as games,
                       SUM(CASE
                           WHEN (white_name_normalized = ? AND result = '1-0') OR
                                (black_name_normalized = ? AND result = '0-1')
                           THEN 1 ELSE 0 END) as wins,
                       SUM(CASE
                           WHEN (white_name_normalized = ? AND result = '0-1') OR
                                (black_name_normalized = ? AND result = '1-0')
                           THEN 1 ELSE 0 END) as losses,
                       SUM(CASE WHEN result = '1/2-1/2' THEN 1 ELSE 0 END) as draws
                FROM games
                WHERE (white_name_normalized = ? OR black_name_normalized = ?)
                      AND eco IS NOT NULL AND eco != ''
                GROUP BY eco, opening
                HAVING COUNT(*) >= ?
                ORDER BY games DESC
                LIMIT ?
            ''', (normalized_name, normalized_name, normalized_name, normalized_name,
                  normalized_name, normalized_name, min_games, limit))

        openings = []
        for row in cursor.fetchall():
            total = row['games']
            win_rate = (row['wins'] / total * 100) if total > 0 else 0

            openings.append({
                'eco': row['eco'],
                'opening': row['opening'] or 'Unknown',
                'games': total,
                'wins': row['wins'],
                'draws': row['draws'],
                'losses': row['losses'],
                'win_rate': round(win_rate, 1),
                'draw_rate': round((row['draws'] / total * 100) if total > 0 else 0, 1)
            })

        conn.close()

        return jsonify({
            'player': player_name,
            'color': color,
            'openings': openings
        })

    except Exception as e:
        logger.error(f"Error getting player openings: {e}")
        return jsonify({'error': str(e)}), 500


@opponent_bp.route('/<player_name>/opponents', methods=['GET'])
def get_player_opponents(player_name: str):
    """
    Get most frequent opponents for a player.

    Query params:
        limit: Max opponents to return (default 20)

    Returns:
        List of opponents with game statistics
    """
    if not check_database_exists():
        return jsonify({'error': 'Database not indexed'}), 503

    try:
        limit = min(int(request.args.get('limit', 20)), 100)

        conn = get_db_connection()
        cursor = conn.cursor()

        normalized_name = normalize_name(player_name)

        cursor.execute('''
            SELECT
                CASE
                    WHEN white_name_normalized = ? THEN black_name
                    ELSE white_name
                END as opponent_name,
                COUNT(*) as games,
                SUM(CASE
                    WHEN (white_name_normalized = ? AND result = '1-0') OR
                         (black_name_normalized = ? AND result = '0-1')
                    THEN 1 ELSE 0 END) as wins,
                SUM(CASE
                    WHEN (white_name_normalized = ? AND result = '0-1') OR
                         (black_name_normalized = ? AND result = '1-0')
                    THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = '1/2-1/2' THEN 1 ELSE 0 END) as draws
            FROM games
            WHERE white_name_normalized = ? OR black_name_normalized = ?
            GROUP BY opponent_name
            ORDER BY games DESC
            LIMIT ?
        ''', (normalized_name, normalized_name, normalized_name,
              normalized_name, normalized_name, normalized_name, normalized_name, limit))

        opponents = []
        for row in cursor.fetchall():
            total = row['games']
            win_rate = (row['wins'] / total * 100) if total > 0 else 0

            opponents.append({
                'name': row['opponent_name'],
                'games': total,
                'wins': row['wins'],
                'draws': row['draws'],
                'losses': row['losses'],
                'win_rate': round(win_rate, 1)
            })

        conn.close()

        return jsonify({
            'player': player_name,
            'opponents': opponents
        })

    except Exception as e:
        logger.error(f"Error getting player opponents: {e}")
        return jsonify({'error': str(e)}), 500


@opponent_bp.route('/game/<int:game_id>/pgn', methods=['GET'])
def get_game_pgn(game_id: int):
    """
    Get full PGN for a specific game.

    Returns:
        PGN text for the game
    """
    if not check_database_exists():
        return jsonify({'error': 'Database not indexed'}), 503

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT pgn_offset, pgn_length FROM games WHERE id = ?
        ''', (game_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'error': 'Game not found'}), 404

        # Read PGN from file using offset
        with open(PGN_PATH, 'rb') as f:
            f.seek(row['pgn_offset'])
            pgn_bytes = f.read(row['pgn_length'])
            try:
                pgn = pgn_bytes.decode('utf-8')
            except UnicodeDecodeError:
                pgn = pgn_bytes.decode('latin-1')

        return jsonify({
            'id': game_id,
            'pgn': pgn.strip()
        })

    except Exception as e:
        logger.error(f"Error getting game PGN: {e}")
        return jsonify({'error': str(e)}), 500
