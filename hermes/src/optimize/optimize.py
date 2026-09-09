"""O4/O5 — the prompt optimizer loop + run artifacts.

**Path taken: critic-loop fallback (not DSPy).** The optimizable object here is a
single, long, hand-written system prompt (the whole ``SOUL.md`` persona), not a
few-shot program with swappable demos or a short instruction field. DSPy's
``MIPROv2`` / ``GEPA`` are built around signatures + demonstrations and would
fight that shape (and drag in ``dspy-ai`` / ``litellm`` + a dedicated venv). So
this slice uses the explicitly-sanctioned fallback: a **propose → evaluate →
select** loop —

  1. a cheap **critic** model reads the current SOUL block + the worst-scoring
     train cases and proposes ``K`` full edited SOUL variants;
  2. each variant is scored on the **train** split via O2 (generate) + O3 (score);
  3. the best-scoring variant becomes the base for the next round (2–3 rounds).

The **holdout** split is scored exactly ONCE, only for the final winner (and the
current prompt, for comparison) — never for selection. Nothing here writes to
``SOUL.md``; every proposal lands as a reviewable artifact under ``runs/``.
"""

import difflib
import json
from pathlib import Path
from typing import Optional

from src.optimize.dataset import load_dataset, split_dataset, split_summary
from src.optimize.generate import (
    Budget,
    BudgetExceeded,
    DiskCache,
    call_openrouter,
    estimate_cost,
    generate_reply,
)
from src.optimize.metric import dataset_metrics, evaluate_reply, score_from_verdict

DEFAULT_ROUNDS = 2
DEFAULT_VARIANTS_PER_ROUND = 3
WORST_CASES_SHOWN = 8

# ── Selection metric ────────────────────────────────────────────────────
# ``mean_score`` (mean of per-case rewards over ALL cases, unscored → 0.0)
# rewards claim VOLUME: a prompt that makes engine-verifiable claims on more
# cases outranks a more accurate but quieter one. Selection therefore uses
# ``mean_correctness`` (mean over scored cases only) with two hard
# disqualifiers: any illegal move on train, and scoring on fewer cases than
# the coverage floor (so a candidate can't win by only speaking when certain).
MIN_SCORED_FLOOR = 3

SELECTION_METRIC = (
    "mean_correctness over scored cases; disqualified if any illegal move on "
    f"train, or n_scored below max(min({MIN_SCORED_FLOOR}, baseline n_scored), "
    "half the baseline's n_scored)"
)


