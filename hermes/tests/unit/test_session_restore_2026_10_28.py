"""A session restored from Supabase after a Hermes restart is whole or not cached at all (28.10).

Before: a failed read of the boards (or messages, or the session row) was swallowed at DEBUG and
a session WITHOUT its boards stayed cached until the next restart — every endpoint then ran in
"no game" mode (engine-note named the best move in a live game, GET /boards persisted a new study
board over the session, a voice transcript append re-created the session at the start position).
"""

import logging
from unittest.mock import patch

import chess
import httpx
import pytest
from fastapi.testclient import TestClient

from src import game_mode, voice_engine_note
from src.middleware.rate_limiter import voice_tool_rate_limiter
from src.session_persistence import SessionLoadError, SessionPersistence
from src.sessions import SessionStore, session_store
from src.tools.game_play import live_game_board

USER = "u-restore-1028"
H = {"X-User-Id": USER}


class _Capture:
    """In-memory rows of a session as Supabase holds them (filled by the write-through calls)."""

    def __init__(self):
        self.sessions, self.boards, self.messages = {}, {}, {}

    def persist_session(self, sid, uid, fen):
        self.sessions[sid] = {"id": sid, "user_id": uid, "title": "", "board_state": fen}

    def persist_message(self, sid, role, content, source, extra=None, evt=None):
        self.messages.setdefault(sid, []).append({"role": role, "content": content, "source": source})

    def update_board_state(self, sid, fen):
        self.sessions[sid]["board_state"] = fen

    def update_session_fields(self, sid, **fields):
        self.sessions[sid].update(fields)

    def persist_board(self, board):
        self.boards[board["id"]] = dict(board)

    def delete_board(self, bid):
        self.boards.pop(bid, None)


class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self._rows


class _FakeSupabase:
    """The PostgREST calls of SessionPersistence: reads served from *capture*, the first
    ``fail[table]`` reads of a table time out, every write is recorded."""

    def __init__(self, capture: _Capture, fail: dict):
        self.capture, self.fail, self.writes = capture, dict(fail), []

    def get(self, url, params=None, **_):
        table = url.rsplit("/", 1)[-1]
        if self.fail.get(table):
            self.fail[table] -= 1
            raise httpx.ReadTimeout("simulated Supabase timeout")
        sid = (params.get("id") or params.get("session_id") or "")[3:]
        if table == "coach_sessions":
            row = self.capture.sessions.get(sid)
            return _Resp([dict(row)] if row else [])
        if table == "coach_boards":
            return _Resp([dict(b) for b in self.capture.boards.values() if b["session_id"] == sid])
        if table == "coach_messages":
            return _Resp(list(self.capture.messages.get(sid, [])))
        return _Resp([])

    def _write(self, method, url, **kw):
        self.writes.append((method, url.rsplit("/", 1)[-1], kw.get("json")))
        return _Resp([])

    def post(self, url, **kw):
        return self._write("post", url, **kw)

    def patch(self, url, **kw):
        return self._write("patch", url, **kw)

    def delete(self, url, **kw):
        return self._write("delete", url, **kw)


@pytest.fixture(autouse=True)
def _no_stockfish(monkeypatch):
    """The engine replies with its first legal move, every position equal (no Stockfish thread)."""
    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))


def _game_in_supabase():
    """A live game (white played e4, the engine replied) as Supabase holds it, and its session id."""
    capture = _Capture()
    s = SessionStore(persistence=capture).create(user_id=USER)
    game_mode.start_game(s, "white", 1500, "mistakes")
    game = next(b for b in s.boards if b.kind == "game")
    game_mode.play_move(s, game, "e4")
    return capture, s.id, game.fen


@pytest.fixture
def restarted(monkeypatch):
    """Hermes after a restart: the global store's cache is empty and its persistence is a real
    SessionPersistence over a fake Supabase whose reads can fail."""

    def make(fail: dict):
        capture, sid, fen = _game_in_supabase()
        sb = _FakeSupabase(capture, fail)
        monkeypatch.setattr("src.session_persistence._sb", lambda: sb)
        monkeypatch.setattr(session_store, "_persistence", SessionPersistence(url="https://sb.example", key="k"))
        session_store._sessions.pop(sid, None)
        voice_tool_rate_limiter.reset()
        return sb, sid, fen

    yield make


