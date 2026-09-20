"""Puzzle database: import script, lookup, theme aliases, set_puzzle by id."""

import csv
import json
import random

import chess
import pytest

from src import puzzle_db
from src.tools.board_control import build_board_action
from src.tools.puzzles import get_puzzle

# Lichess CSV rows: FEN is the position BEFORE the opponent's move in Moves[0].
ROWS = [
    # 3.Qh5?! Nf6?? 4.Qxf7#  — mate in one for White
    {"PuzzleId": "mate01", "FEN": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
     "Moves": "g8f6 h5f7", "Rating": "800", "RatingDeviation": "80", "Popularity": "95",
     "NbPlays": "12000", "Themes": "mate mateIn1 oneMove short", "GameUrl": "https://lichess.org/abc#7",
     "OpeningTags": "Italian_Game"},
    # exd5 Qxd5 — a plain recapture, legal, tagged as an opening puzzle
    {"PuzzleId": "open01", "FEN": "rnbqkbnr/ppp2ppp/8/3pp3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",
     "Moves": "e4d5 d8d5", "Rating": "1500", "RatingDeviation": "75", "Popularity": "80",
     "NbPlays": "3000", "Themes": "opening advantage short", "GameUrl": "https://lichess.org/def#5",
     "OpeningTags": "Scandinavian_Defense"},
    # unpopular duplicate theme, should be filtered by min_popularity
    {"PuzzleId": "unpop1", "FEN": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
     "Moves": "g8f6 h5f7", "Rating": "820", "RatingDeviation": "80", "Popularity": "-50",
     "NbPlays": "10", "Themes": "mate mateIn1", "GameUrl": "", "OpeningTags": ""},
]


@pytest.fixture(scope="module")
def puzzle_csv(tmp_path_factory):
    path = tmp_path_factory.mktemp("puzzles") / "lichess_db_puzzle.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(ROWS[0].keys()))
        writer.writeheader()
        writer.writerows(ROWS)
    return str(path)


@pytest.fixture(scope="module")
def puzzle_db_path(puzzle_csv, tmp_path_factory):
    from scripts.import_puzzles import build

    db = str(tmp_path_factory.mktemp("db") / "puzzles.db")
    total = build(puzzle_csv, db)
    assert total == 3
    return db


@pytest.fixture(autouse=True)
def _point_db(monkeypatch, puzzle_db_path):
    monkeypatch.setattr(puzzle_db, "PUZZLES_DB_PATH", puzzle_db_path)


@pytest.mark.unit
def test_present_puzzle_applies_setup_move_and_converts_solution(puzzle_db_path):
    p = puzzle_db.load_puzzle("mate01")
    assert p["side_to_move"] == "white"
    assert p["last_move_san"] == "Nf6"
    assert p["solution"] == ["Qxf7#"]
    assert p["solution_uci"] == ["h5f7"]
    board = chess.Board(p["fen"])
    assert board.turn == chess.WHITE
    board.push_san("Qxf7#")
    assert board.is_checkmate()
    assert "mateIn1" in p["themes"] and p["opening_tags"] == ["Italian_Game"]


@pytest.mark.unit
def test_find_by_theme_and_rating_widens_the_band():
    rng = random.Random(1)
    got = puzzle_db.find_puzzles(theme="mateIn1", rating=800, rng=rng)
    assert [g["puzzle_id"] for g in got] == ["mate01"]  # unpop1 filtered by popularity
    # 1500-rated request for a theme that only exists at 800: band widens.
    got = puzzle_db.find_puzzles(theme="mateIn1", rating=1500, rng=rng)
    assert got and got[0]["puzzle_id"] == "mate01"
    assert puzzle_db.find_puzzles(theme="zugzwang") == []
    assert puzzle_db.find_puzzles(theme="mateIn1", exclude_ids=["mate01"]) == []


@pytest.mark.unit
def test_theme_aliases_ru_and_exact():
    assert puzzle_db.resolve_theme("fork") == "fork"
    assert puzzle_db.resolve_theme("MateIn2") == "mateIn2"
    assert puzzle_db.resolve_theme("дай задачу на вилку") == "fork"
    assert puzzle_db.resolve_theme("мат в 2 хода") == "mateIn2"
    assert puzzle_db.resolve_theme("пешечный эндшпиль") == "pawnEndgame"
    assert puzzle_db.resolve_theme("что-то непонятное") is None


@pytest.mark.unit
def test_get_puzzle_tool_returns_position_and_how_to_show():
    out = get_puzzle(theme="связка на мат в 1", rating=800)
    assert out["theme"] == "mateIn1"
    assert out["count"] == 1
    assert out["puzzles"][0]["puzzle_id"] == "mate01"
    assert "set_puzzle" in out["how_to_show"]

    assert "error" in get_puzzle(theme="несуществующая тема")
    assert "error" in get_puzzle(theme="zugzwang")


@pytest.mark.unit
def test_get_puzzle_reports_missing_database(monkeypatch, tmp_path):
    monkeypatch.setattr(puzzle_db, "PUZZLES_DB_PATH", str(tmp_path / "missing.db"))
    out = get_puzzle(theme="fork")
    assert "not installed" in out["error"]


@pytest.mark.unit
def test_set_puzzle_by_id_uses_database_position():
    action = build_board_action("set_puzzle", {"puzzle_id": "open01"})
    assert action["type"] == "set_puzzle"
    assert action["puzzle_id"] == "open01"
    assert action["solution"] == ["Qxd5"]
    assert chess.Board(action["fen"]).turn == chess.BLACK

    bad = build_board_action("set_puzzle", {"puzzle_id": "nope"})
    assert "Unknown puzzle_id" in bad["error"]

    # Without an id a solution is mandatory — no more model-invented puzzles.
    assert "error" in build_board_action("set_puzzle", {"fen": chess.STARTING_FEN})
    explicit = build_board_action("set_puzzle", {"fen": chess.STARTING_FEN, "solution": ["e4"]})
    assert explicit["solution"] == ["e4"]


@pytest.mark.unit
def test_get_puzzle_is_registered():
    from src.tools import discover_and_register, get_registered_tools

    discover_and_register()
    assert "get_puzzle" in get_registered_tools()
    out = json.loads(__import__("src.tools.puzzles", fromlist=["_handle_get_puzzle"])._handle_get_puzzle({"theme": "opening"}))
    assert out["puzzles"][0]["puzzle_id"] == "open01"
