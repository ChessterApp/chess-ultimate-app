"""Unit tests for the CL Phase-2 engine-verified coaching playbook.

Fully offline — every boundary (Reflector LLM, Supabase REST, Stockfish engine)
is mocked. Covers the Reflector JSON gate + caps, the Generator candidate
heuristic, engine verification (verified / unverified / refuted), the Curator
dedupe/merge + size cap + audit, and the injection relevance/render/TTL-cache.
"""

from unittest.mock import patch

import pytest

import src.playbook as pb


# ── Reflector: parse + gate + caps ───────────────────────────────────────


@pytest.mark.unit
class TestParseAndGate:
    def test_parse_entries_object_form(self):
        raw = '{"entries": [{"title": "Fork"}, {"title": "Pin"}]}'
        assert [e["title"] for e in pb.parse_entries(raw)] == ["Fork", "Pin"]

    def test_parse_entries_array_form(self):
        assert len(pb.parse_entries('[{"a": 1}, {"b": 2}]')) == 2

    def test_parse_rejects_non_json(self):
        assert pb.parse_entries("here you go: {...}") == []
        assert pb.parse_entries("```json\n{}\n```") == []
        assert pb.parse_entries(None) == []

    def test_gate_accepts_and_caps(self):
        entry = pb.gate_entry({
            "title": "X" * 200,
            "theme": "TACTIC",
            "tags": ["fork", "pin", "skewer", "extra", "fork"],
            "advice": "A" * 900,
            "example_fen": "8/8/8/4k3/8/8/8/4K2R w - - 0 1",
            "example_line": "L" * 300,
            "generalizable": True,
            "confidence": 0.8,
        })
        assert len(entry["title"]) == pb.TITLE_MAX
        assert len(entry["advice"]) == pb.ADVICE_MAX
        assert len(entry["example_line"]) == pb.EXAMPLE_LINE_MAX
        assert entry["tags"] == ["fork", "pin", "skewer"]   # capped + deduped
        assert entry["theme"] == "tactic"                    # lowercased

    def test_gate_drops_non_generalizable(self):
        assert pb.gate_entry({
            "title": "t", "theme": "tactic", "advice": "a",
            "generalizable": False, "confidence": 0.9,
        }) is None

    def test_gate_drops_low_confidence(self):
        assert pb.gate_entry({
            "title": "t", "theme": "tactic", "advice": "a",
            "generalizable": True, "confidence": 0.5,
        }) is None

    def test_gate_drops_missing_required_field(self):
        assert pb.gate_entry({
            "title": "t", "theme": "", "advice": "a",
            "generalizable": True, "confidence": 0.9,
        }) is None

    def test_gate_drops_bad_confidence(self):
        assert pb.gate_entry({
            "title": "t", "theme": "tactic", "advice": "a",
            "generalizable": True, "confidence": "high",
        }) is None


# ── Generator: candidate heuristics ──────────────────────────────────────


@pytest.mark.unit
class TestGenerator:
    def test_is_substantive_by_length(self):
        assert pb.is_substantive({"role": "assistant", "content": "x" * 250})
        assert not pb.is_substantive({"role": "assistant", "content": "short"})

    def test_is_substantive_by_engine_or_fen(self):
        assert pb.is_substantive({"role": "assistant", "content": "hi", "check_ran": True})
        assert pb.is_substantive({"role": "assistant", "content": "hi", "fen": "..."})

    def test_is_substantive_skips_user_role(self):
        assert not pb.is_substantive({"role": "user", "content": "x" * 500})

    def test_build_candidates_pairs_user_by_turn(self):
        messages = [
            {"role": "user", "content": "why is this losing?", "turn_id": "t1"},
            {"role": "assistant", "content": "c" * 250, "turn_id": "t1"},
            {"role": "assistant", "content": "too short", "turn_id": "t2"},
        ]
        cands = pb.build_candidates(messages)
        assert len(cands) == 1
        assert cands[0]["turn_id"] == "t1"
        assert cands[0]["user_text"] == "why is this losing?"


# ── Curator: engine verification (the gatekeeper) ────────────────────────


class _FakeVerdict:
    def __init__(self, status, claims):
        self._d = {"status": status, "claims": claims}

    def to_dict(self):
        return dict(self._d)


