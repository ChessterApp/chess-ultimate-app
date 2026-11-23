"""Tester 20.11: Morphy's 15.Bxd7+ (the best move, mate after 16.Qb8+!) came out of the depth-12 scan as a blunder and
the coach advised 15.Bxf6. The engine's own choice is never a critical moment (critical_moments._moments)."""

import chess
import pytest

from src.tools import critical_moments as cm


def _positions(sans):
    board = chess.Board()
    positions = [board.copy()]
    for san in sans:
        board.push_san(san)
        positions.append(board.copy())
    return positions


@pytest.mark.unit
def test_the_engines_own_move_is_not_a_mistake_whatever_the_shallow_drop():
    sans = ["e4", "e5", "Nf3"]
    positions = _positions(sans)
    # Before 2.Nf3 the engine wanted Nf3 (g1f3) and saw +5; after it, +1 — the horizon, not the move.
    scanned = [(0.3, ["e2e4"]), (0.3, ["e7e5"]), (5.0, ["g1f3"]), (1.0, ["b8c6"])]
    assert cm._moments(positions, sans, scanned, 1.5)["critical_moments"] == []


@pytest.mark.unit
def test_another_move_with_the_same_drop_still_is():
    sans = ["e4", "e5", "Bc4"]
    positions = _positions(sans)
    scanned = [(0.3, ["e2e4"]), (0.3, ["e7e5"]), (5.0, ["g1f3"]), (1.0, ["b8c6"])]
    moments = cm._moments(positions, sans, scanned, 1.5)["critical_moments"]
    assert [(m["move"], m["best_move"]) for m in moments] == [("Bc4", "Nf3")]


# ── 23.11: on the team's server (Stockfish 16) the scan's own choice before 15 was 15.Bxf6 — the rule above never
# applied. A moment is a claim «the alternative was better»; it is checked by a deeper search of just the two moves.

def _bc4(verify, **kw):
    sans = ["e4", "e5", "Bc4"]
    scanned = [(0.3, ["e2e4"]), (0.3, ["e7e5"]), (5.0, ["g1f3"]), (1.0, ["b8c6"])]
    return cm._moments(_positions(sans), sans, scanned, 1.5, verify=verify, **kw)


@pytest.mark.unit
def test_a_claim_the_deeper_look_does_not_confirm_is_dropped():
    seen = []
    res = _bc4(lambda board, played, instead, ms: seen.append((played, instead)) or 0.4)
    assert res["critical_moments"] == [] and seen == [("f1c4", "g1f3")]
    assert "moments_found" not in res


@pytest.mark.unit
@pytest.mark.parametrize("answer", [2.0, None])
def test_a_confirmed_or_unanswered_claim_stays(answer):
    assert [m["move"] for m in _bc4(lambda *a: answer)["critical_moments"]] == ["Bc4"]


@pytest.mark.unit
def test_a_failing_check_leaves_the_claim():
    def boom(*a):
        raise RuntimeError("engine gone")
    assert [m["move"] for m in _bc4(boom)["critical_moments"]] == ["Bc4"]


@pytest.mark.unit
def test_no_time_left_no_check():
    import time
    calls = []
    res = _bc4(lambda *a: calls.append(1) or 0.0, deadline=time.monotonic() - 1)
    assert calls == [] and [m["move"] for m in res["critical_moments"]] == ["Bc4"]
    assert _bc4(lambda *a: calls.append(1) or 0.0, budget_ms=0)["critical_moments"] and calls == []


@pytest.mark.unit
def test_checks_go_biggest_first_and_stop_once_enough_are_confirmed(monkeypatch):
    monkeypatch.setattr(cm, "MAX_MOMENTS", 1)
    sans = ["e4", "e5", "Bc4", "Ke7"]
    # Bc4 loses 4, Ke7 loses 2 — Bc4 checked first; confirmed, so Ke7 is never checked.
    scanned = [(0.3, ["e2e4"]), (0.3, ["e7e5"]), (5.0, ["g1f3"]), (1.0, ["b8c6"]), (3.0, ["g8f6"])]
    calls = []
    res = cm._moments(_positions(sans), sans, scanned, 1.5, verify=lambda b, p, i, ms: calls.append(p) or 3.0)
    assert calls == ["f1c4"] and [m["move"] for m in res["critical_moments"]] == ["Bc4"]
    assert res["moments_found"] == 2


@pytest.mark.unit
def test_the_check_reads_the_two_moves_scores(monkeypatch):
    from src.tools import stockfish

    stockfish.clear_analysis_cache()
    got = {}

    def fake(fen, **kw):
        got.update(kw)
        return {"lines": [{"pv": "b5d7 f6d7 b3b8", "score": 10.2, "depth": 20},
                          {"pv": "g5f6 g7f6", "score": 8.2, "depth": 20}]}

    monkeypatch.setattr(stockfish, "analyze_position", fake)
    board = chess.Board("4kb1r/p2r1ppp/4qn2/1B2p1B1/4P3/1Q6/PPP2PPP/2KR4 w k - 2 15")
    assert cm._verify_claim(board, "b5d7", "g5f6", 2500) == pytest.approx(8.2 - cm.EVAL_CAP)  # +10.2 capped at 10
    assert got["searchmoves"] == ("b5d7", "g5f6") and got["multipv"] == 2 and got["depth"] == cm.VERIFY_DEPTH
    stockfish.clear_analysis_cache()


OPERA = ("1.e4 e5 2.Nf3 d6 3.d4 Bg4 4.dxe5 Bxf3 5.Qxf3 dxe5 6.Bc4 Nf6 7.Qb3 Qe7 8.Nc3 c6 9.Bg5 b5 10.Nxb5 cxb5 "
         "11.Bxb5+ Nbd7 12.O-O-O Rd8 13.Rxd7 Rxd7 14.Rd1 Qe6 15.Bxd7+ Nxd7 16.Qb8+ Nxb8 17.Rd8# 1-0")


@pytest.mark.unit
@pytest.mark.parametrize("depth", [8, 10, 12])
def test_morphy_is_never_told_he_erred_whatever_the_scan_saw(monkeypatch, depth):
    """A real engine: at these scan depths the scan's own choice before move 15 is 15.Bxf6 (Stockfish 19 at 8 and 10,
    Stockfish 16 at 12 on the team's server) — the claim must fall to the deeper check, not to luck of the hash."""
    import shutil

    if not shutil.which(cm.STOCKFISH_PATH) and not __import__("os").path.exists(cm.STOCKFISH_PATH):
        pytest.skip("no Stockfish")
    from src.tools import stockfish

    stockfish.clear_analysis_cache()
    monkeypatch.setattr(cm, "ANALYSIS_DEPTH", depth)
    monkeypatch.setattr(cm, "_pool_on", lambda: False)
    monkeypatch.setattr(stockfish, "pool_on", lambda: False)
    res = cm.find_critical_moments(OPERA, verify_budget_ms=30000)
    assert "critical_moments" in res
    assert not any(m["side"] == "white" for m in res["critical_moments"]), res["critical_moments"]
    stockfish.clear_analysis_cache()
