"""2026-11-10 22:48, Alexander's iPhone, voice, «Анализ» with the start position: «Отлично, смотри на доску. Шах — это
когда на твоего короля нападают. Видишь, белого короля атакует чёрная ладья? У тебя есть т…» — nothing of it on the
board; then «…сейчас всё исправлю. [Board] …» read aloud as noise.

What was wrong on the server, each closed as a class:

* the book's lesson «Шах и мат» says «На картинке сверху белому королю стоит шах от черной ладьи. У белых есть 3
  возможных защиты…» and its two pictures had no position: the text went to the model with a bare «[Диаграмма]» and
  nothing went on the board — the positions are in the data now, and a picture with no position is named as unseen;
* «шах» found the course «Основы шахмат» by substring and put the two bare kings of its first lesson on the board —
  topics match by whole words, the lesson titled as the topic first, a question as it is said aloud is read;
* a showing tool that put nothing on the board did not say so — every such result says it (src/board_truth);
* the coach pointing at the board over the bare start position was not checked — src/unshown_board.
"""

import json
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

from src import board_truth, config, lesson_texts, unshown_board
from src.answer_check import CheckContext, check_sentence
from src.server import app
from src.tools import knowledge_topics as kt
from src.tools import learning_path as lp

START = chess.STARTING_FEN
CHECK_FEN = "6k1/5pp1/2p2n1p/2P1Q3/2B5/8/5PP1/r5K1 w - - 0 1"
MATE_FEN = "6k1/2Q2pp1/2p2n1p/2P5/8/6B1/5PPP/r5K1 w - - 0 1"
CHECK_LESSON = "75d7d3ff-bfeb-4f90-bd7b-51e6fcfb97cf"   # the site's «Шах»
MATE_LESSON = "a703ca8b-c85b-41c8-b5dc-72705559581f"    # the site's «Мат»
FIXTURE = Path(__file__).resolve().parents[2] / "eval/fixtures/site_programme_2026-10-06.json"


# ── the book's pictures of «Шах и мат» and «Рокировка» are positions now ──────────────────────────────────────────

def test_the_check_diagram_shows_what_the_lesson_says():
    own = lesson_texts.lesson_text(lesson_id=CHECK_LESSON, lesson_title="Шах", coach=True)
    assert own["diagrams"][0]["fen"] == CHECK_FEN
    board = chess.Board(CHECK_FEN)
    # «белому королю стоит шах от черной ладьи»
    assert board.is_check() and not board.is_checkmate()
    assert [(board.piece_at(s).symbol(), chess.square_name(s)) for s in board.checkers()] == [("r", "a1")]
    # «съесть ладью ферзем, уйти королем и закрыться слоном»
    assert {"Qxa1", "Kh2", "Bf1"} <= {board.san(m) for m in board.legal_moves}
    assert f"[Диаграмма: {CHECK_FEN}]" in own["text"] and "[Диаграмма]" not in own["text"]


def test_the_lesson_mate_is_taught_from_the_mate_diagram():
    own = lesson_texts.lesson_text(lesson_id=MATE_LESSON, lesson_title="Мат", coach=True)
    assert own["diagrams"][0]["fen"] == MATE_FEN and chess.Board(MATE_FEN).is_checkmate()
    assert own["diagrams"][1]["fen"] == CHECK_FEN  # the other picture of the same book lesson, after it
    # the lesson chat of /learn reads the book in its own order, as before
    assert lesson_texts.lesson_text(lesson_id=MATE_LESSON, lesson_title="Мат")["diagrams"][0]["fen"] == CHECK_FEN


def test_castling_diagrams_are_positions():
    own = lesson_texts.lesson_text(course_slug="chess-basics", module_title="Рокировка", coach=True)
    fens = [d["fen"] for d in own["diagrams"]]
    assert len(fens) == 4 and all(chess.Board(f).is_valid() for f in fens)
    before = chess.Board(fens[0])
    assert {"O-O", "O-O-O"} <= {before.san(m) for m in before.legal_moves}
    before.push_san("O-O")
    before.push_san("O-O")
    assert before.board_fen() == fens[1].split()[0]


