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


# ── «Дай три задачи»: several at once (Asan, 20.10) ─────────────────────────

@pytest.mark.parametrize("text,n", [
    ("дай три задачи на связку", 3), ("дай мне две задачки", 2), ("пару задач на вилку", 2), ("несколько задач", 3),
    ("дай 5 задач", 5), ("give me two puzzles", 2), ("a few puzzles on pins", 3), ("дай задачу", None),
    ("задачу на мат в два хода", None), ("реши три хода", None),
])
def test_the_number_of_puzzles_the_words_ask_for(text, n):
    assert pz.count_in_words(text) == n


def test_several_tasks_at_once_from_the_programme_in_order():
    session = session_store.create(user_id="u-repeat", session_id="puzzle-many-1")
    out = _call(session.id, theme="связка", count=3)
    ids = [p["puzzle_id"] for p in out["puzzles"]]
    assert ids == ["site:l1:1", "site:l1:2", "site:l2:1"] and out["count"] == 3     # the set, then the next set
    assert out["on_board"] == "site:l1:1" and out["board_actions"][0]["puzzle_id"] == "site:l1:1"
    assert "3 tasks are in this result" in out["how_to_show"] and "board_control set_puzzle" in out["how_to_show"]
    assert session.puzzles_shown >= set(ids)
    # the next request continues after all three
    assert _call(session.id, theme="связка")["puzzles"][0]["puzzle_id"] == "site:l2:2"


def test_the_words_set_the_count_when_the_model_does_not():
    out = json.loads(pz._handle_get_puzzle({"theme": "связка"}, session_id="puzzle-many-2", user_id="u-repeat",
                                           student_message="дай мне три задачи на связку"))
    assert out["count"] == 3 and len(out["puzzles"]) == 3
    out = json.loads(pz._handle_get_puzzle({"user_id": "u-repeat"}, student_message="дай пару задач"))
    assert out["count"] == 2 and out["puzzles"][0].get("next_in_programme")


def test_the_card_says_how_many_are_lined_up():
    from src.tool_summaries import build_summary

    session = session_store.create(user_id="u-repeat", session_id="puzzle-many-3")
    raw = pz._handle_get_puzzle({"theme": "связка", "count": 3}, session_id=session.id, user_id="u-repeat")
    card = build_summary("get_puzzle", {"theme": "связка", "count": 3}, raw)
    assert card["kind"] == "puzzle" and card["puzzle_id"] == "site:l1:1" and card["queued"] == 2
    one = build_summary("get_puzzle", {"theme": "связка"}, pz._handle_get_puzzle({"theme": "связка"}, user_id="u-repeat"))
    assert "queued" not in one


# ── the queue and the text pre-step (21.10: «Ещё задачу» left to the model hinted at the old task) ──────

def test_the_queue_serves_the_next_task_on_dalshe_and_the_last_theme_on_more():
    session = session_store.create(user_id="u-repeat", session_id="puzzle-queue-1")
    out = _call(session.id, theme="связка", count=3)
    assert len(session.puzzle_queue) == 2 and session.last_puzzle_theme == "связка"
    nxt = json.loads(pz._handle_get_puzzle({}, session_id=session.id, user_id="u-repeat", student_message="дальше"))
    assert nxt["from_queue"] and nxt["puzzles"][0]["puzzle_id"] == out["puzzles"][1]["puzzle_id"] and nxt["left_in_queue"] == 1
    assert nxt["board_actions"][0]["type"] == "set_puzzle" and "lined up after it" in nxt["how_to_show"]
    nxt2 = json.loads(pz._handle_get_puzzle({}, session_id=session.id, user_id="u-repeat", student_message="сдаюсь, давай следующую"))
    assert nxt2["puzzles"][0]["puzzle_id"] == out["puzzles"][2]["puzzle_id"] and not session.puzzle_queue
    # «ещё задачу» with the queue empty: the same theme as before, the next task after the three
    more = json.loads(pz._handle_get_puzzle({}, session_id=session.id, user_id="u-repeat", student_message="ещё задачу"))
    assert more["puzzles"][0]["puzzle_id"] not in {p["puzzle_id"] for p in out["puzzles"]} and more["theme"] in ("pin", "связка")


def test_the_voice_intent_reads_dalshe_only_with_a_queue():
    from src.intent import read_intent

    assert read_intent("дальше", fen=chess_start(), puzzle_queue=True) == {"kind": "puzzle", "theme": None}
    assert read_intent("дальше", fen=chess_start(), puzzle_queue=False)["kind"] == "none"


def chess_start():
    return "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_the_text_turn_puts_the_puzzle_up_itself(monkeypatch):
    from unittest.mock import MagicMock, patch

    from fastapi.testclient import TestClient

    from src.server import app
    from src.user_profile import UserProfile

    client = TestClient(app)
    user = {"X-User-Id": "u-repeat"}
    sid = client.post("/api/coach/sessions", headers=user).json()["id"]
    seen = {}
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
        mock_profile.return_value = UserProfile(user_id="u-repeat")
        agent = MagicMock()

        def _chat(message, stream_callback=None):
            seen["message"] = message
            if stream_callback:
                stream_callback("Задача на доске.")
            return "Задача на доске."

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent

        def turn(text):
            resp = client.post("/api/coach/chat", headers=user, json={"message": text, "session_id": sid, "fen": chess_start()})
            frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
            puzzles = [a for f in frames for a in f.get("board_actions", []) if a.get("type") == "set_puzzle"]
            cards = [f["tool_result"] for f in frames
                     if isinstance(f.get("tool_result"), dict) and f["tool_result"].get("tool") == "get_puzzle" and f["tool_result"].get("summary")]
            return puzzles, cards, seen["message"]

        p1, cards, msg = turn("дай задачу на связку")
        assert p1 and p1[0]["puzzle_id"] == "site:l1:1" and cards and cards[0]["summary"]["kind"] == "puzzle"
        assert "ALREADY on the board (the system put it there)" in msg and "Do not call get_puzzle" in msg
        p2, _, _ = turn("Ещё задачу")
        assert p2 and p2[0]["puzzle_id"] == "site:l1:2"                        # the next, not the same
        p3, cards3, msg3 = turn("дай три задачи на связку")   # two tasks are left in the fixture after the first two
        assert p3 and p3[0]["puzzle_id"] == "site:l2:1" and cards3[0]["summary"].get("queued") == 1 and "1 more is lined up" in msg3
        p4, _, _ = turn("дальше")
        assert p4 and p4[0]["puzzle_id"] == "site:l2:2"                        # from the queue, no new lookup
        none, _, msg5 = turn("что такое связка?")
        assert not none and "the system put it there" not in msg5

