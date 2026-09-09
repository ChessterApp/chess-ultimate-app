"""Task B — engine-grounded auto-eval: claim extraction + adjudication.

Hand-built FEN fixtures: a known best move, a known blunder, an illegal move,
and eval-direction claims. Uses the local Stockfish binary (no network). If
Stockfish is absent the engine-scored assertions are skipped, but the graceful-
degradation path is always tested.
"""

import os

import pytest

from src.eval.engine_grounded import DEFAULT_DEPTH, evaluate_turn
from src.tools.stockfish import STOCKFISH_PATH

# Fast, deterministic depth for tests.
D = 8

# White queen d2, Black queen hanging on d4 → Qxd4 wins a queen (clear best).
FREE_QUEEN = "4k3/8/8/8/3q4/8/3Q4/4K3 w - - 0 1"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# White has a queen vs a lone king → decisively winning for the side to move.
WHITE_WINNING = "4k3/8/8/8/8/8/8/3QK3 w - - 0 1"

_HAVE_SF = os.path.exists(STOCKFISH_PATH)
requires_sf = pytest.mark.skipif(not _HAVE_SF, reason="Stockfish binary not present")


@pytest.mark.unit
class TestClaimExtraction:
    def test_cued_legal_move_is_recommended(self):
        v = evaluate_turn(START, "You should play e4 to open the center.", depth=D)
        kinds = [c["kind"] for c in v.claims]
        assert "recommended_move" in kinds

    def test_uncued_legal_move_is_a_reference_not_a_recommendation(self):
        v = evaluate_turn(START, "The square e4 is an important central square.", depth=D)
        # 'e4' parses as a legal move but isn't cued → a neutral reference.
        move_claims = [c for c in v.claims if c["kind"] in ("recommended_move", "move_reference")]
        assert all(c["kind"] != "recommended_move" for c in move_claims)

    def test_illegal_uncued_token_is_not_flagged(self):
        # 'e5' is illegal for White at the start; without a move cue it must not
        # be treated as a hallucinated move claim (it's just a square mention).
        v = evaluate_turn(START, "Black often contests the e5 square.", depth=D)
        assert v.illegal_move_rate == 0.0
        assert not any(c["kind"] == "illegal_move" for c in v.claims)


@pytest.mark.unit
@requires_sf
class TestAdjudication:
    def test_known_best_move_scores_top(self):
        v = evaluate_turn(FREE_QUEEN, "You should play Qxd4, winning the queen.", depth=D)
        assert v.status == "ok"
        assert v.correctness_score == 1.0
        rec = [c for c in v.claims if c["kind"] == "recommended_move"][0]
        assert rec["verdict"] == "best"
        assert rec["detail"]["cp_loss"] == 0.0

    def test_known_blunder_scores_zero(self):
        # Ignoring the free queen and shuffling the king hangs everything.
        v = evaluate_turn(FREE_QUEEN, "You should play Kf1 here.", depth=D)
        rec = [c for c in v.claims if c["kind"] == "recommended_move"][0]
        assert rec["verdict"] == "blunder"
        assert v.correctness_score == 0.0

    def test_illegal_move_is_hard_fail(self):
        v = evaluate_turn(START, "You should play Nf6 immediately.", depth=D)
        assert v.illegal_move_rate == 1.0
        assert v.correctness_score == 0.0
        assert any(c["kind"] == "illegal_move" and c["verdict"] == "illegal" for c in v.claims)

    def test_eval_claim_agrees_when_winning(self):
        v = evaluate_turn(WHITE_WINNING, "You are completely winning here.", depth=D)
        ev = [c for c in v.claims if c["kind"] == "eval_claim"][0]
        assert ev["verdict"] == "agree"

    def test_eval_claim_disagrees_when_wrong(self):
        v = evaluate_turn(WHITE_WINNING, "The position is roughly equal.", depth=D)
        ev = [c for c in v.claims if c["kind"] == "eval_claim"][0]
        assert ev["verdict"] == "disagree"
        assert v.correctness_score == 0.0

    def test_deterministic_across_runs(self):
        text = "You should play Qxd4, a strong move."
        a = evaluate_turn(FREE_QUEEN, text, depth=D)
        b = evaluate_turn(FREE_QUEEN, text, depth=D)
        assert a.correctness_score == b.correctness_score
        assert a.to_dict()["claims"] == b.to_dict()["claims"]


@pytest.mark.unit
class TestGracefulDegradation:
    def test_missing_stockfish_returns_skipped(self):
        v = evaluate_turn(START, "You should play e4.", depth=D,
                          stockfish_path="/nonexistent/stockfish")
        assert v.status == "skipped"
        assert v.correctness_score is None
        assert "stockfish_missing" in v.notes

    def test_invalid_fen_returns_skipped_not_crash(self):
        v = evaluate_turn("not-a-fen", "You should play e4.", depth=D)
        assert v.status == "skipped"
        assert "invalid_fen" in v.notes

    def test_default_depth_constant_is_stable(self):
        # The builder, runner and baseline all pin this — guard against drift.
        assert DEFAULT_DEPTH == 12
