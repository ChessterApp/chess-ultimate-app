"""Tests for branches HTTP routes — PRD §11.3 #2."""

from unittest.mock import MagicMock, patch

import pytest


ORG_ID = 'org-aaaa'
ADMIN = 'user_owner'
BRANCH_ADMIN = 'user_branch_admin'


@pytest.fixture
def client():
    from flask import Flask
    from routes.branches import branches_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(branches_bp)
    return app.test_client()


def _make_chain(data=None):
    builder = MagicMock()
    builder.table.return_value = builder
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.update.return_value = builder
    builder.delete.return_value = builder
    builder.insert.return_value = builder
    builder.order.return_value = builder
    builder.single.return_value = builder
    builder.execute.return_value = MagicMock(data=data)
    return builder


class TestListBranches:
    def test_list_requires_user_header(self, client):
        resp = client.get(f'/api/admin/organizations/{ORG_ID}/branches')
        assert resp.status_code == 401

    def test_list_denied_for_non_member(self, client):
        with patch('routes.branches._get_caller_role', return_value=None):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/branches',
                headers={'X-User-Id': 'outsider'},
            )
        assert resp.status_code == 403

    def test_org_admin_sees_all_branches(self, client):
        all_branches = [
            {'id': 'b1', 'name': 'Almaty'},
            {'id': 'b2', 'name': 'Astana'},
        ]
        with patch('routes.branches._get_caller_role', return_value='admin'), \
             patch('services.branches.list_branches', return_value=all_branches):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/branches',
                headers={'X-User-Id': ADMIN},
            )
        assert resp.status_code == 200
        assert len(resp.get_json()['branches']) == 2

    def test_branch_admin_only_sees_own_branch(self, client):
        all_branches = [
            {'id': 'b1', 'name': 'Almaty'},
            {'id': 'b2', 'name': 'Astana'},
        ]
        with patch('routes.branches._get_caller_role', return_value='branch_admin'), \
             patch('services.branches.list_branches', return_value=all_branches), \
             patch('services.branches.get_caller_branch_id', return_value='b2'):
            resp = client.get(
                f'/api/admin/organizations/{ORG_ID}/branches',
                headers={'X-User-Id': BRANCH_ADMIN},
            )
        assert resp.status_code == 200
        branches = resp.get_json()['branches']
        assert len(branches) == 1
        assert branches[0]['id'] == 'b2'


class TestCreateBranch:
    def test_branch_admin_cannot_create_branches(self, client):
        with patch('routes.branches._get_caller_role', return_value='branch_admin'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branches',
                json={'name': 'X', 'slug': 'x'},
                headers={'X-User-Id': BRANCH_ADMIN},
            )
        assert resp.status_code == 403

    def test_org_admin_can_create(self, client):
        created = {'id': 'b-new', 'slug': 'almaty', 'name': 'Almaty'}
        with patch('routes.branches._get_caller_role', return_value='admin'), \
             patch('services.branches.create_branch', return_value=created):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branches',
                json={'name': 'Almaty', 'slug': 'almaty'},
                headers={'X-User-Id': ADMIN},
            )
        assert resp.status_code == 201
        assert resp.get_json()['branch']['id'] == 'b-new'

    def test_create_returns_400_on_invalid_input(self, client):
        from services.branches import BranchScopeError
        with patch('routes.branches._get_caller_role', return_value='admin'), \
             patch('services.branches.create_branch',
                   side_effect=BranchScopeError('invalid_branch', 'bad')):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branches',
                json={'name': '', 'slug': ''},
                headers={'X-User-Id': ADMIN},
            )
        assert resp.status_code == 400


class TestUpdateBranch:
    def test_404_when_branch_not_in_org(self, client):
        with patch('routes.branches._get_caller_role', return_value='admin'), \
             patch('services.branches.get_branch',
                   return_value={'id': 'b1', 'organization_id': 'OTHER_ORG'}):
            resp = client.patch(
                f'/api/admin/organizations/{ORG_ID}/branches/b1',
                json={'name': 'New'},
                headers={'X-User-Id': ADMIN},
            )
        assert resp.status_code == 404

    def test_update_succeeds_for_org_admin(self, client):
        with patch('routes.branches._get_caller_role', return_value='admin'), \
             patch('services.branches.get_branch',
                   return_value={'id': 'b1', 'organization_id': ORG_ID}), \
             patch('services.branches.update_branch',
                   return_value={'id': 'b1', 'name': 'Renamed'}):
            resp = client.patch(
                f'/api/admin/organizations/{ORG_ID}/branches/b1',
                json={'name': 'Renamed'},
                headers={'X-User-Id': ADMIN},
            )
        assert resp.status_code == 200


class TestAssignMember:
    def test_branch_admin_denied_on_sibling_branch(self, client):
        """Scoping gate: branch admin assigning member to sibling branch denied."""
        with patch('routes.branches._get_caller_role', return_value='branch_admin'), \
             patch('services.branches.get_branch',
                   return_value={'id': 'sibling', 'organization_id': ORG_ID}), \
             patch('services.branches.get_caller_branch_id', return_value='own'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branches/sibling/members',
                json={'user_id': 'kid1'},
                headers={'X-User-Id': BRANCH_ADMIN},
            )
        assert resp.status_code == 403
        assert resp.get_json()['error'] == 'not_in_branch_scope'

    def test_branch_admin_can_assign_within_own_branch(self, client):
        with patch('routes.branches._get_caller_role', return_value='branch_admin'), \
             patch('services.branches.get_branch',
                   return_value={'id': 'own', 'organization_id': ORG_ID}), \
             patch('services.branches.get_caller_branch_id', return_value='own'), \
             patch('routes.branches._get_supabase') as mock_sb:
            builder = _make_chain(data=[])
            mock_sb.return_value = builder
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branches/own/members',
                json={'user_id': 'kid1'},
                headers={'X-User-Id': BRANCH_ADMIN},
            )
        assert resp.status_code == 200

    def test_org_admin_can_assign_anywhere(self, client):
        with patch('routes.branches._get_caller_role', return_value='owner'), \
             patch('services.branches.get_branch',
                   return_value={'id': 'any', 'organization_id': ORG_ID}), \
             patch('routes.branches._get_supabase') as mock_sb:
            builder = _make_chain(data=[])
            mock_sb.return_value = builder
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branches/any/members',
                json={'user_id': 'someone'},
                headers={'X-User-Id': ADMIN},
            )
        assert resp.status_code == 200

    def test_assign_requires_user_id(self, client):
        with patch('routes.branches._get_caller_role', return_value='admin'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branches/b1/members',
                json={},
                headers={'X-User-Id': ADMIN},
            )
        assert resp.status_code == 400


class TestDeleteBranch:
    def test_org_admin_can_delete(self, client):
        with patch('routes.branches._get_caller_role', return_value='admin'), \
             patch('services.branches.get_branch',
                   return_value={'id': 'b1', 'organization_id': ORG_ID}), \
             patch('services.branches.delete_branch', return_value=True):
            resp = client.delete(
                f'/api/admin/organizations/{ORG_ID}/branches/b1',
                headers={'X-User-Id': ADMIN},
            )
        assert resp.status_code == 200

    def test_branch_admin_cannot_delete(self, client):
        with patch('routes.branches._get_caller_role', return_value='branch_admin'):
            resp = client.delete(
                f'/api/admin/organizations/{ORG_ID}/branches/b1',
                headers={'X-User-Id': BRANCH_ADMIN},
            )
        assert resp.status_code == 403
