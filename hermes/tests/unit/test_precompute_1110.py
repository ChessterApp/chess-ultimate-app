"""10.11: the review reads what the precompute did (items 2–3 of the owner's request of 04.10).

- a board created with a game (a game tab) is told to the precompute like a saved one;
- «разбери эту партию» about the game on the board — a finished game with the coach, a database game — gets the
  server's review step (COACH_REVIEW_BOARD), never a game in progress;
- a turn that carries the server's moments has no scan tools (COACH_REVIEW_NO_RESCAN);
- the daily plan's review game is scanned in the background (COACH_PRECOMPUTE_PLAN), behind every board;
- two scans of one game share their searches.
Engine tests run on the fake UCI engine of tests/support (no Stockfish needed)."""

import json
import threading
import time
from types import SimpleNamespace

import chess
import pytest

from src import config, engine_pool
from src.tools import stockfish
from tests.unit.test_p7_1031 import _gos, fake, precompute, server_pool  # noqa: F401 — fixtures

GAME = ("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 "
        "10. d4 Nbd7 *")


# ── the words ────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,ok", [
    ("Разбери эту партию", True), ("Разбери мою партию, где я ошибся?", True), ("где я ошибся", True),
    ("мои ошибки в этой партии", True), ("review my game", True), ("Разбери мои ходы", True),
    ("разбери эту позицию", False), ("разбор хода Nxe5", False), ("где я ошибся на 20-м ходу", False),
    ("где я ошибся на 20 ходу", False), ("review this move", False), ("разбери 12. Nxe5", False),
    ("что тут играть?", False),
])
def test_a_game_review_is_told_from_a_question_about_one_position(text, ok):
    from src.intent import asks_game_review

    assert asks_game_review(text) is ok


def test_a_review_needs_a_game_of_ten_plies():
    from src.intent import asks_game_review

    assert asks_game_review("Разбери партию", GAME)
    assert not asks_game_review("Разбери партию", "1. e4 e5 2. Nf3 *")


# ── which game the turn reviews ──────────────────────────────────────────────────────────────────────────────────
def _board(kind="master_game", pgn=GAME, status=None):
    return SimpleNamespace(kind=kind, pgn=pgn, game_state={"status": status} if status else None)


def test_the_board_review_takes_the_game_on_the_board_but_never_a_game_in_progress():
    from src.server import _board_review_pgn

    assert _board_review_pgn(_board(), "Разбери эту партию") == GAME
    assert _board_review_pgn(_board("game", status="finished"), "где я ошибся?") == GAME
    assert _board_review_pgn(_board("study"), "Разбери партию") == GAME            # a game loaded on the study board
    assert _board_review_pgn(_board("game", status="playing"), "где я ошибся?") is None   # no hints in a game
    assert _board_review_pgn(_board(), "разбери эту позицию") is None
    assert _board_review_pgn(_board(pgn=""), "Разбери партию") is None
    assert _board_review_pgn(_board(pgn="1. e4 e5 *"), "Разбери партию") is None


def _agent(*names):
    tools = [{"type": "function", "function": {"name": n}} for n in names]
    return SimpleNamespace(tools=tools, valid_tool_names={n for n in names}, model="google/gemini-3.8-flash")


def test_a_turn_with_the_servers_moments_offers_no_scan_tools():
    from src.server import REVIEW_SCAN_TOOLS, _drop_tools

    agent = _agent("find_critical_moments", "review_game", "analyze_position", "board_control")
    assert _drop_tools(agent, REVIEW_SCAN_TOOLS, agent.model) == ["find_critical_moments", "review_game"]
    assert [t["function"]["name"] for t in agent.tools] == ["analyze_position", "board_control"]
    assert agent.valid_tool_names == {"analyze_position", "board_control"}
    # a model with a cached tool block keeps its full set (the cache is worth more than the dropped call)
    claude = _agent("find_critical_moments", "analyze_position")
    assert _drop_tools(claude, REVIEW_SCAN_TOOLS, "anthropic/claude-sonnet-4.5") == []
    assert len(claude.tools) == 2


