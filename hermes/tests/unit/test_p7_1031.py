"""Plan 31.10 P7a: the persistent Stockfish pool (src/engine_pool.py), the exact store and the shared cache
(src/tools/stockfish.py), the game evals and the review scan on the pool.

Fault tests run against a fake UCI program (tests/support/fake_uci.py); the parity tests against the real
Stockfish are skipped where it is not installed."""

import os
import shutil
import stat
import sys
import threading
import time

import chess
import pytest

from src import config, engine_pool
from src.tools import stockfish

FAKE = os.path.join(os.path.dirname(__file__), "..", "support", "fake_uci.py")
REAL_SF = stockfish.STOCKFISH_PATH if (os.path.exists(stockfish.STOCKFISH_PATH)
                                       or shutil.which(stockfish.STOCKFISH_PATH)) else None
FEN = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
FEN2 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A fake engine binary: (path, log path, mode setter)."""
    exe = tmp_path / "fake-stockfish"
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {os.path.abspath(FAKE)} \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "uci.log"
    monkeypatch.setenv("FAKE_UCI_LOG", str(log))
    monkeypatch.setenv("FAKE_UCI_MODE", "normal")
    pools = []

    def make(size=2, mode="normal", recycle=5000, hash_mb=32):
        monkeypatch.setenv("FAKE_UCI_MODE", mode)
        pool = engine_pool.EnginePool(str(exe), size=size, hash_mb=hash_mb, recycle=recycle)
        pool.start()  # as the server's warm-up does
        pools.append(pool)
        return pool

    yield exe, log, make
    for p in pools:
        p.close()


def _log(log) -> list:
    return log.read_text().splitlines() if log.exists() else []


def _starts(log) -> int:
    return sum(1 for ln in _log(log) if ln.endswith(" START"))


@pytest.fixture
def server_pool(fake, monkeypatch):
    """The server's pool (engine_pool.search) on the fake engine, pool switched on, caches empty."""
    exe, log, make = fake
    pool = make()
    old = engine_pool._set_pool_for_tests(pool)
    monkeypatch.setattr(config, "STOCKFISH_POOL", True)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()
    yield pool, log
    engine_pool._set_pool_for_tests(old)
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()


# ── the pool itself ─────────────────────────────────────────────────────────────────────────────────────────────
def test_processes_start_once_and_every_search_starts_from_an_empty_hash(fake):
    _, log, make = fake
    pool = make(size=2)
    for _ in range(6):
        res = pool.search(FEN, go="depth 5", multipv=2)
        assert res["output"][-1].startswith("bestmove")
    assert _starts(log) == 2                                           # 6 searches, 2 processes
    cmds = [ln.split(" ", 1)[1] for ln in _log(log)]
    assert cmds.count("ucinewgame") == 6                               # an empty hash before each answer-time search
    assert "setoption name Threads value 1" in cmds and "setoption name Hash value 32" in cmds
    pool.search(FEN, go="depth 5", multipv=1, clear_hash=False)        # a background run over a game keeps it
    assert [ln.split(" ", 1)[1] for ln in _log(log)].count("ucinewgame") == 6


def test_pool_result_is_the_new_process_result(server_pool, fake, monkeypatch):
    """Same `go`, same parser: the pool's dict is byte-identical to the process-per-search path's."""
    exe, log, _ = fake
    pooled = stockfish.analyze_position(FEN, depth=6, multipv=3)
    monkeypatch.setattr(config, "STOCKFISH_POOL", False)
    spawned = stockfish.analyze_position(FEN, depth=6, multipv=3, stockfish_path=str(exe))
    assert pooled == spawned and pooled["lines"][0]["depth"] == 6 and len(pooled["lines"]) == 3
    gos = [ln.split(" ", 1)[1] for ln in _log(log) if " go " in f" {ln.split(' ', 1)[1]}"]
    assert gos[0] == gos[1] == f"go depth 6 movetime {stockfish.MAX_MS}"


def test_a_process_killed_mid_search_is_restarted_and_the_search_retried_once(fake):
    _, log, make = fake
    pool = make(size=1, mode="die_once")
    res = pool.search(FEN, go="depth 4", multipv=1)
    assert "output" in res and res["output"][-1].startswith("bestmove")
    assert pool.stats["restarts"] == 1 and pool.stats["retries"] == 1 and _starts(log) == 2


