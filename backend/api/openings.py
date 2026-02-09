"""
Opening Repertoire API - Debut Feature
Endpoints for managing user's opening repertoires, move trees, game search, and training.

Blueprint: /api/openings
"""

import os
import json
import sqlite3
import logging
import time
import uuid
import math
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, List, Dict, Any, Tuple

import chess
import chess.pgn
import io
import requests

from flask import Blueprint, request, jsonify, Response, stream_with_context
from services.supabase_client import supabase
from utils.auth import verify_clerk_token, get_current_user_id

logger = logging.getLogger(__name__)

openings_bp = Blueprint('openings', __name__, url_prefix='/api/openings')

# Paths for TWIC database
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TWIC_DB_PATH = os.path.join(BACKEND_DIR, "data/twic/games_index.db")
TWIC_PGN_PATH = os.path.join(BACKEND_DIR, "data/twic/twic_master_database.pgn")

STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'


# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────

def build_tree(nodes: list) -> dict:
    """Build nested tree from flat node list. Returns root node with 'children' arrays."""
    node_map = {}
    root = None

    for n in nodes:
        n['children'] = []
        node_map[n['id']] = n

    for n in nodes:
        parent_id = n.get('parent_id')
        if parent_id and parent_id in node_map:
            node_map[parent_id]['children'].append(n)
        elif not parent_id or parent_id not in node_map:
            if n.get('move_san') is None:
                root = n

    # If no explicit root found, pick the first node without a parent
    if root is None:
        for n in nodes:
            if n.get('parent_id') is None:
                root = n
                break

    return root


