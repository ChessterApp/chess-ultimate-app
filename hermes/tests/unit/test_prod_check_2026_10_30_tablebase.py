"""Outcome claims in endings of ≤ 7 pieces, judged by the tablebase (src/endgame_claims.py, 2026-10-30).

Production check of 29.10, set B «square»: «Я чёрными, мой ход. Догонит ли мой король пешку?» on
8/8/8/P3k3/8/8/8/7K b — «Нет, не догонит. Твоя пешка проходит.» with the tablebase draw (1...Kd5 and 1...Kd6
catch the pawn). The result check read only «это выигрыш / ничья»; the race verdict passed. The stand corpus had
the mirror error on 8/8/8/P4k2/8/8/8/7K b (a tablebase win for White): «Да, успеет — и даже с запасом.»

No network: the tablebase answers from the tables below (src/board_rules.tablebase and its cache are patched).
"""

import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import board_rules
from src.answer_check import CheckContext, SentenceGate, check_sentence
from src.endgame_claims import judge_pending, outcome_issues, pop_pending, tablebase_from_cache

SQUARE = "8/8/8/P3k3/8/8/8/7K b - - 0 1"         # draw: Kd5, Kd6 catch the pawn
SQUARE_NO = "8/8/8/P4k2/8/8/8/7K b - - 0 1"      # White wins: every king move is too late
OPPOSITION = "8/8/4k3/8/4P3/4K3/8/8 w - - 0 1"   # draw
LUCENA = "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"    # White wins
TWO_KNIGHTS = "8/8/8/8/8/2k5/8/K1N1N3 w - - 0 1"  # draw
FORK_END = "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"     # draw (Nc7+ Nxa8 leaves K+N v K)
# The square after 1...Kd5 2.a6 Kc6 (draw) and after 1...Kd4 2.a6 (White wins).
AFTER_KD5_A6_KC6 = "8/8/P1k5/8/8/8/8/7K w - - 1 3"
AFTER_KD4_A6 = "8/8/P7/8/3k4/8/8/7K b - - 0 2"

Q_SQUARE = "Я чёрными, мой ход. Догонит ли мой король пешку?"
Q_SQUARE_NO = "Я чёрными, мой ход. Король успеет к пешке?"

_DRAW = {"category": "draw", "dtz": 0, "dtm": None, "best_category": "draw"}
TB = {
    SQUARE: {**_DRAW, "best_san": "Kd5", "keeping": ["Kd5", "Kd6"]},
    SQUARE_NO: {"category": "loss", "dtz": -12, "dtm": -25, "best_san": "Ke5", "best_category": "win", "keeping": []},
    OPPOSITION: {**_DRAW, "best_san": "Kd3", "keeping": []},
    LUCENA: {"category": "win", "dtz": 1, "dtm": 19, "best_san": "Rd1+", "best_category": "loss", "keeping": ["Rd1+"]},
    TWO_KNIGHTS: {**_DRAW, "best_san": "Kb1", "keeping": []},
    FORK_END: {**_DRAW, "best_san": "Nc7+", "keeping": []},
    AFTER_KD5_A6_KC6: {**_DRAW, "best_san": "a7", "keeping": []},
    AFTER_KD4_A6: {"category": "loss", "dtz": -3, "dtm": -20, "best_san": "Kc5", "best_category": "win", "keeping": []},
}
_BY_EPD = {chess.Board(f).epd(): v for f, v in TB.items()}


@pytest.fixture(autouse=True)
def _tablebase(monkeypatch):
    """The tablebase from the table; its cache empty, so a line's end is looked up only in the engine stage."""
    asked = []

    def lookup(board):
        asked.append(board.epd())
        found = _BY_EPD.get(board.epd())
        board_rules._tb_cache[board.epd()] = found
        return found

    monkeypatch.setattr(board_rules, "tablebase", lookup)
    monkeypatch.setattr(board_rules, "_tb_cache", {})
    return asked


def _ctx(fen, question, cache_current=True):
    ctx = CheckContext.from_fens([fen], question=question)
    raw = TB[fen]
    ctx.tablebase = board_rules.tablebase_white_result(ctx.current, raw)
    ctx.engine_eval = 0.0 if ctx.tablebase == "draw" else (20.0 if ctx.tablebase.startswith("White") else -20.0)
    if cache_current:
        board_rules._tb_cache[ctx.current.epd()] = raw  # the turn's engine note asked it (src/voice_engine_note.py)
    return ctx


