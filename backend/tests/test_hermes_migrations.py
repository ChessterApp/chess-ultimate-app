"""
Tests for Hermes coaching migrations:
  - 012_create_user_chess_profiles.sql
  - 013_create_coaching_sessions.sql

Validates SQL structure, columns, indexes, triggers, and RLS.
"""

import os
import re
import pytest

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations',
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def read_migration(filename):
    path = os.path.join(MIGRATIONS_DIR, filename)
    with open(path) as f:
        return f.read()


def split_statements(sql):
    """Split SQL into non-empty statements, ignoring comment-only lines."""
    stmts = []
    for s in sql.split(';'):
        lines = [l for l in s.strip().splitlines() if not l.strip().startswith('--')]
        cleaned = '\n'.join(lines).strip()
        if cleaned:
            stmts.append(cleaned)
    return stmts


# ── 012: user_chess_profiles ─────────────────────────────────────────────────

class TestUserChessProfilesMigration:
    @pytest.fixture(autouse=True)
    def load_sql(self):
        self.sql = read_migration('012_create_user_chess_profiles.sql')
        self.stmts = split_statements(self.sql)

    def test_file_exists(self):
        assert os.path.exists(os.path.join(MIGRATIONS_DIR, '012_create_user_chess_profiles.sql'))

    def test_creates_table(self):
        assert 'CREATE TABLE' in self.sql.upper()
        assert 'user_chess_profiles' in self.sql

    def test_uses_if_not_exists(self):
        assert 'IF NOT EXISTS' in self.sql.upper()

    def test_has_id_primary_key(self):
        assert re.search(r'id\s+UUID.*PRIMARY KEY', self.sql, re.IGNORECASE | re.DOTALL)
        assert 'gen_random_uuid()' in self.sql

    def test_user_id_unique_not_null(self):
        assert re.search(r'user_id\s+TEXT\s+UNIQUE\s+NOT\s+NULL', self.sql, re.IGNORECASE)

    def test_has_all_required_columns(self):
        required = [
            'id', 'user_id', 'lichess_username', 'chesscom_username',
            'lichess_rating', 'chesscom_rating', 'last_synced_at',
            'created_at', 'updated_at',
        ]
        for col in required:
            assert re.search(rf'\b{col}\b', self.sql), f"Missing column: {col}"

    def test_rating_columns_are_integer(self):
        assert re.search(r'lichess_rating\s+INTEGER', self.sql, re.IGNORECASE)
        assert re.search(r'chesscom_rating\s+INTEGER', self.sql, re.IGNORECASE)

    def test_timestamps_default_now(self):
        assert self.sql.count('DEFAULT NOW()') >= 2 or self.sql.count('DEFAULT now()') >= 2

    def test_user_id_index(self):
        assert 'idx_user_chess_profiles_user_id' in self.sql

    def test_updated_at_trigger(self):
        assert re.search(r'CREATE\s+TRIGGER.*update.*user_chess_profiles.*updated_at', self.sql, re.IGNORECASE | re.DOTALL)
        assert 'update_updated_at_column' in self.sql

    def test_rls_enabled(self):
        assert re.search(
            r'ALTER\s+TABLE\s+user_chess_profiles\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY',
            self.sql, re.IGNORECASE,
        )

    def test_statements_parseable(self):
        assert len(self.stmts) >= 4  # CREATE TABLE, INDEX, TRIGGER, RLS

    def test_create_table_is_first(self):
        assert 'CREATE TABLE' in self.stmts[0].upper()


# ── 013: coaching_sessions ───────────────────────────────────────────────────

class TestCoachingSessionsMigration:
    @pytest.fixture(autouse=True)
    def load_sql(self):
        self.sql = read_migration('013_create_coaching_sessions.sql')
        self.stmts = split_statements(self.sql)

    def test_file_exists(self):
        assert os.path.exists(os.path.join(MIGRATIONS_DIR, '013_create_coaching_sessions.sql'))

    def test_creates_table(self):
        assert 'CREATE TABLE' in self.sql.upper()
        assert 'coaching_sessions' in self.sql

    def test_uses_if_not_exists(self):
        assert 'IF NOT EXISTS' in self.sql.upper()

    def test_has_id_primary_key(self):
        assert re.search(r'id\s+UUID.*PRIMARY KEY', self.sql, re.IGNORECASE | re.DOTALL)
        assert 'gen_random_uuid()' in self.sql

    def test_user_id_not_null(self):
        assert re.search(r'user_id\s+TEXT\s+NOT\s+NULL', self.sql, re.IGNORECASE)

    def test_has_all_required_columns(self):
        required = ['id', 'user_id', 'title', 'messages', 'board_state', 'created_at', 'updated_at']
        for col in required:
            assert re.search(rf'\b{col}\b', self.sql), f"Missing column: {col}"

    def test_messages_jsonb_default_empty_array(self):
        assert re.search(r'messages\s+JSONB', self.sql, re.IGNORECASE)
        assert "[]" in self.sql

    def test_board_state_is_jsonb(self):
        assert re.search(r'board_state\s+JSONB', self.sql, re.IGNORECASE)

    def test_timestamps_default_now(self):
        assert self.sql.count('DEFAULT NOW()') >= 2 or self.sql.count('DEFAULT now()') >= 2

    def test_user_id_index(self):
        assert 'idx_coaching_sessions_user_id' in self.sql

    def test_updated_at_index(self):
        assert 'idx_coaching_sessions_updated' in self.sql

    def test_updated_at_trigger(self):
        assert re.search(r'CREATE\s+TRIGGER.*update.*coaching_sessions.*updated_at', self.sql, re.IGNORECASE | re.DOTALL)
        assert 'update_updated_at_column' in self.sql

    def test_rls_enabled(self):
        assert re.search(
            r'ALTER\s+TABLE\s+coaching_sessions\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY',
            self.sql, re.IGNORECASE,
        )

    def test_statements_parseable(self):
        assert len(self.stmts) >= 5  # CREATE TABLE, 2 indexes, TRIGGER, RLS

    def test_create_table_is_first(self):
        assert 'CREATE TABLE' in self.stmts[0].upper()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
