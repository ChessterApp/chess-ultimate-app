"""Prod check 29.10, the engine's verdict on lines (30.10): a line the coach writes with the outcome it promises,
and the coach's advice told in the second person, are judged by the engine before the sentence is shown
(src/line_verdict.py, src/answer_check.proposed_move)."""

import json
import os
from unittest.mock import MagicMock, patch

import chess
import pytest

from src import config, server
from src.answer_check import CheckContext, check_sentence, proposed_move
from src.hypothetical import verify_line, verify_recommendation
from src.line_verdict import line_claims, verify_claims
from src.tools.stockfish import STOCKFISH_PATH

requires_sf = pytest.mark.skipif(not os.path.exists(STOCKFISH_PATH), reason="Stockfish is not installed")

# mate2-no: the Fried Liver after 7...Ke6, «Тут есть мат в два хода?»
FRIED = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"
# op-show-italian: «Покажи итальянскую партию» on the start position; the opening's line went up on the board.
ITALIAN = "1. e4 e5 2. Nf3 Nc6 3. Bc4"
ITALIAN_FEN = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
# pawn-b3-bare: the Ruy Lopez after 5...Be7, «А если b3?»
RUY = "r1bqk2r/1pppbppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 4 6"
# Legal's trap after 5...g6?: 6.Nxe5! Bxd1 7.Bxf7+ Ke7 8.Nd5#
LEGAL = "rn1qkbnr/ppp2p1p/3p2p1/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5"


@pytest.fixture
def local_engine(monkeypatch):
    """Stockfish on this machine, never the engine server (no network in unit tests)."""
    monkeypatch.setattr("src.tools.stockfish.ENGINE_API_URL", "")


def _sentences(ctx, *sentences):
    """Each sentence through the check, in order, as the gate does; the claims each one left."""
    out = []
    for s in sentences:
        assert check_sentence(s, ctx) == []
        out.append(ctx.line_claims.get(s, []))
    return out


def _italian_ctx():
    return CheckContext.from_fens([chess.STARTING_FEN, ITALIAN_FEN], [ITALIAN], question="Покажи итальянскую партию")


def _fake_analysis(scores: dict):
    """analyze_timed stand-in: scores[board_fen + turn] → (pawns for the side to move, pv in UCI)."""
    def _analyze(fen, movetime_ms, multipv=1, min_depth=10):
        b = chess.Board(fen)
        score, pv = scores.get(b.board_fen() + (" w" if b.turn else " b"), (0.0, ""))
        return {"lines": [{"multipv": 1, "depth": 14, "pv": pv, "score": score}]}
    return _analyze


def _key(board):
    return board.board_fen() + (" w" if board.turn else " b")


class TestAdviceInTheSecondPerson:
    """«Берёшь коня на d5 с шахом: Qxd5+.» — the coach's move told as the student's, at the start of a sentence."""

    @pytest.mark.parametrize("sentence, san", [
        ("Берёшь коня на d5 с шахом: Qxd5+.", "Qxd5+"),  # mate2-no, as on production
        ("Бьёшь Qxd5+ — и король должен уходить.", "Qxd5+"),
        ("Сейчас ты просто играешь Nc3 и развиваешься.", "Nc3"),
        ("Ставишь коня на c3 — и центр под контролем.", "Nc3"),
    ])
    def test_it_is_advice(self, sentence, san):
        found = proposed_move(sentence, CheckContext.from_fens([FRIED]))
        assert found and found[2] == san

    @pytest.mark.parametrize("sentence", [
        "Берёшь на d5: Qxd5+ — и теряешь ферзя после Qxd5.",  # the move refuted
        "Берёшь коня на d5 с шахом: Qxd5+?",                 # a question
        "Тогда ты берёшь Qxd5+.",                              # a step of a line
        "После Nc3 ты играешь Qxd5+.",                         # a step of a line
        "Ты играешь белыми, и сейчас твой ход.",               # no move
        "Если берёшь Qxd5+, король уходит.",                   # a condition
    ])
    def test_it_is_not(self, sentence):
        assert proposed_move(sentence, CheckContext.from_fens([FRIED])) is None

    def test_not_in_a_game_when_it_is_the_engines_move(self):
        ctx = CheckContext.from_fens([FRIED], student_color=chess.BLACK)
        assert proposed_move("Берёшь коня на d5 с шахом: Qxd5+.", ctx) is None

    @requires_sf
    def test_the_engine_rejects_it(self, local_engine):
        board, move, san = proposed_move("Берёшь коня на d5 с шахом: Qxd5+.", CheckContext.from_fens([FRIED]))
        why = verify_recommendation(board, move, san, 300, 150, reveal_best=False)
        assert why and "Qxd5+ is a mistake" in why and "Qxd5" in why.split("after", 1)[1]


