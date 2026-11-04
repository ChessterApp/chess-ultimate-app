"""fix1101 F8 — the wiring, prevention and speed findings of review-wiring (01.11) on next-1031 57bb4868.

Each test names the finding it pins:
  W1  shadow records reach the detector_shadow event: the engine stage's (answer_check.shadow_into), the voice check's
  W2  answer-check engine stage: every check of a held sentence at the front of the pool's queue; the precompute's
      confirms after captures and checks, every legal move further back
  W3  engine line cold: the threat after the best move starts beside the line (voice_engine_note._AfterBestThreat)
  W4  the lesson tutor's facts are main's (turn_facts.suspended, the context-carrying engine executor)
  W5  game-load review: the final position's note behind the scan, read only when ready
  W6  idle board: a short background search may take the second process
  W8  recap_scope fail-open (patch f8_answer_check.patch; here: the shadow/switch helpers fail open)
  W9  the pool's retry and read limit keep the caller's deadline
  W11 the game's own process is closed when idle beside the pool
  W12 ending_unproven has its own switch
  W13 the board-only fork facts: none beside a mate by checks (the relaxation was measured and dropped)
  W14 CheckContext.facts are the turn's own
  W15 eval_prevent audits every ply of the game corpus
"""

import concurrent.futures
import contextvars
import os
import stat
import sys
import threading
import time

import chess
import pytest

from src import config, engine_pool, turn_facts
from src.answer_check import CheckContext, _detector, record_shadow, shadow_event_payload, shadow_into
from src.tools import stockfish

FAKE = os.path.join(os.path.dirname(__file__), "..", "support", "fake_uci.py")
FEN = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"


@pytest.fixture
def fake(tmp_path, monkeypatch):
    exe = tmp_path / "fake-stockfish"
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {os.path.abspath(FAKE)} \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "uci.log"
    monkeypatch.setenv("FAKE_UCI_LOG", str(log))
    monkeypatch.setenv("FAKE_UCI_MODE", "normal")
    pools = []

    def make(size=2, mode="normal"):
        monkeypatch.setenv("FAKE_UCI_MODE", mode)
        pool = engine_pool.EnginePool(str(exe), size=size, hash_mb=16)
        pool.start()
        pools.append(pool)
        return pool

    yield exe, log, make
    for p in pools:
        p.close()


# ── W1 shadow records ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_shadow_record_without_a_context_goes_to_the_check_it_runs_for():
    ctx = CheckContext.from_fens([FEN])
    record_shadow(None, "piece_decides", ["outside any check"])  # no sink: dropped, never raises
    with shadow_into(ctx, "и решает ферзь."):
        record_shadow(None, "piece_decides", ["the queen's best move here is 8.Qg3"])
    record_shadow(None, "piece_decides", ["after the block"])
    payload = shadow_event_payload(ctx)
    assert payload["total"] == 1
    assert payload["records"][0] == {"detector": "piece_decides", "sentence": "и решает ферзь.",
                                     "issues": ["the queen's best move here is 8.Qg3"]}


def test_the_shadow_sink_reaches_a_worker_thread_through_the_held_check_wrapper():
    from src import server

    ctx = CheckContext.from_fens([FEN])
    seen = {}

    def detector():
        seen["priority"] = engine_pool.current_priority()
        record_shadow(None, "trade_swing_named", ["the trade the sentence names is 2 pawns"])
        return None

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        ex.submit(server._held_check(ctx, "отдают слона за пешку."), detector).result()
    assert seen["priority"] == engine_pool.PRIORITY_CHECK
    assert [r["detector"] for r in shadow_event_payload(ctx)["records"]] == ["trade_swing_named"]


def test_a_detector_switch_that_fails_is_off_and_never_raises(monkeypatch):
    import src.config as cfg

    def boom(*a, **k):
        raise RuntimeError("broken switch")

    monkeypatch.setattr(cfg, "detector_mode", boom)
    assert _detector("recap_scope", CheckContext.from_fens([FEN]), ["an issue"]) == []


def test_record_shadow_never_raises_on_odd_input():
    record_shadow(object(), "x", ["y"])  # a context without the list: it gets one, or nothing happens
    record_shadow(None, "x", None)