def _sentences(ctx, text):
    """Each sentence of *text* with its issues, checked in order as the gate does."""
    from src.answer_check import _split_sentences

    sents, rest = _split_sentences(text + " ")
    return [(s.strip(), check_sentence(s, ctx)) for s in sents + [rest] if s.strip()]


# ── The production answers ──────────────────────────────────────────────────

SQUARE_ANSWER = (
    "Нет, не догонит. Твоя пешка проходит.\n\n"
    "Твой король на e5 слишком далеко: пешка a5 идёт вперёд с темпом, а белый король успевает вернуться и встать на "
    "путь. Чтобы удержать ничью, тебе нужно догонять пешку по кратчайшему пути — Kd5 или Kd6.\n\n"
    "Обе эти дороги ведут к пешке напрямую: после Kd5 a6 ты идёшь Kc6, и король встаёт перед пешкой — ничья. "
    "А вот если король пойдёт в другую сторону — на e4 или f5 — он только удаляется от пешки, и тогда белые спокойно "
    "проводят её в ферзи. Поэтому не гонись за ней по диагонали: вставай на одну вертикаль с пешкой и двигайся прямо к ней.")


def test_prod_square_the_verdict_and_the_pawn_are_cut_with_the_truth():
    ctx = _ctx(SQUARE, Q_SQUARE)
    out = _sentences(ctx, SQUARE_ANSWER)
    first, second = out[0], out[1]
    assert first[0] == "Нет, не догонит."
    assert first[1] == ["the sentence says the black king does not catch the white pawn on a5, so White wins, but the "
                        "endgame tablebase (exact) says it is a draw with best play — Black holds it only with Kd5, Kd6; "
                        "every other move loses"]
    assert second[0] == "Твоя пешка проходит."
    assert "the white pawn on a5 queens, so White wins" in second[1][0]
    assert "it is a draw with best play" in second[1][0]
    assert "the pawn is White's, not the student's (the student plays Black)" in second[1][0]


def test_prod_square_the_rest_of_the_answer_is_not_judged_by_the_outcome_check():
    # Hypotheticals («если король пойдёт…»), a purpose («Чтобы удержать ничью…»), the line told in words
    # («…Kc6, и король встаёт перед пешкой — ничья»), the own king («белый король успевает вернуться»).
    ctx = _ctx(SQUARE, Q_SQUARE)
    for sentence, issues in _sentences(ctx, SQUARE_ANSWER)[2:]:
        assert not any("tablebase" in i for i in issues), sentence


@pytest.mark.parametrize("fen, question, answer", [
    (SQUARE_NO, Q_SQUARE_NO,
     "Нет, король не успевает — но не из-за гонки, а из-за того, что поле d6 под контролем. Играй Ke4, это самая "
     "упорная защита. Смотри: после Ke5 белые играют a6, и ты обязан идти Kd6 — иначе пешка просто идёт в ферзи."),
    (OPPOSITION, "Я играю белыми. Это выигрыш?",
     "Нет, это ничья — при точной игре чёрных пешку не провести. Всё решает одно: чёрный король успевает встать "
     "**перед** пешкой. Сейчас он на e6, вы двигаете e5 — и король просто идёт на e7, а потом не пускает ваш король "
     "вперёд. Ключ — ваш король не успевает поддержать пешку и одновременно оттеснить чёрного короля."),
    (LUCENA, "Как здесь выиграть? Объясни план.",
     "Продолжение: Rd1+ Ke7, Rd4 Ke6, Kc7 — и пешка проходит в ферзи."),
    (TWO_KNIGHTS, "Можно ли тут поставить мат двумя конями?",
     "Два коня — это тупик: ничейный эндшпиль, и здесь ты не выиграешь, даже если чёрный король неосторожно встанет "
     "на край."),
    (FORK_END, "Есть ли здесь вилка?",
     "Только помни, что в этом эндшпиле выигрыша нет — точной игрой чёрные держат ничью, так что вилка здесь спасает "
     "тебя, а не приносит победу."),
])
def test_prod_answers_that_agree_with_the_tablebase_pass(fen, question, answer):
    ctx = _ctx(fen, question)
    for sentence, issues in _sentences(ctx, answer):
        assert not any("endgame tablebase (exact)" in i for i in issues), (sentence, issues)