@pytest.mark.unit
class TestVerify:
    def test_no_fen_is_unverified(self):
        verdict, ev = pb.verify_entry({"advice": "play Nf3", "example_fen": None})
        assert verdict == pb.UNVERIFIED
        assert ev["reason"] == "no_example_fen"

    def test_refuted_on_illegal_move(self):
        fake = lambda fen, text: _FakeVerdict("ok", [
            {"kind": "illegal_move", "verdict": "illegal"}
        ])
        verdict, ev = pb.verify_entry(
            {"advice": "play Ke2", "example_fen": "F", "example_line": "Ke2"},
            evaluate_fn=fake,
        )
        assert verdict == pb.REFUTED

    def test_refuted_on_disagreeing_eval(self):
        fake = lambda fen, text: _FakeVerdict("ok", [
            {"kind": "eval_claim", "verdict": "disagree"}
        ])
        verdict, _ = pb.verify_entry(
            {"advice": "white is winning", "example_fen": "F"}, evaluate_fn=fake
        )
        assert verdict == pb.REFUTED

    def test_verified_when_claims_hold(self):
        fake = lambda fen, text: _FakeVerdict("ok", [
            {"kind": "recommended_move", "verdict": "best"}
        ])
        verdict, _ = pb.verify_entry(
            {"advice": "play Nf3", "example_fen": "F", "example_line": "Nf3"},
            evaluate_fn=fake,
        )
        assert verdict == pb.VERIFIED

    def test_unverified_when_engine_skipped(self):
        fake = lambda fen, text: _FakeVerdict("skipped", [])
        verdict, _ = pb.verify_entry({"advice": "general", "example_fen": "F"}, evaluate_fn=fake)
        assert verdict == pb.UNVERIFIED

    def test_unverified_when_ok_but_no_claims(self):
        fake = lambda fen, text: _FakeVerdict("ok", [])
        verdict, _ = pb.verify_entry({"advice": "general", "example_fen": "F"}, evaluate_fn=fake)
        assert verdict == pb.UNVERIFIED

    def test_engine_exception_is_failopen(self):
        def boom(fen, text):
            raise RuntimeError("engine crashed")
        verdict, ev = pb.verify_entry({"advice": "x", "example_fen": "F"}, evaluate_fn=boom)
        assert verdict == pb.UNVERIFIED
        assert ev["reason"] == "engine_error"


# ── Curator: dedupe / merge ──────────────────────────────────────────────


@pytest.mark.unit
class TestDedupe:
    def test_duplicate_by_normalized_title(self):
        a = {"title": "The Knight Fork!", "theme": "tactic", "tags": []}
        b = {"title": "the knight fork", "theme": "tactic", "tags": []}
        assert pb.is_duplicate(a, b)

    def test_not_duplicate_across_themes(self):
        a = {"title": "Knight fork", "theme": "tactic", "tags": ["fork"]}
        b = {"title": "Knight fork", "theme": "endgame", "tags": ["fork"]}
        assert not pb.is_duplicate(a, b)

    def test_duplicate_by_tag_overlap(self):
        a = {"title": "Trade into a won ending", "theme": "endgame", "tags": ["rook", "activity"]}
        b = {"title": "Activate the rook", "theme": "endgame", "tags": ["rook", "activity"]}
        assert pb.is_duplicate(a, b)

    def test_pick_better_prefers_verified(self):
        new = {"title": "t", "theme": "tactic"}
        existing = {"title": "t", "theme": "tactic", "verified": False}
        assert pb.pick_better(new, pb.VERIFIED, existing) == "new"
        existing_verified = {"title": "t", "theme": "tactic", "verified": True}
        assert pb.pick_better(new, pb.UNVERIFIED, existing_verified) == "existing"


# ── Curator: full orchestration (accept / reject / merge / cap) ──────────