class TestLineClaims:
    """The line and the outcome, read by the board only."""

    def test_mate2_no_the_outcome_after_the_move(self):
        ctx = CheckContext.from_fens([FRIED], question="Тут есть мат в два хода?")
        first, second = _sentences(ctx, "Берёшь коня на d5 с шахом: Qxd5+.",
                                   "Король вынужден уйти с e6, после чего ты забираешь ферзя, и партия фактически решена.")
        assert first == []
        assert len(second) == 1
        claim = second[0]
        assert claim["side"] == chess.WHITE and [m.uci() for m in claim["moves"]] == ["f3d5"]
        assert claim["board"].board_fen() == chess.Board(FRIED).board_fen()

    def test_op_show_italian_the_trap_told_backwards(self):
        ctx = _italian_ctx()
        [claims] = _sentences(ctx, "Но помни про ловушку: если сыграть Nd4, можно нарваться на Nxe5, и там уже начинается "
                                   "опасная для чёрных игра — так что не жадничай.")
        assert len(claims) == 1
        assert claims[0]["side"] == chess.WHITE  # dangerous for Black: said to favour White
        assert claims[0]["board"].board_fen() == chess.Board(ITALIAN_FEN).board_fen()
        assert [m.uci() for m in claims[0]["moves"]] == ["c6d4", "f3e5"]

    @pytest.mark.parametrize("sentence, side", [
        ("Qxd5+ выигрывает ферзя.", chess.WHITE),
        ("После Qxd5+ белые выигрывают ферзя.", chess.WHITE),
        ("После Qxd5+ чёрные теряют ферзя.", chess.WHITE),
        ("После Qxd5+ у белых решающий перевес.", chess.WHITE),
        ("After Qxd5+ White wins the queen.", chess.WHITE),
        ("После Qxd5+ ты остаёшься с лишним ферзём.", chess.WHITE),
        ("После Qxd5+ чёрные теряют ферзя и материал.", chess.WHITE),  # «материал» is not «мат»
    ])
    def test_paraphrases(self, sentence, side):
        [claims] = _sentences(CheckContext.from_fens([FRIED]), sentence)
        assert claims and claims[0]["side"] == side

    @pytest.mark.parametrize("sentence", [
        "После Qxd5+ ты не выигрываешь ферзя: чёрные просто берут Qxd5.",     # denied
        "Ты думаешь, что после Qxd5+ забираешь ферзя, но это не так.",         # the student's belief
        "Белые выигрывают ферзя после Qxd5+.",                                 # the outcome before the line
        "После Qxd5+ белые забирают коня, но теряют ферзя.",                   # the price named
        "После Qxd5+ белые выигрывают ферзя?",                                 # a question
        "Если они берут — ты бьёшь ладью слоном на f7, а ты спокойно играешь Bd3 и забираешь материал.",  # moves in words first
        "Qd3 или Qxd5+ — и белые выигрывают фигуру.",                          # alternatives, not one line
        "После Qxd5+ белые выигрывают темп.",                                  # a tempo is not material
        "После Qxd5+ белые отдают ферзя и через ход ставят мат.",             # a sacrifice is not a loss
        "Берёшь Qxd5+, и если король отойдёт, ты забираешь ферзя.",           # a reply the line does not write
        "Если белые сыграют Qxd5+, ты теряешь ферзя.",                         # «ты» is not White here
    ])
    def test_not_claims_about_a_line_of_this_board(self, sentence):
        assert _sentences(CheckContext.from_fens([FRIED]), sentence) == [[]]

    def test_the_price_named_after_an_outcome_leaves_only_the_last_one(self):
        # «чёрные забирают ферзя» is followed by its price (a mate): only «белые ставят мат» is judged.
        [claims] = _sentences(CheckContext.from_fens([FRIED]), "После Qxd5+ чёрные забирают ферзя, и белые ставят мат.")
        assert [(c["words"], c["side"]) for c in claims] == [("белые ставят мат", chess.WHITE)]

    def test_you_needs_a_known_side_off_the_screens_board(self):
        # The opening's line, not the board on the screen (the start position): «ты» is not known to be Black there.
        ctx = _italian_ctx()
        assert _sentences(ctx, "Если сыграть Nd4, на Nxe5 ты выигрываешь фигуру.") == [[]]
        ctx = CheckContext.from_fens([chess.STARTING_FEN, ITALIAN_FEN], [ITALIAN], student_color=chess.BLACK)
        [claims] = _sentences(ctx, "Если сыграть Nd4, на Nxe5 ты выигрываешь фигуру.")
        assert claims and claims[0]["side"] == chess.BLACK

    def test_a_diagram_only_named_in_a_tool_text_starts_no_line(self):
        ctx = CheckContext.from_fens([chess.STARTING_FEN])
        ctx.add_text(f"Пример из урока: {FRIED}")
        assert _sentences(ctx, "После Qxd5+ белые выигрывают ферзя.") == [[]]

    def test_a_line_that_fits_two_positions_is_not_guessed(self):
        # Nf3 is legal for White both at the start and after 1.e4 e5: which one is meant is not known.
        ctx = CheckContext.from_fens([chess.STARTING_FEN, "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"],
                                     ["1. e4 e5"])
        ctx.current = None
        assert _sentences(ctx, "После Nf3 белые стоят лучше.") == [[]]

    def test_the_move_number_must_be_the_boards(self):
        assert _sentences(CheckContext.from_fens([FRIED]), "После 12.Qxd5+ белые выигрывают ферзя.") == [[]]
        [claims] = _sentences(CheckContext.from_fens([FRIED]), "После 8.Qxd5+ белые выигрывают ферзя.")
        assert claims

    def test_pawn_b3_bare_the_number_and_the_students_move(self):
        ctx = CheckContext.from_fens([RUY], question="А если b3?")
        [_, _, claims] = _sentences(ctx, "Нет, так играть нельзя — b3 теряет слона.",
                                    "После b3 чёрные отвечают b5, и слон на a4 оказывается в ловушке: b5–a4 отступать ему некуда, и он гибнет.",
                                    "В лучшем случае белые отдают слона за пешку — это почти на четыре пешки хуже, чем было.")
        assert len(claims) == 1 and claims[0]["kind"] == "swing" and claims[0]["pawns"] == -4
        assert [m.uci() for m in claims[0]["moves"]] == ["b2b3"]


