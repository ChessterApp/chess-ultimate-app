"""Tests for src/transcript_sweep.py and the session-delete file cleanup."""

import json
import os
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from src import transcript_sweep as ts
from src.transcript_sweep import (
    delete_session_files,
    is_uuid,
    parse_session_id,
    session_files,
    sweep,
)

URL = "https://example.supabase.co"
KEY = "service-key"
OLD = time.time() - 3 * 3600
HEADERS = {"X-User-Id": "sweep-user"}


def _write(dir_, name, mtime=OLD, body="{}"):
    p = dir_ / name
    p.write_text(body)
    os.utime(p, (mtime, mtime))
    return p


def _session(dir_, sid, mtime=OLD, dumps=1):
    paths = [_write(dir_, f"session_{sid}.json", mtime)]
    for i in range(dumps):
        paths.append(_write(dir_, f"request_dump_{sid}_20261013_120000_00000{i}.json", mtime))
    return paths


class _FakeSupabase:
    """Stands in for httpx: answers coach_sessions id=in.(...) lookups."""

    def __init__(self, existing, fail=False):
        self.existing = {s.lower() for s in existing}
        self.fail = fail
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        resp = MagicMock()
        if self.fail:
            resp.raise_for_status.side_effect = RuntimeError("boom")
            return resp
        ids = params["id"][len("in.("):-1].split(",")
        resp.json.return_value = [{"id": i} for i in ids if i in self.existing]
        return resp


@pytest.fixture
def fake_sb():
    def _install(existing=(), fail=False):
        fake = _FakeSupabase(existing, fail)
        patcher = patch.object(ts, "_sb", return_value=fake)
        patcher.start()
        _install.patchers.append(patcher)
        return fake
    _install.patchers = []
    yield _install
    for p in _install.patchers:
        p.stop()


def _run(dir_, **kw):
    kw.setdefault("url", URL)
    kw.setdefault("key", KEY)
    return sweep(dir_, **kw)


@pytest.mark.unit
class TestParsing:
    def test_session_file(self):
        sid = str(uuid.uuid4())
        assert parse_session_id(f"session_{sid}.json") == sid

    def test_request_dump(self):
        sid = str(uuid.uuid4())
        assert parse_session_id(f"request_dump_{sid}_20261013_123456_789012.json") == sid

    def test_non_uuid_ids_parse(self):
        assert parse_session_id("session_test-e2e-7.json") == "test-e2e-7"
        assert parse_session_id("request_dump_e2e-coaching-x_20261013_123456_1.json") == "e2e-coaching-x"

    def test_unrelated_files(self):
        assert parse_session_id("notes.txt") is None
        assert parse_session_id("session_.json") is None
        assert parse_session_id("request_dump_abc.json") is None

    def test_uuid_guard(self):
        assert is_uuid(str(uuid.uuid4()))
        assert not is_uuid("test-lichess-pgn")
        assert not is_uuid("../" + str(uuid.uuid4()))
        assert not is_uuid("")


@pytest.mark.unit
class TestSingleSessionDelete:
    def test_deletes_only_that_session(self, tmp_path):
        sid, other = str(uuid.uuid4()), str(uuid.uuid4())
        _session(tmp_path, sid, dumps=2)
        keep = _session(tmp_path, other)
        assert delete_session_files(sid, tmp_path) == 3
        assert sorted(tmp_path.iterdir()) == sorted(keep)

    def test_traversal_rejected(self, tmp_path):
        victim = tmp_path / "session_x.json"
        victim.write_text("{}")
        sub = tmp_path / "sessions"
        sub.mkdir()
        assert delete_session_files("../x", sub) == 0
        assert delete_session_files("*", sub) == 0
        assert victim.exists()
        with pytest.raises(ValueError):
            session_files("../x", sub)

    def test_missing_dir_is_fine(self, tmp_path):
        assert delete_session_files(str(uuid.uuid4()), tmp_path / "nope") == 0