def test_a_process_that_always_dies_gives_an_error_not_a_hang(fake):
    _, _, make = fake
    pool = make(size=1, mode="die_on_go")
    t = time.monotonic()
    res = pool.search(FEN, go="depth 4", multipv=1)
    assert "error" in res and time.monotonic() - t < 10


def test_a_search_past_its_read_deadline_is_stopped(fake):
    _, log, make = fake
    pool = make(size=1, mode="hang")
    t = time.monotonic()
    res = pool.search(FEN, go="movetime 50", multipv=1, timeout=0.3)
    assert res == {"error": "Stockfish analysis timed out."}
    assert time.monotonic() - t < 2.0
    assert any(ln.endswith(" stop") for ln in _log(log))              # stop, and bestmove came back


def test_a_process_deaf_to_stop_is_killed_and_replaced(fake, monkeypatch):
    _, log, make = fake
    pool = make(size=1, mode="deaf")
    res = pool.search(FEN, go="movetime 50", multipv=1, timeout=0.2)
    assert "error" in res
    monkeypatch.setenv("FAKE_UCI_MODE", "normal")                      # the replacement answers
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and pool.status()["busy"]:
        time.sleep(0.05)
    res = pool.search(FEN, go="depth 3", multipv=1)
    assert "output" in res and _starts(log) == 2


def test_a_depth_search_gets_its_time_cap_once_a_process_is_free(fake):
    _, log, make = fake
    pool = make(size=1)
    busy = threading.Thread(target=pool.search, args=(FEN,), kwargs={"go": "movetime 400", "multipv": 1})
    busy.start()
    time.sleep(0.1)
    t = time.monotonic()
    res = pool.search(FEN2, go="depth 30 movetime 3000", multipv=1, deadline=t + 1.0)
    busy.join()
    assert "output" in res
    go = [ln.split(" ", 1)[1] for ln in _log(log) if ln.split(" ", 1)[1].startswith("go depth 30")][0]
    cap = int(go.split("movetime ")[1])
    assert cap <= 1000 - 200                                           # the ~300 ms spent waiting came off the cap


def test_no_time_left_while_waiting(fake):
    _, _, make = fake
    pool = make(size=1)
    busy = threading.Thread(target=pool.search, args=(FEN,), kwargs={"go": "movetime 500", "multipv": 1})
    busy.start()
    time.sleep(0.05)
    res = pool.search(FEN2, go="depth 10", multipv=1, deadline=time.monotonic() + 0.1)
    busy.join()
    assert res == {"error": "no time left for the search"}


def test_priority_order_checks_first(fake):
    _, log, make = fake
    pool = make(size=1)
    order = []
    busy = threading.Thread(target=pool.search, args=(FEN,), kwargs={"go": "movetime 300", "multipv": 1})
    busy.start()
    time.sleep(0.1)

    def ask(prio, tag):
        pool.search(f"8/8/8/8/8/8/8/K1k5 w - - 0 {tag}", go="depth 2", multipv=1, priority=prio)
        order.append(tag)

    threads = []
    for prio, tag in ((2, 1), (0, 2), (1, 3)):
        th = threading.Thread(target=ask, args=(prio, tag))
        th.start()
        threads.append(th)
        time.sleep(0.03)
    assert pool.running() == 4                                         # one at work, three waiting
    for th in threads + [busy]:
        th.join()
    assert order == [2, 3, 1]                                          # check, engine line, tool call


def test_background_is_stopped_when_an_answer_needs_the_process(fake):
    _, log, make = fake
    pool = make(size=1)
    job = engine_pool.Job("precompute")
    res_bg = {}

    def bg():
        res_bg.update(pool.search(FEN, go="movetime 5000", multipv=1, priority=engine_pool.PRIORITY_BACKGROUND,
                                  job=job))

    th = threading.Thread(target=bg)
    th.start()
    time.sleep(0.2)
    t = time.monotonic()
    res = pool.search(FEN2, go="depth 3", multipv=1, priority=engine_pool.PRIORITY_CHECK)
    waited = time.monotonic() - t
    th.join()
    assert "output" in res and waited < 1.0                            # not the background's 5 s
    assert res_bg.get("stopped") is True and pool.stats["preempted"] == 1