def test_a_picture_without_a_position_is_named_as_unseen_for_the_coach_only():
    rec = {"text_ru": "Ладья ходит по прямой.\n[Диаграмма s1_l1_theory_03.jpg: None]\nНа картинке ладья бьёт пешку."}
    coach = lesson_texts.explanation(rec, unseen=lesson_texts.UNSEEN_PICTURE)
    assert lesson_texts.UNSEEN_PICTURE in coach and "[Диаграмма]" not in coach
    assert "[Диаграмма]" in lesson_texts.explanation(rec)  # the lesson tutor's reading is the old one
    # the book's lesson 1 («как ходит ладья»: schemes without kings) through the coach's tool reading
    own = lesson_texts.lesson_text(course_slug="chess-basics", module_title="Основы шахмат", coach=True)
    assert lesson_texts.UNSEEN_PICTURE in own["text"] and "[Диаграмма]" not in own["text"]
    assert "Картинка учебника" not in lesson_texts.book_view(
        next(r for r in lesson_texts._records() if r.get("docx_lesson") == "2"))["summary"]


def test_no_coach_text_points_at_a_picture_without_saying_it_is_unseen():
    """Every lesson of the book, as the coach's tools read it: no bare «[Диаграмма]» is left."""
    for rec in lesson_texts._records():
        assert "[Диаграмма]" not in lesson_texts.explanation(rec, unseen=lesson_texts.UNSEEN_PICTURE, limit=10 ** 6)


# ── the topic the words name: whole words, the lesson titled so first, a question as it is said ──────────────────

@pytest.fixture
def programme(monkeypatch):
    prog = json.loads(FIXTURE.read_text())
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: prog)
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {})

    def _rows(table, select, select_min, url, key, **extra):
        wanted = (extra.get("id") or "").removeprefix("eq.")
        for _c, _m, lesson in lp.iter_lessons(prog):
            if lesson["id"] == wanted:
                return [{**lesson, "content": "", "content_ru": "", "lesson_puzzles": []}]
        return []

    monkeypatch.setattr(lp, "_query_with_fallback", _rows)
    return prog


@pytest.mark.parametrize("words,first", [
    ("шах", "Шах"), ("Что такое шах?", "Шах"), ("Объясни мне, что такое шах", "Шах"), ("Расскажи про шах", "Шах"),
    ("А что такое шах в шахматах?", "Шах"), ("Шах деген не?", "Шах"), ("What is a check?", "Шах"),
    ("мат", "Мат"), ("Что такое мат?", "Мат"), ("checkmate", "Мат"), ("Что такое шах и мат?", "Шах"),
    ("А что такое пат в шахматах?", "Пат"), ("what is stalemate", "Пат"),
    ("Я не понял, покажи ещё раз, что такое мат.", "Мат"), ("Слушай, а расскажи мне про рокировку", "Зачем делать рокировку?"),  # the word as it was said, in that module
    ("Okay, and what is a check?", "Шах"),
    ("Что такое рокировка?", "Что такое рокировка"), ("связка", "Связка"),
])
def test_the_words_find_their_own_lesson(programme, words, first):
    hits, strength = lp.programme_matches(programme, words)
    assert hits and hits[0][2]["title"] == first and strength in ("module", "lesson")


@pytest.mark.parametrize("words", ["шах", "мат", "Что такое шах?", "Что такое мат?"])
def test_a_word_inside_another_word_is_no_match(programme, words):
    """«шах» and «мат» are inside «Основы шахмат»: its first lesson's two bare kings went up for both (prod 10.11)."""
    hits, _ = lp.programme_matches(programme, words)
    assert all(m["title"] != "Основы шахмат" for _c, m, _l in hits)
    assert "Король" not in [l["title"] for _c, _m, l in hits][:1]


def test_the_course_by_its_own_name_still_matches(programme):
    hits, strength = lp.programme_matches(programme, "основы шахмат")
    assert hits and hits[0][1]["title"] == "Основы шахмат" and strength == "module"


@pytest.mark.parametrize("question,fen", [
    ("Что такое шах?", CHECK_FEN), ("Объясни мне, что такое шах", CHECK_FEN), ("Шах деген не?", CHECK_FEN),
    ("What is a check?", CHECK_FEN), ("Что такое мат?", MATE_FEN),
])
def test_the_concept_goes_on_the_board_from_the_book(programme, question, fen):
    out = kt.get_topic(question, question=question)
    assert out["example"]["fen"] == fen and out["example"]["kind"] == "diagram"
    assert out["board_actions"] == [{"type": "set_fen", "fen": fen}]
    assert "стоит шах от черной ладьи" in out["example"]["note"]


def test_get_lesson_by_its_title_puts_the_diagram_up(programme):
    out = lp.get_lesson("Шах", show=True)
    assert "ambiguous" not in out and out["board_actions"] == [{"type": "set_fen", "fen": CHECK_FEN}]
    assert "стоит шах от черной ладьи" in out["lesson_text"]


