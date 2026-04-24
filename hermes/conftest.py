import sqlite3
from unittest.mock import MagicMock, patch

import chess
import pytest

SAMPLE_PGNS = [
    # Immortal Game (Anderssen vs Kieseritzky, 1851)
    '1. e4 e5 2. f4 exf4 3. Bc4 Qh4+ 4. Kf1 b5 5. Bxb5 Nf6 6. Nf3 Qh6 '
    '7. d3 Nh5 8. Nh4 Qg5 9. Nf5 c6 10. g4 Nf6 11. Rg1 cxb5 12. h4 Qg6 '
    '13. h5 Qg5 14. Qf3 Ng8 15. Bxf4 Qf6 16. Nc3 Bc5 17. Nd5 Qxb2 '
    '18. Bd6 Bxg1 19. e5 Qxa1+ 20. Ke2 Na6 21. Nxg7+ Kd8 22. Qf6+ Nxf6 '
    '23. Be7# 1-0',

    # Opera Game (Morphy vs Duke/Count, 1858)
    '1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 '
    '7. Qb3 Qe7 8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 '
    '12. O-O-O Rd8 13. Rxd7 Rxd7 14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 '
    '17. Rd8# 1-0',

    # Kasparov vs Topalov (1999)
    '1. e4 d6 2. d4 Nf6 3. Nc3 g6 4. Be3 Bg7 5. Qd2 c6 6. f3 b5 '
    '7. Nge2 Nbd7 8. Bh6 Bxh6 9. Qxh6 Bb7 10. a3 e5 11. O-O-O Qe7 '
    '12. Kb1 a6 13. Nc1 O-O-O 14. Nb3 exd4 15. Rxd4 c5 16. Rd1 Nb6 '
    '17. g3 Kb8 18. Na5 Ba8 19. Bh3 d5 20. Qf4+ Ka7 21. Re1 d4 '
    '22. Nd5 Nbxd5 23. exd5 Qd6 24. Rxd4 cxd4 25. Re7+ Kb6 '
    '26. Qxd4+ Kxa5 27. b4+ Ka4 28. Qc3 Qxd5 29. Ra7 Bb7 30. Rxb7 Qc4 '
    '31. Qxf6 Kxa3 32. Qxa6+ Kxb4 33. c3+ Kxc3 34. Qa1+ Kd2 '
    '35. Qb2+ Kd1 36. Bf1 Rd2 37. Rd7 Rxd7 38. Bxc4 bxc4 39. Qxh8 Rd3 '
    '40. Qa8 c3 41. Qa4+ Ke1 42. f4 f5 43. Kc1 Rd2 44. Qa7 1-0',
]

SAMPLE_FENS = [
    chess.STARTING_FEN,
    # Italian Game
    'r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3',
    # Sicilian Najdorf
    'rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6',
    # Ruy Lopez middle game
    'r1bq1rk1/2ppbppp/p1n2n2/1p2p3/4P3/1B3N2/PPPP1PPP/RNBQR1K1 w - - 0 9',
    # Endgame K+R vs K
    '8/8/8/4k3/8/8/8/4K2R w - - 0 1',
]

FIXTURE_GAMES = [
    (1, 'Carlsen', 'Caruana', '1-0', '2024-01-15', 'C65', 'Ruy Lopez', 'Wijk aan Zee',
     '1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. d3 Bc5 5. O-O d6 1-0'),
    (2, 'Caruana', 'Carlsen', '0-1', '2024-01-16', 'B90', 'Sicilian Najdorf', 'Wijk aan Zee',
     '1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 0-1'),
    (3, 'Ding', 'Nepomniachtchi', '1/2-1/2', '2024-02-01', 'D37', 'QGD', 'Candidates',
     '1. d4 Nf6 2. c4 e6 3. Nf3 d5 4. Nc3 Be7 5. Bf4 O-O 1/2-1/2'),
    (4, 'Firouzja', 'Nakamura', '1-0', '2024-02-10', 'C42', 'Petrov Defense', 'Grand Swiss',
     '1. e4 e5 2. Nf3 Nf6 3. Nxe5 d6 4. Nf3 Nxe4 5. d4 d5 1-0'),
    (5, 'Nakamura', 'Firouzja', '0-1', '2024-02-11', 'E20', 'Nimzo-Indian', 'Grand Swiss',
     '1. d4 Nf6 2. c4 e6 3. Nc3 Bb4 4. f3 d5 5. a3 Be7 0-1'),
    (6, 'Gukesh', 'Praggnanandhaa', '1-0', '2024-03-05', 'C50', 'Italian Game', 'Chennai GCT',
     '1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. d3 Bc5 5. O-O d6 1-0'),
    (7, 'Praggnanandhaa', 'Gukesh', '1/2-1/2', '2024-03-06', 'A15', 'English Opening', 'Chennai GCT',
     '1. c4 Nf6 2. g3 e5 3. Bg2 d5 4. cxd5 Nxd5 5. Nc3 Nb6 1/2-1/2'),
    (8, 'Aronian', 'So', '1-0', '2024-04-20', 'D85', 'Grunfeld', 'Superbet Classic',
     '1. d4 Nf6 2. c4 g6 3. Nc3 d5 4. cxd5 Nxd5 5. e4 Nxc3 1-0'),
    (9, 'So', 'Aronian', '0-1', '2024-04-21', 'C67', 'Ruy Lopez Berlin', 'Superbet Classic',
     '1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. O-O Nxe4 5. d4 Nd6 0-1'),
    (10, 'Rapport', 'Dominguez', '1-0', '2024-05-15', 'B12', 'Caro-Kann', 'Norway Chess',
     '1. e4 c6 2. d4 d5 3. e5 Bf5 4. Nf3 e6 5. Be2 Nd7 1-0'),
]