@pytest.mark.unit
class TestSweep:
    def test_orphans_detected_and_deleted(self, tmp_path, fake_sb):
        live, gone = str(uuid.uuid4()), str(uuid.uuid4())
        live_files = _session(tmp_path, live)
        _session(tmp_path, gone, dumps=2)
        fake_sb(existing=[live])
        out = _run(tmp_path, dry_run=False)
        assert out["error"] is None
        assert out["orphan_ids"] == [gone]
        assert out["deleted_files"] == 3
        assert out["bytes"] == 6
        assert sorted(tmp_path.iterdir()) == sorted(live_files)

    def test_dry_run_deletes_nothing(self, tmp_path, fake_sb):
        live, gone = str(uuid.uuid4()), str(uuid.uuid4())
        _session(tmp_path, live)
        _session(tmp_path, gone)
        fake_sb(existing=[live])
        before = sorted(tmp_path.iterdir())
        out = _run(tmp_path)
        assert out["dry_run"] is True
        assert out["orphans"] == 1 and out["deleted_files"] == 2
        assert sorted(tmp_path.iterdir()) == before

    def test_non_uuid_never_touched(self, tmp_path, fake_sb):
        live = str(uuid.uuid4())
        _session(tmp_path, live)
        test_files = _session(tmp_path, "test-e2e-7") + _session(tmp_path, "test-lichess-pgn")
        _write(tmp_path, "README.txt")
        fake = fake_sb(existing=[live])
        out = _run(tmp_path, dry_run=False)
        assert sorted(out["skipped_non_uuid"]) == ["test-e2e-7", "test-lichess-pgn"]
        assert out["skipped_unparsed"] == 1
        assert all(p.exists() for p in test_files)
        assert "test-e2e-7" not in fake.calls[0]["id"]

    def test_batching(self, tmp_path, fake_sb):
        ids = [str(uuid.uuid4()) for _ in range(250)]
        for sid in ids:
            _write(tmp_path, f"session_{sid}.json")
        fake = fake_sb(existing=ids)
        out = _run(tmp_path, dry_run=False)
        assert out["error"] is None and out["orphans"] == 0
        assert [len(c["id"][4:-1].split(",")) for c in fake.calls] == [100, 100, 50]
        assert all(c["select"] == "id" for c in fake.calls)

    def test_supabase_failure_deletes_nothing(self, tmp_path, fake_sb):
        _session(tmp_path, str(uuid.uuid4()))
        before = sorted(tmp_path.iterdir())
        fake_sb(fail=True)
        out = _run(tmp_path, dry_run=False, force=True)
        assert out["error"] and out["deleted_files"] == 0
        assert sorted(tmp_path.iterdir()) == before

    def test_failure_in_later_batch_deletes_nothing(self, tmp_path, fake_sb):
        for _ in range(150):
            _write(tmp_path, f"session_{uuid.uuid4()}.json")
        fake = fake_sb(existing=[])
        real_get = fake.get

        def flaky(*a, **kw):
            if len(fake.calls) == 1:
                fake.fail = True
            return real_get(*a, **kw)

        fake.get = flaky
        out = _run(tmp_path, dry_run=False, force=True)
        assert out["error"] and out["deleted_files"] == 0
        assert len(list(tmp_path.iterdir())) == 150

    def test_missing_config_deletes_nothing(self, tmp_path, fake_sb):
        _session(tmp_path, str(uuid.uuid4()))
        fake = fake_sb()
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""}):
            out = sweep(tmp_path, dry_run=False, force=True)
        assert "not configured" in out["error"]
        assert len(list(tmp_path.iterdir())) == 2
        assert fake.calls == []

    def test_max_fraction_aborts(self, tmp_path, fake_sb):
        live = str(uuid.uuid4())
        _session(tmp_path, live)
        for _ in range(2):
            _session(tmp_path, str(uuid.uuid4()))
        fake_sb(existing=[live])
        out = _run(tmp_path, dry_run=False)
        assert "exceeds max" in out["error"]
        assert out["deleted_files"] == 0
        assert len(list(tmp_path.iterdir())) == 6

    def test_max_fraction_overridable_and_force(self, tmp_path, fake_sb):
        live = str(uuid.uuid4())
        _session(tmp_path, live)
        for _ in range(2):
            _session(tmp_path, str(uuid.uuid4()))
        fake_sb(existing=[live])
        assert _run(tmp_path, max_fraction=0.7)["error"] is None
        out = _run(tmp_path, dry_run=False, force=True)
        assert out["error"] is None and out["deleted_files"] == 4

    def test_grace_period_skips_recent_sessions(self, tmp_path, fake_sb):
        old, fresh = str(uuid.uuid4()), str(uuid.uuid4())
        _session(tmp_path, old)
        # Old transcript but a dump written just now: the whole session is skipped.
        _write(tmp_path, f"session_{fresh}.json")
        fresh_dump = _write(tmp_path, f"request_dump_{fresh}_20261014_100000_1.json", mtime=time.time())
        fake_sb(existing=[])
        out = _run(tmp_path, dry_run=False, force=True, grace_minutes=60)
        assert out["skipped_recent"] == 1
        assert out["orphan_ids"] == [old]
        assert fresh_dump.exists() and (tmp_path / f"session_{fresh}.json").exists()

    def test_grace_zero_includes_recent(self, tmp_path, fake_sb):
        _session(tmp_path, str(uuid.uuid4()), mtime=time.time() - 5)
        fake_sb(existing=[])
        out = _run(tmp_path, force=True, grace_minutes=0)
        assert out["orphans"] == 1 and out["skipped_recent"] == 0

    def test_empty_dir_makes_no_requests(self, tmp_path, fake_sb):
        fake = fake_sb()
        out = _run(tmp_path, dry_run=False)
        assert out["error"] is None and out["scanned"] == 0
        assert fake.calls == []

    def test_missing_dir_is_error(self, tmp_path, fake_sb):
        out = _run(tmp_path / "nope", dry_run=False)
        assert "not found" in out["error"]


