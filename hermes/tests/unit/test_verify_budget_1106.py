"""06.11: a check's fixed-depth search is bounded by the check's own budget, not by STOCKFISH_MAX_MS.

The 04.11 measurement (archive-1103/shipped1104/REPORT.md, «Регрессия, единственная»): V-eng-02 «самое сильное —
сыграй конём на e4» (p170) was cut by 04.11's predecessor and shown by 04.11-2 in 3 runs of 3. The move check
searches the position before and after the move to VERIFY_DEPTH (16) within VERIFY_MAX_MS (6 s), but every depth
search also carried the analysis cap (``go depth 16 movetime 3000``): on the bench host the search after Ne4 (650k
nodes) did not reach depth 16 in 3 s, the check got no complete line and said nothing.

The class: every search that judges (the exact store's searches — the move check, the forced-reply confirm, the
precompute's searches for them, the game's evals) is bounded by its own deadline; STOCKFISH_MAX_MS bounds only the
searches with none (the model's analyze_position call, the review's deeper looks). Fault tests run on the fake UCI
engine (tests/support/fake_uci.py, FAKE_UCI_PLY_MS ms per depth step); the recorded case on the real Stockfish.
"""

import os
import shutil
import stat
import sys
import time

import chess
import pytest

from src import config, engine_pool, hypothetical
from src.tools import stockfish

FAKE = os.path.join(os.path.dirname(__file__), "..", "support", "fake_uci.py")
REAL_SF = stockfish.STOCKFISH_PATH if (os.path.exists(stockfish.STOCKFISH_PATH)
                                       or shutil.which(stockfish.STOCKFISH_PATH)) else None
FEN = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
# V-eng-02 (p170): White to move, Ne4 gives away ~3 pawns (depth 20: −7.1 → −10.4); the engine's move is e4.
P170 = "rnbqkbnr/ppp2p1p/4p3/3p1p2/3P4/2N1PN2/PPP2PPP/R1BQK2R w KQkq - 0 7"


def _exe(tmp_path):
    exe = tmp_path / "fake-stockfish"
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {os.path.abspath(FAKE)} \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


@pytest.fixture
def slow_pool(tmp_path, monkeypatch):
    """The server's pool on a fake engine that needs 40 ms per depth step (depth 16 ≈ 0.65 s), analysis cap 150 ms."""
    exe = _exe(tmp_path)
    log = tmp_path / "uci.log"
    monkeypatch.setenv("FAKE_UCI_LOG", str(log))
    monkeypatch.setenv("FAKE_UCI_MODE", "normal")
    monkeypatch.setenv("FAKE_UCI_PLY_MS", "40")
    pool = engine_pool.EnginePool(str(exe), size=1, hash_mb=16)
    pool.start()
    old = engine_pool._set_pool_for_tests(pool)
    monkeypatch.setattr(config, "STOCKFISH_POOL", True)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    monkeypatch.setattr(stockfish, "MAX_MS", 150)
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()
    yield exe, log
    engine_pool._set_pool_for_tests(old)
    pool.close()
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()


def _gos(log) -> list:
    return [ln.split(" ", 1)[1] for ln in log.read_text().splitlines() if ln.split(" ", 1)[1].startswith("go ")]


def test_the_move_checks_search_reaches_its_depth_past_the_analysis_cap(slow_pool):
    _, log = slow_pool
    t = time.monotonic()
    res = hypothetical._engine_lines(FEN, 1, None, hypothetical.VERIFY_DEPTH,
                                     time.monotonic() + hypothetical.VERIFY_MAX_MS / 1000.0)
    assert res is not None and res["lines"][0]["depth"] == hypothetical.VERIFY_DEPTH
    assert time.monotonic() - t < 3.0
    go = _gos(log)[-1]
    assert go.startswith(f"go depth {hypothetical.VERIFY_DEPTH} movetime ")
    assert int(go.split()[-1]) > 150                                   # the check's own time, not STOCKFISH_MAX_MS
    # …and kept in the exact store: the same verdict in voice and in the next turn
    assert stockfish.exact_get(FEN, hypothetical.VERIFY_DEPTH, 1) is not None


