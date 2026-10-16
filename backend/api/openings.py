"""
Openings API - Master games database (Database page)
Endpoints for game search by position, candidate moves, and single-game PGN/meta.

Blueprint: /api/openings
"""

import os
import json
import re
import sqlite3
import logging
import time
import traceback
import math
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, List, Dict, Any, Tuple

import chess
import chess.pgn
import io
import requests

from flask import Blueprint, request, jsonify, Response, stream_with_context
from utils.auth import verify_clerk_token, get_current_user_id, require_active_membership
from utils.cache import with_cache
from utils.board_image import render_final_position_png

logger = logging.getLogger(__name__)

openings_bp = Blueprint('openings', __name__, url_prefix='/api/openings')

# Paths for TWIC database
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TWIC_DB_PATH = os.path.join(BACKEND_DIR, "data/twic/games_index.db")
TWIC_PGN_PATH = os.path.join(BACKEND_DIR, "data/twic/twic_master_database.pgn")


# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────

def detect_opening(fen: str) -> Optional[Dict]:
    """Query Lichess masters DB for opening name. Returns {'name': ..., 'eco': ...} or None."""
    try:
        resp = requests.get(
            'https://explorer.lichess.org/masters',
            params={'fen': fen},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            opening = data.get('opening')
            if opening:
                return {'name': opening.get('name', ''), 'eco': opening.get('eco', '')}
        elif resp.status_code == 401:
            logger.warning(f"Lichess Explorer returned 401 for FEN: {fen}")
            return None
    except Exception as e:
        logger.debug(f"Opening detection failed for {fen}: {e}")
    return None


def detect_eco_for_search(fen: str) -> Tuple[Optional[str], Optional[str]]:
    """Get (eco_code, eco_name) for FEN from Lichess Explorer. Used for DB pre-filtering."""
    info = detect_opening(fen)
    if info:
        return info.get('eco'), info.get('name')
    return None, None


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
                    'https://explorer.lichess.org/masters',
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
                elif resp.status_code == 401:
                    logger.warning(f"Lichess Explorer returned 401 during BFS for FEN: {current_board.fen()}")
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
    # Open TWIC DB in read-only mode.
    # mode=ro allows reads while backfill/indexer writes via separate connection.
    uri = f"file:{TWIC_DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def check_internal_db_exists() -> bool:
    return os.path.exists(TWIC_DB_PATH)


def _normalize_game_row(game_data: dict) -> dict:
    """Normalize TWIC game row for frontend compatibility.

    Keeps canonical DB fields (white_name/black_name) and also provides
    legacy aliases (white/black) used by some existing UI paths.
    """
    if not game_data:
        return game_data

    if 'white_name' in game_data and 'white' not in game_data:
        game_data['white'] = game_data.get('white_name')
    if 'black_name' in game_data and 'black' not in game_data:
        game_data['black'] = game_data.get('black_name')
    return game_data


def fetch_internal_games(search_query: str, max_games: int, filter_fen: str = None, eco_filter: str = None) -> list:
    """Fetch games from TWIC database, optionally filtering by FEN position."""
    if not check_internal_db_exists():
        return []

    conn = get_internal_db_connection()
    cursor = conn.cursor()

    try:
        # FAST PATH: Use position hash index when available — mirrors
        # fetch_internal_games_progressive's fast path so a rare position
        # (mostly older games) doesn't get filtered out by the global
        # newest-first scan.
        if filter_fen and _has_position_index(conn):
            board_hash = _get_board_hash(filter_fen)
            pool_size = min(max(max_games * 40, 200), 2000)
            max_gid = _get_max_game_id(conn)
            id_rows = conn.execute(
                "SELECT game_id FROM game_positions WHERE board_hash = ? AND game_id <= ? ORDER BY rowid DESC LIMIT ?",
                [board_hash, max_gid, pool_size]
            ).fetchall()
            game_ids = [r['game_id'] for r in id_rows]

            if not game_ids:
                conn.close()
                return []

            placeholders = ','.join('?' * len(game_ids))
            query = f"SELECT * FROM games WHERE id IN ({placeholders})"
            params = list(game_ids)

            if eco_filter:
                query += " AND eco LIKE ?"
                params.append(f"{eco_filter}%")

            if search_query:
                query += " AND (white_name LIKE ? OR black_name LIKE ? OR event LIKE ?)"
                params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])

            query += " ORDER BY date DESC LIMIT ?"
            params.append(max_games)

            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                game_data = _normalize_game_row(dict(row))
                if game_data.get('pgn_offset') is not None and game_data.get('pgn_length'):
                    try:
                        with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
                            f.seek(game_data['pgn_offset'])
                            game_data['pgn'] = f.read(game_data['pgn_length'])
                    except Exception as e:
                        logger.debug(f"Error reading PGN: {e}")
                results.append(game_data)

            conn.close()
            return results

        query = "SELECT * FROM games"
        params = []
        conditions = []

        if eco_filter:
            conditions.append("eco LIKE ?")
            params.append(f"{eco_filter}%")

        if search_query:
            conditions.append("(white_name LIKE ? OR black_name LIKE ? OR event LIKE ?)")
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY date DESC LIMIT ?"
        params.append(max_games * 3 if filter_fen else max_games)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            game_data = _normalize_game_row(dict(row))
            if filter_fen and game_data.get('pgn_offset') is not None:
                # Read PGN from master file using exact length
                try:
                    with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
                        f.seek(game_data['pgn_offset'])
                        pgn_text = f.read(game_data['pgn_length'])

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
    """Convert a full FEN to board hash (pieces + side + castling).
    En passant is normalized to '-' to match the DB storage format."""
    parts = fen.split(' ')
    if len(parts) >= 4:
        parts[3] = '-'
    return ' '.join(parts[:4])


