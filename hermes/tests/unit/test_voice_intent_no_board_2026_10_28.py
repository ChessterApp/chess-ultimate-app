"""28.10: /api/coach/voice/intent on a session without an active board answered 500
(board.kind on None); the hook then fell back to its own rules. It must read the words as usual."""

from fastapi.testclient import TestClient


def test_intent_on_a_session_without_a_board_is_read_not_500():
    from src import server
    from src.sessions import session_store

    session = session_store.create(user_id="intent-no-board")
    assert session.active_board_id is None
    client = TestClient(server.app, raise_server_exceptions=False)
    res = client.post("/api/coach/voice/intent", headers={"X-User-Id": "intent-no-board"},
                      json={"text": "дай мне тактическую задачу", "session_id": session.id})
    assert res.status_code == 200
    assert res.json()["kind"] == "puzzle"


def test_intent_without_a_board_still_uses_the_fen_and_pgn_sent():
    from src import server
    from src.sessions import session_store

    session = session_store.create(user_id="intent-no-board-2")
    client = TestClient(server.app, raise_server_exceptions=False)
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    res = client.post("/api/coach/voice/intent", headers={"X-User-Id": "intent-no-board-2"},
                      json={"text": "е два е четыре", "session_id": session.id, "fen": fen})
    assert res.status_code == 200
