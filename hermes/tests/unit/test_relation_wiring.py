"""The relation checker wired into the text turn (plan 30.10, WP-C): the mode in a real /api/coach/chat turn, the
issues the rewrite gets, the turn's log record, the solution lines, fail-open.

Two tiers. The wiring tier does not depend on the parser and the judge being built: a sentence's claims come from
``SAYS`` (what a parser would extract, written by hand — the parser's own tests are WP-A's) and are judged by the
reference judge (tests/support/ref_judge.py) on the turn's board. The built tier runs the real
claim_grammar/claim_scene/claim_judge and is skipped until they are in (after the merge of WP-A and WP-B).
"""
import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import answer_check_relations as acr
from src import claim_grammar, claim_scene, config
from src.answer_check import CheckContext, check_sentence
from src.claim_types import Claim, Ref, Verdict
from src.middleware.rate_limiter import rate_limiter
from src.sessions import session_store
from src.user_profile import UserProfile

# The st4 game of 29.10 after 1.d4 Nf6 (tests/fixtures/relations/triage.json, st4#7).
ST4 = "rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 2"
ST4_ANSWER = [  # st4#7, the sentences legacy lets through on this board
    "Оценка примерно равная, совсем чуть в твою пользу за счёт права первого хода. ",
    "Смотри на их коня: он на f6 ничем не прикрыт, так что за пешку d4 бояться нечего. ",
    "Сейчас самое время поддержать пешку d4 ходом c3 или развить коня g1 на f3. ",
    "Как думаешь, чем начнёшь строить центр?",
]
UNDEFENDED = "ничем не прикрыт"
USER = {"X-User-Id": "relation-wiring"}

# Words of a sentence → the claims a parser makes of them (by hand: this tier tests the wiring, not the parser).
SAYS = {
    UNDEFENDED: [Claim(rel="undefended", subj=None, objs=(Ref(sq="f6", piece="N"),))],
    "f6 нападает на d4": [Claim(rel="attack", subj=Ref(sq="f6", piece="N"), objs=(Ref(sq="d4"),))],
    "f6 нападает на e4": [Claim(rel="attack", subj=Ref(sq="f6", piece="N"), objs=(Ref(sq="e4"),))],
}


@pytest.fixture
def seams(monkeypatch):
    """The parser from SAYS, the reference judge on ctx.current; records what each call saw."""
    from tests.support.ref_judge import env_for, verify

    seen = {"texts": [], "solution_lines": [], "claims": 0}

    def extract(text, ctx, state):
        seen["texts"].append(text)
        seen["solution_lines"].append([list(x) for x in ctx.solution_lines])
        claims = [c for words, cs in SAYS.items() if words in text for c in cs]
        seen["claims"] += len(claims)
        return claims

    def judge(claim, ctx, state):
        if ctx.current is None:
            return None
        return verify(claim, env_for(ctx.current.fen()), "", require_grounding=False)

    monkeypatch.setattr(acr, "extract_claims", extract)
    monkeypatch.setattr(acr, "judge_claim", judge)
    return seen


def _checker_built() -> bool:
    """The real parser and resolver are in (WP-A, WP-B merged)."""
    try:
        ctx = CheckContext.from_fens([ST4])
        claims = claim_grammar.extract("Конь на f6 ничем не прикрыт.", {}, "ru")
        return bool(claims) and claim_scene.boards_for(claims[0], ctx, {}) is not None
    except Exception:  # noqa: BLE001
        return False


built = pytest.mark.skipif(not _checker_built(), reason="claim_grammar / claim_scene are still stubs (WP-A, WP-B)")


# ── the merge policy ────────────────────────────────────────────────────────────────────────────────────────────
def _ctx(fen=ST4, question=""):
    return CheckContext.from_fens([fen], question=question)


def test_an_issue_the_other_checks_already_gave_is_not_given_twice(monkeypatch):
    monkeypatch.setattr(acr, "extract_claims", lambda text, ctx, state: [SAYS[UNDEFENDED][0]])
    monkeypatch.setattr(acr, "judge_claim", lambda claim, ctx, state: Verdict("false", "", "f6 is defended by e7, g7"))
    for mode in ("on", "shadow"):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", mode)
        ctx = _ctx()
        assert acr.relation_issues("x", ctx, ["f6 is defended by e7, g7"]) == []
        assert ctx.relation_shadow == [] and ctx.relation_stats["flags"] == 0
        ctx = _ctx()
        got = acr.relation_issues("x", ctx, ["something else"])
        assert (got or ctx.relation_shadow[0][1]) == ["f6 is defended by e7, g7"]


