"""
Tests for services/puzzle_rush_source.py — ramp formula, band selection and
widening, quality filter, exclusions, read-only access.

Uses a tiny fixture SQLite DB with the real puzzles schema (never the 1.9 GB file).
"""

import random
import sqlite3

import pytest

from services.puzzle_rush_source import NoPuzzleAvailable, PuzzleSource, target_rating

# Black to move (setup a7a6), then White mates with Rd8# (Re8# also mates).
M1_FEN = '6k1/p4ppp/8/8/8/8/5PPP/3RR1K1 b - - 0 1'
M1_MOVES = 'a7a6 d1d8'


def make_puzzles_db(path, puzzles):
    """puzzles: iterable of (id, fen, moves, rating, rd, popularity)."""
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE puzzles(id TEXT PRIMARY KEY, fen TEXT, moves TEXT, rating INTEGER,
            rating_deviation INTEGER, popularity INTEGER, nb_plays INTEGER, themes TEXT,
            game_url TEXT, opening_tags TEXT);
        CREATE INDEX idx_puzzles_rating ON puzzles(rating);
    ''')
    conn.executemany(
        'INSERT INTO puzzles(id, fen, moves, rating, rating_deviation, popularity, nb_plays) '
        'VALUES (?, ?, ?, ?, ?, ?, 500)',
        list(puzzles),
    )
    conn.commit()
    conn.close()
    return str(path)


def m1(pid, rating, rd=75, pop=90):
    return (pid, M1_FEN, M1_MOVES, rating, rd, pop)


@pytest.fixture
def rng():
    return random.Random(7)


def test_ramp_formula():
    assert [target_rating(i) for i in (0, 5, 10, 20, 30, 40)] == [400, 640, 910, 1540, 2290, 3160]
    assert target_rating(1) == 446  # 400 + 45 + 0.6


def test_pick_stays_in_band(tmp_path, rng):
    db = make_puzzles_db(tmp_path / 'p.db', [m1(f'p{r}', r) for r in range(300, 3000, 10)])
    source = PuzzleSource(db)
    for i in range(0, 35):
        target = target_rating(i)
        for _ in range(5):
            assert abs(source.pick(i, rng=rng)['rating'] - target) <= 30


def test_band_widens_when_empty(tmp_path, rng):
    db = make_puzzles_db(tmp_path / 'p.db', [m1('far', 700)])
    # Target 400: ±30/60/120 are empty, ±480 reaches 700.
    assert PuzzleSource(db).pick(0, rng=rng)['id'] == 'far'


def test_raises_when_db_empty(tmp_path, rng):
    db = make_puzzles_db(tmp_path / 'p.db', [])
    with pytest.raises(NoPuzzleAvailable):
        PuzzleSource(db).pick(0, rng=rng)


def test_excluded_ids_never_repeat(tmp_path, rng):
    db = make_puzzles_db(tmp_path / 'p.db', [m1(f'b{i}', 395 + i) for i in range(5)] + [m1('outside', 600)])
    source = PuzzleSource(db)
    used = []
    for _ in range(5):
        used.append(source.pick(0, used, rng)['id'])
    assert sorted(used) == [f'b{i}' for i in range(5)]
    # Band exhausted by exclusions → widens instead of repeating.
    assert source.pick(0, used, rng)['id'] == 'outside'


def test_quality_filter_applies_in_dense_band(tmp_path, rng):
    good = [m1(f'g{i}', 400 + i) for i in range(20)]
    bad = [m1(f'rd{i}', 400 + i, rd=200) for i in range(20)] + [m1(f'pop{i}', 400 + i, pop=10) for i in range(20)]
    source = PuzzleSource(make_puzzles_db(tmp_path / 'p.db', good + bad))
    picks = {source.pick(0, rng=rng)['id'] for _ in range(40)}
    assert picks and all(p.startswith('g') for p in picks)


def test_quality_relaxes_rd_in_sparse_band_but_keeps_popularity(tmp_path, rng):
    # No row passes rating_deviation <= 80 here (like the real DB at >= 2800).
    rows = [m1(f'hi-rd{i}', 400 + i, rd=150) for i in range(20)] + [m1(f'unpop{i}', 400 + i, rd=150, pop=5)
                                                                     for i in range(20)]
    source = PuzzleSource(make_puzzles_db(tmp_path / 'p.db', rows))
    picks = {source.pick(0, rng=rng)['id'] for _ in range(40)}
    assert picks and all(p.startswith('hi-rd') for p in picks)


def test_ramp_saturates_at_db_max_rating(tmp_path, rng):
    db = make_puzzles_db(tmp_path / 'p.db', [m1(f'p{r}', r) for r in range(2900, 3001, 5)])
    picked = PuzzleSource(db).pick(60, rng=rng)  # target(60) = 5260
    assert picked['rating'] >= 2970


def test_get_and_moves_split(tmp_path):
    db = make_puzzles_db(tmp_path / 'p.db', [m1('x', 500), m1('y', 510)])
    conn = sqlite3.connect(db)
    conn.execute("UPDATE puzzles SET themes = 'fork short' WHERE id = 'y'")
    conn.commit()
    conn.close()
    source = PuzzleSource(db)
    assert source.get('x') == {'id': 'x', 'fen': M1_FEN, 'moves': ['a7a6', 'd1d8'], 'rating': 500, 'themes': []}
    assert source.get('y')['themes'] == ['fork', 'short']
    assert source.get('missing') is None


def test_connection_is_read_only(tmp_path):
    source = PuzzleSource(make_puzzles_db(tmp_path / 'p.db', [m1('x', 500)]))
    with pytest.raises(sqlite3.OperationalError):
        source._conn().execute("DELETE FROM puzzles")


def test_db_path_from_env(tmp_path, monkeypatch):
    db = make_puzzles_db(tmp_path / 'p.db', [m1('x', 500)])
    monkeypatch.setenv('PUZZLE_RUSH_DB_PATH', db)
    assert PuzzleSource().db_path == db