# ── a showing tool that put nothing on the board says so ─────────────────────────────────────────────────────────

def test_a_lesson_with_nothing_for_the_board_says_nothing_was_put_up():
    raw = json.dumps({"title": "Ладья", "lesson_text": "… На картинке ладья бьёт пешку."}, ensure_ascii=False)
    out = json.loads(board_truth.board_truth(raw, {}, "get_lesson"))
    assert out["board_now"] == board_truth.NOTHING_SHOWN_NOTE
    for tool in ("get_topic", "lookup_opening", "famous_game"):
        assert "board_now" in json.loads(board_truth.board_truth(json.dumps({"ambiguous": True}), {}, tool))


def test_arrows_alone_are_not_a_position():
    raw = json.dumps({"title": "x", "board_actions": [{"type": "draw_arrows", "arrows": []}]})
    assert json.loads(board_truth.board_truth(raw, {}, "get_topic"))["board_now"] == board_truth.NOTHING_SHOWN_NOTE


def test_a_result_that_put_a_position_up_names_it_and_other_tools_are_left_alone():
    shown = json.dumps({"title": "Шах", "board_actions": [{"type": "set_fen", "fen": CHECK_FEN}]})
    out = json.loads(board_truth.board_truth(shown, {}, "get_lesson"))
    assert CHECK_FEN in out["board_now"] and "NOTHING" not in out["board_now"]
    plain = json.dumps({"best": "e4"})
    assert board_truth.board_truth(plain, {}, "analyze_position") == plain
    assert board_truth.board_truth(plain, {}) == plain
    failed = json.dumps({"error": "No lesson matches"})
    assert board_truth.board_truth(failed, {}, "get_lesson") == failed  # the error hint says it (ERROR_HINT)


def test_the_board_lock_note_is_not_doubled():
    from src.sessions import HIDDEN_BOARD_NOTE

    raw = json.dumps({"title": "x", "board_hint": HIDDEN_BOARD_NOTE})
    assert "board_now" not in json.loads(board_truth.board_truth(raw, {}, "get_topic"))


def test_the_registered_tool_says_it(programme, monkeypatch):
    """Through the registry, as the model's call runs: «как ходит ладья» has only schemes — nothing goes up."""
    from src.tools import registry

    out = json.loads(registry.get_entry("get_topic").handler({"topic": "шах королю и ферзю одновременно"}))
    assert not out.get("board_actions") and (out.get("board_now") == board_truth.NOTHING_SHOWN_NOTE or "error" in out)
    shown = json.loads(registry.get_entry("get_topic").handler({"topic": "Что такое шах?"}))
    assert CHECK_FEN in shown["board_now"]


# ── the coach points at the board over the bare start position ───────────────────────────────────────────────────

def _said(sentences, fen=START, voice=True):
    ctx = CheckContext.from_fens([fen], [], question="Что такое шах?")
    ctx.voice = voice
    return [check_sentence(s, ctx) for s in sentences], ctx


def test_the_reported_answer():
    issues, _ = _said(["Отлично, смотри на доску.", "Шах — это когда на твоего короля нападают.",
                       "Видишь, белого короля атакует чёрная ладья?"])
    assert issues[0] == [] and issues[1] == []
    assert unshown_board.is_unshown(issues[2]) and "the starting position" in issues[2][0]


@pytest.mark.parametrize("sentences", [
    ["Смотри на доску: чёрная ладья нападает на белого короля."],
    ["Посмотри на доску.", "Белому королю стоит шах от чёрной ладьи."],
    ["Видишь, ладья на e8 даёт шах королю на e1?"],
    ["Король на e1 стоит под шахом от ладьи на e8, видишь?"],
    ["Здесь ферзь может съесть ладью."],
    ["На диаграмме белый слон атакует чёрного ферзя."],
    ["Look at the board: the black rook attacks the white king."],
    ["As you can see, the white king is in check."],
    ["Here the queen can take the rook."],
    ["Тақтаға қара: қара ладья ақ корольге шабуыл жасап тұр."],
    ["Көріп тұрсың ба, ақ корольге шах беріп тұр."],
])
def test_a_contact_told_as_standing_on_the_bare_board(sentences):
    issues, _ = _said(sentences)
    assert unshown_board.is_unshown(issues[-1]), sentences


