"""Unit tests for POST /api/lesson/chat (lesson tutor SSE streaming)."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.server import app
from src.middleware.rate_limiter import rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


USER_HEADERS = {"X-User-Id": "test-user-123"}


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def _deltas(events: list[dict]) -> str:
    return "".join(e["delta"] for e in events if "delta" in e)


@pytest.mark.unit
class TestLessonChat:
    def setup_method(self):
        self.client = TestClient(app)

    def test_requires_user_id(self):
        resp = self.client.post("/api/lesson/chat", json={"message": "hi"})
        assert resp.status_code == 401

    @patch("src.server._lesson_chat_stream")
    def test_streams_event_stream_content_type(self, mock_stream):
        mock_stream.return_value = iter(["A pin ", "is a tactic."])
        resp = self.client.post(
            "/api/lesson/chat",
            headers=USER_HEADERS,
            json={
                "message": "What is a pin?",
                "lesson_title": "Pins",
                "lesson_content": "A pin restricts a piece's movement.",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    @patch("src.server._lesson_chat_stream")
    def test_deltas_reconstruct_message_and_done(self, mock_stream):
        chunks = ["A pin ", "is a ", "tactic."]
        mock_stream.return_value = iter(chunks)
        resp = self.client.post(
            "/api/lesson/chat",
            headers=USER_HEADERS,
            json={"message": "What is a pin?", "lesson_title": "Pins"},
        )
        events = _parse_sse(resp.text)
        # The text arrives whole; since 2026-10-05 a sentence is held until it is
        # complete and checked on the board, so the chunking may differ.
        assert _deltas(events) == "".join(chunks)
        # Final frame is the done sentinel.
        assert events[-1] == {"done": True}
        # No error frame leaked.
        assert all("error" not in e for e in events)

    @patch("src.server._lesson_chat_stream")
    def test_history_forwarded_to_llm(self, mock_stream):
        mock_stream.return_value = iter(["ok"])
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        self.client.post(
            "/api/lesson/chat",
            headers=USER_HEADERS,
            json={
                "message": "more?",
                "lesson_title": "Pins",
                "lesson_content": "content",
                "history": history,
            },
        )
        # (model, system_prompt, message, history)
        args = mock_stream.call_args.args
        assert args[2] == "more?"
        assert args[3] == history
        assert "Pins" in args[1]  # lesson title injected into system prompt

    @patch("src.server._lesson_chat_stream")
    def test_puzzle_context_injected_into_system_prompt(self, mock_stream):
        mock_stream.return_value = iter(["ok"])
        self.client.post(
            "/api/lesson/chat",
            headers=USER_HEADERS,
            json={
                "message": "What should I play here?",
                "lesson_title": "Back rank",
                "lesson_content": "content",
                "puzzle_context": {
                    "mode": "multi",
                    "current_index": 1,
                    "total_count": 2,
                    "current_puzzle": {
                        "order_index": 1,
                        "fen": "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
                        "solution_line": ["e1e8"],
                        "hint_text": "Back rank!",
                    },
                    "current_board_fen": "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
                    "puzzles": [
                        {"order_index": 1, "fen": "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"},
                        {"order_index": 2, "fen": "8/8/8/8/8/8/8/K6k w - - 0 1"},
                    ],
                },
            },
        )
        system_prompt = mock_stream.call_args.args[1]
        assert "PUZZLE SET FOR THIS LESSON" in system_prompt
        assert "STUDENT'S CURRENT PUZZLE" in system_prompt
        assert "Back rank!" in system_prompt

    @patch("src.server._lesson_chat_stream")
    def test_missing_puzzle_context_omits_section(self, mock_stream):
        mock_stream.return_value = iter(["ok"])
        self.client.post(
            "/api/lesson/chat",
            headers=USER_HEADERS,
            json={"message": "hi", "lesson_title": "Pins", "lesson_content": "c"},
        )
        system_prompt = mock_stream.call_args.args[1]
        assert "PUZZLE CONTEXT" not in system_prompt

    @patch("src.server._lesson_chat_stream")
    def test_llm_error_emits_error_frame_not_delta(self, mock_stream):
        # LLM raises (e.g. retired-model 404) — must surface as an error frame,
        # never as a normal delta containing the raw error text.
        def _boom(*args, **kwargs):
            raise RuntimeError("404 model not found")
            yield  # pragma: no cover — makes this a generator function

        mock_stream.side_effect = _boom
        resp = self.client.post(
            "/api/lesson/chat",
            headers=USER_HEADERS,
            json={"message": "What is a pin?", "lesson_title": "Pins"},
        )
        events = _parse_sse(resp.text)
        # No delta frame carries the error text.
        assert _deltas(events) == ""
        assert all("404" not in json.dumps(e) for e in events if "delta" in e)
        # Exactly one error frame, no done frame.
        error_frames = [e for e in events if "error" in e]
        assert len(error_frames) == 1
        assert not any("done" in e for e in events)


@pytest.mark.unit
class TestLessonTutorGrounding:
    """The lesson-page tutor had run past every check (2026-10-05): now it gets the
    programme's own text for the lesson, its sentences are checked on the lesson's
    positions, and its language is the student's."""

    KING_LESSON = "9f0f557c-c5c2-4df7-8725-94bd1e61e715"  # «Король» in «Основы шахмат» on the site
    PIN_FEN = "8/2k5/8/8/2b5/8/2Q4K/8 w - - 0 1"  # the lesson's pin diagram: Qc2 pins Bc4 to Kc7

    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server._lesson_chat_stream")
    def test_the_books_text_joins_the_prompt_by_lesson_id(self, mock_stream):
        mock_stream.return_value = iter(["Король ходит на одно поле."])
        self.client.post("/api/lesson/chat", headers=USER_HEADERS, json={
            "message": "как ходит король?", "lesson_title": "Король", "lesson_content": "# Король\n\n## Видео урок\nhttps://youtu.be/x",
            "lesson_id": self.KING_LESSON, "course_slug": "chess-basics", "locale": "ru",
        })
        system_prompt = mock_stream.call_args.args[1]
        assert "The lesson's own text (the programme «Ступени», step 1, lesson 1 «Шахматная Доска»)" in system_prompt
        assert "Король – главная фигура" in system_prompt
        assert "checked on the board before the student sees it" in system_prompt
        assert "locale: ru — Russian" in system_prompt

    @patch("src.server._lesson_chat_stream")
    def test_the_books_text_by_course_and_title_when_the_id_is_unknown(self, mock_stream):
        mock_stream.return_value = iter(["ok"])
        self.client.post("/api/lesson/chat", headers=USER_HEADERS, json={
            "message": "что такое связка?", "lesson_title": "Связка", "lesson_content": "", "course_slug": "chess-basics",
            "lesson_id": "no-such-id", "locale": "ru",
        })
        system_prompt = mock_stream.call_args.args[1]
        assert "нападение на фигуру противника" in system_prompt
        assert f"- {self.PIN_FEN}" in system_prompt  # the lesson's diagram

    @patch("src.server._lesson_chat_stream")
    def test_a_wrong_sentence_about_the_students_board_is_not_shown(self, mock_stream, monkeypatch):
        from src import config

        monkeypatch.setattr(config, "COACH_ANSWER_CHECK", True)
        mock_stream.return_value = iter(["Смотри: ферзь на c2 связывает слона c4. ", "А слон c4 бьёт ферзя c2 с шахом. ",
                                         "Король на c7 не может уйти с диагонали."])
        with patch("src.server.log_event"):
            resp = self.client.post("/api/lesson/chat", headers=USER_HEADERS, json={
                "message": "почему слон не может ходить?", "lesson_title": "Связка", "locale": "ru",
                "puzzle_context": {"mode": "single", "current_board_fen": self.PIN_FEN},
            })
        text = _deltas(_parse_sse(resp.text))
        assert "ферзь на c2 связывает слона c4" in text
        assert "с шахом" not in text  # a bishop on c4 does not give check to h2 — not shown
        assert "Король на c7" in text

    @patch("src.server._lesson_chat_stream")
    def test_a_reply_in_the_wrong_language_becomes_the_fallback_line(self, mock_stream, monkeypatch):
        from src import config

        monkeypatch.setattr(config, "COACH_ANSWER_CHECK", True)
        mock_stream.return_value = iter(["The bishop on c4 is pinned by the queen on c2 and cannot move away from the diagonal."])
        with patch("src.server.log_event"):
            resp = self.client.post("/api/lesson/chat", headers=USER_HEADERS, json={
                "message": "почему слон не может ходить?", "lesson_title": "Связка", "locale": "ru",
                "puzzle_context": {"mode": "single", "current_board_fen": self.PIN_FEN},
            })
        events = _parse_sse(resp.text)
        assert _deltas(events) == "Давай сверимся с доской: скажи, какой ход или позицию ты имеешь в виду, и я разберу именно её."
        assert events[-1] == {"done": True}
