"""The production blind spots of 2026-10-06 (eval/datasets/blind_spots_v1.jsonl).

Castling through an attacked square called legal, a pawn move «b3» never
looked at, a move of a loaded game judged on the final position, «это
выигрыш» in a tablebase draw, «мат» on a stalemate, a half-open file
mixed up, an en passant capture denied, the move cut out with its arrow mark,
a sentence said twice, weaknesses named with no games.
"""

import chess
import pytest

from src import board_rules
from src.answer_check import CheckContext, SentenceGate, check_sentence
from src.board_markup import MarkupFilter
from src.board_rules import castling_status, known_endgame, rule_facts, structure
from src.past_move import past_position
from src.prompt_builder import moves_in_question_block, question_moves

CAS = "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"  # f1 hit by Bc4
OK_CASTLE = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
NO_RIGHTS = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w kq - 6 5"
RUY = "r1bqk2r/1pppbppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 4 6"
EP = "rnbqkbnr/1pp1pppp/p7/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3"
PASSED = "r2q1rk1/pp2bppp/4bn2/3P4/8/2N2N2/PP2BPPP/R2Q1RK1 b - - 0 12"
STALE = "k7/8/1Q6/8/8/8/8/2K5 b - - 0 1"
WRONG_BISHOP = "7k/8/8/7P/4K3/8/4B3/8 w - - 0 1"
LUCENA = "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"
PHILIDOR = "4k3/8/r7/4PK2/8/8/8/1R6 b - - 0 1"
NOMATE = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"
MATE2 = "r2qkb1r/pp2nppp/3p4/2pNN1B1/2BnP3/3P4/PPP2PPP/R2bK2R w KQkq - 1 1"
GAME = ("1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Nc3 Bc5 5. d3 d6 6. Bg5 h6 7. Bh4 g5 8. Bg3 Bg4 "
        "9. h3 Bxf3 10. Qxf3 Nd4 11. Qd1 c6 12. O-O Qe7 13. a3 O-O-O 14. b4 Bb6 15. a4 a5")


@pytest.fixture(autouse=True)
def _no_tablebase(monkeypatch):
    """No network in unit tests: the tablebase answers from this table."""
    answers = {
        chess.Board(WRONG_BISHOP).epd(): {"category": "draw", "dtz": 0, "dtm": 0, "best_san": "h6", "best_category": "draw"},
        chess.Board(LUCENA).epd(): {"category": "win", "dtz": 1, "dtm": 19, "best_san": "Rd1+", "best_category": "loss"},
        chess.Board(PHILIDOR).epd(): {"category": "draw", "dtz": 0, "dtm": 0, "best_san": "Rh6", "best_category": "draw"},
    }
    monkeypatch.setattr(board_rules, "tablebase", lambda board: answers.get(board.epd()))


# ── Board rules ─────────────────────────────────────────────────────────────

def test_castling_through_an_attacked_square_is_named():
    st = castling_status(chess.Board(CAS))
    assert st["O-O"][0] is False and "f1 is attacked by the black bishop on c4" in st["O-O"][1]
    assert "pieces stand between" in st["O-O-O"][1]


def test_castling_right_lost_with_king_and_rook_at_home():
    legal, why = castling_status(chess.Board(NO_RIGHTS))["O-O"]
    assert not legal and "right to castle is lost" in why


def test_rule_facts_name_castling_en_passant_structure_and_endings():
    assert any("short castling (O-O) is NOT possible" in f for f in rule_facts(chess.Board(CAS)))
    assert any("short castling (O-O) is legal" in f for f in rule_facts(chess.Board(OK_CASTLE)))
    assert any("en passant is available now: exd6" in f for f in rule_facts(chess.Board(EP)))
    assert any("STALEMATED" in f for f in rule_facts(chess.Board(STALE)))
    facts = " ".join(rule_facts(chess.Board(WRONG_BISHOP)))
    assert "DRAW" in facts and "wrong-bishop" in facts
    facts = " ".join(rule_facts(chess.Board(LUCENA)))
    assert "WHITE WINS" in facts and "Rd1+" in facts and "lucena-position" in facts
    assert "philidor-position" in " ".join(rule_facts(chess.Board(PHILIDOR)))
    assert rule_facts(chess.Board()) == []  # nothing worth saying at the start


