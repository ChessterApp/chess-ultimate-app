"""get_learning_path / get_lesson / training_recommender over a fake programme.

``_supabase_query`` is routed by table so the tools read a small, realistic copy
of the site's tables (courses → modules → lessons, lesson_puzzles, user_progress).
"""

import json
from unittest.mock import patch

import pytest

from src.tools import learning_path as lp
from src.tools.learning_path import get_learning_path, get_lesson, find_lessons, _solution_san
from src.tools.training_recommender import training_recommender, match_lessons


COURSES = [
    {"id": "c1", "slug": "chess-basics", "title": "Chess Basics", "title_ru": "Основы шахмат",
     "title_kk": "Шахмат негіздері", "description": "Basics", "description_ru": "Основы",
     "level": "beginner", "order_index": 1},
    {"id": "c2", "slug": "tactics-101", "title": "Tactics", "title_ru": "Тактика",
     "title_kk": None, "description": None, "description_ru": None, "level": "intermediate", "order_index": 2},
]
MODULES = [
    {"id": "m1", "course_id": "c1", "title": "Pieces", "title_ru": "Фигуры", "order_index": 1},
    {"id": "m2", "course_id": "c2", "title": "Double attacks", "title_ru": "Двойные удары", "order_index": 1},
    {"id": "m3", "course_id": "c2", "title": "Endgames", "title_ru": "Эндшпиль", "order_index": 2},
]
LESSONS = [
    {"id": "l1", "slug": "the-king", "module_id": "m1", "title": "The King", "title_ru": "Король",
     "lesson_type": "theory", "exercise_type": None, "order_index": 1},
    {"id": "l2", "slug": "the-rook", "module_id": "m1", "title": "The Rook", "title_ru": "Ладья",
     "lesson_type": "exercise", "exercise_type": "one_move_puzzle", "order_index": 2},
    {"id": "l3", "slug": "knight-fork", "module_id": "m2", "title": "Knight Fork", "title_ru": "Вилка конём",
     "lesson_type": "exercise", "exercise_type": "one_move_puzzle", "order_index": 1},
    {"id": "l4", "slug": "king-and-pawn", "module_id": "m3", "title": "King and Pawn",
     "title_ru": "Король и пешка", "lesson_type": "theory", "exercise_type": None, "order_index": 1},
]
FORK_FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
LESSON_L3_FULL = {
    **LESSONS[2],
    "content": "A knight attacks two pieces at once.", "content_ru": "Конь нападает на две фигуры сразу.",
    "exercise_fen": "6k1/5ppp/8/8/8/8/5PPP/3N2K1 w - - 0 1",
    "solution_move": "d1e3", "solution_line": None, "exercise_solution": None,
    "hint_text": "Look for a knight jump", "hint_text_ru": "Ищите прыжок коня",
    "success_message": None, "success_message_ru": None,
    "lesson_puzzles": [
        {"id": "p2", "order_index": 2, "fen": "6k1/8/8/8/8/8/8/R3K3 w - - 0 1", "solution_move": "a1a8",
         "hint_text": None, "success_message": None},
        {"id": "p1", "order_index": 1, "fen": FORK_FEN, "solution_move": "f3e5",
         "hint_text": "Central knight", "success_message": "Yes!"},
    ],
}
PROGRESS = [
    {"lesson_id": "l1", "status": "completed", "score": 100, "updated_at": "2026-09-20T10:00:00+00:00",
     "completed_at": "2026-09-20T10:00:00+00:00"},
    {"lesson_id": "l2", "status": "in_progress", "score": None, "updated_at": "2026-09-22T10:00:00+00:00",
     "completed_at": None},
]


def _fake_query(progress=PROGRESS, lesson_full=LESSON_L3_FULL, fail=()):
    calls = []

    def q(table, params, url=None, key=None):
        calls.append((table, dict(params)))
        if table in fail:
            return None
        if table == "courses":
            return list(COURSES)
        if table == "modules":
            return list(MODULES)
        if table == "lessons":
            if params.get("id"):
                wanted = params["id"].split("eq.")[1]
                return [lesson_full] if lesson_full["id"] == wanted else []
            return list(LESSONS)
        if table == "user_progress":
            return list(progress)
        raise AssertionError(f"unexpected table {table}")

    q.calls = calls
    return q


@pytest.fixture(autouse=True)
def _fresh_cache():
    lp.clear_programme_cache()
    yield
    lp.clear_programme_cache()


