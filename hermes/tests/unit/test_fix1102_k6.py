"""fix1102 K6: the rewrite after a wrong sentence never adds a fact the check did not prove (VERDICT §6.4).

Live 02.11: the rewrite wrote «Конь вынужден уйти на f7 с шахом» in place of a true mating line (trap-blackburne),
«она прикрыта только пешкой d7» (st1#9), «свои же пешки и слон его запирают» (d2-solution), and it was handed issue
texts that state nothing («the pawn on f6 is defended (by )», «exf4 is impossible after exf4», «no any queen»).
The boards and wordings here are new (a Ruy Lopez after 4...Nf6, a Philidor, a Scotch-like centre), not the reported
ones. src/rewrite_proof.py has the rule; src/server.py keeps a rewrite only when its first sentence with a board word is
proven, and otherwise goes on with the draft.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
import chess
from fastapi.testclient import TestClient

from src.answer_check import CheckContext, check_sentence
from src.quick_reply import QuickReply
from src.rewrite_proof import anchors, clean_issue, engine_moves, fix_issues, malformed, normalized, prove, well_formed
from src.server import app
from src.user_profile import UserProfile

RUY = "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 5"  # 1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6
PHILIDOR = "rnbqkbnr/ppp2ppp/3p4/4P3/8/8/PPP2PPP/RNBQKBNR b KQkq - 0 3"  # 1.e4 e5 2.d4 d6 3.dxe5?? (no white d-pawn)
RUY_LINE = ["O-O", "Be7", "Re1", "b5"]


def _ctx(fen=RUY, lines=None):
    ctx = CheckContext.from_fens([fen])
    if lines is not None:
        ctx.engine_lines = [list(lines)]
    return ctx


def _proof(sentence, fen=RUY, lines=RUY_LINE):
    ctx = _ctx(fen, lines)
    assert check_sentence(sentence, ctx) == []  # the check finds nothing wrong: the proof is the stricter test
    return prove(sentence, ctx)


# ── issue texts ────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
class TestIssueTexts:
    @pytest.mark.parametrize("issue", [
        "the knight on d6 is defended (by ), not undefended",
        "the rook on b2 is attacked (), not safe",
        "Nxf5 is impossible after Nxf5: there is no knight to take back on f5",
        "dxe5 is impossible after 3.dxe5: there is no pawn on d4 to take back on e5",
        "d4xd4: a pawn on d4 cannot capture on d4 (a pawn takes one square diagonally forward)",
        "",
    ])
    def test_a_text_that_states_nothing_is_malformed(self, issue):
        assert malformed(issue)
        assert well_formed([issue]) == []
        assert fix_issues([issue, "the bishop on b5 is not attacked by anything in this position"]) == [
            "the bishop on b5 is not attacked by anything in this position"]

    @pytest.mark.parametrize("issue", [
        "the bishop on b5 is not attacked by anything in this position",
        "the pawn on c4 is defended (by b3), not undefended",
        "exd5 is impossible after cxd5: there is no pawn on e4 to take back on d5",
        "after 6.Re1: White's rook on e1 attacks e2, e3 and e4 — not Black's knight on e5",
        "a knight cannot move from f3 to d5",
        "material: Black has an extra 1 pawn (not equal: материал равный)",
    ])
    def test_a_checkable_text_passes_as_it_is(self, issue):
        assert malformed(issue) is None
        assert well_formed([issue]) == [issue]

    def test_no_any_is_worded_for_the_reader(self):
        issue = "Qxh7 is impossible: no any queen can capture on h7 in the positions of this turn"
        assert malformed(issue) is None
        assert clean_issue(issue) == "Qxh7 is impossible: no queen of either side can capture on h7 in the positions of this turn"
        assert well_formed([issue]) == [clean_issue(issue)]

    def test_a_restated_move_is_the_trace_the_check_leaves_on_a_new_board(self):
        # «dxe5, то есть забрать пешку: dxe5» names one move twice. Before the K5 merge the recapture check read it
        # as a pair and left «dxe5 is impossible after dxe5»; K5 fixed that at its source, so no issue is left at all
        # (and if one ever comes back, it is malformed and never reaches the rewrite)
        issues = check_sentence("Лучший ответ — dxe5, то есть просто забрать пешку: dxe5.", _ctx(PHILIDOR))
        assert well_formed(issues) == []
        assert malformed("dxe5 is impossible after dxe5")


# ── the proof ───────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
class TestProof:
    @pytest.mark.parametrize("sentence", [
        "Конь f3 нападает на пешку e5.",
        "Пешку e5 защищает конь c6.",
        "Конь f6 нападает на пешку e4.",
        "Лучше всего 5.O-O: король уходит в безопасность.",
        "Лучше всего 5.O-O, а на 5...Be7 ответ 6.Re1.",
    ])
    def test_proven(self, sentence):
        assert _proof(sentence).status == "proven"

    @pytest.mark.parametrize("sentence, word", [
        # a forced move with check that nothing judged (trap-blackburne's kind)
        ("Конь вынужден уйти на g5 с шахом.", "вынужден"),
        # a true relation with «только» the claim does not carry (st1#9's kind: e5 is held by c6 and by nothing else
        # here — still, «только» is a word no claim proved)
        ("Пешку e5 защищает только конь c6.", "только"),
        # the king confined by its own pieces (d2-solution's kind)
        ("Свои же пешки и слон запирают короля на e8.", "запирают"),
        # a move that is not the engine's
        ("Лучше всего 5.Nc3, развивая коня.", "5.Nc3"),
        # an evaluation nobody proved
        ("После этого белые остаются с лишней пешкой.", "лишней"),
        # a capture told in words with no move to show it
        ("Теперь конь f3 просто забирает пешку e5.", "забирает"),
    ])
    def test_unproven(self, sentence, word):
        proof = _proof(sentence)
        assert proof.status == "unproven"
        assert any(word.lower() in w.lower() for w in proof.words), proof

    @pytest.mark.parametrize("sentence", [
        "Подумай, как закончить развитие.",
        "Хороший вопрос — давай разберёмся.",
        "Не торопись, сначала посмотри на всю доску целиком.",
    ])
    def test_neutral(self, sentence):
        assert _proof(sentence).status == "neutral"

    def test_the_engine_line_must_start_at_its_first_move(self):
        ctx = _ctx(RUY, RUY_LINE)
        assert engine_moves(["O-O", "Be7"], ctx)
        assert engine_moves(["Be7", "Re1"], ctx) is None  # a line from its middle is no proof
        assert engine_moves(["O-O+"], ctx) is None  # «+» said of a move that gives no check
        ctx = _ctx(RUY, RUY_LINE)
        assert prove("После 6.Re1 ладья смотрит на линию e.", ctx).status == "unproven"

    def test_a_pawn_move_written_as_its_square(self):
        assert _proof("Играй d3, укрепляя центр.", lines=["d3", "b5", "Bb3"]).status == "proven"
        assert _proof("Играй c3, укрепляя центр.", lines=["d3", "b5", "Bb3"]).status == "unproven"

    @pytest.mark.parametrize("sentence, status", [
        ("Ты сыграл 2.Nf3, а я ответил 2...d6.", "proven"),
        ("Ты сыграл Кf3 — конь с g1 вышел на f3.", "proven"),
        ("Ты сыграл 3.Nf3.", "unproven"),  # the record has it as the second move
        ("Я ответил 2...Nc6.", "unproven"),  # not in the record
        ("Сыграй Nf3.", "unproven"),  # advice, not a move told as made
        ("Ты сыграл Nf3 с шахом.", "unproven"),  # it gave no check
    ])
    def test_a_move_told_as_made_is_proven_by_the_game_record(self, sentence, status):
        moves = ["e4", "c5", "Nf3", "d6"]
        board = chess.Board()
        for san in moves:
            board.push_san(san)
        ctx = CheckContext.from_fens([board.fen()])
        ctx.game_moves = list(moves)
        check_sentence(sentence, ctx)
        assert prove(sentence, ctx).status == status

    def test_no_engine_line_proves_no_move(self):
        assert _proof("Лучше всего 5.O-O: король уходит в безопасность.", lines=None).status == "unproven"

    def test_anchors_read_cyrillic_moves_and_squares(self):
        words = anchors(normalized("Ход Кс7+ — конь на с7 с шахом."))
        assert [(a.kind, a.san) for a in words if a.kind == "move"] == [("move", "Nc7+")]
        kinds = [(a.kind, a.text) for a in words]
        assert ("square", "c7") in kinds and ("check", "шахом") in kinds


# ── the turn ────────────────────────────────────────────────────────────────────────────────────────────────────
WRONG = "Слон a4 нападает на пешку f7. "  # false on RUY: the bishop on a4 hits c6
DRAFT = ["Хороший вопрос. ", WRONG, "Спокойно рокируйся."]


@pytest.mark.unit
class TestTurn:
    def setup_method(self):
        self.client = TestClient(app)

    def _turn(self, draft, rewrite, fen=RUY, user="k6-user", message="что тут происходит?"):
        text, seen = self._raw_turn(draft, rewrite, fen, user, message)
        return text.strip(), seen

    def _raw_turn(self, draft, rewrite, fen, user, message):
        agent = MagicMock()

        def _chat(msg, stream_callback=None):
            for part in draft:
                stream_callback(part)
            return "".join(draft)

        agent.chat.side_effect = _chat
        seen = {"calls": 0}

        def _fix(**kwargs):
            seen["calls"] += 1
            seen["messages"] = kwargs["messages"]
            for i in range(0, len(rewrite or ""), 7):
                kwargs["on_delta"](rewrite[i:i + 7])
            return QuickReply(model=kwargs["model"])

        with patch("src.server.config.COACH_ENGINE_NOTE", False), \
                patch("src.server.config.COACH_OPENING_PRESTEP", False), \
                patch("src.server.config.COACH_ANSWER_FIX", True), \
                patch("src.quick_reply.stream_completion", side_effect=_fix), \
                patch("src.server._create_agent", return_value=agent), \
                patch("src.server.load_user_profile", return_value=UserProfile(user_id=user)):
            headers = {"X-User-Id": user}
            sid = self.client.post("/api/coach/sessions", headers=headers).json()["id"]
            resp = self.client.post("/api/coach/chat", headers=headers, json={
                "message": message, "session_id": sid, "fen": fen})
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        return "".join(f.get("delta", "") for f in frames), seen

    def test_an_unproven_rewrite_is_abandoned_and_the_draft_goes_on(self):
        text, seen = self._turn(DRAFT, "Конь вынужден уйти на g5 с шахом, и чёрные теряют пешку f7.")
        assert seen["calls"] == 1
        assert "вынужден" not in text and "a4 нападает" not in text
        assert text == "Хороший вопрос. Спокойно рокируйся."

    def test_a_proven_rewrite_stands_in_for_the_rest(self):
        text, _ = self._turn(DRAFT, "Подумай вот о чём. Конь f3 нападает на пешку e5, а защищает её конь c6.")
        assert text == "Хороший вопрос. Подумай вот о чём. Конь f3 нападает на пешку e5, а защищает её конь c6."
        assert "рокируйся" not in text  # the rewrite replaced the rest of the draft, as before

    def test_a_kept_rewrite_leaves_out_its_later_unproven_sentence(self):
        text, _ = self._turn(DRAFT, "Конь f3 нападает на пешку e5. Поэтому белые просто выигрывают пешку. "
                                    "Подумай, как закончить развитие.")
        assert text == "Хороший вопрос. Конь f3 нападает на пешку e5. Подумай, как закончить развитие."

    def test_neutral_words_before_an_unproven_claim_go_with_it(self):
        text, _ = self._turn(DRAFT, "Смотри внимательно. Конь вынужден уйти на g5 с шахом.")
        assert text == "Хороший вопрос. Спокойно рокируйся."

    def test_a_rewrite_that_opens_with_a_wrong_claim_is_abandoned(self):
        text, _ = self._turn(DRAFT, "Слон a4 нападает на пешку f7 и ладью h8. Конь f3 нападает на пешку e5.")
        assert text == "Хороший вопрос. Спокойно рокируйся."

    def test_a_failed_rewrite_call_lets_the_draft_go_on(self):
        text, seen = self._turn(DRAFT, "")
        assert seen["calls"] == 1
        assert text == "Хороший вопрос. Спокойно рокируйся."

    def test_the_draft_after_the_cut_is_still_checked(self):
        draft = ["Хороший вопрос. ", WRONG, "Конь f3 нападает на пешку e5. ", "Слон a4 бьёт пешку h7."]
        text, _ = self._turn(draft, "Конь вынужден уйти на g5 с шахом.")
        assert text == "Хороший вопрос. Конь f3 нападает на пешку e5."

    def test_the_draft_checked_with_the_cut_sentence_goes_on_too(self):
        # one delta: the gate checks the sentence after the cut one in the same batch, before the rewrite starts
        text, _ = self._turn(["Хороший вопрос. " + WRONG + "Конь f3 нападает на пешку e5. Спокойно рокируйся."],
                             "Конь вынужден уйти на g5 с шахом.")
        assert text == "Хороший вопрос. Конь f3 нападает на пешку e5. Спокойно рокируйся."

    def test_a_draft_in_the_wrong_language_does_not_go_on(self):
        draft = ["Хороший вопрос. ", "The bishop on a4 pins the knight on c6 to the king. ", "Then you castle. Play d3."]
        text, seen = self._turn(draft, "Конь вынужден уйти на g5 с шахом.")
        assert seen["calls"] == 1
        assert text == "Хороший вопрос."  # no English fragment, no unproven rewrite

    def test_never_an_empty_answer(self):
        text, _ = self._turn([WRONG], "Конь вынужден уйти на g5 с шахом.")
        assert text.strip() and "g5" not in text and "a4" not in text
        assert "провер" in text  # the plain line: the coach did not guess

    def test_an_empty_answer_never_keeps_a_lone_promise_of_the_rewrite(self):
        text, _ = self._turn([WRONG], "Хороший вопрос, давай разберёмся по шагам. Конь вынужден уйти на g5 с шахом.")
        assert "разберёмся" not in text and "g5" not in text and "провер" in text

    def test_a_sentence_whose_only_issue_is_malformed_is_shown_and_not_rewritten(self):
        draft = ["Лучший ответ — dxe5, то есть просто забрать пешку: dxe5. ", "Потом развивай коня."]
        text, seen = self._turn(draft, "Конь вынужден уйти на g5 с шахом.", fen=PHILIDOR, user="k6-malformed")
        assert seen["calls"] == 0
        assert text == "Лучший ответ — dxe5, то есть просто забрать пешку: dxe5. Потом развивай коня."

    def test_the_rewrite_is_given_only_checkable_issues(self):
        real = check_sentence

        def _check(sentence, ctx=None, **kw):
            issues = real(sentence, ctx, **kw)
            if "a4 нападает" in sentence:
                issues = ["the pawn on f7 is defended (by ), not undefended"] + list(issues)
            return issues

        with patch("src.answer_check.check_sentence", side_effect=_check):
            text, seen = self._turn(DRAFT, "Конь f3 нападает на пешку e5.")
        prompt = seen["messages"][1]["content"]
        assert "(by )" not in prompt and "a bishop on a4 does not attack f7" in prompt
        assert text == "Хороший вопрос. Конь f3 нападает на пешку e5."
