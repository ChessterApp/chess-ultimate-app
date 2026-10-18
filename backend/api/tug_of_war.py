"""
Tug of War API — `GET /api/puzzles/tug/pack`, public and stateless.

Query: level (pawn|knight|rook|queen, required), themes (comma list of Tug of War
theme tags, optional), count (default 60, max 120), exclude (comma puzzle ids
already served this match, so refills never repeat).
"""

from flask import Blueprint, jsonify, request

from services import tug_pack

tug_of_war_bp = Blueprint('tug_of_war', __name__)


def _csv(name: str) -> list[str]:
    return [v for v in (request.args.get(name) or '').split(',') if v.strip()]


def _bad(error: str):
    return jsonify({'error': error}), 400


@tug_of_war_bp.route('/api/puzzles/tug/pack', methods=['GET'])
def get_pack():
    level = request.args.get('level')
    if level not in tug_pack.LEVEL_BANDS:
        return _bad('invalid_level')
    themes = [t.strip() for t in _csv('themes')]
    if any(t not in tug_pack.THEMES for t in themes):
        return _bad('invalid_theme')
    try:
        count = int(request.args.get('count', tug_pack.DEFAULT_COUNT))
    except ValueError:
        return _bad('invalid_count')
    if count < 1:
        return _bad('invalid_count')
    exclude = [i.strip() for i in _csv('exclude')][:tug_pack.MAX_EXCLUDE]
    puzzles = tug_pack.pack(level, themes, min(count, tug_pack.MAX_COUNT), exclude)
    return jsonify({'puzzles': puzzles, 'source': 'lichess'})