@pytest.mark.unit
class TestCurate:
    def _entry(self, **kw):
        base = {"title": "Fork with the knight", "theme": "tactic",
                "tags": ["fork"], "advice": "look for knight forks",
                "example_fen": None, "example_line": None, "confidence": 0.9}
        base.update(kw)
        return base

    def test_reject_refuted_writes_audit(self):
        fake = lambda fen, text: _FakeVerdict("ok", [{"kind": "illegal_move", "verdict": "illegal"}])
        active = []
        with patch.object(pb, "write_audit") as audit, \
             patch.object(pb, "insert_entry") as ins:
            result = pb.curate_entry(
                self._entry(example_fen="F", example_line="Ke2"),
                active, ["t1"], execute=True, evaluate_fn=fake,
            )
        assert result["action"] == "reject"
        assert result["reason"] == "engine_refuted"
        ins.assert_not_called()
        audit.assert_called_once()
        assert audit.call_args.args[0] == "reject"
        assert audit.call_args.kwargs["engine_verdict"] == pb.REFUTED
        assert active == []

    def test_accept_inserts_and_audits(self):
        fake = lambda fen, text: _FakeVerdict("skipped", [])
        active = []
        with patch.object(pb, "insert_entry", return_value=42) as ins, \
             patch.object(pb, "write_audit") as audit:
            result = pb.curate_entry(self._entry(), active, ["t1"], execute=True, evaluate_fn=fake)
        assert result["action"] == "accept"
        assert result["verified"] is False        # unverifiable → verified=false
        ins.assert_called_once()
        assert audit.call_args.args[0] == "accept"
        assert len(active) == 1 and active[0]["id"] == 42

    def test_accept_marks_verified(self):
        fake = lambda fen, text: _FakeVerdict("ok", [{"kind": "recommended_move", "verdict": "best"}])
        active = []
        with patch.object(pb, "insert_entry", return_value=1), \
             patch.object(pb, "write_audit"):
            result = pb.curate_entry(
                self._entry(example_fen="F", example_line="Nf3"),
                active, ["t1"], execute=True, evaluate_fn=fake,
            )
        assert result["verified"] is True

    def test_duplicate_rejected(self):
        fake = lambda fen, text: _FakeVerdict("skipped", [])
        active = [{"id": 7, "title": "Fork with the knight", "theme": "tactic",
                   "tags": ["fork"], "verified": True}]
        with patch.object(pb, "insert_entry") as ins, patch.object(pb, "write_audit") as audit:
            result = pb.curate_entry(self._entry(), active, ["t1"], execute=True, evaluate_fn=fake)
        assert result["action"] == "reject"
        assert result["reason"] == "duplicate"
        ins.assert_not_called()
        assert audit.call_args.args[0] == "reject"

    def test_duplicate_merge_when_better_verified(self):
        fake = lambda fen, text: _FakeVerdict("ok", [{"kind": "recommended_move", "verdict": "best"}])
        active = [{"id": 7, "title": "Fork with the knight", "theme": "tactic",
                   "tags": ["fork"], "verified": False}]
        with patch.object(pb, "insert_entry", return_value=99) as ins, \
             patch.object(pb, "retire_entry") as ret, \
             patch.object(pb, "write_audit") as audit:
            result = pb.curate_entry(
                self._entry(example_fen="F", example_line="Nf3"),
                active, ["t1"], execute=True, evaluate_fn=fake,
            )
        assert result["action"] == "merge"
        ret.assert_called_once_with(7)
        ins.assert_called_once()
        assert audit.call_args.args[0] == "merge"
        assert len(active) == 1 and active[0]["id"] == 99

    def test_size_cap_rejects(self):
        fake = lambda fen, text: _FakeVerdict("skipped", [])
        active = [{"id": i, "title": f"e{i}", "theme": "endgame", "tags": []}
                  for i in range(pb.MAX_ACTIVE_ENTRIES)]
        with patch.object(pb, "insert_entry") as ins, patch.object(pb, "write_audit") as audit:
            result = pb.curate_entry(self._entry(), active, ["t1"], execute=True, evaluate_fn=fake)
        assert result["action"] == "reject"
        assert result["reason"] == "playbook_full"
        ins.assert_not_called()
        assert audit.call_args.args[0] == "reject"

    def test_dry_run_writes_nothing(self):
        fake = lambda fen, text: _FakeVerdict("skipped", [])
        active = []
        with patch.object(pb, "insert_entry") as ins, patch.object(pb, "write_audit") as audit:
            result = pb.curate_entry(self._entry(), active, ["t1"], execute=False, evaluate_fn=fake)
        assert result["action"] == "accept"
        ins.assert_not_called()
        audit.assert_not_called()
        assert len(active) == 1   # still tracked in-memory for later dedupe