@pytest.fixture
def voice_client(monkeypatch):
    from fastapi.testclient import TestClient

    from src import server

    async def _no_limit(*a, **k):
        return None

    monkeypatch.setattr(server, "enforce_rate_limit", _no_limit)
    events = []
    monkeypatch.setattr(server, "log_event", lambda kind, **kw: events.append((kind, kw)))
    return TestClient(server.app), events, server


def test_the_voice_check_logs_its_shadow_records_and_not_the_earlier_sentences(voice_client, monkeypatch):
    client, events, server = voice_client
    import src.answer_check as ac

    real = ac.check_sentence

    def check(text, ctx, *a, **k):
        out = real(text, ctx, *a, **k)
        record_shadow(ctx, "open_character", [f"shadow on «{text[:20]}»"], text)
        return out

    monkeypatch.setattr(ac, "check_sentence", check)
    r = client.post("/api/coach/voice/check", headers={"X-User-Id": "f8-voice"}, json={
        "text": "Это спокойная позиция.", "previous": "Белые развили коня.", "engine": False,
        "fen": FEN, "question": "Что тут?"})
    assert r.status_code == 200
    shadow = [kw for kind, kw in events if kind == "detector_shadow"]
    assert len(shadow) == 1 and shadow[0]["surface"] == "voice"
    records = shadow[0]["payload"]["records"]
    # the earlier sentence was logged by its own voice check: only this sentence's record here
    assert [r["sentence"] for r in records] == ["Это спокойная позиция."]


def test_the_voice_engine_stage_runs_in_front_of_the_queue_with_its_shadow_sink(voice_client, monkeypatch):
    client, events, server = voice_client
    import src.hypothetical as hyp

    seen = {}

    def fake_verify(found, *a, **k):
        seen["priority"] = engine_pool.current_priority()
        record_shadow(None, "piece_decides", ["engine-stage shadow"])
        return None

    monkeypatch.setattr(hyp, "verify_recommendation", fake_verify)
    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
    import src.answer_check as ac

    monkeypatch.setattr(ac, "proposed_move", lambda text, ctx: ("d4", chess.Board(FEN), "d4"))
    r = client.post("/api/coach/voice/check", headers={"X-User-Id": "f8-voice2"}, json={
        "text": "Сыграй d4.", "fen": FEN, "question": "Что играть?", "engine": True})
    assert r.status_code == 200
    assert seen["priority"] == engine_pool.PRIORITY_CHECK
    shadow = [kw for kind, kw in events if kind == "detector_shadow"]
    assert shadow and shadow[0]["payload"]["records"][0]["issues"] == ["engine-stage shadow"]


# ── W4 the lesson tutor ──────────────────────────────────────────────────────────────────────────────────────────
def test_suspended_turn_facts_are_off_in_that_context_only():
    from src import position_facts

    assert turn_facts.enabled() and position_facts._vetting()
    with turn_facts.suspended():
        assert not turn_facts.enabled() and not position_facts._vetting()
        assert turn_facts.collect(chess.Board(FEN)) == []
        seen = []
        t = threading.Thread(target=lambda: seen.append(turn_facts.enabled()))
        t.start()
        t.join()
        assert seen == [True]  # a plain thread does not inherit it…
    assert turn_facts.enabled()


def test_the_engine_executor_carries_the_lesson_suspension_to_its_work():
    from src import server

    def probe():
        return turn_facts.enabled()

    with turn_facts.suspended():
        assert server._engine_pool.submit(probe).result() is False  # …the engine executor carries it
    assert server._engine_pool.submit(probe).result() is True


def test_the_lesson_board_facts_are_built_with_main_facts(monkeypatch):
    from src import server

    seen = {}

    def note(fen, movetime_ms=None, **k):
        seen["note"] = turn_facts.enabled()
        return None  # late: the board facts block is the lesson's fallback

    def block(fen, *a, **k):
        seen["block"] = turn_facts.enabled()
        return ""

    monkeypatch.setattr(server, "engine_note", note)
    import src.prompt_builder as pb

    monkeypatch.setattr(pb, "board_facts_block", block)
    monkeypatch.setattr(config, "COACH_LESSON_FACTS", True)
    monkeypatch.setattr(config, "COACH_ENGINE_NOTE", True)
    server._lesson_board_facts("что тут?", FEN)
    assert seen == {"note": False, "block": False}
    assert turn_facts.enabled()


