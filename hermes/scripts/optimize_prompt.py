#!/usr/bin/env python3
"""O4 CLI — offline SOUL.md prompt optimizer (CL Phase 1, Slice 3).

Proposes improved coach-persona variants, scores them with the Phase 0
engine-grounded metric, and writes candidate diffs + eval reports for HUMAN
review under ``eval/prompt_opt/runs/<run_id>/``. It NEVER edits SOUL.md, never
touches the serving path, and never deploys.

Usage:
    # Dry run (default): print the plan and exit 0 — ZERO network / LLM calls.
    python3 scripts/optimize_prompt.py

    # Real run (paid): the human triggers this deliberately.
    python3 scripts/optimize_prompt.py --execute --max-llm-calls 250

Fails soft: missing ``OPENROUTER_API_KEY`` on ``--execute`` prints a clear
message and exits 2 (no traceback).
"""

import argparse
import os
import sys

# Make ``src`` importable when run as a script from anywhere.
_HERMES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERMES_DIR)

from src.eval.engine_grounded import DEFAULT_DEPTH  # noqa: E402
from src.optimize.dataset import (  # noqa: E402
    DEFAULT_SEED,
    DEFAULT_TRAIN_FRAC,
    load_dataset,
    split_dataset,
    split_summary,
)
from src.optimize.generate import DEFAULT_MAX_LLM_CALLS, estimate_cost  # noqa: E402
from src.optimize.optimize import (  # noqa: E402
    DEFAULT_ROUNDS,
    DEFAULT_VARIANTS_PER_ROUND,
    optimize,
    rerank,
)

_DEFAULT_DATASET = os.path.join(_HERMES_DIR, "eval", "datasets", "golden_v1.jsonl")
_DEFAULT_SOUL = os.path.join(_HERMES_DIR, "profiles", "chess-coach", "SOUL.md")
_DEFAULT_RUNS_DIR = os.path.join(_HERMES_DIR, "eval", "prompt_opt", "runs")
_DEFAULT_CACHE_DIR = os.path.join(_HERMES_DIR, "eval", "prompt_opt", "cache")


def _main_model() -> str:
    """The coach's configured main-tier model (already an OpenRouter id)."""
    try:
        from src.config import get_model_config

        return get_model_config().get("default") or "google/gemini-2.5-flash"
    except Exception:
        return "google/gemini-2.5-flash"


def _critic_model() -> str:
    """The cheap tier used for proposing edits (same choice as memory_writer)."""
    try:
        from src.config import get_model_config

        tiers = get_model_config().get("tiers", {}) or {}
        return tiers.get("fast") or tiers.get("default") or "google/gemini-2.5-flash"
    except Exception:
        return "google/gemini-2.5-flash"


def _default_run_id() -> str:
    from datetime import datetime, timezone

    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline SOUL.md prompt optimizer (Phase 1 Slice 3).")
    p.add_argument("--dataset", default=_DEFAULT_DATASET)
    p.add_argument("--soul", default=_DEFAULT_SOUL, help="Current SOUL.md (read-only baseline).")
    p.add_argument("--runs-dir", default=_DEFAULT_RUNS_DIR)
    p.add_argument("--cache-dir", default=_DEFAULT_CACHE_DIR)
    p.add_argument("--run-id", default=None)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--train-frac", type=float, default=DEFAULT_TRAIN_FRAC)
    p.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    p.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    p.add_argument("--variants-per-round", type=int, default=DEFAULT_VARIANTS_PER_ROUND)
    p.add_argument("--model", default=None, help="Generation model (default: coach main tier).")
    p.add_argument("--critic-model", default=None, help="Critic model (default: cheap tier).")
    p.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    p.add_argument("--execute", action="store_true",
                   help="Actually run (paid). Without it, print the plan and exit 0.")
    p.add_argument("--rerank", metavar="RUN_DIR", default=None,
                   help="Free: re-judge an existing run's candidates under the current "
                        "selection metric (no LLM calls) and exit.")
    return p


def _print_plan(args, model, critic_model, split_info) -> None:
    print("Prompt-optimization plan (DRY RUN — no LLM calls made)")
    print(f"  dataset:        {args.dataset}")
    print(f"  soul (current): {args.soul}")
    print(f"  seed:           {args.seed}   train_frac: {args.train_frac}")
    print(f"  split:          {split_info['n_train']} train / {split_info['n_holdout']} holdout")
    print(f"    train  by stratum: {split_info['train_by_stratum']}")
    print(f"    holdout by stratum: {split_info['holdout_by_stratum']}")
    print(f"  model (generate): {model}")
    print(f"  critic model:     {critic_model}")
    print(f"  rounds × variants: {args.rounds} × {args.variants_per_round}")
    print(f"  depth:            {args.depth}")
    print(f"  max-llm-calls:    {args.max_llm_calls}")
    print(f"  est. worst-case cost: ~${estimate_cost(args.max_llm_calls, model)} "
          "(rough; cache hits and early convergence cost less)")
    print(f"  runs dir:  {args.runs_dir}")
    print(f"  cache dir: {args.cache_dir}")
    print("\nNo SOUL.md is ever modified. Re-run with --execute to start a paid run.")


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    if args.rerank:
        result = rerank(args.rerank)
        print(f"Re-ranked {result['reranked_from']} — {result['verdict']}")
        print(f"  artifacts: {args.rerank}/rerank.md, rerank.json")
        return 0

    model = args.model or _main_model()
    critic_model = args.critic_model or _critic_model()

    if not os.path.exists(args.dataset):
        print(f"error: dataset not found: {args.dataset}", file=sys.stderr)
        return 2
    if not os.path.exists(args.soul):
        print(f"error: SOUL.md not found: {args.soul}", file=sys.stderr)
        return 2

    # Splitting is pure/offline — safe to compute for both the plan and the run.
    cases = load_dataset(args.dataset)
    train, holdout = split_dataset(cases, seed=args.seed, train_frac=args.train_frac)
    split_info = split_summary(train, holdout)

    if not args.execute:
        _print_plan(args, model, critic_model, split_info)
        return 0

    # ── Execute path (paid) ──────────────────────────────────────────────
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("error: OPENROUTER_API_KEY is not set — cannot run a live optimization.\n"
              "       Set it and re-run with --execute, or drop --execute for a dry run.",
              file=sys.stderr)
        return 2

    run_id = args.run_id or _default_run_id()
    report = optimize(
        dataset_path=args.dataset,
        out_dir=args.runs_dir,
        run_id=run_id,
        current_soul_path=args.soul,
        cache_dir=args.cache_dir,
        model=model,
        critic_model=critic_model,
        seed=args.seed,
        train_frac=args.train_frac,
        max_llm_calls=args.max_llm_calls,
        rounds=args.rounds,
        variants_per_round=args.variants_per_round,
        depth=args.depth,
    )

    out = os.path.join(args.runs_dir, run_id)
    status = "PARTIAL (budget exhausted)" if report["partial"] else "complete"
    print(f"Run {run_id} {status}.")
    print(f"  live LLM calls used: {report['budget']['used']}/{report['budget']['max_llm_calls']}")
    print(f"  candidates: {len(report['candidates'])}   winner: {report['winner']}")
    print(f"  artifacts: {out}/  (report.md, report.json, candidate_*.soul.md, candidate_*.diff)")
    print("SOUL.md was NOT modified. Applying a winner is a separate human commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
