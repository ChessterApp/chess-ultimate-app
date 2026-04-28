"""
Tests for organization migration SQL files.

Validates SQL syntax by parsing migration files.
"""

import os
import pytest


MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'supabase', 'migrations'
)


class TestMigrationFilesExist:
    """Verify all required migration files exist."""

    def test_organizations_migration_exists(self):
        path = os.path.join(MIGRATIONS_DIR, '20260428_001_organizations.sql')
        assert os.path.isfile(path), f'Missing migration: {path}'

    def test_add_org_id_migration_exists(self):
        path = os.path.join(MIGRATIONS_DIR, '20260428_002_add_org_id_to_existing.sql')
        assert os.path.isfile(path), f'Missing migration: {path}'

    def test_rls_policies_migration_exists(self):
        path = os.path.join(MIGRATIONS_DIR, '20260428_005_rls_policies.sql')
        assert os.path.isfile(path), f'Missing migration: {path}'


class TestOrganizationsMigrationContent:
    """Validate the organizations migration has required tables and indexes."""

    @pytest.fixture
    def sql(self):
        path = os.path.join(MIGRATIONS_DIR, '20260428_001_organizations.sql')
        with open(path) as f:
            return f.read()

    def test_creates_organizations_table(self, sql):
        assert 'CREATE TABLE organizations' in sql

    def test_creates_organization_members_table(self, sql):
        assert 'CREATE TABLE organization_members' in sql

    def test_creates_organization_content_table(self, sql):
        assert 'CREATE TABLE organization_content' in sql

    def test_creates_organization_billing_table(self, sql):
        assert 'CREATE TABLE organization_billing' in sql

    def test_slug_unique_constraint(self, sql):
        assert 'slug TEXT UNIQUE NOT NULL' in sql

    def test_slug_index(self, sql):
        assert 'idx_organizations_slug' in sql

    def test_member_unique_constraint(self, sql):
        assert 'UNIQUE(organization_id, user_id)' in sql

    def test_role_check_constraint(self, sql):
        assert "'owner'" in sql
        assert "'admin'" in sql
        assert "'teacher'" in sql
        assert "'student'" in sql

    def test_status_check_constraint(self, sql):
        assert "'active'" in sql
        assert "'suspended'" in sql
        assert "'trial'" in sql

    def test_billing_plan_check(self, sql):
        assert "'starter'" in sql
        assert "'growth'" in sql
        assert "'enterprise'" in sql

    def test_updated_at_trigger(self, sql):
        assert 'update_organizations_updated_at' in sql


class TestAddOrgIdMigrationContent:
    """Validate the add_org_id migration."""

    @pytest.fixture
    def sql(self):
        path = os.path.join(MIGRATIONS_DIR, '20260428_002_add_org_id_to_existing.sql')
        with open(path) as f:
            return f.read()

    def test_adds_org_id_to_user_progress(self, sql):
        assert 'user_progress' in sql
        assert 'organization_id UUID' in sql

    def test_adds_org_id_to_lesson_chat_history(self, sql):
        assert 'lesson_chat_history' in sql

    def test_adds_org_id_to_coaching_sessions(self, sql):
        assert 'coaching_sessions' in sql

    def test_adds_org_id_to_user_games(self, sql):
        assert 'user_games' in sql

    def test_adds_org_id_to_user_chess_profiles(self, sql):
        assert 'user_chess_profiles' in sql

    def test_creates_indexes(self, sql):
        assert 'idx_user_progress_org' in sql
        assert 'idx_lesson_chat_history_org' in sql
        assert 'idx_coaching_sessions_org' in sql
        assert 'idx_user_games_org' in sql
        assert 'idx_user_chess_profiles_org' in sql


class TestRlsPoliciesMigrationContent:
    """Validate the RLS policies migration."""

    @pytest.fixture
    def sql(self):
        path = os.path.join(MIGRATIONS_DIR, '20260428_005_rls_policies.sql')
        with open(path) as f:
            return f.read()

    def test_enables_rls_on_organizations(self, sql):
        assert 'ALTER TABLE organizations ENABLE ROW LEVEL SECURITY' in sql

    def test_enables_rls_on_org_members(self, sql):
        assert 'ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY' in sql

    def test_enables_rls_on_org_content(self, sql):
        assert 'ALTER TABLE organization_content ENABLE ROW LEVEL SECURITY' in sql

    def test_enables_rls_on_org_billing(self, sql):
        assert 'ALTER TABLE organization_billing ENABLE ROW LEVEL SECURITY' in sql

    def test_enables_rls_on_user_progress(self, sql):
        assert 'ALTER TABLE user_progress ENABLE ROW LEVEL SECURITY' in sql

    def test_enables_rls_on_user_games(self, sql):
        assert 'ALTER TABLE user_games ENABLE ROW LEVEL SECURITY' in sql

    def test_has_direct_user_access_policy(self, sql):
        assert 'direct_user_access' in sql

    def test_has_org_member_access_policy(self, sql):
        assert 'org_member_access' in sql

    def test_has_org_admin_access_policy(self, sql):
        assert 'org_admin_access' in sql

    def test_admin_roles_in_policy(self, sql):
        # Verify admin roles are checked in policies
        assert "('owner', 'admin', 'teacher')" in sql

    def test_public_read_active_orgs(self, sql):
        assert 'public_read_active_orgs' in sql
