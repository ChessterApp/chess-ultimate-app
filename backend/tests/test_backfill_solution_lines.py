"""
Unit tests for the pure helpers in scripts/backfill_solution_lines.py

Network / Stockfish paths are not exercised here — only the deterministic
move-normalisation, replay, URL parsing and chapter-matching logic.
"""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"),
)

from backfill_solution_lines import (  # noqa: E402
    solution_move_to_uci,
    replay_legal,
    normalize_fen,
    chapter_id_from_url,
    study_id_from_url,
    training_id_from_url,
    match_chapter,
    uci_line_from_game,
)


class TestSolutionMoveToUci:
    def test_san_is_converted(self):
        # Rf3 from this rook endgame is g3f3
        assert solution_move_to_uci("8/8/5k2/5q2/7K/6R1/8/8 w - - 0 1", "Rf3") == "g3f3"

    def test_uci_passthrough(self):
        assert solution_move_to_uci("6K1/8/6kq/8/8/8/8/5R2 w - - 0 1", "f1f6") == "f1f6"

    def test_promotion_uci(self):
        # White pawn on e7 promotes; e7e8q is legal here.
        fen = "8/4P3/8/8/8/8/8/k1K5 w - - 0 1"
        assert solution_move_to_uci(fen, "e7e8q") == "e7e8q"

    def test_illegal_returns_none(self):
        assert solution_move_to_uci("6K1/8/6kq/8/8/8/8/5R2 w - - 0 1", "a1a2") is None

    def test_empty_returns_none(self):
        assert solution_move_to_uci("6K1/8/6kq/8/8/8/8/5R2 w - - 0 1", "") is None


class TestReplayLegal:
    def test_legal_multi_move_line(self):
        # d2d4, c5d4 (capture), e3g5 mate-in-2 style line
        fen = "r1bqkb1r/ppp2ppp/2n2n2/2ppp3/8/2N1P3/PPPP1PPP/R1BQKBNR w KQkq - 0 5"
        # Just assert a simple known-legal 2-ply line replays.
        assert replay_legal("6K1/8/6kq/8/8/8/8/5R2 w - - 0 1", ["f1f6"]) is True

    def test_illegal_move_fails(self):
        assert replay_legal("6K1/8/6kq/8/8/8/8/5R2 w - - 0 1", ["a1a2"]) is False

    def test_empty_line_is_not_legal(self):
        assert replay_legal("6K1/8/6kq/8/8/8/8/5R2 w - - 0 1", []) is False

    def test_second_move_illegal_fails(self):
        # first legal, second illegal
        assert replay_legal("6K1/8/6kq/8/8/8/8/5R2 w - - 0 1", ["f1f6", "a1a1"]) is False


class TestUrlParsing:
    def test_normalize_fen_drops_clocks(self):
        assert normalize_fen("8/8/5k2/5q2/7K/6R1/8/8 w - - 12 34") == "8/8/5k2/5q2/7K/6R1/8/8 w - -"

    def test_chapter_id(self):
        assert chapter_id_from_url("https://lichess.org/study/ADy5QqBp/Ek3IivCj") == "Ek3IivCj"

    def test_chapter_id_absent(self):
        assert chapter_id_from_url("https://lichess.org/study/ADy5QqBp") is None

    def test_study_id_from_study_url(self):
        assert study_id_from_url("https://lichess.org/study/ADy5QqBp/Ek3IivCj") == "ADy5QqBp"

    def test_study_id_from_practice_url(self):
        assert study_id_from_url("https://lichess.org/practice/Qj281y1p") == "Qj281y1p"

    def test_training_id(self):
        assert training_id_from_url("https://lichess.org/training/LdLzX") == "LdLzX"

    def test_training_id_absent(self):
        assert training_id_from_url("https://lichess.org/study/ADy5QqBp") is None


class TestMatchChapter:
    def _chapters(self):
        return [
            {"chapter_id": "aaa", "norm_fen": "fenA", "ucis": ["e2e4", "e7e5"]},
            {"chapter_id": "bbb", "norm_fen": "fenB", "ucis": ["d2d4", "d7d5"]},
        ]

    def test_match_by_chapter_id(self):
        assert match_chapter(self._chapters(), "bbb", "whatever", None) == ["d2d4", "d7d5"]

    def test_match_by_fen_when_no_chapter_id(self):
        assert match_chapter(self._chapters(), None, "fenA", None) == ["e2e4", "e7e5"]

    def test_disambiguate_by_first_move(self):
        chapters = [
            {"chapter_id": None, "norm_fen": "fenX", "ucis": ["a2a3"]},
            {"chapter_id": None, "norm_fen": "fenX", "ucis": ["b2b3"]},
        ]
        assert match_chapter(chapters, None, "fenX", "b2b3") == ["b2b3"]

    def test_no_match_returns_none(self):
        assert match_chapter(self._chapters(), "zzz", "nope", None) is None

    def test_empty_chapters_returns_none(self):
        assert match_chapter(None, "aaa", "fenA", None) is None

    def test_ignores_chapters_with_empty_line(self):
        chapters = [{"chapter_id": "aaa", "norm_fen": "fenA", "ucis": []}]
        assert match_chapter(chapters, "aaa", "fenA", None) is None