def detect_opening(fen: str) -> Optional[Dict]:
    """Query Lichess masters DB for opening name. Returns {'name': ..., 'eco': ...} or None."""
    try:
        resp = requests.get(
            'https://explorer.lichess.ovh/masters',
            params={'fen': fen},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            opening = data.get('opening')
            if opening:
                return {'name': opening.get('name', ''), 'eco': opening.get('eco', '')}
    except Exception as e:
        logger.debug(f"Opening detection failed for {fen}: {e}")
    return None


def detect_eco_for_search(fen: str) -> Tuple[Optional[str], Optional[str]]:
    """Get (eco_code, eco_name) for FEN from Lichess Explorer. Used for DB pre-filtering."""
    info = detect_opening(fen)
    if info:
        return info.get('eco'), info.get('name')
    return None, None


def validate_move(fen: str, move_san: str) -> Tuple[str, str, bool]:
    """Validate move is legal. Returns (new_fen, move_uci, is_white_move). Raises ValueError."""
    board = chess.Board(fen)
    try:
        move = board.parse_san(move_san)
    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as e:
        raise ValueError(f"Invalid move '{move_san}': {e}")

    is_white_move = board.turn == chess.WHITE
    board.push(move)
    return board.fen(), move.uci(), is_white_move


def create_default_repertoires(user_id: str) -> list:
    """Auto-create 'White Repertoire' and 'Black Repertoire' for new users."""
    defaults = [
        {'name': 'White Repertoire', 'color': 'w'},
        {'name': 'Black Repertoire', 'color': 'b'},
    ]
    created = []
    for d in defaults:
        rep_id = str(uuid.uuid4())
        rep = supabase.table('opening_repertoires').insert({
            'id': rep_id,
            'user_id': user_id,
            'name': d['name'],
            'color': d['color'],
            'is_primary': True,
        }).execute()

        # Create root node
        supabase.table('opening_nodes').insert({
            'id': str(uuid.uuid4()),
            'repertoire_id': rep_id,
            'parent_id': None,
            'fen': STARTING_FEN,
            'move_san': None,
            'move_number': 0,
            'is_white_move': None,
        }).execute()

        if rep.data:
            created.append(rep.data[0])
    return created


def build_pgn_moves(tree: dict, include_notes: bool) -> str:
    """Recursively build PGN notation from tree (with variations)."""

    def traverse(node, is_main=True, force_move_number=False):
        parts = []
        move_san = node.get('move_san')
        if move_san:
            move_num = node.get('move_number', 0)
            is_white = node.get('is_white_move', True)

            if is_white:
                parts.append(f"{move_num}. {move_san}")
            elif force_move_number or not is_main:
                parts.append(f"{move_num}... {move_san}")
            else:
                parts.append(move_san)

            if include_notes and node.get('notes'):
                parts.append(f"{{{node['notes']}}}")

        children = node.get('children', [])
        if children:
            # First child is main line
            main_child = children[0]
            main_text = traverse(main_child, is_main=True, force_move_number=False)
            parts.append(main_text)

            # Remaining children are variations
            for alt in children[1:]:
                var_text = traverse(alt, is_main=False, force_move_number=True)
                parts.append(f"({var_text})")

        return ' '.join(parts)

    return traverse(tree)


def generate_repertoire_pgn(repertoire, tree, eco_info, include_notes) -> str:
    """Generate complete PGN with headers for export."""
    headers = []
    headers.append(f'[Event "Opening Repertoire: {repertoire["name"]}"]')
    headers.append(f'[Site "Chesster"]')
    headers.append(f'[Date "{datetime.now().strftime("%Y.%m.%d")}"]')
    if repertoire['color'] == 'w':
        headers.append('[White "Repertoire"]')
        headers.append('[Black "Opponent"]')
    else:
        headers.append('[White "Opponent"]')
        headers.append('[Black "Repertoire"]')
    headers.append('[Result "*"]')

    if eco_info:
        eco_code, eco_name = eco_info
        if eco_code:
            headers.append(f'[ECO "{eco_code}"]')
        if eco_name:
            headers.append(f'[Opening "{eco_name}"]')

    moves = build_pgn_moves(tree, include_notes)
    return '\n'.join(headers) + '\n\n' + moves + ' *\n'


def check_game_reaches_fen(pgn_text: str, target_fen: str, debug_game_id: str = '') -> bool:
    """Check if a game passes through a specific FEN position."""
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
        if not game:
            return False

        # Normalize target FEN (ignore move counters)
        target_parts = target_fen.split(' ')
        target_board = ' '.join(target_parts[:4])  # position + castling + en passant

        board = game.board()
        board_fen = board.fen().split(' ')
        if ' '.join(board_fen[:4]) == target_board:
            return True

        for move in game.mainline_moves():
            board.push(move)
            board_fen = board.fen().split(' ')
            if ' '.join(board_fen[:4]) == target_board:
                return True

        return False
    except Exception as e:
        logger.debug(f"Error checking game {debug_game_id}: {e}")
        return False


def find_moves_to_fen(target_fen: str, max_depth: int = 30) -> List[str]:
    """BFS through Lichess opening book to find move sequence to target FEN."""
    try:
        target_parts = target_fen.split(' ')
        target_board = ' '.join(target_parts[:4])

        board = chess.Board()
        queue = [(board.copy(), [])]
        visited = set()

        for _ in range(max_depth):
            if not queue:
                break
            current_board, moves = queue.pop(0)

            current_fen_key = ' '.join(current_board.fen().split(' ')[:4])
            if current_fen_key in visited:
                continue
            visited.add(current_fen_key)

            if current_fen_key == target_board:
                return moves

            # Query Lichess for top moves
            try:
                resp = requests.get(
                    'https://explorer.lichess.ovh/masters',
                    params={'fen': current_board.fen()},
                    timeout=3
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get('moves', [])[:5]:  # Top 5 moves
                        try:
                            move = current_board.parse_san(m['san'])
                            new_board = current_board.copy()
                            new_board.push(move)
                            queue.append((new_board, moves + [m['san']]))
                        except Exception:
                            pass
            except Exception:
                pass

        return []
    except Exception as e:
        logger.error(f"Error finding moves to FEN: {e}")
        return []


# ─────────────────────────────────────────────
# TWIC / Internal database helpers
# ─────────────────────────────────────────────

def get_internal_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(TWIC_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def check_internal_db_exists() -> bool:
    return os.path.exists(TWIC_DB_PATH)


def fetch_internal_games(search_query: str, max_games: int, filter_fen: str = None, eco_filter: str = None) -> list:
    """Fetch games from TWIC database, optionally filtering by FEN position."""
    if not check_internal_db_exists():
        return []

    conn = get_internal_db_connection()
    cursor = conn.cursor()

    try:
        query = "SELECT * FROM games"
        params = []
        conditions = []

        if eco_filter:
            conditions.append("eco LIKE ?")
            params.append(f"{eco_filter}%")

        if search_query:
            conditions.append("(white LIKE ? OR black LIKE ? OR event LIKE ?)")
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY date DESC LIMIT ?"
        params.append(max_games * 3 if filter_fen else max_games)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            game_data = dict(row)
            if filter_fen and game_data.get('pgn_offset') is not None:
                # Read PGN from master file
                try:
                    with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
                        f.seek(game_data['pgn_offset'])
                        pgn_text = ''
                        for line in f:
                            pgn_text += line
                            if line.strip() in ['1-0', '0-1', '1/2-1/2', '*'] and len(pgn_text) > 50:
                                break

                        if check_game_reaches_fen(pgn_text, filter_fen, str(game_data.get('id', ''))):
                            game_data['pgn'] = pgn_text
                            results.append(game_data)
                except Exception as e:
                    logger.debug(f"Error reading PGN: {e}")
            else:
                results.append(game_data)

            if len(results) >= max_games:
                break

        conn.close()
        return results
    except Exception as e:
        logger.error(f"Error fetching internal games: {e}")
        conn.close()
        return []


def _has_position_index(conn) -> bool:
    """Check if game_positions hash table exists."""
    result = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='game_positions'"
    ).fetchone()
    return result is not None


def _get_board_hash(fen: str) -> str:
    """Convert a full FEN to board hash (pieces + side + castling + ep)."""
    parts = fen.split(' ')
    return ' '.join(parts[:4])


def fetch_internal_games_progressive(filter_fen: str, eco_filter: str = None,
                                      min_rating: int = 0, max_games: int = 10,
                                      stop_after: int = 500):
    """Generator: yield games progressively from TWIC DB that reach a given FEN."""
    if not check_internal_db_exists():
        return

    conn = get_internal_db_connection()
    cursor = conn.cursor()

    try:
        # FAST PATH: Use position hash index if available
        if filter_fen and _has_position_index(conn):
            board_hash = _get_board_hash(filter_fen)
            logger.info(f"Using position hash index for: {board_hash[:40]}...")

            query = """
                SELECT DISTINCT g.* FROM games g
                INNER JOIN game_positions gp ON g.id = gp.game_id
                WHERE gp.board_hash = ?
            """
            params = [board_hash]

            if min_rating > 0:
                query += " AND (g.white_elo >= ? OR g.black_elo >= ?)"
                params.extend([min_rating, min_rating])

            if eco_filter:
                query += " AND g.eco LIKE ?"
                params.append(f"{eco_filter}%")

            query += " ORDER BY g.date DESC LIMIT ?"
            params.append(max_games)

            cursor.execute(query, params)
            found = 0
            for row in cursor.fetchall():
                game_data = dict(row)
                # Load PGN
                if game_data.get('pgn_offset') is not None:
                    try:
                        with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
                            f.seek(game_data['pgn_offset'])
                            pgn_text = ''
                            for line in f:
                                pgn_text += line
                                if line.strip() in ['1-0', '0-1', '1/2-1/2', '*'] and len(pgn_text) > 50:
                                    break
                            game_data['pgn'] = pgn_text
                    except Exception:
                        pass
                found += 1
                yield {'type': 'game', 'game': game_data, 'checked': found, 'found': found}

            conn.close()
            yield {'type': 'done', 'checked': found, 'found': found}
            return

        # SLOW PATH: Scan games and replay PGN to check position
        query = "SELECT * FROM games"
        params = []
        conditions = []

        if eco_filter:
            conditions.append("eco LIKE ?")
            params.append(f"{eco_filter}%")

        if min_rating > 0:
            conditions.append("(white_elo >= ? OR black_elo >= ?)")
            params.extend([min_rating, min_rating])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY date DESC LIMIT ?"
        params.append(stop_after)

        cursor.execute(query, params)

        found = 0
        checked = 0
        for row in cursor.fetchall():
            checked += 1
            game_data = dict(row)

            if filter_fen and game_data.get('pgn_offset') is not None:
                try:
                    with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
                        f.seek(game_data['pgn_offset'])
                        pgn_text = ''
                        for line in f:
                            pgn_text += line
                            if line.strip() in ['1-0', '0-1', '1/2-1/2', '*'] and len(pgn_text) > 50:
                                break

                        if check_game_reaches_fen(pgn_text, filter_fen):
                            game_data['pgn'] = pgn_text
                            found += 1
                            yield {'type': 'game', 'game': game_data, 'checked': checked, 'found': found}
                except Exception:
                    pass
            elif not filter_fen:
                found += 1
                yield {'type': 'game', 'game': game_data, 'checked': checked, 'found': found}

            if found >= max_games:
                break

            if checked % 50 == 0:
                yield {'type': 'progress', 'checked': checked, 'found': found}

        conn.close()
        yield {'type': 'done', 'checked': checked, 'found': found}
    except Exception as e:
        logger.error(f"Error in progressive internal search: {e}")
        conn.close()
        yield {'type': 'error', 'message': str(e)}


def fetch_lichess_games(username: str, since: str = None, max_games: int = 10, filter_fen: str = None) -> list:
    """Fetch games from Lichess API for a user."""
    try:
        headers = {'Accept': 'application/x-ndjson'}
        params = {'max': max_games * 3 if filter_fen else max_games, 'opening': 'true'}
        if since:
            params['since'] = since

        resp = requests.get(
            f'https://lichess.org/api/games/user/{username}',
            headers=headers, params=params, timeout=30
        )

        if resp.status_code != 200:
            return []

        results = []
        for line in resp.text.strip().split('\n'):
            if not line.strip():
                continue
            try:
                game = json.loads(line)
                game_data = {
                    'id': game.get('id'),
                    'source': 'lichess',
                    'white': game.get('players', {}).get('white', {}).get('user', {}).get('name', '?'),
                    'black': game.get('players', {}).get('black', {}).get('user', {}).get('name', '?'),
                    'white_elo': game.get('players', {}).get('white', {}).get('rating'),
                    'black_elo': game.get('players', {}).get('black', {}).get('rating'),
                    'result': game.get('winner', 'draw'),
                    'date': game.get('createdAt', ''),
                    'eco': game.get('opening', {}).get('eco', ''),
                    'opening': game.get('opening', {}).get('name', ''),
                    'pgn': game.get('pgn', ''),
                    'url': f"https://lichess.org/{game.get('id')}",
                }

                if filter_fen and game_data.get('pgn'):
                    if check_game_reaches_fen(game_data['pgn'], filter_fen):
                        results.append(game_data)
                else:
                    results.append(game_data)

                if len(results) >= max_games:
                    break
            except json.JSONDecodeError:
                pass

        return results
    except Exception as e:
        logger.error(f"Lichess fetch error: {e}")
        return []


def fetch_lichess_games_progressive(username: str, filter_fen: str = None,
                                     min_rating: int = 0, max_games: int = 10):
    """Generator: yield Lichess games progressively."""
    try:
        headers = {'Accept': 'application/x-ndjson'}
        params = {'max': 200, 'opening': 'true', 'pgnInJson': 'true'}

        resp = requests.get(
            f'https://lichess.org/api/games/user/{username}',
            headers=headers, params=params, timeout=30, stream=True
        )

        if resp.status_code != 200:
            yield {'type': 'error', 'message': f'Lichess API returned {resp.status_code}'}
            return

        found = 0
        checked = 0
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.strip():
                continue
            try:
                game = json.loads(line)
                checked += 1

                game_data = {
                    'id': game.get('id'),
                    'source': 'lichess',
                    'white': game.get('players', {}).get('white', {}).get('user', {}).get('name', '?'),
                    'black': game.get('players', {}).get('black', {}).get('user', {}).get('name', '?'),
                    'white_elo': game.get('players', {}).get('white', {}).get('rating'),
                    'black_elo': game.get('players', {}).get('black', {}).get('rating'),
                    'result': game.get('winner', 'draw'),
                    'date': game.get('createdAt', ''),
                    'eco': game.get('opening', {}).get('eco', ''),
                    'opening': game.get('opening', {}).get('name', ''),
                    'pgn': game.get('pgn', ''),
                    'url': f"https://lichess.org/{game.get('id')}",
                }

                # Filter by rating
                w_elo = game_data.get('white_elo') or 0
                b_elo = game_data.get('black_elo') or 0
                if min_rating > 0 and max(w_elo, b_elo) < min_rating:
                    if checked % 20 == 0:
                        yield {'type': 'progress', 'checked': checked, 'found': found}
                    continue

                if filter_fen and game_data.get('pgn'):
                    if check_game_reaches_fen(game_data['pgn'], filter_fen):
                        found += 1
                        yield {'type': 'game', 'game': game_data, 'checked': checked, 'found': found}
                elif not filter_fen:
                    found += 1
                    yield {'type': 'game', 'game': game_data, 'checked': checked, 'found': found}

                if found >= max_games:
                    break

                if checked % 20 == 0:
                    yield {'type': 'progress', 'checked': checked, 'found': found}

            except json.JSONDecodeError:
                pass

        yield {'type': 'done', 'checked': checked, 'found': found}
    except Exception as e:
        logger.error(f"Lichess progressive error: {e}")
        yield {'type': 'error', 'message': str(e)}


def fetch_chesscom_games(username: str, since: str = None, max_games: int = 10, filter_fen: str = None) -> list:
    """Fetch games from Chess.com API for a user."""
    try:
        # Get archives list
        resp = requests.get(
            f'https://api.chess.com/pub/player/{username}/games/archives',
            timeout=10
        )
        if resp.status_code != 200:
            return []

        archives = resp.json().get('archives', [])
        archives.reverse()  # Most recent first

        results = []
        for archive_url in archives[:3]:  # Last 3 months
            try:
                arch_resp = requests.get(archive_url, timeout=10)
                if arch_resp.status_code != 200:
                    continue

                games = arch_resp.json().get('games', [])
                games.reverse()

                for g in games:
                    game_data = {
                        'id': g.get('url', '').split('/')[-1],
                        'source': 'chesscom',
                        'white': g.get('white', {}).get('username', '?'),
                        'black': g.get('black', {}).get('username', '?'),
                        'white_elo': g.get('white', {}).get('rating'),
                        'black_elo': g.get('black', {}).get('rating'),
                        'result': g.get('white', {}).get('result', ''),
                        'date': g.get('end_time', ''),
                        'eco': g.get('eco', '').split('/')[-1] if g.get('eco') else '',
                        'opening': '',
                        'pgn': g.get('pgn', ''),
                        'url': g.get('url', ''),
                    }

                    if filter_fen and game_data.get('pgn'):
                        if check_game_reaches_fen(game_data['pgn'], filter_fen):
                            results.append(game_data)
                    else:
                        results.append(game_data)

                    if len(results) >= max_games:
                        break

            except Exception as e:
                logger.debug(f"Chess.com archive error: {e}")

            if len(results) >= max_games:
                break

        return results
    except Exception as e:
        logger.error(f"Chess.com fetch error: {e}")
        return []


def fetch_chesscom_games_progressive(username: str, filter_fen: str = None,
                                      min_rating: int = 0, max_games: int = 10):
    """Generator: yield Chess.com games progressively."""
    try:
        resp = requests.get(
            f'https://api.chess.com/pub/player/{username}/games/archives',
            timeout=10
        )
        if resp.status_code != 200:
            yield {'type': 'error', 'message': f'Chess.com API returned {resp.status_code}'}
            return

        archives = resp.json().get('archives', [])
        archives.reverse()

        found = 0
        checked = 0
        for archive_url in archives[:6]:
            try:
                arch_resp = requests.get(archive_url, timeout=10)
                if arch_resp.status_code != 200:
                    continue

                games = arch_resp.json().get('games', [])
                games.reverse()

                for g in games:
                    checked += 1
                    game_data = {
                        'id': g.get('url', '').split('/')[-1],
                        'source': 'chesscom',
                        'white': g.get('white', {}).get('username', '?'),
                        'black': g.get('black', {}).get('username', '?'),
                        'white_elo': g.get('white', {}).get('rating'),
                        'black_elo': g.get('black', {}).get('rating'),
                        'result': g.get('white', {}).get('result', ''),
                        'date': g.get('end_time', ''),
                        'eco': g.get('eco', '').split('/')[-1] if g.get('eco') else '',
                        'pgn': g.get('pgn', ''),
                        'url': g.get('url', ''),
                    }

                    w_elo = game_data.get('white_elo') or 0
                    b_elo = game_data.get('black_elo') or 0
                    if min_rating > 0 and max(w_elo, b_elo) < min_rating:
                        if checked % 20 == 0:
                            yield {'type': 'progress', 'checked': checked, 'found': found}
                        continue

                    if filter_fen and game_data.get('pgn'):
                        if check_game_reaches_fen(game_data['pgn'], filter_fen):
                            found += 1
                            yield {'type': 'game', 'game': game_data, 'checked': checked, 'found': found}
                    elif not filter_fen:
                        found += 1
                        yield {'type': 'game', 'game': game_data, 'checked': checked, 'found': found}

                    if found >= max_games:
                        break

                    if checked % 20 == 0:
                        yield {'type': 'progress', 'checked': checked, 'found': found}

            except Exception as e:
                logger.debug(f"Chess.com archive progressive error: {e}")

            if found >= max_games:
                break

        yield {'type': 'done', 'checked': checked, 'found': found}
    except Exception as e:
        logger.error(f"Chess.com progressive error: {e}")
        yield {'type': 'error', 'message': str(e)}


# ─────────────────────────────────────────────
# Repertoire CRUD endpoints
# ─────────────────────────────────────────────

@openings_bp.route('/repertoires', methods=['GET'])
@verify_clerk_token
def list_repertoires():
    """List user's repertoires, auto-creating defaults for new users."""
    user_id = get_current_user_id()

    try:
        result = supabase.table('opening_repertoires') \
            .select('*') \
            .eq('user_id', user_id) \
            .order('created_at') \
            .execute()

        repertoires = result.data or []

        if not repertoires:
            repertoires = create_default_repertoires(user_id)

        # Count nodes per repertoire
        for rep in repertoires:
            count_result = supabase.table('opening_nodes') \
                .select('id', count='exact') \
                .eq('repertoire_id', rep['id']) \
                .execute()
            rep['node_count'] = count_result.count if count_result.count is not None else 0

        return jsonify({'repertoires': repertoires})
    except Exception as e:
        logger.error(f"Error listing repertoires: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/repertoires', methods=['POST'])
@verify_clerk_token
def create_repertoire():
    """Create a new repertoire."""
    user_id = get_current_user_id()
    data = request.get_json()

    name = data.get('name', 'New Repertoire')
    color = data.get('color', 'w')
    description = data.get('description')
    starting_fen = data.get('startingFen')
    starting_move_line = data.get('startingMoveLine')

    if color not in ('w', 'b'):
        return jsonify({'error': 'Color must be "w" or "b"'}), 400

    try:
        rep_id = str(uuid.uuid4())
        rep_result = supabase.table('opening_repertoires').insert({
            'id': rep_id,
            'user_id': user_id,
            'name': name,
            'color': color,
            'description': description,
            'starting_fen': starting_fen,
            'starting_move_line': starting_move_line,
        }).execute()

        # Create root node
        root_fen = starting_fen or STARTING_FEN
        root_id = str(uuid.uuid4())
        root_result = supabase.table('opening_nodes').insert({
            'id': root_id,
            'repertoire_id': rep_id,
            'parent_id': None,
            'fen': root_fen,
            'move_san': None,
            'move_number': 0,
            'is_white_move': None,
        }).execute()

        return jsonify({
            'repertoire': rep_result.data[0] if rep_result.data else None,
            'root_node': root_result.data[0] if root_result.data else None,
        }), 201
    except Exception as e:
        logger.error(f"Error creating repertoire: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/repertoires/<repertoire_id>', methods=['GET'])
@verify_clerk_token
def get_repertoire(repertoire_id):
    """Get repertoire with full tree."""
    user_id = get_current_user_id()

    try:
        rep_result = supabase.table('opening_repertoires') \
            .select('*') \
            .eq('id', repertoire_id) \
            .eq('user_id', user_id) \
            .execute()

        if not rep_result.data:
            return jsonify({'error': 'Repertoire not found'}), 404

        repertoire = rep_result.data[0]

        # Get all nodes
        nodes_result = supabase.table('opening_nodes') \
            .select('*') \
            .eq('repertoire_id', repertoire_id) \
            .order('created_at') \
            .execute()

        nodes = nodes_result.data or []

        # Get arrows for all nodes
        node_ids = [n['id'] for n in nodes]
        arrows = []
        if node_ids:
            arrows_result = supabase.table('opening_arrows') \
                .select('*') \
                .in_('node_id', node_ids) \
                .execute()
            arrows = arrows_result.data or []

        # Attach arrows to nodes
        arrow_map = {}
        for a in arrows:
            arrow_map.setdefault(a['node_id'], []).append(a)

        for n in nodes:
            n['arrows'] = arrow_map.get(n['id'], [])

        tree = build_tree(nodes)

        return jsonify({
            'repertoire': repertoire,
            'tree': tree,
        })
    except Exception as e:
        logger.error(f"Error getting repertoire: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/repertoires/<repertoire_id>', methods=['PUT'])
@verify_clerk_token
def update_repertoire(repertoire_id):
    """Update repertoire metadata."""
    user_id = get_current_user_id()
    data = request.get_json()

    try:
        # Verify ownership
        check = supabase.table('opening_repertoires') \
            .select('id') \
            .eq('id', repertoire_id) \
            .eq('user_id', user_id) \
            .execute()

        if not check.data:
            return jsonify({'error': 'Repertoire not found'}), 404

        update_data = {}
        for key in ['name', 'description', 'startingFen', 'startingMoveLine']:
            camel_to_snake = {
                'name': 'name',
                'description': 'description',
                'startingFen': 'starting_fen',
                'startingMoveLine': 'starting_move_line',
            }
            if key in data:
                update_data[camel_to_snake[key]] = data[key]

        update_data['updated_at'] = datetime.utcnow().isoformat()

        result = supabase.table('opening_repertoires') \
            .update(update_data) \
            .eq('id', repertoire_id) \
            .execute()

        return jsonify({'repertoire': result.data[0] if result.data else None})
    except Exception as e:
        logger.error(f"Error updating repertoire: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/repertoires/<repertoire_id>/starting-position', methods=['PUT'])
@verify_clerk_token
def update_starting_position(repertoire_id):
    """Set starting FEN + optionally create move line nodes."""
    user_id = get_current_user_id()
    data = request.get_json()
    new_fen = data.get('fen', STARTING_FEN)
    move_line = data.get('moveLine')

    try:
        check = supabase.table('opening_repertoires') \
            .select('id') \
            .eq('id', repertoire_id) \
            .eq('user_id', user_id) \
            .execute()

        if not check.data:
            return jsonify({'error': 'Repertoire not found'}), 404

        supabase.table('opening_repertoires') \
            .update({
                'starting_fen': new_fen,
                'starting_move_line': move_line,
                'updated_at': datetime.utcnow().isoformat(),
            }) \
            .eq('id', repertoire_id) \
            .execute()

        # Update root node FEN
        root = supabase.table('opening_nodes') \
            .select('id') \
            .eq('repertoire_id', repertoire_id) \
            .is_('parent_id', 'null') \
            .execute()

        if root.data:
            supabase.table('opening_nodes') \
                .update({'fen': new_fen}) \
                .eq('id', root.data[0]['id']) \
                .execute()

        result = supabase.table('opening_repertoires') \
            .select('*') \
            .eq('id', repertoire_id) \
            .execute()

        return jsonify({'repertoire': result.data[0] if result.data else None})
    except Exception as e:
        logger.error(f"Error updating starting position: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/repertoires/<repertoire_id>', methods=['DELETE'])
@verify_clerk_token
def delete_repertoire(repertoire_id):
    """Delete repertoire and all its nodes (cascade)."""
    user_id = get_current_user_id()

    try:
        check = supabase.table('opening_repertoires') \
            .select('id') \
            .eq('id', repertoire_id) \
            .eq('user_id', user_id) \
            .execute()

        if not check.data:
            return jsonify({'error': 'Repertoire not found'}), 404

        supabase.table('opening_repertoires') \
            .delete() \
            .eq('id', repertoire_id) \
            .execute()

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting repertoire: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/repertoires/<repertoire_id>/pgn', methods=['GET'])
@verify_clerk_token
def export_repertoire_pgn(repertoire_id):
    """Export repertoire as PGN."""
    user_id = get_current_user_id()
    include_notes = request.args.get('include_notes', 'true').lower() == 'true'

    try:
        rep_result = supabase.table('opening_repertoires') \
            .select('*') \
            .eq('id', repertoire_id) \
            .eq('user_id', user_id) \
            .execute()

        if not rep_result.data:
            return jsonify({'error': 'Repertoire not found'}), 404

        repertoire = rep_result.data[0]

        nodes_result = supabase.table('opening_nodes') \
            .select('*') \
            .eq('repertoire_id', repertoire_id) \
            .order('created_at') \
            .execute()

        nodes = nodes_result.data or []
        tree = build_tree(nodes)

        # Detect ECO
        root_fen = repertoire.get('starting_fen') or STARTING_FEN
        eco_info = detect_eco_for_search(root_fen) if root_fen != STARTING_FEN else (None, None)

        pgn = generate_repertoire_pgn(repertoire, tree, eco_info, include_notes)

        return Response(
            pgn,
            mimetype='application/x-chess-pgn',
            headers={'Content-Disposition': f'attachment; filename="{repertoire["name"]}.pgn"'}
        )
    except Exception as e:
        logger.error(f"Error exporting PGN: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/repertoires/<repertoire_id>/import', methods=['POST'])
@verify_clerk_token
def import_pgn(repertoire_id):
    """Import PGN with variations into repertoire."""
    user_id = get_current_user_id()
    data = request.get_json()

    pgn_text = data.get('pgn', '')
    max_ply = min(int(data.get('maxPly', 30)), 100)

    if not pgn_text.strip():
        return jsonify({'error': 'No PGN provided'}), 400

    try:
        # Verify ownership
        rep_check = supabase.table('opening_repertoires') \
            .select('*') \
            .eq('id', repertoire_id) \
            .eq('user_id', user_id) \
            .execute()

        if not rep_check.data:
            return jsonify({'error': 'Repertoire not found'}), 404

        # Get existing nodes for deduplication
        existing = supabase.table('opening_nodes') \
            .select('id, parent_id, fen, move_san') \
            .eq('repertoire_id', repertoire_id) \
            .execute()

        existing_nodes = existing.data or []
        # Build lookup: (parent_id, move_san) -> node
        existing_map = {}
        fen_to_node = {}
        for n in existing_nodes:
            key = (n.get('parent_id'), n.get('move_san'))
            existing_map[key] = n
            fen_to_node[n['fen']] = n

        # Find root node
        root = None
        for n in existing_nodes:
            if n.get('move_san') is None and n.get('parent_id') is None:
                root = n
                break

        if not root:
            return jsonify({'error': 'No root node found. Please recreate the repertoire.'}), 400

        imported = 0
        skipped = 0
        errors = []
        sample_nodes = []

        # Parse PGN (may contain multiple games)
        pgn_io = io.StringIO(pgn_text)

        game_num = 0
        while True:
            game = chess.pgn.read_game(pgn_io)
            if game is None:
                break
            game_num += 1

            def import_variation(node, parent_db_node, ply_count):
                nonlocal imported, skipped, errors, sample_nodes

                if ply_count > max_ply:
                    return

                for child in node.variations:
                    move = child.move
                    board_before = node.board()
                    move_san = board_before.san(move)
                    board_before.push(move)
                    new_fen = board_before.fen()
                    move_uci = move.uci()
                    is_white = not board_before.turn == chess.WHITE  # It was white's move if now it's black's turn
                    move_number = board_before.fullmove_number if board_before.turn == chess.WHITE else board_before.fullmove_number - 1 if not is_white else board_before.fullmove_number

                    # Calculate proper move number
                    fen_parts = new_fen.split(' ')
                    fullmove = int(fen_parts[5]) if len(fen_parts) > 5 else 1
                    # If it's now black's turn, white just moved, move number = fullmove
                    # If it's now white's turn, black just moved, move number = fullmove - 1
                    actual_move_number = fullmove if board_before.turn == chess.BLACK else fullmove - 1

                    # Check for existing node
                    key = (parent_db_node['id'], move_san)
                    if key in existing_map:
                        skipped += 1
                        import_variation(child, existing_map[key], ply_count + 1)
                        continue

                    # Also check by FEN (transposition)
                    fen_key = ' '.join(new_fen.split(' ')[:4])
                    existing_by_fen = None
                    for fn, nd in fen_to_node.items():
                        if ' '.join(fn.split(' ')[:4]) == fen_key:
                            existing_by_fen = nd
                            break

                    if existing_by_fen:
                        skipped += 1
                        import_variation(child, existing_by_fen, ply_count + 1)
                        continue

                    try:
                        # Detect opening
                        opening_info = detect_opening(new_fen) if ply_count < 15 else None

                        new_node_id = str(uuid.uuid4())
                        new_node = {
                            'id': new_node_id,
                            'repertoire_id': repertoire_id,
                            'parent_id': parent_db_node['id'],
                            'fen': new_fen,
                            'move_san': move_san,
                            'move_uci': move_uci,
                            'move_number': actual_move_number,
                            'is_white_move': is_white,
                            'opening_name': opening_info.get('name') if opening_info else None,
                            'eco_code': opening_info.get('eco') if opening_info else None,
                        }

                        # Add comment as notes
                        if child.comment:
                            new_node['notes'] = child.comment

                        result = supabase.table('opening_nodes').insert(new_node).execute()

                        if result.data:
                            new_db_node = result.data[0]
                            existing_map[(parent_db_node['id'], move_san)] = new_db_node
                            fen_to_node[new_fen] = new_db_node
                            imported += 1
                            if len(sample_nodes) < 10:
                                sample_nodes.append({
                                    'id': new_db_node['id'],
                                    'move_san': move_san,
                                    'opening_name': new_node.get('opening_name'),
                                })

                            import_variation(child, new_db_node, ply_count + 1)
                        else:
                            errors.append(f"Failed to insert node for move {move_san}")

                    except Exception as e:
                        errors.append(f"Error at move {move_san}: {str(e)}")

            try:
                import_variation(game, root, 0)
            except Exception as e:
                errors.append(f"Game {game_num}: {str(e)}")

        return jsonify({
            'imported': imported,
            'skipped': skipped,
            'errors': errors[:20],  # Limit error list
            'nodes': sample_nodes,
        })
    except Exception as e:
        logger.error(f"Error importing PGN: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/repertoires/<repertoire_id>/repair-tree', methods=['POST'])
@verify_clerk_token
def repair_repertoire_tree(repertoire_id):
    """Repair tree from move line — rebuild nodes from starting position."""
    user_id = get_current_user_id()

    try:
        rep = supabase.table('opening_repertoires') \
            .select('*') \
            .eq('id', repertoire_id) \
            .eq('user_id', user_id) \
            .execute()

        if not rep.data:
            return jsonify({'error': 'Repertoire not found'}), 404

        move_line = rep.data[0].get('starting_move_line')
        if not move_line:
            return jsonify({'error': 'No starting move line set'}), 400

        starting_fen = rep.data[0].get('starting_fen') or STARTING_FEN

        # Get root node
        root_result = supabase.table('opening_nodes') \
            .select('*') \
            .eq('repertoire_id', repertoire_id) \
            .is_('parent_id', 'null') \
            .execute()

        if not root_result.data:
            return jsonify({'error': 'No root node'}), 400

        root = root_result.data[0]
        board = chess.Board(starting_fen)
        created_nodes = []
        parent = root

        moves = move_line.split()
        for m in moves:
            # Skip move numbers
            if m.endswith('.') or m == '...':
                continue
            try:
                new_fen, move_uci, is_white = validate_move(board.fen(), m)

                fen_parts = new_fen.split(' ')
                fullmove = int(fen_parts[5]) if len(fen_parts) > 5 else 1
                move_num = fullmove if chess.Board(new_fen).turn == chess.BLACK else fullmove - 1

                new_id = str(uuid.uuid4())
                node_data = {
                    'id': new_id,
                    'repertoire_id': repertoire_id,
                    'parent_id': parent['id'],
                    'fen': new_fen,
                    'move_san': m,
                    'move_uci': move_uci,
                    'move_number': move_num,
                    'is_white_move': is_white,
                }

                result = supabase.table('opening_nodes').insert(node_data).execute()
                if result.data:
                    parent = result.data[0]
                    created_nodes.append(parent)
                    board = chess.Board(new_fen)

            except ValueError as e:
                return jsonify({'error': f"Invalid move '{m}': {str(e)}"}), 400

        return jsonify({'created_nodes': created_nodes})
    except Exception as e:
        logger.error(f"Error repairing tree: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
# Node operations
# ─────────────────────────────────────────────

@openings_bp.route('/nodes', methods=['POST'])
@verify_clerk_token
def add_node():
    """Add a move to the tree."""
    user_id = get_current_user_id()
    data = request.get_json()

    parent_id = data.get('parentId')
    move_san = data.get('moveSan')
    move_uci = data.get('moveUci')
    new_fen = data.get('newFen')
    is_critical = data.get('isCritical', False)

    if not parent_id or not move_san or not new_fen:
        return jsonify({'error': 'parentId, moveSan, and newFen are required'}), 400

    try:
        # Verify parent belongs to user
        parent = supabase.table('opening_nodes') \
            .select('*, opening_repertoires!inner(user_id)') \
            .eq('id', parent_id) \
            .execute()

        if not parent.data:
            return jsonify({'error': 'Parent node not found'}), 404

        if parent.data[0].get('opening_repertoires', {}).get('user_id') != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        parent_node = parent.data[0]
        repertoire_id = parent_node['repertoire_id']

        # Check for existing child with same move (by SAN or UCI)
        existing = supabase.table('opening_nodes') \
            .select('*') \
            .eq('parent_id', parent_id) \
            .eq('move_san', move_san) \
            .execute()

        if existing.data:
            existing.data[0]['children'] = []
            return jsonify(existing.data[0])  # Return existing node

        # Also check by UCI to handle the unique constraint
        if move_uci:
            existing_uci = supabase.table('opening_nodes') \
                .select('*') \
                .eq('parent_id', parent_id) \
                .eq('move_uci', move_uci) \
                .execute()

            if existing_uci.data:
                existing_uci.data[0]['children'] = []
                return jsonify(existing_uci.data[0])  # Return existing node

        # Determine move number and color
        fen_parts = new_fen.split(' ')
        fullmove = int(fen_parts[5]) if len(fen_parts) > 5 else 1
        # After the move: if it's black's turn, white just moved
        is_white_move = fen_parts[1] == 'b' if len(fen_parts) > 1 else True
        move_number = fullmove if fen_parts[1] == 'b' else fullmove - 1

        # Detect opening
        opening_info = detect_opening(new_fen)

        new_node = {
            'id': str(uuid.uuid4()),
            'repertoire_id': repertoire_id,
            'parent_id': parent_id,
            'fen': new_fen,
            'move_san': move_san,
            'move_uci': move_uci or '',
            'move_number': move_number,
            'is_white_move': is_white_move,
            'is_critical': is_critical,
            'opening_name': opening_info.get('name') if opening_info else None,
            'eco_code': opening_info.get('eco') if opening_info else None,
        }

        try:
            result = supabase.table('opening_nodes').insert(new_node).execute()
        except Exception as insert_err:
            # Handle duplicate key race condition — return existing node
            if '23505' in str(insert_err):
                existing_retry = supabase.table('opening_nodes') \
                    .select('*') \
                    .eq('parent_id', parent_id) \
                    .eq('move_san', move_san) \
                    .execute()
                if existing_retry.data:
                    existing_retry.data[0]['children'] = []
                    return jsonify(existing_retry.data[0])
            raise insert_err

        if result.data:
            result.data[0]['children'] = []
            return jsonify(result.data[0]), 201
        else:
            return jsonify({'error': 'Failed to create node'}), 500

    except Exception as e:
        logger.error(f"Error adding node: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/nodes/<node_id>', methods=['PUT'])
@verify_clerk_token
def update_node(node_id):
    """Update node metadata (notes, priority, critical)."""
    user_id = get_current_user_id()
    data = request.get_json()

    try:
        # Verify ownership
        node = supabase.table('opening_nodes') \
            .select('*, opening_repertoires!inner(user_id)') \
            .eq('id', node_id) \
            .execute()

        if not node.data:
            return jsonify({'error': 'Node not found'}), 404

        if node.data[0].get('opening_repertoires', {}).get('user_id') != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        update_data = {}
        if 'notes' in data:
            update_data['notes'] = data['notes']
        if 'priority' in data:
            update_data['priority'] = data['priority']
        if 'isCritical' in data:
            update_data['is_critical'] = data['isCritical']

        update_data['updated_at'] = datetime.utcnow().isoformat()

        result = supabase.table('opening_nodes') \
            .update(update_data) \
            .eq('id', node_id) \
            .execute()

        return jsonify(result.data[0] if result.data else {})
    except Exception as e:
        logger.error(f"Error updating node: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/nodes/<node_id>', methods=['DELETE'])
@verify_clerk_token
def delete_node(node_id):
    """Delete node and all its children (cascading). Cannot delete root."""
    user_id = get_current_user_id()

    try:
        node = supabase.table('opening_nodes') \
            .select('*, opening_repertoires!inner(user_id)') \
            .eq('id', node_id) \
            .execute()

        if not node.data:
            return jsonify({'error': 'Node not found'}), 404

        if node.data[0].get('opening_repertoires', {}).get('user_id') != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        if node.data[0].get('parent_id') is None:
            return jsonify({'error': 'Cannot delete root node'}), 400

        supabase.table('opening_nodes') \
            .delete() \
            .eq('id', node_id) \
            .execute()

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting node: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
# Arrow annotations
# ─────────────────────────────────────────────

@openings_bp.route('/nodes/<node_id>/arrows', methods=['POST'])
@verify_clerk_token
def add_arrow(node_id):
    """Add arrow annotation to a node."""
    user_id = get_current_user_id()
    data = request.get_json()

    from_square = data.get('fromSquare')
    to_square = data.get('toSquare')
    color = data.get('color', 'green')

    if not from_square or not to_square:
        return jsonify({'error': 'fromSquare and toSquare are required'}), 400

    try:
        # Verify ownership
        node = supabase.table('opening_nodes') \
            .select('*, opening_repertoires!inner(user_id)') \
            .eq('id', node_id) \
            .execute()

        if not node.data or node.data[0].get('opening_repertoires', {}).get('user_id') != user_id:
            return jsonify({'error': 'Node not found'}), 404

        result = supabase.table('opening_arrows').insert({
            'id': str(uuid.uuid4()),
            'node_id': node_id,
            'from_square': from_square,
            'to_square': to_square,
            'color': color,
        }).execute()

        return jsonify(result.data[0] if result.data else {}), 201
    except Exception as e:
        logger.error(f"Error adding arrow: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/nodes/<node_id>/arrows/<arrow_id>', methods=['DELETE'])
@verify_clerk_token
def delete_arrow(node_id, arrow_id):
    """Delete arrow annotation."""
    user_id = get_current_user_id()

    try:
        # Verify ownership through node
        node = supabase.table('opening_nodes') \
            .select('*, opening_repertoires!inner(user_id)') \
            .eq('id', node_id) \
            .execute()

        if not node.data or node.data[0].get('opening_repertoires', {}).get('user_id') != user_id:
            return jsonify({'error': 'Not found'}), 404

        supabase.table('opening_arrows') \
            .delete() \
            .eq('id', arrow_id) \
            .eq('node_id', node_id) \
            .execute()

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting arrow: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
# Spaced repetition training
# ─────────────────────────────────────────────

@openings_bp.route('/training/due', methods=['GET'])
@verify_clerk_token
def get_due_nodes():
    """Get nodes due for review."""
    user_id = get_current_user_id()
    repertoire_id = request.args.get('repertoire_id')
    limit = min(int(request.args.get('limit', 20)), 100)

    try:
        now = datetime.utcnow().isoformat()

        query = supabase.table('opening_nodes') \
            .select('*, opening_repertoires!inner(user_id)') \
            .eq('opening_repertoires.user_id', user_id) \
            .not_.is_('move_san', 'null')

        if repertoire_id:
            query = query.eq('repertoire_id', repertoire_id)

        # Get nodes where next_review_at <= now OR never trained
        query = query.or_(f'next_review_at.lte.{now},next_review_at.is.null')
        query = query.limit(limit)

        result = query.execute()
        nodes = result.data or []

        # Clean up joined data
        for n in nodes:
            if 'opening_repertoires' in n:
                del n['opening_repertoires']

        return jsonify({'nodes': nodes, 'total_due': len(nodes)})
    except Exception as e:
        logger.error(f"Error getting due nodes: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/training/result', methods=['POST'])
@verify_clerk_token
def record_training_result():
    """Record training result using SM-2 algorithm."""
    user_id = get_current_user_id()
    data = request.get_json()

    node_id = data.get('nodeId')
    correct = data.get('correct', False)
    time_ms = data.get('timeMs')

    if not node_id:
        return jsonify({'error': 'nodeId is required'}), 400

    try:
        # Get current node stats
        node_result = supabase.table('opening_nodes') \
            .select('*, opening_repertoires!inner(user_id)') \
            .eq('id', node_id) \
            .execute()

        if not node_result.data:
            return jsonify({'error': 'Node not found'}), 404

        if node_result.data[0].get('opening_repertoires', {}).get('user_id') != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        node = node_result.data[0]

        # SM-2 algorithm
        ease_factor = node.get('ease_factor', 2.5)
        interval_days = node.get('interval_days', 1)
        times_trained = node.get('times_trained', 0) + 1
        times_correct = node.get('times_correct', 0) + (1 if correct else 0)

        if correct:
            # Quality score (0-5): 5 for fast correct, 3 for slow correct
            q = 5 if (time_ms and time_ms < 5000) else 4 if (time_ms and time_ms < 15000) else 3

            ease_factor = max(1.3, ease_factor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))

            if times_trained == 1:
                interval_days = 1
            elif times_trained == 2:
                interval_days = 6
            else:
                interval_days = round(interval_days * ease_factor)
        else:
            # Wrong answer: reset
            interval_days = 1
            ease_factor = max(1.3, ease_factor - 0.2)

        next_review = (datetime.utcnow() + timedelta(days=interval_days)).isoformat()

        update_data = {
            'times_trained': times_trained,
            'times_correct': times_correct,
            'ease_factor': round(ease_factor, 2),
            'interval_days': interval_days,
            'last_trained_at': datetime.utcnow().isoformat(),
            'next_review_at': next_review,
            'updated_at': datetime.utcnow().isoformat(),
        }

        result = supabase.table('opening_nodes') \
            .update(update_data) \
            .eq('id', node_id) \
            .execute()

        updated = result.data[0] if result.data else {}
        if 'opening_repertoires' in updated:
            del updated['opening_repertoires']

        return jsonify(updated)
    except Exception as e:
        logger.error(f"Error recording training result: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/training/stats', methods=['GET'])
@verify_clerk_token
def get_training_stats():
    """Get overall training statistics."""
    user_id = get_current_user_id()
    repertoire_id = request.args.get('repertoire_id')

    try:
        query = supabase.table('opening_nodes') \
            .select('times_trained, times_correct, next_review_at, opening_repertoires!inner(user_id)') \
            .eq('opening_repertoires.user_id', user_id) \
            .not_.is_('move_san', 'null')

        if repertoire_id:
            query = query.eq('repertoire_id', repertoire_id)

        result = query.execute()
        nodes = result.data or []

        total_nodes = len(nodes)
        trained_nodes = sum(1 for n in nodes if n.get('times_trained', 0) > 0)
        total_reviews = sum(n.get('times_trained', 0) for n in nodes)
        total_correct = sum(n.get('times_correct', 0) for n in nodes)

        now = datetime.utcnow().isoformat()
        due_nodes = sum(1 for n in nodes if
                        n.get('next_review_at') is None or
                        n.get('next_review_at', '') <= now)

        accuracy = (total_correct / total_reviews * 100) if total_reviews > 0 else 0

        return jsonify({
            'total_nodes': total_nodes,
            'trained_nodes': trained_nodes,
            'due_nodes': due_nodes,
            'total_reviews': total_reviews,
            'accuracy': round(accuracy, 1),
        })
    except Exception as e:
        logger.error(f"Error getting training stats: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
# Game search & linking
# ─────────────────────────────────────────────

@openings_bp.route('/nodes/<node_id>/games', methods=['GET'])
@verify_clerk_token
def get_node_games(node_id):
    """Get games linked to a node."""
    user_id = get_current_user_id()

    try:
        # Verify ownership — return empty list for deleted/missing nodes
        node = supabase.table('opening_nodes') \
            .select('id, opening_repertoires!inner(user_id)') \
            .eq('id', node_id) \
            .execute()

        if not node.data or node.data[0].get('opening_repertoires', {}).get('user_id') != user_id:
            return jsonify({'games': []})

        result = supabase.table('opening_game_links') \
            .select('*') \
            .eq('node_id', node_id) \
            .order('created_at', desc=True) \
            .execute()

        return jsonify({'games': result.data or []})
    except Exception as e:
        logger.error(f"Error getting node games: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/nodes/<node_id>/games', methods=['POST'])
@verify_clerk_token
def link_game_to_node(node_id):
    """Link a game to a node."""
    user_id = get_current_user_id()
    data = request.get_json()

    try:
        # Verify ownership
        node = supabase.table('opening_nodes') \
            .select('id, opening_repertoires!inner(user_id)') \
            .eq('id', node_id) \
            .execute()

        if not node.data or node.data[0].get('opening_repertoires', {}).get('user_id') != user_id:
            return jsonify({'error': 'Not found'}), 404

        game_link = {
            'id': str(uuid.uuid4()),
            'node_id': node_id,
            'game_source': data.get('gameSource', 'user'),
            'game_id': data.get('gameId'),
            'game_pgn': data.get('gamePgn'),
            'white_player': data.get('whitePlayer'),
            'black_player': data.get('blackPlayer'),
            'white_elo': data.get('whiteElo'),
            'black_elo': data.get('blackElo'),
            'result': data.get('result'),
            'date_played': data.get('datePlayed'),
            'event_name': data.get('eventName'),
            'move_reached': data.get('moveReached'),
            'notes': data.get('notes'),
        }

        result = supabase.table('opening_game_links').insert(game_link).execute()

        return jsonify(result.data[0] if result.data else {}), 201
    except Exception as e:
        logger.error(f"Error linking game: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/games/<game_link_id>', methods=['DELETE'])
@verify_clerk_token
def delete_game_link(game_link_id):
    """Remove a game link."""
    user_id = get_current_user_id()

    try:
        # Verify ownership through node → repertoire
        link = supabase.table('opening_game_links') \
            .select('*, opening_nodes!inner(opening_repertoires!inner(user_id))') \
            .eq('id', game_link_id) \
            .execute()

        if not link.data:
            return jsonify({'error': 'Not found'}), 404

        supabase.table('opening_game_links') \
            .delete() \
            .eq('id', game_link_id) \
            .execute()

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting game link: {e}")
        return jsonify({'error': str(e)}), 500


# In-memory cache for position counts (board_hash -> count)
_position_count_cache = {}

@openings_bp.route('/games/by-position', methods=['GET'])
@verify_clerk_token
def games_by_position():
    """Fast lookup: find games that reach a given FEN using the position hash index.
    Returns games immediately; total count is served from cache or estimated."""
    fen = request.args.get('fen', '')
    if not fen:
        return jsonify({'error': 'Missing fen parameter'}), 400

    limit = min(int(request.args.get('limit', 5)), 50)
    min_rating = int(request.args.get('min_rating', 0))

    if not check_internal_db_exists():
        return jsonify({'games': [], 'total': 0, 'indexed': False})

    conn = get_internal_db_connection()
    try:
        if not _has_position_index(conn):
            conn.close()
            return jsonify({'games': [], 'total': 0, 'indexed': False})

        board_hash = _get_board_hash(fen)

        # Fast path: get games without blocking on COUNT
        pool_size = min(max(limit * 40, 200), 2000)
        id_rows = conn.execute(
            "SELECT game_id FROM game_positions WHERE board_hash = ? LIMIT ?",
            [board_hash, pool_size]
        ).fetchall()
        game_ids = [r['game_id'] for r in id_rows]

        if not game_ids:
            _position_count_cache[board_hash] = 0
            conn.close()
            return jsonify({'games': [], 'total': 0, 'indexed': True})

        # Use cached count, or estimate from pool
        cached_count = _position_count_cache.get(board_hash)
        if cached_count is not None:
            total = cached_count
        elif len(game_ids) < pool_size:
            # Pool wasn't full — exact count
            total = len(game_ids)
            _position_count_cache[board_hash] = total
        else:
            # Pool is full — we have at least pool_size games, show "N+" estimate
            total = pool_size  # Will be updated by deferred count endpoint

        # Fetch game details for the pool, filter by rating, sort by strength
        placeholders = ','.join('?' * len(game_ids))
        query = f"SELECT * FROM games WHERE id IN ({placeholders})"
        params = list(game_ids)

        if min_rating > 0:
            query += " AND (white_elo >= ? OR black_elo >= ?)"
            params.extend([min_rating, min_rating])

        query += " ORDER BY COALESCE(white_elo, 0) + COALESCE(black_elo, 0) DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        games = []
        for row in cursor.fetchall():
            game_data = dict(row)
            if game_data.get('pgn_offset') is not None:
                try:
                    with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
                        f.seek(game_data['pgn_offset'])
                        pgn_text = ''
                        for line in f:
                            pgn_text += line
                            if line.strip() in ['1-0', '0-1', '1/2-1/2', '*'] and len(pgn_text) > 50:
                                break
                        game_data['pgn'] = pgn_text
                except Exception:
                    pass
            games.append(game_data)

        conn.close()
        return jsonify({
            'games': games,
            'total': total,
            'indexed': True,
            'count_exact': cached_count is not None or len(game_ids) < pool_size,
        })
    except Exception as e:
        logger.error(f"Error in games_by_position: {e}")
        conn.close()
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/games/position-count', methods=['GET'])
@verify_clerk_token
def position_count():
    """Deferred COUNT endpoint — called async by frontend after games load."""
    fen = request.args.get('fen', '')
    if not fen:
        return jsonify({'error': 'Missing fen parameter'}), 400

    if not check_internal_db_exists():
        return jsonify({'count': 0})

    conn = get_internal_db_connection()
    try:
        if not _has_position_index(conn):
            conn.close()
            return jsonify({'count': 0})

        board_hash = _get_board_hash(fen)

        # Check cache first
        cached = _position_count_cache.get(board_hash)
        if cached is not None:
            conn.close()
            return jsonify({'count': cached})

        # Do the slow COUNT
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM game_positions WHERE board_hash = ?",
            [board_hash]
        ).fetchone()['cnt']

        _position_count_cache[board_hash] = total
        conn.close()
        return jsonify({'count': total})
    except Exception as e:
        logger.error(f"Error in position_count: {e}")
        conn.close()
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/games/search', methods=['GET'])
@verify_clerk_token
def search_games():
    """Search games (non-streaming)."""
    user_id = get_current_user_id()
    source = request.args.get('source', 'internal')
    fen = request.args.get('fen', '')
    username = request.args.get('username', '')
    max_games = min(int(request.args.get('max_games', 10)), 50)

    try:
        games = []

        if source == 'internal':
            eco_code, _ = detect_eco_for_search(fen) if fen else (None, None)
            games = fetch_internal_games('', max_games, fen, eco_code)
        elif source == 'lichess':
            if not username:
                return jsonify({'error': 'Username required for Lichess'}), 400
            games = fetch_lichess_games(username, max_games=max_games, filter_fen=fen)
        elif source == 'chesscom':
            if not username:
                return jsonify({'error': 'Username required for Chess.com'}), 400
            games = fetch_chesscom_games(username, max_games=max_games, filter_fen=fen)
        else:
            return jsonify({'error': f'Unknown source: {source}'}), 400

        return jsonify({'games': games})
    except Exception as e:
        logger.error(f"Error searching games: {e}")
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/games/search/stream', methods=['GET'])
@verify_clerk_token
def search_games_stream():
    """SSE streaming game search."""
    user_id = get_current_user_id()
    source = request.args.get('source', 'internal')
    fen = request.args.get('fen', '')
    username = request.args.get('username', '')
    eco = request.args.get('eco', '')
    min_rating = int(request.args.get('min_rating', 0))
    max_games = min(int(request.args.get('max_games', 10)), 50)

    def generate():
        try:
            if source == 'internal':
                eco_filter = eco or None
                if not eco_filter and fen:
                    eco_filter, _ = detect_eco_for_search(fen)

                for event in fetch_internal_games_progressive(fen, eco_filter, min_rating, max_games):
                    yield f"data: {json.dumps(event)}\n\n"

            elif source == 'lichess':
                if not username:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Username required'})}\n\n"
                    return

                for event in fetch_lichess_games_progressive(username, fen, min_rating, max_games):
                    yield f"data: {json.dumps(event)}\n\n"

            elif source == 'chesscom':
                if not username:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Username required'})}\n\n"
                    return

                for event in fetch_chesscom_games_progressive(username, fen, min_rating, max_games):
                    yield f"data: {json.dumps(event)}\n\n"

            else:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Unknown source: {source}'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@openings_bp.route('/games/internal/status', methods=['GET'])
@verify_clerk_token
def internal_db_status():
    """Check TWIC database status."""
    try:
        if not check_internal_db_exists():
            return jsonify({
                'available': False,
                'message': 'TWIC database not found',
            })

        conn = get_internal_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT key, value FROM metadata")
        metadata = {row['key']: row['value'] for row in cursor.fetchall()}

        conn.close()

        return jsonify({
            'available': True,
            'game_count': int(metadata.get('game_count', 0)),
            'player_count': int(metadata.get('player_count', 0)),
            'indexed_at': metadata.get('indexed_at', 'unknown'),
        })
    except Exception as e:
        logger.error(f"Error checking internal DB status: {e}")
        return jsonify({'error': str(e)}), 500