@pytest.mark.unit
class TestLearningPath:
    def test_overview_counts_progress_and_continue_lesson(self):
        fake = _fake_query()
        with patch("src.tools.learning_path._supabase_query", fake):
            out = get_learning_path("u1", locale="ru")
        assert out["lessons_total"] == 4 and out["lessons_completed"] == 1
        by_slug = {c["slug"]: c for c in out["courses"]}
        assert by_slug["chess-basics"]["title"] == "Основы шахмат"
        assert by_slug["chess-basics"]["lessons_completed"] == 1
        assert by_slug["tactics-101"]["url"] == "https://chesster.io/learn/tactics-101"
        # The in-progress lesson wins over "first not completed".
        assert out["continue_with"]["slug"] == "the-rook"
        assert out["continue_with"]["status"] == "in_progress"
        assert out["continue_with"]["url"] == "https://chesster.io/learn/chess-basics/the-rook"
        # Programme read once (3 tables) + progress.
        assert [t for t, _ in fake.calls] == ["courses", "modules", "lessons", "user_progress"]
        json.dumps(out)  # serialisable

    def test_kazakh_titles_fall_back_to_russian(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            out = get_learning_path("u1", locale="kz")
        titles = [c["title"] for c in out["courses"]]
        assert titles == ["Шахмат негіздері", "Тактика"]

    def test_course_expanded_with_statuses(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            out = get_learning_path("u1", locale="en", course="basics")
        assert out["course"]["slug"] == "chess-basics"
        lessons = out["modules"][0]["lessons"]
        assert [(l["slug"], l["status"]) for l in lessons] == [("the-king", "completed"), ("the-rook", "in_progress")]
        assert lessons[0]["score"] == 100
        assert lessons[0]["title"] == "The King"

    def test_unknown_course_lists_the_real_ones(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            out = get_learning_path("u1", course="quantum chess")
        assert "error" in out
        assert [c["slug"] for c in out["courses"]] == ["chess-basics", "tactics-101"]

    def test_no_progress_still_answers(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query(fail=("user_progress",))):
            out = get_learning_path("u1")
        assert out["continue_with"]["slug"] == "the-king"
        assert "note" in out

    def test_programme_unavailable_is_an_error(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query(fail=("courses",))):
            out = get_learning_path("u1")
        assert "error" in out

    def test_programme_is_cached(self):
        fake = _fake_query()
        with patch("src.tools.learning_path._supabase_query", fake):
            get_learning_path("u1")
            get_learning_path("u1")
        assert [t for t, _ in fake.calls].count("courses") == 1
        assert [t for t, _ in fake.calls].count("user_progress") == 2


@pytest.mark.unit
class TestFindLessons:
    def test_by_slug_id_and_title_fragment(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            prog = lp.fetch_programme()
        assert [l["id"] for _, _, l in find_lessons(prog, "knight-fork")] == ["l3"]
        assert [l["id"] for _, _, l in find_lessons(prog, "L2")] == ["l2"]
        assert [l["id"] for _, _, l in find_lessons(prog, "вилка")] == ["l3"]
        assert [l["id"] for _, _, l in find_lessons(prog, "король")] == ["l1", "l4"]  # substring in both
        assert find_lessons(prog, "") == []

    def test_token_overlap(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            prog = lp.fetch_programme()
        assert [l["id"] for _, _, l in find_lessons(prog, "урок про пешку и короля")] == ["l4"]


@pytest.mark.unit
class TestGetLesson:
    def test_full_lesson_with_san_solutions(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            out = get_lesson("knight-fork", user_id="u1", locale="ru")
        assert out["title"] == "Вилка конём"
        assert out["course"]["slug"] == "tactics-101" and out["module"] == "Двойные удары"
        assert out["content"] == "Конь нападает на две фигуры сразу."
        assert out["url"] == "https://chesster.io/learn/tactics-101/knight-fork"
        assert out["student_status"] == "not_started"
        assert out["exercise"]["solution"] == ["Ne3"]          # d1e3 → SAN
        assert out["exercise"]["hint"] == "Ищите прыжок коня"
        assert out["board_puzzle"] == {"fen": "6k1/5ppp/8/8/8/8/5PPP/3N2K1 w - - 0 1", "solution": ["Ne3"]}
        # Puzzles come in order_index order, UCI converted to SAN.
        assert [p["n"] for p in out["puzzles"]] == [1, 2]
        assert out["puzzles"][0]["solution"] == ["Nxe5"]
        assert out["puzzles"][1]["solution"] == ["Ra8+"]
        assert out["puzzles"][0]["hint"] == "Central knight"

    def test_english_locale_uses_base_columns(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            out = get_lesson("knight-fork", locale="en")
        assert out["content"] == "A knight attacks two pieces at once."
        assert out["exercise"]["hint"] == "Look for a knight jump"
        assert "student_status" not in out

    def test_ambiguous_title_lists_candidates(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            out = get_lesson("король", locale="ru")
        assert out["ambiguous"] is True
        assert [l["slug"] for l in out["lessons"]] == ["the-king", "king-and-pawn"]

    def test_unknown_lesson(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            out = get_lesson("ферзевый гамбит для чайников")
        assert "error" in out

    def test_content_is_capped(self):
        long_lesson = {**LESSON_L3_FULL, "content_ru": "х" * 10_000}
        with patch("src.tools.learning_path._supabase_query", _fake_query(lesson_full=long_lesson)):
            out = get_lesson("knight-fork", locale="ru")
        assert out["content_truncated"] is True
        assert len(out["content"]) == lp.CONTENT_CHAR_CAP


@pytest.mark.unit
def test_solution_san_handles_uci_san_and_lines():
    fen = "6k1/5ppp/8/8/8/8/5PPP/3N2K1 w - - 0 1"
    assert _solution_san(fen, "d1e3") == ["Ne3"]
    assert _solution_san(fen, "Ne3") == ["Ne3"]
    assert _solution_san(fen, ["d1e3", "g8f8", "e3d5"]) == ["Ne3", "Kf8", "Nd5"]
    assert _solution_san(fen, json.dumps([{"move": "Ne3", "explanation": "x"}])) == ["Ne3"]
    assert _solution_san(fen, None) == []
    assert _solution_san("not a fen", "d1e3") == ["d1e3"]  # unparseable → raw


@pytest.mark.unit
class TestRecommenderOnProgramme:
    def _prog(self):
        with patch("src.tools.learning_path._supabase_query", _fake_query()):
            return lp.fetch_programme()

    def test_weakness_maps_to_real_lesson(self):
        prog = self._prog()
        progress = {r["lesson_id"]: r for r in PROGRESS}
        out = training_recommender(
            "u1", locale="ru", _weaknesses=[{"category": "tactics", "frequency": 4}],
            _focus=[], _programme=prog, _progress=progress,
        )
        rec = out["recommendations"][0]
        assert rec["type"] == "lesson" and rec["lesson_slug"] == "knight-fork"
        assert rec["url"] == "https://chesster.io/learn/tactics-101/knight-fork"
        assert rec["weakness_addressed"] == "tactics"
        assert "fork" in rec["puzzle_themes"]
        assert out["continue_with"]["lesson_slug"] == "the-rook"

    def test_focus_theme_ranks_first_and_skips_completed(self):
        prog = self._prog()
        progress = {"l3": {"lesson_id": "l3", "status": "completed"}}
        out = training_recommender(
            "u1", _weaknesses=[{"category": "endgame", "frequency": 1}],
            _focus=[{"theme": "fork", "rationale": "5 blunders"}], _programme=prog, _progress=progress,
        )
        first, second = out["recommendations"][:2]
        # fork lesson is completed but still the only match → recommended with status
        assert first["lesson_slug"] == "knight-fork" and first["status"] == "completed"
        assert first["priority"] == "high" and "5 blunders" in first["description"]
        assert second["lesson_slug"] == "king-and-pawn" and second["weakness_addressed"] == "endgame"
        assert out["signals"] == {"focus_themes": ["fork"], "weaknesses": ["endgame"]}

    def test_no_signals_recommends_next_lesson(self):
        prog = self._prog()
        out = training_recommender("u1", _weaknesses=[], _focus=[], _programme=prog, _progress={})
        assert out["recommendations"][0]["lesson_slug"] == "the-king"
        assert out["recommendations"][0]["weakness_addressed"] == "programme"

    def test_theme_without_lesson_becomes_puzzle_rec(self):
        prog = self._prog()
        out = training_recommender("u1", _weaknesses=[], _focus=[{"theme": "zugzwang"}],
                                   _programme=prog, _progress={})
        rec = out["recommendations"][0]
        assert rec["type"] == "puzzle" and rec["puzzle_themes"] == ["zugzwang"]

    def test_match_lessons_prefers_own_title_and_not_completed(self):
        prog = self._prog()
        progress = {"l4": {"status": "completed"}}
        got = match_lessons(prog, ("король",), progress, limit=3)
        assert [l["id"] for _, _, l in got] == ["l1", "l4"]  # completed one last


@pytest.mark.unit
def test_rich_select_falls_back_to_base_columns():
    """A missing optional column fails the PostgREST query; the tool retries with the base schema."""
    calls = []

    def q(table, params, url=None, key=None):
        calls.append((table, params["select"]))
        if table == "courses" and "title_kk" in params["select"]:
            return None  # e.g. 400: column courses.title_kk does not exist
        if table == "courses":
            return [{"id": "c1", "slug": "chess-basics", "title": "Chess Basics", "level": "beginner", "order_index": 1}]
        if table == "modules":
            return [{"id": "m1", "course_id": "c1", "title": "Pieces", "title_ru": "Фигуры", "order_index": 1}]
        if table == "lessons":
            return [{"id": "l1", "slug": "the-king", "module_id": "m1", "title": "The King", "title_ru": "Король",
                     "lesson_type": "theory", "exercise_type": None, "order_index": 1}]
        if table == "user_progress":
            return []
        raise AssertionError(table)

    with patch("src.tools.learning_path._supabase_query", q):
        out = get_learning_path("u1", locale="ru")
    assert out["courses"][0]["title"] == "Chess Basics"  # base column, no ru available
    assert out["continue_with"]["title"] == "Король"
    assert [s for t, s in calls if t == "courses"] == [lp.COURSE_SELECT, lp.COURSE_SELECT_MIN]
