#!/usr/bin/env python3
"""Task E — CI regression gate.

Runs the engine-grounded eval (Task D) against the frozen golden set using the
committed ``assistant_text`` (no live model, no Supabase) and fails the build if
aggregate engine-correctness regresses below ``baseline - tolerance`` or the
illegal-move rate rises above ``baseline + tolerance``.

This guards two things at once:
  * the scoring + engine plumbing stays green (a broken Stockfish wire-up or a
    scoring regression fails CI), and
  * any prompt-source change (SOUL.md / config.yaml / prompt_builder.py) is
    accompanied by a deliberate re-baseline rather than a silent score drop.

Exit code 0 = pass, 1 = regression, 2 = harness error.
"""

import argparse
import json
import os
import sys

# Make ``src`` importable when run as a script from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.eval.engine_grounded import DEFAULT_DEPTH  # noqa: E402
from src.eval.runner import run  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CI engine-correctness regression gate (Task E).")
    parser.add_argument("--dataset", default="eval/datasets/golden_v1.jsonl")
    parser.add_argument("--baseline", default="eval/baselines/golden_v1.baseline.json")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--out", default="eval_report.json")
    args = parser.parse_args(argv)

    if not os.path.exists(args.dataset):
        print(f"::error::golden dataset missing: {args.dataset}")
        return 2
    if not os.path.exists(args.baseline):
        print(f"::error::baseline missing: {args.baseline}")
        return 2

    try:
        report = run(
            dataset_path=args.dataset,
            baseline_path=args.baseline,
            depth=args.depth,
            tolerance=args.tolerance,
        )
    except Exception as exc:  # pragma: no cover - defensive harness guard
        print(f"::error::eval harness crashed: {exc}")
        return 2

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(report["summary"])
    comparison = report["comparison"]
    if not comparison.get("passed"):
        print(f"::error::engine-correctness regression: {comparison.get('reason')}")
        return 1

    print("Engine-correctness gate PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
