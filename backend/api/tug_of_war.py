"""
Tug of War API — `GET /api/puzzles/tug/pack`, public and stateless.

Query: EITHER level (pawn|knight|rook|queen) OR rating (400..2800) + optional
spread (25..400, default 75) — exactly one of level/rating — themes (comma list of Tug of War
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


def _int_in(name: str, lo: int, hi: int, default: int | None) -> int | None:
    """Integer query param within lo..hi, `default` when absent, None when invalid."""
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if lo <= value <= hi else None


@tug_of_war_bp.route('/api/puzzles/tug/pack', methods=['GET'])
def get_pack():
    level = request.args.get('level')
    rating = request.args.get('rating')
    if (level is None) == (rating is None):
        return _bad('invalid_params')
    if level is not None and level not in tug_pack.LEVEL_BANDS:
        return _bad('invalid_level')
    if rating is not None:
        rating = _int_in('rating', tug_pack.RATING_MIN, tug_pack.RATING_MAX, None)
        if rating is None:
            return _bad('invalid_rating')
        spread = _int_in('spread', tug_pack.SPREAD_MIN, tug_pack.SPREAD_MAX, tug_pack.DEFAULT_SPREAD)
        if spread is None:
            return _bad('invalid_spread')
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
    count = min(count, tug_pack.MAX_COUNT)
    if level is not None:
        puzzles = tug_pack.pack(level, themes, count, exclude)
    else:
        puzzles = tug_pack.pack_rating(rating, spread, themes, count, exclude)
    return jsonify({'puzzles': puzzles, 'source': 'lichess'})
