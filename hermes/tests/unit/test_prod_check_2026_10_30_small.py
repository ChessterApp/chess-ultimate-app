"""Prod re-check of Hermes 29.10, the small classes (30.10).

Material counted on the wrong board: in a game the checker accepted «теперь у чёрных на пешку больше» because a move
ago it was true (st3: two pawns up after 6...Nxe4), and «Материал пока равный — ты отдал пешку e5, но забрал f4» was
judged on the board before 2...exf4 (can-kg-accept). A promise to show something on the board with the board left as
it was (rule-promote: «Покажу на доске.»). «Пример вилки конём» answered with the lesson's double attack by a rook
(d3-example). The board named as a whole against what stands on it («это позиция «король против короля»»)."""

import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src.answer_check import PROMISE_ISSUE, CheckContext, SentenceGate, check_sentence, promises_board
from src.motifs import motif_piece, shows_motif
from src.server import app
from src.user_profile import UserProfile

# ── (a) Material: the board now in a game, the board after a capture told as made ─────────────────────────────

ST3_LINE = "1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4"
ST3_FEN = "rnbqk2r/ppp1bppp/3p4/8/2Bpn3/2P2N2/PP3PPP/RNBQ1RK1 w kq - 0 7"


def _game_ctx(line=ST3_LINE, student=chess.WHITE, question="0-0"):
    """The text path's context in a game: the board, the game's record as a line, its moves (src/server.py)."""
    moves = [t.split(".")[-1] for t in line.split()]
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    ctx = CheckContext.from_fens([board.fen()], [line], question=question, student_color=student)
    ctx.game_moves = moves
    first = 0 if student == chess.WHITE else 1
    ctx.game_engine_moves = [m for i, m in enumerate(moves) if i % 2 != first]
    return ctx


def _run(text, ctx):
    from src.answer_check import _split_sentences

    sents, rest = _split_sentences(text + " ")
    return [(s, check_sentence(s, ctx)) for s in sents + [rest] if s.strip()]


@pytest.mark.unit
class TestMaterialNow:
    BUBBLE = ("Рокировка сделана правильно — король на g1 в безопасности. Но чёрные ответили Nxe4: конь с f6 встал на "
              "e4 и забрал твою пешку e4. Так что теперь у чёрных на пешку больше, и позиция уже в их пользу. Посмотри "
              "внимательно: их конь на e4 застрял в центре — чем ты можешь его прогнать или разменять?")

    def test_prod_st3_one_pawn_said_two_on_the_board(self):
        ctx = _game_ctx()
        assert ctx.current.fen() == ST3_FEN
        out = dict(_run(self.BUBBLE, ctx))
        bad = [s for s, issues in out.items() if issues]
        assert bad == ["Так что теперь у чёрных на пешку больше, и позиция уже в их пользу. "]
        assert out[bad[0]] == ["material: Black has an extra 2 pawns (not: у черных на пешку больше)"]

    @pytest.mark.parametrize("sentence", [
        "Теперь чёрные на пешку впереди.",
        "Сейчас у чёрных на одну пешку больше.",
        "Так что у тебя на пешку меньше.",
    ])
    def test_paraphrases(self, sentence):
        assert check_sentence(sentence, _game_ctx()), sentence

    @pytest.mark.parametrize("sentence", [
        "Теперь у чёрных на две пешки больше.",
        "Сейчас у чёрных лишняя пешка, даже две.",
        "После 5...exd4 у чёрных была лишняя пешка, а теперь их уже две.",
        "Ход назад у чёрных была одна лишняя пешка.",
        "Если ты заберёшь d4, у чёрных будет на пешку больше.",
    ])
    def test_true_or_about_another_moment(self, sentence):
        assert check_sentence(sentence, _game_ctx()) == [], sentence

    def test_a_move_ago_it_was_one_pawn(self):
        # The bubble before (after 5...exd4): one pawn — true then, still shown.
        ctx = _game_ctx("1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4", question="Сc4")
        assert check_sentence("Так что теперь у чёрных на одну пешку больше, и это уже чуть в их пользу.", ctx) == []

    def test_outside_a_game_a_line_still_counts(self):
        # No game on the board: a line's positions stay boards a claim may be about (unchanged).
        ctx = CheckContext.from_fens([chess.STARTING_FEN], ["1.e4 d5 2.exd5 Nf6 3.c4 c6"])
        assert check_sentence("У белых на пешку больше.", ctx) == []