def test_the_rewrite_gets_the_relation_issues_first_and_at_most_three(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    truths = iter(["truth one", "truth two"])
    monkeypatch.setattr(acr, "extract_claims", lambda text, ctx, state: [SAYS[UNDEFENDED][0]])
    monkeypatch.setattr(acr, "judge_claim", lambda claim, ctx, state: Verdict("false", "", next(truths)))
    ctx = _ctx()
    acr.relation_issues("a", ctx, [])
    acr.relation_issues("b", ctx, [])
    legacy = ["legacy one", "legacy two"]
    assert acr.issues_for_fix(legacy + ["truth two", "truth one", "legacy one"], ctx) == ["truth two", "truth one",
                                                                                          "legacy one"]
    assert acr.issues_for_fix(legacy, ctx) == legacy
    assert acr.issues_for_fix(["a", "b", "c", "d", "e"], ctx) == ["a", "b", "c"]
    assert acr.issues_for_fix(["only"], CheckContext()) == ["only"]
    assert acr.MAX_FIX_ISSUES == 3
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "off")  # off: the rewrite gets what it got before the checker
    assert acr.issues_for_fix(["a", "b", "c", "d"], ctx) == ["a", "b", "c", "d"]


def test_shadow_issues_are_never_marked_for_the_rewrite(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    monkeypatch.setattr(acr, "extract_claims", lambda text, ctx, state: [SAYS[UNDEFENDED][0]])
    monkeypatch.setattr(acr, "judge_claim", lambda claim, ctx, state: Verdict("false", "", "t"))
    ctx = _ctx()
    acr.relation_issues("a", ctx, [])
    assert "issued" not in ctx.relation_stats and ctx.relation_shadow == [("a", ["t"])]


# ── timing and the log record ───────────────────────────────────────────────────────────────────────────────────
def test_time_is_measured_per_call_and_the_summary_carries_the_counters(monkeypatch, seams):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    ctx = _ctx()
    for sentence in ["Он на f6 ничем не прикрыт.", "Конь f6 нападает на e4.", "Просто текст."]:
        check_sentence(sentence, ctx)
    summary = acr.turn_summary(ctx)
    assert summary["relation_mode"] == "shadow"
    assert summary["relation_calls"] == 3 and summary["relation_claims"] == 2 and summary["relation_flags"] == 1
    assert summary["relation_errors"] == 0
    assert 0 < summary["relation_ms_max"] <= summary["relation_ms"]
    record = acr.log_record(ctx)
    assert record["relation_shadow"] == [{"sentence": "Он на f6 ничем не прикрыт.",
                                          "issues": [record["relation_shadow"][0]["issues"][0]]}]
    assert "defended by e7, g7" in record["relation_shadow"][0]["issues"][0]
    assert record["relation_shadow_total"] == 1 and record["relation_issued"] == []
    json.dumps(record)  # one JSON row


def test_nothing_to_review_is_not_logged(monkeypatch, seams):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    ctx = _ctx()
    check_sentence("Конь f6 нападает на e4.", ctx)
    assert acr.log_record(ctx) is None
    assert acr.turn_summary(CheckContext())["relation_calls"] == 0  # a turn with no check at all


def test_the_shadow_records_fit_one_log_row():
    ctx = _ctx()
    ctx.relation_shadow = [("слово " * 200, ["issue " * 60]) for _ in range(60)]
    entries = acr.shadow_entries(ctx)
    assert entries and len(json.dumps(entries, ensure_ascii=False).encode()) <= acr.SHADOW_BYTES
    assert all(len(e["sentence"]) <= 300 and len(e["issues"][0]) <= acr.MAX_ISSUE_CHARS for e in entries)
    ctx.relation_shadow = [object()]  # never raises
    assert acr.shadow_entries(ctx) == []


# ── solution lines ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("question, asks", [
    ("Задача из урока «Двойной удар». Какой здесь первый ход?", True),
    ("Что мне здесь играть?", True),
    ("что тут делать", True),
    ("Как белым выиграть?", True),
    ("Каким ходом начать атаку?", True),
    ("Чем ходить?", True),
    ("What is the best move here?", True),
    ("What should I play?", True),
    ("Мұнда қандай жүріс жақсы?", True),
    ("Почему конь стоит на f6?", False),
    ("Стоит ли брать пешку f4?", False),
    ("Расскажи про сицилианскую защиту", False),
    ("Привет", False),
    ("", False),
])
def test_asks_for_a_move(question, asks):
    assert acr.asks_for_a_move(question) is asks