@pytest.mark.unit
@pytest.mark.parametrize("table", ["coach_boards", "coach_messages", "coach_sessions"])
def test_a_read_failing_once_is_not_cached_and_the_next_access_sees_the_game(restarted, table, caplog):
    sb, sid, _ = restarted({table: 1})
    with caplog.at_level(logging.WARNING):
        with pytest.raises(SessionLoadError):
            session_store.get(sid, USER)
    assert sid not in session_store._sessions  # nothing half-loaded stays in memory
    assert any(sid in r.getMessage() and r.levelno >= logging.WARNING for r in caplog.records)

    session = session_store.get(sid, USER)  # Supabase answers now: the session is whole
    assert live_game_board(session) is not None
    assert sb.writes == []


@pytest.mark.unit
def test_get_boards_never_persists_a_new_study_board_over_unloaded_boards(restarted):
    sb, sid, _ = restarted({"coach_boards": 1})
    client = TestClient(__import__("src.server", fromlist=["app"]).app)
    r = client.get(f"/api/coach/sessions/{sid}/boards", headers=H)
    assert r.status_code == 503
    assert sb.writes == []  # no new study board, no switch of active_board_id

    r = client.get(f"/api/coach/sessions/{sid}/boards", headers=H)
    assert r.status_code == 200
    assert [b["kind"] for b in r.json()["boards"]] == ["game"]
    assert sb.writes == []


@pytest.mark.unit
def test_engine_note_in_a_live_game_after_a_failed_restore_gives_no_best_move(restarted):
    sb, sid, fen = restarted({"coach_boards": 1})
    client = TestClient(__import__("src.server", fromlist=["app"]).app)
    engine = {"best_move": "", "lines": [{"pv": "g1f3", "score": 0.3, "depth": 16}]}
    with patch.object(voice_engine_note, "analyze_cached", return_value=engine):
        r = client.post("/api/coach/voice/engine-note", headers=H, json={"fen": fen, "session_id": sid})
        assert r.status_code == 503  # not the engine line of a study board
        voice_tool_rate_limiter.reset()
        r = client.post("/api/coach/voice/engine-note", headers=H, json={"fen": fen, "session_id": sid})
    assert r.status_code == 200
    assert r.json().get("kind") == "game" and not r.json().get("best")


@pytest.mark.unit
def test_voice_transcript_append_does_not_recreate_a_session_whose_row_failed_to_load(restarted):
    sb, sid, _ = restarted({"coach_sessions": 1})
    client = TestClient(__import__("src.server", fromlist=["app"]).app)
    r = client.post(f"/api/coach/sessions/{sid}/messages", headers=H, json={"role": "user", "content": "е5"})
    assert r.status_code == 503
    assert sb.writes == []  # no upsert of the session row at the start position
    assert live_game_board(session_store.get(sid, USER)) is not None


@pytest.mark.unit
def test_list_skips_a_session_that_failed_to_load_and_retries_it_later(restarted):
    sb, sid, _ = restarted({"coach_boards": 1})
    session_store._persistence.load_user_sessions = lambda uid: [{"id": sid, "user_id": USER}]
    assert sid not in {s.id for s in session_store.list(USER)}
    assert sid not in session_store._sessions
    assert live_game_board(session_store.get(sid, USER)) is not None


@pytest.mark.unit
def test_voice_check_and_voice_tools_do_not_run_without_the_game_they_could_not_load(restarted):
    sb, sid, fen = restarted({"coach_boards": 2})
    client = TestClient(__import__("src.server", fromlist=["app"]).app)
    # voice/check used to pass «Я пойду конём на f6» (a move the engine never made) with the game lost
    r = client.post("/api/coach/voice/check", headers=H,
                    json={"text": "Я пойду конём на f6.", "fen": fen, "session_id": sid})
    assert r.status_code == 503
    # a voice tool used to run without the session (analyze_position gave the full line in a game)
    voice_tool_rate_limiter.reset()
    r = client.post("/api/coach/tool/analyze_position", headers=H, json={"args": {"fen": fen}, "session_id": sid})
    assert r.status_code == 503
    assert sb.writes == []


def test_a_wrong_device_clock_does_not_move_a_message_in_time():
    """Review 28.10: client_ts from a device whose clock is off by hours is ignored; a close one is kept."""
    import time as _time

    from src.sessions import Session

    s = Session(id="clock-1", user_id="u-clock")
    now = _time.time()
    s.add_message("user", "e4", source="voice", extra={"client_ts": now - 3 * 3600})
    s.add_message("user", "e5", source="voice", extra={"client_ts": now - 5})
    assert abs(s.messages[0].timestamp - now) < 60
    assert abs(s.messages[1].timestamp - (now - 5)) < 1
