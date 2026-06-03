"""Tests for branches service — multi-branch support (PRD §11.3 #2)."""

from unittest.mock import MagicMock, patch

import pytest

from services import branches as svc


class TestRoleConstants:
    def test_org_wide_roles_include_owner_and_admin(self):
        assert 'owner' in svc.ORG_WIDE_ADMIN_ROLES
        assert 'admin' in svc.ORG_WIDE_ADMIN_ROLES
        assert 'teacher' not in svc.ORG_WIDE_ADMIN_ROLES

    def test_branch_admin_role_identifier_is_lowercase(self):
        # PRD §6 convention: lowercase enum identifiers
        assert svc.BRANCH_ADMIN_ROLE == 'branch_admin'

    def test_valid_member_roles_include_branch_admin(self):
        assert 'branch_admin' in svc.VALID_MEMBER_ROLES


class TestAssertBranchAccess:
    def test_owner_is_unrestricted_across_branches(self):
        svc.assert_branch_access(
            caller_role='owner', caller_branch_id=None,
            target_branch_id='branch-A',
        )
        svc.assert_branch_access(
            caller_role='owner', caller_branch_id='branch-A',
            target_branch_id='branch-B',
        )

    def test_admin_is_unrestricted_across_branches(self):
        svc.assert_branch_access(
            caller_role='admin', caller_branch_id=None,
            target_branch_id='branch-A',
        )
        svc.assert_branch_access(
            caller_role='admin', caller_branch_id='branch-A',
            target_branch_id=None,
        )

    def test_branch_admin_can_act_on_own_branch(self):
        svc.assert_branch_access(
            caller_role='branch_admin', caller_branch_id='branch-A',
            target_branch_id='branch-A',
        )

    def test_branch_admin_denied_on_sibling_branch(self):
        """Core test: branch admin denied on sibling-branch rows (PRD §11.3 gate)."""
        with pytest.raises(svc.BranchScopeError) as exc:
            svc.assert_branch_access(
                caller_role='branch_admin', caller_branch_id='branch-A',
                target_branch_id='branch-B',
            )
        assert exc.value.code == 'not_in_branch_scope'

    def test_branch_admin_denied_on_unassigned_target(self):
        """A branch_admin should not be able to touch an unscoped row either."""
        with pytest.raises(svc.BranchScopeError) as exc:
            svc.assert_branch_access(
                caller_role='branch_admin', caller_branch_id='branch-A',
                target_branch_id=None,
            )
        assert exc.value.code == 'not_in_branch_scope'

    def test_branch_admin_without_branch_id_rejected(self):
        with pytest.raises(svc.BranchScopeError) as exc:
            svc.assert_branch_access(
                caller_role='branch_admin', caller_branch_id=None,
                target_branch_id='branch-A',
            )
        assert exc.value.code == 'not_in_branch_scope'

    def test_teacher_denied_for_branch_admin_actions(self):
        with pytest.raises(svc.BranchScopeError):
            svc.assert_branch_access(
                caller_role='teacher', caller_branch_id=None,
                target_branch_id='branch-A',
            )

    def test_student_denied_for_branch_admin_actions(self):
        with pytest.raises(svc.BranchScopeError):
            svc.assert_branch_access(
                caller_role='student', caller_branch_id=None,
                target_branch_id='branch-A',
            )


class TestCreateBranch:
    def test_create_branch_happy_path(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.insert.return_value = builder
        builder.execute.return_value = MagicMock(
            data=[{
                'id': 'branch-xxx', 'organization_id': 'org-1',
                'name': 'Almaty', 'slug': 'almaty',
            }],
        )
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            res = svc.create_branch('org-1', name='Almaty', slug='almaty')
        assert res['slug'] == 'almaty'
        assert res['organization_id'] == 'org-1'

    def test_create_branch_rejects_empty_name(self):
        with pytest.raises(svc.BranchScopeError) as exc:
            svc.create_branch('org-1', name='', slug='ok')
        assert exc.value.code == 'invalid_branch'

    def test_create_branch_rejects_bad_slug(self):
        with pytest.raises(svc.BranchScopeError):
            svc.create_branch('org-1', name='X', slug='Bad Slug!')

    def test_create_branch_lowercases_slug(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.insert.return_value = builder
        builder.execute.return_value = MagicMock(data=[{'id': 'b1', 'slug': 'astana'}])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.create_branch('org-1', name='Astana', slug='ASTANA')
        insert_call = builder.insert.call_args[0][0]
        assert insert_call['slug'] == 'astana'

    def test_create_branch_accepts_optional_address(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.insert.return_value = builder
        builder.execute.return_value = MagicMock(data=[{'id': 'b1'}])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.create_branch(
                'org-1', name='X', slug='x', address='123 Main St',
            )
        insert_call = builder.insert.call_args[0][0]
        assert insert_call['address'] == '123 Main St'


class TestListMembersForCaller:
    def test_org_admin_sees_all_members(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[
            {'user_id': 'u1', 'branch_id': 'branch-A'},
            {'user_id': 'u2', 'branch_id': 'branch-B'},
            {'user_id': 'u3', 'branch_id': None},
        ])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            members = svc.list_members_for_caller(
                'org-1', caller_role='admin', caller_branch_id=None,
            )
        assert len(members) == 3

    def test_branch_admin_filters_to_own_branch(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[
            {'user_id': 'u1', 'branch_id': 'branch-A'},
        ])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.list_members_for_caller(
                'org-1', caller_role='branch_admin',
                caller_branch_id='branch-A',
            )
        # Both org_id filter and branch_id filter should be applied
        assert builder.eq.call_count >= 2
        eq_calls = builder.eq.call_args_list
        # Confirm we filter by branch_id
        all_filters = [(c.args[0], c.args[1]) for c in eq_calls]
        assert ('branch_id', 'branch-A') in all_filters

    def test_branch_admin_without_branch_returns_empty(self):
        mock_sb = MagicMock()
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            members = svc.list_members_for_caller(
                'org-1', caller_role='branch_admin', caller_branch_id=None,
            )
        assert members == []


class TestUpdateBranch:
    def test_update_branch_normalises_slug(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[
            {'id': 'b1', 'slug': 'new-slug'},
        ])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.update_branch('b1', slug='NEW-SLUG', name='New')
        update_call = builder.update.call_args[0][0]
        assert update_call['slug'] == 'new-slug'

    def test_update_branch_rejects_no_fields(self):
        with pytest.raises(svc.BranchScopeError) as exc:
            svc.update_branch('b1')
        assert exc.value.code == 'invalid_branch'

    def test_update_branch_rejects_bad_slug(self):
        with pytest.raises(svc.BranchScopeError):
            svc.update_branch('b1', slug='!!!bad!!!')

    def test_update_branch_ignores_disallowed_fields(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[{'id': 'b1'}])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.update_branch(
                'b1', name='Allowed',
                organization_id='HACK-attempt',  # disallowed
            )
        update_call = builder.update.call_args[0][0]
        assert 'organization_id' not in update_call
        assert update_call['name'] == 'Allowed'


class TestDeleteBranch:
    def test_delete_branch_returns_true(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.delete.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=None)
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            ok = svc.delete_branch('b1')
        assert ok is True
        # Confirm delete was actually called
        builder.delete.assert_called()