def test_stand_square_no_yes_he_makes_it_is_cut():
    # The stand corpus (out_71_stand, out_71_1028): «Да, успеет» where every king move loses.
    ctx = _ctx(SQUARE_NO, Q_SQUARE_NO)
    issues = check_sentence("Да, успеет — и даже с запасом.", ctx)
    assert issues and "the black king catches the white pawn on a5, so White does not win" in issues[0]
    assert "White wins with best play — every Black move loses" in issues[0]


# ── Paraphrases: the same class in other words and languages ────────────────

@pytest.mark.parametrize("sentence, meaning", [
    ("Твой король не успевает.", "the black king does not catch the white pawn on a5, so White wins"),
    ("Нет, король не догонит пешку a5.", "the black king does not catch the white pawn on a5, so White wins"),
    ("Пешку уже не остановить.", "the black king does not catch the white pawn on a5, so White wins"),
    ("Белая пешка проходит в ферзи.", "the white pawn on a5 queens, so White wins"),
    ("Пешка a5 превратится в ферзя.", "the white pawn on a5 queens, so White wins"),
    ("Спасения нет.", "Black cannot save the game, so White wins"),
    ("Ничью не удержать.", "Black cannot save the game, so White wins"),
    ("No, the king does not catch the pawn.", "the black king does not catch the white pawn on a5, so White wins"),
    ("The pawn queens.", "the white pawn on a5 queens, so White wins"),
    ("Жоқ, король пешканы қуып жете алмайды.", "the black king does not catch the white pawn on a5, so White wins"),
])
def test_paraphrases_in_the_draw_are_cut(sentence, meaning):
    ctx = _ctx(SQUARE, Q_SQUARE)
    issues = check_sentence(sentence, ctx)
    assert issues and meaning in issues[0] and "draw with best play" in issues[0], issues


@pytest.mark.parametrize("sentence", [
    "Король догонит пешку.",
    "Да, догонит: Kd5 или Kd6.",
    "Да, успеешь — но только одним точным ходом.",
    "Yes, your king catches the pawn.",
    "Ты удержишь ничью.",
    "Здесь не выиграть.",
])
def test_true_verdicts_in_the_draw_pass(sentence):
    assert check_sentence(sentence, _ctx(SQUARE, Q_SQUARE)) == []


@pytest.mark.parametrize("sentence", [
    "Нет, не успеет — белая пешка проходит в ферзи.",
    "Нет, не успеет — с точной защитой белые проводят пешку в ферзи.",
    "Спасения нет: любой ход проигрывает.",
])
def test_true_verdicts_in_the_win_pass(sentence):
    assert check_sentence(sentence, _ctx(SQUARE_NO, Q_SQUARE_NO)) == []


# ── Not claims about this board ─────────────────────────────────────────────

@pytest.mark.parametrize("sentence", [
    # a condition, a hypothetical, a purpose, advice, a rule in general
    "Если бы ход был у белых, пешка прошла бы в ферзи.",
    "Король догонит пешку, если войдёт в квадрат.",
    "А вот если король пойдёт на f5, белые спокойно проводят её в ферзи.",
    "Чтобы удержать ничью, тебе нужно догонять пешку по кратчайшему пути.",
    "Как правило, король не догонит пешку вне квадрата.",
    "В таких окончаниях пешка обычно проходит.",
    # a question, a quote, a comparison, a manner denied
    "Как думаешь, догонит ли король пешку?",
    "Правило звучит так: «если король не в квадрате, он не догонит пешку».",
    "Ферзь появляется раньше, чем король её догонит.",
    "Играй Kd5, и пешку ты не догонишь в лоб, а встанешь у неё на дороге.",
    # a move told in words before the claim, another piece's «успевает»
    "Король уходит слишком далеко от пешки — и догнать её ты уже не успеваешь.",
    "Белый король успевает вернуться и встать на путь.",
    # not the race: a line through the centre, an attack stopped
    "Диагональ проходит через центр.",
])
def test_not_claims_about_this_board_pass(sentence):
    assert check_sentence(sentence, _ctx(SQUARE, Q_SQUARE)) == []


