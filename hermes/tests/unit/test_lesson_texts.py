"""The programme's own words for the site's lessons (src/lesson_texts.py, 2026-10-04)."""

import chess
import pytest

from src.lesson_texts import _records, diagrams, explanation, lesson_text

KING_LESSON = "9f0f557c-c5c2-4df7-8725-94bd1e61e715"  # «Король» in «Основы шахмат» on the site


@pytest.mark.unit
class TestLessonTexts:
    def test_the_books_are_shipped_with_the_coach(self):
        recs = _records()
        assert len(recs) == 37
        assert {r["course_slug"] for r in recs} == {"chess-basics", "chess-tactics", "advanced-tactics"}
        assert sum(1 for r in recs if len(r.get("text_ru") or "") > 200) >= 36

    def test_by_lesson_id(self):
        own = lesson_text(lesson_id=KING_LESSON)
        assert own["step"] == 1 and own["title"] == "Шахматная Доска"
        assert "Король – главная фигура" in own["text"]

    def test_by_course_and_module_then_by_lesson_title(self):
        pin = lesson_text(course_slug="chess-basics", module_title="Связка")
        assert pin and pin["title"] == "Связка" and "нападение на фигуру противника" in pin["text"]
        assert pin["diagrams"] and chess.Board(pin["diagrams"][0]["fen"]).is_valid()
        assert pin["diagrams"][0]["context"].startswith("Связка - это")
        by_title = lesson_text(course_slug="chess-tactics", lesson_title="Открытое нападение")
        assert by_title and len(by_title["diagrams"]) == 4

    def test_unknown_lessons_give_nothing(self):
        assert lesson_text(lesson_id="no-such-lesson") is None
        assert lesson_text(course_slug="mate-in-3-moves", module_title="Мат в 3 хода") is None
        assert lesson_text() is None

    def test_markers_keep_legal_positions_and_drop_file_names(self):
        rec = {"text_ru": "Смотри.\n[Диаграмма s1_l8_theory_02.png: 6rk/6p1/7p/8/8/8/1B1Q4/7K w - - 0 1]\n\n\n\n"
                          "А это схема.\n[Диаграмма s1_l1_theory_01.png: 8/8/8/8/8/8/8/R7 w - - 0 1] Конец."}
        text = explanation(rec)
        assert "[Диаграмма: 6rk/6p1/7p/8/8/8/1B1Q4/7K w - - 0 1]" in text
        assert "s1_l8_theory_02.png" not in text
        assert "[Диаграмма] Конец." in text  # no kings: a scheme, not a position
        assert "\n\n\n" not in text

    def test_long_texts_are_cut_at_a_sentence(self):
        rec = {"text_ru": "Первое предложение. " * 300}
        text = explanation(rec, limit=500)
        assert len(text) <= 505 and text.endswith(". …")

    def test_diagrams_skip_schemes_and_broken_positions(self):
        rec = {"diagrams": [
            {"fen": "8/8/8/8/8/8/8/R7 w - - 0 1", "valid": False, "context": "как ходит ладья"},
            {"fen": "not a fen", "valid": True, "context": ""},
            {"fen": "8/2k5/8/8/2b5/8/2Q4K/8 w - - 0 1", "valid": True, "context": "связка"},
        ]}
        assert diagrams(rec) == [{"fen": "8/2k5/8/8/2b5/8/2Q4K/8 w - - 0 1", "context": "связка"}]