# ── the server turn, the model replaced ──────────────────────────────────────────────────────────────────────────
@pytest.fixture
def turn(monkeypatch):
    """The text turn with the model replaced: (client, seen) — seen gets the message and the tools of the call."""
    from fastapi.testclient import TestClient

    from src import game_mode, server
    from src.tools import critical_moments as cm

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-key")
    monkeypatch.setattr(config, "COACH_TWO_STAGE", False)
    monkeypatch.setattr(config, "COACH_TOOL_SUBSET", False, raising=False)
    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))
    scans = []

    def scan(pgn, *a, **k):
        scans.append(pgn)
        return {"total_moves": 20, "engine_depth": 12, "evals_from": "white", "critical_moments": [{
            "move_number": 5, "side": "white", "move": "O-O", "eval_before": 0.3, "eval_after": -1.5,
            "eval_change": -1.8, "type": "mistake", "fen_before": chess.STARTING_FEN, "best_move": "d4"}]}

    monkeypatch.setattr(cm, "find_critical_moments", scan)
    seen: dict = {}

    def fake_chat(agent, message, session_id, stream_callback=None, student_message="", game_step=False):
        seen["message"] = message
        seen["tools"] = {t["function"]["name"] for t in (getattr(agent, "tools", None) or [])}
        if stream_callback:
            stream_callback("Хорошо.")
        return "Хорошо."

    monkeypatch.setattr(server, "_chat_in_session", fake_chat)
    client = TestClient(server.app)
    yield client, seen, scans


H = {"X-User-Id": "precompute-1110"}


def _say(client, sid, text, **kw):
    frames = []
    with client.stream("POST", "/api/coach/chat", json={"message": text, "session_id": sid, "locale": "ru", **kw},
                       headers=H) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                frames.append(json.loads(line[5:]))
    return frames


def test_a_database_game_in_its_tab_is_reviewed_by_the_server_without_scan_tools(turn):
    client, seen, scans = turn
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    client.post(f"/api/coach/sessions/{sid}/boards", json={"kind": "master_game", "pgn": GAME}, headers=H)
    frames = _say(client, sid, "Разбери эту партию")
    assert scans == [GAME]
    assert "Critical moments of the student's game" in seen["message"]
    assert not seen["tools"] & {"find_critical_moments", "review_game"}
    assert "analyze_position" in seen["tools"]
    # the game is on the board already: no load_pgn frame replaces it
    assert not any(a.get("type") == "load_pgn" for f in frames for a in f.get("board_actions") or [])


def test_a_position_question_on_the_game_board_keeps_its_tools_and_no_review(turn):
    client, seen, scans = turn
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    client.post(f"/api/coach/sessions/{sid}/boards", json={"kind": "master_game", "pgn": GAME}, headers=H)
    _say(client, sid, "Разбери эту позицию")
    assert scans == [] and "Critical moments" not in seen["message"]
    assert "find_critical_moments" in seen["tools"]


def test_the_game_with_the_coach_is_reviewed_once_over_and_never_while_on(turn):
    client, seen, scans = turn
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    game = client.post(f"/api/coach/sessions/{sid}/game", json={"color": "white", "elo": 1500}, headers=H).json()
    bid = game.get("board_id") or client.get(f"/api/coach/sessions/{sid}/boards", headers=H).json()["active_board_id"]
    for san in ("e4", "Nf3", "Bc4", "d3", "O-O", "c3"):
        board = chess.Board(next(b for b in client.get(f"/api/coach/sessions/{sid}/boards", headers=H).json()["boards"]
                                 if b["id"] == bid)["fen"])
        move = san if board.is_legal(board.parse_san(san)) else board.san(next(iter(board.legal_moves)))
        client.post(f"/api/coach/sessions/{sid}/game/{bid}/move", json={"move": move}, headers=H)
    _say(client, sid, "Где я ошибся?", board_id=bid)
    assert scans == [] and "Critical moments" not in seen["message"]       # the game is on: no engine verdicts
    client.post(f"/api/coach/sessions/{sid}/game/{bid}/resign", headers=H)
    _say(client, sid, "Где я ошибся?", board_id=bid)
    assert len(scans) == 1 and "Critical moments of the student's game" in seen["message"]
    assert not seen["tools"] & {"find_critical_moments", "review_game"}