def coverage_floor(baseline_scored: Optional[int]) -> int:
    b = baseline_scored or 0
    return max(min(MIN_SCORED_FLOOR, b), b // 2)


def selection_view(ev: Optional[dict], baseline_scored: Optional[int]) -> Optional[dict]:
    """Judge one evaluation under the selection metric.

    Returns ``{selection_score, qualified, disqualified: [reasons]}``. The
    score is ``mean_correctness`` (0.0 when nothing was scored); ``qualified``
    is False when any train reply contained an illegal move or coverage fell
    below the floor.
    """
    if ev is None:
        return None
    m = ev["metrics"] if "metrics" in ev else ev
    reasons: list[str] = []
    if m.get("illegal_move_rate") or 0.0:
        reasons.append(f"illegal moves on train (rate {m['illegal_move_rate']})")
    floor = coverage_floor(baseline_scored)
    if (m.get("n_scored") or 0) < floor:
        reasons.append(f"coverage {m.get('n_scored')} scored cases < floor {floor}")
    score = m.get("mean_correctness")
    return {
        "selection_score": float(score) if score is not None else 0.0,
        "qualified": not reasons,
        "disqualified": reasons,
    }

# The critic is told the current SOUL is DATA to improve, and to return ONLY the
# full revised markdown between the sentinels so it parses cleanly.
_CRITIC_SYSTEM = (
    "You are a prompt engineer improving the system prompt (a chess coach's "
    "'SOUL.md' persona) of an AI chess coach. The coach's replies are graded by "
    "a chess ENGINE: recommending an illegal move scores zero; recommending a "
    "weaker move loses points by centipawn loss; correct engine-agreeing "
    "assessments score full marks. Your job is to revise the SOUL so the coach "
    "makes more engine-correct, legal move recommendations and accurate "
    "position assessments — WITHOUT changing its teaching voice or removing its "
    "tool-use discipline.\n\n"
    "You will be given the current SOUL and its worst-scoring cases. Propose a "
    "SINGLE improved full SOUL. Keep it roughly the same length and structure. "
    "Do NOT invent chess facts or hard-code answers to the sample cases.\n\n"
    "Output ONLY the full revised markdown between <SOUL> and </SOUL> — no "
    "commentary, no code fences."
)

# Distinct angles so K proposals aren't near-duplicates.
_VARIATION_HINTS = (
    "Emphasise verifying every recommended move with the engine/tools before "
    "stating it, and never asserting an unverified move.",
    "Emphasise precise, engine-grounded position assessments (winning/equal/"
    "losing) and hedging when unsure rather than overclaiming.",
    "Tighten the move-recommendation instructions so the coach names the single "
    "strongest legal move clearly when asked, without burying it.",
    "Reduce hallucination risk broadly: be explicit that any concrete move or "
    "evaluation must be engine-checked and legal.",
)


def _norm(text: str) -> str:
    return (text or "").strip()


def _extract_soul(raw: Optional[str]) -> Optional[str]:
    """Pull the revised SOUL out of a critic response.

    Prefers the ``<SOUL>...</SOUL>`` sentinels; falls back to the whole response
    (minus any accidental code fences). Returns None for an empty response.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw
    start = text.find("<SOUL>")
    end = text.rfind("</SOUL>")
    if start != -1 and end != -1 and end > start:
        text = text[start + len("<SOUL>"):end]
    text = text.strip()
    if text.startswith("```"):
        # strip a leading/trailing fence if the model added one anyway
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text or None


def build_critic_prompt(current_soul: str, worst: list[dict], hint: str) -> str:
    """User message for the critic: current SOUL + worst cases + this round's angle."""
    lines = ["Focus for this proposal: " + hint, "", "## Worst-scoring cases"]
    if worst:
        for w in worst:
            lines.append(
                f"- case {w.get('id')} (score {w.get('score')}, "
                f"{w.get('message_type', '?')}): user asked "
                f"{json.dumps(w.get('user_text', ''))} at FEN {w.get('fen', '')}"
            )
    else:
        lines.append("- (none available)")
    lines += ["", "## Current SOUL to improve", current_soul,
              "", "Return the full revised SOUL between <SOUL> and </SOUL>."]
    return "\n".join(lines)


def call_critic(current_soul: str, worst: list[dict], model: str, hint: str) -> Optional[str]:
    """One critic chat call (reuses the O2 httpx path). Returns raw text or None."""
    user = build_critic_prompt(current_soul, worst, hint)
    return call_openrouter(_CRITIC_SYSTEM, user, model)


def propose_variants(
    current_soul: str,
    worst: list[dict],
    k: int,
    model: str,
    budget: Budget,
) -> list[str]:
    """Propose up to ``k`` distinct full-SOUL variants via the critic.

    Each proposal is one live call (budget-charged before the call, so a breach
    raises :class:`BudgetExceeded` and the caller can stop cleanly). Empty or
    duplicate proposals (including no-ops equal to the current SOUL) are dropped.
    """
    variants: list[str] = []
    seen = {_norm(current_soul)}
    for i in range(k):
        budget.record()
        raw = call_critic(current_soul, worst, model, _VARIATION_HINTS[i % len(_VARIATION_HINTS)])
        variant = _extract_soul(raw)
        if variant and _norm(variant) not in seen:
            seen.add(_norm(variant))
            variants.append(variant)
    return variants


def evaluate_variant(
    soul_text: str,
    cases: list[dict],
    model: str,
    cache: DiskCache,
    budget: Budget,
    depth: int,
) -> dict:
    """Score one SOUL variant over ``cases`` (generate → engine-score).

    Returns ``mean_score`` (the selection reward), the dataset-level engine
    metrics, and a per-case ``[{id, score}]`` list (used to pick worst cases).
    May raise :class:`BudgetExceeded` from generation.
    """
    verdicts: list[dict] = []
    per_case: list[dict] = []
    scores: list[float] = []
    for case in cases:
        reply = generate_reply(soul_text, case, model, cache, budget)
        verdict = evaluate_reply(reply, case, depth=depth)
        score = score_from_verdict(verdict)
        verdicts.append(verdict)
        scores.append(score)
        per_case.append({
            "id": case.get("id"),
            "score": round(score, 4),
            "message_type": case.get("message_type"),
            "cohort": case.get("cohort"),
            "user_text": case.get("user_text", ""),
            "fen": case.get("fen", ""),
        })
    mean_score = round(sum(scores) / len(scores), 4) if scores else 0.0
    return {
        "mean_score": mean_score,
        "metrics": dataset_metrics(verdicts),
        "per_case": per_case,
    }


def _worst_cases(evaluation: dict, n: int = WORST_CASES_SHOWN) -> list[dict]:
    return sorted(evaluation["per_case"], key=lambda p: p["score"])[:n]


def _unified_diff(current_soul: str, variant: str, run_id: str, n: int) -> str:
    return "".join(
        difflib.unified_diff(
            current_soul.splitlines(keepends=True),
            variant.splitlines(keepends=True),
            fromfile="profiles/chess-coach/SOUL.md (current)",
            tofile=f"runs/{run_id}/candidate_{n}.soul.md",
        )
    )


def optimize(
    dataset_path: str,
    out_dir: str,
    run_id: str,
    current_soul_path: str,
    cache_dir: str,
    *,
    model: str,
    critic_model: str,
    seed: int,
    train_frac: float,
    max_llm_calls: int,
    rounds: int = DEFAULT_ROUNDS,
    variants_per_round: int = DEFAULT_VARIANTS_PER_ROUND,
    depth: int,
) -> dict:
    """Run the propose→evaluate→select loop and write run artifacts.

    Never writes ``SOUL.md``. Aborts cleanly on budget exhaustion, still emitting
    a (partial) report. Returns the report dict.
    """
    cases = load_dataset(dataset_path)
    train, holdout = split_dataset(cases, seed=seed, train_frac=train_frac)
    current_soul = Path(current_soul_path).read_text(encoding="utf-8")

    run_path = Path(out_dir) / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    cache = DiskCache(cache_dir)
    budget = Budget(max_llm_calls, state_path=str(run_path / "budget.json"))

    partial = False
    candidates: list[dict] = []  # {n, soul, round, hint_index, train}
    baseline_train: Optional[dict] = None

    try:
        baseline_train = evaluate_variant(current_soul, train, model, cache, budget, depth)
    except BudgetExceeded:
        partial = True

    baseline_scored = baseline_train["metrics"]["n_scored"] if baseline_train else None

    def _sel(ev: Optional[dict]) -> Optional[dict]:
        return selection_view(ev, baseline_scored)

    best_soul = current_soul
    best_train = baseline_train
    next_n = 1

    if not partial:
        for _round in range(rounds):
            worst = _worst_cases(best_train) if best_train else []
            try:
                variants = propose_variants(best_soul, worst, variants_per_round, critic_model, budget)
            except BudgetExceeded:
                partial = True
                break
            round_best = None
            for variant in variants:
                try:
                    ev = evaluate_variant(variant, train, model, cache, budget, depth)
                except BudgetExceeded:
                    partial = True
                    break
                candidates.append({"n": next_n, "soul": variant, "round": _round + 1, "train": ev})
                next_n += 1
                sel = _sel(ev)
                if sel["qualified"] and (
                    round_best is None or sel["selection_score"] > _sel(round_best[1])["selection_score"]
                ):
                    round_best = (variant, ev)
            if partial:
                break
            if round_best and (
                best_train is None
                or _sel(round_best[1])["selection_score"] > _sel(best_train)["selection_score"]
            ):
                best_soul, best_train = round_best

    # Winner: the best QUALIFIED candidate (no illegal moves, coverage ≥ floor)
    # that strictly beats the current prompt's mean_correctness on train.
    winner_n: Optional[int] = None
    winner: Optional[dict] = None
    if candidates and baseline_train is not None:
        qualified = [c for c in candidates if _sel(c["train"])["qualified"]]
        if qualified:
            top = max(qualified, key=lambda c: _sel(c["train"])["selection_score"])
            if _sel(top["train"])["selection_score"] > _sel(baseline_train)["selection_score"]:
                winner_n = top["n"]
                winner = top

    # Holdout scored ONCE — only for the current prompt (baseline) and the winner.
    baseline_holdout: Optional[dict] = None
    winner_holdout: Optional[dict] = None
    if not partial:
        try:
            baseline_holdout = evaluate_variant(current_soul, holdout, model, cache, budget, depth)
            if winner is not None:
                winner_holdout = evaluate_variant(winner["soul"], holdout, model, cache, budget, depth)
        except BudgetExceeded:
            partial = True

    report = _build_report(
        run_id=run_id, seed=seed, model=model, critic_model=critic_model, depth=depth,
        rounds=rounds, variants_per_round=variants_per_round, budget=budget, partial=partial,
        split_info=split_summary(train, holdout),
        baseline_train=baseline_train, baseline_holdout=baseline_holdout,
        candidates=candidates, winner_n=winner_n, winner_holdout=winner_holdout,
    )

    _write_artifacts(run_path, current_soul, candidates, winner_n, report, run_id)
    return report


# ── Free re-rank of an existing run ─────────────────────────────────────


def rerank(run_dir: str) -> dict:
    """Re-judge an existing run's candidates under the CURRENT selection metric.

    Costs nothing: works from the run's ``report.json`` (whose per-candidate
    metrics were produced by the engine scorer at run time). Writes
    ``rerank.json`` / ``rerank.md`` next to the original report and returns the
    rerank dict. A new winner found here has NO holdout numbers unless the
    original run happened to score it — the artifact says so explicitly.
    """
    run_path = Path(run_dir)
    report = json.loads((run_path / "report.json").read_text(encoding="utf-8"))
    baseline_train = report["baseline"]["train"]
    baseline_scored = baseline_train.get("n_scored") if baseline_train else None
    baseline_sel = selection_view(baseline_train, baseline_scored)

    judged = []
    for c in report["candidates"]:
        sel = selection_view(c["train"], baseline_scored)
        judged.append({
            "n": c["n"],
            "round": c["round"],
            "original_winner": c["is_winner"],
            "train": c["train"],
            "selection": sel,
            "holdout": c["holdout"],
        })

    winner = None
    qualified = [j for j in judged if j["selection"]["qualified"]]
    if qualified and baseline_sel is not None:
        top = max(qualified, key=lambda j: j["selection"]["selection_score"])
        if top["selection"]["selection_score"] > baseline_sel["selection_score"]:
            winner = top

    result = {
        "reranked_from": report["run_id"],
        "selection_metric": SELECTION_METRIC,
        "baseline": {"train": baseline_train, "selection": baseline_sel,
                     "holdout": report["baseline"]["holdout"]},
        "candidates": judged,
        "winner": winner["n"] if winner else None,
        "winner_has_holdout": bool(winner and winner["holdout"]),
        "verdict": (
            f"candidate_{winner['n']} beats baseline on the honest metric"
            + ("" if winner["holdout"] else " (NO holdout validation — score it before applying)")
            if winner else
            "baseline retained — no qualified candidate beats the current SOUL.md"
        ),
    }

    md = [
        f"# Re-rank of `{report['run_id']}` under the honest selection metric",
        "",
        f"- **Metric:** {SELECTION_METRIC}",
        f"- **Baseline:** train correctness {baseline_train.get('mean_correctness')} "
        f"on {baseline_train.get('n_scored')}/{baseline_train.get('n_cases')} scored, "
        f"illegal {baseline_train.get('illegal_move_rate')}",
        "",
        "| # | round | train correctness | scored | illegal | qualified | old winner |",
        "|---|-------|-------------------|--------|---------|-----------|------------|",
    ]
    for j in judged:
        t = j["train"]
        qual = "✅" if j["selection"]["qualified"] else "❌ " + "; ".join(j["selection"]["disqualified"])
        md.append(
            f"| {j['n']} | {j['round']} | {t.get('mean_correctness')} | "
            f"{t.get('n_scored')}/{t.get('n_cases')} | {t.get('illegal_move_rate')} | "
            f"{qual} | {'⚠️' if j['original_winner'] else ''} |"
        )
    md += ["", f"**Verdict:** {result['verdict']}", ""]

    (run_path / "rerank.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_path / "rerank.md").write_text("\n".join(md), encoding="utf-8")
    return result


# ── Artifacts (O5) ──────────────────────────────────────────────────────


def _metrics_view(ev: Optional[dict]) -> Optional[dict]:
    if ev is None:
        return None
    return {"mean_score": ev["mean_score"], **ev["metrics"]}


def _build_report(
    *, run_id, seed, model, critic_model, depth, rounds, variants_per_round,
    budget, partial, split_info, baseline_train, baseline_holdout,
    candidates, winner_n, winner_holdout,
) -> dict:
    baseline_scored = baseline_train["metrics"]["n_scored"] if baseline_train else None
    cand_records = []
    for c in candidates:
        is_winner = c["n"] == winner_n
        cand_records.append({
            "n": c["n"],
            "round": c["round"],
            "is_winner": is_winner,
            "soul_file": f"candidate_{c['n']}.soul.md",
            "diff_file": f"candidate_{c['n']}.diff",
            "train": _metrics_view(c["train"]),
            "selection": selection_view(c["train"], baseline_scored),
            "holdout": _metrics_view(winner_holdout) if is_winner else None,
        })
    return {
        "run_id": run_id,
        "selection_metric": SELECTION_METRIC,
        "path_taken": "critic-loop fallback (single-system-prompt shape; DSPy not used)",
        "seed": seed,
        "model": model,
        "critic_model": critic_model,
        "depth": depth,
        "rounds": rounds,
        "variants_per_round": variants_per_round,
        "partial": partial,
        "budget": {
            "max_llm_calls": budget.max_calls,
            "used": budget.count,
            "remaining": budget.remaining,
            "estimated_cost_usd": estimate_cost(budget.count, model),
        },
        "split": split_info,
        "baseline": {
            "train": _metrics_view(baseline_train),
            "holdout": _metrics_view(baseline_holdout),
        },
        "candidates": cand_records,
        "winner": winner_n,
    }


_FOOTER = (
    "This harness never edits profiles/chess-coach/SOUL.md. Applying a winning "
    "candidate is a separate, deliberate human commit — and that commit changes "
    "the coach's prompt source, which triggers the Phase 0 engine-correctness CI "
    "eval gate (.github/workflows/hermes-eval.yml). Re-baseline the frozen golden "
    "set in the same commit or the gate fails."
)


def _render_report_md(report: dict) -> str:
    lines = [
        f"# Prompt optimization run `{report['run_id']}`",
        "",
        f"- **Path:** {report['path_taken']}",
        f"- **Model (generate):** `{report['model']}`  |  **Critic:** `{report['critic_model']}`",
        f"- **Seed:** {report['seed']}  |  **Depth:** {report['depth']}  |  "
        f"**Rounds:** {report['rounds']} × {report['variants_per_round']} variants",
        f"- **Budget:** {report['budget']['used']}/{report['budget']['max_llm_calls']} "
        f"live calls (~${report['budget']['estimated_cost_usd']} est.)"
        + ("  ⚠️ **PARTIAL run (budget exhausted)**" if report["partial"] else ""),
        f"- **Split:** {report['split']['n_train']} train / "
        f"{report['split']['n_holdout']} holdout",
        f"- **Selection metric:** {report.get('selection_metric', 'mean_score (legacy)')}",
        "",
        "## Baseline (current SOUL.md)",
        f"- train: {report['baseline']['train']}",
        f"- holdout: {report['baseline']['holdout']}",
        "",
        "## Candidates",
    ]
    if report["candidates"]:
        lines.append("| # | round | train correctness | scored | train illegal | qualified | winner | holdout correctness |")
        lines.append("|---|-------|-------------------|--------|---------------|-----------|--------|---------------------|")
        for c in report["candidates"]:
            t = c["train"] or {}
            ho = c["holdout"]
            sel = c.get("selection") or {}
            qual = "✅" if sel.get("qualified") else "❌ " + "; ".join(sel.get("disqualified", []))
            lines.append(
                f"| {c['n']} | {c['round']} | {t.get('mean_correctness')} | "
                f"{t.get('n_scored')}/{t.get('n_cases')} | {t.get('illegal_move_rate')} | "
                f"{qual} | {'✅' if c['is_winner'] else ''} | "
                f"{ho.get('mean_correctness') if ho else '—'} |"
            )
    else:
        lines.append("_No candidates were produced._")
    lines += [
        "",
        f"**Winner:** {('candidate_' + str(report['winner'])) if report['winner'] else 'none (baseline retained)'}",
        "",
        "---",
        _FOOTER,
    ]
    return "\n".join(lines) + "\n"


def _write_artifacts(
    run_path: Path, current_soul: str, candidates: list[dict],
    winner_n: Optional[int], report: dict, run_id: str,
) -> None:
    for c in candidates:
        (run_path / f"candidate_{c['n']}.soul.md").write_text(c["soul"], encoding="utf-8")
        (run_path / f"candidate_{c['n']}.diff").write_text(
            _unified_diff(current_soul, c["soul"], run_id, c["n"]), encoding="utf-8"
        )
    (run_path / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_path / "report.md").write_text(_render_report_md(report), encoding="utf-8")
