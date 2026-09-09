"""Task D — runner aggregation + baseline comparison.

The aggregation and gate logic are pure functions over verdict dicts, so most of
this runs with no engine. One tiny end-to-end runner pass exercises the wiring
against the local Stockfish binary.
"""

import json
import os

import pytest

from src.eval import report as report_mod
from src.eval.runner import run
from src.tools.stockfish import STOCKFISH_PATH

_HAVE_SF = os.path.exists(STOCKFISH_PATH)


def _verdict(score, illegal=0, moves=1, status="ok"):
    """Build a synthetic verdict dict with `illegal` illegal-move claims."""
    claims = []
    for _ in range(illegal):
        claims.append({"text": "x", "kind": "illegal_move", "verdict": "illegal",
                       "score": 0.0, "detail": {}})
    for _ in range(moves - illegal):
        claims.append({"text": "y", "kind": "recommended_move", "verdict": "best",
                       "score": 1.0, "detail": {}})
    return {"status": status, "correctness_score": score,
            "illegal_move_rate": round(illegal / moves, 4) if moves else 0.0,
            "claims": claims, "notes": []}


@pytest.mark.unit
class TestAggregate:
    def test_mean_and_illegal_rate(self):
        results = [
            {"id": "a", "verdict": _verdict(1.0, illegal=0, moves=1)},
            {"id": "b", "verdict": _verdict(0.0, illegal=1, moves=1)},
            {"id": "c", "verdict": _verdict(0.5, illegal=0, moves=2)},
        ]
        agg = report_mod.aggregate(results)
        assert agg["n_cases"] == 3
        assert agg["n_scored"] == 3
        assert agg["mean_correctness"] == pytest.approx(0.5, abs=1e-4)
        # 1 illegal claim across 4 move claims.
        assert agg["illegal_move_rate"] == pytest.approx(0.25, abs=1e-4)

    def test_skipped_and_none_excluded_from_mean(self):
        results = [
            {"id": "a", "verdict": _verdict(1.0)},
            {"id": "b", "verdict": _verdict(None, moves=0, status="skipped")},
        ]
        agg = report_mod.aggregate(results)
        assert agg["n_scored"] == 1
        assert agg["n_skipped"] == 1
        assert agg["mean_correctness"] == 1.0

    def test_worst_cases_sorted_ascending(self):
        results = [
            {"id": "hi", "verdict": _verdict(0.9)},
            {"id": "lo", "verdict": _verdict(0.1)},
            {"id": "mid", "verdict": _verdict(0.5)},
        ]
        agg = report_mod.aggregate(results)
        assert agg["worst_cases"][0]["id"] == "lo"


@pytest.mark.unit
class TestBaselineComparison:
    def test_pass_within_tolerance(self):
        agg = {"mean_correctness": 0.84, "illegal_move_rate": 0.05}
        baseline = {"mean_correctness": 0.86, "illegal_move_rate": 0.05, "tolerance": 0.02}
        cmp = report_mod.compare_baseline(agg, baseline)
        assert cmp["passed"] is True

    def test_fail_on_correctness_regression(self):
        agg = {"mean_correctness": 0.80, "illegal_move_rate": 0.05}
        baseline = {"mean_correctness": 0.86, "illegal_move_rate": 0.05, "tolerance": 0.02}
        cmp = report_mod.compare_baseline(agg, baseline)
        assert cmp["passed"] is False
        assert "mean_correctness" in cmp["reason"]

    def test_fail_on_illegal_rate_rise(self):
        agg = {"mean_correctness": 0.86, "illegal_move_rate": 0.20}
        baseline = {"mean_correctness": 0.86, "illegal_move_rate": 0.05, "tolerance": 0.02}
        cmp = report_mod.compare_baseline(agg, baseline)
        assert cmp["passed"] is False
        assert "illegal_move_rate" in cmp["reason"]

    def test_no_baseline_is_non_gating_pass(self):
        cmp = report_mod.compare_baseline({"mean_correctness": 0.5}, None)
        assert cmp["passed"] is True
        assert cmp["reason"] == "no_baseline"


@pytest.mark.unit
def test_format_summary_smoke():
    agg = report_mod.aggregate([{"id": "a", "verdict": _verdict(1.0)}])
    cmp = report_mod.compare_baseline(agg, None)
    text = report_mod.format_summary(agg, cmp, "ds.jsonl", 12)
    assert "mean_correctness" in text
    assert "gate:" in text


@pytest.mark.integration
@pytest.mark.skipif(not _HAVE_SF, reason="Stockfish binary not present")
def test_runner_end_to_end(tmp_path):
    dataset = tmp_path / "mini.jsonl"
    cases = [
        {"id": "best", "fen": "4k3/8/8/8/3q4/8/3Q4/4K3 w - - 0 1",
         "assistant_text": "You should play Qxd4, winning the queen."},
        {"id": "illegal", "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
         "assistant_text": "You should play Nf6 immediately."},
    ]
    dataset.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")

    report = run(dataset_path=str(dataset), baseline_path=None, depth=8)
    assert report["metrics"]["n_cases"] == 2
    assert report["metrics"]["illegal_move_rate"] > 0
    assert report["comparison"]["passed"] is True  # no baseline → non-gating
    assert "summary" in report
