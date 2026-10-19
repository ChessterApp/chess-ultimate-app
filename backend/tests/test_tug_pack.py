"""
Tests for the Tug of War pack (services/tug_pack.py + GET /api/puzzles/tug/pack).

Uses a fixture SQLite DB with the real puzzles + puzzle_themes schema (never the
prod file).
"""

import random
import sqlite3

import chess
import pytest
from flask import Flask

from api.tug_of_war import tug_of_war_bp
from services import tug_pack
from services.puzzle_rush_source import PuzzleSource

# Black to move (setup a7a6), then White mates with Rd8#.
M1_FEN = '6k1/p4ppp/8/8/8/8/5PPP/3RR1K1 b - - 0 1'
M1_MOVES = 'a7a6 d1d8'
# White to move (setup h2h3), then Black plays e7e5, White replies, Black mates.
FORK_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
FORK_MOVES = 'h2h3 e7e5 a2a3 d8h4'

THEME_CYCLE = ('mateIn1 backRankMate', 'fork short', 'pin middlegame', 'skewer endgame')


def make_db(path, rows):
    """rows: iterable of (id, fen, moves, rating, themes)."""
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE puzzles(id TEXT PRIMARY KEY, fen TEXT, moves TEXT, rating INTEGER,
            rating_deviation INTEGER, popularity INTEGER, nb_plays INTEGER, themes TEXT,
            game_url TEXT, opening_tags TEXT);
        CREATE INDEX idx_puzzles_rating ON puzzles(rating);
        CREATE TABLE puzzle_themes(puzzle_id TEXT NOT NULL, theme TEXT NOT NULL, rating INTEGER NOT NULL,
            PRIMARY KEY (theme, rating, puzzle_id)) WITHOUT ROWID;
    ''')
    for pid, fen, moves, rating, themes in rows:
        conn.execute('INSERT INTO puzzles(id, fen, moves, rating, rating_deviation, popularity, nb_plays, themes) '
                     'VALUES (?, ?, ?, ?, 75, 90, 500, ?)', (pid, fen, moves, rating, themes))
        conn.executemany('INSERT INTO puzzle_themes VALUES (?, ?, ?)',
                         [(pid, t, rating) for t in themes.split()])
    conn.commit()
    conn.close()
    return str(path)


@pytest.fixture
def source(tmp_path):
    rows = []
    for i, rating in enumerate(range(300, 2600, 5)):
        themes = THEME_CYCLE[i % len(THEME_CYCLE)]
        fen, moves = (M1_FEN, M1_MOVES) if 'mateIn1' in themes else (FORK_FEN, FORK_MOVES)
        rows.append((f'p{i:04d}', fen, moves, rating, themes))
    return PuzzleSource(make_db(tmp_path / 'p.db', rows))


@pytest.fixture
def client(source, monkeypatch):
    monkeypatch.setattr(tug_pack, 'get_puzzle_source', lambda: source)
    app = Flask(__name__)
    app.register_blueprint(tug_of_war_bp)
    return app.test_client()


def ids(puzzles):
    return [p['id'] for p in puzzles]


@pytest.mark.parametrize('level', list(tug_pack.LEVEL_BANDS))
def test_band_respected_per_level(source, level):
    lo, hi = tug_pack.LEVEL_BANDS[level]
    puzzles = tug_pack.pack(level, count=40, source=source, rng=random.Random(1))
    assert len(puzzles) == 40
    assert all(lo <= p['rating'] <= hi for p in puzzles)


def test_theme_filter_matches_any_requested_tag(source):
    puzzles = tug_pack.pack('knight', ['fork', 'pin'], count=30, source=source, rng=random.Random(2))
    assert len(puzzles) == 30
    assert all({'fork', 'pin'} & set(p['themes']) for p in puzzles)
    assert {'fork', 'pin'} <= {t for p in puzzles for t in p['themes']}  # both themes mixed in


def test_no_duplicate_ids_and_stops_when_band_runs_dry(source):
    # Rook band 1200-1600 holds 81 fixture puzzles; asking for 120 returns all, once each.
    puzzles = tug_pack.pack('rook', count=120, source=source, rng=random.Random(3))
    assert len(puzzles) == 81
    assert len(set(ids(puzzles))) == len(puzzles)


def test_exclude_never_repeats(source):
    first = tug_pack.pack('pawn', count=40, source=source, rng=random.Random(4))
    second = tug_pack.pack('pawn', count=40, exclude=ids(first), source=source, rng=random.Random(4))
    assert not set(ids(first)) & set(ids(second))


def test_setup_move_applied(source):
    for p in tug_pack.pack('queen', count=20, source=source, rng=random.Random(5)) + \
            tug_pack.pack('pawn', ['mateIn1'], count=20, source=source, rng=random.Random(5)):
        original = FORK_FEN if p['moves'] == FORK_MOVES.split()[1:] else M1_FEN
        board = chess.Board(p['fen'])
        # Solver (the side NOT to move in the Lichess fen) is to move now.
        assert board.turn != chess.Board(original).turn
        assert chess.Move.from_uci(p['moves'][0]) in board.legal_moves
        assert len(p['moves']) % 2 == 1


def test_endpoint_shape(client):
    res = client.get('/api/puzzles/tug/pack?level=knight&themes=fork,skewer&count=10')
    assert res.status_code == 200
    body = res.get_json()
    assert body['source'] == 'lichess'
    assert len(body['puzzles']) == 10
    assert set(body['puzzles'][0]) == {'id', 'fen', 'moves', 'rating', 'themes'}
    assert all({'fork', 'skewer'} & set(p['themes']) for p in body['puzzles'])


def test_endpoint_default_count_and_exclude(client):
    first = client.get('/api/puzzles/tug/pack?level=queen').get_json()['puzzles']
    assert len(first) == tug_pack.DEFAULT_COUNT
    excl = ','.join(ids(first))
    second = client.get(f'/api/puzzles/tug/pack?level=queen&count=120&exclude={excl}').get_json()['puzzles']
    assert len(second) == 101  # 161 queen-band puzzles minus the 60 excluded
    assert not set(ids(first)) & set(ids(second))


def test_endpoint_caps_count(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(tug_pack, 'pack', lambda level, themes, count, exclude: seen.update(count=count) or [])
    assert client.get('/api/puzzles/tug/pack?level=pawn&count=500').status_code == 200
    assert seen['count'] == tug_pack.MAX_COUNT


@pytest.mark.parametrize('query', ['', 'level=king', 'level=pawn&themes=zugzwang',
                                   'level=pawn&count=abc', 'level=pawn&count=0'])
def test_bad_params_400(client, query):
    assert client.get(f'/api/puzzles/tug/pack?{query}').status_code == 400


def test_pack_rating_band_respected(source):
    puzzles = tug_pack.pack_rating(1340, 75, count=10, source=source, rng=random.Random(6))
    assert len(puzzles) == 10
    assert all(1265 <= p['rating'] <= 1415 for p in puzzles)


def test_rating_band_clamped():
    assert tug_pack.rating_band(420, 75) == (400, 495)
    assert tug_pack.rating_band(2790, 100) == (2690, 2800)


def test_level_pack_delegates_to_band(source):
    a = tug_pack.pack('knight', count=15, source=source, rng=random.Random(7))
    b = tug_pack.pack_band(800, 1200, count=15, source=source, rng=random.Random(7))
    assert ids(a) == ids(b)


def test_pack_rating_widens_when_band_runs_dry(source):
    # 1000±25 holds 11 fixture puzzles; widening ×2 (50, 100) fills a pack of 30 without repeats.
    puzzles = tug_pack.pack_rating(1000, 25, count=30, source=source, rng=random.Random(8))
    assert len(puzzles) == 30
    assert len(set(ids(puzzles))) == 30
    assert all(900 <= p['rating'] <= 1100 for p in puzzles)
    assert sum(975 <= p['rating'] <= 1025 for p in puzzles) == 11  # narrow band drained first


def test_pack_rating_widens_at_most_three_times(source):
    # 25 → 50 → 100 → 200: at most 1000±200 = 81 puzzles, never the whole DB.
    puzzles = tug_pack.pack_rating(1000, 25, count=120, source=source, rng=random.Random(9))
    assert len(puzzles) == 81
    assert all(800 <= p['rating'] <= 1200 for p in puzzles)


def test_pack_rating_honours_themes_and_exclude(source):
    first = tug_pack.pack_rating(1500, 75, ['fork'], count=5, source=source, rng=random.Random(10))
    assert all('fork' in p['themes'] for p in first)
    second = tug_pack.pack_rating(1500, 75, ['fork'], count=5, exclude=ids(first), source=source,
                                  rng=random.Random(10))
    assert not set(ids(first)) & set(ids(second))


def test_endpoint_rating_pack(client):
    res = client.get('/api/puzzles/tug/pack?rating=1340&spread=50&count=10')
    assert res.status_code == 200
    puzzles = res.get_json()['puzzles']
    assert len(puzzles) == 10
    assert all(1290 <= p['rating'] <= 1390 for p in puzzles)


def test_endpoint_rating_default_spread(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(tug_pack, 'pack_rating',
                        lambda rating, spread, themes, count, exclude: seen.update(r=rating, s=spread, c=count) or [])
    assert client.get('/api/puzzles/tug/pack?rating=900&count=10').status_code == 200
    assert seen == {'r': 900, 's': tug_pack.DEFAULT_SPREAD, 'c': 10}


@pytest.mark.parametrize('query,error', [
    ('level=pawn&rating=900', 'invalid_params'),
    ('spread=75', 'invalid_params'),
    ('rating=abc', 'invalid_rating'),
    ('rating=399', 'invalid_rating'),
    ('rating=2801', 'invalid_rating'),
    ('rating=900&spread=24', 'invalid_spread'),
    ('rating=900&spread=401', 'invalid_spread'),
    ('rating=900&spread=x', 'invalid_spread'),
    ('rating=900&count=0', 'invalid_count'),
])
def test_rating_bad_params_400(client, query, error):
    res = client.get(f'/api/puzzles/tug/pack?{query}')
    assert res.status_code == 400
    assert res.get_json()['error'] == error


def test_db_opened_read_only(source):
    with pytest.raises(sqlite3.OperationalError):
        source._conn().execute("INSERT INTO puzzle_themes VALUES ('x', 'fork', 500)")