def test_background_further_back_gives_way_to_background_ahead(fake):
    """A board's own long search (level 5) is stopped for the positions the turn's check will ask for (level 3)."""
    _, _, make = fake
    pool = make(size=2)
    res_board = {}

    def board():
        res_board.update(pool.search(FEN, go="movetime 5000", multipv=1, priority=engine_pool.PRIORITY_BACKGROUND + 2))

    th = threading.Thread(target=board)
    th.start()
    time.sleep(0.2)
    t = time.monotonic()
    res = pool.search(FEN2, go="movetime 100", multipv=1, priority=engine_pool.PRIORITY_BACKGROUND)
    assert "output" in res and not res["stopped"] and time.monotonic() - t < 1.0
    th.join()
    assert res_board.get("stopped") is True
    # …and not the other way round: a search further back waits for the one ahead of it.
    ahead = threading.Thread(target=pool.search, args=(FEN,), kwargs={"go": "movetime 400", "multipv": 1,
                                                                     "priority": engine_pool.PRIORITY_BACKGROUND})
    ahead.start()
    time.sleep(0.1)
    t = time.monotonic()
    back = pool.search(FEN2, go="movetime 50", multipv=1, priority=engine_pool.PRIORITY_BACKGROUND + 2)
    ahead.join()
    assert "output" in back and not back["stopped"] and time.monotonic() - t >= 0.25


def test_background_takes_one_process_at_most(fake):
    _, _, make = fake
    pool = make(size=2)
    running = []
    peak = [0]
    lock = threading.Lock()

    def bg(n):
        with lock:
            running.append(n)
        pool.search(f"8/8/8/8/8/8/8/K1k5 w - - 0 {n + 1}", go="movetime 150", multipv=1,
                    priority=engine_pool.PRIORITY_BACKGROUND)

    def watch():
        end = time.monotonic() + 0.6
        while time.monotonic() < end:
            peak[0] = max(peak[0], pool.status()["background"])
            time.sleep(0.005)

    ths = [threading.Thread(target=bg, args=(n,)) for n in range(3)] + [threading.Thread(target=watch)]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    assert peak[0] == 1


def test_a_stale_job_is_dropped(fake):
    _, log, make = fake
    pool = make(size=1)
    job = engine_pool.Job("board 1, change 1")
    out = {}

    def run(tag, go):
        out[tag] = pool.search(FEN, go=go, multipv=1, priority=engine_pool.PRIORITY_BACKGROUND, job=job)

    a = threading.Thread(target=run, args=("running", "movetime 5000"))
    a.start()
    time.sleep(0.2)
    b = threading.Thread(target=run, args=("waiting", "movetime 100"))
    b.start()
    time.sleep(0.1)
    t = time.monotonic()
    pool.cancel(job)
    a.join()
    b.join()
    assert time.monotonic() - t < 1.0
    assert out["running"].get("stopped") is True
    assert out["waiting"] == {"error": "cancelled"}
    assert pool.search(FEN, go="depth 2", multipv=1, job=job) == {"error": "cancelled"}


def test_missing_binary_fails_at_once_and_is_retried_later(tmp_path, monkeypatch):
    pool = engine_pool.EnginePool(str(tmp_path / "no-such-stockfish"), size=2)
    t = time.monotonic()
    res = pool.search(FEN, go="depth 5", multipv=1)
    assert res == {"error": f"Stockfish not found at {tmp_path / 'no-such-stockfish'}."}
    assert time.monotonic() - t < 2.0 and pool.status()["down"]
    attempts = []
    real_start = engine_pool._Worker.start
    monkeypatch.setattr(engine_pool._Worker, "start", lambda self: attempts.append(1) or real_start(self))
    pool.search(FEN, go="depth 5", multipv=1)
    assert attempts == []                                              # not again before DOWN_RETRY_S
    monkeypatch.setattr(engine_pool, "DOWN_RETRY_S", 0.0)
    pool.search(FEN, go="depth 5", multipv=1)
    assert attempts                                                    # tried again
    pool.close()