def fetch_internal_games_progressive(filter_fen: str, eco_filter: str = None,
                                      min_rating: int = 0, max_games: int = 10,
                                      stop_after: int = 500, result: str = None):
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

            # 2-step: get IDs first (fast index scan), then fetch details
            pool_size = min(max(max_games * 40, 200), 2000)
            max_gid = _get_max_game_id(conn)
            id_rows = conn.execute(
                "SELECT game_id FROM game_positions WHERE board_hash = ? AND game_id <= ? ORDER BY rowid DESC LIMIT ?",
                [board_hash, max_gid, pool_size]
            ).fetchall()
            game_ids = [r['game_id'] for r in id_rows]

            if not game_ids:
                conn.close()
                yield {'type': 'done', 'checked': 0, 'found': 0}
                return

            placeholders = ','.join('?' * len(game_ids))
            query = f"SELECT * FROM games WHERE id IN ({placeholders})"
            params = list(game_ids)

            if min_rating > 0:
                query += " AND white_elo >= ? AND black_elo >= ?"
                params.extend([min_rating, min_rating])

            if eco_filter:
                query += " AND eco LIKE ?"
                params.append(f"{eco_filter}%")

            if result:
                query += " AND result = ?"
                params.append(result)

            query += " ORDER BY date DESC LIMIT ?"
            params.append(max_games)

            cursor.execute(query, params)
            found = 0
            for row in cursor.fetchall():
                game_data = _normalize_game_row(dict(row))
                # Load PGN
                if game_data.get('pgn_offset') is not None and game_data.get('pgn_length'):
                    try:
                        with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
                            f.seek(game_data['pgn_offset'])
                            pgn_text = f.read(game_data['pgn_length'])
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
            conditions.append("white_elo >= ? AND black_elo >= ?")
            params.extend([min_rating, min_rating])

        if result:
            conditions.append("result = ?")
            params.append(result)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY date DESC LIMIT ?"
        params.append(stop_after)

        cursor.execute(query, params)

        found = 0
        checked = 0
        for row in cursor.fetchall():
            checked += 1
            game_data = _normalize_game_row(dict(row))

            if filter_fen and game_data.get('pgn_offset') is not None:
                try:
                    pgn_length = game_data.get('pgn_length')
                    with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
                        f.seek(game_data['pgn_offset'])
                        if pgn_length:
                            pgn_text = f.read(pgn_length)
                        else:
                            # Fallback: line-by-line with fixed termination
                            pgn_text = ''
                            for line in f:
                                pgn_text += line
                                if line.strip().endswith(('1-0', '0-1', '1/2-1/2', '*')) and len(pgn_text) > 50:
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
                                     min_rating: int = 0, max_games: int = 10,
                                     archive_months: int = 3, player_color: str = '',
                                     result_filter: str = ''):
    """Generator: yield Lichess games progressively."""
    try:
        headers = {'Accept': 'application/x-ndjson'}
        params = {'max': 200, 'opening': 'true', 'pgnInJson': 'true'}

        # Add time filter based on archive_months
        if archive_months < 999:
            # Calculate milliseconds since N months ago
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=archive_months * 30)
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            params['since'] = cutoff_ms

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

                # Apply color filter
                if player_color:
                    player_white = game_data.get('white', '').lower() == username.lower()
                    player_black = game_data.get('black', '').lower() == username.lower()
                    if player_color == 'white' and not player_white:
                        continue
                    if player_color == 'black' and not player_black:
                        continue

                # Apply result filter
                if result_filter:
                    game_result = game_data.get('result', '')  # 'white', 'black', or 'draw'
                    player_white = game_data.get('white', '').lower() == username.lower()

                    if result_filter == 'win':
                        # Win for the player
                        if player_white and game_result != 'white':
                            continue
                        if not player_white and game_result != 'black':
                            continue
                    elif result_filter == 'loss':
                        # Loss for the player
                        if player_white and game_result == 'white':
                            continue
                        if not player_white and game_result == 'black':
                            continue
                        if game_result == 'draw':
                            continue
                    elif result_filter == 'draw':
                        if game_result != 'draw':
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
                                      min_rating: int = 0, max_games: int = 10,
                                      archive_months: int = 3, player_color: str = '',
                                      result_filter: str = ''):
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

        # Limit archives based on archive_months parameter
        max_archives = archive_months if archive_months < 999 else len(archives)

        found = 0
        checked = 0
        for archive_url in archives[:max_archives]:
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

                    # Apply color filter
                    if player_color:
                        player_white = game_data.get('white', '').lower() == username.lower()
                        player_black = game_data.get('black', '').lower() == username.lower()
                        if player_color == 'white' and not player_white:
                            continue
                        if player_color == 'black' and not player_black:
                            continue

                    # Apply result filter
                    if result_filter:
                        game_result = game_data.get('result', '')
                        player_white = game_data.get('white', '').lower() == username.lower()

                        if result_filter == 'win':
                            # Win for the player
                            if player_white and game_result != 'win':
                                continue
                            if not player_white and game_result != 'checkmated':
                                continue
                        elif result_filter == 'loss':
                            # Loss for the player
                            if player_white and game_result != 'checkmated':
                                continue
                            if not player_white and game_result != 'win':
                                continue
                        elif result_filter == 'draw':
                            if game_result not in ('agreed', 'stalemate', 'repetition', 'insufficient', 'timevsinsufficient'):
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


# In-memory cache for position counts (board_hash -> count)
_position_count_cache = {}

# Cached max game_id to filter orphaned game_positions entries
_max_game_id_cache = {'value': None, 'ts': 0}

def _get_max_game_id(conn) -> int:
    """Get max game_id from games table, cached for 5 minutes."""
    import time as _time
    now = _time.time()
    if _max_game_id_cache['value'] is not None and now - _max_game_id_cache['ts'] < 300:
        return _max_game_id_cache['value']
    row = conn.execute("SELECT MAX(id) FROM games").fetchone()
    val = row[0] if row else 0
    _max_game_id_cache['value'] = val
    _max_game_id_cache['ts'] = now
    return val


_NAME_TOKEN_SPLIT = re.compile(r"[\s,]+")


def _longest_name_token(name: str) -> str:
    """Pick the most selective token from a player-name input for prefix LIKE.

    TWIC names are normalized to lowercase with the comma in `Lastname,I`
    replaced by a space, e.g. `Carlsen,M` -> `carlsen m`. The longest token
    is the surname for both `Magnus Carlsen` and `Carlsen,M` style input,
    which is what we want for an index-friendly `LIKE 'token%'` lookup.
    Substring search (e.g. `arlse`) is not supported by this approach.
    """
    if not name:
        return ''
    tokens = [t for t in _NAME_TOKEN_SPLIT.split(name.lower().strip()) if t]
    return max(tokens, key=len) if tokens else ''