@requires_sf
class TestEngineVerdict:
    """The claims against Stockfish on this machine (300 ms, as on production)."""

    def test_mate2_no(self, local_engine):
        ctx = CheckContext.from_fens([FRIED])
        _, claims = _sentences(ctx, "Берёшь коня на d5 с шахом: Qxd5+.",
                               "Король вынужден уйти с e6, после чего ты забираешь ферзя, и партия фактически решена.")
        why = verify_claims(claims, 300, reveal=True)
        assert why and "after 8.Qxd5+" in why and "White stands worse" in why and "8...Qxd5" in why

    def test_op_show_italian(self, local_engine):
        ctx = _italian_ctx()
        [claims] = _sentences(ctx, "Но помни про ловушку: если сыграть Nd4, можно нарваться на Nxe5, и там уже начинается "
                                   "опасная для чёрных игра — так что не жадничай.")
        why = verify_claims(claims, 300, reveal=True)
        assert why and "4.Nxe5 is White's mistake" in why and "Black stands better" in why and "Qg5" in why
        # In a live game the engine's continuation stays out.
        assert "goes on" not in verify_claims(claims, 300, reveal=False)

    @pytest.mark.parametrize("sentence", [
        "Если сыграть Nd4, то после Nxd4 exd4 белые стоят лучше.",            # the real refutation of 3...Nd4
        "Если сыграть Nd4, то на Nxe5 у чёрных есть Qg5, и белые проигрывают.",  # the trap told the right way
    ])
    def test_true_outcomes_of_the_italian_pass(self, local_engine, sentence):
        [claims] = _sentences(_italian_ctx(), sentence)
        assert claims and verify_claims(claims, 300) is None

    def test_a_mate_at_the_end_holds(self, local_engine):
        [claims] = _sentences(CheckContext.from_fens([LEGAL]), "После Nxe5 Bxd1 Bxf7+ Ke7 Nd5# белые ставят мат.")
        assert claims and verify_claims(claims, 300) is None

    def test_pawn_b3_bare_the_material_reading_holds(self, local_engine):
        # «почти на четыре пешки хуже»: the engine says −6.3, but the line loses a whole bishop (−3) — a coach who
        # counts material is not clearly wrong, so the sentence stays (false positives are worse than misses).
        ctx = CheckContext.from_fens([RUY], question="А если b3?")
        [claims] = _sentences(ctx, "В лучшем случае белые отдают слона за пешку — это почти на четыре пешки хуже, чем было.")
        assert verify_claims(claims, 300) is None

    def test_a_swing_far_from_both_is_wrong(self, local_engine):
        ctx = CheckContext.from_fens([RUY], question="А если b3?")
        [claims] = _sentences(ctx, "Это всего на пешку хуже, чем было.")
        why = verify_claims(claims, 300)
        assert why and "pawns worse for White" in why and "in material -" in why  # −2 or −3: where the search stops


