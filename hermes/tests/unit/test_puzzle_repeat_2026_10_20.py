"""2026-10-20: «Ещё задачу» never brings the same task again — the session remembers what it put up
(Asan on production: task 1 of the set «Связка» came back on every «Ещё задачу», on any theme; the
exclusion relied on the model passing exclude_ids and it did not)."""

import json

import pytest

from src import config
from src.server import session_store
from src.tools import learning_path as lp
from src.tools import puzzles as pz


def _programme():
    return {"courses": [{"id": "c1", "slug": "chess-basics", "title": "Основы шахмат", "modules": [
        {"id": "m1", "title": "Связка", "lessons": [
            {"id": "l1", "slug": "pin", "title": "Связка", "module_id": "m1", "course_id": "c1", "lesson_type": "exercise"},
            {"id": "l2", "slug": "pin-continued", "title": "Связка. Продолжение", "module_id": "m1", "course_id": "c1", "lesson_type": "exercise"},
        ]}]}]}


def _lesson(lid, **k):
    tasks = [
        {"n": 1, "fen": "8/7p/8/4K2k/7r/7R/6P1/8 w - - 0 1", "solution": ["g4#"]},
        {"n": 2, "fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "solution": ["Ra8#"]},
    ]
    return {"lesson_id": lid, "title": f"Связка {lid}", "course": {"title": "Основы шахмат"},
            "url": f"https://chesster.io/learn/chess-basics/{lid}", "puzzles": tasks}


@pytest.fixture(autouse=True)
def _site(monkeypatch):
    monkeypatch.setattr(config, "COACH_PUZZLES_FROM_SITE", True)
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: _programme())
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {})
    monkeypatch.setattr(lp, "get_lesson", _lesson)


def _call(sid, **args):
    return json.loads(pz._handle_get_puzzle(args, session_id=sid, user_id="u-repeat"))


def test_the_next_task_each_time_without_exclude_ids():
    session = session_store.create(user_id="u-repeat", session_id="puzzle-repeat-1")
    first = _call(session.id, theme="связка")
    second = _call(session.id, theme="связка")        # «Ещё задачу» — the model repeats the theme
    third = _call(session.id)                         # «Ещё задачу» — no theme at all
    ids = [r["puzzles"][0]["puzzle_id"] for r in (first, second, third)]
    assert ids[0] == "site:l1:1" and len(set(ids)) == 3, ids
    assert session.puzzles_shown >= set(ids)
    # The next set when the first one is used up
    assert ids[2].startswith("site:l1:") or ids[2].startswith("site:l2:")


def test_the_puzzle_on_the_board_counts_as_shown_after_a_restart():
    session = session_store.create(user_id="u-repeat", session_id="puzzle-repeat-2")
    session.apply_board_actions([{"type": "set_puzzle", "fen": "8/7p/8/4K2k/7r/7R/6P1/8 w - - 0 1",
                                  "solution": ["g4#"], "puzzle_id": "site:l1:1"}])
    assert "site:l1:1" in session.puzzles_shown          # from the board, not from memory
    out = _call(session.id, theme="связка")
    assert out["puzzles"][0]["puzzle_id"] == "site:l1:2"
    assert "exclude_ids" not in out["how_to_show"] and "remembers" in out["how_to_show"]


def test_the_models_own_exclude_ids_still_count():
    session = session_store.create(user_id="u-repeat", session_id="puzzle-repeat-3")
    out = _call(session.id, theme="связка", exclude_ids=["site:l1:1", "site:l1:2"])
    assert out["puzzles"][0]["puzzle_id"] == "site:l2:1"


def test_without_a_session_the_tool_works_as_before():
    out = json.loads(pz._handle_get_puzzle({"theme": "связка"}, user_id="u-repeat"))
    assert out["puzzles"][0]["puzzle_id"] == "site:l1:1"
