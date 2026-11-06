"""06.11 review of the check's own budget (a30a51d6): what a check joins, what it leaves behind, and one budget per
held sentence.

1. A precompute search a check joined and then gave up on is demoted back to the background: an answer may stop it
   again. Promoted for good, it held a process unstoppable up to STOCKFISH_EXACT_MAX_MS (8 s) on a pool of two.
2. A check joins only a search bounded at least as loosely as its own would be: the model's analyze_position call at
   the check's depth and lines is capped at STOCKFISH_MAX_MS, stops short on a slow host, and the check that waited
   for it had too little time left for its own search (the V-eng-02 class again).
3. verify_recommendation and the written line after the move share the sentence's VERIFY_MAX_MS; a fresh budget for
   the line held a sentence ~12 s once the searches were no longer cut at STOCKFISH_MAX_MS.

Fault tests on the fake UCI engine (tests/support/fake_uci.py, FAKE_UCI_PLY_MS ms per depth step).
"""

import os
import stat
import sys
import threading
import time

import chess
import pytest

from src import config, engine_pool, hypothetical
from src.tools import stockfish

FAKE = os.path.join(os.path.dirname(__file__), "..", "support", "fake_uci.py")
FEN = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
FEN2 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def _pool(tmp_path, monkeypatch, size):
    exe = tmp_path / "fake-stockfish"
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {os.path.abspath(FAKE)} \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "uci.log"
    monkeypatch.setenv("FAKE_UCI_LOG", str(log))
    monkeypatch.setenv("FAKE_UCI_MODE", "normal")
    monkeypatch.setenv("FAKE_UCI_PLY_MS", "40")
    pool = engine_pool.EnginePool(str(exe), size=size, hash_mb=16)
    pool.start()
    old = engine_pool._set_pool_for_tests(pool)
    monkeypatch.setattr(config, "STOCKFISH_POOL", True)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()
    return pool, old, log


@pytest.fixture
def pool1(tmp_path, monkeypatch):
    pool, old, log = _pool(tmp_path, monkeypatch, 1)
    yield pool, log
    engine_pool._set_pool_for_tests(old)
    pool.close()
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()


@pytest.fixture
def pool2(tmp_path, monkeypatch):
    pool, old, log = _pool(tmp_path, monkeypatch, 2)
    yield pool, log
    engine_pool._set_pool_for_tests(old)
    pool.close()
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()


def _gos(log) -> list:
    return [ln.split(" ", 1)[1] for ln in log.read_text().splitlines() if ln.split(" ", 1)[1].startswith("go ")]


def _background(fn, *args, **kwargs):
    box = {}

    def run():
        with engine_pool.priority(engine_pool.PRIORITY_BACKGROUND):
            box["res"] = fn(*args, **kwargs)

    th = threading.Thread(target=run, daemon=True)
    th.start()
    return th, box


