"""The voice [Engine] line: SAN lines, White-side evals, game-over notes, the endpoint."""

from unittest.mock import call, patch

import pytest
from fastapi.testclient import TestClient

from src import voice_engine_note
from src.middleware.rate_limiter import voice_tool_rate_limiter
from src.server import app
from src.voice_engine_note import engine_note

SICILIAN = "r1bqkbnr/pp1ppppp/2n5/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
ITALIAN_BLACK = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"


def _engine(lines):
    return patch.object(voice_engine_note, "analyze_cached", return_value={"best_move": "", "lines": lines})


@pytest.mark.unit
class TestEngineNote:
    def test_lines_are_san_and_best_leads(self):
        with _engine([
            {"pv": "d2d4 c5d4 f3d4 g7g6 b1c3", "score": 0.4, "depth": 16},
            {"pv": "f1b5 g7g6", "score": 0.37, "depth": 16},
        ]):
            note = engine_note(SICILIAN)
        assert note["best"] == "d4"
        assert note["lines"][0]["moves"] == ["d4", "cxd4", "Nxd4", "g6"]
        assert "White to move. Best: d4 (+0.40; line d4 cxd4 Nxd4 g6). Also: Bb5 (+0.37)." in note["note"]

    def test_black_to_move_evals_are_flipped_to_whites_side(self):
        # Stockfish scores for the side to move: +0.5 for Black is -0.50 for White.
        with _engine([{"pv": "f8c5", "score": 0.5, "depth": 16}]):
            note = engine_note(ITALIAN_BLACK)
        assert "Black to move. Best: Bc5 (-0.50" in note["note"]

    def test_mate_is_spoken_for_the_winner(self):
        with _engine([{"pv": "f8c5", "score": 10000, "mate_in": 3, "depth": 16}]):
            note = engine_note(ITALIAN_BLACK)
        assert "mate in 3 for Black" in note["note"]

    def test_illegal_pv_tail_is_cut(self):
        with _engine([{"pv": "d2d4 a1a8", "score": 0.4, "depth": 16}]):
            note = engine_note(SICILIAN)
        assert note["lines"][0]["moves"] == ["d4"]

    def test_checkmate_needs_no_engine(self):
        fools_mate = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
        with _engine([]) as run:
            note = engine_note(fools_mate)
        run.assert_not_called()
        assert "checkmate, Black has won" in note["note"]

    def test_bad_fen_and_engine_error_give_none(self):
        assert engine_note("not a fen") is None
        with patch.object(voice_engine_note, "analyze_cached", return_value={"error": "timed out"}):
            assert engine_note(SICILIAN) is None

    def test_movetime_searches_by_time_and_reports_the_depth_reached(self):
        lines = {"best_move": "", "lines": [{"pv": "d2d4 c5d4", "score": 0.4, "depth": 19}]}
        with patch.object(voice_engine_note, "analyze_timed", return_value=lines) as timed, \
             patch.object(voice_engine_note, "analyze_cached") as by_depth:
            note = engine_note(SICILIAN, movetime_ms=1500)
        # The main search goes by time; the others are the short threat searches
        # of the facts (300 ms, one line each).
        assert call(SICILIAN, 1500, multipv=3) in timed.call_args_list
        assert all(c.args[1] == 300 for c in timed.call_args_list if c != call(SICILIAN, 1500, multipv=3))
        by_depth.assert_not_called()
        assert "Stockfish depth 19" in note["note"]


@pytest.mark.unit
class TestEngineNoteRoute:
    def setup_method(self):
        voice_tool_rate_limiter.reset()
        self.client = TestClient(app)

    def test_returns_the_note(self):
        with _engine([{"pv": "d2d4", "score": 0.4, "depth": 16}]):
            res = self.client.post(
                "/api/coach/voice/engine-note", json={"fen": SICILIAN}, headers={"X-User-Id": "u1"}
            )
        assert res.status_code == 200
        assert res.json()["best"] == "d4"

    def test_unanalysable_position_is_422(self):
        res = self.client.post(
            "/api/coach/voice/engine-note", json={"fen": "nonsense"}, headers={"X-User-Id": "u1"}
        )
        assert res.status_code == 422

    def test_requires_user(self):
        res = self.client.post("/api/coach/voice/engine-note", json={"fen": SICILIAN})
        assert res.status_code == 401
