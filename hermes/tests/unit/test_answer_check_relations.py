"""The relation checker's hook in the answer check (src/answer_check_relations.py, plan 30.10 WP-0): the mode
switch, shadow recording, fail-open, the claim cap, and the state a cut sentence leaves behind."""
import importlib
import os

import chess
import pytest

from src import answer_check_relations as acr
from src import claim_grammar, claim_judge, claim_rules, claim_scene, config
from src.answer_check import CheckContext, check_sentence
from src.claim_types import BoardSet, Claim, Ref, Verdict

CLEAN = "Это хорошая позиция для спокойного развития."  # nothing the legacy checks flag
ISSUE = "on the board now: Black's knight on f6 attacks d5, e4, g4, h5 — not d4"


def _claim(sq="d4"):
    return Claim(rel="attack", subj=Ref(sq="f6", piece="N"), objs=(Ref(sq=sq),))


@pytest.fixture
def fake(monkeypatch):
    """One claim per sentence, judged false; records the calls."""
    seen = {"extract": 0, "judge": 0, "remember": []}

    def extract(text, ctx, state):
        seen["extract"] += 1
        return [_claim()]

    def judge(claim, ctx, state):
        seen["judge"] += 1
        return Verdict("false", "on the board now", "Black's knight on f6 attacks d5, e4, g4, h5 — not d4")

    def remember(text, claims, ctx, state):
        seen["remember"].append(text)
        state["last"] = text

    monkeypatch.setattr(acr, "extract_claims", extract)
    monkeypatch.setattr(acr, "judge_claim", judge)
    monkeypatch.setattr(acr, "remember", remember)
    return seen


def _ctx():
    return CheckContext.from_fens([chess.STARTING_FEN])


def test_the_merged_modules_find_and_judge():
    """After the merge of WP-A/B/D (30.10) the stubs are real: the parser finds the claim, the rules have judges, the
    resolver builds the board, and the judge decides on it (a false claim on the st4 board is false)."""
    ctx = CheckContext.from_fens(["rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 2"])
    got = claim_grammar.extract("Конь f6 нападает на d4.", {}, "ru")
    assert [c.rel for c in got] == ["attack"]
    assert claim_rules.RULE_JUDGES
    boards = claim_scene.boards_for(got[0], ctx, {})
    assert boards is not None and boards.primary is not None
    assert claim_judge.decide(got[0], boards, ctx).status == "false"
    assert claim_scene.remember("x", [], ctx, {}) is None


def test_with_the_stubs_every_mode_leaves_the_answer_check_as_it_was(monkeypatch):
    sentences = [CLEAN, "Конь на g1 атакует пешку e5.", "Слон c4 нападает на f7."]
    got = {}
    for mode in ("off", "shadow", "on"):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", mode)
        ctx = _ctx()
        got[mode] = [check_sentence(s, ctx) for s in sentences]
        assert ctx.relation_shadow == []
    assert got["off"] == got["shadow"] == got["on"]


@pytest.mark.parametrize("raw, mode", [("off", "off"), ("0", "off"), ("", "off"), ("shadow", "shadow"), ("on", "on"),
                                       ("1", "on"), (" ON ", "on"), ("maybe", "shadow")])
def test_mode_is_read_at_call_time(monkeypatch, raw, mode):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", raw)
    assert acr.mode() == mode


def test_default_mode_is_on():
    saved = os.environ.pop("COACH_RELATION_CHECK", None)
    try:
        assert importlib.reload(config).COACH_RELATION_CHECK == "on"
        os.environ["COACH_RELATION_CHECK"] = "Shadow"
        assert importlib.reload(config).COACH_RELATION_CHECK == "shadow"
    finally:
        os.environ.pop("COACH_RELATION_CHECK", None)
        if saved is not None:
            os.environ["COACH_RELATION_CHECK"] = saved
        importlib.reload(config)


def test_off_does_not_run(monkeypatch, fake):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "off")
    ctx = _ctx()
    assert check_sentence(CLEAN, ctx) == []
    assert fake["extract"] == 0 and ctx.relation_shadow == [] and ctx.relation_stats == {}


def test_shadow_records_and_returns_nothing(monkeypatch, fake):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    ctx = _ctx()
    assert check_sentence(CLEAN, ctx) == []
    assert ctx.relation_shadow == [(CLEAN, [ISSUE])]
    assert ctx.relation_stats["calls"] == 1 and ctx.relation_stats["flags"] == 1 and ctx.relation_stats["claims"] == 1
    assert ctx.relation_state == {"last": CLEAN}  # not cut: what it remembered stays