class TestNeverBlocks:
    def test_no_engine_no_verdict(self, monkeypatch):
        monkeypatch.setattr("src.hypothetical.analyze_timed", lambda *a, **k: {"error": "no engine"})
        [claims] = _sentences(CheckContext.from_fens([FRIED]), "После Qxd5+ белые выигрывают ферзя.")
        assert claims and verify_claims(claims) is None

    def test_an_engine_that_raises(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("engine died")
        monkeypatch.setattr("src.hypothetical.analyze_timed", _boom)
        [claims] = _sentences(CheckContext.from_fens([FRIED]), "После Qxd5+ белые выигрывают ферзя.")
        assert verify_claims(claims) is None


def _turn(monkeypatch, answer: str, message: str, fen: str, **flags):
    """One chat turn with a mocked agent streaming *answer*; returns the SSE frames."""
    from fastapi.testclient import TestClient

    from src.sessions import session_store
    from src.user_profile import UserProfile

    session = session_store.create(user_id="line-user")
    board = session.ensure_board()
    session.set_board_state(fen, board_id=board.id)
    agent = MagicMock()
    agent.tools = []
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = 0

    def _chat(msg, stream_callback=None):
        for i in range(0, len(answer), 7):
            stream_callback(answer[i:i + 7])
        return answer

    agent.chat.side_effect = _chat
    for name, value in {"COACH_TWO_STAGE": False, "COACH_ENGINE_NOTE": False, "COACH_ANSWER_CHECK": True,
                        "COACH_HYPOTHETICAL_NOTE": False, "COACH_MOVE_VERIFY": True, "COACH_LINE_VERDICT": True,
                        "COACH_ANSWER_FIX": False, **flags}.items():
        monkeypatch.setattr(config, name, value)
    with patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id="line-user")), \
            patch("src.server.log_event"):
        resp = TestClient(server.app).post(
            "/api/coach/chat", headers={"X-User-Id": "line-user"},
            json={"message": message, "session_id": session.id, "locale": "ru", "fen": fen},
        )
    assert resp.status_code == 200
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def _fried_scores():
    board = chess.Board(FRIED)
    after = board.copy(stack=False)
    after.push_san("Qxd5+")
    # White to move: +1.1 (8.Nc3); after 8.Qxd5+ Black to move: +6.2 for Black (8...Qxd5 9.Bxd5+ Kxd5).
    return {_key(board): (1.1, "b1c3"), _key(after): (6.2, "d8d5 c4d5 e6d5")}


