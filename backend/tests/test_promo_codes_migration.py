"""
Tests for the promo_codes migration (PROMO_CODE_PRD §1).

Validates:
  - migration file exists at the expected path
  - SQL declares the table, columns, and constraints called for in the PRD
  - the seed INSERT for the 'FREE' code is present and idempotent

These tests are file-content checks; they do not touch the live database.
"""

import os
import re

import pytest


MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'supabase', 'migrations',
)

MIGRATION_FILENAME = '20260629_014_promo_codes.sql'


@pytest.fixture
def sql():
    path = os.path.join(MIGRATIONS_DIR, MIGRATION_FILENAME)
    with open(path) as f:
        return f.read()


class TestPromoCodesMigrationFile:
    def test_file_exists(self):
        path = os.path.join(MIGRATIONS_DIR, MIGRATION_FILENAME)
        assert os.path.isfile(path), f'Missing migration: {path}'


class TestPromoCodesSchema:
    def test_creates_table(self, sql):
        assert re.search(r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+promo_codes', sql, re.IGNORECASE)

    def test_code_is_primary_key(self, sql):
        assert re.search(r'code\s+TEXT\s+PRIMARY\s+KEY', sql, re.IGNORECASE)

    def test_discount_pct_range_check(self, sql):
        assert re.search(
            r'discount_pct\s+INT\s+NOT\s+NULL\s+CHECK\s*\(\s*discount_pct\s+BETWEEN\s+1\s+AND\s+100\s*\)',
            sql, re.IGNORECASE,
        )

    def test_max_uses_nullable(self, sql):
        # max_uses must allow NULL (unlimited). Reject anything with NOT NULL on that column.
        assert re.search(r'max_uses\s+INT(\s|,)', sql, re.IGNORECASE)
        assert not re.search(r'max_uses\s+INT\s+NOT\s+NULL', sql, re.IGNORECASE)

    def test_uses_defaults_to_zero(self, sql):
        assert re.search(r'uses\s+INT\s+NOT\s+NULL\s+DEFAULT\s+0', sql, re.IGNORECASE)

    def test_active_defaults_to_true(self, sql):
        assert re.search(r'active\s+BOOLEAN\s+NOT\s+NULL\s+DEFAULT\s+TRUE', sql, re.IGNORECASE)

    def test_expires_at_timestamptz_nullable(self, sql):
        assert re.search(r'expires_at\s+TIMESTAMPTZ', sql, re.IGNORECASE)
        assert not re.search(r'expires_at\s+TIMESTAMPTZ\s+NOT\s+NULL', sql, re.IGNORECASE)

    def test_created_at_defaults_to_now(self, sql):
        assert re.search(r'created_at\s+TIMESTAMPTZ\s+NOT\s+NULL\s+DEFAULT\s+now\(\)', sql, re.IGNORECASE)


class TestFreeCodeSeed:
    def test_seeds_free_code(self, sql):
        assert re.search(
            r"INSERT\s+INTO\s+promo_codes\s*\(\s*code\s*,\s*discount_pct\s*,\s*max_uses\s*,\s*active\s*\)",
            sql, re.IGNORECASE,
        )
        assert re.search(r"VALUES\s*\(\s*'FREE'\s*,\s*100\s*,\s*NULL\s*,\s*TRUE\s*\)", sql, re.IGNORECASE)

    def test_seed_is_idempotent(self, sql):
        assert re.search(r'ON\s+CONFLICT\s*\(\s*code\s*\)\s+DO\s+NOTHING', sql, re.IGNORECASE)


class TestDatabaseState:
    """Live-database check (skipped if SUPABASE_DB_URL is not set)."""

    def _connect(self):
        url = os.environ.get('SUPABASE_DB_URL')
        if not url:
            pytest.skip('SUPABASE_DB_URL not set')
        try:
            import psycopg2
        except ImportError:
            pytest.skip('psycopg2 not installed')
        return psycopg2.connect(url)

    def test_free_promo_code_row_exists(self):
        """Acceptance criterion #1: select * from promo_codes where code='FREE' returns 1 row."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT code, discount_pct, max_uses, active "
                    "FROM promo_codes WHERE code = 'FREE'"
                )
                rows = cur.fetchall()
                assert len(rows) == 1, f'expected exactly 1 FREE row, got {len(rows)}'
                code, discount_pct, max_uses, active = rows[0]
                assert code == 'FREE'
                assert discount_pct == 100
                assert max_uses is None  # unlimited
                assert active is True
        finally:
            conn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
