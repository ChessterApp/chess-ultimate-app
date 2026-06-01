"""Tests for migration 20260601_009_org_custom_domain.sql.

These are static-content tests — we don't apply migrations against a live DB
in this suite (see test_rls_isolation.py for live-DB coverage). The goal is to
catch typos and structural drift in the migration file.
"""

import os
import re

import pytest


MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'supabase', 'migrations',
)
MIGRATION_FILE = os.path.join(MIGRATIONS_DIR, '20260601_009_org_custom_domain.sql')


@pytest.fixture
def sql():
    assert os.path.isfile(MIGRATION_FILE), f'Missing migration: {MIGRATION_FILE}'
    with open(MIGRATION_FILE) as f:
        return f.read()


class TestMigration009Structure:
    def test_adds_custom_domain_column(self, sql):
        assert 'ADD COLUMN IF NOT EXISTS custom_domain TEXT' in sql

    def test_adds_status_column(self, sql):
        assert 'custom_domain_status TEXT' in sql

    def test_adds_verified_at_column(self, sql):
        assert 'custom_domain_verified_at TIMESTAMPTZ' in sql

    def test_adds_vercel_id_column(self, sql):
        assert 'custom_domain_vercel_id TEXT' in sql

    def test_status_check_constraint_covers_all_states(self, sql):
        for state in ('pending', 'verifying', 'active', 'failed'):
            assert f"'{state}'" in sql, f'Missing state in CHECK: {state}'

    def test_unique_partial_index(self, sql):
        # idx must be UNIQUE and ignore NULL domains
        idx_block = re.search(
            r'CREATE UNIQUE INDEX[^;]+idx_org_custom_domain[^;]+WHERE custom_domain IS NOT NULL',
            sql, flags=re.IGNORECASE | re.DOTALL,
        )
        assert idx_block, 'Expected unique partial index on custom_domain'

    def test_status_index(self, sql):
        assert 'idx_org_custom_domain_status' in sql

    def test_idempotent_guards(self, sql):
        # Re-running the migration shouldn't error — these guards are required.
        assert 'IF NOT EXISTS' in sql
        # ALTER ADD CONSTRAINT must be wrapped in a DO block (Postgres has no
        # native IF NOT EXISTS for constraints).
        assert 'pg_constraint' in sql


class TestMigration009DoesNotTouchRLS:
    """Sanity: migration 009 must not redefine RLS policies (migration 008 owns them)."""

    def test_no_policy_creation(self, sql):
        assert 'CREATE POLICY' not in sql.upper().replace('  ', ' ')

    def test_no_enable_rls(self, sql):
        assert 'ENABLE ROW LEVEL SECURITY' not in sql