def test_switches_restore_the_old_turn(turn, monkeypatch):
    client, seen, scans = turn
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    client.post(f"/api/coach/sessions/{sid}/boards", json={"kind": "master_game", "pgn": GAME}, headers=H)
    monkeypatch.setattr(config, "COACH_REVIEW_BOARD", False)
    _say(client, sid, "Разбери эту партию")
    assert scans == [] and "find_critical_moments" in seen["tools"]
    monkeypatch.setattr(config, "COACH_REVIEW_BOARD", True)
    monkeypatch.setattr(config, "COACH_REVIEW_NO_RESCAN", False)
    _say(client, sid, "Разбери эту партию")
    assert scans == [GAME] and "find_critical_moments" in seen["tools"]


# ── the precompute ───────────────────────────────────────────────────────────────────────────────────────────────
def test_a_board_created_with_a_game_is_scanned_in_the_background(precompute):
    from src import engine_precompute
    from src.sessions import session_store
    from src.tools import critical_moments as cm

    _, log = precompute
    session = session_store.create("p1110-user")
    session.add_board(activate=True, kind="master_game", pgn=GAME)        # POST …/boards: never saved again
    assert engine_precompute.idle(20)
    n = len(_gos(log))
    t = time.monotonic()
    review = cm.find_critical_moments(GAME)
    assert review["total_moves"] == 20 and time.monotonic() - t < 0.05 and len(_gos(log)) == n


def test_the_offered_game_is_scanned_behind_the_boards_and_switches_off(precompute, monkeypatch):
    from src import engine_precompute
    from src.tools import critical_moments as cm

    _, log = precompute
    monkeypatch.setattr(config, "COACH_PRECOMPUTE_PLAN", False)
    assert engine_precompute.game_offered("plan/u1", GAME) is None
    monkeypatch.setattr(config, "COACH_PRECOMPUTE_PLAN", True)
    job = engine_precompute.game_offered("plan/u1", GAME)
    assert job is not None
    with engine_precompute._lock:
        task = engine_precompute._pending.get("plan/u1")
        assert task is None or task.level == engine_precompute.LEVEL_OFFERED > engine_precompute.LEVEL_BOARD
    assert engine_precompute.idle(20)
    n = len(_gos(log))
    assert cm.find_critical_moments(GAME)["total_moves"] == 20 and len(_gos(log)) == n


def test_a_new_offer_replaces_the_old_one():
    from src import engine_precompute

    with engine_precompute._lock:
        old = engine_precompute._Task("plan/u2", engine_pool.Job("old"), [("x", lambda: None)], 0,
                                      engine_precompute.LEVEL_OFFERED)
        engine_precompute._pending["plan/u2"] = old
        engine_precompute._cancel_locked("plan/u2")
    assert old.job.cancelled and "plan/u2" not in engine_precompute._pending


def test_the_daily_plan_offers_its_review_game(monkeypatch):
    from src import daily_plan, engine_precompute

    offered = []
    monkeypatch.setattr(engine_precompute, "game_offered", lambda key, pgn: offered.append((key, pgn)))
    monkeypatch.setattr(daily_plan, "_sources", lambda uid: {
        "games": lambda: [{"id": "g1", "pgn": GAME, "white": "A", "black": "B"}],
        "insights": lambda: [], "focus": lambda: []})
    plan = daily_plan.load_daily_plan("u3")
    assert plan["cards"][0] == {"type": "review_last_game", "game_id": "g1", "title": "A – B"}
    assert offered == [("plan/u3", GAME)]


def test_the_daily_plan_never_fails_on_the_precompute(monkeypatch):
    from src import daily_plan, engine_precompute

    def boom(key, pgn):
        raise RuntimeError("engine down")

    monkeypatch.setattr(engine_precompute, "game_offered", boom)
    monkeypatch.setattr(daily_plan, "_sources", lambda uid: {
        "games": lambda: [{"id": "g1", "pgn": GAME, "white": "A", "black": "B"}],
        "insights": lambda: [], "focus": lambda: []})
    assert daily_plan.load_daily_plan("u4")["cards"][0]["type"] == "review_last_game"


