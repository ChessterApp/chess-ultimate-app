"""get_game_pgn reads the game's bytes from the master PGN (live site, 02.11).

The coach found Sindarov – Nakamura (Miami 2026) but got no moves, while the
site's database page showed them: a strict text read raised on a Latin-1 byte
near the game. The read now takes the exact bytes and decodes with replacement.
"""
import sqlite3

from src.tools import twic_search

GAME = (
    '[Event "WR Rapid Miami 2026"]\n[White "Sindarov,Javokhir"]\n[Black "Nakamura,Hi"]\n'
    '[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nf6 1-0\n'
)


def _db(offset, length):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE games (id INTEGER, white_name TEXT, black_name TEXT, result TEXT, date TEXT,"
        " eco TEXT, event TEXT, white_elo INTEGER, black_elo INTEGER, pgn_offset INTEGER, pgn_length INTEGER)"
    )
    conn.execute(
        "INSERT INTO games VALUES (1, 'Sindarov,Javokhir', 'Nakamura,Hi', '1-0', '2026.07.27', 'C43',"
        " 'WR Rapid Miami 2026', 2750, 2800, ?, ?)",
        (offset, length),
    )
    return conn


def _master(tmp_path, monkeypatch, before: bytes, after: bytes):
    data = before + GAME.encode() + after
    path = tmp_path / "master.pgn"
    path.write_bytes(data)
    monkeypatch.setattr(twic_search, "PGN_FILE_PATH", str(path))
    return len(before), len(GAME.encode())


def test_latin1_bytes_around_the_game_do_not_lose_its_moves(tmp_path, monkeypatch):
    # Invalid UTF-8 (Latin-1 «é», «ö») right before and after the game, inside one read chunk.
    off, length = _master(tmp_path, monkeypatch, b'[White "Ren\xe9"]\n\n1. d4 *\n\n', b'\n[Black "G\xf6tz"]\n' * 50)
    out = twic_search.get_game_pgn(1, conn=_db(off, length))
    assert "error" not in out
    assert out["pgn"].startswith('[Event "WR Rapid Miami 2026"]')
    assert "1. e4 e5 2. Nf3 Nf6" in out["pgn"]


def test_a_bad_byte_inside_the_game_is_replaced_not_fatal(tmp_path, monkeypatch):
    raw = GAME.encode().replace(b"Nakamura,Hi", b"Nakamura,H\xefi")
    path = tmp_path / "master.pgn"
    path.write_bytes(raw)
    monkeypatch.setattr(twic_search, "PGN_FILE_PATH", str(path))
    out = twic_search.get_game_pgn(1, conn=_db(0, len(raw)))
    assert "1. e4 e5 2. Nf3 Nf6" in out["pgn"]


def test_no_moves_is_an_error_not_an_empty_score(tmp_path, monkeypatch):
    monkeypatch.setattr(twic_search, "PGN_FILE_PATH", str(tmp_path / "missing.pgn"))
    out = twic_search.get_game_pgn(1, conn=_db(0, 120))
    assert "error" in out and "pgn" not in out
    assert out["headers"]["White"] == "Sindarov,Javokhir"