class TestWiring:
    def test_text_coach_leaves_the_line_out(self, monkeypatch):
        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake_analysis(_fried_scores()))
        # (not advice to the recommendation check: nothing praises the move — the outcome is told for Black)
        answer = "Мата в два хода тут нет. После Qxd5+ чёрные теряют ферзя. Сначала разовьём фигуры."
        frames = _turn(monkeypatch, answer, "Тут есть мат в два хода?", FRIED)
        text = "".join(f.get("delta", "") for f in frames)
        assert "Мата в два хода тут нет." in text and "Сначала разовьём фигуры." in text
        assert "теряют ферзя" not in text

    def test_text_coach_kill_switch(self, monkeypatch):
        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake_analysis(_fried_scores()))
        answer = "Мата в два хода тут нет. После Qxd5+ чёрные теряют ферзя. "
        frames = _turn(monkeypatch, answer, "Тут есть мат в два хода?", FRIED, COACH_LINE_VERDICT=False)
        assert "теряют ферзя" in "".join(f.get("delta", "") for f in frames)

    def test_voice_check_reads_it_back(self, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake_analysis(_fried_scores()))
        monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
        monkeypatch.setattr(config, "COACH_LINE_VERDICT", True)
        monkeypatch.setattr("src.board_rules.tablebase", lambda board: None)  # no network: no ending here anyway
        client = TestClient(server.app)
        resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "line-user"},
                           json={"text": "После Qxd5+ чёрные теряют ферзя.", "fen": FRIED})
        assert resp.status_code == 200
        issues = resp.json()["issues"]
        assert issues and "White stands worse" in issues[0] and "goes on" not in issues[0]
        resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "line-user"},
                           json={"text": "Берёшь коня на d5 с шахом: Qxd5+.", "fen": FRIED})
        assert resp.json()["issues"] and "Qxd5+ is a mistake" in resp.json()["issues"][0]
        resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "line-user"},
                           json={"text": "После Nc3 белые стоят лучше.", "fen": FRIED})
        assert resp.json()["issues"] == []


# ── review 30.10: correct teaching the first version cut ────────────────────────────────────────────────────────────

FRIED_GAME = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7 Kxf7 7. Qf3+ Ke6 8. Qxd5+ Qxd5"
# 3...Nd4 on the board, White to move (Nxd4 is right, Nxe5? Qg5! the trap)
BLACKBURNE = "r1bqkbnr/pppp1ppp/8/4p3/2BnP3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"

ROOKS = "1r2k3/8/8/8/8/8/8/R3K2R w KQ - 0 1"
ROOKS_SENTENCE = ("Куда сильнее сразу врываться по открытым линиям — ладья идёт на h8 с шахом, чёрный король вынужден "
                  "уйти с e8, и тогда ладьи забирают ладью на b8.")


