"""O6 — offline tests for the prompt-optimization harness (CL Phase 1 Slice 3).

Fully offline: the LLM call is mocked everywhere and no Stockfish/network is
touched (the metric's ``evaluate_turn`` is patched). Covers:

  * split determinism + stratification;
  * cache hit prevents a second live call;
  * budget abort still produces a (partial) report;
  * metric mapping: illegal move → 0.0, legal best move → 1.0;
  * the optimizer loop selects the higher-scoring variant with a mocked LLM;
  * artifacts are written and SOUL.md is never touched (content + mtime).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.optimize import dataset as ds
from src.optimize import generate as gen
from src.optimize import metric as met
from src.optimize import optimize as opt

_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _cases(n_per_stratum: int, strata) -> list[dict]:
    """Build a tiny synthetic dataset with ``id/fen/cohort/message_type``."""
    out = []
    i = 0
    for cohort, mtype in strata:
        for _ in range(n_per_stratum):
            i += 1
            out.append({
                "id": f"c{i:03d}", "fen": _FEN, "user_text": "best move?",
                "cohort": cohort, "message_type": mtype,
            })
    return out


# ── O1: split ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSplit:
    def test_deterministic_same_seed(self):
        cases = _cases(5, [("a", "x"), ("b", "y")])
        t1, h1 = ds.split_dataset(cases, seed=13)
        t2, h2 = ds.split_dataset(cases, seed=13)
        assert [c["id"] for c in t1] == [c["id"] for c in t2]
        assert [c["id"] for c in h1] == [c["id"] for c in h2]

    def test_partition_is_complete_and_disjoint(self):
        cases = _cases(5, [("a", "x"), ("b", "y")])
        train, holdout = ds.split_dataset(cases, seed=13)
        train_ids = {c["id"] for c in train}
        holdout_ids = {c["id"] for c in holdout}
        assert train_ids.isdisjoint(holdout_ids)
        assert train_ids | holdout_ids == {c["id"] for c in cases}

    def test_stratified_every_cell_represented(self):
        # 2 strata × 5 cases, 60% train ⇒ round(5*0.6)=3 train / 2 holdout each.
        cases = _cases(5, [("a", "x"), ("b", "y")])
        train, holdout = ds.split_dataset(cases, seed=13, train_frac=0.6)
        summary = ds.split_summary(train, holdout)
        assert summary["train_by_stratum"] == {"a|x": 3, "b|y": 3}
        assert summary["holdout_by_stratum"] == {"a|x": 2, "b|y": 2}

    def test_no_rng_state_leak_between_seeds(self):
        cases = _cases(4, [("a", "x")])
        a, _ = ds.split_dataset(cases, seed=1)
        b, _ = ds.split_dataset(cases, seed=1)
        assert [c["id"] for c in a] == [c["id"] for c in b]


# ── O2: cache + budget ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestGenerateCacheBudget:
    def test_cache_hit_prevents_second_call(self, tmp_path):
        cache = gen.DiskCache(str(tmp_path / "cache"))
        budget = gen.Budget(max_calls=10)
        case = {"id": "c1", "fen": _FEN, "user_text": "?"}
        mock_call = MagicMock(return_value="hello")
        with patch.object(gen, "build_case_prompt", return_value=("s", "u")), \
                patch.object(gen, "call_openrouter", mock_call):
            r1 = gen.generate_reply("SOUL", case, "m", cache, budget)
            r2 = gen.generate_reply("SOUL", case, "m", cache, budget)
        assert r1 == r2 == "hello"
        assert mock_call.call_count == 1  # second was a cache hit
        assert budget.count == 1

    def test_variant_hash_changes_cache_key(self):
        assert gen.cache_key("A", "c1", "m") != gen.cache_key("B", "c1", "m")
        assert gen.cache_key("A", "c1", "m") == gen.cache_key("A", "c1", "m")

    def test_budget_record_raises_when_exhausted(self):
        budget = gen.Budget(max_calls=1)
        budget.record()
        assert budget.exceeded()
        with pytest.raises(gen.BudgetExceeded):
            budget.record()

    def test_budget_persists_across_instances(self, tmp_path):
        state = str(tmp_path / "budget.json")
        b1 = gen.Budget(max_calls=5, state_path=state)
        b1.record()
        b1.record()
        b2 = gen.Budget(max_calls=5, state_path=state)
        assert b2.count == 2  # resumed from disk


# ── O3: metric ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMetric:
    def test_illegal_move_scores_zero(self):
        assert met.score_from_verdict(
            {"illegal_move_rate": 0.5, "correctness_score": 0.9}
        ) == 0.0

    def test_legal_best_move_scores_one(self):
        assert met.score_from_verdict(
            {"illegal_move_rate": 0.0, "correctness_score": 1.0}
        ) == 1.0

    def test_no_verifiable_claim_scores_zero(self):
        assert met.score_from_verdict(
            {"illegal_move_rate": 0.0, "correctness_score": None}
        ) == 0.0

    def test_score_reply_wires_through_evaluate_turn(self):
        fake = MagicMock()
        fake.to_dict.return_value = {"illegal_move_rate": 0.0, "correctness_score": 0.85}
        with patch.object(met, "evaluate_turn", return_value=fake):
            assert met.score_reply("Play Nf3.", {"fen": _FEN}) == 0.85

    def test_illegal_via_evaluate_turn_is_zero(self):
        fake = MagicMock()
        fake.to_dict.return_value = {"illegal_move_rate": 1.0, "correctness_score": 0.0}
        with patch.object(met, "evaluate_turn", return_value=fake):
            assert met.score_reply("Play Ke9.", {"fen": _FEN}) == 0.0

    def test_dataset_metrics_match_runner_definitions(self):
        verdicts = [
            {"status": "ok", "correctness_score": 1.0, "illegal_move_rate": 0.0,
             "claims": [{"kind": "recommended_move", "score": 1.0}]},
            {"status": "ok", "correctness_score": 0.0, "illegal_move_rate": 1.0,
             "claims": [{"kind": "illegal_move", "score": 0.0}]},
        ]
        m = met.dataset_metrics(verdicts)
        assert m["mean_correctness"] == pytest.approx(0.5, abs=1e-4)
        assert m["illegal_move_rate"] == pytest.approx(0.5, abs=1e-4)


# ── O4/O5: optimizer loop + artifacts ──────────────────────────────────────


def _fake_verdict_for(reply: str) -> dict:
    """Map a mocked reply string to a deterministic verdict dict (no engine)."""
    if "GOOD" in reply:
        cs = 1.0
    elif "BAD" in reply:
        cs = 0.2
    else:  # the baseline / current SOUL reply
        cs = 0.5
    return {"status": "ok", "correctness_score": cs, "illegal_move_rate": 0.0,
            "claims": [{"kind": "recommended_move", "score": cs}]}


def _run_mocked_optimizer(tmp_path, *, max_llm_calls=100, rounds=1):
    """Drive optimize() with the LLM path fully mocked. Returns (report, run_dir, soul_path)."""
    soul_path = tmp_path / "SOUL.md"
    soul_path.write_text("BASE SOUL persona", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    cache_dir = tmp_path / "cache"
    cases = _cases(2, [("a", "x"), ("b", "y")])
    dataset = tmp_path / "ds.jsonl"
    dataset.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")

    def fake_generate(soul_text, case, model, cache, budget):
        return f"REPLY::{soul_text}"

    def fake_evaluate(reply, case, depth):
        return _fake_verdict_for(reply)

    proposals = [["GOOD SOUL improved", "BAD SOUL worse"]] + [[]] * rounds

    def fake_propose(current_soul, worst, k, model, budget):
        return proposals.pop(0) if proposals else []

    with patch.object(opt, "generate_reply", side_effect=fake_generate), \
            patch.object(opt, "evaluate_reply", side_effect=fake_evaluate), \
            patch.object(opt, "propose_variants", side_effect=fake_propose):
        report = opt.optimize(
            dataset_path=str(dataset), out_dir=str(runs_dir), run_id="testrun",
            current_soul_path=str(soul_path), cache_dir=str(cache_dir),
            model="m", critic_model="c", seed=13, train_frac=0.5,
            max_llm_calls=max_llm_calls, rounds=rounds, variants_per_round=2, depth=8,
        )
    return report, runs_dir / "testrun", soul_path


@pytest.mark.unit
class TestOptimizer:
    def test_selects_higher_scoring_variant(self, tmp_path):
        report, _, _ = _run_mocked_optimizer(tmp_path)
        # Baseline 0.5, GOOD 1.0, BAD 0.2 ⇒ winner is the GOOD candidate.
        winner = next(c for c in report["candidates"] if c["is_winner"])
        assert report["winner"] == winner["n"]
        assert winner["train"]["mean_score"] == pytest.approx(1.0)
        assert report["baseline"]["train"]["mean_score"] == pytest.approx(0.5)
        # Holdout scored once for the winner (and baseline), never for the loser.
        assert winner["holdout"] is not None
        loser = next(c for c in report["candidates"] if not c["is_winner"])
        assert loser["holdout"] is None

    def test_artifacts_written(self, tmp_path):
        report, run_dir, _ = _run_mocked_optimizer(tmp_path)
        assert (run_dir / "report.json").exists()
        assert (run_dir / "report.md").exists()
        # One .soul.md + .diff per candidate.
        for c in report["candidates"]:
            assert (run_dir / f"candidate_{c['n']}.soul.md").exists()
            diff = (run_dir / f"candidate_{c['n']}.diff").read_text()
            assert "SOUL.md" in diff  # unified diff header references the source
        loaded = json.loads((run_dir / "report.json").read_text())
        assert loaded["path_taken"].startswith("critic-loop fallback")

    def test_soul_md_never_touched(self, tmp_path):
        # The REAL committed SOUL.md must be untouched by any optimizer run.
        from src.config import PROFILE_DIR

        real_soul = PROFILE_DIR / "SOUL.md"
        before_content = real_soul.read_text()
        before_mtime = real_soul.stat().st_mtime
        _run_mocked_optimizer(tmp_path)
        assert real_soul.read_text() == before_content
        assert real_soul.stat().st_mtime == before_mtime

    def test_budget_abort_produces_partial_report(self, tmp_path):
        soul_path = tmp_path / "SOUL.md"
        soul_path.write_text("BASE SOUL", encoding="utf-8")
        cases = _cases(3, [("a", "x")])  # 3 train (frac 1.0) ⇒ 3 generations needed
        dataset = tmp_path / "ds.jsonl"
        dataset.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")

        # Real generate_reply + real Budget, but the LLM call and prompt build are
        # mocked; max_llm_calls=2 forces a BudgetExceeded on the 3rd baseline case.
        with patch.object(gen, "build_case_prompt", return_value=("s", "u")), \
                patch.object(gen, "call_openrouter", return_value="canned"), \
                patch.object(opt, "evaluate_reply", side_effect=lambda r, c, depth: _fake_verdict_for(r)):
            report = opt.optimize(
                dataset_path=str(dataset), out_dir=str(tmp_path / "runs"), run_id="partial",
                current_soul_path=str(soul_path), cache_dir=str(tmp_path / "cache"),
                model="m", critic_model="c", seed=13, train_frac=1.0,
                max_llm_calls=2, rounds=1, variants_per_round=2, depth=8,
            )
        assert report["partial"] is True
        assert report["budget"]["used"] == 2
        assert (tmp_path / "runs" / "partial" / "report.json").exists()