# Starting position board hash for move_stats
STARTING_BOARD_HASH = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - -"

FIXTURE_MOVE_STATS = [
    (STARTING_BOARD_HASH, 'e4', 1000, 400, 300, 300, 2500, 2020),
    (STARTING_BOARD_HASH, 'd4', 800, 320, 280, 200, 2500, 2020),
    (STARTING_BOARD_HASH, 'Nf3', 200, 80, 70, 50, 2450, 2019),
    (STARTING_BOARD_HASH, 'c4', 150, 60, 50, 40, 2400, 2019),
]

CANNED_STOCKFISH_OUTPUT = (
    'info depth 20 seldepth 30 multipv 1 score cp 35 nodes 1234567 nps 2000000 '
    'time 617 pv e2e4 e7e5 g1f3 b8c6 f1b5\n'
    'bestmove e2e4 ponder e7e5\n'
)


@pytest.fixture
def fake_twic_db():
    """In-memory SQLite with games and move_stats tables."""
    conn = sqlite3.connect(':memory:')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE games (
            id INTEGER PRIMARY KEY,
            white TEXT,
            black TEXT,
            result TEXT,
            date TEXT,
            eco TEXT,
            opening TEXT,
            event TEXT,
            pgn TEXT
        )
    ''')
    cur.executemany(
        'INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        FIXTURE_GAMES,
    )
    cur.execute('''
        CREATE TABLE move_stats (
            board_hash TEXT NOT NULL,
            move_san TEXT NOT NULL,
            games INTEGER NOT NULL,
            white_wins INTEGER NOT NULL,
            draws INTEGER NOT NULL,
            black_wins INTEGER NOT NULL,
            avg_elo INTEGER,
            avg_year INTEGER,
            PRIMARY KEY (board_hash, move_san)
        )
    ''')
    cur.executemany(
        'INSERT INTO move_stats VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        FIXTURE_MOVE_STATS,
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mock_stockfish():
    """Patches subprocess.Popen to return canned Stockfish output."""
    import io

    def make_mock_popen(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = io.StringIO(CANNED_STOCKFISH_OUTPUT)
        mock_proc.stderr = io.StringIO('')
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock(return_value=0)
        mock_proc.kill = MagicMock()
        return mock_proc

    with patch('subprocess.Popen', side_effect=make_mock_popen) as mock_popen:
        yield mock_popen


@pytest.fixture
def fake_supabase():
    """Mock Supabase HTTP responses for user data tests.

    Returns a dict with canned repertoire and user_games data, plus
    a mock httpx.get function that returns them based on URL path.
    """
    repertoire_data = [
        {"id": 1, "user_id": "user123", "color": "white", "eco": "C50",
         "opening": "Italian Game", "moves": "1. e4 e5 2. Nf3 Nc6 3. Bc4"},
        {"id": 2, "user_id": "user123", "color": "black", "eco": "B90",
         "opening": "Sicilian Najdorf", "moves": "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6"},
        {"id": 3, "user_id": "user123", "color": "white", "eco": "D37",
         "opening": "QGD", "moves": "1. d4 d5 2. c4 e6 3. Nf3 Nf6 4. Nc3 Be7"},
    ]
    user_games_data = [
        {"id": 1, "user_id": "user123", "white": "user123", "black": "opponent1",
         "result": "1-0", "played_at": "2024-05-01", "eco": "C50", "pgn": "1. e4 e5 1-0"},
        {"id": 2, "user_id": "user123", "white": "opponent2", "black": "user123",
         "result": "0-1", "played_at": "2024-04-28", "eco": "B90", "pgn": "1. e4 c5 0-1"},
        {"id": 3, "user_id": "user123", "white": "user123", "black": "opponent3",
         "result": "1/2-1/2", "played_at": "2024-04-25", "eco": "D37", "pgn": "1. d4 d5 1/2-1/2"},
    ]

    return {
        "repertoire": repertoire_data,
        "user_games": user_games_data,
    }


@pytest.fixture
def sample_fens():
    """List of 5 standard test positions."""
    return SAMPLE_FENS.copy()


@pytest.fixture
def sample_pgns():
    """List of 3 complete game PGNs."""
    return SAMPLE_PGNS.copy()
