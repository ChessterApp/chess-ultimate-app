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
