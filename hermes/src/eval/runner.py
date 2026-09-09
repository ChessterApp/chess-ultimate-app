"""Task D — eval runner.

Runs every golden case through the engine-grounded auto-eval (Task B),
aggregates to dataset-level metrics, compares to a stored baseline, and emits
``eval_report.json`` plus a short human summary.

The runner re-scores the *committed* ``assistant_text`` against the engine — it
does NOT call a live model or Supabase — so it runs offline given only Stockfish.

Usage:
    python -m src.eval.runner --dataset eval/datasets/golden_v1.jsonl
    python -m src.eval.runner --dataset eval/datasets/golden_v1.jsonl \
        --baseline eval/baselines/golden_v1.baseline.json --out eval_report.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from src.eval import report as report_mod
from src.eval.engine_grounded import DEFAULT_DEPTH, evaluate_turn


def load_jsonl(path: str) -> list[dict]:
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def load_baseline(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def pedagogy_judge_stub(case: dict) -> dict:
    """Secondary (B) channel — pedagogy LLM-judge STUB. Off by default.

    Phase 0 does NOT turn pedagogy into a reward or a gate. This stub only emits
    a placeholder record so the plumbing exists; it never influences the pass/
    fail decision. A real pairwise LLM-judge is validated against a human gold
    set in a later phase.
    """
    return {"id": case.get("id"), "pedagogy_score": None, "note": "stub_not_scored"}


def run(
    dataset_path: str,
    baseline_path: Optional[str] = None,
    depth: int = DEFAULT_DEPTH,
    tolerance: float = report_mod.DEFAULT_TOLERANCE,
    pedagogy: bool = False,
) -> dict:
    cases = load_jsonl(dataset_path)
    results = []
    for case in cases:
        verdict = evaluate_turn(
            fen=case["fen"],
            assistant_text=case["assistant_text"],
            user_text=case.get("user_text", ""),
            depth=depth,
        )
        results.append({"id": case.get("id"), "verdict": verdict.to_dict()})

    agg = report_mod.aggregate(results)
    baseline = load_baseline(baseline_path)
    comparison = report_mod.compare_baseline(agg, baseline, tolerance)

    report = {
        "dataset": dataset_path,
        "depth": depth,
        "metrics": {
            "mean_correctness": agg["mean_correctness"],
            "illegal_move_rate": agg["illegal_move_rate"],
            "n_cases": agg["n_cases"],
            "n_scored": agg["n_scored"],
            "n_skipped": agg["n_skipped"],
        },
        "comparison": comparison,
        "worst_cases": agg["worst_cases"],
        "per_case": agg["per_case"],
    }

    if pedagogy:
        report["pedagogy"] = [pedagogy_judge_stub(c) for c in cases]

    report["summary"] = report_mod.format_summary(agg, comparison, dataset_path, depth)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Engine-grounded eval runner (Phase 0).")
    parser.add_argument("--dataset", required=True, help="Path to golden .jsonl")
    parser.add_argument("--baseline", default="eval/baselines/golden_v1.baseline.json")
    parser.add_argument("--out", default="eval_report.json")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--tolerance", type=float, default=report_mod.DEFAULT_TOLERANCE)
    parser.add_argument(
        "--pedagogy", action="store_true",
        help="Emit the pedagogy LLM-judge STUB (logged only, never gates).",
    )
    args = parser.parse_args(argv)

    report = run(
        dataset_path=args.dataset,
        baseline_path=args.baseline,
        depth=args.depth,
        tolerance=args.tolerance,
        pedagogy=args.pedagogy,
    )

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report["summary"])
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
