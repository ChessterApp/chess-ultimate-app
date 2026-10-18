"""2026-10-16: the whole programme «Ступени» inside Hermes — steps 4–7 (no lessons on the site) answer
«что такое открытая линия», «расскажи про русскую партию», put their diagrams and games on the board;
«дай задачу» with no theme continues the student's own programme."""

import json

import pytest

from src import config
from src.lesson_texts import _records, book_for_words, book_series, book_title_extra, book_view, clear_cache


@pytest.fixture(autouse=True)
def _fresh_book():
    clear_cache()
    yield
    clear_cache()


def test_the_book_holds_steps_one_to_seven():
    steps = {}
    for r in _records():
        steps[r["docx_step"]] = steps.get(r["docx_step"], 0) + 1
    assert steps[1] + steps[2] + steps[3] == 41 and steps[4] == 15 and steps[5] >= 14 and steps[6] >= 15 and steps[7] >= 15
    assert book_for_words("миттельшпиль")["docx_lesson"] == "12"          # step 1, no module on the site
    assert book_for_words("освобождение поля или линии")["docx_lesson"] == "37"
    with_games = [r for r in _records() if r.get("pgn")]
    assert len(with_games) >= 10 and all(r["pgn"].startswith("1. ") for r in with_games)
    assert sum(len(book_view(r)["diagrams"]) for r in _records() if r["docx_step"] == 4) >= 20   # up to 4 per lesson


@pytest.mark.parametrize("words,step,lesson", [
    ("что такое открытая линия", 4, "50"),
    ("расскажи про заколдованные квадраты", 4, "47"),
    ("как атаковать нерокированного короля", 4, "53"),
    ("партия Ласкер Томас", 4, "54"),
    ("шотландская партия", 5, "61"),               # the first lesson of the series, not a «(продолжение)»
    ("защита двух коней", 5, "68"),                 # «2-х» in the title
    ("оппозиция в эндшпиле", 6, "77"),
    ("русская партия", 7, "91"),
    ("королевский гамбит", 7, "96"),
    ("связка", 1, "8"),
    ("рокировка", 1, "4"),                          # the earlier step wins over «Правильный момент для рокировки»
])
def test_the_lesson_the_words_name(words, step, lesson):
    rec = book_for_words(words)
    assert rec and (rec["docx_step"], rec["docx_lesson"]) == (step, lesson), rec and rec["docx_title"]


@pytest.mark.parametrize("words", ["партия", "дебют", "что такое вилка", "привет", "эндшпиль"])
def test_generic_words_name_no_lesson(words):
    assert book_for_words(words) is None


def test_a_series_and_the_view():
    rec = book_for_words("королевский гамбит")
    assert [r["docx_lesson"] for r in book_series(rec)] == ["96", "97", "98", "99", "100"]
    view = book_view(rec)
    assert view["source"] == "programme_book" and view["title"] == "Королевский Гамбит" and view["step"] == 7
    assert len(view["parts"]) == 4 and view["summary"] and "[Диаграмма" not in view["summary"]
    assert book_title_extra(rec, "королевский гамбит") == 0


def test_get_topic_teaches_from_the_programme_when_the_base_and_the_site_have_nothing(monkeypatch):
    from src.tools import knowledge_topics as kt

    monkeypatch.setattr(kt, "_site_programme_topic", lambda *a, **k: None)
    monkeypatch.setattr(kt, "_lessons_for_words", lambda *a, **k: [])
    monkeypatch.setattr(kt, "_related_lessons", lambda *a, **k: [])
    out = kt.get_topic("заколдованные квадраты")
    assert out["source"] == "programme_book" and out["title"] == "Заколдованные квадраты"
    assert out["board_actions"][0]["type"] == "set_fen" and out["example"]["fen"] == out["positions"][0]["fen"]
    assert "programme" in out["how_to_use"].lower() and out["programme"]["step"] == 4
    # a lesson that writes a game out: the game goes on the board
    out = kt.get_topic("партия Ласкер Томас")
    assert out["source"] == "programme_book" and out["board_actions"][0]["type"] == "load_pgn"
    assert out["game_pgn"].startswith("1. d4 f5") and out["game_pgn"].endswith("1-0")
    # the base's own topic keeps the lead, with the programme's words attached
    out = kt.get_topic("связка")
    assert out["slug"] == "pin" and out["programme_lesson"]["step"] == 1 and "Связка" in out["programme_lesson"]["title"]


def test_lookup_opening_carries_the_programmes_lesson():
    from src.tools.opening_lookup import lookup_opening

    out = lookup_opening("расскажи про шотландскую партию")
    assert out["found"] and out["name"].startswith("Scotch")
    assert out["programme_lesson"]["title"] == "Шотландская партия" and out["programme_lesson"]["step"] == 5
    assert "1.e4 e5 2.Кf3" in out["programme_lesson"]["text"] or "Шотландская" in out["programme_lesson"]["text"]


def _programme():
    return {"courses": [{"id": "c1", "slug": "chess-tactics", "title": "Тактика", "modules": [
        {"id": "m1", "title": "Связка", "lessons": [
            {"id": "l1", "slug": "pin-1", "title": "Связка — Набор 1", "module_id": "m1", "course_id": "c1"},
            {"id": "l2", "slug": "pin-2", "title": "Связка — Набор 2", "module_id": "m1", "course_id": "c1"},
        ]}]}]}


def test_a_puzzle_asked_without_a_theme_continues_the_programme(monkeypatch):
    from src.tools import learning_path as lp
    from src.tools import puzzles as pz

    monkeypatch.setattr(config, "COACH_PUZZLES_FROM_SITE", True)
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: _programme())
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {"l1": {"status": "completed"}})
    monkeypatch.setattr(lp, "get_lesson", lambda lid, **k: {
        "lesson_id": lid, "title": f"Набор {lid}", "course": {"title": "Тактика"}, "url": f"https://chesster.io/learn/{lid}",
        "puzzles": [{"n": 1, "fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "solution": ["Ra8#"]}],
    })
    out = pz.get_puzzle(theme=None, user_id="u1")
    assert out["source"] == "site_lesson" and out["puzzles"][0]["puzzle_id"] == "site:l2:1"
    assert "next set" in out["how_to_show"] and out["board_actions"][0]["type"] == "set_puzzle"
    # the same task is not shown twice; «любую» goes past the programme (Lichess, absent here → its error)
    again = pz.get_puzzle(theme=None, user_id="u1", exclude_ids=["site:l2:1"])
    assert again.get("source") != "site_lesson"
    assert pz.get_puzzle(theme=None, user_id="u1", any=True).get("source") != "site_lesson"


def test_the_tool_handler_reads_the_any_flag(monkeypatch):
    from src.tools import puzzles as pz

    seen = {}
    monkeypatch.setattr(pz, "get_puzzle", lambda **kw: seen.update(kw) or {"puzzles": []})
    pz._handle_get_puzzle({"any": True, "count": 1})
    assert seen.get("any") is True
