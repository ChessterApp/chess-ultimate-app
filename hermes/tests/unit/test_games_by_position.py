"""find_games_by_position — master games reaching a FEN via the game_positions index."""

import chess
import pytest

from src.tools.games_by_position import find_games_by_position, position_hash

RUY = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"


@pytest.fixture
def positions_db(fake_twic_db):
    cur = fake_twic_db.cursor()
    cur.execute("CREATE TABLE game_positions (game_id INTEGER, ply INTEGER, board_hash TEXT)")
    cur.execute("CREATE INDEX idx_positions_hash ON game_positions(board_hash)")
    h = position_hash(RUY)
    cur.executemany("INSERT INTO game_positions VALUES (?, ?, ?)", [(1, 5, h), (9, 5, h)])
    cur.execute("UPDATE games SET white_elo = 2850, black_elo = 2800 WHERE id = 1")
    cur.execute("UPDATE games SET white_elo = 2700, black_elo = 2750 WHERE id = 9")
    fake_twic_db.commit()
    return fake_twic_db


@pytest.mark.unit
def test_hash_normalises_en_passant_and_keeps_castling():
    assert position_hash("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1") == \
        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -"


@pytest.mark.unit
def test_games_reaching_position_strongest_first(positions_db):
    out = find_games_by_position(RUY, conn=positions_db)
    assert [g["id"] for g in out["games"]] == [1, 9]
    assert out["games"][0]["white"] == "Carlsen" and out["games"][0]["ply"] == 5
    assert out["total"] == 2  # no move_stats row for this hash → pool size


@pytest.mark.unit
def test_filters_and_unknown_position(positions_db):
    out = find_games_by_position(RUY, result="0-1", conn=positions_db)
    assert [g["id"] for g in out["games"]] == [9]
    out = find_games_by_position(RUY, min_avg_elo=2800, conn=positions_db)
    assert [g["id"] for g in out["games"]] == [1]
    # The fixture's move_stats knows 2150 games from the start position but the
    # positions index has none of them: the count comes from move_stats, the
    # list from the index.
    out = find_games_by_position(chess.STARTING_FEN, conn=positions_db)
    assert out["games"] == [] and out["total"] == 2150
    assert "error" in find_games_by_position("not a fen", conn=positions_db)


@pytest.mark.unit
def test_missing_index_and_missing_db(fake_twic_db, tmp_path):
    out = find_games_by_position(RUY, conn=fake_twic_db)
    assert "not built" in out["error"]
    out = find_games_by_position(RUY, db_path=str(tmp_path / "none.db"))
    assert "not available" in out["error"]