# Live run 11.11 (main's Hermes, gemini-3.1-flash-live): «Вот, посмотрите, теперь на доске должен быть пример спёртого
# мата. Видите, король противника заблокирован собственными фигурами, и конь наносит решающий удар» and «Вот,
# посмотри на эту позицию. Здесь белая ладья нападает на чёрного короля» — over the start position.
@pytest.mark.parametrize("sentences,flagged", [
    (["Прошу прощения, заминочка вышла.", "Одну секунду, сейчас исправлю...",
      "Вот, посмотрите, теперь на доске должен быть пример спёртого мата.",
      "Видите, король противника заблокирован собственными фигурами, и конь наносит решающий удар."], [2, 3]),
    (["Я сейчас найду подходящий пример на доске.", "Вот, посмотри на эту позицию.",
      "Здесь белая ладья нападает на чёрного короля."], [1, 2]),
    (["Вот, посмотри на доску теперь.", "Видишь, чёрному королю на e8 объявлен шах белой ладьёй?"], [1]),
    (["Я поставил пример на доску."], [0]), (["Пример уже на доске."], [0]),
    (["The example is now on the board."], [0]), (["I've put the position on the board."], [0]),
    (["Тақтада мысал тұр."], [0]), (["Смотри, королю мат."], [0]), (["Видишь, конь связан слоном."], [0]),
])
def test_an_example_said_to_be_on_the_bare_board(sentences, flagged):
    issues, _ = _said(sentences)
    assert [i for i, found in enumerate(issues) if unshown_board.is_unshown(found)] == flagged, sentences


@pytest.mark.parametrize("sentence", [
    "На доске начальная позиция.", "Сейчас на доске пока нет примера.", "Хочешь, покажу пример на доске?",
    "Сейчас поставлю пример на доску.", "Прошу прощения, на доске сейчас нет примера.",
    "Давай я поставлю задачу, где королю объявлен шах, и ты сам попробуешь защититься?",
    "Прости, прямо сейчас на доске не могу показать.", "Если хочешь, я могу показать пример на доске.",
    "Извини, на доске сейчас начальная позиция, там никого не атакуют.", "Вот пример: конь ходит буквой Г.",
    "Would you like me to put an example on the board?", "There is no example on the board yet.",
    "Here is an example: a knight moves in an L shape.", "Мат — это шах, от которого нет защиты.",
    "Попробуй подвинуть коня на доске, и мы посмотрим, как это работает.",
    "Скажи, какой выбрать, и я поставлю на доску.", "Тақтада әзірге мысал жоқ.",
])
def test_offers_plans_and_the_start_position_itself_are_left_alone(sentence):
    issues, _ = _said([sentence])
    assert not unshown_board.is_unshown(issues[0]), sentence


def test_a_game_against_the_coach_owns_its_start_position():
    ctx = CheckContext.from_fens([START], [])
    ctx.voice = True
    ctx.game_moves = []          # a live game, no move made yet (set by /voice/check from the session)
    ctx.game_engine_moves = []
    assert check_sentence("Я поставил позицию на доску, ты играешь белыми.", ctx) == []


@pytest.mark.parametrize("sentences", [
    ["Шах — это нападение на короля."],                                         # a definition, no pointer
    ["Смотри на доску.", "Шах — это когда на твоего короля нападают."],          # a definition after a pointer
    ["Ладья атакует короля — это и есть шах."],
    ["Смотри на доску: если пешка пойдёт на e4, слон f1 нападает на b5."],       # a condition
    ["Посмотри на доску: после e4 e5 ферзь на h5 нападает на пешку e5."],        # a line
    ["Видишь, сейчас никто никого не атакует."],                                 # a denial
    ["На доске начальная позиция, и королю никто не угрожает."],
    ["Смотри на доску.", "Сейчас я поставлю позицию, где ладья атакует короля."],  # a plan
    ["Ой, извини, это моя ошибка!", "Я забыл поменять позицию на доске.", "Секунду, сейчас всё исправлю."],
    ["Давай посмотрим на первый ход белых, например e4."],
    ["Look at the board. If the rook moves, it attacks the king."],
    ["A check is when a piece attacks the king."],
    ["Тақтаға қара.", "Егер ладья жүрсе, корольге шабуыл жасайды."],
    # the pointer is three sentences back: general talk again
    ["Смотри на доску.", "Белые начинают.", "Обычно первой идёт пешка.", "Ладья атакует короля по линии."],
])
def test_what_is_not_a_claim_about_the_board_is_left_alone(sentences):
    issues, _ = _said(sentences)
    assert not any(unshown_board.is_unshown(i) for i in issues), sentences