def test_on_cuts_the_sentence(monkeypatch, fake):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    ctx = _ctx()
    assert check_sentence(CLEAN, ctx) == [ISSUE]
    assert ctx.relation_shadow == []


def test_shadow_records_what_on_returns(monkeypatch, fake):
    issues = {}
    for mode in ("shadow", "on"):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", mode)
        ctx = _ctx()
        on = acr.relation_issues(CLEAN, ctx, [])
        issues[mode] = on or [i for _, iss in ctx.relation_shadow for i in iss]
    assert issues["shadow"] == issues["on"] == [ISSUE]


def test_a_cut_sentence_leaves_the_relation_state_unchanged(monkeypatch, fake):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    ctx = _ctx()
    ctx.relation_state = {"antecedent": ("N", "f6")}
    assert check_sentence(CLEAN, ctx) == [ISSUE]  # cut by the relation check
    assert fake["remember"] == [CLEAN]  # it did remember the sentence…
    assert ctx.relation_state == {"antecedent": ("N", "f6")}  # …and the cut took it back
    # cut by a legacy check alone: the same
    monkeypatch.setattr(acr, "judge_claim", lambda claim, ctx, state: Verdict("true"))
    issues = check_sentence("Конь на g1 атакует пешку e5.", ctx)
    assert issues and ISSUE not in issues
    assert ctx.relation_state == {"antecedent": ("N", "f6")}
    # a sentence shown keeps what it remembered
    assert check_sentence(CLEAN, ctx) == []
    assert ctx.relation_state == {"antecedent": ("N", "f6"), "last": CLEAN}


def test_fail_open(monkeypatch, fake):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")

    def broken(text, ctx, state):
        raise RuntimeError("parser bug")

    monkeypatch.setattr(acr, "extract_claims", broken)
    ctx = _ctx()
    assert check_sentence(CLEAN, ctx) == []
    assert ctx.relation_stats["errors"] == 1
    # one claim's judge failing hides neither the others nor the sentence's other issues
    monkeypatch.setattr(acr, "extract_claims", lambda text, ctx, state: [_claim("e5"), _claim("d4")])

    def judge(claim, ctx, state):
        if claim.objs[0].sq == "e5":
            raise ValueError("judge bug")
        return Verdict("false", "", "the knight on f6 does not attack d4")

    monkeypatch.setattr(acr, "judge_claim", judge)
    ctx = _ctx()
    assert check_sentence(CLEAN, ctx) == ["the knight on f6 does not attack d4"]
    assert ctx.relation_stats["errors"] == 1
    # remember failing: counted, the verdicts stand
    monkeypatch.setattr(acr, "remember", lambda *a: 1 / 0)
    ctx = _ctx()
    assert check_sentence(CLEAN, ctx) == ["the knight on f6 does not attack d4"]
    assert ctx.relation_stats["errors"] == 2


def test_at_most_eight_claims_and_undecided_or_unresolved_is_silent(monkeypatch, fake):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.setattr(acr, "extract_claims", lambda text, ctx, state: [_claim()] * 12)
    verdicts = iter([None, Verdict("undecided"), Verdict("true")] + [Verdict("false", "", "x")] * 9)
    judged = []

    def judge(claim, ctx, state):
        judged.append(claim)
        return next(verdicts)

    monkeypatch.setattr(acr, "judge_claim", judge)
    ctx = _ctx()
    assert check_sentence(CLEAN, ctx) == ["x"]  # five false verdicts, one issue after de-duplication
    assert len(judged) == acr.MAX_CLAIMS == 8


def test_the_issue_is_one_line_of_at_most_220_characters():
    v = Verdict("false", "after 4.e5", "White's pawn on e5 attacks d6 and f6\n— " + "not Black's knight on g8 " * 20)
    line = acr.issue_text(_claim(), v)
    assert line.startswith("after 4.e5: White's pawn on e5 attacks d6 and f6 — not")
    assert "\n" not in line and len(line) <= 220
    assert acr.issue_text(_claim(), Verdict("false")) == "the attack claim is not true on the board"


def test_the_voice_check_seeds_the_relation_state_from_the_answer_so_far(monkeypatch, fake):
    """/api/coach/voice/check replays the earlier sentences on its context (server._replay_previous): the relation
    checker sees them as the text gate does — no extra field from the site (lead's ruling, 30.10)."""
    from src import server

    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    ctx = _ctx()
    server._replay_previous(ctx, "Первое предложение про центр. Второе предложение про фланг.")
    assert [t.strip() for t in fake["remember"]] == ["Первое предложение про центр.", "Второе предложение про фланг."]
    assert ctx.relation_state["last"].strip() == "Второе предложение про фланг."