@pytest.mark.unit
class TestCli:
    def _main(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "scripts" / "sweep_transcripts.py"
        spec = importlib.util.spec_from_file_location("sweep_transcripts", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.main

    def test_dry_run_prints_summary(self, tmp_path, fake_sb, capsys):
        gone = str(uuid.uuid4())
        _session(tmp_path, gone)
        fake_sb(existing=[])
        with patch.dict(os.environ, {"SUPABASE_URL": URL, "SUPABASE_SERVICE_KEY": KEY}):
            rc = self._main()(["--dir", str(tmp_path), "--force"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["dry_run"] is True and out["orphan_ids"] == [gone]
        assert len(list(tmp_path.iterdir())) == 2

    def test_apply_and_error_exit(self, tmp_path, fake_sb, capsys):
        _session(tmp_path, str(uuid.uuid4()))
        fake_sb(existing=[])
        with patch.dict(os.environ, {"SUPABASE_URL": URL, "SUPABASE_SERVICE_KEY": KEY}):
            main = self._main()
            assert main(["--dir", str(tmp_path), "--apply"]) == 1  # 100% orphans
            assert len(list(tmp_path.iterdir())) == 2
            assert main(["--dir", str(tmp_path), "--apply", "--max-fraction", "1"]) == 0
        assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
class TestDeleteEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        from src.server import app
        from src.sessions import session_store
        session_store._sessions.clear()
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            (tmp_path / "sessions").mkdir()
            yield TestClient(app), session_store, tmp_path / "sessions"
        session_store._sessions.clear()

    def test_delete_removes_transcript_files(self, client):
        c, store, sdir = client
        session = store.create("sweep-user")
        mine = _session(sdir, session.id, dumps=2)
        other = _session(sdir, str(uuid.uuid4()))
        resp = c.delete(f"/api/coach/sessions/{session.id}", headers=HEADERS)
        assert resp.status_code == 200
        assert not any(p.exists() for p in mine)
        assert all(p.exists() for p in other)

    def test_not_found_keeps_files(self, client):
        c, store, sdir = client
        sid = str(uuid.uuid4())
        files = _session(sdir, sid)
        with patch.object(store, "get", return_value=None):
            resp = c.delete(f"/api/coach/sessions/{sid}", headers=HEADERS)
        assert resp.status_code == 404
        assert all(p.exists() for p in files)

    def test_other_users_session_keeps_files(self, client):
        c, store, sdir = client
        session = store.create("someone-else")
        files = _session(sdir, session.id)
        resp = c.delete(f"/api/coach/sessions/{session.id}", headers=HEADERS)
        assert resp.status_code == 404
        assert all(p.exists() for p in files)

    def test_non_uuid_session_keeps_files(self, client):
        c, store, sdir = client
        store.create("sweep-user", session_id="test-e2e-7")
        files = _session(sdir, "test-e2e-7")
        resp = c.delete("/api/coach/sessions/test-e2e-7", headers=HEADERS)
        assert resp.status_code == 200
        assert all(p.exists() for p in files)
