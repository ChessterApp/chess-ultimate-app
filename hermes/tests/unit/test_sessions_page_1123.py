"""The session list in pages (tester 17.11: the test account's 1001 sessions took 7–11 s after a restart and twice
ran past the site proxy's 10 s). A page loads only its own sessions; every message bumps its session's activity."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src import session_persistence as sp
from src.sessions import SessionStore

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


class _Stored:
    enabled = True

    def __init__(self, n, user="u1"):
        self.rows = {f"s{i:04d}": {"id": f"s{i:04d}", "user_id": user, "title": f"Сессия {i}",
                                   "created_at": (T0 + timedelta(minutes=i)).isoformat(),
                                   "updated_at": (T0 + timedelta(minutes=i)).isoformat()} for i in range(n)}
        self.loaded = []

    def persist_session(self, *a):
        pass

    def load_session(self, sid):
        self.loaded.append(sid)
        return self.rows.get(sid)

    def load_user_sessions(self, uid):
        return [r for r in self.rows.values() if r["user_id"] == uid]

    def load_user_session_page(self, uid, limit, offset):
        rows = sorted(self.load_user_sessions(uid), key=lambda r: (r["updated_at"], r["id"]), reverse=True)
        return [{"id": r["id"], "updated_at": r["updated_at"]} for r in rows[offset:offset + limit]]

    def load_messages(self, sid):
        return []

    def load_boards(self, sid):
        return []


@pytest.mark.unit
def test_a_page_loads_only_its_own_sessions_newest_first():
    stored = _Stored(1001)
    store = SessionStore(persistence=stored)
    page = store.list("u1", 30, 0)
    assert [s.id for s in page] == [f"s{i:04d}" for i in range(1000, 970, -1)]
    assert len(stored.loaded) == 30
    second = store.list("u1", 30, 30)
    assert [s.id for s in second][0] == "s0970" and len(stored.loaded) == 60
    assert store.list("u1", 30, 990)[-1].id == "s0000"
    assert store.list("u1", 30, 1001) == []


@pytest.mark.unit
def test_a_session_not_stored_yet_is_on_the_first_page():
    stored = _Stored(40)
    store = SessionStore(persistence=stored)
    fresh = store.create("u1")  # its row is still being written
    assert fresh.id in {s.id for s in store.list("u1", 30, 0)}
    assert fresh.id not in {s.id for s in store.list("u1", 30, 30)}


@pytest.mark.unit
def test_without_storage_the_pages_are_the_memory_s():
    class Off(_Stored):
        enabled = False

    store = SessionStore(persistence=Off(0))
    made = [store.create("u1") for _ in range(5)]
    for i, s in enumerate(made):
        s.created_at = 1000 + i
    assert [s.id for s in store.list("u1", 2, 0)] == [made[4].id, made[3].id]
    assert [s.id for s in store.list("u1", 2, 4)] == [made[0].id]


@pytest.mark.unit
def test_a_written_message_bumps_its_session(monkeypatch):
    calls = []

    class Resp:
        def raise_for_status(self):
            return None

    class Client:
        def post(self, url, **k):
            calls.append(("post", url.rsplit("/", 1)[-1], k.get("json")))
            return Resp()

        def patch(self, url, **k):
            calls.append(("patch", url.rsplit("/", 1)[-1], k.get("params"), k.get("json")))
            return Resp()

    monkeypatch.setattr(sp, "_sb", lambda: Client())
    p = sp.SessionPersistence.__new__(sp.SessionPersistence)
    p.url, p.key = "https://x.supabase.co", "k"
    monkeypatch.setattr(p, "_await_session_ready", lambda sid: None, raising=False)
    p._persist_message("s1", "user", "привет", "text")
    assert calls[0][:2] == ("post", "coach_messages")
    assert calls[1][:3] == ("patch", "coach_sessions", {"id": "eq.s1"}) and "updated_at" in calls[1][3]


@pytest.mark.unit
def test_the_route_pages_and_bounds_its_query(monkeypatch):
    from src import server

    seen = []
    monkeypatch.setattr(server.session_store, "list", lambda uid, limit=None, offset=0: seen.append((limit, offset)) or [])
    client = TestClient(server.app)
    h = {"X-User-Id": "u1"}
    client.get("/api/coach/sessions", headers=h)
    client.get("/api/coach/sessions?limit=50&offset=30", headers=h)
    client.get("/api/coach/sessions?limit=5000&offset=-3", headers=h)
    client.get("/api/coach/sessions?limit=abc", headers=h)
    assert seen == [(30, 0), (50, 30), (100, 0), (30, 0)]