def test_structure_passed_and_files():
    st = structure(chess.Board(PASSED))
    assert st["passed"][chess.WHITE] == ["d5"] and st["passed"][chess.BLACK] == []
    assert st["files"]["c"] == "open" and st["files"]["e"] == "open"
    assert st["files"]["d"] == "half-open for Black" and st["files"]["a"] == "closed"


def test_known_endgames():
    assert known_endgame(chess.Board(WRONG_BISHOP))["slug"] == "wrong-bishop"
    assert known_endgame(chess.Board(LUCENA))["slug"] == "lucena-position"
    assert known_endgame(chess.Board(PHILIDOR))["slug"] == "philidor-position"
    assert known_endgame(chess.Board("8/8/8/8/8/2k5/8/K1N1N3 w - - 0 1"))["verdict"] == "draw"
    # The right bishop (dark-squared for h8) is a win: not the textbook draw.
    assert known_endgame(chess.Board("7k/8/8/7P/4K3/8/5B2/8 w - - 0 1")) is None


# ── Claims in the answer ────────────────────────────────────────────────────

def _check(fen, sentence, question="", ev=None, tb=None, mate=None):
    ctx = CheckContext.from_fens([fen], question=question)
    ctx.engine_eval, ctx.tablebase, ctx.engine_mate = ev, tb, mate
    return check_sentence(sentence, ctx)


@pytest.mark.parametrize("fen,sentence,question,kw", [
    (CAS, "Yes — you can castle here, and it's perfectly legal.", "Can I castle kingside now?", {}),
    (CAS, "Иә, қысқа рокировка жасай аласың — f1 мен g1 бос.", "Қазір қысқа рокировка жасай аламын ба?", {}),
    (CAS, "Да, рокироваться сейчас можно.", "Можно мне рокироваться?", {}),
    (OK_CASTLE, "Нет, рокироваться сейчас нельзя.", "Можно мне рокироваться в короткую?", {}),
    (STALE, "Чёрные получили мат.", "", {}),
    (WRONG_BISHOP, "Да, это выигрыш — но не автоматический.", "Это выигрыш?", {"ev": 1.13, "tb": "draw"}),
    (PASSED, "Линия d полуоткрыта для белых.", "Какие вертикали здесь открытые и полуоткрытые?", {}),
    (PASSED, "А на линии a только твоя пешка a7, так что для тебя это полуоткрытая линия.", "Какие вертикали открыты?", {}),
    (PASSED, "Пешка a7 — проходная.", "Есть ли проходные пешки?", {}),
    (EP, "Нет, взять на проходе сейчас нельзя.", "Могу ли я побить пешку d5 своей пешкой e5?", {}),
    (NOMATE, "Да, здесь есть мат в два хода.", "Тут есть мат в два хода?", {"ev": 0.88}),
    (MATE2, "Нет, мата в два хода здесь нет.", "Здесь есть мат в два хода?", {"ev": 100.0, "mate": 2}),
])
def test_false_rule_claims_are_caught(fen, sentence, question, kw):
    assert _check(fen, sentence, question, **kw)


@pytest.mark.parametrize("fen,sentence,question,kw", [
    (CAS, "Рокироваться можно, даже если ладья под боем.", "Можно ли рокироваться, если ладья под боем?", {}),
    (CAS, "Нет, короткая рокировка сейчас невозможна: поле f1 бьёт слон c4.", "Можно мне рокироваться?", {}),
    (OK_CASTLE, "Да, короткая рокировка сейчас возможна.", "Можно рокироваться?", {}),
    (NO_RIGHTS, "Нет, рокироваться уже нельзя: король уже ходил.", "Можно рокироваться?", {}),
    (STALE, "Нет, это не мат — это пат.", "Это мат?", {}),
    (WRONG_BISHOP, "Это ничья, хотя у белых лишний слон.", "", {"ev": 1.13, "tb": "draw"}),
    (WRONG_BISHOP, "Белые выиграют, только если чёрный король уйдёт из угла.", "", {"ev": 1.13, "tb": "draw"}),
    (PASSED, "Линии c и e открыты, а линия d полуоткрыта для чёрных.", "Какие вертикали открыты?", {}),
    (PASSED, "Пешка d5 — проходная.", "Есть ли проходные?", {}),
    (EP, "Да, можешь: это взятие на проходе, exd6.", "", {}),
    (EP, "Взятие на проходе возможно только сразу, следующим ходом.", "Можно ли взять на проходе через ход?", {}),
    (MATE2, "Да, есть мат в два хода: Nf6+ gxf6 Bxf7#.", "", {"ev": 100.0, "mate": 2}),
    (NOMATE, "Нет, мата в два хода здесь нет.", "", {"ev": 0.88}),
    (CAS, "Сначала разберись со слоном, а потом рокируйся.", "", {}),
    # Opening theory about files that are not on the board.
    (chess.STARTING_FEN, "Чёрные получают игру по полуоткрытой линии c.", "Как играть против сицилианки?", {}),
    (chess.STARTING_FEN, "Сейчас посмотрю, что это за мат Легаля.", "Что такое мат Легаля?", {}),
])
def test_true_or_general_rule_claims_pass(fen, sentence, question, kw):
    assert _check(fen, sentence, question, **kw) == []