def test_the_lesson_facts_block_equals_the_one_with_turn_facts_off(monkeypatch):
    from src.prompt_builder import board_facts_block

    fen = "2r1kb1r/1ppb1p2/5n2/4N3/6pq/1Q6/P1P1RPP1/R5K1 w - - 0 1"
    with turn_facts.suspended():
        lesson = board_facts_block(fen)
    monkeypatch.setattr(config, "COACH_TURN_FACTS", False)
    assert lesson == board_facts_block(fen)


# ── W3 engine line: the threat after the best move beside the line ───────────────────────────────────────────────
def test_the_threat_after_the_line_best_moves_is_started_before_the_line_ends(monkeypatch):
    import src.voice_engine_note as ven

    monkeypatch.setattr(stockfish, "pool_on", lambda: True)
    monkeypatch.setattr(engine_pool, "has_spare", lambda: True)
    started = []
    monkeypatch.setattr(ven._threat_pool, "submit", lambda fn, fen: started.append(fen))
    board = chess.Board(FEN)
    spec = ven._AfterBestThreat.start(board, 1500)
    assert spec is not None and abs(spec._delay - (1500 - 2 * 300 - 150) / 1000.0) < 1e-9
    spec._delay = 0.05
    spec.on_line("info string NNUE evaluation using nn-1.nnue")
    spec.on_line("info depth 12 seldepth 18 multipv 1 score cp 40 nodes 1 pv f1b5 a7a6")
    spec.on_line("info depth 12 seldepth 18 multipv 2 score cp 30 nodes 1 pv f1c4 g8f6")
    spec.on_line("info depth 13 seldepth 18 multipv 1 score cp 41 lowerbound nodes 1 pv d2d4")  # a bound: not a best
    time.sleep(0.3)
    spec.done()
    want = []
    for uci in ("f1b5", "f1c4"):
        b = board.copy()
        b.push_uci(uci)
        b.push(chess.Move.null())
        want.append(b.fen())
    assert started == want


def test_no_guessing_on_a_busy_pool_or_without_the_pool(monkeypatch):
    import src.voice_engine_note as ven

    monkeypatch.setattr(stockfish, "pool_on", lambda: False)
    assert ven._AfterBestThreat.start(chess.Board(FEN), 1500) is None
    monkeypatch.setattr(stockfish, "pool_on", lambda: True)
    monkeypatch.setattr(engine_pool, "has_spare", lambda: False)
    started = []
    monkeypatch.setattr(ven._threat_pool, "submit", lambda fn, fen: started.append(fen))
    spec = ven._AfterBestThreat.start(chess.Board(FEN), 1500)
    spec.best = "f1b5"
    spec.fire()
    assert started == []


def test_the_null_position_after_a_check_or_a_mate_is_not_searched():
    import src.voice_engine_note as ven

    board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    assert ven._null_fen_after(board, "a1a8") is None  # mate
    assert ven._null_fen_after(board, "a1a7") is not None
    assert ven._null_fen_after(board, "zz") is None


# ── W6 / W2 the pool's background rule, the held check ─────────────────────────────────────────────────────────
def test_short_searches_are_recognised():
    assert engine_pool._is_short("movetime 300") and engine_pool._is_short("movetime 300 searchmoves e2e4")
    assert not engine_pool._is_short("movetime 1500") and not engine_pool._is_short("depth 17 movetime 300")
    assert not engine_pool._is_short("depth 12")


def test_has_spare_is_false_while_a_search_waits(fake):
    _, _, make = fake
    pool = make(size=1)
    assert pool.has_spare()
    th = threading.Thread(target=pool.search, args=(FEN,), kwargs={"go": "movetime 400", "multipv": 1})
    th.start()
    time.sleep(0.15)
    assert not pool.has_spare()
    th.join()


# ── W9 the caller's deadline ─────────────────────────────────────────────────────────────────────────────────────
def test_a_hung_search_with_a_deadline_returns_by_the_deadline_plus_the_slack(fake):
    _, _, make = fake
    pool = make(size=1, mode="deaf")
    t = time.monotonic()
    res = pool.search(FEN, go="depth 30", multipv=1, deadline=time.monotonic() + 0.4)
    took = time.monotonic() - t
    assert "error" in res
    assert took < 0.4 + engine_pool.READ_SLACK_S + engine_pool.STOP_GRACE_S + 0.6


