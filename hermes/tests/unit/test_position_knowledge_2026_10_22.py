"""2026-10-22: the position on the board recognised — a task of the site's lesson that came as a FEN gets
its solution (src/site_puzzle_lookup), a position on a known trap's line gets the trap's lines
(src/trap_positions), and the answer check reads the object of an attack and a from-to capture."""

from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import config
from src import site_puzzle_lookup as spl
from src.answer_check import CheckContext, check_sentence
from src.server import app
from src.trap_positions import trap_block, traps_at
from src.user_profile import UserProfile

START = chess.STARTING_FEN
# 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nd4 — «Можно мне взять пешку e5 конём?» (prod 19.10: «да, можно»)
BLACKBURNE = "r1bqkbnr/pppp1ppp/8/4p3/2BnP3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
# «Что у меня сейчас под ударом?» (prod 19.10: «Bb5+ … давит на коня c6» — the knight is on a5)
ATTACKED = "r1bqkb1r/ppp2ppp/5n2/n2Pp1N1/2B5/8/PPPP1PPP/RNBQK2R w KQkq - 1 6"
# «Могу я взять пешку d5 на проходе?» (prod 19.10: «обычным взятием — e5xd5»)
EP = "rnbqkbnr/1pp1ppp1/p6p/3pP3/8/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 4"
DECOY = "r6q/ppp1nkb1/3pN3/1P1Pp3/P2P1pn1/B4QP1/4P1Br/1R3RK1 b - - 0 1"

PROGRAMME = {"courses": [{"id": "c1", "slug": "advanced-tactics", "title": "Продвинутая тактика", "modules": [
    {"id": "m1", "title": "Завлечение", "lessons": [
        {"id": "l1", "slug": "decoy-example-1", "title": "Завлечение — пример 1"},
        {"id": "l2", "slug": "decoy-example-2", "title": "Завлечение — пример 2"}]}]}]}
PUZZLES = [
    {"id": "p1", "lesson_id": "l1", "order_index": 1, "fen": DECOY, "solution_move": "h8h2", "hint_text": "Жертва ферзя"},
    {"id": "p2", "lesson_id": "l1", "order_index": 2, "fen": "6k1/5pp1/2r4p/8/6nq/3Q4/1B3PPP/4R1K1 w - - 0 1", "solution_move": "Re8#"},
    {"id": "p3", "lesson_id": "l2", "order_index": 1, "fen": DECOY, "solution_move": "h8h2"},
]
LESSONS = [{"id": "l2", "exercise_fen": "4rkn1/1p3p2/2pP3P/8/3B4/8/P4PP1/2R3K1 w - - 0 1", "solution_move": "d4g7"}]


@pytest.fixture
def index():
    return spl.build_index(PROGRAMME, PUZZLES, LESSONS)


# ── the site's task found by its position ───────────────────────────────────────────────────────

def test_the_task_is_found_by_its_position_whatever_the_flags(index):
    assert len(index) == 3
    hit = spl.site_puzzle_at("r6q/ppp1nkb1/3pN3/1P1Pp3/P2P1pn1/B4QP1/4P1Br/1R3RK1 b KQkq - 5 9", index)
    assert hit["lesson"] == "Завлечение — пример 1" and hit["solution"] == ["Qh2#"] and hit["n"] == 1 and hit["total"] == 2
    assert hit["also_in"] == ["Завлечение — пример 2"]  # the same position in two lessons: both named
    assert hit["url"] == "https://chesster.io/learn/advanced-tactics/decoy-example-1"
    block = spl.site_puzzle_block(hit)
    assert "task 1 of 2 of the lesson «Завлечение — пример 1»" in block and "solution: Qh2#" in block
    assert "Black to move" in block and "Жертва ферзя" in block and "exactly this solution" in block
    exercise = spl.site_puzzle_at("4rkn1/1p3p2/2pP3P/8/3B4/8/P4PP1/2R3K1 w - - 0 1", index)
    assert exercise["solution"] == ["Bg7#"] and exercise["lesson"] == "Завлечение — пример 2"
    assert spl.site_puzzle_at(START, index) is None and spl.site_puzzle_at(BLACKBURNE, index) is None
    assert spl.site_puzzle_block(None) == ""