def test_a_process_is_recycled_after_its_searches(fake):
    _, log, make = fake
    pool = make(size=1, recycle=3)
    for _ in range(3):
        assert "output" in pool.search(FEN, go="depth 2", multipv=1)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _starts(log) < 2:
        time.sleep(0.05)
    assert _starts(log) == 2 and pool.stats["recycled"] == 1
    assert "output" in pool.search(FEN, go="depth 2", multipv=1)


def test_an_idle_process_that_died_is_found_by_the_ping(fake, monkeypatch):
    _, log, make = fake
    monkeypatch.setattr(engine_pool, "PING_INTERVAL_S", 0.05)
    pool = make(size=1)
    pool.search(FEN, go="depth 2", multipv=1)
    pool._workers[0].proc.kill()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _starts(log) < 2:
        time.sleep(0.05)
    assert _starts(log) == 2
    assert "output" in pool.search(FEN, go="depth 2", multipv=1)


def test_engines_running_counts_busy_and_waiting(server_pool):
    pool, _ = server_pool
    ths = [threading.Thread(target=pool.search, args=(f"8/8/8/8/8/8/8/K1k5 w - - 0 {n + 1}",),
                            kwargs={"go": "movetime 300", "multipv": 1}) for n in range(3)]
    for th in ths:
        th.start()
    time.sleep(0.1)
    assert stockfish.engines_running() == 3                            # 2 at work + 1 waiting
    for th in ths:
        th.join()
    assert stockfish.engines_running() == 0


def test_with_time_cap():
    assert engine_pool._with_time_cap("depth 16 movetime 3000", 800) == "depth 16 movetime 800"
    assert engine_pool._with_time_cap("depth 16 movetime 300", 800) == "depth 16 movetime 300"
    assert engine_pool._with_time_cap("depth 16", 800) == "depth 16 movetime 800"
    assert engine_pool._with_time_cap("depth 9 searchmoves d1h5", 500) == "depth 9 movetime 500 searchmoves d1h5"
    assert engine_pool._with_time_cap("movetime 300", 100) == "movetime 300"


# ── the cache layer ─────────────────────────────────────────────────────────────────────────────────────────────
def _gos(log) -> list:
    return [ln.split(" ", 1)[1] for ln in _log(log) if ln.split(" ", 1)[1].startswith("go ")]


def test_two_requests_for_one_position_share_one_search(server_pool):
    """The site's prewarm and the turn's engine line, or voice and text, of one board: one search."""
    _, log = server_pool
    out = []
    ths = [threading.Thread(target=lambda: out.append(stockfish.analyze_timed(FEN, 300, multipv=3, min_depth=3)))
           for _ in range(3)]
    for th in ths:
        th.start()
        time.sleep(0.02)
    for th in ths:
        th.join()
    assert len(_gos(log)) == 1 and len(out) == 3 and all(o["lines"] for o in out)


def test_a_longer_search_at_work_is_not_waited_for(server_pool):
    """A depth search that may run its full 3 s does not hold a 300 ms request: that one searches itself."""
    _, log = server_pool
    th = threading.Thread(target=stockfish.analyze_cached, args=(FEN,), kwargs={"depth": 99, "multipv": 3})
    th.start()
    time.sleep(0.05)
    t = time.monotonic()
    res = stockfish.analyze_timed(FEN, 200, multipv=1, min_depth=3)
    assert res["lines"] and time.monotonic() - t < 1.5
    th.join()
    assert len(_gos(log)) == 2


def test_the_exact_store_keeps_complete_depth_searches_only(server_pool):
    stockfish.analyze_timed(FEN, 100, multipv=1, min_depth=1)          # a timed look: never exact
    assert stockfish.exact_get(FEN, 5, 1) is None
    full = stockfish.analyze_exact(FEN, 5, 2)
    assert full["lines"][0]["depth"] == 5 and stockfish.exact_get(FEN, 5, 2) == full
    assert stockfish.exact_get(FEN, 5, 1) is None and stockfish.exact_get(FEN, 6, 2) is None  # its own key


