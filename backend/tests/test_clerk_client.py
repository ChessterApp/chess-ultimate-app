"""
Tests for backend/services/clerk_client.py.

Mocks httpx at the request boundary; asserts each method hits the right URL,
sends the right body, raises ClerkAPIError on 5xx, and treats 404 as a no-op
on delete only.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from services.clerk_client import (
    CLERK_API_BASE,
    ClerkAPIError,
    ClerkClient,
    map_role_to_clerk,
)


def _resp(status: int, body: dict | None = None, content: bytes | None = None) -> MagicMock:
    """Build a fake httpx.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.content = content if content is not None else (b'' if body is None else b'{}')
    resp.json.return_value = body if body is not None else {}
    resp.text = '' if body is None else 'body-text'
    return resp


@pytest.fixture
def client():
    return ClerkClient(secret_key='sk_test_fake', timeout=1.0)


class TestRoleMapping:
    def test_owner_maps_to_admin(self):
        assert map_role_to_clerk('owner') == 'admin'

    def test_admin_maps_to_admin(self):
        assert map_role_to_clerk('admin') == 'admin'

    def test_teacher_maps_to_basic_member(self):
        assert map_role_to_clerk('teacher') == 'basic_member'

    def test_student_maps_to_basic_member(self):
        assert map_role_to_clerk('student') == 'basic_member'

    def test_unknown_maps_to_basic_member(self):
        assert map_role_to_clerk('something-else') == 'basic_member'


class TestCreateOrganization:
    def test_posts_to_organizations_endpoint(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(200, {'id': 'org_123', 'name': 'Acme'})) as mock_req:
            result = client.create_organization(
                name='Acme', slug='acme', created_by_user_id='user_42',
            )
        assert result == {'id': 'org_123', 'name': 'Acme'}
        args, kwargs = mock_req.call_args
        assert args[0] == 'POST'
        assert args[1] == f'{CLERK_API_BASE}/organizations'
        assert kwargs['json'] == {
            'name': 'Acme',
            'slug': 'acme',
            'created_by': 'user_42',
        }
        assert kwargs['headers']['Authorization'] == 'Bearer sk_test_fake'

    def test_raises_on_5xx(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(500, {'error': 'boom'})):
            with pytest.raises(ClerkAPIError) as exc_info:
                client.create_organization(name='x', slug='x', created_by_user_id='u')
        assert exc_info.value.status_code == 500

    def test_raises_on_4xx_other_than_404(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(422, {'error': 'invalid'})):
            with pytest.raises(ClerkAPIError) as exc_info:
                client.create_organization(name='x', slug='x', created_by_user_id='u')
        assert exc_info.value.status_code == 422

    def test_raises_when_secret_missing(self):
        empty = ClerkClient(secret_key='', timeout=1.0)
        with pytest.raises(ClerkAPIError):
            empty.create_organization(name='x', slug='x', created_by_user_id='u')


class TestDeleteOrganization:
    def test_deletes_via_id(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(200, content=b'')) as mock_req:
            client.delete_organization('org_999')
        args, _ = mock_req.call_args
        assert args[0] == 'DELETE'
        assert args[1] == f'{CLERK_API_BASE}/organizations/org_999'

    def test_404_is_no_op(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(404, {'error': 'not_found'})):
            # No exception expected.
            client.delete_organization('org_missing')

    def test_5xx_still_raises_on_delete(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(503, {'error': 'down'})):
            with pytest.raises(ClerkAPIError):
                client.delete_organization('org_999')


class TestCreateMembership:
    def test_posts_admin_role(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(200, {'id': 'omem_1'})) as mock_req:
            client.create_membership('org_1', 'user_9', 'admin')
        args, kwargs = mock_req.call_args
        assert args[0] == 'POST'
        assert args[1] == f'{CLERK_API_BASE}/organizations/org_1/memberships'
        assert kwargs['json'] == {'user_id': 'user_9', 'role': 'admin'}

    def test_posts_basic_member_role(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(200, {'id': 'omem_2'})) as mock_req:
            client.create_membership('org_1', 'user_9', 'basic_member')
        _, kwargs = mock_req.call_args
        assert kwargs['json']['role'] == 'basic_member'

    def test_rejects_invalid_role(self, client):
        with pytest.raises(ValueError):
            client.create_membership('org_1', 'user_9', 'owner')


class TestDeleteMembership:
    def test_deletes_membership(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(200, content=b'')) as mock_req:
            client.delete_membership('org_1', 'user_9')
        args, _ = mock_req.call_args
        assert args[0] == 'DELETE'
        assert args[1] == f'{CLERK_API_BASE}/organizations/org_1/memberships/user_9'

    def test_404_is_no_op(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(404, {'error': 'not_found'})):
            client.delete_membership('org_1', 'user_missing')


class TestUpdateMembershipRole:
    def test_patches_role(self, client):
        with patch('services.clerk_client.httpx.request',
                   return_value=_resp(200, {'role': 'admin'})) as mock_req:
            client.update_membership_role('org_1', 'user_9', 'admin')
        args, kwargs = mock_req.call_args
        assert args[0] == 'PATCH'
        assert args[1] == f'{CLERK_API_BASE}/organizations/org_1/memberships/user_9'
        assert kwargs['json'] == {'role': 'admin'}

    def test_rejects_invalid_role(self, client):
        with pytest.raises(ValueError):
            client.update_membership_role('org_1', 'user_9', 'teacher')


class TestNetworkErrors:
    def test_httpx_error_wraps_as_clerk_api_error(self, client):
        import httpx
        with patch('services.clerk_client.httpx.request',
                   side_effect=httpx.ConnectError('network down')):
            with pytest.raises(ClerkAPIError) as exc_info:
                client.create_organization(name='x', slug='x', created_by_user_id='u')
        assert exc_info.value.status_code == 502