def test_the_retry_after_a_crash_keeps_the_deadline(fake, monkeypatch):
    _, log, make = fake
    pool = make(size=1, mode="die_on_go")
    t = time.monotonic()
    res = pool.search(FEN, go="depth 30", multipv=1, deadline=time.monotonic() + 0.3)
    assert "error" in res and time.monotonic() - t < 3.0
    # the retry's go (if any) was capped by what was left, never the first spec again past the deadline
    gos = [ln for ln in log.read_text().splitlines() if " go " in ln]
    caps = [int(ln.split("movetime ")[1].split()[0]) for ln in gos if "movetime" in ln]
    assert caps and all(c <= 300 for c in caps)


def test_read_timeout_follows_movetime_and_deadline():
    assert engine_pool._read_timeout("movetime 300", None, None) == pytest.approx(0.3 + engine_pool.READ_SLACK_S)
    assert engine_pool._read_timeout("depth 12", None, None) == 30.0
    got = engine_pool._read_timeout("depth 12", None, time.monotonic() + 1.0)
    assert got <= 1.0 + engine_pool.READ_SLACK_S + 0.01


# ── W2 the precompute's coverage ─────────────────────────────────────────────────────────────────────────────────
def test_confirms_follow_the_best_move_and_the_captures_and_checks(monkeypatch):
    from src import engine_precompute as ep

    # Legal's trap: 1.e4 e5 2.Nf3 d6 3.Bc4 Bg4 4.Nc3 g6 — 5.Nxe5 is a capture among the candidates
    board = chess.Board("rn1qkbnr/ppp2p1p/3p2p1/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5")
    captured = []
    monkeypatch.setattr(ep, "_confirm_steps", lambda fens: captured.extend(fens) or [("confirm", None)] * len(fens))
    rest = []
    steps, confirm = ep._after_move_steps(board, {"lines": [{"moves": ["O-O"]}]}, rest)
    after = {}
    for m in board.legal_moves:
        b = board.copy()
        b.push(m)
        after[b.fen()] = board.san(m)
    sans = [after[f] for f in captured]
    assert sans[0] == "O-O" and "Nxe5" in sans and len(sans) <= ep.CONFIRM_MOVES
    # every legal move gets its step: the candidates first, the rest further back
    assert len(steps) + len(rest) == sum(1 for m in board.legal_moves if not _ends(board, m))


def _ends(board, move):
    b = board.copy()
    b.push(move)
    return b.is_game_over()


def test_a_board_change_drops_the_old_boards_least_likely_moves(monkeypatch):
    from src import engine_precompute as ep

    monkeypatch.setattr(ep, "enabled", lambda: True)
    cancelled = []
    real = ep._cancel_locked
    monkeypatch.setattr(ep, "_cancel_locked", lambda key: (cancelled.append(key), real(key)))
    monkeypatch.setattr(ep, "_submit", lambda *a, **k: None)

    class B:
        id, kind, fen, pgn, game_state = "b1", "position", FEN, "", None

    class S:
        id = "s1"

    ep.board_changed(S(), B())
    assert "s1/b1" in cancelled and "s1/b1#rest" in cancelled and "s1/b1#line" not in cancelled


# ── W5 the review note ───────────────────────────────────────────────────────────────────────────────────────────
def test_the_review_note_is_read_only_when_ready():
    from src import server

    slow = concurrent.futures.Future()
    t = time.monotonic()
    assert server._ready_result(slow, server.REVIEW_NOTE_GRACE_S) is None
    assert time.monotonic() - t < 0.5
    done = concurrent.futures.Future()
    done.set_result({"note": "x"})
    assert server._ready_result(done, server.REVIEW_NOTE_GRACE_S) == {"note": "x"}
    assert server._ready_result(None, 0.01) is None


# ── W11 the game's own process ───────────────────────────────────────────────────────────────────────────────────
def test_the_game_process_is_closed_when_idle_beside_the_pool(monkeypatch):
    from src import game_engine

    closed = []

    class Eng:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(game_engine, "IDLE_CLOSE_S", 0.1)
    monkeypatch.setattr(stockfish, "pool_on", lambda: True)
    ge = game_engine.GameEngine(path="/nonexistent")
    ge._engine = Eng()
    assert ge._run(lambda e: 42) == 42
    time.sleep(0.4)
    assert closed == [True] and ge._engine is None
    # without the pool it stays (today's process for the server's life)
    monkeypatch.setattr(stockfish, "pool_on", lambda: False)
    ge._engine = Eng()
    ge._run(lambda e: 1)
    time.sleep(0.3)
    assert closed == [True] and ge._engine is not None


