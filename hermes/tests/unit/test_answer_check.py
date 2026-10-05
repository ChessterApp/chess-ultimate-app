"""The answer check: sentences checked on the board before they are shown."""

from unittest.mock import MagicMock, patch

import json
import chess
import pytest
from fastapi.testclient import TestClient

from src.answer_check import CheckContext, SentenceGate, _split_sentences, check_sentence
from src.quick_reply import QuickReply
from src.server import app
from src.sessions import session_store
from src.user_profile import UserProfile

# The quiet Italian that stood on the board on production (2026-09-30).
PIANISSIMO = "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2PP1N2/PP3PPP/RNBQ1RK1 w - - 2 7"
ELEPHANT = "rnbqkbnr/ppp2ppp/8/3pp3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3"


def _ctx(fen=PIANISSIMO, question=""):
    return CheckContext.from_fens([fen], question=question)


@pytest.mark.unit
class TestWrong:
    """What the coach said on production — each is caught."""

    def test_knight_jump(self):
        issues = check_sentence("Ход, о котором речь — это Nd5: конь с f3 прыгает на d5 и бьёт ферзя.", _ctx())
        assert issues == ["a knight cannot move from f3 to d5"]

    def test_knight_attack_across_a_dash(self):
        issues = check_sentence("Не путай с конём на c7 — вот он действительно бил бы и a8-ладью, и ферзя на d8.", _ctx())
        assert issues == ["a knight on c7 does not attack d8"]

    def test_wrong_opening_for_the_moves(self):
        issues = check_sentence("«Жареная печень» — это итальянская партия наоборот: 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 "
                                "4.c3 Nf6 5.d3 d6, и чёрные играют так же.", _ctx())
        assert len(issues) == 1 and "Fried Liver" in issues[0] and "Giuoco Pianissimo" in issues[0]

    def test_capture_no_piece_can_make(self):
        issues = check_sentence("If they recapture with ...Nxe5 you win the pawn back.", _ctx(ELEPHANT))
        assert issues and "...Nxe5 is impossible" in issues[0]

    @pytest.mark.parametrize("sentence", [
        "Ладья на d7 бьёт по пешкам c6 и b7.",
        "Слон на e3 контролирует d4 и d5.",
        "The knight on d4 attacks d5.",
    ])
    def test_attacks_against_the_pattern(self, sentence):
        assert check_sentence(sentence, _ctx())

    # The game tester (2026-10-01): "instead of b3, Rg1 — and the rook hits the
    # queen on h4". A hypothetical is a claim about the piece on its new square.
    ROOK_G1 = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 b - - 0 1"

    @pytest.mark.parametrize("sentence", [
        "Look at the board: after a4 gets taken, your rook sits on g1 hitting the queen on h4 — and Black's queen has to run.",
        "Your rook on g1 hits the queen on h4.",
        "After Rg1 the rook lands on g1, attacking the queen on h4.",
        "The rook would attack the queen from g1: the rook on g1 would hit h4.",
        "Rg1 attacks the queen on h4.",
        "Ладья на g1 будет бить ферзя на h4.",
        "После Rg1 ладья встаёт на g1 с нападением на ферзя h4.",
        "Rg1 нападает на ферзя h4.",
        "Лg1 нападает на ферзя h4.",
    ])
    def test_a_hypothetical_attack_against_the_pattern(self, sentence):
        issues = check_sentence(sentence, _ctx(self.ROOK_G1))
        assert "a rook on g1 does not attack h4" in issues, (sentence, issues)
        # "Your rook on g1" with no rook of the side to move there is a second, true complaint.
        assert all(i == "a rook on g1 does not attack h4" or "no rook of the student's on g1" in i for i in issues), issues


