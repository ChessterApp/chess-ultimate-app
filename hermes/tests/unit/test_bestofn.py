"""Unit tests for best-of-N with engine selection — CL Phase 2, Slice 3.

Fully offline: the engine (evaluate_turn), the judge LLM, and Supabase are all
injected fakes or mocks — no network, no Stockfish binary, no DB. Covers the
engine gate, the survivors-only judge, every fallback path (judge_error,
all_failed, engine_skipped, budget_exceeded, exception), the N clamp, the audit
row shape, and the flag-off byte-identical no-op.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

import src.bestofn as bon


# ── Fake engine verdicts ─────────────────────────────────────────────────


def _verdict(status="ok", correctness=1.0, illegal_rate=0.0):
    """Build an engine verdict dict shaped like EngineVerdict.to_dict()."""
    return {
        "status": status,
        "correctness_score": correctness,
        "illegal_move_rate": illegal_rate,
        "claims": [],
        "notes": [],
    }


def _fake_evaluate(mapping):
    """Return an evaluate_fn(fen, text, user_text, depth) that maps text→verdict."""
    def _ev(fen, assistant_text, user_text, depth):
        return dict(mapping[assistant_text])
    return _ev


# ── rank_candidates: engine classification ───────────────────────────────


@pytest.mark.unit
class TestRankCandidates:
    def test_classifies_pass_fail_skip(self):
        mapping = {
            "good": _verdict(correctness=0.9),
            "illegal": _verdict(correctness=0.0, illegal_rate=0.5),
            "skipped": _verdict(status="skipped", correctness=None),
        }
        ranked = bon.rank_candidates(
            "fen", "q", ["good", "illegal", "skipped"], evaluate_fn=_fake_evaluate(mapping)
        )
        assert [rc.idx for rc in ranked] == [0, 1, 2]
        assert ranked[0].passed is True and ranked[0].score == 0.9
        assert ranked[1].passed is False and ranked[1].score == 0.0   # illegal → gate fail
        assert ranked[2].passed is False and ranked[2].status == "skipped"

    def test_zero_score_still_passes_gate(self):
        # No verifiable claim (score 0.0, no illegal move) survives — the gate
        # drops hallucinations, not merely-unremarkable answers.
        mapping = {"meh": _verdict(correctness=None)}
        ranked = bon.rank_candidates("fen", "q", ["meh"], evaluate_fn=_fake_evaluate(mapping))
        assert ranked[0].score == 0.0 and ranked[0].passed is True

    def test_pure_given_injected_fn(self):
        calls = []

        def _ev(fen, text, user, depth):
            calls.append((fen, text, user, depth))
            return _verdict()

        bon.rank_candidates("F", "U", ["a", "b"], depth=7, evaluate_fn=_ev)
        assert calls == [("F", "a", "U", 7), ("F", "b", "U", 7)]


# ── select_best: gate + judge + tie-breaking ─────────────────────────────


def _ranked(specs):
    """specs: list of (score, status, passed) → RankedCandidate list."""
    return [
        bon.RankedCandidate(idx=i, text=f"c{i}", score=s, status=st, passed=p, verdict={})
        for i, (s, st, p) in enumerate(specs)
    ]


@pytest.mark.unit
class TestSelectBest:
    def test_judge_only_sees_survivors(self):
        ranked = _ranked([(0.9, "ok", True), (0.0, "ok", False), (0.8, "ok", True)])
        seen = {}

        def judge(survivors):
            seen["idxs"] = [rc.idx for rc in survivors]
            return {"choice": 2, "reason": "clearest"}

        sel = bon.select_best(ranked, judge)
        # The engine-failing candidate 1 is never shown to the judge.
        assert seen["idxs"] == [0, 2]
        assert sel.selected_idx == 2 and sel.fallback_reason is None
        assert sel.judge == {"choice": 2, "reason": "clearest"}

    def test_single_survivor_skips_judge(self):
        ranked = _ranked([(0.9, "ok", True), (0.0, "ok", False)])
        judge = MagicMock()
        sel = bon.select_best(ranked, judge)
        judge.assert_not_called()
        assert sel.selected_idx == 0 and sel.fallback_reason is None

    def test_judge_malformed_falls_back_to_highest_score(self):
        ranked = _ranked([(0.7, "ok", True), (0.95, "ok", True)])
        sel = bon.select_best(ranked, lambda s: {"garbage": True})
        assert sel.selected_idx == 1 and sel.fallback_reason == "judge_error"

    def test_judge_returns_non_survivor_is_judge_error(self):
        ranked = _ranked([(0.7, "ok", True), (0.6, "ok", False), (0.95, "ok", True)])
        # choice 1 is not a survivor → treated as malformed.
        sel = bon.select_best(ranked, lambda s: {"choice": 1, "reason": "x"})
        assert sel.selected_idx == 2 and sel.fallback_reason == "judge_error"

    def test_judge_raises_falls_back(self):
        ranked = _ranked([(0.5, "ok", True), (0.9, "ok", True)])

        def judge(s):
            raise RuntimeError("boom")

        sel = bon.select_best(ranked, judge)
        assert sel.selected_idx == 1 and sel.fallback_reason == "judge_error"

    def test_all_failed_picks_least_bad(self):
        ranked = _ranked([(0.0, "ok", False), (0.2, "ok", False), (0.1, "ok", False)])
        sel = bon.select_best(ranked, MagicMock())
        assert sel.selected_idx == 1 and sel.fallback_reason == "all_failed"

    def test_all_skipped_is_no_op_passthrough(self):
        ranked = _ranked([(0.0, "skipped", False), (0.0, "skipped", False)])
        judge = MagicMock()
        sel = bon.select_best(ranked, judge)
        judge.assert_not_called()
        assert sel.selected_idx == 0 and sel.fallback_reason == "engine_skipped"

    def test_score_tie_breaks_to_first(self):
        ranked = _ranked([(0.5, "ok", False), (0.9, "ok", False), (0.9, "ok", False)])
        sel = bon.select_best(ranked, MagicMock())
        assert sel.selected_idx == 1 and sel.fallback_reason == "all_failed"


# ── judge prompt / parse ─────────────────────────────────────────────────


@pytest.mark.unit
class TestJudgeParsing:
    def test_parse_rejects_non_json(self):
        assert bon.parse_judge("not json") is None
        assert bon.parse_judge("") is None
        assert bon.parse_judge(None) is None

    def test_parse_rejects_missing_choice(self):
        assert bon.parse_judge('{"reason": "x"}') is None
        assert bon.parse_judge('{"choice": "two", "reason": "x"}') is None
        assert bon.parse_judge('[1, 2]') is None

    def test_parse_accepts_and_caps_reason(self):
        out = bon.parse_judge('{"choice": 1, "reason": "' + "z" * 500 + '"}')
        assert out["choice"] == 1
        assert len(out["reason"]) == bon.JUDGE_REASON_CAP

    def test_build_prompt_labels_original_idx_and_caps_text(self):
        survivors = _ranked([(0.9, "ok", True), (0.8, "ok", True)])
        survivors[1].text = "y" * 5000
        prompt = bon.build_judge_prompt("why?", survivors)
        assert "Candidate 0:" in prompt and "Candidate 1:" in prompt
        assert "why?" in prompt
        # Long candidate text is truncated for the judge context.
        assert "y" * bon.JUDGE_TEXT_CAP in prompt
        assert "y" * (bon.JUDGE_TEXT_CAP + 1) not in prompt

    def test_run_judge_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        survivors = _ranked([(0.9, "ok", True), (0.8, "ok", True)])
        assert bon.run_judge(survivors, user_text="q", model="m") is None

    def test_run_judge_parses_and_records_usage(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        survivors = _ranked([(0.9, "ok", True), (0.8, "ok", True)])
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": '{"choice": 1, "reason": "clear"}'}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 7},
        }
        resp.raise_for_status = MagicMock()
        recorded = []
        with patch("src.bestofn.httpx.post", return_value=resp):
            out = bon.run_judge(
                survivors, user_text="q", model="cheap",
                on_usage=lambda p, c, m: recorded.append((p, c, m)),
            )
        assert out == {"choice": 1, "reason": "clear", "model": "cheap"}
        assert recorded == [(42, 7, "cheap")]

    def test_run_judge_http_failure_returns_none(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        survivors = _ranked([(0.9, "ok", True), (0.8, "ok", True)])
        with patch("src.bestofn.httpx.post", side_effect=RuntimeError("net")):
            assert bon.run_judge(survivors, user_text="q", model="m") is None


# ── run_bestofn: orchestration + fallbacks ───────────────────────────────


@pytest.mark.unit
class TestRunBestOfN:
    def _gen(self, texts):
        return lambda i: texts[i]

    def test_happy_path_engine_and_judge(self):
        texts = ["weak answer", "strong answer"]
        mapping = {"weak answer": _verdict(correctness=0.5),
                   "strong answer": _verdict(correctness=0.95)}
        res = bon.run_bestofn(
            fen="fen", user_text="q", generate=self._gen(texts),
            judge_fn=lambda s: {"choice": 1, "reason": "clearer"},
            n=2, evaluate_fn=_fake_evaluate(mapping),
        )
        assert res.selected_idx == 1 and res.text == "strong answer"
        assert res.fallback_reason is None and res.n == 2
        assert res.judge == {"choice": 1, "reason": "clearer"}

    def test_n_clamped_to_max(self):
        gen_calls = []

        def gen(i):
            gen_calls.append(i)
            return f"cand{i}"

        mapping = {f"cand{i}": _verdict(correctness=0.5) for i in range(bon.MAX_N)}
        res = bon.run_bestofn(
            fen="fen", user_text="q", generate=gen,
            judge_fn=lambda s: {"choice": 0, "reason": "x"},
            n=99, evaluate_fn=_fake_evaluate(mapping),
        )
        assert res.n == bon.MAX_N
        assert sorted(gen_calls) == list(range(bon.MAX_N))

    def test_skipped_verdict_is_no_op_candidate_one(self):
        texts = ["a", "b"]
        mapping = {"a": _verdict(status="skipped", correctness=None),
                   "b": _verdict(status="skipped", correctness=None)}
        judge = MagicMock()
        res = bon.run_bestofn(
            fen="bad", user_text="q", generate=self._gen(texts), judge_fn=judge,
            n=2, evaluate_fn=_fake_evaluate(mapping),
        )
        judge.assert_not_called()
        assert res.selected_idx == 0 and res.text == "a"
        assert res.fallback_reason == "engine_skipped"

    def test_all_failed_records_reason_and_serves_least_bad(self):
        texts = ["x", "y"]
        mapping = {"x": _verdict(correctness=0.0, illegal_rate=1.0),
                   "y": _verdict(correctness=0.0, illegal_rate=1.0)}
        res = bon.run_bestofn(
            fen="fen", user_text="q", generate=self._gen(texts), judge_fn=MagicMock(),
            n=2, evaluate_fn=_fake_evaluate(mapping),
        )
        assert res.fallback_reason == "all_failed"
        assert res.text in ("x", "y")

    def test_budget_exceeded_returns_best_so_far(self):
        texts = ["lo", "hi"]
        mapping = {"lo": _verdict(correctness=0.4), "hi": _verdict(correctness=0.9)}
        # Clock jumps far past the deadline right after candidate 0 is generated,
        # so generation of extras is skipped and the judge is bypassed.
        ticks = iter([0.0, 100.0, 100.0, 100.0, 100.0, 100.0])
        judge = MagicMock()
        res = bon.run_bestofn(
            fen="fen", user_text="q", generate=self._gen(texts), judge_fn=judge,
            n=2, budget_ms=1, evaluate_fn=_fake_evaluate(mapping),
            clock=lambda: next(ticks),
        )
        judge.assert_not_called()
        assert res.fallback_reason == "budget_exceeded"
        assert res.selected_idx == 0 and res.text == "lo"

    def test_exception_anywhere_serves_candidate_one(self):
        def bad_eval(*a, **k):
            raise RuntimeError("engine blew up")

        res = bon.run_bestofn(
            fen="fen", user_text="q", generate=self._gen(["only", "second"]),
            judge_fn=MagicMock(), n=2, evaluate_fn=bad_eval,
        )
        assert res.fallback_reason == "exception"
        assert res.selected_idx == 0 and res.text == "only"
        # The audit still shows the candidate texts even on the exception path.
        assert res.ranked and res.ranked[0].text == "only"

    def test_candidate_zero_generation_failure_propagates(self):
        def gen(i):
            raise RuntimeError("total failure")

        with pytest.raises(RuntimeError):
            bon.run_bestofn(
                fen="fen", user_text="q", generate=gen, judge_fn=MagicMock(), n=2,
            )


# ── Audit row shape ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestAudit:
    def _result(self):
        ranked = [
            bon.RankedCandidate(idx=0, text="a" * 5000, score=0.5, status="ok",
                                passed=True, verdict={}),
            bon.RankedCandidate(idx=1, text="b", score=0.9, status="ok",
                                passed=True, verdict={}),
        ]
        return bon.BestOfNResult(
            text="b", selected_idx=1, n=2, ranked=ranked,
            judge={"choice": 1, "reason": "clear", "model": "cheap"},
            fallback_reason=None, latency_ms=123,
        )

    def test_build_audit_row_shape_and_truncation(self):
        row = bon.build_audit_row(self._result(), "user1", "sess1", "fen1")
        assert row["user_id"] == "user1" and row["session_id"] == "sess1"
        assert row["fen"] == "fen1" and row["n"] == 2
        assert row["selected_idx"] == 1 and row["fallback_reason"] is None
        assert row["latency_ms"] == 123
        assert row["judge"]["choice"] == 1
        assert len(row["candidates"]) == 2
        c0 = row["candidates"][0]
        assert set(c0) == {"idx", "engine_score", "engine_status", "text_truncated"}
        assert len(c0["text_truncated"]) == bon.AUDIT_TEXT_CAP   # truncated to cap

    def test_write_audit_no_creds_is_noop(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        with patch("src.bestofn.httpx.post") as post:
            t = bon.write_audit(self._result(), "u", "s", "f")
            t.join(timeout=2)
        post.assert_not_called()

    def test_write_audit_posts_row(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://db")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        with patch("src.bestofn.httpx.post", return_value=resp) as post:
            t = bon.write_audit(self._result(), "u", "s", "f")
            t.join(timeout=2)
        post.assert_called_once()
        url = post.call_args[0][0]
        assert url.endswith("/rest/v1/coach_bestofn_audit")
        sent = post.call_args[1]["json"]
        assert sent["selected_idx"] == 1 and sent["n"] == 2


# ── Flag-off no-op (Design rule 1) ───────────────────────────────────────


@pytest.mark.unit
class TestFlagOff:
    def test_flag_defaults_off(self):
        import src.config as config

        assert config.COACH_BESTOFN is False

    def test_clamp_n(self):
        assert bon.clamp_n(0) == 1
        assert bon.clamp_n(1) == 1
        assert bon.clamp_n(3) == 3
        assert bon.clamp_n(10) == bon.MAX_N
        assert bon.clamp_n("nope") == bon.DEFAULT_N