def _flight_running(pool, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pool._busy:
            return True
        time.sleep(0.01)
    return False


# ── 1. a joiner that gives up undoes its promotion ─────────────────────────────────────────────────────────────────
def test_a_precompute_search_the_check_gave_up_on_can_be_stopped_by_an_answer_again(pool1):
    pool, log = pool1
    th, box = _background(stockfish.analyze_exact, FEN, 60, 1)        # 60 plies × 40 ms ≈ 2.4 s, cap 8 s
    assert _flight_running(pool)
    with engine_pool.priority(engine_pool.PRIORITY_CHECK):
        t = time.monotonic()
        assert hypothetical._engine_lines(FEN, 1, None, 60, time.monotonic() + 0.3) is None
        assert time.monotonic() - t < 0.6                             # it joined the flight and gave up at its deadline
    # the next answer's engine line gets the only process at once: the flight is a background search again
    t = time.monotonic()
    res = stockfish.analyze_position(FEN2, depth=4, multipv=1, max_ms=3000)
    assert res.get("lines"), res
    assert time.monotonic() - t < 0.8
    th.join(5)
    assert "error" in box["res"]                                      # stopped for the answer: incomplete…
    assert stockfish.exact_get(FEN, 60, 1) is None                    # …and never kept


def test_a_joiner_that_gives_up_leaves_the_others_promotion(pool1):
    pool, log = pool1
    th, box = _background(stockfish.analyze_exact, FEN, 30, 1)        # ≈ 1.2 s
    assert _flight_running(pool)
    got = {}

    def line_joiner():
        with engine_pool.priority(engine_pool.PRIORITY_LINE):
            got["res"] = stockfish.exact_join(FEN, 30, 1, 5.0)

    j = threading.Thread(target=line_joiner, daemon=True)
    j.start()
    time.sleep(0.05)
    with engine_pool.priority(engine_pool.PRIORITY_CHECK):
        assert stockfish.exact_join(FEN, 30, 1, 0.2) is None          # gives up
    busy = [p for _, p, _ in pool._busy.values()]
    assert busy == [engine_pool.PRIORITY_LINE]                        # still the waiting joiner's priority
    j.join(5)
    th.join(5)
    assert got["res"] and got["res"]["lines"][0]["depth"] == 30


# ── 2. a check joins only a search bounded at least as loosely as its own ──────────────────────────────────────────
def test_the_check_does_not_wait_for_a_search_capped_tighter_than_its_own(pool2, monkeypatch):
    """The model's analyze_position call (no clock of its own: STOCKFISH_MAX_MS) at the check's depth and lines is at
    work on the position after the move. Joined, it stopped short at its cap and the check's own search was then cut."""
    pool, log = pool2
    monkeypatch.setattr(stockfish, "MAX_MS", 600)                    # depth 16 needs ≈ 0.65 s here
    box = {}

    def tool():
        with engine_pool.priority(engine_pool.PRIORITY_TOOL):
            box["res"] = stockfish.analyze_position(FEN, depth=16, multipv=1)

    th = threading.Thread(target=tool, daemon=True)
    th.start()
    time.sleep(0.05)
    with engine_pool.priority(engine_pool.PRIORITY_CHECK):
        res = hypothetical._engine_lines(FEN, 1, None, 16, time.monotonic() + 1.0)
    th.join(5)
    assert box["res"].get("time_capped") is True                     # the tool's search stopped short…
    assert res is not None and res["lines"][0]["depth"] == 16          # …the check's own reached the depth beside it


def test_the_check_still_joins_a_precompute_search_with_room_to_complete(pool2):
    pool, log = pool2
    th, box = _background(stockfish.analyze_exact, FEN, 16, 1)        # cap STOCKFISH_EXACT_MAX_MS
    assert _flight_running(pool)
    with engine_pool.priority(engine_pool.PRIORITY_CHECK):
        res = hypothetical._engine_lines(FEN, 1, None, 16, time.monotonic() + 6.0)
    th.join(5)
    assert res is not None and res["lines"][0]["depth"] == 16
    assert sum(1 for g in _gos(log) if g.startswith("go depth 16")) == 1   # one search, not two side by side


# ── 3. one budget per held sentence ───────────────────────────────────────────────────────────────────────────────
def _recording_look(monkeypatch, pv):
    seen = []

    def look(fen, movetime_ms, deadline):
        seen.append(deadline)
        return {"score": 0.3, "pv": pv, "depth": hypothetical.VERIFY_DEPTH}

    monkeypatch.setattr(hypothetical, "_look", look)
    return seen


def test_the_written_line_after_the_engines_move_shares_the_sentences_budget(monkeypatch):
    seen = _recording_look(monkeypatch, "e2e4 e7e5")
    board = chess.Board()
    t = time.monotonic()
    assert hypothetical.verify_recommendation(board, chess.Move.from_uci("e2e4"), "e4",
                                              line=["e4", "e5", "Nf3", "Nc6"]) is None
    assert len(seen) == 3 and len(set(seen)) == 1                      # base, line's board, line's end: one deadline
    assert seen[0] <= t + hypothetical.VERIFY_MAX_MS / 1000.0 + 0.05


def test_the_written_line_after_a_move_that_holds_shares_the_sentences_budget(monkeypatch):
    seen = _recording_look(monkeypatch, "e2e4 e7e5")                   # the engine's move is e4; d4 holds (same eval)
    board = chess.Board()
    assert hypothetical.verify_recommendation(board, chess.Move.from_uci("d2d4"), "d4",
                                              line=["d4", "d5", "c4", "e6"]) is None
    assert len(seen) == 4 and len(set(seen)) == 1                      # base, after, line's board, line's end


def test_a_line_checked_on_its_own_gets_its_own_budget(monkeypatch):
    seen = _recording_look(monkeypatch, "e2e4 e7e5")
    t = time.monotonic()
    assert hypothetical.verify_line(chess.Board(), ["e4", "e5", "Nf3"]) is None
    assert len(seen) == 2 and seen[0] >= t + hypothetical.VERIFY_MAX_MS / 1000.0 - 0.05
