"""Task D — scoring aggregation, baseline comparison, and human summary.

Pure functions over a list of per-case verdict dicts (the shape produced by
``EngineVerdict.to_dict()``). No engine, no I/O — so the aggregation and the
pass/fail gate logic are unit-testable offline without Stockfish.
"""

from typing import Optional

DEFAULT_TOLERANCE = 0.02

_MOVE_KINDS = {"recommended_move", "move_reference", "illegal_move"}


def _case_move_counts(verdict: dict) -> tuple[int, int]:
    """(#illegal move claims, #move claims) for one verdict."""
    illegal = move = 0
    for c in verdict.get("claims", []):
        if c["kind"] in _MOVE_KINDS:
            move += 1
            if c["kind"] == "illegal_move":
                illegal += 1
    return illegal, move


def aggregate(results: list[dict]) -> dict:
    """Aggregate per-case verdicts into dataset-level metrics.

    ``results`` is a list of ``{id, verdict}`` (or bare verdict dicts). Cases
    with no scorable claims (``correctness_score is None``) or ``status ==
    "skipped"`` are excluded from the mean but still counted.
    """
    scored: list[float] = []
    total_illegal = total_moves = 0
    skipped = 0
    per_case = []

    for item in results:
        verdict = item.get("verdict", item)
        cid = item.get("id")
        cs = verdict.get("correctness_score")
        illegal, moves = _case_move_counts(verdict)
        total_illegal += illegal
        total_moves += moves
        if verdict.get("status") == "skipped":
            skipped += 1
        if cs is not None:
            scored.append(cs)
        per_case.append({
            "id": cid,
            "correctness_score": cs,
            "illegal_move_rate": verdict.get("illegal_move_rate", 0.0),
            "status": verdict.get("status"),
        })

    mean_correctness = round(sum(scored) / len(scored), 4) if scored else None
    illegal_rate = round(total_illegal / total_moves, 4) if total_moves else 0.0

    worst = sorted(
        (p for p in per_case if p["correctness_score"] is not None),
        key=lambda p: p["correctness_score"],
    )[:5]

    return {
        "n_cases": len(results),
        "n_scored": len(scored),
        "n_skipped": skipped,
        "mean_correctness": mean_correctness,
        "illegal_move_rate": illegal_rate,
        "worst_cases": worst,
        "per_case": per_case,
    }


def compare_baseline(
    agg: dict, baseline: Optional[dict], tolerance: float = DEFAULT_TOLERANCE
) -> dict:
    """Compare aggregate metrics to a stored baseline.

    Pass iff ``mean_correctness >= baseline.mean_correctness - tolerance`` AND
    illegal-move rate does not rise above the baseline (plus the same slack).
    Returns a dict with ``passed`` and per-metric deltas. With no baseline the
    result is a non-gating pass (nothing to regress against yet).
    """
    if not baseline:
        return {"passed": True, "reason": "no_baseline", "deltas": {}}

    tol = baseline.get("tolerance", tolerance)
    base_corr = baseline.get("mean_correctness")
    base_illegal = baseline.get("illegal_move_rate", 0.0)
    cur_corr = agg.get("mean_correctness")

    deltas = {}
    passed = True
    reasons = []

    if base_corr is not None and cur_corr is not None:
        d = round(cur_corr - base_corr, 4)
        deltas["mean_correctness"] = d
        if cur_corr < base_corr - tol:
            passed = False
            reasons.append(
                f"mean_correctness {cur_corr} < baseline {base_corr} - tol {tol}"
            )

    d_ill = round(agg.get("illegal_move_rate", 0.0) - base_illegal, 4)
    deltas["illegal_move_rate"] = d_ill
    if agg.get("illegal_move_rate", 0.0) > base_illegal + tol:
        passed = False
        reasons.append(
            f"illegal_move_rate {agg.get('illegal_move_rate')} > baseline {base_illegal} + tol {tol}"
        )

    return {
        "passed": passed,
        "reason": "; ".join(reasons) if reasons else "within_tolerance",
        "tolerance": tol,
        "deltas": deltas,
    }


def format_summary(agg: dict, comparison: dict, dataset: str, depth: int) -> str:
    """Short human-readable summary."""
    lines = [
        f"Engine-grounded eval — {dataset} (depth {depth})",
        f"  cases: {agg['n_cases']}  scored: {agg['n_scored']}  skipped: {agg['n_skipped']}",
        f"  mean_correctness: {agg['mean_correctness']}",
        f"  illegal_move_rate: {agg['illegal_move_rate']}",
    ]
    if comparison.get("deltas"):
        d = comparison["deltas"]
        parts = [f"{k}: {v:+.4f}" for k, v in d.items()]
        lines.append("  vs baseline: " + "  ".join(parts))
    verdict = "PASS" if comparison.get("passed") else "FAIL"
    lines.append(f"  gate: {verdict} ({comparison.get('reason')})")
    if agg["worst_cases"]:
        lines.append("  worst cases:")
        for w in agg["worst_cases"]:
            lines.append(f"    - {w['id']}: correctness={w['correctness_score']}")
    return "\n".join(lines)