def test_a_real_position_is_never_judged_here():
    issues, _ = _said(["Смотри на доску: чёрная ладья даёт шах белому королю."], fen=CHECK_FEN)
    assert issues == [[]]
    # another board that is somebody's: the other checks judge it, this one does not
    mid = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    issues, _ = _said(["Смотри на доску: чёрная ладья нападает на белого короля."], fen=mid)
    assert issues[0] and not unshown_board.is_unshown(issues[0])
    assert unshown_board.nobodys(chess.Board("8/8/8/8/8/8/8/8 w - - 0 1")) == "an empty board"


def test_a_loaded_game_or_another_position_of_the_turn_is_theirs_to_describe():
    client = TestClient(app)
    said = {"text": "Смотри на доску: на десятом ходу конь нападает на ферзя.", "fen": START, "engine": False}
    assert client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-demo-1111"}, json=said).json().get("unshown")
    with_game = {**said, "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7"}
    assert "unshown" not in client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-demo-1111"},
                                        json=with_game).json()
    # the student's own idea is another position of the turn
    ctx = CheckContext.from_fens([START, "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"], [])
    ctx.voice = True
    assert check_sentence("Видишь, пешка нападает на d5.", ctx) == []


def test_a_position_a_tool_put_up_during_the_answer_is_another_board():
    ctx = CheckContext.from_fens([START], [], question="Что такое шах?")
    ctx.voice = True
    ctx.board_moved = True
    assert check_sentence("Смотри на доску: чёрная ладья нападает на белого короля.", ctx) == []


def test_the_text_turn_only_records_it(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    issues, ctx = _said(["Смотри на доску: чёрная ладья нападает на белого короля."], voice=False)
    assert issues == [[]]
    assert [(r[0], unshown_board.is_unshown(r[2])) for r in ctx.detector_shadow] == [("unshown_board", True)]


def test_the_switches(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    assert config.detector_mode("unshown_board_voice") == "on" and config.detector_mode("unshown_board") == "shadow"
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "unshown_board_voice")
    issues, ctx = _said(["Смотри на доску: чёрная ладья нападает на белого короля."])
    assert issues == [[]] and ctx.detector_shadow
    monkeypatch.setenv("COACH_DETECTORS_OFF", "unshown_board_voice")
    issues, ctx = _said(["Смотри на доску: чёрная ладья нападает на белого короля."])
    assert issues == [[]] and not ctx.detector_shadow
    lesson = CheckContext.from_fens([START])
    lesson.relation_surface = "lesson"   # the /learn tutor: never
    lesson.voice = True
    assert check_sentence("Смотри на доску: чёрная ладья нападает на белого короля.", lesson) == []


def test_the_voice_check_tells_the_site_to_cut_the_turn():
    client = TestClient(app)
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-demo-1111"}, json={
        "text": "Видишь, белого короля атакует чёрная ладья?", "fen": START, "question": "Что такое шах?",
        "previous": "Отлично, смотри на доску. Шах — это когда на твоего короля нападают. ", "engine": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["unshown"] is True and unshown_board.is_unshown(data["issues"])
    # the same words over the lesson's own diagram: true, nothing to cut
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-demo-1111"}, json={
        "text": "Видишь, белого короля атакует чёрная ладья?", "fen": CHECK_FEN, "question": "Что такое шах?",
        "previous": "Отлично, смотри на доску. ", "engine": False})
    assert resp.status_code == 200 and "unshown" not in resp.json() and resp.json()["issues"] == []


def test_the_pointer_of_the_answer_so_far_is_read_from_previous():
    client = TestClient(app)
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-demo-1111"}, json={
        "text": "Белому королю стоит шах от чёрной ладьи.", "fen": START,
        "previous": "Посмотри на доску. ", "engine": False})
    assert resp.json().get("unshown") is True
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-demo-1111"}, json={
        "text": "Белому королю стоит шах от чёрной ладьи.", "fen": START, "engine": False})
    assert "unshown" not in resp.json()  # no pointer: theory talk over the start position, as before


# ── the voice prompt ─────────────────────────────────────────────────────────────────────────────────────────────

def test_the_voice_prompt_says_how_the_board_changes():
    from src.prompt_builder import VOICE_TOOL_LAYER

    assert "The board changes ONLY through a tool call" in VOICE_TOOL_LAYER
    assert "Never say a tag in square brackets, a FEN or a tool's name aloud" in VOICE_TOOL_LAYER