def test_the_index_is_read_page_by_page_and_kept(monkeypatch):
    calls = []

    def _query(table, select, select_min, url, key, **extra):
        calls.append((table, extra.get("offset")))
        if table == "lesson_puzzles":
            return PUZZLES if extra.get("offset") == "0" else []
        return LESSONS

    monkeypatch.setattr("src.tools.learning_path._query_with_fallback", _query)
    monkeypatch.setattr("src.tools.learning_path.fetch_programme", lambda url=None, key=None: PROGRAMME)
    monkeypatch.setattr(spl, "_PAGE", 3)
    spl.clear_index()
    idx = spl.site_puzzle_index()
    assert len(idx) == 3 and ("lesson_puzzles", "0") in calls and ("lesson_puzzles", "3") in calls
    calls.clear()
    assert spl.site_puzzle_index() is idx and not calls  # cached
    spl.clear_index()


def test_the_lesson_whose_solution_is_legal_here_comes_first():
    # «Эндшпиль — Набор 21» writes h4 with no h-pawn; «Двойной удар — Набор 17» has the same position with Ke5
    fen = "8/8/K7/2p5/2P2k2/8/8/8 b - - 0 1"
    index = {spl.position_key(fen): [
        {"lesson_id": "a", "lesson": "Эндшпиль — Набор 21", "fen": fen, "solution": ["h4"], "n": 1, "total": 8},
        {"lesson_id": "b", "lesson": "Двойной удар — Набор 17", "fen": fen, "solution": ["Ke5"], "n": 4, "total": 8}]}
    hit = spl.site_puzzle_at(fen, index)
    assert hit["lesson"] == "Двойной удар — Набор 17" and hit["solution"] == ["Ke5"] and hit["also_in"] == ["Эндшпиль — Набор 21"]


# ── a known trap recognised by the position ─────────────────────────────────────────────────────

def test_the_trap_is_known_from_the_position_not_the_name():
    hits = traps_at(BLACKBURNE)
    names = {h["name"] for h in hits}
    assert "Blackburne Shilling Trap" in names and "Blackburne Shilling Trap, avoided 4. Nxd4" in names
    trap = next(h for h in hits if h["name"] == "Blackburne Shilling Trap")
    assert trap["walks_in"] and trap["trap_move"] == "Nxe5" and trap["loser"] == "white"
    assert trap["text"] == "4.Nxe5 Qg5 5.Nxf7 Qxg2 6.Rf1 Qxe4+ 7.Be2 Nf3#"
    block = trap_block(BLACKBURNE)
    assert "the tempting Nxe5 here LOSES" in block and "ловушка Блэкберна" in block
    assert "the sound continuation from here is 4.Nxd4 exd4 5.c3" in block
    # after the mistake: the punishment line for Black
    after = trap_block("r1bqkbnr/pppp1ppp/8/4N3/2BnP3/8/PPPP1PPP/RNBQK2R b KQkq - 0 4")
    assert "4...Qg5 5.Nxf7 Qxg2 6.Rf1 Qxe4+ 7.Be2 Nf3# — mate; this is the punishment line Black plays" in after
    assert trap_block(START) == "" and trap_block(ATTACKED) == "" and trap_block("bad fen") == ""


# ── the answer check: the object of an attack, a from-to capture ────────────────────────────────

@pytest.mark.parametrize("fen,sentence,wrong", [
    (ATTACKED, "Лучший ход — Bb5+ с шахом: Bb5+ он и слона уводит из-под удара, и заодно давит на коня c6.", "no knight on c6"),
    (ATTACKED, "Белые нападают на коня c6.", "no knight on c6"),
    (ATTACKED, "White attacks the knight on c6 with the bishop.", "no knight on c6"),
    (EP, "Поэтому на d5 вы можете пойти только обычным взятием — e5xd5 — и это хороший ход.", "a pawn on e5 cannot capture on d5"),
])
def test_the_wrong_sentences_of_the_prod_run_are_caught(fen, sentence, wrong):
    issues = check_sentence(sentence, CheckContext.from_fens([fen], question="Что у меня под ударом?"))
    assert issues and wrong in issues[0], issues


