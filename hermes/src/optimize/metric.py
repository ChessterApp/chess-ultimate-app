"""O3 — the optimization metric.

Thin wrapper over the Phase 0 engine-grounded auto-eval
(:func:`src.eval.engine_grounded.evaluate_turn`). Given a freshly-generated coach
reply and a case (``fen`` / ``user_text`` / ``message_type``), returns a scalar:

  * an illegal move presented as a move → ``0.0`` (the hallucination hard fail);
  * otherwise the case's correctness score in ``[0, 1]`` (``0.0`` when the reply
    made no engine-verifiable claim, so an evasive non-answer earns nothing).

Dataset-level aggregation reuses :mod:`src.eval.report` so ``mean_correctness``
and ``illegal_move_rate`` are computed exactly as the Phase 0 baseline runner
computes them — the optimizer's numbers are directly comparable to the gate.
"""

from src.eval import report as report_mod
from src.eval.engine_grounded import DEFAULT_DEPTH, evaluate_turn


def evaluate_reply(reply: str, case: dict, depth: int = DEFAULT_DEPTH) -> dict:
    """Score one reply against the engine; return the verdict dict."""
    verdict = evaluate_turn(
        fen=case["fen"],
        assistant_text=reply or "",
        user_text=case.get("user_text", ""),
        depth=depth,
    )
    return verdict.to_dict()


def score_from_verdict(verdict: dict) -> float:
    """Map a verdict dict to the scalar reward.

    ``illegal move → 0.0``; otherwise the correctness score (``0.0`` when there
    is nothing verifiable to score, so an evasive non-answer can't inflate a
    candidate). A skipped verdict (missing engine / invalid FEN) also scores
    ``0.0``.
    """
    if verdict.get("illegal_move_rate", 0.0):
        return 0.0
    score = verdict.get("correctness_score")
    return float(score) if score is not None else 0.0


def score_reply(reply: str, case: dict, depth: int = DEFAULT_DEPTH) -> float:
    """Scalar reward for a single generated reply. Never raises."""
    return score_from_verdict(evaluate_reply(reply, case, depth=depth))


def dataset_metrics(verdicts: list[dict]) -> dict:
    """Aggregate a list of verdict dicts into dataset-level metrics.

    Delegates to :func:`src.eval.report.aggregate` so ``mean_correctness`` and
    ``illegal_move_rate`` match ``runner.py``'s definitions exactly.
    """
    agg = report_mod.aggregate([{"verdict": v} for v in verdicts])
    return {
        "mean_correctness": agg["mean_correctness"],
        "illegal_move_rate": agg["illegal_move_rate"],
        "n_cases": agg["n_cases"],
        "n_scored": agg["n_scored"],
        "n_skipped": agg["n_skipped"],
    }
