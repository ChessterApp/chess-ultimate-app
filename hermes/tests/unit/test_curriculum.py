"""Unit tests for the CL Phase-2 automatic curriculum (engine-measured).

Fully offline — every boundary (Supabase REST) is mocked. Covers blunder/solve
aggregation with defensive schema handling, the learnability scoring formula,
the target-difficulty frontier, missing-data degradation, cap enforcement, and
the injection render + 500-char cap + per-user TTL cache.
"""

from unittest.mock import patch

import pytest

import src.curriculum as cur


# ── Aggregation: engine-verified blunders ────────────────────────────────


@pytest.mark.unit
class TestAggregateBlunders:
    def test_counts_and_avg_cp_by_theme(self):
        insights = [
            {"blunders": [
                {"theme": "fork", "cp_loss": 200},
                {"theme": "fork", "cp_loss": 400},
            ]},
            {"blunders": [{"theme": "pin", "cp_loss": 300}]},
        ]
        agg = cur.aggregate_blunders(insights)
        assert agg["fork"]["blunder_count"] == 2
        assert agg["fork"]["avg_cp_loss"] == 300.0
        assert agg["pin"]["blunder_count"] == 1

    def test_falls_back_to_classification_when_theme_missing(self):
        agg = cur.aggregate_blunders([
            {"blunders": [{"classification": "Blunder", "cp_loss": 500}]},
        ])
        assert "blunder" in agg          # lowercased classification used as theme

    def test_missing_cp_loss_still_counts_but_not_averaged(self):
        agg = cur.aggregate_blunders([
            {"blunders": [{"theme": "endgame"}, {"theme": "endgame", "cp_loss": 100}]},
        ])
        assert agg["endgame"]["blunder_count"] == 2
        assert agg["endgame"]["avg_cp_loss"] == 100.0   # only the numeric one

    def test_blunders_as_json_string(self):
        agg = cur.aggregate_blunders([
            {"blunders": '[{"theme": "fork", "cp_loss": 250}]'},
        ])
        assert agg["fork"]["blunder_count"] == 1

    def test_empty_and_malformed_failopen(self):
        assert cur.aggregate_blunders([]) == {}
        assert cur.aggregate_blunders([{"blunders": "not json"}]) == {}
        assert cur.aggregate_blunders([{"blunders": [{"cp_loss": 10}]}]) == {}  # no theme


# ── Aggregation: puzzle solve rates (defensive schema) ───────────────────


@pytest.mark.unit
class TestSolveRates:
    def test_detect_theme_and_rating_keys(self):
        rows = [{"solved": True, "themes": "fork pin", "rating": 1500}]
        assert cur.detect_key(rows, cur.PUZZLE_THEME_KEYS) == "themes"
        assert cur.detect_key(rows, cur.PUZZLE_RATING_KEYS) == "rating"

    def test_detect_returns_none_when_absent(self):
        assert cur.detect_key([{"solved": True}], cur.PUZZLE_THEME_KEYS) is None

    def test_solve_rate_by_theme_multi_theme_string(self):
        attempts = [
            {"solved": True, "themes": "fork pin"},
            {"solved": False, "themes": "fork"},
        ]
        rates = cur.solve_rates_by_theme(attempts, "themes")
        assert rates["fork"] == 0.5     # 1/2
        assert rates["pin"] == 1.0      # 1/1

    def test_solve_rate_by_theme_list_field(self):
        attempts = [{"solved": True, "tags": ["endgame"]}]
        assert cur.solve_rates_by_theme(attempts, "tags") == {"endgame": 1.0}

    def test_no_theme_key_yields_empty(self):
        assert cur.solve_rates_by_theme([{"solved": True}], None) == {}

    def test_overall_solve_rate(self):
        assert cur.overall_solve_rate([{"solved": True}, {"solved": False}]) == 0.5
        assert cur.overall_solve_rate([]) is None


@pytest.mark.unit
class TestTargetDifficulty:
    def test_adaptive_without_rating_key(self):
        assert cur.compute_target_difficulty([{"solved": True}], None) == "adaptive"

    def test_picks_band_nearest_50pct(self):
        attempts = (
            [{"solved": True, "rating": 1000} for _ in range(3)]      # 100% @ ~1100
            + [{"solved": True, "rating": 1600} for _ in range(2)]    # 50% @ ~1700
            + [{"solved": False, "rating": 1600} for _ in range(2)]
        )
        assert cur.compute_target_difficulty(attempts, "rating") == "~1700"

    def test_adaptive_when_no_band_has_enough_attempts(self):
        assert cur.compute_target_difficulty(
            [{"solved": True, "rating": 1500}], "rating"
        ) == "adaptive"

    def test_non_numeric_rating_is_skipped(self):
        assert cur.compute_target_difficulty(
            [{"solved": True, "rating": "easy"} for _ in range(5)], "rating"
        ) == "adaptive"