def test_a_lesson_task_named_in_the_question():
    assert acr.names_a_lesson_task("Задача из урока «Вилка»: найди лучший ход")
    assert acr.names_a_lesson_task("Упражнение 3 из урока «Связка»")
    assert not acr.names_a_lesson_task("Что такое урок?")


def test_the_line_from_the_current_position():
    after_e4 = chess.Board()
    after_e4.push_san("e4")
    start = chess.STARTING_FEN
    assert acr.line_from(start, ["e4", "e5", "Nf3", "Nc6"], after_e4) == ["e5", "Nf3", "Nc6"]
    assert acr.line_from(None, ["e7e5", "g1f3"], after_e4) == ["e5", "Nf3"]  # UCI from the current position
    assert acr.line_from(start, ["1.e4", "1...e5"], after_e4) == ["e5"]
    assert acr.line_from(start, ["d4", "d5"], after_e4) is None  # never stands on the board
    assert acr.line_from(start, ["e4"], after_e4) is None  # over on the board
    assert acr.line_from(None, ["e5", "Qxh7"], after_e4) == ["e5"]  # cut at the first move that cannot be played
    assert acr.line_from("not a fen", ["e5"], after_e4) is None
    assert acr.line_from(None, ["e5"], None) is None
    assert len(acr.line_from(None, ["e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O"], after_e4)) == acr.SOLUTION_PLIES


def _note(fen=ST4, moves=("c4", "e6", "Nc3")):
    return {"fen": fen, "note": "[Engine] …", "best": moves[0], "lines": [{"moves": list(moves), "eval": "+0.30"}]}


def test_the_engine_line_is_a_solution_line_only_for_a_move_question_or_a_task_on_the_board():
    ctx = _ctx()
    assert acr.engine_solution_line(_note(), ctx, "Какой здесь первый ход?") == ["c4", "e6", "Nc3"]
    assert acr.engine_solution_line(_note(), ctx, "Задача из урока «Центр»") == ["c4", "e6", "Nc3"]
    assert acr.engine_solution_line(_note(), ctx, "Почему конь на f6?", task_on_board=True) == ["c4", "e6", "Nc3"]
    assert acr.engine_solution_line(_note(), ctx, "Почему конь на f6?") is None
    # a line of another board (a hidden position, an example) is not this board's solution
    assert acr.engine_solution_line(_note(chess.STARTING_FEN, ("e4",)), ctx, "Какой ход?") is None
    assert acr.engine_solution_line(None, ctx, "Какой ход?") is None
    assert acr.engine_solution_line({"fen": ST4, "lines": []}, ctx, "Какой ход?") is None
    assert acr.engine_solution_line({"fen": ST4, "lines": [{"moves": "c4 e6"}]}, ctx, "Какой ход?") == ["c4", "e6"]
    assert acr.engine_solution_line(_note(), CheckContext(), "Какой ход?") is None
    lines = []
    ctx.solution_lines = lines
    acr.add_solution_line(ctx, ["c4"])
    acr.add_solution_line(ctx, ["c4"])
    acr.add_solution_line(ctx, None)
    assert lines == [["c4"]]


# ── the text turn ───────────────────────────────────────────────────────────────────────────────────────────────
def _agent(parts):
    agent = MagicMock()
    agent.tools = []
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_cache_read_tokens = 0

    def _chat(message, stream_callback=None):
        for part in parts:
            stream_callback(part)
        return "".join(parts)

    agent.chat.side_effect = _chat
    return agent