@pytest.mark.unit
class TestRight:
    """Correct coach sentences are never stopped."""

    @pytest.mark.parametrize("sentence", [
        "Смотри на доску: конь на d5 бьёт f6, e7, c7, b6, b4, c3 и e3.",
        "Ферзя d8 и ладей он не атакует.",
        "Слон c4 держит f7 на прицеле, и если чёрные сыграют ...h6, то Ng5 становится угрозой.",
        "Дальше слон уходит с c5 на a7 после ...a6 — там он и безопасен.",
        "Ключевой момент — пешка f2 у белых приколота слоном c5.",
        "Главные планы белых: c2–c3 и d2–d4, маневр коня b1–d2–f1–g3.",
        "Конь на f6 смотрит на e4 и g4, конь на c6 — на d4 и b4.",
        "Жареная печень: 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7! Kxf7 7.Qf3+ — "
        "конь на f7 бьёт ферзя d8 и ладью h8.",
        "Против неё лучше 5...Na5 или сразу 4...Bc5.",
        "После 1.e4 e5 2.Qh5 Nc6 3.Bc4 g6 4.Qf3 Nf6 детский мат не проходит.",
        "Против жареной печени проще сразу сыграть 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 — это джуоко пиано.",
        "The knight on f7 attacks the queen on d8 and the rook on h8, so Black takes it: 6...Kxf7.",
        "Пешка e5 у чёрных висит, её держит только конь c6.",
        "The pawn on e5 is defended by the knight on c6, which also covers d4.",
        # What the coach wrote on the benches: negated, passive, a table cell, a new subject after a comma.
        "Заметь: сам по себе Nf6 **не защищает f7**, но после него у тебя есть ресурс против связки.",
        "| Цель | ♗c4 давит на f7 | ♗c5 — зеркально |",
        "Ваша задача здесь — быстро развиться: Bc4 бьёт в слабое поле f7, d4 занимает центр, O-O уводит короля.",
        "If Black now plays 4...d5 5.exd5 Nxd5, the knight on d5 is hit by the bishop on c4.",
        "Чёрные берут пешку конём на d5, а белые бьют конём на f7 — король вынужден его забрать.",
        "Конь с g8 сразу бьёт в e4.",
        "Нет, Лe4 сыграть нельзя — ладья с d1 так не ходит.",
        "Следи за чёрными пешками f7–g7–h7.",
        "2. Nf6 — защита двух коней.",
        "Это тот же клубок, что 1.d4 Nf6 2.c4 e6 3.Nf3 d5 4.g3 — каталонский.",
    ])
    def test_not_stopped(self, sentence):
        assert check_sentence(sentence, _ctx(question="можно ли Лe4?")) == []

    @pytest.mark.parametrize("sentence", [
        # Right hypotheticals in the tester's game (the knight on c5 reaches a4 and
        # b3; a rook on e1 hits e4 and the e-file; a rook on g1 hits g7).
        "After Rg1 the rook sits on g1 hitting g7, and the knight on c5 is eyeing a4 and b3.",
        "Your rook on e1 will attack e4 only after the pawn moves.",
        "Ладья на e1 будет бить по линии e: e4, e5, e6.",
        "После ...Nxa4 конь встаёт на a4 с нападением на c3 и b2.",
        "Nxa4 attacks the queen on c3.",
        "Rd5 hits the knight on c5 and the pawn on d6.",
        "After Rg1 and ...Nxa4 you are a pawn down, but the rook on g1 is active.",
    ])
    def test_a_right_hypothetical_is_not_stopped(self, sentence):
        assert check_sentence(sentence, _ctx(TestWrong.ROOK_G1)) == []

    def test_a_line_written_in_the_answer_goes_on(self):
        ctx = _ctx(chess_start := "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        assert check_sentence("После 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5", ctx) == []
        assert check_sentence("белые берут 5.exd5, и на 5...Nxd5 решает 6.Nxf7.", ctx) == []
        assert chess_start

    def test_positions_from_tools_count(self):
        ctx = _ctx()
        assert check_sentence("Белые только что сыграли Qxf7#.", ctx)
        ctx.add_text('{"fen": "r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4"}')
        assert check_sentence("Белые только что сыграли Qxf7#.", ctx) == []


@pytest.mark.unit
class TestSentences:
    def test_split_keeps_move_numbers(self):
        done, rest = _split_sentences("Ход 1. e4 e5 2. Nf3 — хорош. Дальше 5... Na5! А теперь?\n- пункт\nКон")
        assert done == ["Ход 1. e4 e5 2. Nf3 — хорош. ", "Дальше 5... Na5! ", "А теперь?", "\n", "- пункт\n"]
        assert rest == "Кон"

    def test_gate_holds_from_where_a_claim_can_begin(self):
        gate = SentenceGate(_ctx())
        # Words before the first piece name stream at once; the claim is held.
        assert gate.feed("Смотри сюда: конь с f3 ") == [("Смотри сюда: ", [], "Смотри сюда: ")]
        assert gate.feed("прыгает на d5. Дальше") == [
            ("конь с f3 прыгает на d5. ", ["a knight cannot move from f3 to d5"], "Смотри сюда: конь с f3 прыгает на d5. ")]
        assert gate.flush() == [("Дальше", [], "Дальше")]

    def test_gate_never_releases_a_partial_word(self):
        gate = SentenceGate(_ctx())
        assert gate.feed("Хороший вопрос, ко") == [("Хороший вопрос, ", [], "Хороший вопрос, ")]
        assert gate.feed("нь с f3 бьёт e5.") == []  # a final "." may be a move number: wait
        assert gate.flush() == [("конь с f3 бьёт e5.", [], "Хороший вопрос, конь с f3 бьёт e5.")]

    def test_disabled_gate_passes_text_through(self):
        gate = SentenceGate(_ctx(), enabled=False)
        assert gate.feed("Конь с f3 ") == [("Конь с f3 ", [], "Конь с f3 ")]


@pytest.mark.unit
class TestTurn:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.config.COACH_ENGINE_NOTE", False)
    @patch("src.server.config.COACH_OPENING_PRESTEP", False)
    @patch("src.quick_reply.stream_completion")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_wrong_sentence_is_replaced(self, mock_profile, mock_agent, mock_fix):
        mock_profile.return_value = UserProfile(user_id="check-user")
        draft = ["Хороший вопрос. ", "Ход, о котором речь — Nd5: конь с f3 ", "прыгает на d5. ", "Дальше ерунда."]
        agent = MagicMock()

        def _chat(message, stream_callback=None):
            for part in draft:
                stream_callback(part)
            return "".join(draft)

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        seen = {}

        def _fix(**kwargs):
            seen["messages"] = kwargs["messages"]
            kwargs["on_delta"]("это удар конём на f7: конь на f7 бьёт ферзя d8 и ладью h8.")
            reply = QuickReply(model=kwargs["model"])
            reply.prompt_tokens, reply.completion_tokens = 100, 20
            return reply

        mock_fix.side_effect = _fix
        user = {"X-User-Id": "check-user"}
        sid = self.client.post("/api/coach/sessions", headers=user).json()["id"]
        resp = self.client.post("/api/coach/chat", headers=user, json={
            "message": "почему в жареной печени вилка?", "session_id": sid, "fen": PIANISSIMO,
        })
        text = "".join(json.loads(l[6:]).get("delta", "") for l in resp.text.splitlines() if l.startswith("data: "))
        assert "f3 прыгает" not in text and "ерунда" not in text
        # The claim-free start of the sentence was already out; the rewrite continues it.
        assert text == "Хороший вопрос. Ход, о котором речь — это удар конём на f7: конь на f7 бьёт ферзя d8 и ладью h8."
        fix_prompt = seen["messages"][1]["content"]
        assert "a knight cannot move from f3 to d5" in fix_prompt
        assert "Хороший вопрос. Ход, о котором речь —" in fix_prompt
        assert "Ход, о котором речь — Nd5: конь с f3 прыгает на d5." in fix_prompt
        stored = [m.content for m in session_store.get(sid, "check-user").messages if m.role == "assistant"]
        assert stored == [text.strip()]


@pytest.mark.unit
@pytest.mark.parametrize("text, clean", [
    ('id" string="false">3686097Нашёл — у Карлсена полно партий.', "Нашёл — у Карлсена полно партий."),
    ('<｜DSML｜invoke name="get_game_pgn"><｜DSML｜parameter name="game_id" string="false">3686097'
     '</｜DSML｜parameter></｜DSML｜invoke>Вот партия.', "Вот партия."),
    ("Обычный текст: конь на f3, «кавычки» и > знак.", "Обычный текст: конь на f3, «кавычки» и > знак."),
])
def test_tool_markup_written_as_text_is_cut(text, clean):
    from src.answer_check import strip_leaks

    assert strip_leaks(text) == clean


@pytest.mark.unit
class TestPlanningAsAnswer:
    """Production 2026-09-30: the model wrote its deliberation as the reply."""

    @pytest.mark.parametrize("text", [
        "Студент спрашивает о планах белых в испанской партии.",
        "Нужно ответить по-русски, коротко, с ходами из блока (d4, O-O).",
        "Стоит ли вызывать get_topic?",
        "Только факты из блока: конь c6 атакован слоном b5.",
        "The student asks about plans; I should answer briefly.",
    ])
    def test_meta_is_caught(self, text):
        from src.answer_check import META_ISSUE

        assert check_sentence(text, _ctx()) == [META_ISSUE]

    @pytest.mark.parametrize("text", [
        "Главное правило — король идёт вперёд.",
        "Блокада проходной пешки — конь на d5.",
        "Ты сам сказал, что хочешь подтянуть эндшпиль.",
        "Take on d5 with exd5, and Black has to recapture.",
    ])
    def test_coaching_is_not_meta(self, text):
        assert check_sentence(text, _ctx()) == []

    def test_gate_holds_a_planning_sentence_whole(self):
        from src.answer_check import META_ISSUE

        gate = SentenceGate(_ctx())
        # Nothing of «Студент спрашивает …» streams out before the sentence is judged.
        assert gate.feed("Студент спрашивает о планах ") == []
        out = gate.feed("белых в испанской партии. Дам планы")
        assert out[0] == ("Студент спрашивает о планах белых в испанской партии. ", [META_ISSUE],
                          "Студент спрашивает о планах белых в испанской партии. ")


@pytest.mark.unit
class TestRewriteOverlap:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.config.COACH_ENGINE_NOTE", False)
    @patch("src.server.config.COACH_OPENING_PRESTEP", False)
    @patch("src.quick_reply.stream_completion")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_rewrite_repeating_the_shown_start_is_trimmed(self, mock_profile, mock_agent, mock_fix):
        """A rewrite told to continue after «Take on» wrote «Take on d5 …» again (2026-09-30)."""
        mock_profile.return_value = UserProfile(user_id="overlap-user")
        agent = MagicMock()

        def _chat(message, stream_callback=None):
            stream_callback("Take on ")
            stream_callback("d5: the knight jumps from f3 to d5. ")
            return "Take on d5: the knight jumps from f3 to d5. "

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent

        def _fix(**kwargs):
            for part in ("Take on d5 ", "with exd5, and Black recaptures with the queen."):
                kwargs["on_delta"](part)
            return QuickReply(model=kwargs["model"])

        mock_fix.side_effect = _fix
        user = {"X-User-Id": "overlap-user"}
        sid = self.client.post("/api/coach/sessions", headers=user).json()["id"]
        resp = self.client.post("/api/coach/chat", headers=user, json={
            "message": "what should I play?", "session_id": sid, "fen": ELEPHANT, "locale": "en",
        })
        text = "".join(json.loads(l[6:]).get("delta", "") for l in resp.text.splitlines() if l.startswith("data: "))
        assert text == "Take on d5 with exd5, and Black recaptures with the queen."


@pytest.mark.unit
class TestVoiceCheckEndpoint:
    """The voice coach's spoken sentences go through the same check after the fact."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_wrong_sentence_reports_issues(self):
        resp = self.client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-check"}, json={
            "text": "Конь с f3 прыгает на d5 и бьёт ферзя.", "fen": PIANISSIMO,
        })
        assert resp.status_code == 200
        assert resp.json()["issues"] == ["a knight cannot move from f3 to d5"]

    def test_right_sentence_is_clean(self):
        resp = self.client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-check"}, json={
            "text": "Слон c4 держит f7 на прицеле, и если чёрные сыграют h6, то Ng5 становится угрозой.",
            "fen": PIANISSIMO, "question": "почему слон на c4 опасен?",
        })
        assert resp.json() == {"issues": []}


# ── Facts about the position (2026-10-02) ───────────────────────────────────
#
# The game tester's position (White to move after ...Qh4; the student is White).
ROOK_G1_W = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1"


def _game_ctx(fen=ROOK_G1_W, student=chess.WHITE, question=""):
    return CheckContext.from_fens([fen], question=question, student_color=student)


@pytest.mark.unit
class TestFactsWrong:
    @pytest.mark.parametrize("sentence, expect", [
        ("Black is up two pawns already.", "material: White has an extra 1 pawn; Black has an extra 1 knight"),
        ("Чёрные уже на две пешки впереди.", "material:"),
        ("You are a pawn down.", "material:"),
        ("У белых лишняя фигура.", "material:"),
        ("Материал равный, борьба впереди.", "(not equal)"),
        ("Your bishop on e1 attacks h4.", "there is no bishop of the student's on e1"),
        ("Твой конь на c5 хорошо стоит.", "the knight on c5 is Black's, not the student's"),
        ("The pawn on a4 is hanging and nothing defends it.", "the pawn on a4 is defended (by b3), not undefended"),
        ("Пешка a4 ничем не защищена.", "defended (by b3)"),
        ("Пешка c2 висит.", "the pawn on c2 is not attacked, so it is not hanging"),
        ("Ферзь на c3 защищён.", "the queen on c3 is not defended by anything"),
        ("Ферзь на h4 висит.", "the queen on h4 is not attacked, so it is not hanging"),
        ("The pawn on d6 is undefended.", "the pawn on d6 is defended (by c7), not undefended"),
        ("Конь на c5 связан.", "the knight on c5 is not pinned"),
        ("The knight on c5 is pinned.", "is not pinned"),
        ("Ладья на d5 бьёт d8.", "a rook on d5 does not reach d8: a piece is in the way"),
        ("The rook on d5 attacks the rook on c8.", "does not attack c8"),
        ("Rxd6# wins at once.", "Rxd6# is not checkmate"),
        ("Сыграй Rxd6+ с шахом.", "Rxd6+ gives no check"),
        ("Rxd6 — это мат.", "Rxd6# is not checkmate"),
        ("Rxd6 is checkmate.", "Rxd6# is not checkmate"),
    ])
    def test_caught(self, sentence, expect):
        issues = check_sentence(sentence, _game_ctx())
        assert issues and any(expect in i for i in issues), (sentence, issues)

    def test_a_relative_pin_counts(self):
        # Bg5 pins the f6 knight to the queen on d8: «связан» is right, «не связан» too would be left alone.
        fen = "rnbqkb1r/pppp1ppp/5n2/4p1B1/4P3/8/PPPP1PPP/RN1QKBNR b KQkq - 2 3"
        assert check_sentence("Конь на f6 связан.", CheckContext.from_fens([fen])) == []
        assert check_sentence("Слон g5 связывает коня f6.", CheckContext.from_fens([fen])) == []
        assert check_sentence("Конь на b8 связан.", CheckContext.from_fens([fen])) == ["the knight on b8 is not pinned"]

    def test_a_written_line_is_followed_from_its_last_move(self):
        start = CheckContext.from_fens(["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"])
        assert check_sentence("1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7#", start) == []
        start = CheckContext.from_fens(["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"])
        assert check_sentence("1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7+ — и это мат.", start) == []
        start = CheckContext.from_fens(["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"])
        assert check_sentence("1.e4 f6 2.Qh5+ — шах, чёрные закрываются g6.", start) == []
        start = CheckContext.from_fens(["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"])
        assert check_sentence("1.e4 f6 2.Qh5# — всё, мат.", start) == ["2.Qh5# is not checkmate"]


@pytest.mark.unit
class TestFactsRight:
    @pytest.mark.parametrize("sentence", [
        # material, read on the tester's board (White: +pawn, Black: +knight)
        "Black is a knight up for a pawn.", "У чёрных лишний конь, у белых лишняя пешка.",
        "Белые без фигуры, но с лишней пешкой.", "You are down a knight.",
        # hypotheticals are left alone
        "After Rxd6 you are up a pawn.", "Если бы ты взял на c5, был бы фигурой больше.",
        "Твой конь на c5 — если бы он туда попал — доминировал бы.",
        # whose piece, where
        "Твоя ладья на d5 стоит отлично.", "Your queen on c3 is overloaded.", "Мой конь на c5 бьёт a4 и b3.",
        "Твоя ладья на e1 была активнее на g1.",
        # hanging / defended
        "Пешка a4 висит, но защищена пешкой b3.", "Ферзь на h4 ничем не защищён.", "The queen on c3 is undefended.",
        "Пешка a4 защищена пешкой b3.", "Пешка d6 защищена.", "Пешка a6 защищена конём.", "The pawn on a4 is attacked but nothing defends h4.", "The knight on c5 is not pinned.", "Конь на c5 не связан.",
        # blockers: what the piece really reaches, and soft verbs look through
        "Ладья на d5 бьёт d6 и c5.", "Ладья на d5 смотрит на d8.", "The rook on e1 eyes e8.",
        "Ладья на e1 будет бить e8 после размена на e4.",
        # check and mate that are true
        "Rd8+ — шах, но ладья бьётся: Rxd8.",
        # a line explained, not on the board
        "Удар конём на f7: конь на f7 бьёт ферзя d8 и ладью h8.",
        "Пешка e5 у чёрных висит, её держит только конь c6.",
    ])
    def test_not_stopped(self, sentence):
        assert check_sentence(sentence, _game_ctx()) == [], sentence

    def test_without_the_student_colour_whose_claims_are_judged_for_the_side_to_move(self):
        ctx = CheckContext.from_fens([ROOK_G1_W])
        assert check_sentence("Твой конь на c5 хорошо стоит.", ctx) == ["the knight on c5 is Black's, not the student's"]
        assert check_sentence("Твоя ладья на d5 стоит отлично.", ctx) == []
        # «You» outside a game is the side to move (White here, a knight down for a pawn).
        assert check_sentence("You are a pawn down.", ctx) == [
            "material: White has an extra 1 pawn; Black has an extra 1 knight (not: you are a pawn down)"]
        assert check_sentence("You are a knight down for a pawn.", ctx) == []
        assert check_sentence("Black is up two pawns already.", ctx)  # the sides are named: still judged


@pytest.mark.unit
class TestArrows:
    def test_an_arrow_a_piece_cannot_draw_is_dropped(self):
        from src.board_markup import prune_arrows

        fen = ROOK_G1_W
        action = {"type": "draw_arrows", "arrows": [
            {"from": "e1", "to": "h4", "brush": "green"},   # the rook on e1 does not go to h4
            {"from": "e1", "to": "g1", "brush": "green"},   # it does go to g1
            {"from": "g1", "to": "h4", "brush": "red"},     # g1 is empty: a line of play, kept
            {"from": "c5", "to": "a4", "brush": "red"},     # the knight's jump
            {"from": "b3", "to": "b5", "brush": "blue"},    # a pawn two squares ahead is fine
            {"from": "b3", "to": "b2", "brush": "blue"},    # a pawn does not go back
        ]}
        pruned = prune_arrows(action, fen)
        assert [(a["from"], a["to"]) for a in pruned["arrows"]] == [("e1", "g1"), ("g1", "h4"), ("c5", "a4"), ("b3", "b5")]
        assert prune_arrows({"type": "draw_arrows", "arrows": [{"from": "e1", "to": "h4"}]}, fen) == {}
        assert prune_arrows({"type": "highlight_squares", "squares": ["e1"]}, fen) == {"type": "highlight_squares", "squares": ["e1"]}
        assert prune_arrows(action, None) is action


@pytest.mark.unit
class TestLanguage:
    """A sentence in the wrong language is treated like a wrong move: withheld and rewritten."""

    def test_english_in_a_russian_answer(self):
        ctx = CheckContext.from_fens([PIANISSIMO])
        ctx.language = "ru"
        assert check_sentence("The knight on f3 is well placed and the centre is yours for now.", ctx) == [
            "this sentence is in English; the whole answer must be in Russian"]
        assert check_sentence("Конь на f3 стоит отлично, центр пока за тобой.", ctx) == []
        # Names, moves, FENs and links are not language.
        assert check_sentence("Это называется Fried Liver Attack — жареная печень.", ctx) == []
        assert check_sentence("Партия тут: https://lichess.org/study/abcdefgh/ijklmnop — посмотри.", ctx) == []
        assert check_sentence("Позиция r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4 — итальянская.", ctx) == []
        assert check_sentence("Линия 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7 Kxf7 7.Qf3+ Ke6 8.Nc3 — острая.", ctx) == []

    def test_russian_in_an_english_answer_and_no_language_set(self):
        ctx = CheckContext.from_fens([PIANISSIMO])
        ctx.language = "en"
        assert check_sentence("Конь на f3 стоит отлично, центр пока за тобой и это хорошо.", ctx) == [
            "this sentence is not in English; the whole answer must be in English"]
        assert check_sentence("The knight on f3 is well placed.", ctx) == []
        ctx.language = None
        assert check_sentence("The knight on f3 is well placed and the centre is yours for now.", ctx) == []


# ── What the live run of 2026-10-04 let through ─────────────────────────────


@pytest.mark.unit
class TestLiveRunMisses:
    """Sentences the coach wrote on the stand (2026-10-04), each wrong on the
    tester's board, each passed by the checker then."""

    T_PRE = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/2Q2P1P/1PP2PK1/4R3 w - - 0 1"  # before b3

    @pytest.mark.parametrize("fen, sentence, expect", [
        (T_PRE, "Посчитаем материал: у Чёрных лишняя пешка, и после Rg1 Nxa4 у тебя действительно не хватает пешки.", "material:"),
        (ROOK_G1_W, "Впереди чёрные — у них на две пешки больше.", "material:"),
        (T_PRE, "This position is already badly lost for you (Black is up a couple of pawns and your a4 pawn is dropping anyway).", "material:"),
        (ROOK_G1_W, "The a4 pawn is attacked by the b6 pawn, but c2 defends it.", "a pawn on b6 does not attack a4"),
        (ROOK_G1_W, "The a4 pawn is attacked by the b6 pawn, but c2 defends it.", "the pawn on c2 does not reach a4"),
        (ROOK_G1_W, "К тому же твою ладью на d5 сейчас атакуют сразу две чёрные фигуры — конь c5 и пешка d6.", "a knight on c5 does not attack d5"),
        (ROOK_G1_W, "К тому же твою ладью на d5 сейчас атакуют сразу две чёрные фигуры — конь c5 и пешка d6.", "a pawn on d6 does not attack d5"),
        (ROOK_G1_W, "Белая ладья e1 при этом связана: чёрный ферзь с h4 давит на пешку f2, и та держит ладью.", "the rook on e1 is not pinned"),
        (ROOK_G1_W, "Обе легальны, но Rg1 — правильная: ладья уходит из-под связки и берёт на прицел g7.", "Qxg7 is not a legal move here"),
        (ROOK_G1_W, "Ты бьёшь коня ладьёй с f5, отгоняя фигуру.", "there is no rook on f5"),
        (ROOK_G1_W, "Be honest with yourself here: you're down a rook already, so grabbing material wildly won't save it.", "material:"),
        (ROOK_G1_W, "Чёрные отвечают спокойно и остаются с лишней ладьёй.", "material:"),
        (ROOK_G1_W, "Qxg7 легален, и это лучший ход.", "Qxg7 is not a legal move here"),
        (ROOK_G1_W, "You can play Qxg7 here.", "Qxg7 is not a legal move here"),
        # the rerun of 2026-10-04
        (ROOK_G1_W, "Your a4 pawn isn't hanging freely — the black knight on c5 is eyeing it, but your queen on c3 defends it.", "a queen on c3 does not attack a4"),
        (ROOK_G1_W, "Так что конь держится, а ладья на d5 стоит под боем, и защищать её нечем.", "the rook on d5 is not attacked"),
        # the third rerun of 2026-10-04
        (ROOK_G1_W, "Look at the board: the knight on c5 attacks a4, but your b3 queen guards it, so a4 is contested.", "there is no queen of the student's on b3"),
        (ROOK_G1_W, "Нет, конь на c5 не связан — наоборот, он сам нападает: бьёт твою ладью d5 и пешку e4.", "a knight on c5 does not attack d5"),
        ("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
         "Your bishop on c4 already pins the f7 pawn (because the knight on g8 defends it).", "a knight on g8 does not attack f7"),
    ])
    def test_caught(self, fen, sentence, expect):
        ctx = CheckContext.from_fens([fen], question="Могу ли я сыграть Rg1 сейчас? А Qxg7?", student_color=chess.WHITE)
        issues = check_sentence(sentence, ctx)
        assert any(expect in i for i in issues), (sentence, issues)

    @pytest.mark.parametrize("sentence", [
        # right on the tester's board (White to move, a knight down for a pawn)
        "Под боем у тебя пешки e4, f2, h3 и a4; пешку e4 бьют конь c5 и ферзь h4, а защищают пешка f3 и ладья e1.",
        "Пешка f2 связана: она прикрывает твою ладью на e1 от ферзя h4.",
        "The knight on c5 is attacked by the rook on d5 and the queen on c3, and defended by the b6 and d6 pawns.",
        "Твою ладью на d5 никто не атакует.",
        "Конь на c5 атакован и ладьёй d5, и ферзём c3, а защищают его две чёрные пешки — b6 и d6.",
        "b3 defends a4.", "Пешка b3 защищает a4.",
        "You are a knight down for a pawn; Black has an extra knight.",
        "Rg1 легален, а вот Qxg7 — нет: пешка f6 перекрывает диагональ.",
        "Можно сыграть Rg1 — ладья уходит с e1.",
        "После Rg1 Nxa4 у чёрных лишняя пешка.",
        "Твой конь на c5 — если бы он туда попал — доминировал бы.",
        "Если бы ладья стояла на f5, ты бил бы его ладьёй с f5.",
        "Если чёрные ответят конём на e6, ты бьёшь его ладьёй с f5, отгоняя фигуру.",
        "Конь на c5 не связан — он сам нападает: бьёт пешку e4 и поле b3.",
        "Your c3 queen eyes the c5 knight, and your b3 pawn guards a4.",
        "If Black now plays ...Nxa4, the pawn on b3 is attacked by the knight on a4.",
        "Пешка e4 под боем: её бьют конь c5 и ферзь h4, а защищают пешка f3 и ладья e1.",
        "Your f2 pawn is under attack from the queen on h4 and pinned to the rook on e1.",
        "So if ...Nxa4, you recapture with bxa4 and you're fine.",
    ])
    def test_not_stopped(self, sentence):
        ctx = CheckContext.from_fens([ROOK_G1_W], question="Могу ли я сыграть Rg1 сейчас? А Qxg7?", student_color=chess.WHITE)
        assert check_sentence(sentence, ctx) == [], sentence


@pytest.mark.unit
def test_a_pronoun_opening_a_sentence_means_the_previous_sentences_square():
    ctx = CheckContext.from_fens([ROOK_G1_W], student_color=chess.WHITE)
    assert check_sentence("No — a4 isn't hanging.", ctx) == []
    assert ctx.topic == "a4"
    issues = check_sentence("It's attacked by the b6 pawn, but c2 defends it, and there's no black piece adding pressure there.", ctx)
    assert "a pawn on b6 does not attack a4" in issues and "the pawn on c2 does not reach a4" in issues
    # The true version is not stopped.
    ctx = CheckContext.from_fens([ROOK_G1_W], student_color=chess.WHITE)
    check_sentence("Пешка a4 под боем.", ctx)
    assert check_sentence("Её атакует конь c5, а защищает пешка b3.", ctx) == []


@pytest.mark.unit
def test_the_topic_is_what_the_sentence_hits_not_who_hits():
    ital = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 3 3"
    ctx = CheckContext.from_fens([ital])
    assert check_sentence("Твой конь с f3 действительно бьёт e5 — пешка выглядит «висящей».", ctx) == []
    assert ctx.topic == "e5"
    assert check_sentence("Но она не висит: её прикрывает конь с c6.", ctx) == []


@pytest.mark.unit
def test_a_short_claim_free_start_waits_for_its_sentence():
    """«А вот твоя ладья d5 под боем…» was cut, but «А вот твоя » had already gone
    out and dangled before the rewrite (stand, 2026-10-04)."""
    gate = SentenceGate(_ctx(ROOK_G1_W))
    assert gate.feed("А вот твоя ладья ") == []
    assert gate.feed("d5 под боем, защищать её нечем. ") == [
        ("А вот твоя ладья d5 под боем, защищать её нечем. ",
         ["the rook on d5 is not attacked, so it is not hanging"], "А вот твоя ладья d5 под боем, защищать её нечем. ")]
    # A longer start still streams at once.
    gate = SentenceGate(_ctx(ROOK_G1_W))
    assert gate.feed("Хороший вопрос, и ответ на него простой: ладья ") == [
        ("Хороший вопрос, и ответ на него простой: ", [], "Хороший вопрос, и ответ на него простой: ")]


class TestHypotheticalPhrasings:
    """The client's example of 2026-10-01 («поставь ладью на g1 — она нападает
    на ферзя h4») in the phrasings that still passed the checker on 2026-10-04:
    the piece named without a square after a written move, the attacker named
    by kind only, a capture written through a piece of one's own."""

    H4 = "r1b1k1nr/pppp1ppp/2n5/2b1p3/4P2q/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 0 5"  # black queen h4, white Nf3, Nc3, Bf1

    def _ctx(self, question="что если поставить ладью на g1?"):
        return CheckContext.from_fens([self.H4], question=question, student_color=chess.WHITE)

    @pytest.mark.parametrize("sentence, expect", [
        ("Если сыграть Rg1, ладья нападает на ферзя h4.", "a rook on g1 does not attack h4"),
        ("Если сыграть Rg1, ладья нападает на ферзя.", "a rook on g1 does not attack h4"),  # the one black queen
        ("Rg1 — и ладья нападает на ферзя h4.", "a rook on g1 does not attack h4"),
        ("If you play Rg1, the rook attacks the queen on h4.", "a rook on g1 does not attack h4"),
        ("После Rg1 ферзь h4 под ударом ладьи.", "no rook attacks h4"),
        ("After Rg1 the queen on h4 is under attack from the rook.", "no rook attacks h4"),
        ("Пешка f7 под ударом слона.", "no bishop attacks f7"),
        ("Если сыграть Nd5, конь нападает на слона c5.", "a knight on d5 does not attack c5"),
        ("Возьми ферзя ладьёй: Rxh4.", "Rxh4 is not possible here: the pawn on h2 is in the way of the rook on h1"),
        ("Rxh4 и ферзь потерян.", "Rxh4 is not possible here"),
    ])
    def test_caught(self, sentence, expect):
        issues = check_sentence(sentence, self._ctx())
        assert any(expect in i for i in issues), (sentence, issues)

    @pytest.mark.parametrize("sentence", [
        "Ферзь h4 атакован конём.",  # Nf3 does hit h4
        "Ферзь h4 под ударом коня f3.",
        "Пешка e5 атакована конём.",
        "Сыграй Nd5 — конь атакует пешку c7.",
        "После Nd5 конь на d5 бьёт c7 и f6.",
        "If you play Nd5, the knight attacks the pawn on c7.",
        "Rxh4 после h3 не проходит.",  # the move is being refuted
        "А если Rxh4? Нет: пешка h2 мешает.",
        "Ладья и слон бьют по h4.",  # two pieces: not one piece's claim
        "Ладья может пойти на g1, а ферзь — на e2.",
        "Ход Rg1 создаёт угрозу ферзю h4.",  # «создаёт угрозу Кf6» names a move, not a square: not judged
        "После Kxf7 белые бьют ферзём с шахом — Qf3+ — и король обязан идти на e6.",  # «ферзём» is the instrument
        "Пешка f7 держит удар только королём.",
        "А вот Qxg7 — хода нет: на f6 стоит чёрная пешка, она просто закрывает ферзю дорогу.",
    ])
    def test_right_or_unjudged_sentences_pass(self, sentence):
        assert check_sentence(sentence, self._ctx()) == [], sentence

    def test_the_students_own_move_is_not_judged_as_the_coachs(self):
        ctx = self._ctx(question="а если Rxh4?")
        assert check_sentence("Rxh4 здесь невозможен — пешка h2 стоит на пути.", ctx) == []
        assert check_sentence("Rxh4 не сыграть.", ctx) == []


class TestNotAttacked:
    """«ничто не атакует», "nothing is attacking it", «не под боем» (live bench
    2026-10-04: "Your a4 pawn is fine — nothing is attacking it" with the knight
    on c5 hitting it)."""

    T = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1"

    @pytest.mark.parametrize("sentence, expect", [
        ("Your a4 pawn is fine — nothing is attacking it.", "the pawn on a4 IS attacked — by the knight on c5"),
        ("Пешка a4 не под боем.", "the pawn on a4 IS attacked"),
        ("The knight on c5 is not attacked.", "the knight on c5 IS attacked — by the queen on c3, the rook on d5"),
        ("Nothing attacks e4.", "the pawn on e4 IS attacked"),
        ("Ничто не атакует твою пешку e4.", "the pawn on e4 IS attacked"),
    ])
    def test_caught(self, sentence, expect):
        ctx = CheckContext.from_fens([self.T], question="Is my pawn on a4 hanging?", student_color=chess.WHITE)
        issues = check_sentence(sentence, ctx)
        assert any(expect in i for i in issues), (sentence, issues)

    @pytest.mark.parametrize("sentence", [
        "Твоя ладья d5 в безопасности.",  # «в безопасности» / "safe" can mean defended: not judged
        "Is it safe? Yes — nothing can hit it easily.",  # f7 in the Italian: attacked but defended
        "It's not a real threat yet (nothing attacks f7 a second time).",
        "The pawn on a4 is not attacked by the queen.",  # a named attacker is another claim
        "Пешку a4 никто не атакует, кроме коня.",
        "После Rg1 пешка a4 не под боем.",  # hypothetical
        "Ничто не угрожает твоему королю на g2.",  # true
        "Your king on g2 is safe.",
    ])
    def test_right_or_unjudged(self, sentence):
        ctx = CheckContext.from_fens([self.T], question="Is my pawn on a4 hanging?", student_color=chess.WHITE)
        assert check_sentence(sentence, ctx) == [], sentence


class TestNotDefended:
    """"Right now nothing defends a4" with the pawn on b3 defending it (production, 2026-10-04)."""

    T = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1"

    @pytest.mark.parametrize("sentence, expect", [
        ("Right now nothing defends a4, so if Black plays ...Nxa4 the pawn drops.", "the pawn on a4 IS defended — by the pawn on b3"),
        ("Пешку a4 никто не защищает.", "the pawn on a4 IS defended"),
        ("Nothing of yours defends the rook on d5.", "the rook on d5 IS defended — by the pawn on e4"),
    ])
    def test_caught(self, sentence, expect):
        ctx = CheckContext.from_fens([self.T], question="Is my pawn on a4 hanging?", student_color=chess.WHITE)
        issues = check_sentence(sentence, ctx)
        assert any(expect in i for i in issues), (sentence, issues)

    @pytest.mark.parametrize("sentence", [
        "Nothing defends the rook on d6 after Rxd6.",  # hypothetical
        "Ладью d6 никто не защищает, кроме ферзя.",
        "Nothing defends f2 except the king.",
    ])
    def test_unjudged(self, sentence):
        ctx = CheckContext.from_fens([self.T], question="", student_color=chess.WHITE)
        assert check_sentence(sentence, ctx) == [], sentence


class TestGateHoldsMaterialClaims:
    """«Да, ты выигрываешь — у тебя лишняя ладья…» to a student playing Black with no
    rook (production, 2026-10-05): the start went out before the check. A material
    or result word now starts the held part, like a piece or a square."""

    T3 = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1"

    def test_nothing_of_the_wrong_sentence_is_shown(self):
        ctx = CheckContext.from_fens([self.T3], question="Я тут выигрываю, правда?")
        gate = SentenceGate(ctx)
        text = "Да, ты выигрываешь — у тебя лишняя ладья против трёх пешек — этого достаточно для победы. План простой."
        out = []
        for i in range(0, len(text), 6):
            out += gate.feed(text[i:i + 6])
        out += gate.flush()
        shown = "".join(t for t, issues, _ in out if not issues)
        assert "выигрываешь" not in shown and "лишняя" not in shown
        assert any("material:" in i for _, issues, _ in out for i in issues)
        assert shown.strip().endswith("План простой.")  # «Да, » up to the comma may go out, as designed

    def test_the_rewrite_is_told_whose_side_the_student_is(self):
        from src.answer_check import fix_messages

        msgs = fix_messages("turn", "shown", "wrong", ["material: White has an extra 1 rook"], "lang",
                            "The student plays Black (the side to move on the board): «ты» means Black; White is the opponent.")
        assert "The student plays Black" in msgs[1]["content"]


class TestPlanThroughOwnKing:
    """"After Rg1 … the rook is ready to swing to g3 or g4" with the king on g2
    (production, 2026-10-05). Only the own king in the way, or a square the piece
    cannot reach at all, is judged — a pawn or a piece in the way may move first."""

    T = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/2Q2P1P/1PP2PK1/4R3 w - - 0 1"

    @pytest.mark.parametrize("sentence, expect", [
        ("After Rg1 the knight grabbing a4 costs Black time, and the rook is ready to swing to g3 or g4 to hit the queen.",
         "a rook on g1 cannot go to g3: its own king on g2 is in the way"),
        ("После Rg1 ладья перейдёт на g3 и нападёт на ферзя.", "a rook on g1 cannot go to g3: its own king on g2 is in the way"),
        ("После Rg1 ладья пойдёт на h2.", "a rook on g1 cannot go to h2"),
    ])
    def test_caught(self, sentence, expect):
        ctx = CheckContext.from_fens([self.T], question="что делать?", student_color=chess.WHITE)
        issues = check_sentence(sentence, ctx)
        assert any(expect in i for i in issues), (sentence, issues)

    @pytest.mark.parametrize("sentence", [
        "После Rf1 ладья перейдёт на f2.",  # a pawn on f2 of one's own: a plan to move it first — not judged
        "После Rd1 ладья пойдёт на d7.",  # d5 rook (own piece, not the king) in the way: let be
        "Ладья перейдёт на g3.",  # no written move binds the rook: not judged
        "Нет, конь на f7 — плохая идея: там его съест король, и ты останешься без фигуры.",  # a future, not the material now
        "After Rg1 the knight goes to e6.",  # knights are never judged here: the written move may be another knight's
        "Play 5...Na5 instead of 5...Nxd5 — your knight goes to a5 hitting the bishop.",
    ])
    def test_unjudged(self, sentence):
        ctx = CheckContext.from_fens([self.T], question="что делать?", student_color=chess.WHITE)
        issues = [i for i in check_sentence(sentence, ctx) if "cannot go to" in i]
        assert issues == [], (sentence, issues)


class TestEvalClaims:
    """«у белых лучше», «позиция равная», «ты выигрываешь» against the engine's
    evaluation of the turn (2026-10-05)."""

    T = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1"

    def _ctx(self, ev, student=chess.WHITE):
        ctx = CheckContext.from_fens([self.T], question="кто лучше?", student_color=student)
        ctx.engine_eval = ev
        return ctx

    @pytest.mark.parametrize("sentence, ev, expect", [
        ("У белых лучше.", -2.0, "White is worse, not better"),
        ("Перевес у белых.", -2.0, "White is worse, not better"),
        ("Позиция примерно равная.", -3.0, "not equal"),
        ("The position is balanced.", 2.5, "not equal"),
        ("Ты выигрываешь.", 0.3, "White is not winning"),
        ("Black is winning here.", 0.5, "Black is not winning"),
        ("У чёрных хуже.", -1.5, "Black is better, not worse"),
        ("Ты проигрываешь.", 0.2, "White is not lost"),
    ])
    def test_caught(self, sentence, ev, expect):
        issues = check_sentence(sentence, self._ctx(ev))
        assert any(expect in i for i in issues), (sentence, issues)

    @pytest.mark.parametrize("sentence, ev", [
        ("У чёрных перевес.", -1.5),
        ("У белых не лучше.", -2.0),
        ("Позиция равная.", 0.3),
        ("После Rg1 у белых лучше.", -2.0),  # a hypothetical
        ("Ты выигрываешь.", 2.0),
        ("White is slightly better.", 0.4),  # too close to call either way
    ])
    def test_right_or_unjudged(self, sentence, ev):
        assert check_sentence(sentence, self._ctx(ev)) == [], sentence

    def test_without_an_evaluation_nothing_is_judged(self):
        ctx = CheckContext.from_fens([self.T], question="кто лучше?", student_color=chess.WHITE)
        assert check_sentence("У белых лучше.", ctx) == []

    def test_written_line_after_a_move(self):
        from src.answer_check import written_line_after

        assert written_line_after("После Nf7 Kxf7 Qxc5 у тебя перевес.", "Nxf7") == ["Nf7", "Kxf7", "Qxc5"]
        assert written_line_after("Сыграй 1.Nf7 Kxf7 2.Qxc5 — и перевес.", "Nf7") == ["Nf7", "Kxf7", "Qxc5"]
        assert written_line_after("Сыграй Nf7 — конь бьёт ладью.", "Nf7") == []
