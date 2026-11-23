"""Tester 20.11, item 12: the coach offered and opened «Двойной удар» of the course «Шахматная тактика», which /learn
showed under a lock. Asan, 22.11: only the lessons open to the student — for a closed one, the coach says which
lessons to pass first. The locks are the site's (frontend src/lib/learn-gating.ts computeLockStates)."""

import json
import time

import pytest

from src import learn_access as la
from src.tools import learning_path as lp

PROGRAMME = {"courses": [
    {"id": "c1", "slug": "basics", "title": "Основы", "level": 1, "modules": [
        {"id": "m1", "title": "Фигуры", "lessons": [{"id": "l1", "slug": "pawn", "title": "Пешка"},
                                                   {"id": "l2", "slug": "knight", "title": "Конь"}]}]},
    {"id": "c2", "slug": "tactics", "title": "Шахматная тактика", "level": 2, "modules": [
        {"id": "m2", "title": "Удары", "lessons": [{"id": "l3", "slug": "double-attack", "title": "Двойной удар"}]}]},
    {"id": "c3", "slug": "endgame", "title": "Эндшпиль", "level": 3, "modules": [
        {"id": "m3", "title": "Пешечные", "lessons": [{"id": "l4", "slug": "square", "title": "Правило квадрата"}]}]},
]}


def done(*ids):
    return {i: {"status": "completed"} for i in ids}


@pytest.fixture
def student(monkeypatch):
    progress = {"value": done("l1")}
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: PROGRAMME)
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: progress["value"])
    la._cache.clear()
    la._floors.clear()
    yield progress
    la._cache.clear()
    la._floors.clear()


@pytest.mark.unit
@pytest.mark.parametrize("completed, floor, locked", [
    ((), None, {"c2", "c3"}),                    # the first course is open
    (("l1",), None, {"c2", "c3"}),               # half of it is not enough
    (("l1", "l2"), None, {"c3"}),                # the first complete opens the second
    (("l1", "l2", "l3"), None, set()),
    (("l4",), None, {"c2"}),                     # a complete course is open itself
    ((), 2, {"c3"}),                             # a Chess Empire student's level opens up to it
    ((), 3, set()),
])
def test_the_locks_are_the_sites(completed, floor, locked):
    states = la.course_states(PROGRAMME, done(*completed), floor)
    assert {cid for cid, st in states.items() if st["locked"]} == locked


@pytest.mark.unit
def test_a_locked_lesson_is_not_opened_and_the_way_is_told(student):
    lesson = {"lesson_id": "l3", "title": "Двойной удар", "course": {"title": "Шахматная тактика"},
              "content": "…", "board_actions": [{"type": "set_position"}], "url": "/learn/tactics/double-attack"}
    out = la.gate_lesson(lesson, "user_a", "ru")
    assert out["locked"] is True and "board_actions" not in out and "content" not in out and "url" not in out
    assert out["unlock_path"][0]["course"] == "Основы"
    assert out["unlock_path"][0]["next"] == [{"title": "Конь", "url": lp._lesson_url(PROGRAMME["courses"][0],
                                                                                    PROGRAMME["courses"][0]["modules"][0]["lessons"][1])}]
    # Open lesson: untouched.
    open_lesson = {"lesson_id": "l2", "title": "Конь", "board_actions": [1]}
    assert la.gate_lesson(dict(open_lesson), "user_a", "ru") == open_lesson


@pytest.mark.unit
def test_a_topic_offers_only_open_lessons_and_no_link_to_a_closed_one(student):
    from src.server import lesson_link_line

    topic = {"site_lessons": [{"lesson_id": "l3", "title": "Двойной удар", "course": "Шахматная тактика", "url": "/learn/tactics/double-attack"}],
             "example": {"source": "site_lesson", "lesson_id": "l3", "url": "/learn/tactics/double-attack",
                         "title": "Двойной удар", "fen": "8/8/8/8/8/8/8/8 w - - 0 1"}}
    out = la.gate_topic(topic, "user_a", "ru")
    assert out["site_lessons"] == [] and out["example"]["source"] == "site_lesson_locked" and "url" not in out["example"]
    assert out["example"]["fen"]  # the position itself still serves the explanation
    assert out["locked_lessons"] == [{"title": "Двойной удар", "course": "Шахматная тактика"}]
    assert out["unlock_path"][0]["course"] == "Основы"
    assert lesson_link_line([json.dumps(out, ensure_ascii=False)], "Двойной удар — это…", "ru") is None