@pytest.mark.unit
class TestTextTurn:
    @pytest.fixture(autouse=True)
    def _turn(self, monkeypatch):
        session_store._sessions.clear()
        rate_limiter.reset()
        for name, value in (("COACH_TWO_STAGE", False), ("COACH_ENGINE_NOTE", False), ("COACH_OPENING_PRESTEP", False),
                            ("COACH_SITE_PUZZLE_LOOKUP", False), ("COACH_ANSWER_CHECK", True), ("COACH_ANSWER_FIX", False)):
            monkeypatch.setattr(config, name, value)
        self.client = TestClient(__import__("src.server", fromlist=["app"]).app)
        self.fix_prompts = []
        yield
        session_store._sessions.clear()
        rate_limiter.reset()

    def _turn_with(self, parts, message="d4", fen=ST4, fix_text=None, note=None, site_hit=None):
        """One chat turn with a fake model streaming *parts*; (shown text, {event: payload}, the turn's frames)."""
        from src.quick_reply import QuickReply

        def _fix(**kwargs):
            self.fix_prompts.append(kwargs["messages"][1]["content"])
            kwargs["on_delta"](fix_text or "Конь f6 защищён пешками e7 и g7.")
            return QuickReply(model=kwargs["model"])

        with patch("src.server._create_agent", return_value=_agent(parts)), \
                patch("src.server.load_user_profile", return_value=UserProfile(user_id="relation-wiring")), \
                patch("src.quick_reply.stream_completion", side_effect=_fix), \
                patch("src.server.engine_note", return_value=note), \
                patch("src.site_puzzle_lookup.site_puzzle_at", return_value=site_hit), \
                patch("src.server.log_event") as log:
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": message, "fen": fen})
        assert resp.status_code == 200
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        events = {}
        for call in log.call_args_list:
            events.setdefault(call.args[0], call.kwargs.get("payload"))
        return "".join(f.get("delta", "") for f in frames), events, frames

    def test_shadow_records_and_logs_but_does_not_cut(self, monkeypatch, seams):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
        shown, events, _ = self._turn_with(ST4_ANSWER)
        assert UNDEFENDED in shown and "чем начнёшь" in shown
        record = events["relation_check"]
        assert record["relation_mode"] == "shadow" and record["relation_flags"] == 1
        assert [e["sentence"] for e in record["relation_shadow"]] == [
            "Смотри на их коня: он на f6 ничем не прикрыт, так что за пешку d4 бояться нечего."]
        assert "defended by e7, g7" in record["relation_shadow"][0]["issues"][0]
        end = events["turn_end"]
        assert end["relation_flags"] == 1 and end["relation_errors"] == 0 and end["relation_mode"] == "shadow"
        assert end["relation_calls"] >= len(ST4_ANSWER) and end["relation_ms"] >= 0
        assert "answer_check" not in events  # nothing was cut

    def test_on_cuts_the_sentence(self, monkeypatch, seams):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
        shown, events, _ = self._turn_with(ST4_ANSWER)
        assert UNDEFENDED not in shown and "Оценка примерно равная" in shown and "чем начнёшь" in shown
        dropped = events["answer_check"]["dropped"]
        assert [d["sentence"][:20] for d in dropped] == ["Смотри на их коня: о"]
        assert "defended by e7, g7" in dropped[0]["issues"][0]
        assert events["relation_check"]["relation_shadow"] == []
        assert "defended by e7, g7" in events["relation_check"]["relation_issued"][0]
        assert events["turn_end"]["relation_flags"] == 1

    def test_the_rewrite_gets_the_board_truth_first(self, monkeypatch, seams):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
        monkeypatch.setattr(config, "COACH_ANSWER_FIX", True)
        shown, events, _ = self._turn_with(ST4_ANSWER)
        assert UNDEFENDED not in shown and "защищён пешками e7 и g7" in shown
        assert len(self.fix_prompts) == 1
        why = self.fix_prompts[0].split("Why it is wrong (checked on the board): ", 1)[1]
        assert why.startswith("f6 (Black knight) is attacked by nothing and defended by e7, g7")

    def test_the_rewrite_is_checked_on_the_same_context(self, monkeypatch, seams):
        """fix_gate shares check_ctx: a rewrite sentence with a false relation claim is left out too."""
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
        monkeypatch.setattr(config, "COACH_ANSWER_FIX", True)
        shown, events, _ = self._turn_with(ST4_ANSWER, fix_text="Конь f6 нападает на d4. Конь f6 нападает на e4.")
        assert "нападает на e4" in shown and "нападает на d4" not in shown
        dropped = [d["sentence"] for d in events["answer_check"]["dropped"]]
        assert dropped == ["Конь f6 нападает на d4."]
        assert events["turn_end"]["relation_flags"] == 2

    def test_off_runs_nothing_and_logs_no_relation_event(self, monkeypatch, seams):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "off")
        shown, events, _ = self._turn_with(ST4_ANSWER)
        assert shown == "".join(ST4_ANSWER)
        assert seams["texts"] == [] and "relation_check" not in events
        assert events["turn_end"]["relation_calls"] == 0 and events["turn_end"]["relation_mode"] == "off"

    def test_an_exception_in_the_relation_path_never_blocks_a_sentence(self, monkeypatch, seams):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")

        def broken(text, ctx, state):
            raise RuntimeError("parser bug")

        monkeypatch.setattr(acr, "extract_claims", broken)
        shown, events, _ = self._turn_with(ST4_ANSWER)
        assert shown == "".join(ST4_ANSWER)
        assert events["turn_end"]["relation_errors"] == len(ST4_ANSWER)
        assert events["relation_check"]["relation_errors"] == len(ST4_ANSWER)

    def test_solution_lines_for_a_lesson_task(self, monkeypatch, seams):
        """«Задача из урока … Какой здесь первый ход»: the engine's line of the turn (no new engine call) is the solution
        line, from the position on the board."""
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE", True)
        note = _note(moves=("c4", "e6", "Nc3", "Bb4"))
        self._turn_with(["Здесь хорош ход c4. ", "Он захватывает центр."],
                        message="Задача из урока «Центр». Какой здесь первый ход?", note=note)
        assert seams["solution_lines"] and all(s == [["c4", "e6", "Nc3", "Bb4"]] for s in seams["solution_lines"])

    def test_no_solution_line_when_the_question_asks_no_move(self, monkeypatch, seams):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE", True)
        self._turn_with(["Конь развит в центр. "], message="Почему чёрные сыграли Nf6?", note=_note())
        assert seams["solution_lines"] and all(s == [] for s in seams["solution_lines"])

    def test_the_site_lessons_task_gives_its_solution_and_the_engine_line(self, monkeypatch, seams):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE", True)
        monkeypatch.setattr(config, "COACH_SITE_PUZZLE_LOOKUP", True)
        hit = {"fen": ST4, "solution": ["Nf3", "e6"], "lesson": "Центр", "module": "Дебют", "course": "Ступени",
               "n": 1, "total": 3}
        self._turn_with(["Подумай над развитием. "], message="Почему чёрные сыграли Nf6?", note=_note(), site_hit=hit)
        assert seams["solution_lines"][0] == [["Nf3", "e6"], ["c4", "e6", "Nc3"]]