def test_two_scans_of_one_game_search_each_position_once(server_pool):
    """The turn's review step and the background scan of the board it loads, side by side."""
    from src.tools import critical_moments as cm

    _, log = server_pool
    out = []
    threads = [threading.Thread(target=lambda: out.append(cm.find_critical_moments(GAME))) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert out[0] == out[1] and out[0]["total_moves"] == 20
    assert len(_gos(log)) <= 21 + 4          # 21 positions; at most a search or two raced at the start of each half


# ── the load test of 10.11: a review the turn cannot wait for never holds the live path ───────────────────────────
def test_the_scan_estimate_counts_what_is_left_at_this_hosts_speed(server_pool, monkeypatch):
    from src.tools import critical_moments as cm

    pool, _ = server_pool
    monkeypatch.setattr(cm, "_search_ms", [100.0])
    monkeypatch.setattr(pool, "answer_wait_ms", 0.0)
    missing, est = cm.scan_estimate_ms(GAME)
    assert missing == 21 and est == pytest.approx(21 / 2 * 100)           # two processes, no wait for one
    monkeypatch.setattr(pool, "answer_wait_ms", 400.0)                     # the other students' answers queue
    assert cm.scan_estimate_ms(GAME)[1] == pytest.approx(21 / 2 * 500)
    cm.find_critical_moments(GAME)
    assert cm.scan_estimate_ms(GAME) == (0, 0.0)                          # all in the cache now
    assert cm._search_ms[0] != 100.0                                      # learned from the searches it made
    assert cm.scan_estimate_ms("not a game")[0] in (-1, 0)


def test_a_board_game_whose_scan_does_not_fit_goes_as_on_main_and_is_finished_in_the_background(turn, monkeypatch):
    from src import engine_precompute
    from src.tools import critical_moments as cm

    client, seen, scans = turn
    later = []
    monkeypatch.setattr(cm, "scan_estimate_ms", lambda pgn: (60, 30_000.0))
    monkeypatch.setattr(engine_precompute, "review_soon", lambda key, pgn: later.append((key, pgn)))
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    bid = client.post(f"/api/coach/sessions/{sid}/boards", json={"kind": "master_game", "pgn": GAME},
                      headers=H).json()["id"]
    _say(client, sid, "Разбери эту партию")
    assert scans == [] and "Critical moments" not in seen["message"]       # no 6 s wait for a scan that cannot end
    assert "find_critical_moments" in seen["tools"]                         # the model's tools, as on main
    assert later == [(f"{sid}/{bid}#review", GAME)]
    monkeypatch.setattr(cm, "scan_estimate_ms", lambda pgn: (0, 0.0))      # the background has done it
    _say(client, sid, "Разбери эту партию")
    assert scans == [GAME] and "Critical moments of the student's game" in seen["message"]


@pytest.fixture
def slow_pool(fake, monkeypatch):
    """The server's pool on a fake engine that takes 25 ms per depth (a depth-12 scan search: 0.3 s)."""
    exe, log, make = fake
    monkeypatch.setenv("FAKE_UCI_PLY_MS", "25")
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


def test_a_late_review_step_gives_the_engine_back(slow_pool, monkeypatch):
    """Past COACH_REVIEW_WAIT_MS the turn's scan is cancelled (both processes free at once) and handed to the
    background; nothing it stopped part-way is cached as a depth-12 look."""
    from concurrent.futures import ThreadPoolExecutor

    from src import server

    pool, _ = slow_pool
    monkeypatch.setattr(config, "COACH_REVIEW_WAIT_MS", 400)
    job, state, handed = engine_pool.Job("review step"), {}, []
    ex = ThreadPoolExecutor(1)
    started = time.monotonic()
    future = ex.submit(server._review_scan, GAME, job)
    assert server._await_review(future, started, state, job=job, on_late=lambda: handed.append(1)) is None
    assert state.get("late") and job.cancelled and handed == [1]
    t = time.monotonic()
    future.result(timeout=5)
    assert time.monotonic() - t < 1.0                                       # stopped, not run to its end
    deadline = time.monotonic() + 1.0
    while pool.status()["busy"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert pool.status()["busy"] == 0
    with stockfish._cache_lock:
        depths = [stockfish._result_depth(v) for v in stockfish._cache.values()]
    assert depths and all(d >= 12 for d in depths)                           # only whole searches were kept
    ex.shutdown()


def test_an_answer_waits_behind_no_abandoned_review(slow_pool, monkeypatch):
    """The live path after a late review: the model's own tool call (behind every answer-time search) gets a process
    at once — before, the abandoned scan held both processes at an answer's level until its last position (20 s to
    the model's answer on the 10.11 load test)."""
    from concurrent.futures import ThreadPoolExecutor

    from src import server

    monkeypatch.setattr(config, "COACH_REVIEW_WAIT_MS", 300)
    job = engine_pool.Job("review step")
    ex = ThreadPoolExecutor(1)
    started = time.monotonic()
    future = ex.submit(server._review_scan, GAME, job)
    server._await_review(future, started, {}, job=job)
    res = engine_pool.search(chess.Board().fen(), go="depth 2", multipv=1, priority=engine_pool.PRIORITY_TOOL)
    assert res.get("wait_ms", 1e9) < 500
    future.result(timeout=5)
    ex.shutdown()


def test_the_background_queue_stays_bounded_while_its_workers_are_blocked(monkeypatch):
    """20 students on a 2-vCPU host (10.11 load test): both workers wait on the pool in a step, and every board save
    still queues a task — the queue keeps MAX_TASKS, the furthest back and oldest dropped first."""
    from src import engine_precompute as ep

    monkeypatch.setattr(ep, "_ensure_workers", lambda: None)               # nobody takes work: the workers are blocked
    keys = [f"bound/{i}" for i in range(ep.MAX_TASKS + 16)]
    try:
        for i, key in enumerate(keys):
            ep._submit(key, [("x", lambda: None)], key, level=ep.LEVEL_OFFERED if i % 2 else ep.LEVEL_BOARD)
        with ep._lock:
            mine = [k for k in ep._pending if k.startswith("bound/")]
            levels = [ep._pending[k].level for k in mine]
        assert len(mine) <= ep.MAX_TASKS
        assert levels.count(ep.LEVEL_BOARD) == (ep.MAX_TASKS + 16) // 2      # the offered games went first
    finally:
        with ep._lock:
            for key in keys:
                ep._cancel_locked(key)


def test_a_live_games_position_goes_before_every_boards_review(precompute, monkeypatch):
    """One student, 10.11 load test: the game's position after each move waited behind the tab's and the plan's
    80-move scans, and the move's verdict searched it itself. Now a game in progress has its own level, ahead."""
    from src import engine_precompute as ep
    from src.sessions import session_store

    assert ep.LEVEL_CONFIRM < ep.LEVEL_LIVE < ep.LEVEL_BOARD < ep.LEVEL_OFFERED
    seen = {}
    real = ep._submit

    def spy(key, steps, label, replace=True, level=ep.LEVEL_BOARD, delay_s=0.0):
        seen[key] = level
        return real(key, steps, label, replace=replace, level=level, delay_s=delay_s)

    monkeypatch.setattr(ep, "_submit", spy)
    session = session_store.create("p1110-live")
    tab = session.add_board(activate=False, kind="master_game", pgn=GAME)
    game = session.add_board(activate=True, kind="game", title="")
    game.game_state = {"status": "playing", "student_color": "white", "moves": []}
    ep.board_changed(session, game)
    over = session.add_board(activate=False, kind="game", title="")
    over.game_state = {"status": "finished", "student_color": "white", "moves": []}
    ep.board_changed(session, over)
    assert seen[f"{session.id}/{tab.id}"] == ep.LEVEL_BOARD
    assert seen[f"{session.id}/{game.id}"] == ep.LEVEL_LIVE
    assert seen[f"{session.id}/{over.id}"] == ep.LEVEL_BOARD          # a finished game's review: a board's level
    assert ep.idle(20)