# ── Scoring: learnability formula ─────────────────────────────────────────


@pytest.mark.unit
class TestScoring:
    def test_proximity_peaks_at_50pct(self):
        assert cur.proximity_to_50pct(0.5) == 1.0
        assert cur.proximity_to_50pct(0.95) == pytest.approx(0.1)   # clamped floor
        assert cur.proximity_to_50pct(0.0) == pytest.approx(0.1)
        assert cur.proximity_to_50pct(None) == 1.0                  # unknown → neutral 0.5

    def test_cp_loss_weight(self):
        assert cur.cp_loss_weight(300) == 1.0
        assert cur.cp_loss_weight(150) == pytest.approx(0.5)
        assert cur.cp_loss_weight(10) == pytest.approx(0.1)         # clamped floor
        assert cur.cp_loss_weight(None) == cur.NEUTRAL_CP_WEIGHT

    def test_ranking_near50_beats_easy_beats_lowblunder(self):
        """Spec P4 fixture: high-blunder+near-50% > high-blunder+95% > low-blunder."""
        blunder_agg = {
            "near50": {"blunder_count": 10, "avg_cp_loss": 250},
            "easy": {"blunder_count": 10, "avg_cp_loss": 250},
            "lowblunder": {"blunder_count": 1, "avg_cp_loss": 250},
        }
        solve_rates = {"near50": 0.5, "easy": 0.95, "lowblunder": 0.7}
        focus = cur.score_themes(blunder_agg, solve_rates)
        assert [f["theme"] for f in focus] == ["near50", "easy", "lowblunder"]
        assert focus[0]["score"] > focus[1]["score"] > focus[2]["score"]

    def test_theme_solve_rate_falls_back_to_overall(self):
        focus = cur.score_themes(
            {"fork": {"blunder_count": 5, "avg_cp_loss": 300}},
            solve_rates={},              # no theme-level rate
            overall_rate=0.5,
        )
        assert focus[0]["solve_rate"] == 0.5

    def test_unknown_solve_rate_is_neutral(self):
        focus = cur.score_themes({"fork": {"blunder_count": 5, "avg_cp_loss": 300}})
        assert focus[0]["solve_rate"] is None
        # neutral proximity (1.0) * full cp weight * norm freq 1.0
        assert focus[0]["score"] == 1.0

    def test_missing_cp_loss_uses_neutral_weight(self):
        focus = cur.score_themes({"fork": {"blunder_count": 5, "avg_cp_loss": None}})
        assert focus[0]["avg_cp_loss"] is None
        assert focus[0]["score"] == pytest.approx(cur.NEUTRAL_CP_WEIGHT)

    def test_empty_blunders_yields_no_focus(self):
        assert cur.score_themes({}) == []

    def test_caps_at_three_themes(self):
        agg = {f"t{i}": {"blunder_count": i + 1, "avg_cp_loss": 300} for i in range(6)}
        focus = cur.score_themes(agg)
        assert len(focus) == cur.MAX_FOCUS_THEMES

    def test_focus_dict_shape(self):
        focus = cur.score_themes(
            {"fork": {"blunder_count": 3, "avg_cp_loss": 250}},
            solve_rates={"fork": 0.5},
            target_difficulty="~1500",
        )[0]
        assert set(focus) == {
            "theme", "score", "blunder_count", "avg_cp_loss",
            "solve_rate", "target_difficulty", "rationale",
        }
        assert focus["target_difficulty"] == "~1500"
        assert isinstance(focus["rationale"], str) and focus["rationale"]


# ── compute_curriculum end-to-end (pure) ──────────────────────────────────


