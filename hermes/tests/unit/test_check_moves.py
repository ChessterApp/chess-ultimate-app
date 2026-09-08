"""Unit tests for the check_moves move-legality tool."""

import json

import chess
import pytest

from src.tools.check_moves import check_moves, _handle_check_moves


# Frequently reused positions.
START = chess.STARTING_FEN
# White may castle kingside (e1g1) here.
CASTLE_OK = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 1"
# Black just played f7-f5; white e5 pawn can take en passant on f6.
EN_PASSANT = "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"
# White pawn on e7 promotes.
PROMOTION = "7k/4P3/8/8/8/8/8/4K3 w - - 0 1"
# Knights on d3 and f3 both reach e5 → "Ne5" is ambiguous.
AMBIGUOUS = "4k3/8/8/8/8/3N1N2/8/4K3 w - - 0 1"
# 218 legal moves — forces the truncation path.
MAX_MOBILITY = "3Q4/1Q4Q1/4Q3/2Q4R/Q4Q2/3Q4/1Q4Rp/1K1BBNNk w - - 0 1"


def _result_for(out: dict, move: str) -> dict:
    """Return the per-move result dict for *move* from a check_moves output."""
    return next(r for r in out["results"] if r["move"] == move)


@pytest.mark.unit
class TestBasics:
    def test_echoes_fen_and_side(self):
        out = check_moves(START, ["e4"])
        assert out["fen"] == START
        assert out["side_to_move"] == "white"

    def test_side_to_move_black(self):
        out = check_moves(
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", ["e5"]
        )
        assert out["side_to_move"] == "black"


@pytest.mark.unit
class TestSAN:
    def test_legal_san(self):
        out = check_moves(START, ["Nf3"])
        r = _result_for(out, "Nf3")
        assert r["legal"] is True
        assert r["san"] == "Nf3"
        assert r["uci"] == "g1f3"

    def test_illegal_san(self):
        out = check_moves(START, ["Qe5"])
        r = _result_for(out, "Qe5")
        assert r["legal"] is False
        assert "queen" in r["reason"]
        assert "e5" in r["reason"]

    def test_ambiguous_san(self):
        out = check_moves(AMBIGUOUS, ["Ne5"])
        r = _result_for(out, "Ne5")
        assert r["legal"] is False
        assert "ambiguous" in r["reason"].lower()

    def test_unparseable_move(self):
        out = check_moves(START, ["banana"])
        r = _result_for(out, "banana")
        assert r["legal"] is False
        assert "unparseable" in r["reason"].lower()


@pytest.mark.unit
class TestUCI:
    def test_legal_uci(self):
        out = check_moves(START, ["g1f3"])
        r = _result_for(out, "g1f3")
        assert r["legal"] is True
        assert r["san"] == "Nf3"
        assert r["uci"] == "g1f3"

    def test_illegal_uci_piece_cannot_reach(self):
        # No white piece move from e2 to e5 in one step.
        out = check_moves(START, ["e2e5"])
        r = _result_for(out, "e2e5")
        assert r["legal"] is False
        assert "reason" in r

    def test_uci_no_piece_on_source(self):
        out = check_moves(START, ["e5e6"])
        r = _result_for(out, "e5e6")
        assert r["legal"] is False
        assert "no piece on e5" in r["reason"]


@pytest.mark.unit
class TestSpecialMoves:
    def test_castling_legal(self):
        out = check_moves(CASTLE_OK, ["O-O"])
        r = _result_for(out, "O-O")
        assert r["legal"] is True
        assert r["uci"] == "e1g1"

    def test_castling_illegal(self):
        # No castling from the starting position (pieces in the way).
        out = check_moves(START, ["O-O"])
        r = _result_for(out, "O-O")
        assert r["legal"] is False
        assert "castling" in r["reason"].lower()

    def test_promotion_san(self):
        out = check_moves(PROMOTION, ["e8=Q"])
        r = _result_for(out, "e8=Q")
        assert r["legal"] is True
        assert r["uci"] == "e7e8q"
        assert r["san"].startswith("e8=Q")

    def test_promotion_uci(self):
        out = check_moves(PROMOTION, ["e7e8q"])
        r = _result_for(out, "e7e8q")
        assert r["legal"] is True
        assert r["uci"] == "e7e8q"

    def test_en_passant_san(self):
        out = check_moves(EN_PASSANT, ["exf6"])
        r = _result_for(out, "exf6")
        assert r["legal"] is True
        assert r["uci"] == "e5f6"

    def test_en_passant_uci(self):
        out = check_moves(EN_PASSANT, ["e5f6"])
        r = _result_for(out, "e5f6")
        assert r["legal"] is True
        assert r["san"] == "exf6"


@pytest.mark.unit
class TestBatchAndListing:
    def test_mixed_legal_and_illegal(self):
        out = check_moves(START, ["e4", "Qe5", "g1f3", "Ke2"])
        assert _result_for(out, "e4")["legal"] is True
        assert _result_for(out, "g1f3")["legal"] is True
        assert _result_for(out, "Qe5")["legal"] is False
        assert _result_for(out, "Ke2")["legal"] is False
        # Order is preserved.
        assert [r["move"] for r in out["results"]] == ["e4", "Qe5", "g1f3", "Ke2"]

    def test_legal_moves_count_start_position(self):
        out = check_moves(START, ["e4"])
        assert len(out["legal_moves"]) == 20
        assert "e4" in out["legal_moves"]
        assert "Nf3" in out["legal_moves"]
        assert "legal_moves_truncated" not in out

    def test_legal_moves_truncated(self):
        out = check_moves(MAX_MOBILITY, ["Qd8d7"])
        assert out.get("legal_moves_truncated") is True
        assert len(out["legal_moves"]) == 60


@pytest.mark.unit
class TestInputValidation:
    def test_invalid_fen(self):
        out = check_moves("not a fen", ["e4"])
        assert "error" in out
        assert "results" not in out

    def test_structurally_invalid_position(self):
        # Two white kings is not a valid position.
        out = check_moves("4k3/8/8/8/8/8/8/K3K3 w - - 0 1", ["e4"])
        assert "error" in out

    def test_empty_moves_array(self):
        out = check_moves(START, [])
        assert "error" in out

    def test_oversized_moves_array(self):
        out = check_moves(START, ["e4"] * 11)
        assert "error" in out


@pytest.mark.unit
class TestHandler:
    def test_handler_returns_json(self):
        raw = _handle_check_moves({"fen": START, "moves": ["e4", "Qe5"]})
        parsed = json.loads(raw)
        assert parsed["side_to_move"] == "white"
        assert len(parsed["results"]) == 2

    def test_handler_invalid_fen_json(self):
        raw = _handle_check_moves({"fen": "garbage", "moves": ["e4"]})
        parsed = json.loads(raw)
        assert "error" in parsed
