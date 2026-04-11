"""
Tests for the user_games migration (011_create_user_games.sql)
"""

import os
import pytest
import re

MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations',
    '011_create_user_games.sql',
)


@pytest.fixture
def sql_content():
    with open(MIGRATION_PATH, 'r') as f:
        return f.read()


@pytest.fixture
def sql_statements(sql_content):
    """Split SQL into individual statements, ignoring comments."""
    stmts = []
    for s in sql_content.split(';'):
        cleaned = s.strip()
        # Remove leading comment lines
        lines = [l for l in cleaned.splitlines() if not l.strip().startswith('--')]
        cleaned = '\n'.join(lines).strip()
        if cleaned:
            stmts.append(cleaned)
    return stmts


class TestMigrationFileExists:
    def test_file_exists(self):
        assert os.path.exists(MIGRATION_PATH), (
            f"Migration file not found at {MIGRATION_PATH}"
        )

    def test_file_is_not_empty(self, sql_content):
        assert len(sql_content.strip()) > 0


class TestTableDefinition:
    def test_creates_user_games_table(self, sql_content):
        assert 'CREATE TABLE' in sql_content.upper()
        assert 'user_games' in sql_content

    def test_uses_if_not_exists(self, sql_content):
        assert 'IF NOT EXISTS' in sql_content.upper()

    def test_has_id_primary_key(self, sql_content):
        assert 'id UUID' in sql_content
        assert 'PRIMARY KEY' in sql_content
        assert 'gen_random_uuid()' in sql_content

    def test_has_user_id_not_null(self, sql_content):
        assert re.search(r'user_id\s+TEXT\s+NOT NULL', sql_content)

    def test_has_pgn_not_null(self, sql_content):
        assert re.search(r'pgn\s+TEXT\s+NOT NULL', sql_content)

    def test_has_all_required_columns(self, sql_content):
        required_columns = [
            'id', 'user_id', 'title', 'white', 'black',
            'white_elo', 'black_elo', 'result', 'date', 'event',
            'eco', 'opening_name', 'pgn', 'notes', 'tags',
            'is_favorite', 'source', 'deleted_at', 'created_at', 'updated_at',
        ]
        for col in required_columns:
            assert re.search(rf'\b{col}\b', sql_content), (
                f"Missing column: {col}"
            )

    def test_tags_is_text_array(self, sql_content):
        assert "TEXT[]" in sql_content or "text[]" in sql_content

    def test_tags_default_empty_array(self, sql_content):
        assert "DEFAULT '{}'" in sql_content

    def test_is_favorite_default_false(self, sql_content):
        assert re.search(r'is_favorite\s+BOOLEAN\s+DEFAULT\s+FALSE', sql_content, re.IGNORECASE)

    def test_source_default_manual(self, sql_content):
        assert re.search(r"source\s+TEXT\s+DEFAULT\s+'manual'", sql_content)

    def test_deleted_at_default_null(self, sql_content):
        assert re.search(r'deleted_at\s+TIMESTAMPTZ\s+DEFAULT\s+NULL', sql_content, re.IGNORECASE)

    def test_timestamps_default_now(self, sql_content):
        assert sql_content.count('DEFAULT NOW()') >= 2 or sql_content.count('DEFAULT now()') >= 2

    def test_elo_columns_are_integer(self, sql_content):
        assert re.search(r'white_elo\s+INTEGER', sql_content)
        assert re.search(r'black_elo\s+INTEGER', sql_content)


class TestIndexes:
    def test_user_id_index(self, sql_content):
        assert 'idx_user_games_user_id' in sql_content
        assert re.search(
            r'CREATE\s+INDEX.*idx_user_games_user_id\s+ON\s+user_games\s*\(\s*user_id\s*\)',
            sql_content,
            re.IGNORECASE,
        )

    def test_deleted_at_partial_index(self, sql_content):
        assert 'idx_user_games_deleted' in sql_content
        # Should be a partial index filtering on non-deleted rows
        assert re.search(
            r'WHERE\s+deleted_at\s+IS\s+NULL',
            sql_content,
            re.IGNORECASE,
        )


class TestRowLevelSecurity:
    def test_rls_enabled(self, sql_content):
        assert re.search(
            r'ALTER\s+TABLE\s+user_games\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY',
            sql_content,
            re.IGNORECASE,
        )


class TestMigrationRunnerCompatibility:
    """Verify the SQL can be split by the migration runner's semicolon splitting."""

    def test_statements_are_parseable(self, sql_statements):
        assert len(sql_statements) >= 4, (
            f"Expected at least 4 statements (CREATE TABLE, 2 indexes, RLS), "
            f"got {len(sql_statements)}"
        )

    def test_no_empty_statements_after_split(self, sql_statements):
        for stmt in sql_statements:
            assert len(stmt.strip()) > 0

    def test_create_table_is_first_statement(self, sql_statements):
        assert 'CREATE TABLE' in sql_statements[0].upper()

    def test_each_statement_is_valid_sql_keyword(self, sql_statements):
        valid_starts = ('CREATE', 'ALTER', 'INSERT', 'UPDATE', 'DROP', 'SET')
        for stmt in sql_statements:
            first_word = stmt.lstrip().split()[0].upper()
            assert first_word in valid_starts, (
                f"Statement starts with unexpected keyword: {first_word}"
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