# ── Moves in the question ───────────────────────────────────────────────────

def test_castling_in_words_and_zeros_with_the_reason():
    for q in ("Можно мне сейчас рокироваться в короткую?", "А если 0-0?", "Can I castle kingside now?",
              "Қазір қысқа рокировка жасай аламын ба?"):
        named = question_moves(q, CAS)
        assert [m["san"] for m in named] == ["O-O"], q
        assert "f1 is attacked" in named[0]["verdict"]
    assert "right to castle is lost" in question_moves("Можно сделать короткую рокировку?", NO_RIGHTS)[0]["verdict"]
    both = {m["san"]: m["legal"] for m in question_moves("Можно рокироваться?", OK_CASTLE)}
    assert both == {"O-O": True, "O-O-O": False}


@pytest.mark.parametrize("q", ["А если b3?", "Если пешка пойдёт b3, чтобы у слона было место?", "What about b3?"])
def test_a_bare_pawn_move_asked_about_is_a_move(q):
    named = question_moves(q, RUY)
    assert [m["san"] for m in named] == ["b3"] and named[0]["legal"]


@pytest.mark.parametrize("q", ["Почему слон не может отступить на b3?", "Смотри на поле b3"])
def test_a_square_is_not_a_pawn_move(q):
    assert [m["san"] for m in question_moves(q, RUY)] == []


def test_capturing_the_pawn_that_just_moved_two_squares_is_en_passant():
    named = question_moves("Могу ли я побить пешку d5 своей пешкой e5?", EP)
    assert [m["san"] for m in named] == ["exd6"] and "en passant" in named[0]["verdict"]


# ── A move of the game on the board ────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "А что было бы, если бы на 8-м ходу я взял слоном на g5 вместо Bg3?",
    "А если бы вместо Bg3 я сыграл Bxg5?",
    "What if I had played 8.Bxg5 instead?",
])
def test_the_question_goes_to_that_move_of_the_game(q):
    past = past_position(q, GAME)
    assert past and past["number"] == 8 and past["played"] == "Bg3" and past["color"] == chess.WHITE
    named = question_moves(q, past["fen"])
    bxg5 = next(m for m in named if m["san"] == "Bxg5")
    assert bxg5["legal"]
    block = moves_in_question_block(q, past["fen"], [m for m in named if m["san"] != "Bg3"], where=past["label"])
    assert "NOT on the final position" in block and "8.Bg3" in block


def test_black_move_number_and_no_moment():
    past = past_position("На 9-м ходу чёрные взяли Bxf3 — а если бы ...Bh5?", GAME)
    assert past["color"] == chess.BLACK and past["played"] == "Bxf3"
    assert past_position("А если сейчас Bxg5?", GAME) is None
    assert past_position("На 8-м ходу что было?", None) is None


# ── The move cut out with its arrow ────────────────────────────────────────

def _stream(text, fen, size):
    f = MarkupFilter(fen)
    out = []
    for i in range(0, len(text), size):
        out.append(f.feed(text[i:i + size])[0])
    return "".join(out) + f.flush()