def test_no_tablebase_or_a_big_board_is_not_judged():
    ctx = CheckContext.from_fens([SQUARE], question=Q_SQUARE)  # the lookup failed: no verdict
    assert check_sentence("Нет, не догонит.", ctx) == []
    big = CheckContext.from_fens(["r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2PP1N2/PP3PPP/RNBQ1RK1 w - - 2 7"],
                                 question="Догонит ли король пешку?")
    big.tablebase = "draw"
    assert outcome_issues("нет, не догонит.", big) == []


def test_material_that_does_not_decide_is_not_judged():
    # Black has a rook: the pawn queening does not decide the result (a rook for the new queen).
    ctx = CheckContext.from_fens([LUCENA], question="Как здесь выиграть?")
    ctx.tablebase = "draw"  # a made-up verdict: the claim must not be read as «White wins» at all
    assert outcome_issues("пешка проходит в ферзи.", ctx) == []


# ── A line written before the claim: judged at its end ──────────────────────

def test_a_claim_after_a_line_waits_for_the_tablebase_of_its_end(_tablebase):
    ctx = _ctx(SQUARE, Q_SQUARE)
    sentence = "После 1...Kd5 2.a6 Kc6 пешка проходит."
    assert check_sentence(sentence, ctx) == []  # no network inside the check
    pending = pop_pending(ctx, sentence)
    assert [(fen, line) for fen, _claim, line in pending] == [(AFTER_KD5_A6_KC6, "Kd5 a6 Kc6")]
    issue = judge_pending(pending)
    assert issue.startswith("the sentence says the white pawn on a6 queens, so White wins after Kd5 a6 Kc6, "
                            "but the endgame tablebase (exact) says it is a draw with best play")
    assert pop_pending(ctx, sentence) == []


def test_a_cached_line_end_is_judged_at_once():
    ctx = _ctx(SQUARE, Q_SQUARE)
    board_rules._tb_cache[chess.Board(AFTER_KD5_A6_KC6).epd()] = TB[AFTER_KD5_A6_KC6]
    issues = check_sentence("После 1...Kd5 2.a6 Kc6 пешка проходит.", ctx)
    assert issues and "after Kd5 a6 Kc6" in issues[0]
    assert check_sentence("После 1...Kd5 2.a6 Kc6 король догоняет пешку — ничья.", ctx) == []


def test_a_draw_named_after_a_line_is_judged_for_both_sides():
    ctx = _ctx(SQUARE, Q_SQUARE)
    sentence = "После 1...Kd4 2.a6 — ничья."
    assert check_sentence(sentence, ctx) == []
    issue = judge_pending(pop_pending(ctx, sentence))
    assert issue.startswith("the sentence says it is a draw after Kd4 a6, but the endgame tablebase (exact) says "
                            "White wins with best play")


def test_true_claim_after_a_line_passes():
    ctx = _ctx(SQUARE, Q_SQUARE)
    sentence = "После 1...Kd4? 2.a6 пешку уже не догнать."
    assert check_sentence(sentence, ctx) == []
    assert judge_pending(pop_pending(ctx, sentence)) is None  # White wins there: the claim is right


@pytest.mark.parametrize("sentence", [
    "Kd5 или Kd6 — и король догонит пешку.",          # two alternatives, not one line
    "После Kd5 и a6 ты успеваешь — пешка не пройдёт.",  # a move of the line the check did not follow
    "После Kd5 a6 ты идёшь Kc6, и король встаёт перед пешкой — ничья.",  # the line goes on in words
    "После Kd5, если белые ошибутся, пешка не пройдёт.",  # a condition between the line and the claim
])
def test_lines_that_do_not_say_where_they_end_are_not_judged(sentence):
    ctx = _ctx(SQUARE, Q_SQUARE)
    assert check_sentence(sentence, ctx) == []
    assert pop_pending(ctx, sentence) == []


# ── The tablebase reaches the check and the model ───────────────────────────