# ── Injection: relevance / render / TTL cache ────────────────────────────


@pytest.mark.unit
class TestTurnContext:
    def test_fen_phase(self):
        assert pb.fen_phase("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1") == "opening"
        assert pb.fen_phase("8/8/8/4k3/8/8/8/4K2R w - - 0 1") == "endgame"
        assert pb.fen_phase(None) is None
        assert pb.fen_phase("not a fen") == "endgame"   # no piece letters → 0 pieces

    def test_build_turn_context(self):
        class _P:
            weaknesses = ["misses knight forks"]
        ctx = pb.build_turn_context(
            board_fen="8/8/8/4k3/8/8/8/4K2R w - - 0 1",
            move_history=["e4", "e5", "Nf3"],
            user_profile=_P(),
        )
        assert ctx["theme"] == "endgame"
        assert "misses knight forks" in ctx["tags"]
        assert "nf3" in ctx["keywords"]


@pytest.mark.unit
class TestInjection:
    def test_relevance_theme_and_tags(self):
        entry = {"theme": "tactic", "tags": ["fork", "pin"], "verified": True}
        high = pb.relevance_score(entry, {"theme": "tactic", "tags": ["fork"]})
        low = pb.relevance_score(entry, {"theme": "endgame", "tags": ["king"]})
        assert high > low
        assert low == 0

    def test_select_drops_irrelevant_and_caps_k(self):
        entries = [
            {"title": "A", "theme": "tactic", "tags": ["fork"], "advice": "a", "verified": True},
            {"title": "B", "theme": "tactic", "tags": ["fork"], "advice": "b", "verified": False},
            {"title": "C", "theme": "endgame", "tags": ["king"], "advice": "c"},
        ]
        selected = pb.select_entries(entries, {"theme": "tactic", "tags": ["fork"]}, k=3)
        titles = [e["title"] for e in selected]
        assert "C" not in titles              # zero relevance dropped
        assert titles[0] == "A"               # verified ranks first on a tie

    def test_render_marks_verified_and_caps(self):
        entries = [
            {"title": "Fork", "advice": "x" * 50, "verified": True},
            {"title": "Pin", "advice": "y" * 50, "verified": False},
        ]
        block = pb.render_playbook_block(entries, cap=1000)
        assert block.startswith("## Coaching playbook (engine-verified)")
        assert "[✓] Fork" in block
        assert "[~] Pin" in block

    def test_render_hard_cap(self):
        entries = [{"title": f"t{i}", "advice": "z" * 200, "verified": True} for i in range(10)]
        block = pb.render_playbook_block(entries, cap=pb.PLAYBOOK_BLOCK_CAP)
        assert len(block) <= pb.PLAYBOOK_BLOCK_CAP

    def test_render_empty(self):
        assert pb.render_playbook_block([]) == ""
        assert pb.render_playbook_block([{"title": "", "advice": ""}]) == ""

    def test_ttl_cache_hits_then_refreshes(self):
        pb.clear_playbook_cache()
        rows_v1 = [{"title": "A", "advice": "a"}]
        rows_v2 = [{"title": "B", "advice": "b"}]
        with patch.object(pb, "load_active_entries", side_effect=[rows_v1, rows_v2]) as load:
            first = pb.get_cached_active_entries(ttl=300)
            second = pb.get_cached_active_entries(ttl=300)   # cache hit, no reload
            assert first == rows_v1 and second == rows_v1
            assert load.call_count == 1
            # Force expiry → next read reloads and picks up v2.
            pb._cache_expires_at = 0.0
            expired = pb.get_cached_active_entries(ttl=300)
            assert expired == rows_v2
            assert load.call_count == 2
        pb.clear_playbook_cache()

    def test_load_block_failopen(self):
        pb.clear_playbook_cache()
        with patch.object(pb, "load_active_entries", side_effect=RuntimeError("db down")):
            assert pb.load_playbook_block({"theme": "tactic"}) == ""
        pb.clear_playbook_cache()