@pytest.mark.parametrize("text,want", [
    ("Начни с шаха — [[arrows: c1d1 green]]. Король уходит.", "Начни с шаха — Rd1+. Король уходит."),
    ("Правильный первый ход — [[arrows: c1d1]]", "Правильный первый ход — Rd1+"),
    ("Смотри: [[arrows: c1c4 green]] — ладья встаёт на четвёртую.", "Смотри: Rc4 — ладья встаёт на четвёртую."),
    ("Ладья идёт на d1 [[arrows: c1d1]] с шахом.", "Ладья идёт на d1 с шахом."),
    ("Мост строится так. [[arrows: c1c4 green]] Ладья на четвёртую.", "Мост строится так. Ладья на четвёртую."),
])
@pytest.mark.parametrize("size", [2, 3, 5, 50])
def test_an_arrow_standing_for_the_move_is_written_out(text, want, size):
    assert _stream(text, LUCENA, size) == want


def test_a_sentence_said_twice_is_shown_once():
    g = SentenceGate(CheckContext.from_fens([chess.STARTING_FEN]))
    text = "Хороший вопрос — давай проверим, что там на самом деле. Хороший вопрос — давай проверим, что там на самом деле.\n\nДальше."
    shown = "".join(t for i in range(0, len(text), 4) for t, issues, _ in g.feed(text[i:i + 4]) if not issues)
    shown += "".join(t for t, issues, _ in g.flush() if not issues)
    assert shown.count("Хороший вопрос") == 1 and "Дальше." in shown


def test_no_games_tells_the_coach_to_say_so(monkeypatch):
    from src.tools import weakness_tracker as wt

    monkeypatch.setattr(wt, "get_user_games", lambda **kw: [])
    out = wt.weakness_tracker(user_id="u1")
    assert out["games_analyzed"] == 0 and "Do not name weaknesses" in out["note"]


# ── Every topic of the site's programme links its own lessons ──────────────

def _programme_fixture(monkeypatch):
    import json
    from pathlib import Path

    from src.tools import learning_path as lp

    prog = json.loads((Path(__file__).resolve().parents[2] / "eval/fixtures/site_programme_2026-10-06.json").read_text())
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: prog)
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {})
    return prog


def test_every_module_topic_links_its_own_lessons(monkeypatch):
    from src.tools import knowledge_topics as kt

    prog = _programme_fixture(monkeypatch)
    sets = {"mate-in-3-moves", "winning-the-queen", "pins-endgames", "deflection-luring"}
    for c in prog["courses"]:
        if c["slug"] in sets:
            continue
        for m in c["modules"]:
            if m["title"] in ("Основы шахмат", "Тесты"):
                continue
            r = kt.get_topic(m["title"], show=False)
            modules = {x.get("module") for x in r.get("site_lessons") or []}
            assert m["title"] in modules, (m["title"], r.get("slug") or r.get("source"), modules)


@pytest.mark.parametrize("query,module", [
    ("Ловля фигуры", "Ловля фигуры"), ("выигрыш ферзя", "Выигрыш ферзя"), ("Вкусная пешка", "Вкусная пешка"),
    ("Разрушение прикрытия короля", "Разрушение прикрытия короля"), ("мат в 3 хода", "Мат в 3 хода"),
])
def test_former_misses(monkeypatch, query, module):
    from src.tools import knowledge_topics as kt

    _programme_fixture(monkeypatch)
    lessons = kt.get_topic(query, show=False).get("site_lessons") or []
    assert lessons and lessons[0]["module"] == module


def test_no_lesson_by_one_shared_word(monkeypatch):
    from src.tools import knowledge_topics as kt

    _programme_fixture(monkeypatch)
    assert not kt.get_topic("испанская партия", show=False).get("site_lessons")
    assert not kt.get_topic("Лусена", show=False).get("site_lessons")  # no «Стоимость фигур» via «мост»


# ── The student's position stays on the board ──────────────────────────────

@pytest.mark.parametrize("message,has_fen,live,locked", [
    ("Задача из урока «Пример 5» (курс «Продвинутая тактика»). Какой здесь первый ход и почему?", True, False, True),
    ("Как здесь выиграть? Объясни план.", True, False, True),
    ("Какой здесь лучший ход?", True, False, True),
    ("Покажи пример связки", True, False, False),
    ("Что такое связка?", True, False, False),
    ("Дай задачу на вилку", True, False, False),
    ("Какой здесь лучший ход?", False, False, False),
    ("Объясни связку", False, True, True),
])
def test_board_lock_rule(message, has_fen, live, locked):
    from src.server import _board_lock_for_turn

    assert bool(_board_lock_for_turn(message, has_fen, live, chess.STARTING_FEN)) is locked