def test_the_cache_fills_the_check_when_the_engine_line_had_no_tablebase():
    ctx = CheckContext.from_fens([SQUARE], question=Q_SQUARE)
    tablebase_from_cache(ctx)
    assert ctx.tablebase is None  # never asked: nothing to read, and no network
    board_rules._tb_cache[chess.Board(SQUARE).epd()] = TB[SQUARE]
    tablebase_from_cache(ctx)
    assert ctx.tablebase == "draw" and ctx.engine_eval == 0.0


def test_the_live_game_note_carries_the_tablebase_result(monkeypatch):
    from src import hypothetical, voice_engine_note

    monkeypatch.setattr(voice_engine_note, "_tablebase_result", lambda board: "draw")
    monkeypatch.setattr(hypothetical, "analyze_timed",
                        lambda fen, ms, multipv=1, min_depth=None: {"lines": [{"score": 0.4, "pv": "e5d5", "depth": 20}]})
    monkeypatch.setattr("src.position_facts._threat", lambda board, score, analyse: None)
    note = hypothetical.live_game_note(SQUARE, 100)
    assert note["tablebase"] == "draw"
    assert "Endgame tablebase (exact, perfect play): DRAW" in note["note"]


@pytest.mark.unit
class TestPaths:
    def setup_method(self):
        from src.server import app

        self.client = TestClient(app)

    def test_voice_check_judges_the_race(self):
        resp = self.client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-tb"}, json={
            "text": "Нет, не догонит.", "fen": SQUARE, "question": Q_SQUARE})
        assert resp.status_code == 200
        issues = resp.json()["issues"]
        assert issues and "so White wins" in issues[0] and "draw with best play" in issues[0]
        resp = self.client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-tb"}, json={
            "text": "Да, догонит.", "fen": SQUARE, "question": Q_SQUARE})
        assert resp.json() == {"issues": []}

    def test_voice_check_asks_the_tablebase_for_a_line(self):
        resp = self.client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-tb"}, json={
            "text": "После 1...Kd5 2.a6 Kc6 пешка проходит.", "fen": SQUARE, "question": Q_SQUARE})
        issues = resp.json()["issues"]
        assert issues and "after Kd5 a6 Kc6" in issues[0]

    @patch("src.server.config.COACH_ENGINE_NOTE", False)
    @patch("src.server.config.COACH_OPENING_PRESTEP", False)
    @patch("src.quick_reply.stream_completion")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    @pytest.mark.parametrize("draft, said, issue", [
        # The board facts asked the tablebase about the board (no engine line this turn): the check reads the cache.
        (["Нет, не догонит. ", "Король далеко."], "не догонит",
         "the black king does not catch the white pawn on a5, so White wins"),
        # The line's end is asked in the engine stage, before the sentence goes out.
        (["Посмотри: после 1...Kd5 2.a6 Kc6 пешка ", "проходит. ", "Король далеко."], "пешка проходит",
         "the white pawn on a6 queens, so White wins after Kd5 a6 Kc6"),
    ])
    def test_text_turn_cuts_the_verdict_and_a_line_end(self, mock_profile, mock_agent, mock_fix, draft, said, issue):
        from src.quick_reply import QuickReply
        from src.user_profile import UserProfile

        mock_profile.return_value = UserProfile(user_id="tb-user")
        board_rules._tb_cache[chess.Board(SQUARE).epd()] = TB[SQUARE]
        agent = MagicMock()

        def _chat(message, stream_callback=None):
            for part in draft:
                stream_callback(part)
            return "".join(draft)

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        prompts = []

        def _fix(**kwargs):
            prompts.append(kwargs["messages"][1]["content"])
            kwargs["on_delta"]("Да, догонит: Kd5 или Kd6.")
            reply = QuickReply(model=kwargs["model"])
            reply.prompt_tokens, reply.completion_tokens = 100, 20
            return reply

        mock_fix.side_effect = _fix
        user = {"X-User-Id": "tb-user"}
        sid = self.client.post("/api/coach/sessions", headers=user).json()["id"]
        resp = self.client.post("/api/coach/chat", headers=user, json={
            "message": Q_SQUARE, "session_id": sid, "fen": SQUARE})
        text = "".join(json.loads(l[6:]).get("delta", "") for l in resp.text.splitlines() if l.startswith("data: "))
        assert said not in text
        assert prompts and issue in prompts[0]