@openings_bp.route('/games/by-position', methods=['GET'])
@require_active_membership
def games_by_position():
    """Fast lookup: find games that reach a given FEN using the position hash index.
    Returns game metadata only (no PGN). PGN is fetched on demand via /games/<id>/pgn.

    Note: This endpoint is public (no auth required) to support the position analysis page."""
    fen = request.args.get('fen', '')
    if not fen:
        return jsonify({'error': 'Missing fen parameter'}), 400

    limit = min(int(request.args.get('limit', 5)), 50)
    player_color = request.args.get('player_color', '').strip().lower()
    if player_color not in ('white', 'black', ''):
        player_color = ''
    # opponent_color is a linked view of the same single filter: the opponent's
    # colour is the inverse of the player's. Reconcile the two into player_color
    # so the query logic below stays untouched.
    opponent_color = request.args.get('opponent_color', '').strip().lower()
    if opponent_color not in ('white', 'black', ''):
        opponent_color = ''
    if opponent_color:
        inverse = 'black' if opponent_color == 'white' else 'white'
        if player_color and player_color != inverse:
            # Both sides claim the same colour (white/white or black/black) —
            # unrepresentable in a single game.
            return jsonify({'error': 'player_color and opponent_color cannot both be the same colour'}), 400
        player_color = inverse
    player_name = request.args.get('player_name', '').strip()
    opponent_name = request.args.get('opponent_name', '').strip()
    sort_by = request.args.get('sort_by', 'date_desc')
    result = request.args.get('result', '').strip()
    if result not in ('1-0', '0-1', '1/2-1/2', ''):
        result = ''

    # ELO range filters
    white_elo_min = int(request.args.get('white_elo_min', 0))
    white_elo_max = int(request.args.get('white_elo_max', 3500))
    black_elo_min = int(request.args.get('black_elo_min', 0))
    black_elo_max = int(request.args.get('black_elo_max', 3500))

    # New filters
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    eco_code = request.args.get('eco_code', '').strip().upper()
    event_name = request.args.get('event_name', '').strip()

    if not check_internal_db_exists():
        return jsonify({'games': [], 'total': 0, 'indexed': False})

    conn = get_internal_db_connection()
    query_timeout = [False, time.time()]  # [timed_out flag, start_time]

    def progress_handler():
        """Progress handler to interrupt long-running queries after 3 seconds."""
        if time.time() - query_timeout[1] > 3.0:
            query_timeout[0] = True
            return 1  # Non-zero return aborts query
        return 0

    try:
        # Set 3-second timeout for all queries
        conn.execute("PRAGMA busy_timeout = 3000")
        conn.set_progress_handler(progress_handler, 10000)  # Check every 10k VM instructions

        if not _has_position_index(conn):
            conn.close()
            return jsonify({'games': [], 'total': 0, 'indexed': False})

        board_hash = _get_board_hash(fen)

        # Estimate total count from cache or move_stats table (instant)
        cached_count = _position_count_cache.get(board_hash)
        if cached_count is not None:
            total = cached_count
        else:
            # Use move_stats table for instant count (pre-computed)
            try:
                query_timeout[1] = time.time()  # Reset timeout for this query
                move_stats_row = conn.execute(
                    "SELECT SUM(games) as total FROM move_stats WHERE board_hash = ?",
                    [board_hash]
                ).fetchone()
                if move_stats_row and move_stats_row['total']:
                    total = move_stats_row['total']
                    _position_count_cache[board_hash] = total
                else:
                    # Fallback: simple count on game_positions without JOIN
                    query_timeout[1] = time.time()  # Reset timeout for fallback query
                    probe = conn.execute(
                        "SELECT COUNT(*) as cnt FROM (SELECT 1 FROM game_positions WHERE board_hash = ? LIMIT 2001)",
                        [board_hash]
                    ).fetchone()['cnt']
                    if probe <= 2000:
                        total = probe
                        _position_count_cache[board_hash] = total
                    else:
                        total = 2000  # Will be updated by deferred count endpoint
            except (sqlite3.OperationalError, Exception) as e:
                logger.warning(f"Error getting count from move_stats: {e}, using fallback")
                # Fallback: try counting from game_positions directly
                try:
                    query_timeout[1] = time.time()
                    probe = conn.execute(
                        "SELECT COUNT(*) as cnt FROM (SELECT 1 FROM game_positions WHERE board_hash = ? LIMIT 2001)",
                        [board_hash]
                    ).fetchone()['cnt']
                    if probe <= 2000:
                        total = probe
                        _position_count_cache[board_hash] = total
                    else:
                        total = 2000
                except Exception:
                    pool_size = min(max(limit * 40, 200), 2000)
                    total = pool_size

        # 2-step approach: get limited IDs first, then fetch+sort the small set.
        pool_multiplier = 80 if result else 40
        pool_size = min(max(limit * pool_multiplier, 200), 2000)

        # Always use position intersection — even for player searches.
        # The old code skipped game_positions when player_name was set, returning
        # ALL games by that player regardless of board position.
        has_elo_filters = (white_elo_min != 0 or white_elo_max != 3500 or black_elo_min != 0 or black_elo_max != 3500)
        # Narrow filters strongly reduce the games-table candidate pool (a player
        # has thousands of games, not millions), so candidate-first works well.
        has_narrow_filters = bool(player_name or opponent_name)
        # Wide filters (elo/result/date/eco/event) don't narrow candidates enough —
        # SELECT … LIMIT 5000 hits the first 5000 games by id (oldest), most of
        # which won't reach the queried position. Apply them post-position instead.
        has_wide_filters = bool(result or has_elo_filters or date_from or date_to or eco_code or event_name)
        has_filters = has_narrow_filters or has_wide_filters

        # For very common positions (>50K games) WITHOUT filters, skip game_positions
        # and query games table directly. But when filters are active, always use
        # game_positions to intersect position with filters.
        DIRECT_QUERY_THRESHOLD = 50000
        if not has_filters and total > DIRECT_QUERY_THRESHOLD:
            sort_clauses = {
                'rating': 'white_elo DESC',
                'date_desc': 'date DESC',
                'date_asc': 'date ASC',
            }
            order = sort_clauses.get(sort_by, sort_clauses['rating'])
            query = f"SELECT * FROM games ORDER BY {order} LIMIT ?"
            params = [limit]

            timed_out = False
            games = []
            try:
                query_timeout[1] = time.time()
                cursor = conn.execute(query, params)
                for row in cursor.fetchall():
                    games.append(_normalize_game_row(dict(row)))
            except sqlite3.OperationalError:
                if query_timeout[0]:
                    logger.warning(f"Direct query timed out for common position board_hash={board_hash}")
                    timed_out = True
                else:
                    raise

            logger.info(f"games_by_position DIRECT: board_hash={board_hash} sort_by={sort_by} returned={len(games)} total_est={total} timed_out={timed_out}")
            conn.close()
            return jsonify({
                'games': games,
                'total': total,
                'indexed': True,
                'count_exact': cached_count is not None,
                'timeout': timed_out,
            })

        # When narrow filters are active (player_name / opponent_name), intersect
        # the position with an index-friendly name-prefix lookup in a single
        # SQL statement using EXISTS. Earlier versions materialised every
        # game_id at the position into a Python set first — that pulled ~3.3 M
        # rows for the starting FEN and dominated the request (>90 s).
        if has_narrow_filters:
            p_tok = _longest_name_token(player_name)
            o_tok = _longest_name_token(opponent_name)

            # Single-character tokens would prefix-scan a huge fraction of the
            # table — refuse and return empty rather than risk a timeout.
            if (player_name and len(p_tok) < 2) or (opponent_name and len(o_tok) < 2):
                conn.close()
                return jsonify({
                    'games': [],
                    'total': 0,
                    'indexed': True,
                })

            sort_clauses_sql = {
                'rating': 'COALESCE(white_elo, 0) + COALESCE(black_elo, 0) DESC',
                'date_desc': 'date DESC',
                'date_asc': 'date ASC',
            }
            order_sql = sort_clauses_sql.get(sort_by, sort_clauses_sql['date_desc'])

            exists_sql = (
                "EXISTS (SELECT 1 FROM game_positions gp "
                "WHERE gp.game_id = g.id AND gp.board_hash = ?)"
            )

            def _build_side(p_col: Optional[str], o_col: Optional[str]) -> Tuple[str, list]:
                """Build a single-side WHERE fragment plus its params."""
                where_parts: List[str] = []
                params: list = []
                if p_col is not None and p_tok:
                    where_parts.append(f"g.{p_col} LIKE ?")
                    params.append(f"{p_tok}%")
                if o_col is not None and o_tok:
                    where_parts.append(f"g.{o_col} LIKE ?")
                    params.append(f"{o_tok}%")
                where_parts.append(exists_sql)
                params.append(board_hash)
                return f"SELECT g.* FROM games g WHERE {' AND '.join(where_parts)}", params

            subqueries: List[Tuple[str, list]] = []
            if player_color == 'white':
                subqueries.append(_build_side(
                    'white_name_normalized' if p_tok else None,
                    'black_name_normalized' if o_tok else None,
                ))
            elif player_color == 'black':
                subqueries.append(_build_side(
                    'black_name_normalized' if p_tok else None,
                    'white_name_normalized' if o_tok else None,
                ))
            else:
                if p_tok:
                    subqueries.append(_build_side(
                        'white_name_normalized',
                        'black_name_normalized' if o_tok else None,
                    ))
                    subqueries.append(_build_side(
                        'black_name_normalized',
                        'white_name_normalized' if o_tok else None,
                    ))
                else:
                    subqueries.append(_build_side(None, 'white_name_normalized'))
                    subqueries.append(_build_side(None, 'black_name_normalized'))

            if len(subqueries) == 1:
                sub_sql, sub_params = subqueries[0]
                final_sql = f"{sub_sql} ORDER BY {order_sql} LIMIT ?"
                final_params: list = list(sub_params) + [limit]
            else:
                # UNION (not OR) — SQLite picks a covering name-index plan
                # for each branch, then merges; a single OR forces a SCAN.
                inner = " UNION ".join(s[0] for s in subqueries)
                inner_params: list = []
                for s in subqueries:
                    inner_params.extend(s[1])
                final_sql = f"SELECT * FROM ({inner}) ORDER BY {order_sql} LIMIT ?"
                final_params = inner_params + [limit]

            # `LIKE 'pattern%'` only uses the name index when LIKE is treated
            # as case-sensitive. Names are pre-normalised to lowercase, so
            # turning case-sensitive LIKE on for this connection is safe.
            conn.execute("PRAGMA case_sensitive_like = 1")

            timed_out = False
            rows: List[Dict[str, Any]] = []
            try:
                query_timeout[1] = time.time()
                cursor = conn.execute(final_sql, final_params)
                for r in cursor.fetchall():
                    rows.append(dict(r))
            except sqlite3.OperationalError:
                if query_timeout[0]:
                    logger.warning(f"Narrow-filter query timed out for board_hash={board_hash}")
                    timed_out = True
                else:
                    raise
            except Exception as e:
                logger.warning(f"Narrow-filter query error: {e}")
                timed_out = True

            try:
                year_from_int = int(date_from) if date_from else None
            except ValueError:
                year_from_int = None
            try:
                year_to_int = int(date_to) if date_to else None
            except ValueError:
                year_to_int = None
            event_lc = event_name.lower() if event_name else ''

            def _passes(g: Dict[str, Any]) -> bool:
                if result and g.get('result') != result:
                    return False
                we = g.get('white_elo') or 0
                be = g.get('black_elo') or 0
                if white_elo_min and we < white_elo_min:
                    return False
                if white_elo_max != 3500 and we > white_elo_max:
                    return False
                if black_elo_min and be < black_elo_min:
                    return False
                if black_elo_max != 3500 and be > black_elo_max:
                    return False
                if year_from_int is not None or year_to_int is not None:
                    date_str = g.get('date') or ''
                    try:
                        y = int(date_str[:4])
                    except (ValueError, TypeError):
                        return False
                    if year_from_int is not None and y < year_from_int:
                        return False
                    if year_to_int is not None and y > year_to_int:
                        return False
                if eco_code and not (g.get('eco') or '').upper().startswith(eco_code):
                    return False
                if event_lc and event_lc not in (g.get('event') or '').lower():
                    return False
                return True

            filtered = [g for g in rows if _passes(g)]
            games = [_normalize_game_row(g) for g in filtered]

            # If SQL returned fewer than the cap we have every match; otherwise
            # more games may exist beyond the cap — fall back to the
            # position-level total.
            if len(rows) < limit:
                report_total = len(filtered)
                report_count_exact = True
            else:
                report_total = total
                report_count_exact = cached_count is not None

            logger.info(
                f"games_by_position FILTERED: board_hash={board_hash} "
                f"player_name='{player_name}' opponent='{opponent_name}' "
                f"color='{player_color}' result='{result}' sort_by={sort_by} "
                f"rows={len(rows)} after_wide={len(filtered)} returned={len(games)} "
                f"timed_out={timed_out}"
            )
            conn.close()
            response_data = {
                'games': games,
                'total': report_total,
                'indexed': True,
                'count_exact': report_count_exact,
            }
            if timed_out:
                response_data['timeout'] = True
            return jsonify(response_data)

        # Unfiltered path: use 2-step pool approach for less common positions
        try:
            query_timeout[1] = time.time()
            max_gid = _get_max_game_id(conn)
            id_rows = conn.execute(
                "SELECT game_id FROM game_positions WHERE board_hash = ? AND game_id <= ? ORDER BY rowid DESC LIMIT ?",
                [board_hash, max_gid, pool_size]
            ).fetchall()
            game_ids = [r['game_id'] for r in id_rows]
        except sqlite3.OperationalError as e:
            if query_timeout[0]:
                logger.warning(f"Query timed out for board_hash={board_hash}, returning empty result")
                conn.close()
                return jsonify({
                    'games': [],
                    'total': total,
                    'indexed': True,
                    'timeout': True,
                    'count_exact': cached_count is not None,
                })
            else:
                raise

        if not game_ids:
            _position_count_cache[board_hash] = 0
            conn.close()
            return jsonify({'games': [], 'total': 0, 'indexed': True})

        # Update total estimate if pool wasn't full (only meaningful when no
        # post-filters are applied — otherwise filtered_total is set below).
        if len(game_ids) < pool_size and not has_wide_filters:
            total = len(game_ids)
            _position_count_cache[board_hash] = total

        placeholders = ','.join('?' * len(game_ids))
        where_clauses = [f"id IN ({placeholders})"]
        filter_params: list = list(game_ids)

        # Apply wide filters as post-filters on the position pool. These filters
        # don't narrow the games-table candidate set effectively (e.g. white_elo
        # >= 1000 matches millions), so we apply them after the position lookup.
        if result:
            where_clauses.append("result = ?")
            filter_params.append(result)
        if white_elo_min != 0:
            where_clauses.append("white_elo >= ?")
            filter_params.append(white_elo_min)
        if white_elo_max != 3500:
            where_clauses.append("white_elo <= ?")
            filter_params.append(white_elo_max)
        if black_elo_min != 0:
            where_clauses.append("black_elo >= ?")
            filter_params.append(black_elo_min)
        if black_elo_max != 3500:
            where_clauses.append("black_elo <= ?")
            filter_params.append(black_elo_max)
        if date_from:
            try:
                where_clauses.append("CAST(substr(date, 1, 4) AS INTEGER) >= ?")
                filter_params.append(int(date_from))
            except ValueError:
                pass
        if date_to:
            try:
                where_clauses.append("CAST(substr(date, 1, 4) AS INTEGER) <= ?")
                filter_params.append(int(date_to))
            except ValueError:
                pass
        if eco_code:
            where_clauses.append("eco LIKE ?")
            filter_params.append(f"{eco_code}%")
        if event_name:
            where_clauses.append("event LIKE ?")
            filter_params.append(f"%{event_name}%")

        where = " AND ".join(where_clauses)

        sort_clauses = {
            'rating': 'COALESCE(white_elo, 0) + COALESCE(black_elo, 0) DESC',
            'date_desc': 'date DESC',
            'date_asc': 'date ASC',
        }
        order = sort_clauses.get(sort_by, sort_clauses['rating'])

        # When wide filters are applied, count the filtered subset so the UI
        # shows the true number of matching games at this position.
        filtered_total = None
        if has_wide_filters:
            try:
                count_row = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM games WHERE {where}",
                    filter_params
                ).fetchone()
                filtered_total = count_row['cnt']
            except sqlite3.OperationalError:
                pass

        query = f"SELECT * FROM games WHERE {where} ORDER BY {order} LIMIT ?"
        params = list(filter_params) + [limit]

        # Execute query with timeout handling
        timed_out = False
        games = []
        try:
            query_timeout[1] = time.time()
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                games.append(_normalize_game_row(dict(row)))
        except sqlite3.OperationalError as e:
            if query_timeout[0]:
                logger.warning(f"Final query timed out in games_by_position")
                timed_out = True
            else:
                raise
        except Exception as e:
            logger.warning(f"Query error in games_by_position: {e}")
            timed_out = True

        # When wide filters are applied, report the filtered count instead of
        # the all-position count; otherwise the UI claims more games than it
        # actually returns.
        report_total = filtered_total if filtered_total is not None else total
        report_count_exact = (filtered_total is not None) or (cached_count is not None)

        logger.info(f"games_by_position result: board_hash={board_hash} player_name='{player_name}' opponent='{opponent_name}' color='{player_color}' result='{result}' sort_by={sort_by} wide_filters={has_wide_filters} returned={len(games)} total_est={report_total} timed_out={timed_out}")
        conn.close()
        response_data = {
            'games': games,
            'total': report_total,
            'indexed': True,
            'count_exact': report_count_exact,
        }
        if timed_out:
            response_data['timeout'] = True
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error in games_by_position: {e}")
        try:
            conn.close()
        except:
            pass
        # Return HTTP 200 with timeout flag instead of 500 when query is interrupted
        return jsonify({
            'games': [],
            'total': 0,
            'indexed': True,
            'timeout': True,
            'error': str(e)
        }), 200