@pytest.mark.unit
def test_the_programme_overview_marks_closed_courses_without_links(student):
    out = lp.get_learning_path("user_a")
    rows = {r["slug"]: r for r in out["courses"]}
    assert "locked" not in rows["basics"] and rows["basics"]["url"]
    assert rows["tactics"]["locked"] is True and "url" not in rows["tactics"]
    assert rows["endgame"]["locked"] is True and out["locked_note"]
    assert out["continue_with"]["lesson_id"] == "l2"


@pytest.mark.unit
def test_a_closed_course_shows_what_it_teaches_and_the_way(student):
    out = lp.get_learning_path("user_a", course="tactics")
    assert out["course"]["locked"] is True and "url" not in out["course"]
    assert out["modules"] == [{"title": "Удары", "lessons": ["Двойной удар"]}]
    assert out["unlock_path"][0]["course"] == "Основы" and out["note"] == la.LOCKED_COURSE_NOTE


@pytest.mark.unit
def test_continue_never_points_into_a_closed_course(student):
    student["value"] = {"l1": {"status": "completed"}, "l3": {"status": "in_progress", "updated_at": "2026-11-20"}}
    assert lp.get_learning_path("user_a")["continue_with"]["lesson_id"] == "l2"


@pytest.mark.unit
def test_a_chess_empire_level_opens_its_courses(student):
    la.note_floor("user_a", la.floor_from_header("2"))
    assert la.gate_lesson({"lesson_id": "l3", "title": "Двойной удар"}, "user_a", "ru") == {
        "lesson_id": "l3", "title": "Двойной удар"}
    la.note_floor("user_a", la.floor_from_header(None))
    assert la.gate_lesson({"lesson_id": "l3", "title": "Двойной удар"}, "user_a", "ru")["locked"] is True


@pytest.mark.unit
@pytest.mark.parametrize("raw, level", [("3", 3), (" 1 ", 1), ("0", None), ("abc", None), ("100", None), (None, None)])
def test_the_floor_header_is_a_level_or_nothing(raw, level):
    assert la.floor_from_header(raw) == level


@pytest.mark.unit
def test_an_unread_programme_hides_nothing(monkeypatch):
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: None)
    la._cache.clear()
    lesson = {"lesson_id": "l3", "title": "Двойной удар"}
    assert la.gate_lesson(dict(lesson), "user_x", "ru") == lesson


@pytest.mark.unit
def test_the_level_travels_in_the_pass_never_from_the_page(monkeypatch):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from src import direct_access as da

    monkeypatch.setenv("COACH_DIRECT_SECRET", "s")
    app = FastAPI()

    @app.post("/api/coach/chat")
    async def chat(request: Request):
        return {"floor": request.headers.get("x-learn-floor")}

    app.add_middleware(da.DirectAccess)
    client = TestClient(app)
    base = {"sub": "u", "tier": "free", "exp": int(time.time()) + 60, "aud": da.AUDIENCE}
    with_floor = da.sign({**base, "floor": 2}, b"s")
    without = da.sign(base, b"s")
    assert client.post("/direct/chat", json={}, headers={"Authorization": f"Bearer {with_floor}"}).json() == {"floor": "2"}
    assert client.post("/direct/chat", json={}, headers={"Authorization": f"Bearer {without}", "x-learn-floor": "9"}).json() == {"floor": None}


@pytest.mark.unit
def test_get_lesson_does_not_even_read_a_locked_lesson(student, monkeypatch):
    read = []
    monkeypatch.setattr(lp, "_query_with_fallback", lambda *a, **k: read.append(k) or [])
    out = lp.get_lesson("Двойной удар", user_id="user_a", locale="ru", show=True)
    assert out["locked"] is True and out["unlock_path"][0]["course"] == "Основы" and read == []
    # An open one is read as before.
    lp.get_lesson("Конь", user_id="user_a", locale="ru")
    assert read


@pytest.mark.unit
def test_the_way_is_the_courses_that_open_it_not_every_one_before(student):
    # No level: the first course, then the second, open the third.
    assert [x["course"] for x in la.unlock_path("user_a", la._states("user_a")["c3"], "ru")] == ["Основы", "Шахматная тактика"]
    # Level 2: the second course is open already — only it stands before the third.
    la.note_floor("user_a", 2)
    path = la.unlock_path("user_a", la._states("user_a")["c3"], "ru")
    assert [x["course"] for x in path] == ["Шахматная тактика"] and path[0]["next"][0]["title"] == "Двойной удар"