KG = "rnbqkbnr/pppp1ppp/8/4p3/4PP2/8/PPPP2PP/RNBQKBNR b KQkq - 0 2"  # 1.e4 e5 2.f4, Black to move


@pytest.mark.unit
class TestToldCapture:
    def test_prod_can_kg_accept(self):
        ctx = CheckContext.from_fens([KG], question="Стоит ли брать пешку f4?")
        issues = check_sentence("Материал пока равный — ты отдал пешку e5, но забрал f4, так что лишней пешки ни у "
                                "кого нет.", ctx)
        assert issues == ["material after exf4 (the capture this sentence tells as made): Black has an extra 1 pawn "
                          "(not equal)"]

    @pytest.mark.parametrize("sentence", [
        "Ты забрал f4, и материал равный.",
        "Ты взял пешку f4, так что лишней пешки ни у кого нет.",
        "Ты забрал пешку f4, и теперь у белых на пешку больше.",
    ])
    def test_paraphrases(self, sentence):
        assert check_sentence(sentence, CheckContext.from_fens([KG])), sentence

    @pytest.mark.parametrize("sentence", [
        "Ты забрал f4 — теперь у тебя лишняя пешка.",
        "Ты забрал пешку f4, и у тебя на пешку больше.",
        "Если ты заберёшь f4, материал будет равный.",
        "Материал пока равный, а после взятия на f4 у тебя будет лишняя пешка.",
        "Белые взяли бы на f4 — материал равный.",
    ])
    def test_true_or_hypothetical(self, sentence):
        assert check_sentence(sentence, CheckContext.from_fens([KG])) == [], sentence

    def test_the_capture_just_played_is_on_the_board(self):
        # 1.e4 d5 2.exd5 Qxd5: «ты взял на d5, чёрные забрали обратно» — the recapture is the board now.
        ctx = _game_ctx("1.e4 d5 2.exd5 Qxd5", question="exd5")
        assert check_sentence("Ты взял на d5, чёрные забрали обратно — материал равный.", ctx) == []

    def test_the_other_side_named(self):
        # «Белые забрали …»: not the side to move (Black) — the capture is not this sentence's moment.
        assert check_sentence("Белые забрали e5 — материал равный.", CheckContext.from_fens([KG])) == []


# ── (b) A promise to show it on the board ────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestPromise:
    @pytest.mark.parametrize("sentence", [
        "Покажу на доске.",
        "Покажу на доске, как это выглядит.",
        "Сейчас поставлю позицию на доску.",
        "I'll show it on the board.",
    ])
    def test_promises(self, sentence):
        assert promises_board(sentence)

    @pytest.mark.parametrize("sentence", [
        "Хочешь, покажу на доске?",
        "Хотите, покажу на доске, как выглядит выигрыш при «правильном» слоне?",
        "Если хочешь, поставлю на доску саму задачу из урока.",
        "Покажу на доске: пешка e5 бьёт d6.",
        "Посмотри на доску.",
        "Сейчас покажу, как это работает.",
        "Сыграешь bxc6 — и я покажу, как довести это до мата?",
    ])
    def test_not_a_bare_promise(self, sentence):
        assert not promises_board(sentence)

    def test_prod_rule_promote_left_out_when_the_board_stays(self):
        gate = SentenceGate(CheckContext.from_fens(), hold_promises=True)
        out = []
        for part in ("А король один на всю партию: второго не бывает.\n\n", "Покажу на ", "доске.\n\n",
                     "Хочешь, дам задачку на превращение пешки?"):
            out += gate.feed(part)
        assert "".join(p[0] for p in out) == "А король один на всю партию: второго не бывает.\n\n"
        rest = gate.flush()
        promise = [p for p in rest if p[1]]
        assert len(promise) == 1 and promise[0][1] == [PROMISE_ISSUE] and promise[0][2].strip() == "Покажу на доске."
        assert "".join(p[0] for p in rest if not p[1]).strip() == "Хочешь, дам задачку на превращение пешки?"

    def test_kept_when_the_tool_puts_it_up(self):
        # prod 23.10: «Покажу на доске, как это выглядит.» then board_control set_fen — the promise was kept.
        gate = SentenceGate(CheckContext.from_fens(), hold_promises=True)
        assert gate.feed("Покажу на доске, как это выглядит. На доске") == []
        gate.board_changed()
        out = gate.feed(" чёрные только что сыграли d5. ")
        assert [p[0] for p in out] == ["Покажу на доске, как это выглядит. ", "На доске чёрные только что сыграли d5. "]
        assert all(not p[1] for p in out) and gate.flush() == []

    def test_other_gates_do_not_hold(self):
        # The voice check and the lesson tutor: spoken words cannot wait — nothing held.
        gate = SentenceGate(CheckContext.from_fens())
        assert gate.feed("Покажу на доске. ") == [("Покажу на доске. ", [], "Покажу на доске. ")]