@pytest.mark.parametrize("fen,sentence", [
    (ATTACKED, "Слон c4 атакован конём a5, и его никто не защищает."),
    (ATTACKED, "Можно поставить коня на c6."),  # a destination, not a piece there
    (ATTACKED, "Конь g5 нападает на пешку f7."),
    (ATTACKED, "Не трогай коня a5."),
    (EP, "Бить можно только диагонально: d4xe5 или f4xe5."),  # nothing stands on d4/f4: a plan, not judged
    ("r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2PP1N2/PP3PPP/RNBQ1RK1 w - - 2 7", "После Bb5 ты нападаешь на коня c6."),
    (BLACKBURNE, "Nxd4 — конь забирает коня на d4, и после exd4 пешка d4 висит."),
])
def test_the_true_sentences_pass(fen, sentence):
    assert check_sentence(sentence, CheckContext.from_fens([fen], question="Что мне делать?")) == []


# ── the text turn carries the blocks ────────────────────────────────────────────────────────────

def _turn(monkeypatch, message, fen, user="position-user"):
    monkeypatch.setattr(config, "COACH_SITE_PUZZLE_LOOKUP", True)
    monkeypatch.setattr(config, "COACH_TRAP_POSITIONS", True)
    client = TestClient(app)
    headers = {"X-User-Id": user}
    sid = client.post("/api/coach/sessions", headers=headers).json()["id"]
    seen = {}
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
        mock_profile.return_value = UserProfile(user_id=user)
        agent = MagicMock()

        def _chat(msg, stream_callback=None):
            seen["message"] = msg
            if stream_callback:
                stream_callback("Понял.")
            return "Понял."

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        resp = client.post("/api/coach/chat", headers=headers, json={"message": message, "session_id": sid, "fen": fen})
        assert resp.status_code == 200
    return seen["message"]


def test_the_turn_carries_the_lesson_task_and_the_trap(monkeypatch, index):
    monkeypatch.setattr(spl, "site_puzzle_index", lambda force=False, url=None, key=None: index)
    message = _turn(monkeypatch, "Какой здесь первый ход и почему?", DECOY)
    assert "task of the site's lesson" in message and "solution: Qh2#" in message
    message = _turn(monkeypatch, "Можно мне взять пешку e5 конём?", BLACKBURNE, user="trap-user")
    assert "A known opening trap passes through THIS position" in message and "Nxe5 here LOSES" in message
    assert "task of the site's lesson" not in message
    message = _turn(monkeypatch, "Что такое вилка?", START, user="start-user")
    assert "task of the site's lesson" not in message and "known opening trap" not in message


def test_a_new_puzzle_request_and_the_flags_switch_it_off(monkeypatch, index):
    monkeypatch.setattr(spl, "site_puzzle_index", lambda force=False, url=None, key=None: index)
    monkeypatch.setattr(config, "COACH_PUZZLE_PRESTEP", False)
    message = _turn(monkeypatch, "Дай мне другую задачу", DECOY, user="new-puzzle-user")
    assert "task of the site's lesson" not in message
    monkeypatch.setattr(config, "COACH_SITE_PUZZLE_LOOKUP", False)
    monkeypatch.setattr(config, "COACH_TRAP_POSITIONS", False)

    def _no_flags(mp, message, fen, user):
        client = TestClient(app)
        headers = {"X-User-Id": user}
        sid = client.post("/api/coach/sessions", headers=headers).json()["id"]
        seen = {}
        with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
            mock_profile.return_value = UserProfile(user_id=user)
            agent = MagicMock()
            agent.chat.side_effect = lambda msg, stream_callback=None: seen.setdefault("message", msg) and "Ок."
            mock_agent.return_value = agent
            client.post("/api/coach/chat", headers=headers, json={"message": message, "session_id": sid, "fen": fen})
        return seen["message"]

    assert "task of the site's lesson" not in _no_flags(monkeypatch, "Какой ход?", DECOY, "off-user")
    assert "known opening trap" not in _no_flags(monkeypatch, "Взять e5?", BLACKBURNE, "off-user-2")