def test_the_checks_own_deadline_still_ends_it(slow_pool):
    t = time.monotonic()
    res = hypothetical._engine_lines(FEN, 1, None, hypothetical.VERIFY_DEPTH, time.monotonic() + 0.3)
    assert res is None                                                 # short of the depth: it says nothing
    assert time.monotonic() - t < 0.3 + engine_pool.DEADLINE_SLACK_S + 0.2


def test_a_search_with_no_budget_of_its_own_keeps_the_analysis_cap(slow_pool):
    """The model's analyze_position call (and any depth search without a deadline) is still capped by MAX_MS."""
    _, log = slow_pool
    res = stockfish.analyze_position(FEN, depth=16, multipv=1)
    assert _gos(log)[-1] == "go depth 16 movetime 150"
    assert res.get("time_capped") is True


def test_the_exact_stores_searches_get_the_check_budget_not_the_analysis_cap(slow_pool):
    """The precompute asks analyze_exact(fen, VERIFY_DEPTH, 1) in advance for the check: capped at MAX_MS it never
    completed on a slow host, so nothing was stored and the check searched again."""
    _, log = slow_pool
    res = stockfish.analyze_exact(FEN, hypothetical.VERIFY_DEPTH, 1)
    assert _gos(log)[-1] == f"go depth {hypothetical.VERIFY_DEPTH} movetime {stockfish.EXACT_MAX_MS}"
    assert res["lines"][0]["depth"] == hypothetical.VERIFY_DEPTH and not res.get("time_capped")
    assert stockfish.exact_get(FEN, hypothetical.VERIFY_DEPTH, 1) is not None


def test_process_per_search_path_follows_the_same_rule(tmp_path, monkeypatch):
    """STOCKFISH_POOL=0: the caller's budget replaces the cap there too, and the process gets the pool's hash."""
    exe = _exe(tmp_path)
    log = tmp_path / "uci.log"
    monkeypatch.setenv("FAKE_UCI_LOG", str(log))
    monkeypatch.setenv("FAKE_UCI_PLY_MS", "1")
    monkeypatch.setattr(config, "STOCKFISH_POOL", False)
    monkeypatch.setattr(config, "STOCKFISH_HASH_MB", 24)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    monkeypatch.setattr(stockfish, "MAX_MS", 150)
    stockfish.analyze_position(FEN, depth=8, multipv=1, stockfish_path=str(exe), max_ms=4000)
    go = _gos(log)[-1]
    assert go.startswith("go depth 8 movetime ") and 3000 < int(go.split()[-1]) <= 4000
    stockfish.analyze_position(FEN, depth=8, multipv=1, stockfish_path=str(exe))
    assert _gos(log)[-1] == "go depth 8 movetime 150"
    cmds = [ln.split(" ", 1)[1] for ln in log.read_text().splitlines()]
    assert "setoption name Hash value 24" in cmds and "setoption name Threads value 1" in cmds


@pytest.mark.skipif(REAL_SF is None, reason="Stockfish not installed")
def test_recorded_case_v_eng_02_ne4_is_judged_when_the_analysis_cap_is_short(monkeypatch):
    """V-eng-02 on the real engine with the analysis cap below the search's need on this host (the bench host's
    3000 ms against ~3.3 s there; 100 ms here): the move check still reaches depth 16 and names Ne4 a mistake."""
    pool = engine_pool.EnginePool(REAL_SF, size=1, hash_mb=config.STOCKFISH_HASH_MB)
    old = engine_pool._set_pool_for_tests(pool)
    monkeypatch.setattr(config, "STOCKFISH_POOL", True)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    monkeypatch.setattr(stockfish, "MAX_MS", 100)
    monkeypatch.setattr(hypothetical, "VERIFY_MAX_MS", 30000)  # this test's host may be loaded: the depth decides
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()
    try:
        board = chess.Board(P170)
        move = board.parse_san("Ne4")
        why = hypothetical.verify_recommendation(board, move, "Ne4")
    finally:
        engine_pool._set_pool_for_tests(old)
        pool.close()
        stockfish.clear_analysis_cache()
        stockfish.clear_exact_store()
    assert why and why.startswith("Ne4 is a mistake on this board (engine)"), why