def test_locked_tools_keep_the_board(monkeypatch):
    import json

    from src.sessions import session_store
    from src.tools import knowledge_topics as kt
    from src.tools import learning_path as lp

    _programme_fixture(monkeypatch)
    monkeypatch.setattr(lp, "get_lesson", lambda **kw: {"title": "x", "board_actions": [{"type": "set_puzzle", "fen": "8/8/8/8/8/8/8/K6k w - - 0 1"}]})
    session = session_store.create(user_id="lock-test")
    session.lock_board(chess.STARTING_FEN)
    out = json.loads(kt._handle_get_topic({"topic": "связка"}, session_id=session.id))
    assert "board_actions" not in out and "stays on the board" in out["board_hint"]
    out = json.loads(lp._handle_get_lesson({"lesson": "Связка"}, session_id=session.id))
    assert "board_actions" not in out and "stays on the board" in out["board_hint"]
    session.lock_board(None)
    out = json.loads(kt._handle_get_topic({"topic": "связка"}, session_id=session.id))
    assert "stays on the board" not in (out.get("board_hint") or "")


# ── Voice (2026-10-06 voice bench): the king, check, files, whose piece ────

@pytest.mark.parametrize("fen,sentence,question", [
    ("k7/8/3Q4/8/8/8/8/2K5 w - - 0 1", "Если ты пойдешь ферзем на b6, король может просто пойти на a7.",
     "Хочу поставить ферзя на b6, чтобы запереть короля. Хорошо?"),
    (NO_RIGHTS, "Сейчас рокировка невозможна, потому что твой король находится под шахом.", "Можно рокироваться?"),
    (PASSED, "Смотри, полностью открытых вертикалей тут нет, но вертикали 'c' и 'e' наполовину свободны.", "Какие вертикали открыты?"),
])
def test_voice_claims_are_caught(fen, sentence, question):
    assert check_sentence(sentence, CheckContext.from_fens([fen], question=question))


@pytest.mark.parametrize("fen,sentence,question", [
    ("k7/8/8/8/8/8/1Q6/2K5 b - - 0 1", "Король может пойти на a7.", "Куда пойдёт король?"),
    (NO_RIGHTS, "Рокироваться нельзя, если король под шахом.", "Можно ли рокироваться под шахом?"),
    ("4k3/8/8/8/8/8/8/4K2r w - - 0 1", "Твой король под шахом!", "Что делать?"),
])
def test_true_voice_claims_pass(fen, sentence, question):
    assert check_sentence(sentence, CheckContext.from_fens([fen], question=question)) == []


def test_whose_piece_issue_names_the_real_occupant():
    issues = check_sentence("Зато ваша пешка на d5 под ударом.", CheckContext.from_fens([NOMATE], question="Тут есть мат?"))
    assert issues and "the black knight stands there" in issues[0]


def test_idea_note_leads_with_the_verdict(monkeypatch):
    from src import prompt_builder as pb

    moves = pb.question_moves("Хочу поставить ферзя на b6", "k7/8/3Q4/8/8/8/8/2K5 w - - 0 1")
    hypo = {"note": "- Qb6 (White): STALEMATE", "items": [{"san": "Qb6", "headline": "Qb6 is stalemate — an immediate draw"}]}
    note = pb.voice_idea_note(moves, hypo)
    assert note.index("VERDICT: Qb6 is stalemate") < note.index("Played on the board")


def test_a_general_castling_rule_names_no_move():
    assert question_moves("Можно ли рокироваться, если моя ладья под боем?", chess.STARTING_FEN) == []
    assert question_moves("Can I castle if my rook is attacked?", chess.STARTING_FEN) == []
    assert [m["san"] for m in question_moves("А если рокироваться?", OK_CASTLE)] == ["O-O", "O-O-O"]