@openings_bp.route('/games/<int:game_id>/pgn', methods=['GET'])
@verify_clerk_token
@with_cache(max_age=300)
def get_game_pgn(game_id):
    """Fetch PGN for a single game on demand."""
    if not check_internal_db_exists():
        return jsonify({'error': 'Database not available'}), 503

    conn = get_internal_db_connection()
    try:
        row = conn.execute("SELECT pgn_offset, pgn_length FROM games WHERE id = ?", [game_id]).fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Game not found'}), 404
        conn.close()

        with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
            f.seek(row['pgn_offset'])
            pgn_text = f.read(row['pgn_length'])

        return jsonify({'pgn': pgn_text})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@openings_bp.route('/games/lichess/<game_id>/pgn', methods=['GET'])
@verify_clerk_token
@with_cache(max_age=3600)
def get_lichess_game_pgn(game_id):
    """Fetch PGN for a Lichess game on demand."""
    try:
        resp = requests.get(
            f'https://lichess.org/game/export/{game_id}',
            headers={'Accept': 'application/x-chess-pgn'},
            timeout=10
        )
        if resp.status_code != 200:
            return jsonify({'error': f'Lichess returned {resp.status_code}'}), resp.status_code
        return jsonify({'pgn': resp.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


_PGN_TAG_RE = re.compile(r'^\[(\w+)\s+"(.*)"\]\s*$')


def _parse_pgn_tags(pgn_text: str) -> dict:
    """Extract the leading [Tag "value"] header block from a PGN string."""
    tags = {}
    for line in (pgn_text or '').splitlines():
        s = line.strip()
        if s.startswith('['):
            m = _PGN_TAG_RE.match(s)
            if m:
                tags[m.group(1)] = m.group(2)
        elif s:
            break  # reached movetext — headers are done
    return tags


def _meta_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _lichess_game_meta(game_id: str):
    """Fetch public header-only metadata for a Lichess game (no moves)."""
    try:
        resp = requests.get(
            f'https://lichess.org/game/export/{game_id}',
            headers={'Accept': 'application/x-chess-pgn'},
            params={'moves': 'false', 'clocks': 'false', 'evals': 'false', 'tags': 'true'},
            timeout=10,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 502
    if resp.status_code == 404:
        return jsonify({'error': 'Game not found'}), 404
    if resp.status_code != 200:
        return jsonify({'error': f'Lichess returned {resp.status_code}'}), resp.status_code
    tags = _parse_pgn_tags(resp.text)
    return jsonify({
        'white': tags.get('White'),
        'black': tags.get('Black'),
        'result': tags.get('Result'),
        'event': tags.get('Event'),
        'date': tags.get('Date') or tags.get('UTCDate'),
        'white_elo': _meta_int(tags.get('WhiteElo')),
        'black_elo': _meta_int(tags.get('BlackElo')),
    })


@openings_bp.route('/games/<int:game_id>/meta', methods=['GET'])
@with_cache(max_age=3600)
def get_game_meta(game_id):
    """Public game metadata for Open Graph link previews.

    PUBLIC — no Clerk auth. Powers the `/g/<slug>` short-link OG cards so a
    shared game unfurls nicely in WhatsApp/Telegram. Returns ONLY header
    fields (players, result, event, date, elos) — never the PGN or move list,
    which stay behind the auth-gated `/pgn` endpoints.
    """
    source = request.args.get('source', 'twic').strip().lower()
    if source not in ('twic', 'lichess'):
        return jsonify({'error': f'Unknown source: {source}'}), 400

    if source == 'lichess':
        return _lichess_game_meta(str(game_id))

    # twic / internal master database
    if not check_internal_db_exists():
        return jsonify({'error': 'Database not available'}), 503

    conn = get_internal_db_connection()
    try:
        row = conn.execute(
            "SELECT white_name, black_name, result, event, date, white_elo, black_elo "
            "FROM games WHERE id = ?",
            [game_id],
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({'error': 'Game not found'}), 404

    return jsonify({
        'white': row['white_name'],
        'black': row['black_name'],
        'result': row['result'],
        'event': row['event'],
        'date': row['date'],
        'white_elo': row['white_elo'],
        'black_elo': row['black_elo'],
    })


def _twic_game_pgn(game_id: int) -> Optional[str]:
    """Read a master game's PGN text from the TWIC file by DB offset."""
    conn = get_internal_db_connection()
    try:
        row = conn.execute(
            "SELECT pgn_offset, pgn_length FROM games WHERE id = ?", [game_id]
        ).fetchone()
    finally:
        conn.close()
    if not row or row['pgn_offset'] is None or not row['pgn_length']:
        return None
    with open(TWIC_PGN_PATH, 'r', errors='replace') as f:
        f.seek(row['pgn_offset'])
        return f.read(row['pgn_length'])


def _lichess_game_pgn(game_id: str) -> Optional[str]:
    """Fetch a Lichess game's full PGN (with moves) for rendering."""
    try:
        resp = requests.get(
            f'https://lichess.org/game/export/{game_id}',
            headers={'Accept': 'application/x-chess-pgn'},
            timeout=10,
        )
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    return resp.text


@openings_bp.route('/games/<int:game_id>/thumbnail.png', methods=['GET'])
def get_game_thumbnail(game_id):
    """Public board-image thumbnail for Open Graph link previews.

    PUBLIC — no Clerk auth. Renders ONLY the game's FINAL position as a PNG so
    a shared `/g/<slug>` link unfurls with an actual chessboard. Never exposes
    the PGN, move list, or any identity. Unknown id/source → 404.
    """
    source = request.args.get('source', 'twic').strip().lower()
    if source not in ('twic', 'lichess'):
        return jsonify({'error': f'Unknown source: {source}'}), 400

    if source == 'lichess':
        pgn_text = _lichess_game_pgn(str(game_id))
    else:
        if not check_internal_db_exists():
            return jsonify({'error': 'Database not available'}), 503
        pgn_text = _twic_game_pgn(game_id)

    png = render_final_position_png(pgn_text) if pgn_text else None
    if png is None:
        return jsonify({'error': 'Game not found'}), 404

    resp = Response(png, mimetype='image/png')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@openings_bp.route('/games/position-count', methods=['GET'])
@verify_clerk_token
@with_cache(max_age=300)
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


@openings_bp.route('/_cache/invalidate', methods=['POST'])
def invalidate_position_count_cache():
    """Clear the in-memory position-count cache. Localhost-only.

    Called by the TWIC incremental indexer after new games are committed so
    the "N games reach this position" chip reflects the freshly imported set.
    """
    if request.remote_addr not in ("127.0.0.1", "::1", "localhost"):
        return jsonify({'error': 'forbidden'}), 403
    prior_size = len(_position_count_cache)
    _position_count_cache.clear()
    logger.info(f"Position count cache invalidated: cleared {prior_size} entries")
    return jsonify({'cleared': True, 'count': prior_size})


_candidates_cache = {}   # board_hash -> (timestamp, result_dict)
_CANDIDATES_CACHE_TTL = 600  # 10 minutes

@openings_bp.route('/positions/candidates', methods=['GET'])
@require_active_membership
@with_cache(max_age=300)
def position_candidates():
    """Return candidate next moves for a FEN using TWIC position index.

    Used by Analysis tab as primary local source; frontend can still fallback
    to external ChessDB when this endpoint has no data.
    """
    import time as _time

    fen = request.args.get('fen', '')
    if not fen:
        return jsonify({'status': 'error', 'message': 'Missing fen parameter', 'moves': []}), 400

    limit = min(int(request.args.get('limit', 12)), 30)

    try:
        board = chess.Board(fen)
    except Exception:
        return jsonify({'status': 'error', 'message': 'Invalid FEN', 'moves': []}), 400

    if not check_internal_db_exists():
        return jsonify({'status': 'ok', 'source': 'twic', 'moves': [], 'indexed': False})

    board_hash = _get_board_hash(fen)

    # Check cache first
    cached = _candidates_cache.get(board_hash)
    if cached:
        ts, result = cached
        if _time.time() - ts < _CANDIDATES_CACHE_TTL:
            # Re-apply limit if needed
            result_copy = dict(result)
            result_copy['moves'] = result_copy['moves'][:limit]
            return jsonify(result_copy)

    conn = get_internal_db_connection()
    try:
        if not _has_position_index(conn):
            conn.close()
            return jsonify({'status': 'ok', 'source': 'twic', 'moves': [], 'indexed': False})

        side_to_move = fen.split(' ')[1] if len(fen.split(' ')) > 1 else 'w'

        # ── Fastest path: pre-aggregated move_stats table (<5ms) ──
        has_move_stats = False
        try:
            test_stats = conn.execute(
                "SELECT 1 FROM move_stats WHERE board_hash = ? LIMIT 1",
                [board_hash]
            ).fetchone()
            has_move_stats = test_stats is not None
        except Exception:
            pass

        if has_move_stats:
            sql_rows = conn.execute(
                '''
                SELECT move_san, games as cnt,
                       white_wins as w_wins, black_wins as b_wins, draws,
                       avg_elo, avg_year
                FROM move_stats
                WHERE board_hash = ?
                ORDER BY games DESC
                LIMIT ?
                ''',
                [board_hash, limit]
            ).fetchall()
            conn.close()

            if not sql_rows:
                return jsonify({'status': 'ok', 'source': 'twic', 'moves': [], 'indexed': True})

            total_all_games = sum(r['cnt'] for r in sql_rows)
            moves = []
            for idx, r in enumerate(sql_rows, start=1):
                total = max(r['cnt'], 1)
                white_wins = r['w_wins'] or 0
                black_wins = r['b_wins'] or 0
                draws = r['draws'] or 0
                avg_elo = round(r['avg_elo']) if r['avg_elo'] else None
                avg_year = round(r['avg_year']) if r['avg_year'] else None

                if side_to_move == 'w':
                    winrate = ((white_wins + 0.5 * draws) / total) * 100.0
                else:
                    winrate = ((black_wins + 0.5 * draws) / total) * 100.0

                score_cp = int(round((winrate - 50.0) * 8.0))
                note = 'Best' if idx == 1 else ('Good' if idx <= 3 else 'Playable')
                percentage = round((total / total_all_games * 100), 1) if total_all_games > 0 else 0

                moves.append({
                    'uci': '',
                    'san': r['move_san'],
                    'score': str(score_cp),
                    'winrate': f"{winrate:.1f}",
                    'rank': str(idx),
                    'note': note,
                    'count': total,
                    'white_wins': white_wins,
                    'draws': draws,
                    'black_wins': black_wins,
                    'avg_elo': avg_elo,
                    'avg_year': avg_year,
                    'percentage': percentage,
                })

            result = {'status': 'ok', 'source': 'twic', 'indexed': True, 'total_games': total_all_games, 'moves': moves}
            _candidates_cache[board_hash] = (_time.time(), result)
            return jsonify(result)

        # ── Fallback: PGN parsing (used until backfill completes) ──
        rows = conn.execute(
            '''
            SELECT gp.game_id, gp.ply,
                   g.result, g.white_elo, g.black_elo, g.year,
                   g.pgn_offset, g.pgn_length
            FROM game_positions gp
            JOIN games g ON g.id = gp.game_id
            WHERE gp.board_hash = ?
            LIMIT 1000
            ''',
            [board_hash]
        ).fetchall()

        if not rows:
            conn.close()
            return jsonify({'status': 'ok', 'source': 'twic', 'moves': [], 'indexed': True})

        conn.close()

        rows_sorted = sorted(rows, key=lambda r: r['pgn_offset'])
        move_stats = {}

        try:
            pgn_file = open(TWIC_PGN_PATH, 'r', errors='replace')
        except Exception:
            return jsonify({'status': 'error', 'message': 'PGN file not available', 'moves': []}), 500

        for r in rows_sorted:
            ply_target = r['ply'] + 1
            san = None
            uci = None
            try:
                pgn_file.seek(r['pgn_offset'])
                pgn_text = pgn_file.read(r['pgn_length'])
                game_obj = chess.pgn.read_game(io.StringIO(pgn_text))
                if game_obj:
                    b = game_obj.board()
                    for ply_i, mv in enumerate(game_obj.mainline_moves(), start=1):
                        if ply_i == ply_target:
                            san = b.san(mv)
                            uci = mv.uci()
                            break
                        b.push(mv)
            except Exception:
                continue

            if not san:
                continue

            if san not in move_stats:
                move_stats[san] = {
                    'uci': uci, 'count': 0,
                    'white_wins': 0, 'draws': 0, 'black_wins': 0,
                    'elo_sum': 0, 'elo_count': 0,
                    'year_sum': 0, 'year_count': 0,
                }

            ms = move_stats[san]
            ms['count'] += 1
            result = r['result']
            if result == '1-0':
                ms['white_wins'] += 1
            elif result == '0-1':
                ms['black_wins'] += 1
            elif result == '1/2-1/2':
                ms['draws'] += 1

            w_elo = r['white_elo'] or 0
            b_elo = r['black_elo'] or 0
            if w_elo > 0 and b_elo > 0:
                ms['elo_sum'] += (w_elo + b_elo) / 2.0
                ms['elo_count'] += 1
            yr = r['year'] or 0
            if yr > 0:
                ms['year_sum'] += yr
                ms['year_count'] += 1

        pgn_file.close()

        if not move_stats:
            return jsonify({'status': 'ok', 'source': 'twic', 'moves': [], 'indexed': True})

        sorted_moves = sorted(move_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:limit]
        total_all_games = sum(ms['count'] for _, ms in sorted_moves)

        moves = []
        for idx, (san, ms) in enumerate(sorted_moves, start=1):
            total = max(ms['count'], 1)
            white_wins = ms['white_wins']
            black_wins = ms['black_wins']
            draws = ms['draws']
            avg_elo = round(ms['elo_sum'] / ms['elo_count']) if ms['elo_count'] > 0 else None
            avg_year = round(ms['year_sum'] / ms['year_count']) if ms['year_count'] > 0 else None

            if side_to_move == 'w':
                winrate = ((white_wins + 0.5 * draws) / total) * 100.0
            else:
                winrate = ((black_wins + 0.5 * draws) / total) * 100.0

            score_cp = int(round((winrate - 50.0) * 8.0))
            note = 'Best' if idx == 1 else ('Good' if idx <= 3 else 'Playable')
            percentage = round((total / total_all_games * 100), 1) if total_all_games > 0 else 0

            moves.append({
                'uci': ms['uci'] or '',
                'san': san,
                'score': str(score_cp),
                'winrate': f"{winrate:.1f}",
                'rank': str(idx),
                'note': note,
                'count': total,
                'white_wins': white_wins,
                'draws': draws,
                'black_wins': black_wins,
                'avg_elo': avg_elo,
                'avg_year': avg_year,
                'percentage': percentage,
            })

        result = {'status': 'ok', 'source': 'twic', 'indexed': True, 'total_games': total_all_games, 'moves': moves}
        _candidates_cache[board_hash] = (_time.time(), result)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in position_candidates: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'status': 'error', 'message': str(e), 'moves': []}), 500


_top_players_cache = {}   # board_hash -> (timestamp, result_list)
_TOP_PLAYERS_CACHE_TTL = 600  # 10 minutes

@openings_bp.route('/positions/top-players', methods=['GET'])
@verify_clerk_token
@with_cache(max_age=300)
def position_top_players():
    """Return top-rated players who played at a given position."""
    import time as _time

    fen = request.args.get('fen', '')
    if not fen:
        return jsonify({'status': 'error', 'message': 'Missing fen parameter', 'players': []}), 400

    limit = min(int(request.args.get('limit', 10)), 30)

    if not check_internal_db_exists():
        return jsonify({'status': 'ok', 'players': []})

    board_hash = _get_board_hash(fen)

    # Check cache
    cached = _top_players_cache.get(board_hash)
    if cached:
        ts, players_list = cached
        if _time.time() - ts < _TOP_PLAYERS_CACHE_TTL:
            return jsonify({'status': 'ok', 'players': players_list[:limit]})

    conn = get_internal_db_connection()
    try:
        if not _has_position_index(conn):
            conn.close()
            return jsonify({'status': 'ok', 'players': []})

        # Sample up to 2000 game_positions rows then extract player info.
        # Without LIMIT, the starting position (4M+ rows) causes 20s+ queries.
        rows = conn.execute('''
            SELECT name, MAX(elo) as elo, MAX(title) as title, COUNT(*) as games
            FROM (
                SELECT g.white_name as name, g.white_elo as elo, g.white_title as title
                FROM game_positions gp
                JOIN games g ON g.id = gp.game_id
                WHERE gp.board_hash = ? AND g.white_elo > 0
                LIMIT 2000
            )
            GROUP BY name
            ORDER BY elo DESC
            LIMIT ?
        ''', [board_hash, limit]).fetchall()

        conn.close()

        players = [{'name': r['name'], 'elo': r['elo'], 'title': r['title'] or '', 'games': r['games']} for r in rows]
        _top_players_cache[board_hash] = (_time.time(), players)
        return jsonify({'status': 'ok', 'players': players})

    except Exception as e:
        logger.error(f"Error in position_top_players: {e}")
        conn.close()
        return jsonify({'status': 'error', 'message': str(e), 'players': []}), 500


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

    # New parameters for Chess.com/Lichess
    archive_months = int(request.args.get('archive_months', 3))
    player_color = request.args.get('player_color', '').strip().lower()
    result_filter = request.args.get('result_filter', '').strip().lower()

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

                for event in fetch_lichess_games_progressive(username, fen, min_rating, max_games, archive_months, player_color, result_filter):
                    yield f"data: {json.dumps(event)}\n\n"

            elif source == 'chesscom':
                if not username:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Username required'})}\n\n"
                    return

                for event in fetch_chesscom_games_progressive(username, fen, min_rating, max_games, archive_months, player_color, result_filter):
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
