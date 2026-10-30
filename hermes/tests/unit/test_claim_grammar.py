"""The parser of the relation checker (src/claim_grammar.py, WP-A of plan 30.10).

The cases in tests/fixtures/relations/grammar_cases.json are examples of classes, not sentences to special-case:
  positive  the claim each sentence makes (relation, subject, objects, the position its words point at);
  negative  sentences that make no checkable claim (idioms, rules, hypotheticals, yes/no questions, ambiguous
            pronouns, the NOT-BOARD-CHECKABLE eval rows): no claim, or only claims whose Pos.at is 'skip'.
The coverage test measures the plan's WP-A acceptance against recorded_claims.json with the reference judge.
"""
from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path

import pytest

from src import claim_grammar as cg
from src.claim_types import ALL_RELATIONS, Claim, Pos

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "relations"
CASES = json.loads((FIX / "grammar_cases.json").read_text())


def _full(obj):
    """A claim as nested dicts with every field (defaults too), sides as booleans."""
    return dataclasses.asdict(obj)


def _match(pattern, value) -> bool:
    if isinstance(pattern, dict):
        return isinstance(value, dict) and all(k in value and _match(v, value[k]) for k, v in pattern.items())
    if isinstance(pattern, list):
        return isinstance(value, (list, tuple)) and len(pattern) == len(value) and all(
            _match(p, v) for p, v in zip(pattern, value))
    return pattern == value


def _extract(case) -> list[Claim]:
    state: dict = {}
    for s in case.get("prev", []):
        cg.extract(s, state)
    return cg.extract(case["text"], state, case.get("language"))


@pytest.mark.parametrize("case", CASES["positive"], ids=[c["id"] for c in CASES["positive"]])
def test_positive(case):
    claims = _extract(case)
    got = [_full(c) for c in claims]
    for pattern in case["expect"]:
        assert any(_match(pattern, g) for g in got), (
            f"{case['id']}: no claim matches {pattern}\n got: {[c.to_dict() for c in claims]}")


@pytest.mark.parametrize("case", CASES["negative"], ids=[c["id"] for c in CASES["negative"]])
def test_negative(case):
    claims = [c for c in _extract(case) if c.pos.at != "skip"]
    if case.get("none"):
        assert not claims, f"{case['id']}: {[c.to_dict() for c in claims]}"
    for pattern in case.get("forbid", []):
        assert not any(_match(pattern, _full(c)) for c in claims), f"{case['id']}: {[c.to_dict() for c in claims]}"


def test_negatives_cover_at_least_40_not_checkable_rows():
    assert sum(c["source"] == "eval_not_checkable" for c in CASES["negative"]) >= 40


def test_every_claim_is_a_valid_schema_value():
    """Each claim round-trips through the frozen schema and names a relation the judges know."""
    for case in CASES["positive"] + CASES["negative"]:
        for c in _extract(case):
            assert c.rel in ALL_RELATIONS
            assert c.source == "grammar"
            assert Claim.from_dict(json.loads(json.dumps(c.to_dict()))) == c


def test_state_holds_only_immutable_values():
    state: dict = {}
    cg.extract("Слон на a4 пока держится только потому, что его защищает конь f3.", state)
    cg.extract("Посмотри на пешку чёрных на f5 — из-за неё ослабел пункт e6.", state)

    def immutable(v):
        if isinstance(v, (str, int, float, bool, type(None))):
            return True
        return isinstance(v, tuple) and all(immutable(x) for x in v)

    assert state and all(immutable(v) for v in state.values())
    assert set(state) <= {cg.FOCUS_KEY, cg.SQUARES_KEY}


def test_pronoun_from_the_sentence_before():
    state: dict = {}
    cg.extract("Твой конь стоит на f6.", state)
    claims = cg.extract("Он ничем не защищён.", state)
    assert [c.to_dict()["objs"][0]["sq"] for c in claims if c.rel == "undefended"] == ["f6"]


def test_pronoun_with_two_candidates_is_skipped():
    state: dict = {}
    claims = cg.extract("Конь на c3 и конь на f3 стоят рядом, и он защищает пешку e4.", state)
    assert all(c.pos.at == "skip" for c in claims if c.rel == "defend")


def test_noun_between_piece_and_pronoun_makes_it_ambiguous():
    """«…слон смотрит на f7 — это уязвимый пункт, ведь его прикрывает только король»: «его» may be the point."""
    claims = cg.extract("Твой слон с c4 смотрит на f7 — это самый уязвимый пункт у чёрных, ведь его прикрывает только король.", {})
    assert not [c for c in claims if c.rel == "defend" and c.pos.at != "skip"]


def test_then_continues_the_line_before():
    claims = cg.extract("Тогда чёрный слон бьёт твою пешку b6.", {})
    assert claims and claims[0].pos.at == "then"


def test_told_move_alternatives_and_line():
    claims = cg.extract("После Kc2 вы прячете короля, а слон на a2 держит поле b1.", {})
    hold = [c for c in claims if c.rel == "hold"]
    assert hold and hold[0].pos.at == "after" and [m.to for m in hold[0].pos.moves] == ["c2"]


