"""Tests for the 30-day hard-delete cleanup command.

Unlike the API tests (which use a filter-agnostic mock), cleanup correctness
hinges on the filters actually selecting the right rows, so this uses a small
STATEFUL fake Supabase that honours eq / is_ / not_.is_ / lt and really mutates
its in-memory store on delete. We seed one long-expired deleted db and one
recently-deleted db, run cleanup, and assert only the expired db (and its games)
is gone.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from commands.cleanup_deleted_databases import (
    cleanup_deleted_databases,
    DATABASES_TABLE,
    GAMES_TABLE,
    RETENTION_DAYS,
)


# ─── Stateful fake Supabase ────────────────────────────────────────────────────

class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._mode = 'select'
        self._filters = []
        self._negate_next_is = False

    # builders
    def select(self, *a, **k):
        self._mode = 'select'
        return self

    def delete(self, *a, **k):
        self._mode = 'delete'
        return self

    @property
    def not_(self):
        self._negate_next_is = True
        return self

    def is_(self, col, val):
        want_null = str(val).lower() == 'null'
        negate = self._negate_next_is
        self._negate_next_is = False

        def pred(row):
            is_null = row.get(col) is None
            matches_null = is_null if want_null else (not is_null)
            return (not matches_null) if negate else matches_null

        self._filters.append(pred)
        return self

    def eq(self, col, val):
        self._filters.append(lambda row: row.get(col) == val)
        return self

    def lt(self, col, val):
        self._filters.append(lambda row: row.get(col) is not None and row.get(col) < val)
        return self

    def order(self, *a, **k):
        return self

    def _match(self, row):
        return all(pred(row) for pred in self._filters)

    def execute(self):
        rows = self._store.get(self._table, [])
        matched = [r for r in rows if self._match(r)]
        if self._mode == 'delete':
            self._store[self._table] = [r for r in rows if not self._match(r)]
        return FakeResult([dict(r) for r in matched])


class FakeSupabase:
    def __init__(self, store):
        self._store = store

    def table(self, name):
        return FakeQuery(self._store, name)


# ─── Fixtures ──────────────────────────────────────────────────────────────────

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _ts(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def store():
    return {
        DATABASES_TABLE: [
            {'id': 'old-db', 'user_id': 'u1', 'deleted_at': _ts(RETENTION_DAYS + 10)},
            {'id': 'recent-db', 'user_id': 'u1', 'deleted_at': _ts(5)},
            {'id': 'live-db', 'user_id': 'u1', 'deleted_at': None},
        ],
        GAMES_TABLE: [
            {'id': 'g1', 'database_id': 'old-db'},
            {'id': 'g2', 'database_id': 'old-db'},
            {'id': 'g3', 'database_id': 'recent-db'},
            {'id': 'g4', 'database_id': 'live-db'},
        ],
    }


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestCleanupDeletedDatabases:
    def test_removes_only_expired_db_and_its_games(self, store):
        with patch('commands.cleanup_deleted_databases.supabase', FakeSupabase(store)):
            summary = cleanup_deleted_databases(now=NOW)

        assert summary == {'databases': 1, 'games': 2}

        remaining_dbs = {r['id'] for r in store[DATABASES_TABLE]}
        assert remaining_dbs == {'recent-db', 'live-db'}  # old-db gone

        remaining_games = {r['id'] for r in store[GAMES_TABLE]}
        assert remaining_games == {'g3', 'g4'}  # g1/g2 (old-db) gone

    def test_idempotent_second_run_is_noop(self, store):
        with patch('commands.cleanup_deleted_databases.supabase', FakeSupabase(store)):
            cleanup_deleted_databases(now=NOW)
            second = cleanup_deleted_databases(now=NOW)

        assert second == {'databases': 0, 'games': 0}
        assert {r['id'] for r in store[DATABASES_TABLE]} == {'recent-db', 'live-db'}
        assert {r['id'] for r in store[GAMES_TABLE]} == {'g3', 'g4'}

    def test_keeps_recent_deletion_until_window_lapses(self, store):
        # At a point where recent-db is only 5 days old, nothing but old-db goes.
        with patch('commands.cleanup_deleted_databases.supabase', FakeSupabase(store)):
            cleanup_deleted_databases(now=NOW)
        assert 'recent-db' in {r['id'] for r in store[DATABASES_TABLE]}

        # Advance past recent-db's window → it is now collected too.
        later = NOW + timedelta(days=RETENTION_DAYS)
        with patch('commands.cleanup_deleted_databases.supabase', FakeSupabase(store)):
            summary = cleanup_deleted_databases(now=later)
        assert summary['databases'] == 1
        assert 'recent-db' not in {r['id'] for r in store[DATABASES_TABLE]}
        assert 'g3' not in {r['id'] for r in store[GAMES_TABLE]}

    def test_no_deleted_rows_is_noop(self):
        empty = {DATABASES_TABLE: [{'id': 'live', 'deleted_at': None}], GAMES_TABLE: []}
        with patch('commands.cleanup_deleted_databases.supabase', FakeSupabase(empty)):
            summary = cleanup_deleted_databases(now=NOW)
        assert summary == {'databases': 0, 'games': 0}
        assert len(empty[DATABASES_TABLE]) == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
