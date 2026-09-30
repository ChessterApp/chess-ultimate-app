"""The answer check: sentences checked on the board before they are shown."""

from unittest.mock import MagicMock, patch

import json
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
        "Нет, Лe4 сыграть нельзя — ладья с d1 так не ходит.",
        "Следи за чёрными пешками f7–g7–h7.",
        "2. Nf6 — защита двух коней.",
        "Это тот же клубок, что 1.d4 Nf6 2.c4 e6 3.Nf3 d5 4.g3 — каталонский.",
    ])
    def test_not_stopped(self, sentence):
        assert check_sentence(sentence, _ctx(question="можно ли Лe4?")) == []

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
        assert gate.feed("нь с f3 бьёт d5.") == []  # a final "." may be a move number: wait
        assert gate.flush() == [("конь с f3 бьёт d5.", [], "Хороший вопрос, конь с f3 бьёт d5.")]

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