# ── the built checker end to end (after WP-A and WP-B are merged) ───────────────────────────────────────────────
@built
@pytest.mark.unit
class TestBuiltTextTurn(TestTextTurn):
    """The same st4 turn with the real parser and judge: «он на f6 ничем не прикрыт» — the pronoun is the knight of
    the sentence's own «их коня»."""

    def test_shadow_records_and_logs_but_does_not_cut(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
        shown, events, _ = self._turn_with(ST4_ANSWER)
        assert UNDEFENDED in shown
        assert any(UNDEFENDED in e["sentence"] for e in events["relation_check"]["relation_shadow"])

    def test_on_cuts_the_sentence(self, monkeypatch):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
        shown, events, _ = self._turn_with(ST4_ANSWER)
        assert UNDEFENDED not in shown and "Оценка примерно равная" in shown

    # the rest of the wiring tier needs SAYS; the built tier covers only the turn itself
    test_the_rewrite_gets_the_board_truth_first = None
    test_the_rewrite_is_checked_on_the_same_context = None
    test_off_runs_nothing_and_logs_no_relation_event = None
    test_an_exception_in_the_relation_path_never_blocks_a_sentence = None
    test_solution_lines_for_a_lesson_task = None
    test_no_solution_line_when_the_question_asks_no_move = None
    test_the_site_lessons_task_gives_its_solution_and_the_engine_line = None