@pytest.mark.unit
class TestPromiseInTheTextTurn:
    def setup_method(self):
        self.client = TestClient(app)

    def _turn(self, mock_profile, mock_agent, chat):
        mock_profile.return_value = UserProfile(user_id="promise-user")
        agent = MagicMock()
        agent.chat.side_effect = lambda message, stream_callback=None: chat(agent, stream_callback)
        mock_agent.return_value = agent
        user = {"X-User-Id": "promise-user"}
        sid = self.client.post("/api/coach/sessions", headers=user).json()["id"]
        resp = self.client.post("/api/coach/chat", headers=user, json={
            "message": "Можно ли превратить пешку в короля или во второго ферзя?", "session_id": sid,
            "fen": chess.STARTING_FEN,
        })
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        return "".join(f.get("delta", "") for f in frames), [f for f in frames if f.get("board_actions")]

    @patch("src.server.config.COACH_ENGINE_NOTE", False)
    @patch("src.server.config.COACH_OPENING_PRESTEP", False)
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_prod_rule_promote(self, mock_profile, mock_agent):
        draft = ["Нет — в короля превратить нельзя, а во второго ферзя можно.\n\n", "Покажу на доске.\n\n",
                 "Хочешь, дам задачку на превращение пешки?"]

        def chat(agent, cb):
            for part in draft:
                cb(part)
            return "".join(draft)

        text, boards = self._turn(mock_profile, mock_agent, chat)
        assert not boards
        assert "Покажу на доске" not in text
        assert text.startswith("Нет — в короля превратить нельзя") and text.rstrip().endswith("на превращение пешки?")

    @patch("src.server.config.COACH_ENGINE_NOTE", False)
    @patch("src.server.config.COACH_OPENING_PRESTEP", False)
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_promise_kept_by_the_tool_after_it(self, mock_profile, mock_agent):
        fen = "8/P7/8/8/8/8/k7/4K3 w - - 0 1"

        def chat(agent, cb):
            cb("Покажу на доске.\n\n")  # the model writes the promise, then calls the tool
            agent.tool_complete_callback("t1", "board_control", {"action": "set_fen"},
                                         json.dumps({"type": "set_fen", "fen": fen}))
            cb("Пешка a7 идёт на a8 и становится ферзём.")
            return "Покажу на доске.\n\nПешка a7 идёт на a8 и становится ферзём."

        text, boards = self._turn(mock_profile, mock_agent, chat)
        assert boards and text.startswith("Покажу на доске.") and "становится ферзём" in text


# ── (c) An example asked with a named piece ──────────────────────────────────────────────────────────────────

ROOK_FORK = "3r2k1/5pp1/7p/8/1B4NP/8/5PP1/7K b - - 0 1"  # the lesson «Двойной удар»: 1...Rd4


@pytest.mark.unit
class TestMotifPiece:
    @pytest.mark.parametrize("text, want", [
        ("Покажи на доске пример вилки конём", ("fork", chess.KNIGHT)),
        ("knight fork", ("fork", chess.KNIGHT)),
        ("a fork with the queen", ("fork", chess.QUEEN)),
        ("пешечная вилка", ("fork", chess.PAWN)),
        ("связка слоном", ("pin", chess.BISHOP)),
        ("Покажи пример вилки", None),
        ("вилка", None),
    ])
    def test_parse(self, text, want):
        assert motif_piece(text) == want

    def test_motif_by_the_piece(self):
        assert shows_motif(ROOK_FORK, "fork") is True
        assert shows_motif(ROOK_FORK, "fork", chess.ROOK) is True
        assert shows_motif(ROOK_FORK, "fork", chess.KNIGHT) is False
        assert shows_motif("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1", "fork", chess.KNIGHT) is True  # Nc7+


