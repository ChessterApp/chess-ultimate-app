"""The opponent's move choice (pure part) — no Stockfish needed."""

import random
from collections import Counter

import pytest

from src.game_engine import (
    MATE_CP, STRENGTH_LIMIT_FROM, clamp_elo, pick_candidate, search_depth_for, tolerance_cp_for,
)


@pytest.mark.unit
def test_clamp_and_curves():
    assert clamp_elo("abc") == 1500 and clamp_elo(100) == 400 and clamp_elo(9999) == 3190
    assert search_depth_for(400) == 6 and search_depth_for(1500) == 12 and search_depth_for(2100) == 15
    assert tolerance_cp_for(400) == 260 and 110 <= tolerance_cp_for(1500) <= 125 and tolerance_cp_for(2100) < 50
    assert STRENGTH_LIMIT_FROM == 2200


@pytest.mark.unit
def test_never_hangs_a_queen_even_at_the_floor():
    """A 400 opponent plays second-rate moves but never one 900 cp worse than the best."""
    cands = [("n1c3", 20), ("d2d4", 5), ("b1a3", -40), ("g2g4", -200), ("f2f3", -900)]
    rng = random.Random(1)
    seen = Counter(pick_candidate(cands, 400, rng) for _ in range(500))
    assert "f2f3" not in seen and "g2g4" in seen        # within 260 cp is playable at 400
    assert seen["n1c3"] > 200                             # the best still wins about half the time


@pytest.mark.unit
def test_strength_narrows_the_pool():
    cands = [("a", 0), ("b", -60), ("c", -150), ("d", -300)]
    rng = random.Random(7)
    at_800 = Counter(pick_candidate(cands, 800, rng) for _ in range(400))
    at_2000 = Counter(pick_candidate(cands, 2000, rng) for _ in range(400))
    assert set(at_800) >= {"a", "b", "c"} and "d" not in at_800
    assert set(at_2000) == {"a"}                          # tolerance ~52 cp → only the best


@pytest.mark.unit
def test_mate_is_always_played_and_allowed_mate_avoided():
    assert pick_candidate([("mate", MATE_CP - 3), ("other", 50)], 400, random.Random(0)) == "mate"
    cands = [("a", 10), ("b", -MATE_CP + 5)]
    assert all(pick_candidate(cands, 400, random.Random(i)) == "a" for i in range(50))
    assert pick_candidate([("only", -MATE_CP + 1)], 1500, random.Random(0)) == "only"


@pytest.mark.unit
def test_empty_candidates():
    with pytest.raises(RuntimeError):
        pick_candidate([], 1500, random.Random(0))
