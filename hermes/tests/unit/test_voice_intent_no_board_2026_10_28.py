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


def test_intent_without_a_board_still_uses_the_fen_and_pgn_sent(monkeypatch):
    from src import intent, server
    from src.sessions import session_store

    seen = {}
    real = intent.read_intent

    def spy(text, **kw):
        seen.update(kw)
        return real(text, **kw)

    monkeypatch.setattr(intent, "read_intent", spy)
    session = session_store.create(user_id="intent-no-board-2")
    client = TestClient(server.app, raise_server_exceptions=False)
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    pgn = "1. e4 e5 2. Nf3"
    res = client.post("/api/coach/voice/intent", headers={"X-User-Id": "intent-no-board-2"},
                      json={"text": "разбери эту партию", "session_id": session.id, "fen": fen, "pgn": pgn})
    assert res.status_code == 200
    # the words were read against the board the browser sent, not against nothing
    assert seen["fen"] == fen and seen["pgn"] == pgn
    assert seen["live_game"] is False and seen["puzzle_on_board"] is False