@pytest.fixture
def lesson_with_a_rook_fork(monkeypatch):
    import src.tools.knowledge_topics as kt
    import src.tools.learning_path as lp

    monkeypatch.setattr(kt, "_lessons_for_words", lambda *a, **k: [])
    monkeypatch.setattr(kt, "_related_lessons", lambda *a, **k: [
        {"lesson_id": "l-da", "slug": "double-attack", "title": "Двойной удар", "course": "Шахматная тактика"}])
    monkeypatch.setattr(lp, "get_lesson", lambda key, **kw: {
        "lesson_id": "l-da", "title": "Двойной удар", "course": {"slug": "chess-tactics", "title": "Шахматная тактика"},
        "url": "https://chesster.io/learn/chess-tactics/double-attack",
        "diagrams": [{"fen": ROOK_FORK, "context": "Лd4 — двойной удар по g4 и b4"}],
    })
    monkeypatch.setattr(kt, "_example_look", lambda fen: {})


@pytest.mark.unit
class TestExampleSearch:
    def test_prod_d3_example_knight_asked(self, lesson_with_a_rook_fork):
        from src import knowledge_base as kb
        from src.tools.knowledge_topics import get_topic

        out = get_topic("вилка", locale="ru", topics=kb.load_topics(force=True),
                        question="Покажи на доске пример вилки конём")
        assert out["example"]["fen"] != ROOK_FORK
        assert shows_motif(out["example"]["fen"], "fork", chess.KNIGHT) is True

    def test_piece_in_the_topic(self, lesson_with_a_rook_fork):
        from src import knowledge_base as kb
        from src.tools.knowledge_topics import get_topic

        out = get_topic("knight fork", locale="ru", topics=kb.load_topics(force=True))
        assert out.get("slug") == "fork" and out["example"]["fen"] != ROOK_FORK

    def test_no_piece_named_keeps_the_lesson(self, lesson_with_a_rook_fork):
        from src import knowledge_base as kb
        from src.tools.knowledge_topics import get_topic

        out = get_topic("вилка", locale="ru", topics=kb.load_topics(force=True), question="Покажи пример вилки")
        assert out["example"]["fen"] == ROOK_FORK

    def test_none_with_that_piece_says_so(self, lesson_with_a_rook_fork):
        from src import knowledge_base as kb
        from src.tools.knowledge_topics import get_topic

        out = get_topic("вилка", locale="ru", topics=kb.load_topics(force=True), question="Покажи вилку королём")
        assert "example" not in out and "board_actions" not in out
        assert "made by a king" in out["board_hint"]

    def test_the_handler_passes_the_student_words(self, lesson_with_a_rook_fork):
        from src.tools.knowledge_topics import _handle_get_topic

        out = json.loads(_handle_get_topic({"topic": "вилка"}, student_message="Покажи на доске пример вилки конём"))
        assert out["example"]["fen"] != ROOK_FORK


@pytest.mark.unit
class TestAskedMotifSentence:
    Q = "Покажи на доске пример вилки конём"

    def _ctx(self, question=Q):
        ctx = CheckContext.from_fens([chess.STARTING_FEN], question=question)
        ctx.add(ROOK_FORK)  # get_topic put the example up
        return ctx

    def test_prod_d3_example(self):
        issues = check_sentence("Ход чёрных: ладья идёт на d4 — и сразу бьёт по двум незащищённым фигурам: коню на g4 "
                                "и слону на b4.", self._ctx())
        assert issues == ["the student asked for a fork made by a knight; this sentence presents a blow by a rook — "
                          "that is not the knight fork asked for: say so plainly"]

    @pytest.mark.parametrize("sentence", [
        "Здесь ход чёрных, и решает 1...Лd4! — ладья бьёт сразу по двум незащищённым фигурам: коню g4 и слону b4.",
        "Чёрные играют Rd4 — двойной удар по коню и слону.",
    ])
    def test_paraphrases(self, sentence):
        assert check_sentence(sentence, self._ctx()), sentence

    @pytest.mark.parametrize("sentence", [
        "Это двойной удар ладьёй, а не вилка конём.",
        "Ладья тоже умеет бить по двум фигурам сразу.",
        "Конь прыгает на c7 и бьёт сразу по двум фигурам: королю и ладье.",
        "Вилка — это тот же двойной удар, но сделанный конём или пешкой.",
        "Если бы ладья пошла на d4, она била бы по двум фигурам.",
    ])
    def test_right_or_contrasted(self, sentence):
        assert check_sentence(sentence, self._ctx()) == [], sentence

    def test_no_piece_asked(self):
        sentence = "Ход чёрных: ладья идёт на d4 — и сразу бьёт по двум незащищённым фигурам: коню на g4 и слону на b4."
        assert check_sentence(sentence, self._ctx("Покажи на доске пример вилки")) == []


