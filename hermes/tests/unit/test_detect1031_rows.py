"""The 42 rows main 02bb40d0 misses, and the true controls, as fixtures (plan 31.10, WP-0 §2.8).

Every row of tests/fixtures/detect1031/rows/ is replayed from the CheckContext its turn had when the answer check
began (tests/support/ctx_fixture.py) and must keep its measured ``status`` — a row that becomes caught, or stops
being caught, fails here, so no row drifts without notice. The package that catches its row changes that row's
``status`` to "caught" in its branch; the integrator alone changes ``expect`` and ``tier``. A row the plan leaves out
(tier "out") that becomes caught is a finding to review before it may stay.

Every control of tests/fixtures/detect1031/negatives/<pkg>.json is a true sentence on its board: nothing flags it.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import chess
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"
ROWS = sorted((FIX / "rows").glob("*.json"))
CONTROLS = [(p.stem, c) for p in sorted((FIX / "negatives").glob("*.json"))
            for c in json.loads(p.read_text(encoding="utf-8"))["controls"]]
TIERS = {"wp0": "caught", "must": "caught", "target": "caught", "stretch": "stretch", "out": "not_caught"}


def _stockfish() -> bool:
    from src.tools.stockfish import STOCKFISH_PATH

    return bool(shutil.which(STOCKFISH_PATH) or os.path.exists(STOCKFISH_PATH))


def test_the_rows_are_the_42_misses_of_main():
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in ROWS]
    assert len(rows) == 42 and len({r["id"] for r in rows}) == 42
    tiers = {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
        assert r["expect"] == TIERS[r["tier"]], r["id"]
        assert r["owner"] and r["stage"] in ("sync", "engine") and r["status"] in ("caught", "missed")
        assert r["fidelity"], f"{r['id']}: the fixture did not reproduce the replay's issues when it was built"
    # PLAN §3: 1 (WP-0) + 22 must, 2 more for the target, 5 stretch, 12 left out (§8)
    assert tiers == {"wp0": 1, "must": 22, "target": 2, "stretch": 5, "out": 12}


def _engine_stage_on(monkeypatch):
    """tests/conftest.py turns the engine stage off for every test; a row or control of the engine stage runs it as
    the server does (stage 2 integration: these were empty checks before)."""
    from src import config

    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)


@pytest.mark.parametrize("path", ROWS, ids=[p.stem for p in ROWS])
def test_row_keeps_its_status(path, monkeypatch):
    row = json.loads(path.read_text(encoding="utf-8"))
    if row["sentence"] is None:
        pytest.skip("the graded quote is not one sentence of the answer")
    if row["stage"] == "engine" and not _stockfish():
        pytest.skip("the engine stage needs a local Stockfish")
    if row["stage"] == "engine":
        _engine_stage_on(monkeypatch)
    ctx = load_ctx(row["ctx"])
    got = run_answer(row["prefix"] + [row["sentence"]], ctx, engine=row["stage"] == "engine",
                     live_game=row["turn"].get("live_game"))
    sentence, issues, stage = got[-1]
    status = "caught" if issues else "missed"
    assert status == row["status"], (
        f"{row['id']} ({row['owner']}, {row['mechanism']}) is now {status} — {issues or 'shown'}: if this is the "
        f"package's mechanism working, set \"status\" in rows/{path.name}; otherwise it is a regression")
    if row["tier"] == "out":
        assert status == "missed", f"{row['id']} is left out on purpose (PLAN §8) but is now cut: review it"


def _ctx_for(c: dict):
    from src.answer_check import CheckContext

    moves = c["moves"].split() if c.get("moves") else None
    fen = c.get("fen")
    if moves:
        b = chess.Board()
        for m in moves:
            b.push_san(m)
        fen = b.fen()
    student = {"w": chess.WHITE, "b": chess.BLACK}.get(c.get("student") or "")
    lines = list(c.get("lines") or []) + ([" ".join(moves)] if moves else [])
    ctx = CheckContext.from_fens([fen], lines, question=c.get("question") or "", student_color=student)
    if moves and student is not None:
        ctx.game_moves = moves
        first = 0 if student == chess.WHITE else 1
        ctx.game_engine_moves = [m for i, m in enumerate(moves) if i % 2 != first]
    ctx.language = "ru"
    if c.get("tablebase"):
        ctx.tablebase = c["tablebase"]
        ctx.engine_eval = 0.0 if c["tablebase"] == "draw" else (20.0 if c["tablebase"].startswith("White") else -20.0)
    if c.get("engine_eval") is not None:
        ctx.engine_eval = c["engine_eval"]
    return ctx


SENTENCE_CONTROLS = [(pkg, c) for pkg, c in CONTROLS if c.get("kind") != "fact"]


@pytest.mark.parametrize("pkg,control", SENTENCE_CONTROLS, ids=[f"{p}:{c['id']}" for p, c in SENTENCE_CONTROLS])
def test_true_control_is_not_flagged(pkg, control, monkeypatch):
    if control.get("stage") == "engine" and not _stockfish():
        pytest.skip("the engine stage needs a local Stockfish")
    if control.get("stage") == "engine":
        _engine_stage_on(monkeypatch)
    ctx = _ctx_for(control)
    got = run_answer(list(control.get("before") or []) + [control["sentence"]], ctx,
                     engine=control.get("stage") == "engine")
    assert got and got[-1][1] == [], f"{pkg}/{control['id']} ({control.get('detector')}): {got[-1][1]} — {control['why']}"


@pytest.mark.parametrize("control", [c for p, c in CONTROLS if c.get("kind") == "fact"],
                         ids=[c["id"] for p, c in CONTROLS if c.get("kind") == "fact"])
def test_fact_control_is_well_formed(control):
    b = chess.Board(control["fen"])
    assert b.is_valid()
    san = control.get("keep") or control.get("drop")
    if san and san[0] in "KQRBN" or (san and "x" in san):
        b.parse_san(san)