def test_a_capped_depth_search_is_not_exact(server_pool, monkeypatch):
    monkeypatch.setenv("FAKE_UCI_PLY_MS", "50")
    pool, _ = server_pool
    pool.close()
    pool.start()                                                       # processes with slow plies
    res = stockfish.analyze_exact(FEN, 40, 1, max_ms=300)
    assert res.get("time_capped") and stockfish.exact_get(FEN, 40, 1) is None


def test_forced_confirm_reads_the_exact_store_only(server_pool, monkeypatch):
    from src import hypothetical

    seen = []
    real = hypothetical.analyze_position
    monkeypatch.setattr(hypothetical, "analyze_position", lambda *a, **k: seen.append(k) or real(*a, **k))
    # A timed look that reached the depth is in the analysis cache: the confirm does not take it…
    stockfish._cache_put(FEN, {"lines": [{"pv": "e2e4", "score": 9.0, "depth": 30}] * 3, "evaluation": 9.0})
    first = hypothetical._engine_lines(FEN, 3, None, 5)
    assert seen and first["lines"][0]["score"] == 0.1
    # …and a second ask of the same sentence (voice, a later turn) reads the store: the same lines, no search.
    seen.clear()
    assert hypothetical._engine_lines(FEN, 3, None, 5) == first and not seen


def _kings(n: int) -> list:
    """*n* distinct legal positions (two kings)."""
    out = []
    for a in range(64):
        for b in range(64):
            if len(out) >= n:
                return out
            if chess.square_distance(a, b) > 1:
                board = chess.Board(None)
                board.set_piece_at(a, chess.Piece(chess.KING, chess.WHITE))
                board.set_piece_at(b, chess.Piece(chess.KING, chess.BLACK))
                out.append(board.fen())
    return out


def test_the_cache_holds_4096_positions_with_the_pool(server_pool, monkeypatch):
    for fen in _kings(300):
        stockfish._cache_put(fen, {"lines": [{"pv": "a1a2", "depth": 1}]})
    assert len(stockfish._cache) == 300 > stockfish._CACHE_MAX
    monkeypatch.setattr(config, "STOCKFISH_POOL", False)
    stockfish._cache_put(FEN, {"lines": [{"pv": "e2e4", "depth": 1}]})
    assert len(stockfish._cache) == stockfish._CACHE_MAX                # today's size without the pool


def test_pool_off_is_a_process_per_search(fake, monkeypatch):
    exe, log, _ = fake
    monkeypatch.setattr(config, "STOCKFISH_POOL", False)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    for _ in range(3):
        stockfish.analyze_position(FEN, depth=3, multipv=1, stockfish_path=str(exe))
    assert _starts(log) == 3 and engine_pool.running() == 0
    stockfish.clear_exact_store()
    stockfish.analyze_position(FEN, depth=3, multipv=1, stockfish_path=str(exe))
    assert stockfish.exact_get(FEN, 3, 1) is None                     # no exact store without the pool


def test_the_tool_call_waits_behind_checks(server_pool):
    seen = []
    real = engine_pool.EnginePool.search

    def spy(self, fen, **kw):
        seen.append(engine_pool.current_priority() if kw.get("priority") is None else kw["priority"])
        return real(self, fen, **kw)

    engine_pool.EnginePool.search = spy
    try:
        stockfish._handle_analyze_position({"fen": FEN, "depth": 3, "multipv": 1})
    finally:
        engine_pool.EnginePool.search = real
    assert seen == [engine_pool.PRIORITY_TOOL]


# ── game evals and the review scan ──────────────────────────────────────────────────────────────────────────────
def test_game_eval_on_the_pool_converts_like_python_chess(server_pool):
    from src.game_engine import _pooled_eval

    # The fake scores the side to move +10 cp with e2e4: the score from either side; e2e4 is no move here, so no best.
    board = chess.Board(FEN)
    assert _pooled_eval(board, chess.WHITE, 4) == (10, None)
    assert _pooled_eval(board, chess.BLACK, 4) == (-10, None)
    start = chess.Board()
    assert _pooled_eval(start, chess.WHITE, 4) == (10, "e4")
    assert stockfish.exact_get(start.fen(), 4, 1) is not None          # the review scan can read it