# ── (d) The board named as a whole ───────────────────────────────────────────────────────────────────────────

KK = "7k/8/8/8/8/4K3/8/8 w - - 0 1"


@pytest.mark.unit
class TestComposition:
    @pytest.mark.parametrize("sentence, issue", [
        ("Это позиция «король против короля» — ничья.", "not «король против короля»"),
        ("Позиция чистая: король и пешка против короля.", "not «король и пешка против короля»"),
        ("На доске ладья и король против короля.", "not «ладья и король против короля»"),
        ("Посмотри на доску — там только два короля.", "the board holds more than the two kings"),
        ("Здесь уже эндшпиль, и король должен идти в центр.", "this is not an endgame"),
    ])
    def test_named_against_the_start_position(self, sentence, issue):
        issues = check_sentence(sentence, CheckContext.from_fens([chess.STARTING_FEN]))
        assert len(issues) == 1 and issue in issues[0]

    def test_the_board_a_tool_put_up(self):
        # prod 23.10 («Шах и Мат»): set_puzzle put two kings up — «там пустая доска, только два короля» is true.
        ctx = CheckContext.from_fens([chess.STARTING_FEN])
        ctx.add(KK)
        assert check_sentence("Посмотри на доску — там пустая доска, только два короля.", ctx) == []
        assert check_sentence("Это позиция «король против короля» — ничья.", ctx) == []

    @pytest.mark.parametrize("fen, sentence", [
        ("8/8/4k3/8/4P3/4K3/8/8 w - - 0 1", "Позиция чистая: король и пешка против короля."),
        ("4k3/8/4K3/8/8/8/8/R7 w - - 0 1", "На доске ладья и король против короля."),
        ("8/8/8/8/8/2k5/8/K1N1N3 w - - 0 1", "Здесь два коня против короля, и мат не форсируется."),
        ("6k1/5pp1/7p/8/8/8/5PPP/3R2K1 w - - 0 1", "Здесь у тебя ладья против короля."),  # pawns not counted unless named
    ])
    def test_true(self, fen, sentence):
        assert check_sentence(sentence, CheckContext.from_fens([fen])) == [], sentence

    @pytest.mark.parametrize("sentence", [
        # prod 29.10 x-poem: the student's study plan (the profile), not the board — no now-word, not judged
        "Стихи стихами, а ладью с королём против короля пора бы уже дожать.",
        "А хочешь — вернёмся к доске и разберём твой эндшпиль?",
        # g2-takeback, «Доска пустая, все фигуры на местах»: a new game, no moves yet — an idiom
        "Ты снова белыми, поле пустое — делай любой ход.",
        "Доска пустая, все фигуры на местах, и мне сейчас играет движок примерно твоего уровня.",
        # a rule, a list of cases, an offer, a topic
        "Ладья против короля — всегда выигрыш.",
        "Это два короля, король со слоном против короля, король с конём против короля и король с двумя конями "
        "против короля.",
        "Хочешь, разберём на доске ладью против короля?",
        "Это техника «ладья против короля»: сначала отрезаем короля.",
        "Здесь не эндшпиль «ладья против короля», а миттельшпиль.",
    ])
    def test_not_about_the_board(self, sentence):
        assert check_sentence(sentence, CheckContext.from_fens([chess.STARTING_FEN])) == [], sentence


# ── The voice check: the same sentence checks ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestVoiceParity:
    def setup_method(self):
        self.client = TestClient(app)

    def test_told_capture(self):
        resp = self.client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-small"}, json={
            "text": "Материал пока равный — ты отдал пешку e5, но забрал f4.", "fen": KG,
            "question": "Стоит ли брать пешку f4?",
        })
        assert resp.json()["issues"] and "after exf4" in resp.json()["issues"][0]

    def test_asked_piece(self):
        resp = self.client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-small"}, json={
            "text": "Ладья идёт на d4 и бьёт сразу по двум фигурам.", "fen": ROOK_FORK,
            "question": "Покажи пример вилки конём",
        })
        assert resp.json()["issues"] and "knight fork" in resp.json()["issues"][0]
