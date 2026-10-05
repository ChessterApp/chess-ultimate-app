"""The coach's comment after a move in a live game goes through the answer check (2026-10-05)."""

import json

import chess
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src import config, game_mode
from src.game_mode import play_move, start_game
from src.quick_reply import QuickReply
from src.server import app
from src.sessions import session_store

USER = {"X-User-Id": "comment-user"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    session_store._sessions.clear()
    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: chess.Board(fen).parse_san("e5").uci()
                        if "e5" in [chess.Board(fen).san(m) for m in chess.Board(fen).legal_moves] else next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))
    monkeypatch.setattr(config, "COACH_ANSWER_CHECK", True)


def _fake_completion(text: str):
    def fake(*, model, api_key, messages, on_delta=None, **kw):
        for i in range(0, len(text), 9):
            on_delta(text[i:i + 9])
        return QuickReply(text=text, model=model, prompt_tokens=30, completion_tokens=20)
    return fake


def _game():
    session = session_store.create(user_id="comment-user")
    board, _ = start_game(session, "white", 1500)
    play_move(session, board, "e4")  # 1.e4 e5
    return session, board


def _comment(session, board, text):
    with patch("src.quick_reply.stream_completion", _fake_completion(text)), patch("src.server.log_event"):
        resp = TestClient(app).post(f"/api/coach/sessions/{session.id}/game/{board.id}/comment", headers=USER,
                                    json={"locale": "ru"})
    assert resp.status_code == 200
    frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
    return "".join(f.get("delta", "") for f in frames), frames


@pytest.mark.unit
def test_a_wrong_sentence_of_the_comment_is_not_shown():
    session, board = _game()
    shown, frames = _comment(session, board, "Твой конь на f3 бьёт ферзя на d8. Хороший ход — ты занял центр.")
    assert "конь на f3" not in shown and "Хороший ход — ты занял центр." in shown
    assert frames[-1]["done"] is True
    assert [m for m in session.messages if m.role == "assistant"][-1].content == shown.strip()


@pytest.mark.unit
def test_a_comment_lost_whole_becomes_the_plain_facts():
    session, board = _game()
    shown, _ = _comment(session, board, "Твой конь на f3 бьёт ферзя на d8.")
    assert shown.strip() == "Ход e4 — нормальный ход, продолжаем."


@pytest.mark.unit
def test_a_right_comment_streams_as_before():
    session, board = _game()
    shown, _ = _comment(session, board, "Хороший ход: пешка e4 занимает центр и открывает слона f1.")
    assert shown.strip() == "Хороший ход: пешка e4 занимает центр и открывает слона f1."


@pytest.mark.unit
def test_fallback_comment_words():
    from src.game_mode import fallback_comment
    from src.sessions import Board

    rec = Board(id="b", session_id="s", kind="game", fen=chess.STARTING_FEN, game_state={"status": "playing", "annotations": [
        {"ply": 1, "san": "g4", "verdict": "blunder", "cp_loss": 300, "best": "e4"}]})
    assert fallback_comment(rec, "ru") == "Ход g4 — грубая ошибка, он отдаёт слишком много. Сильнее было e4."
    assert fallback_comment(rec, "en") == "g4 is a blunder — it gives up too much. e4 was stronger."
    assert fallback_comment(rec, "kk").startswith("g4 жүрісі — өрескел қате")
    rec.game_state["status"] = "finished"; rec.game_state["result"] = "0-1"
    assert fallback_comment(rec, "ru") == "Партия окончена: 0-1."
