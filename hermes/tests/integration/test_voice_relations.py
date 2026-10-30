"""The relation checker on /api/coach/voice/check (plan 30.10, WP-C; lead's ruling: no new field from the site).

The browser sends the spoken sentence and ``previous`` — the earlier sentences of the answer — which the endpoint
replays through check_sentence on its context (server._replay_previous). The relation checker's pronoun and scene
state comes from that replay; without ``previous`` a pronoun has nothing to refer to and its claim is skipped.

Wiring tier: the claims come from a hand-written table (what a parser extracts; ``SAYS``) whose pronoun entry
resolves «он» only through ``ctx.relation_state`` — the state the replay leaves — and the reference judge judges them
on the board. Built tier: the real parser and judge, skipped until WP-A and WP-B are merged.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src import answer_check_relations as acr
from src import claim_grammar, claim_scene, config
from src.answer_check import CheckContext
from src.claim_types import Claim, Ref
from src.middleware.rate_limiter import rate_limiter

ST4 = "rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 2"  # 1.d4 Nf6 (st4, 29.10)
SPOKEN = "Конь эф шесть нападает на дэ четыре."
REL = "d4 (White pawn) is attacked by nothing"  # the reference judge's truth: the relation checker's issue
USER = {"X-User-Id": "voice-relations"}


def _knight_f6():
    return Ref(sq="f6", piece="N")


@pytest.fixture
def seams(monkeypatch):
    """«конь f6 …» names its piece; «он …» is the piece the sentence before named (``relation_state['it']``), and
    with no such sentence there is no claim. The reference judge on ctx.current."""
    from tests.support.ref_judge import env_for, verify

    seen = {"texts": [], "states": []}

    def extract(text, ctx, state):
        seen["texts"].append(text)
        seen["states"].append(dict(state))
        low = text.lower()
        subj = _knight_f6() if "конь f6" in low or "конь на f6" in low else None
        if subj is None and low.startswith("он ") and state.get("it"):
            subj = Ref(sq=state["it"][1], piece=state["it"][0], pronoun=True)
        if subj is None:
            return []
        for target in ("d4", "e4", "d5", "g4", "h5"):
            if f"нападает на {target}" in low:
                return [Claim(rel="attack", subj=subj, objs=(Ref(sq=target),))]
        return []

    def judge(claim, ctx, state):
        return verify(claim, env_for(ctx.current.fen()), "", require_grounding=False) if ctx.current else None

    def remember(text, claims, ctx, state):
        if "конь f6" in text.lower() or "конь на f6" in text.lower():
            state["it"] = ("N", "f6")

    monkeypatch.setattr(acr, "extract_claims", extract)
    monkeypatch.setattr(acr, "judge_claim", judge)
    monkeypatch.setattr(acr, "remember", remember)
    return seen


def _checker_built() -> bool:
    try:
        claims = claim_grammar.extract("Конь на f6 ничем не прикрыт.", {}, "ru")
        return bool(claims) and claim_scene.boards_for(claims[0], CheckContext.from_fens([ST4]), {}) is not None
    except Exception:  # noqa: BLE001
        return False


built = pytest.mark.skipif(not _checker_built(), reason="claim_grammar / claim_scene are still stubs (WP-A, WP-B)")


@pytest.fixture
def client():
    rate_limiter.reset()
    from src.server import app

    yield TestClient(app)
    rate_limiter.reset()


def _check(client, text, previous=None, **extra):
    body = {"text": text, "fen": ST4, "question": "Что делать дальше?", "engine": False, **extra}
    if previous is not None:
        body["previous"] = previous
    with patch("src.server.log_event") as log:
        resp = client.post("/api/coach/voice/check", headers=USER, json=body)
    assert resp.status_code == 200
    events = [(c.args[0], c.kwargs) for c in log.call_args_list]
    return resp.json()["issues"], events


def test_a_spoken_relation_claim_is_judged_in_on(monkeypatch, client, seams):
    """The squares said in words («эф шесть», «дэ четыре») reach the relation checker as squares."""
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    issues, events = _check(client, SPOKEN)
    assert seams["texts"] == ["Конь f6 нападает на d4."]
    assert any(REL in i for i in issues)  # beside the attack check's own «a knight on f6 does not attack d4»
    relation = [kw for name, kw in events if name == "relation_check"]
    assert relation and relation[0]["surface"] == "voice" and relation[0]["payload"]["relation_flags"] == 1
    # a true one passes
    issues, _ = _check(client, "Конь эф шесть нападает на е четыре.")
    assert issues == []


def test_shadow_answers_nothing_and_logs_the_flag(monkeypatch, client, seams):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    issues, events = _check(client, SPOKEN)
    assert not any(REL in i for i in issues)
    payload = [kw["payload"] for name, kw in events if name == "relation_check"][0]
    assert payload["relation_mode"] == "shadow"
    assert payload["relation_shadow"][0]["sentence"] == "Конь f6 нападает на d4."


def test_off_runs_nothing(monkeypatch, client, seams):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "off")
    issues, events = _check(client, SPOKEN)
    assert not any(REL in i for i in issues)
    assert seams["texts"] == [] and not [e for e in events if e[0] == "relation_check"]


def test_the_pronoun_is_resolved_from_the_replayed_previous_sentences(monkeypatch, client, seams):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    issues, events = _check(client, "Он нападает на дэ четыре.", previous="Чёрные вывели коня. Конь f6 стоит в центре.")
    assert seams["states"][-1] == {"it": ("N", "f6")}
    assert any(REL in i for i in issues)
    # what the replayed sentences themselves flagged is not this sentence's: they were checked when said
    issues, events = _check(client, "Он нападает на е четыре.",
                            previous="Конь f6 нападает на d4. Конь f6 стоит в центре.")
    assert issues == [] and not [e for e in events if e[0] == "relation_check"]


def test_without_previous_a_pronoun_claim_is_skipped(monkeypatch, client, seams):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    issues, events = _check(client, "Он нападает на дэ четыре.")
    assert issues == [] and seams["states"] == [{}]
    assert not [e for e in events if e[0] == "relation_check"]


def test_a_broken_relation_path_never_blocks_the_voice_check(monkeypatch, client, seams):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.setattr(acr, "extract_claims", lambda text, ctx, state: 1 / 0)
    issues, events = _check(client, SPOKEN)
    assert issues == ["a knight on f6 does not attack d4"]  # the other checks still judge it
    payload = [kw["payload"] for name, kw in events if name == "relation_check"][0]
    assert payload["relation_errors"] == 1 and payload["relation_flags"] == 0


@built
def test_built_a_spoken_relation_claim_is_judged_in_on(monkeypatch, client):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "off")
    legacy, _ = _check(client, SPOKEN)
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    issues, _ = _check(client, SPOKEN)
    assert len(issues) > len(legacy) and any("d4" in i for i in issues)


@built
def test_built_without_previous_a_pronoun_claim_is_skipped(monkeypatch, client):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    issues, _ = _check(client, "Он нападает на дэ четыре.")
    assert issues == []
    issues, _ = _check(client, "Он нападает на дэ четыре.", previous="Чёрные вывели коня на f6.")
    assert issues and any("d4" in i for i in issues)