# ── W12 ending_unproven ──────────────────────────────────────────────────────────────────────────────────────────
def test_ending_unproven_has_its_own_switch(monkeypatch):
    from src import board_rules, hypothetical

    monkeypatch.setattr(board_rules, "tablebase", lambda b: None)
    board = chess.Board("8/8/6r1/6P1/PQ4p1/4k3/1K6/8 w - - 0 1")
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    assert hypothetical._ending_unproven(board, 7.9, 5.0) is True
    monkeypatch.setenv("COACH_DETECTORS_OFF", "ending_unproven")
    assert hypothetical._ending_unproven(board, 7.9, 5.0) is False


# ── W13 fork facts on the board-only path ───────────────────────────────────────────────────────────────────────
def test_a_fork_beside_a_mate_by_checks_in_three_is_not_told():
    """The game corpus's one bad fork fact (eval_prevent on 375 boards): Nd3+ wins a rook, but g3+ hxg3 Rf3+ Rxf3
    Ng2# mates in 3. The review's relaxation (tell double attacks that lose nothing by exchange count) was measured
    and dropped: 24 of 28 such moves lost ≥ 1.5 at depth 18, among them Qxd5+ on mate2-no — the very poison."""
    from src.position_facts import fork_facts, has_mate_by_checks, vetted_forks

    board = chess.Board("4B2r/8/8/3K2p1/5kPp/R6P/5rP1/4N3 w - - 0 1")
    assert has_mate_by_checks(board.copy(), skip=board.parse_san("Nd3+"))
    assert [board.san(m) for m, *_ in vetted_forks(board)] == []
    assert not any("Nd3+" in f for f in fork_facts(board))
    # a plain fork with no mate beside it is still told
    knight = chess.Board("r3k2r/8/8/1N6/8/8/8/4K3 w - - 0 1")
    assert any(f.startswith("a fork is available now: Nc7+") for f in fork_facts(knight))


def test_the_mate_search_by_checks_is_bounded():
    import time as _t

    from src.position_facts import has_mate_by_checks

    board = chess.Board("r1bq1rk1/ppp2ppp/2n2n2/3pp3/1bPP4/2N1PN2/PP1B1PPP/R2QKB1R w KQ - 0 7")
    t = _t.perf_counter()
    has_mate_by_checks(board.copy())
    assert (_t.perf_counter() - t) < 0.5


# ── W14 CheckContext.facts are the turn's own ───────────────────────────────────────────────────────────────────
def test_the_engine_block_renders_the_notes_own_facts_and_reports_them(monkeypatch):
    from src.prompt_builder import engine_note_block
    from src.turn_facts import Fact

    mine = Fact("piece_safety", "the knight on f6 is attacked; safe squares: d5, g8", {"sq": "f6", "safe": []}, "see")
    other = Fact("piece_safety", "SOMEONE ELSE'S FACT", {"sq": "a1", "safe": []}, "see")
    monkeypatch.setattr(turn_facts, "recent", lambda fen, engine=False: [other])
    given = []
    block = engine_note_block("[Engine] x", fen=FEN, facts=[mine], given=given)
    assert "safe squares: d5, g8" in block and "SOMEONE ELSE" not in block
    assert given == [mine]


def test_the_board_block_reports_the_typed_facts_it_gave():
    from src.prompt_builder import board_facts_block

    given = []
    block = board_facts_block("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", given=given)
    assert given and all(f.text in block for f in given)


# ── W15 eval_prevent's corpus ────────────────────────────────────────────────────────────────────────────────────
def test_eval_prevent_audits_every_ply_of_the_game_corpus():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    import importlib

    ev = importlib.import_module("eval_prevent")
    seen = {chess.Board(fen).epd() for _, _, fen in ev._positions()}
    assert len(seen) > 318


def test_context_copying_executor_keeps_contextvars():
    from src import server

    var = contextvars.ContextVar("f8_probe", default="unset")
    var.set("set")
    assert server._engine_pool.submit(var.get).result() == "set"