class TestReviewNoFalseCuts:
    """Each sentence is correct; the review of 30.10 found the first version cutting it."""

    @pytest.mark.parametrize("question, sentence", [
        # The student is Black: White's capture is asked about, «ты» is the side that wins the queen.
        ("Что если белые возьмут ферзём на d5?", "После Qxd5+ Qxd5 ты остаёшься с лишним ферзём."),
        ("Я пошёл королём на e6. Что если он возьмёт ферзём на d5?", "После Qxd5+ Qxd5 ты остаёшься с лишним ферзём."),
        ("Тут есть мат в два хода?", "Он может взять Qxd5+, но тогда ты забираешь ферзя, и партия решена."),
    ])
    def test_you_is_not_the_side_to_move_when_the_other_side_moves(self, question, sentence):
        assert _sentences(CheckContext.from_fens([FRIED], question=question), sentence) == [[]]

    @pytest.mark.parametrize("sentence", [
        "После 8.Qxd5+ Qxd5 9.Bxd5+ Kxd5 у белых нет ферзя, а после 8.Nc3 белые стоят лучше.",
        "Ход 8.Qxd5+ проигрывает ферзя после 8...Qxd5, а вот 8.Nc3 сохраняет атаку, и белые стоят лучше.",
        "8.Qxd5+ Qxd5 9.Bxd5+ Kxd5 оставляет белых без ферзя; правильно 8.Nc3, и у белых решающий перевес.",
    ])
    def test_two_branches_are_not_one_line(self, sentence):
        ctx = CheckContext.from_fens([FRIED], question="Тут есть мат в два хода?")
        assert _sentences(ctx, sentence) == [[]]

    @pytest.mark.parametrize("sentence", [
        "Берёшь Qxd5+, а он просто отвечает Qxd5 — и ферзя у тебя больше нет.",
        "Забираешь коня ферзём, Qxd5+, но чёрный ферзь бьёт обратно, и ты остаёшься без ферзя.",
        "Играешь Qxd5+, чёрные отвечают Qxd5, и вместо мата у тебя минус ферзь.",
        "Вот ты берёшь Qxd5+ — и сразу видно, почему так не играют: ферзь d8 защищает коня.",
    ])
    def test_a_refutation_told_in_the_second_person_is_not_advice(self, sentence):
        assert proposed_move(sentence, CheckContext.from_fens([FRIED], question="Можно ферзём взять коня на d5?")) is None

    @pytest.mark.parametrize("question", ["Разбери мою партию, где я ошибся?", "Что тут было?"])
    @pytest.mark.parametrize("sentence", [
        "Здесь ты играешь Qxd5+, и после Qxd5 партия переворачивается.",
        "Тут ты играешь 8.Qxd5+, а соперник отвечает 8...Qxd5.",
        "Здесь ты играешь Qxd5+.",  # the game's own next move
    ])
    def test_the_students_game_told_in_the_present_is_not_advice(self, question, sentence):
        ctx = CheckContext.from_fens([FRIED], [FRIED_GAME], question=question)
        assert proposed_move(sentence, ctx) is None

    def test_advice_in_the_second_person_still_is(self):
        # Not the game's move, no answer told: still the coach's advice (mate2-no).
        ctx = CheckContext.from_fens([FRIED], ["1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7 Kxf7 7. Qf3+ Ke6 8. Nc3"],
                                     question="Тут есть мат в два хода?")
        found = proposed_move("Берёшь коня на d5 с шахом: Qxd5+.", ctx)
        assert found and found[2] == "Qxd5+"

    @pytest.mark.parametrize("question, first, second", [
        ("А если Nxe5?", "Правильно здесь 4.Nxd4 exd4 5.O-O, и позиция примерно равная.",
         "А взятие пешки конём — это почти на две пешки хуже, чем было, из-за ответа ферзём на g5."),
        ("Можно взять конём на e5?", "Лучший ход здесь 4.Nxd4.", "Твоя идея взять на e5 примерно на две пешки хуже, чем было."),
    ])
    def test_a_number_is_not_held_against_the_line_recommended_before(self, question, first, second):
        ctx = CheckContext.from_fens([BLACKBURNE], question=question)
        _, claims = _sentences(ctx, first, second)
        assert [c for c in claims if c["kind"] == "swing"] == []

    @pytest.mark.parametrize("sentence", [
        "Ты говоришь, что после Qxd5+ белые выигрывают ферзя.",
        "Многие новички уверены, что после Qxd5+ белые выигрывают ферзя.",
        "Ты утверждаешь, что Qxd5+ выигрывает ферзя.",
        "По твоим словам, после Qxd5+ ты забираешь ферзя.",
        "Твоя идея такая: Qxd5+, и белые выигрывают ферзя.",
        "Это миф, что после Qxd5+ белые выигрывают ферзя.",
        "После Qxd5+ Qxd5 никто не скажет, что белые стоят лучше.",
    ])
    def test_what_someone_says_is_not_the_coachs_claim(self, sentence):
        assert _sentences(CheckContext.from_fens([FRIED], question="Я думаю, Qxd5+ выигрывает ферзя, да"), sentence) == [[]]

    def test_the_plan_instead_of_a_refuted_line(self):
        ctx = CheckContext.from_fens([FRIED], question="Что тут играть?")
        assert _sentences(ctx, "Брать 8.Qxd5+ нельзя: после 8...Qxd5 белые остаются без ферзя.",
                          "Поэтому дальше спокойно развиваешься и рокируешься, и у тебя перевес.")[1] == []

    @pytest.mark.parametrize("sentence", [
        "После 8.Qxd5+ Qxd5 9.Bxd5+ Kxd5 белым лучше сдаться.",
        "После Qxd5+ Qxd5 тебе лучше не спешить и вывести фигуры.",
        "После Qxd5+ Qxd5 ты лучше сразу подумай о защите.",
    ])
    def test_dative_better_is_advice(self, sentence):
        assert _sentences(CheckContext.from_fens([FRIED], question="Что если ферзь возьмёт на d5?"), sentence) == [[]]

    def test_the_nominative_is_still_an_evaluation(self):
        [claims] = _sentences(CheckContext.from_fens([FRIED]), "После Qxd5+ Qxd5 белые стоят лучше.")
        assert claims and claims[0]["side"] == chess.WHITE

    @pytest.mark.parametrize("sentence", [
        "После размена ферзей Qxd8+ Kxd8 позиция белых примерно на две пешки лучше, чем у чёрных: лишнее качество.",
        "После Qxd8+ Kxd8 белые стоят на две пешки лучше, чем чёрные.",
    ])
    def test_a_comparison_of_the_sides_is_not_a_swing(self, sentence):
        ctx = CheckContext.from_fens(["1nbqkbnr/ppp2ppp/8/4p3/4P3/8/PPP2PPP/R1BQKBNR w KQk - 0 5"], question="Стоит меняться ферзями?")
        [claims] = _sentences(ctx, sentence)
        assert [c for c in claims if c["kind"] == "swing"] == []

    def test_a_practical_warning_with_its_condition(self):
        ctx = CheckContext.from_fens([chess.STARTING_FEN], question="Расскажи про опасные гамбиты")
        assert _sentences(ctx, "Гамбит Стаффорда: 1.e4 e5 2.Nf3 Nf6 3.Nxe5 Nc6 4.Nxc6 dxc6 — неприятная для белых позиция, "
                               "если не знать ловушек.") == [[]]

    def test_the_engines_own_move_is_no_mistake(self, monkeypatch):
        # A short search under load: 4...Qg5 «gives away» 1.6 pawns (+0.7 → −0.9 for Black) while it is the engine's
        # own choice after 4.Nxe5 — noise, not the trap told backwards.
        board = chess.Board(ITALIAN_FEN)
        keys = []
        for san in ("Nd4", "Nxe5", "Qg5"):
            board.push_san(san)
            keys.append(_key(board))
        scores = {keys[1]: (0.7, "d8g5 e5f7"), keys[2]: (0.9, "c4f7 e8d8")}
        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake_analysis(scores))
        [claims] = _sentences(_italian_ctx(), "Если сыграть Nd4, то на Nxe5 у чёрных есть Qg5, и белые проигрывают.")
        assert claims and verify_claims(claims, 150) is None


    @staticmethod
    def _mate_then(monkeypatch, after_score):
        """Before Rh8+: a mate in 11 found by the short search; after it, *after_score* for Black to move."""
        def _analyze(fen, movetime_ms, multipv=1, min_depth=10):
            if fen.split()[0] == ROOKS.split()[0]:
                return {"lines": [{"multipv": 1, "depth": 17, "pv": "h1h7 e8d8 a1a8", "score": 100.0, "mate_in": 11}]}
            return {"lines": [{"multipv": 1, "depth": 13, "pv": "e8e7 h8b8 e7d7", "score": after_score}]}
        monkeypatch.setattr("src.hypothetical.analyze_timed", _analyze)

    def test_a_move_that_keeps_a_decided_win_is_no_mistake(self, monkeypatch):
        # castle-long-b1 (replay 30.10): Rh8+ is the engine's best move at depth 30 (#11); the 300 ms search found
        # the mate before it and +7.6 after it — «about 92.4 pawns given away» cut a true sentence.
        self._mate_then(monkeypatch, -7.6)
        found = proposed_move(ROOKS_SENTENCE, CheckContext.from_fens([ROOKS]))
        assert found and found[2] == "Rh8+"
        assert verify_recommendation(*found, 300, 150, True) is None
        board = chess.Board(ROOKS)
        assert verify_line(board, ["Rh8+", "Ke7", "Rxb8"], 300, 150) is None

    def test_a_move_that_throws_the_mate_away_still_is(self, monkeypatch):
        self._mate_then(monkeypatch, -1.0)
        found = proposed_move(ROOKS_SENTENCE, CheckContext.from_fens([ROOKS]))
        why = verify_recommendation(*found, 300, 150, True)
        assert why and "the forced mate is gone" in why and "pawns given away" not in why

    def test_a_dropped_sentences_line_is_not_the_next_ones(self):
        # The first sentence is cut (no bishop on c4 attacks h7) and never shown: «В итоге ты выигрываешь фигуру»
        # after it is about no line — not judged at the end of 4.Nxe5 Nxe5 (review 30.10, interplay).
        ctx = CheckContext.from_fens(["r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"],
                                     student_color=chess.WHITE)
        before = (ctx._line_end, ctx._line_advice, ctx.forced_line, ctx.line_scene)
        assert check_sentence("После 4.Nxe5 Nxe5 слон на c4 нападает на h7.", ctx)
        assert (ctx._line_end, ctx._line_advice, ctx.forced_line, ctx.line_scene) == before
        assert _sentences(ctx, "В итоге ты выигрываешь фигуру.") == [[]]

    def test_a_shown_sentences_line_still_is(self):
        ctx = CheckContext.from_fens(["r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"],
                                     student_color=chess.WHITE)
        [claims] = _sentences(ctx, "После 4.Nxe5 Nxe5 ход 5.d4 возвращает фигуру.", "В итоге ты выигрываешь фигуру.")[1:]
        assert claims and [m.uci() for m in claims[0]["moves"]][:2] == ["f3e5", "c6e5"]

