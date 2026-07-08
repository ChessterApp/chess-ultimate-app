"""
Tests for the solution_line migration (014_add_solution_line.sql)
"""

import os
import pytest

MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations',
    '014_add_solution_line.sql',
)


@pytest.fixture
def sql_content():
    with open(MIGRATION_PATH, 'r') as f:
        return f.read()


class TestMigrationFile:
    def test_file_exists(self):
        assert os.path.exists(MIGRATION_PATH), (
            f"Migration file not found at {MIGRATION_PATH}"
        )

    def test_file_is_not_empty(self, sql_content):
        assert len(sql_content.strip()) > 0

    def test_wrapped_in_transaction(self, sql_content):
        upper = sql_content.upper()
        assert 'BEGIN;' in upper
        assert 'COMMIT;' in upper


class TestColumnDefinition:
    def test_adds_solution_line_column(self, sql_content):
        upper = sql_content.upper()
        assert 'ALTER TABLE LESSON_PUZZLES' in upper
        assert 'ADD COLUMN IF NOT EXISTS SOLUTION_LINE' in upper

    def test_column_is_jsonb(self, sql_content):
        assert 'solution_line JSONB' in sql_content

    def test_is_idempotent(self, sql_content):
        # IF NOT EXISTS keeps re-runs safe
        assert 'IF NOT EXISTS' in sql_content.upper()

    def test_does_not_touch_solution_move(self, sql_content):
        # We must not DROP/rename the existing solution_move column
        upper = sql_content.upper()
        assert 'DROP COLUMN' not in upper
        assert 'DROP TABLE' not in upper