def test_game_eval_mate_scores_match_python_chess(monkeypatch):
    from src import game_engine

    monkeypatch.setattr(stockfish, "pool_on", lambda: True)
    board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
    monkeypatch.setattr(stockfish, "analyze_exact",
                        lambda fen, d, m: {"lines": [{"pv": "d1d8", "score": 10000, "mate_in": 1, "depth": 4}]})
    assert game_engine._pooled_eval(board, chess.WHITE, 12) == (9999, "Rd8#")
    assert game_engine._pooled_eval(board, chess.BLACK, 12) == (-9999, "Rd8#")
    monkeypatch.setattr(stockfish, "analyze_exact",
                        lambda fen, d, m: {"lines": [{"pv": "g8h8", "score": -10000, "mate_in": -2, "depth": 4}]})
    assert game_engine._pooled_eval(board, chess.WHITE, 12)[0] == -9998
    monkeypatch.setattr(stockfish, "analyze_exact", lambda fen, d, m: {"error": "x"})
    assert game_engine._pooled_eval(board, chess.WHITE, 12) is None   # the game's own process then


def test_review_scan_reads_positions_analysed_before(server_pool):
    from src.tools import critical_moments as cm

    _, log = server_pool
    pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *"
    first = cm.find_critical_moments(pgn)
    n = len(_gos(log))
    assert n == 7 and first["total_moves"] == 6
    again = cm.find_critical_moments(pgn)
    assert again == first and len(_gos(log)) == n                      # all from the cache: no search


@pytest.mark.skipif(REAL_SF is None, reason="Stockfish not installed")
def test_real_stockfish_pool_with_stockfish_default_hash_equals_a_new_process(monkeypatch):
    """With Stockfish's own default hash (16 MB) a pool search to a depth gives exactly a new process's lines; the
    plan's 32 MB hash changes some lines below the first (reported to the integrator)."""
    pool = engine_pool.EnginePool(REAL_SF, size=1, hash_mb=16)
    old = engine_pool._set_pool_for_tests(pool)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    try:
        for fen in (FEN, "r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPP2PPP/R2Q1RK1 w - - 4 8"):
            monkeypatch.setattr(config, "STOCKFISH_POOL", False)
            a = stockfish.analyze_position(fen, depth=10, multipv=3, max_ms=None)
            monkeypatch.setattr(config, "STOCKFISH_POOL", True)
            b = stockfish.analyze_position(fen, depth=10, multipv=3)
            c = stockfish.analyze_position(fen, depth=10, multipv=3)
            if a.get("time_capped") or b.get("time_capped"):
                pytest.skip("host too loaded to reach depth 10 in the cap")
            assert a["lines"] == b["lines"] == c["lines"]
    finally:
        engine_pool._set_pool_for_tests(old)
        pool.close()
        stockfish.clear_exact_store()


@pytest.mark.skipif(REAL_SF is None, reason="Stockfish not installed")
def test_real_stockfish_review_scan_matches_its_own_process(monkeypatch):
    """The scan on the pool in one half (one process, hash kept from move to move, 16 MB as the scan's own process)
    finds exactly the moments its own process found; two halves start the second from an empty hash."""
    from src.tools import critical_moments as cm

    pgn = ("1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 Qg5 5. Nxf7 Qxg2 6. Rf1 Qxe4+ 7. Be2 Nf3# 0-1")
    monkeypatch.setattr(config, "STOCKFISH_POOL", False)
    own = cm.find_critical_moments(pgn)
    pool = engine_pool.EnginePool(REAL_SF, size=1, hash_mb=16)
    old = engine_pool._set_pool_for_tests(pool)
    monkeypatch.setattr(config, "STOCKFISH_POOL", True)
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()
    real_scan = cm._scan_pooled
    monkeypatch.setattr(cm, "_scan_pooled", lambda positions: real_scan(positions, halves=1))
    try:
        pooled = cm.find_critical_moments(pgn)
    finally:
        engine_pool._set_pool_for_tests(old)
        pool.close()
        stockfish.clear_analysis_cache()
    assert pooled == own