@requires_sf
class TestReviewTrapsWithThePriceNext:
    """A trap told in two sentences: the grab, then its price. The grab is true as material."""

    def test_legal(self, local_engine):
        ctx = CheckContext.from_fens([chess.STARTING_FEN], question="Покажи мат Легаля")
        claims, _ = _sentences(ctx, "1.e4 e5 2.Nf3 d6 3.Bc4 Bg4 4.Nc3 g6 5.Nxe5 Bxd1 — чёрные выигрывают ферзя.",
                               "Но после 6.Bxf7+ Ke7 7.Nd5# белые ставят мат.")
        assert claims and verify_claims(claims, 300) is None

    def test_blackburne(self, local_engine):
        claims, _ = _sentences(_italian_ctx(), "После 3...Nd4 4.Nxe5 Qg5 5.Nxf7 Qxg2 6.Rf1 Qxe4+ 7.Be2 белые уже выигрывают ладью.",
                               "Однако следует 7...Nf3#, и это мат.")
        assert claims and verify_claims(claims, 300) is None

    def test_a_material_claim_the_line_does_not_make_is_still_judged(self, local_engine):
        # mate2-no: «ты забираешь ферзя» after 8.Qxd5+ — no queen taken in the line, and no mate: −6 is the answer.
        ctx = CheckContext.from_fens([FRIED], question="Тут есть мат в два хода?")
        _, claims = _sentences(ctx, "Берёшь коня на d5 с шахом: Qxd5+.",
                               "Король вынужден уйти с e6, после чего ты забираешь ферзя, и партия фактически решена.")
        assert verify_claims(claims, 300)


class TestReviewVoiceParity:
    def test_voice_keeps_a_refutation_in_the_second_person(self, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake_analysis(_fried_scores()))
        monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
        monkeypatch.setattr(config, "COACH_LINE_VERDICT", True)
        monkeypatch.setattr("src.board_rules.tablebase", lambda board: None)
        resp = TestClient(server.app).post(
            "/api/coach/voice/check", headers={"X-User-Id": "line-user"},
            json={"text": "Берёшь Qxd5+, а он просто отвечает Qxd5 — и ферзя у тебя больше нет.", "fen": FRIED,
                  "question": "Можно ферзём взять коня на d5?"})
        assert resp.status_code == 200 and resp.json()["issues"] == []
