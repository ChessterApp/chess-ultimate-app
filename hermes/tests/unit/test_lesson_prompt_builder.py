"""Unit tests for the lesson-tutor system prompt builder and its puzzle-context
injection (server._build_lesson_system_prompt)."""

import pytest

from src.server import (
    PuzzleContext,
    PuzzleContextPuzzle,
    _build_lesson_system_prompt,
    _uci_line_to_readable,
)


@pytest.mark.unit
class TestLessonSystemPrompt:
    def test_no_puzzle_context_backward_compatible(self):
        prompt = _build_lesson_system_prompt(
            "Pins", "A pin restricts a piece.", "en", None
        )
        assert "Pins" in prompt
        assert "A pin restricts a piece." in prompt
        assert "locale: en" in prompt
        # No puzzle section when context is absent.
        assert "PUZZLE CONTEXT" not in prompt
        assert "PUZZLE SET" not in prompt

    def test_none_mode_empty_context_adds_nothing(self):
        pc = PuzzleContext(mode="none")
        prompt = _build_lesson_system_prompt("Forks", "content", "ru", pc)
        assert "Forks" in prompt
        assert "PUZZLE CONTEXT" not in prompt

    def test_multi_puzzle_context_renders_set_and_current(self):
        pc = PuzzleContext(
            mode="multi",
            current_index=2,
            total_count=3,
            current_puzzle=PuzzleContextPuzzle(
                order_index=2,
                fen="6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
                solution_line=["e1e8"],
                hint_text="Back rank!",
                attempts=1,
                completed=False,
            ),
            current_board_fen="6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
            puzzles=[
                PuzzleContextPuzzle(order_index=1, fen="8/8/8/8/8/8/8/K6k w - - 0 1", completed=True),
                PuzzleContextPuzzle(
                    order_index=2,
                    fen="6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
                    solution_line=["e1e8"],
                    hint_text="Back rank!",
                    completed=False,
                ),
                PuzzleContextPuzzle(order_index=3, fen="8/8/8/8/8/8/8/K6k w - - 0 1", completed=False),
            ],
        )
        prompt = _build_lesson_system_prompt("Back rank mate", "content", "ru", pc)
        assert "PUZZLE SET FOR THIS LESSON (3 total)" in prompt
        assert "STUDENT'S CURRENT PUZZLE" in prompt
        assert "Puzzle 2 of 3" in prompt
        assert "Back rank!" in prompt
        assert "Attempts this session: 1" in prompt
        assert "Student's current board position:" in prompt
        # The lesson body is still present.
        assert "Back rank mate" in prompt
        # UCI e1e8 should convert to SAN Re8.
        assert "Re8" in prompt

    def test_single_puzzle_context_renders_current_only(self):
        pc = PuzzleContext(
            mode="single",
            current_puzzle=PuzzleContextPuzzle(
                fen="6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
                solution_move="e1e8",
                hint_text="Look at the back rank.",
            ),
        )
        prompt = _build_lesson_system_prompt("Rook endings", "content", "en", pc)
        assert "STUDENT'S CURRENT PUZZLE" in prompt
        assert "Look at the back rank." in prompt
        # No puzzle-set listing for a single-puzzle lesson.
        assert "PUZZLE SET FOR THIS LESSON" not in prompt

    def test_puzzle_list_capped_at_50(self):
        puzzles = [
            PuzzleContextPuzzle(order_index=i, fen="8/8/8/8/8/8/8/K6k w - - 0 1")
            for i in range(1, 61)
        ]
        pc = PuzzleContext(mode="multi", total_count=60, puzzles=puzzles)
        prompt = _build_lesson_system_prompt("Big lesson", "content", "en", pc)
        assert "PUZZLE SET FOR THIS LESSON (60 total)" in prompt
        # 60 - 50 = 10 puzzles omitted.
        assert "and 10 more" in prompt

    def test_long_hint_is_truncated(self):
        long_hint = "x" * 500
        pc = PuzzleContext(
            mode="single",
            current_puzzle=PuzzleContextPuzzle(fen=None, hint_text=long_hint),
        )
        prompt = _build_lesson_system_prompt("t", "c", "en", pc)
        assert long_hint not in prompt
        assert "…" in prompt


@pytest.mark.unit
class TestUciLineToReadable:
    def test_empty_line_returns_empty(self):
        assert _uci_line_to_readable("8/8/8/8/8/8/8/K6k w - - 0 1", []) == ""

    def test_no_fen_falls_back_to_uci(self):
        assert _uci_line_to_readable(None, ["e2e4", "e7e5"]) == "e2e4 e7e5"

    def test_valid_line_converts_to_san(self):
        san = _uci_line_to_readable(
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            ["e2e4", "e7e5"],
        )
        assert san == "e4 e5"

    def test_illegal_move_falls_back_to_uci(self):
        # e2e5 is illegal from the start position → whole line falls back to UCI.
        assert (
            _uci_line_to_readable(
                "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                ["e2e5"],
            )
            == "e2e5"
        )

    def test_bad_fen_falls_back_to_uci(self):
        assert _uci_line_to_readable("not-a-fen", ["e2e4"]) == "e2e4"
