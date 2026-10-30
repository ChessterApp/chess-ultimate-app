"""The relation judge and resolver on hand-written claims (WP-B, plan 30.10 §4): tests/fixtures/relations/judge_cases.json.

The claims are written by hand in the claim_types JSON, so these tests do not depend on the parser (WP-A). Groups:
  relation       each relation on fixed boards (x-ray aim through one piece and not two, the battery and the wrong-line
                 battery, en passant, absolute and relative pins, locked_by with kings excluded, capture_with, «which»)
  finding        the 29.10 production findings that must come out false (name-winawer … g3-draw)
  resolver       which board a Pos means (named move, «X или Y», a pawn move for both sides, a move told twice, a move
                 already on the board or in the game, a numbered line move, «then», the idea after a null move, …)
  puzzle         answers about the board after an unnamed solution move (plan §1.2) — never false
  prevent_wrong  prevent's five wrong flags (plan §1.3) — never false; prevent_real: its ten real ones — false
  negative       the 48 true claims of the triage answers — never false
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import chess
import pytest

from src import claim_judge, claim_scene
from src.answer_check import CheckContext
from src.answer_check_relations import MAX_ISSUE_CHARS, issue_text
from src.claim_types import Claim

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "relations"
CASES = json.loads((FIX / "judge_cases.json").read_text())["cases"]
TRIAGE = json.loads((FIX / "triage.json").read_text())["answers"]


def build_ctx(spec: dict) -> CheckContext:
    """The context the server builds for a turn (src/server.py): the board, the shown board, the game and the lines,
    the question, the student; the solution lines when the case gives them."""
    base = dict(TRIAGE[spec["answer"]]) if "answer" in spec else {}
    base.update({k: v for k, v in spec.items() if k != "answer"})
    student = {"w": chess.WHITE, "b": chess.BLACK}.get(base.get("student"))
    game_moves = base.get("game_moves")
    lines = list(base.get("lines") or []) + ([" ".join(game_moves)] if game_moves else [])
    ctx = CheckContext.from_fens([base.get("fen") or chess.STARTING_FEN, base.get("shown")], lines=lines,
                                 question=base.get("question") or "", student_color=student)
    if game_moves is not None:
        ctx.game_moves = list(game_moves) or None
    if base.get("solution_lines"):
        ctx.solution_lines = [list(x) for x in base["solution_lines"]]
    if base.get("puzzle_solution"):
        ctx.puzzle_solution = list(base["puzzle_solution"])
    return ctx


def run_case(case: dict):
    ctx = build_ctx(case["ctx"])
    state: dict = {}
    if case.get("state_from"):
        before = Claim.from_dict(case["state_from"])
        claim_scene.remember("", [before], ctx, state)
    claim = Claim.from_dict(case["claim"])
    boards = claim_scene.boards_for(claim, ctx, state)
    if boards is None:
        return None, None
    return boards, claim_judge.decide(claim, boards, ctx)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_judge_case(case):
    boards, verdict = run_case(case)
    expect = case["expect"]
    if expect == "none":
        assert boards is None, f"expected no board, got {boards and boards.where}: {verdict}"
        return
    if expect == "not_false":  # true, undecided, or no board at all: never reported
        assert verdict is None or verdict.status != "false", verdict
        return
    assert boards is not None, "no board was built"
    assert verdict.status == expect, verdict
    if case.get("where"):
        assert case["where"] in verdict.where, verdict.where
    if case.get("truth"):
        assert case["truth"] in verdict.truth, verdict.truth


def test_groups_are_all_present():
    groups = {c["group"] for c in CASES}
    assert {"relation", "finding", "resolver", "puzzle", "prevent_wrong", "prevent_real", "negative"} <= groups
    assert sum(c["group"] == "negative" for c in CASES) >= 48
    assert sum(c["group"] == "prevent_real" for c in CASES) == 10
    assert sum(c["group"] == "prevent_wrong" for c in CASES) == 5


def test_issue_lines_are_short_and_say_the_board():
    """Every false verdict makes one issue line of at most 220 characters, the board first, truth after it."""
    for case in CASES:
        _boards, verdict = run_case(case)
        if verdict is None or verdict.status != "false":
            continue
        line = issue_text(Claim.from_dict(case["claim"]), verdict)
        assert len(line) <= MAX_ISSUE_CHARS, line
        assert verdict.where and line.startswith(verdict.where), line
        assert verdict.truth, case["id"]


def test_rule_relations_go_to_the_rule_judges(monkeypatch):
    """The board-rule relations are WP-D's: decide dispatches them to claim_rules.RULE_JUDGES, under the same rule."""
    from src import claim_rules
    from src.claim_types import Verdict

    claim = Claim.from_dict({"rel": "occupied", "subj": None, "objs": [{"sq": "e5", "piece": "P"}]})
    ctx = CheckContext.from_fens(["rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"])
    boards = claim_scene.boards_for(claim, ctx, {})
    monkeypatch.setattr(claim_rules, "RULE_JUDGES", {})
    assert claim_judge.decide(claim, boards, ctx).status == "undecided"
    monkeypatch.setattr(claim_rules, "RULE_JUDGES", {"occupied": lambda c, b, x: Verdict("false", "", "e5 is empty")})
    v = claim_judge.decide(claim, boards, ctx)
    assert v.status == "false" and v.truth == "e5 is empty"

    def broken(c, b, x):
        raise RuntimeError("boom")

    monkeypatch.setattr(claim_rules, "RULE_JUDGES", {"occupied": broken})
    assert claim_judge.decide(claim, boards, ctx).status == "undecided"


def test_decide_latency():
    """decide p99 ≤ 0.3 ms per claim; boards_for with from-square alternatives p99 ≤ 1 ms (plan §4 WP-B)."""
    prepared = []
    for case in CASES:
        ctx = build_ctx(case["ctx"])
        claim = Claim.from_dict(case["claim"])
        boards = claim_scene.boards_for(claim, ctx, {})
        if boards is not None:
            prepared.append((claim, boards, ctx))
    for claim, boards, ctx in prepared:  # warm
        claim_judge.decide(claim, boards, ctx)
    times = []
    for _ in range(5):
        for claim, boards, ctx in prepared:
            t = time.perf_counter()
            claim_judge.decide(claim, boards, ctx)
            times.append((time.perf_counter() - t) * 1000)
    times.sort()
    p99 = times[int(0.99 * (len(times) - 1))]
    assert p99 <= 0.3 * 3, f"decide p99 {p99:.3f} ms"  # 3× head-room for a loaded test machine; the harness gates 0.3

    from_sq = []
    for case in CASES:
        claim = Claim.from_dict(case["claim"])
        if claim.subj is not None and claim.subj.from_sq and not claim.pos.moves:
            ctx = build_ctx(case["ctx"])
            claim_scene.boards_for(claim, ctx, {})
            ctx = build_ctx(case["ctx"])  # a fresh context: no memo
            t = time.perf_counter()
            claim_scene.boards_for(claim, ctx, {})
            from_sq.append((time.perf_counter() - t) * 1000)
    assert from_sq
    assert max(from_sq) <= 1.0 * 3, f"boards_for from-square max {max(from_sq):.3f} ms"