@pytest.mark.parametrize("text,lang", [
    ("А если пешка пойдёт на b3?", "ru"), ("Can I castle kingside now?", "en"),
    ("Hozir qisqa roliklar yasay olamanmi?", None), ("Қазір қысқа рокировка жасай аламын ба?", "kk"),
])
def test_spoken_language(text, lang):
    from src.server import _spoken_language

    assert _spoken_language(text) == lang


@pytest.mark.parametrize("fen,sentence", [
    (WRONG_BISHOP, "Видишь, поле превращения твоей пешки на h8 чёрного цвета, а твой слон белопольный."),
    (LUCENA, "Сейчас наш король на b8 и он мешает своей же пешке."),
])
def test_no_false_alarm_on_whose_piece(fen, sentence):
    assert check_sentence(sentence, CheckContext.from_fens([fen])) == []


@pytest.mark.parametrize("sentence,caught", [
    ("Видишь, какой нюанс — слон на е2 чернопольный, а поле превращения на h8 белое.", True),  # Cyrillic «е2»
    ("Слон на e2 белопольный, а поле h8 чёрное.", False),
    ("Поле h1 светлое.", False),
    ("The bishop on e2 is dark-squared.", True),
])
def test_square_colours(sentence, caught):
    assert bool(check_sentence(sentence, CheckContext.from_fens([WRONG_BISHOP]))) is caught


@pytest.mark.parametrize("sentence,caught", [
    ("Нет, рокироваться нельзя, если твоя ладья находится под боем.", True),
    ("Да, рокироваться можно, если только ваша ладья не находится под боем прямо сейчас.", True),
    ("По правилам, рокироваться можно, даже если ладья под боем.", False),
    ("Рокироваться нельзя, если король под шахом или проходит через битое поле.", False),
])
def test_the_castling_rule_with_an_attacked_rook(sentence, caught):
    issues = check_sentence(sentence, CheckContext.from_fens([chess.STARTING_FEN], question="Можно ли рокироваться, если моя ладья под боем?"))
    assert bool(issues) is caught
    if caught:
        assert "allowed when the rook is attacked" in issues[0]  # the rule, not this board


def test_direct_answer_layer_switch(monkeypatch):
    from src import config
    from src import prompt_builder as pb

    monkeypatch.setattr(config, "COACH_DIRECT_ANSWERS", True)
    assert "FIRST sentence answers it" in pb.direct_answer_layer()
    monkeypatch.setattr(config, "COACH_DIRECT_ANSWERS", False)
    assert pb.direct_answer_layer() == ""


# ── Production voice, 2026-10-07 ───────────────────────────────────────────────
QB6_BOARD = "k7/8/3Q4/8/8/8/8/2K5 w - - 0 1"


@pytest.mark.parametrize("words,san", [
    ("Хочу сыграть ферзь b6, чтобы запереть короля. Хорошо?", "Qb6"),  # what speech recognition wrote
    ("а если ферзь b6?", "Qb6"),
    ("давай ферзь на b6", "Qb6"),
    ("ферзь b6 атакует короля?", None),  # no cue to play: a piece and a square
    ("Если ферзь d6 уйдёт?", None),  # the queen already stands on d6
])
def test_spoken_piece_and_square(words, san):
    found = [m["san"] for m in question_moves(words, QB6_BOARD) if m.get("legal")]
    assert found == ([san] if san else [])


@pytest.mark.parametrize("sentence,question,caught", [
    # the true «Qb6 — пат» was «corrected» into a falsehood on production
    ("Слушай, ферзь на b6 — звучит логично, но тогда королю некуда двигаться, получается пат, и это ничья.",
     "Хочу сыграть ферзь b6, чтобы запереть короля. Хорошо?", False),
    ("Тогда это ничья, пат.", "Хочу сыграть ферзь b6, чтобы запереть короля. Хорошо?", False),
    ("Ферзь на b6 — это выигрыш.", "Хочу сыграть ферзь b6, чтобы запереть короля. Хорошо?", True),
    ("Это ничья.", "Это ничья?", True),  # this board: White wins
])
def test_result_after_the_students_move(sentence, question, caught):
    ctx = CheckContext.from_fens([QB6_BOARD], question=question)
    ctx.tablebase, ctx.engine_eval = "White wins", 20.0
    assert bool(check_sentence(sentence, ctx)) is caught