# ── W1 every detector a row catches: in shadow it records what 'on' cuts, on the detector_shadow event ─────────────
_SHADOW_ROWS = [("castle-ru", "retreat_cover", "src.claim_rules", "_shadowed"),
                ("lucena", "checks_geometry", "src.claim_rules", "_shadowed"),
                ("op-show-ck-attack", "prevents", "src.claim_rules", "_shadowed"),
                ("x-wc2021-g6", "trades", "src.trade_claims", "trade_issues"),
                ("mate2-no", "piece_decides", "src.line_verdict", "verify_claims"),
                ("st2_5", "student_capture", None, None),
                ("square-made_up", "race_distance", None, None),
                ("two-knights", "mate_squares", None, None),
                ("st1_2", "open_plain", None, None),
                ("plan-caro-adv", "pin_escape", None, None),
                ("can-scotch", "idea_scope", None, None)]


def _sink_patched(module: str, fn: str) -> bool:
    """The detector's own file routes its shadow through answer_check.record_shadow (fix1101/f8_<file>.patch)."""
    import importlib
    import inspect

    return "record_shadow" in inspect.getsource(getattr(importlib.import_module(module), fn))


@pytest.mark.parametrize("rid,name,module,fn", _SHADOW_ROWS, ids=[r[1] for r in _SHADOW_ROWS])
def test_a_detector_in_shadow_records_what_on_cuts(rid, name, module, fn, monkeypatch):
    import json
    import shutil
    from pathlib import Path

    if module and not _sink_patched(module, fn):
        pytest.skip(f"{module}.{fn} still logs only: apply fix1101/f8_{module.split('.')[-1]}.patch")
    row = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "detect1031" / "rows" / f"{rid}.json")
                     .read_text(encoding="utf-8"))
    if row["stage"] == "engine" and not (shutil.which(stockfish.STOCKFISH_PATH)
                                         or os.path.exists(stockfish.STOCKFISH_PATH)):
        pytest.skip("Stockfish is not installed")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
    from ctx_fixture import load_ctx, run_answer

    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
    got = {}
    for mode in ("on", "shadow"):
        monkeypatch.setenv("COACH_DETECTORS_SHADOW", name if mode == "shadow" else "")
        ctx = load_ctx(row["ctx"])
        with shadow_into(ctx):
            out = run_answer(row["prefix"] + [row["sentence"]], ctx, engine=row["stage"] == "engine",
                             live_game=row["turn"].get("live_game"))
        got[mode] = (out[-1][1], [r for r in (shadow_event_payload(ctx) or {}).get("records", [])
                                  if r["detector"] == name])
    cut, _ = got["on"]
    assert cut, f"{rid}: 'on' no longer cuts — the row's own test says why"
    assert not got["shadow"][0]
    recorded = [i for r in got["shadow"][1] for i in r["issues"]]
    assert any(cut[0][:150] in i or i[:150] in cut[0] for i in recorded), (cut, recorded)


def test_the_students_idea_moves_are_confirmed_ahead_of_the_candidates(monkeypatch):
    """trap-legal (replay 01.11): «можно сыграть Nxe5?» — the confirm after 5.Nxe5 sat at the confirm level and the
    candidates' searches stopped it six times; the held sentence searched it itself (1.6 s, lost under load)."""
    from src import engine_precompute as ep

    got = {}
    monkeypatch.setattr(ep, "enabled", lambda: True)
    monkeypatch.setattr(ep, "_submit", lambda key, steps, label, replace=True, level=ep.LEVEL_BOARD:
                        got.setdefault(key, level))
    ep.after_ideas("s", "b", ["rn1qkbnr/ppp2p1p/3p2p1/4N3/2B1P1b1/2N5/PPPP1PPP/R1BQK2R b KQkq - 0 5"])
    assert got == {"s/b#ideas": ep.LEVEL_IDEA}


def test_two_short_steps_of_a_task_run_at_once_but_one_long(monkeypatch):
    from src import engine_precompute as ep

    job = engine_pool.Job("t")
    short = ep._Task("k", job, [("after_move", None), ("after_move", None)], 0, ep.LEVEL_CHECK)
    short.busy = 1
    assert ep._startable(short)
    short.busy = ep.WORKERS
    assert not ep._startable(short)
    long = ep._Task("k2", job, [("confirm", None)], 0, ep.LEVEL_CONFIRM)
    long.busy = 1
    assert not ep._startable(long)