@pytest.mark.unit
class TestComputeCurriculum:
    def test_end_to_end_with_themes_and_ratings(self):
        insights = [{"blunders": [
            {"theme": "fork", "cp_loss": 300},
            {"theme": "fork", "cp_loss": 300},
            {"theme": "endgame", "cp_loss": 120},
        ]}]
        attempts = (
            [{"solved": True, "themes": "fork", "rating": 1500} for _ in range(2)]
            + [{"solved": False, "themes": "fork", "rating": 1500} for _ in range(2)]
        )
        result = cur.compute_curriculum(insights, attempts, since="2026-06-01")
        assert result["computed_from"]["blunders"] == 3
        assert result["computed_from"]["theme_key"] == "themes"
        assert result["computed_from"]["rating_key"] == "rating"
        themes = [f["theme"] for f in result["focus"]]
        assert "fork" in themes

    def test_degrades_without_puzzle_data(self):
        result = cur.compute_curriculum(
            [{"blunders": [{"theme": "fork", "cp_loss": 300}]}], attempts=[]
        )
        f = result["focus"][0]
        assert f["theme"] == "fork"
        assert f["solve_rate"] is None
        assert f["target_difficulty"] == "adaptive"

    def test_empty_inputs_yield_empty_focus(self):
        result = cur.compute_curriculum([], [])
        assert result["focus"] == []
        assert result["computed_from"]["blunders"] == 0


# ── Injection: render / cap / per-user TTL cache ─────────────────────────


@pytest.mark.unit
class TestInjection:
    def _focus(self, n=3):
        return [
            {"theme": f"theme{i}", "rationale": f"{i} blunders; solve rate 50%.",
             "score": 0.5, "target_difficulty": "adaptive"}
            for i in range(n)
        ]

    def test_render_block_shape(self):
        block = cur.render_curriculum_block(self._focus(2))
        assert block.startswith("## Training focus (engine-measured)")
        assert "theme0" in block and "theme1" in block
        assert "set_puzzle" in block

    def test_render_caps_to_three_themes(self):
        block = cur.render_curriculum_block(self._focus(6), cap=100000)
        # 6 provided but only MAX_FOCUS_THEMES rendered
        assert block.count("set_puzzle") == cur.MAX_FOCUS_THEMES

    def test_render_hard_cap_500(self):
        focus = [{"theme": f"t{i}", "rationale": "z" * 300, "score": 0.1}
                 for i in range(3)]
        block = cur.render_curriculum_block(focus)
        assert len(block) <= cur.CURRICULUM_BLOCK_CAP

    def test_render_empty(self):
        assert cur.render_curriculum_block([]) == ""
        assert cur.render_curriculum_block([{"theme": ""}]) == ""

    def test_ttl_cache_per_user_hits_then_refreshes(self):
        cur.clear_curriculum_cache()
        v1 = [{"theme": "a", "rationale": "r"}]
        v2 = [{"theme": "b", "rationale": "r"}]
        with patch.object(cur, "load_current_curriculum", side_effect=[v1, v2]) as load:
            first = cur.get_cached_curriculum("u1", ttl=300)
            second = cur.get_cached_curriculum("u1", ttl=300)   # cache hit
            assert first == v1 and second == v1
            assert load.call_count == 1
            cur._cache["u1"] = (0.0, v1)                        # force expiry
            expired = cur.get_cached_curriculum("u1", ttl=300)
            assert expired == v2
            assert load.call_count == 2
        cur.clear_curriculum_cache()

    def test_ttl_cache_is_keyed_by_user(self):
        cur.clear_curriculum_cache()
        with patch.object(cur, "load_current_curriculum",
                          side_effect=lambda uid: [{"theme": uid, "rationale": "r"}]) as load:
            a = cur.get_cached_curriculum("ua")
            b = cur.get_cached_curriculum("ub")
            assert a[0]["theme"] == "ua" and b[0]["theme"] == "ub"
            assert load.call_count == 2
        cur.clear_curriculum_cache()

    def test_load_block_failopen(self):
        cur.clear_curriculum_cache()
        with patch.object(cur, "load_current_curriculum", side_effect=RuntimeError("db down")):
            assert cur.load_curriculum_block("u1") == ""
        cur.clear_curriculum_cache()


# ── Supabase persistence (mocked) ─────────────────────────────────────────


@pytest.mark.unit
class TestPersistence:
    def test_persist_upserts_and_audits(self):
        result = {"focus": [{"theme": "fork"}], "computed_from": {"blunders": 1}}
        with patch.object(cur, "upsert_curriculum", return_value=True) as up, \
             patch.object(cur, "write_audit", return_value=True) as audit:
            ok = cur.persist_curriculum("u1", result)
        assert ok is True
        up.assert_called_once()
        audit.assert_called_once()
        # audit always fires (append-only ledger is the source of truth)
        assert audit.call_args.args[0] == "u1"

    def test_load_current_curriculum_no_creds_failopen(self):
        with patch.object(cur, "_supabase_creds", return_value=("", "")):
            assert cur.load_current_curriculum("u1") == []