def test_future_without_a_move_is_skipped_and_a_plan_is_geometry():
    assert all(c.pos.at == "skip" for c in cg.extract("Конь потом будет атаковать f7.", {}))
    plan = cg.extract("План простой: фианкетто, и слон на g2 будет бить по b7.", {})
    assert [(c.rel, c.pos.at) for c in plan] == [("plan_reach", "plan")]


def test_kazakh_is_out_of_scope():
    assert cg.extract("Ат f3 e5 сарбазына шабуылдайды.", {}, "kk") == []


def test_sentence_without_a_relation_word_only_remembers():
    state: dict = {}
    assert cg.extract("Ход за тобой, позиция равная.", state) == []
    assert cg.extract("Твой конь стоит на f6.", state) == []
    assert state[cg.FOCUS_KEY]


def _recorded_false_keys():
    """The recorded claims (llm extractions) the reference judge finds false, per eval row: the plan's measure
    of WP-A (§4: ≥ 30 of the 49 false claims matched by the grammar)."""
    from tests.support import ref_judge as rj

    rows = json.loads((FIX / "eval_set.json").read_text())["rows"]
    recorded = json.loads((FIX / "recorded_claims.json").read_text())["eval"]
    out = []
    for r in rows:
        env = rj.env_for(r["fen"], r["shown_board"], r["game_moves"], r["student"], r["question"])
        text = (r.get("prev") or "")[-300:] + " " + r["sentence"] + " " + (r["question"] or "")
        for c in recorded.get(str(r["row"]), []):
            claim = Claim.from_dict(c)
            if rj.verify(claim, env, text).status == "false":
                out.append((r, claim))
    return out


_FAMILY = {"attack": "A", "aim": "A", "chase": "A", "threat": "A", "attacked": "A", "plan_reach": "A", "hold": "A",
           "defend": "D", "undefended": "D", "pins": "P", "pinned": "P", "pin_after": "P", "locked_by": "L",
           "locked": "L", "blocks": "L", "capture_with": "C", "can_capture": "C"}


def _facts(c: Claim) -> set:
    """What a claim states, comparable across the two schemas: locked_by(B c1, [d3, h3]) = locked(c1) + blocks(d3 →
    c1) + blocks(h3 → c1); a move subject of «Nc3 или Nd2» stands on each alternative's destination; «держит» (hold,
    colour-free) is the attack or the defence family."""
    if c.rel == "locked_by":
        s = c.subj.sq if c.subj else None
        return {("L", s, frozenset())} | {("L", o.sq, frozenset([s])) for o in c.objs}
    subjs = {c.subj.sq if c.subj else None}
    if c.subj is not None and c.subj.sq is None and c.pos.moves:
        subjs = {p.moves[-1].to for p in (c.pos, *c.pos.alts) if p.moves and p.moves[-1].piece == c.subj.piece}
    fams = {"A", "D"} if c.rel == "hold" else {_FAMILY.get(c.rel, c.rel)}
    return {(f, s, frozenset(o.sq for o in c.objs if o.sq)) for f in fams for s in subjs}


def test_false_claims_of_the_eval_set_are_read():
    """Acceptance (plan §4 WP-A): the grammar finds ≥ 30 of the recorded false claims (same relation family, same
    subject and object squares); the FALSE rows hold 45 of the 49."""
    from src.game_intent import spoken_squares

    pairs = _recorded_false_keys()
    assert len(pairs) == 49
    matched = 0
    for r, claim in pairs:
        mine = [c for c in cg.extract(spoken_squares(r["sentence"]), {}) if c.pos.at != "skip"]
        if any(_facts(claim) & _facts(c) for c in mine):
            matched += 1
    assert matched >= 30, matched


def test_not_checkable_rows_rarely_yield_a_claim():
    """Acceptance: at most 10 of the 81 NOT-BOARD-CHECKABLE rows yield a non-skip claim."""
    from src.game_intent import spoken_squares

    rows = json.loads((FIX / "eval_set.json").read_text())["rows"]
    n = sum(any(c.pos.at != "skip" for c in cg.extract(spoken_squares(r["sentence"]), {}))
            for r in rows if r["label"] == "NOT-BOARD-CHECKABLE")
    assert n <= 10, n


def test_extract_is_fast():
    """The corpus p99 is measured by scripts (≤ 0.5 ms on 7,045 sentences); here a coarse guard on the fixtures."""
    texts = [c["text"] for c in CASES["positive"] + CASES["negative"]]
    for t in texts:  # warm
        cg.extract(t, {})
    times = []
    for t in texts * 3:
        t0 = time.perf_counter()
        cg.extract(t, {})
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    assert times[int(0.99 * len(times))] < 5.0


def test_pos_default_is_now():
    claims = cg.extract("Конь на f6 атакует пешку e4.", {})
    assert claims and claims[0].pos == Pos()
