"""06.11-2 review of a30a51d6 / eb16995c: one engine budget per held sentence in the line verdict, and the voice check
bounded by what the site waits for.

1. src/line_verdict._eval set a fresh VERIFY_MAX_MS deadline for every search. Once a check's search was no longer cut
   at STOCKFISH_MAX_MS (a30a51d6), a line claim (up to three searches) held a sentence ~18 s on a slow host, a swing
   claim ~12 s, and verify_claims looped over every claim of the sentence. Now verify_claims sets one deadline and every
   search of every claim shares it; a search it cannot complete says nothing (the sentence stands).
2. /api/coach/voice/check: the site aborts after CHECK_TIMEOUT_MS (4 s) and reads that as «no issues», but the engine
   part ran in a thread nobody cancels, at check priority (never preempted), for up to 6–10 s per stage. Now the whole
   engine part ends within COACH_VOICE_CHECK_BUDGET_MS of the request's arrival.
"""

import os
import stat
import sys
import time

import chess
import pytest
from fastapi.testclient import TestClient

from src import config, engine_pool, hypothetical, line_verdict, server
from src.tools import stockfish

FAKE = os.path.join(os.path.dirname(__file__), "..", "support", "fake_uci.py")


@pytest.fixture
def pool2(tmp_path, monkeypatch):
    exe = tmp_path / "fake-stockfish"
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {os.path.abspath(FAKE)} \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_UCI_MODE", "normal")
    monkeypatch.setenv("FAKE_UCI_PLY_MS", "40")                       # depth 16 ≈ 0.65 s
    pool = engine_pool.EnginePool(str(exe), size=2, hash_mb=16)
    pool.start()
    old = engine_pool._set_pool_for_tests(pool)
    monkeypatch.setattr(config, "STOCKFISH_POOL", True)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()
    yield pool
    engine_pool._set_pool_for_tests(old)
    pool.close()
    stockfish.clear_analysis_cache()
    stockfish.clear_exact_store()


def _mv(*ucis):
    return [chess.Move.from_uci(u) for u in ucis]


def _swing(moves, pawns=3.0):
    return {"kind": "swing", "board": chess.Board(), "moves": _mv(*moves), "side": chess.WHITE, "pawns": pawns,
            "words": "на три пешки лучше"}


# ── 1. one budget per held sentence: the line verdict ─────────────────────────────────────────────────────────────
def test_two_swing_claims_hold_the_sentence_no_longer_than_its_budget(pool2, monkeypatch):
    """Four depth-16 searches (two claims × before/after) at ≈ 0.65 s each, budget 1 s: held 1.4+ s before."""
    monkeypatch.setattr(hypothetical, "VERIFY_MAX_MS", 1000)
    t = time.monotonic()
    with engine_pool.priority(engine_pool.PRIORITY_CHECK):
        line_verdict.verify_claims([_swing(("e2e4", "e7e5")), _swing(("d2d4", "d7d5"))], 300)
    assert time.monotonic() - t <= 1.0 + 0.3


def test_a_swing_the_budget_covers_is_still_judged(pool2):
    """The default budget (6 s) covers both searches here: the claim is judged (fake engine: +0.1 before and after,
    «на три пешки лучше» is wrong)."""
    with engine_pool.priority(engine_pool.PRIORITY_CHECK):
        why = line_verdict.verify_claims([_swing(("e2e4", "e7e5"))], 300)
    assert why and "is wrong" in why


def _recording_look(monkeypatch, answers):
    seen = []

    def look(fen, movetime_ms, deadline):
        seen.append(deadline)
        return answers[len(seen) - 1] if len(seen) <= len(answers) else None

    monkeypatch.setattr(hypothetical, "_look", look)
    return seen


def test_a_three_search_line_claim_shares_one_deadline(monkeypatch):
    """«после e4 e5 Nf3 Nc6 белые лучше»: the end is −1.0 for White (worse, not clearly), so the verdict looks for the
    side's mistake — the position before Nf3 (+1.0) and after it (−1.0): three searches, one deadline."""
    seen = _recording_look(monkeypatch, [
        {"score": -1.0, "pv": "", "depth": 16},        # the line's end, White to move
        {"score": 1.0, "pv": "d2d4", "depth": 16},     # before Nf3 (the engine prefers d4)
        {"score": 1.0, "pv": "", "depth": 16},         # after Nf3, Black to move: −1.0 for White
    ])
    claim = {"kind": "outcome", "board": chess.Board(), "moves": _mv("e2e4", "e7e5", "g1f3", "b8c6"),
             "side": chess.WHITE, "words": "белые лучше"}
    t = time.monotonic()
    why = line_verdict.verify_claims([claim], 300)
    assert len(seen) == 3 and len(set(seen)) == 1
    assert seen[0] <= t + hypothetical.VERIFY_MAX_MS / 1000.0 + 0.05
    assert why and "mistake" in why                                  # the verdict itself is unchanged


def test_every_claim_of_the_sentence_shares_the_deadline(monkeypatch):
    seen = _recording_look(monkeypatch, [{"score": 0.1, "pv": "", "depth": 16}] * 4)
    line_verdict.verify_claims([_swing(("e2e4", "e7e5"), 0.0), _swing(("d2d4", "d7d5"), 0.0)], 300)
    assert len(seen) == 4 and len(set(seen)) == 1


def test_a_callers_tighter_deadline_bounds_the_claims(monkeypatch):
    seen = _recording_look(monkeypatch, [{"score": 0.1, "pv": "", "depth": 16}] * 2)
    until = time.monotonic() + 0.5
    line_verdict.verify_claims([_swing(("e2e4", "e7e5"), 0.0)], 300, deadline=until)
    assert seen == [until, until]


def test_a_spent_budget_starts_no_timed_look_for_a_piece_claim(monkeypatch):
    calls = []
    monkeypatch.setattr(hypothetical, "analyze_timed", lambda *a, **k: calls.append(a) or {"lines": []})
    claim = {"kind": "piece_decides", "board": chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1"), "side": chess.WHITE,
             "squares": [chess.D1], "piece": chess.QUEEN, "words": "решает ферзь"}
    assert line_verdict.verify_claims([claim], 300, deadline=time.monotonic() - 0.01) is None
    assert calls == []


# ── 2. the voice check ends when the site stops listening ─────────────────────────────────────────────────────────
NAJDORF_W = "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"
ONLY_F3 = "1k2b1r1/8/8/8/8/8/5P1P/7K b - - 0 1"


@pytest.fixture
def voice(monkeypatch):
    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
    monkeypatch.setattr(config, "COACH_LINE_VERDICT", True)
    monkeypatch.setattr("src.board_rules.tablebase", lambda board: None)

    async def _no_limit(*a, **k):
        return None

    monkeypatch.setattr(server, "enforce_rate_limit", _no_limit)
    seen = {}

    def _move(board, move, san, *a, deadline=None, **k):
        seen["move"] = deadline
        return None

    def _forced(claim, *a, until=None, **k):
        seen["forced"] = until
        return None

    def _line(claims, *a, deadline=None, **k):
        seen["line"] = deadline
        return None

    monkeypatch.setattr("src.hypothetical.verify_recommendation", _move)
    monkeypatch.setattr("src.hypothetical.verify_forced_reply", _forced)
    monkeypatch.setattr("src.line_verdict.verify_claims", _line)

    def check(text, fen):
        t = time.monotonic()
        resp = TestClient(server.app).post("/api/coach/voice/check", headers={"X-User-Id": "verify-1106-2"},
                                           json={"text": text, "fen": fen, "question": "Что мне делать?",
                                                 "engine": True})
        assert resp.status_code == 200
        return t, time.monotonic()

    return seen, check


def _within_the_sites_wait(got, t0, t1):
    budget = config.COACH_VOICE_CHECK_BUDGET_MS / 1000.0
    return got is not None and t0 + budget - 0.05 <= got <= t1 + budget


def test_the_voice_checks_recommendation_ends_when_the_site_stops_listening(voice):
    seen, check = voice
    t0, t1 = check("Сыграй ферзём на жэ четыре.", NAJDORF_W)
    assert _within_the_sites_wait(seen.get("move"), t0, t1)


def test_the_voice_checks_line_verdict_ends_when_the_site_stops_listening(voice):
    seen, check = voice
    t0, t1 = check("После Nf5 g6 Nh6 белые выигрывают фигуру.", NAJDORF_W)
    assert _within_the_sites_wait(seen.get("line"), t0, t1)


def test_the_voice_checks_forced_reply_ends_when_the_site_stops_listening(voice):
    seen, check = voice
    t0, t1 = check("После Bc6+ белые обязаны ответить f3.", ONLY_F3)
    assert _within_the_sites_wait(seen.get("forced"), t0, t1)


def test_the_voice_budget_answers_before_the_site_gives_up():
    route = os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "src", "app", "api", "coach",
                         "voice", "check", "route.ts")
    if not os.path.exists(route):
        pytest.skip("the site's route is not beside this Hermes")
    import re

    site_ms = int(re.search(r"CHECK_TIMEOUT_MS = (\d+)", open(route, encoding="utf-8").read()).group(1))
    assert config.COACH_VOICE_CHECK_BUDGET_MS <= site_ms - 300


def test_a_voice_line_verdict_with_the_budget_spent_waits_for_no_search(pool2, monkeypatch):
    """The real verify_claims on the fake engine with the voice deadline already past: no search is waited for."""
    t = time.monotonic()
    with engine_pool.priority(engine_pool.PRIORITY_CHECK):
        assert line_verdict.verify_claims([_swing(("e2e4", "e7e5"))], 300, reveal=False,
                                          deadline=time.monotonic() - 0.01) is None
    assert time.monotonic() - t < 0.3
