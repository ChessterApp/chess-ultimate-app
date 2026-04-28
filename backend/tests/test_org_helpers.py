"""
Tests for organization query helpers in supabase_client.
"""

import pytest
from unittest.mock import patch, MagicMock


SAMPLE_ORG = {
    'id': 'org-uuid-1',
    'slug': 'almatychess',
    'name': 'Almaty Chess School',
    'logo_url': None,
    'primary_color': '#1a73e8',
    'secondary_color': '#ffffff',
    'accent_color': '#ffd700',
    'status': 'active',
}

SAMPLE_MEMBERS = [
    {'id': 'm1', 'organization_id': 'org-uuid-1', 'user_id': 'user_1', 'role': 'owner'},
    {'id': 'm2', 'organization_id': 'org-uuid-1', 'user_id': 'user_2', 'role': 'student'},
]


class TestGetOrgBySlug:
    """Test get_org_by_slug helper."""

    def test_returns_org_for_valid_slug(self):
        mock_client = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=SAMPLE_ORG)
        mock_eq2 = MagicMock()
        mock_eq2.single.return_value = mock_single
        mock_eq1 = MagicMock()
        mock_eq1.eq.return_value = mock_eq2
        mock_select = MagicMock()
        mock_select.eq.return_value = mock_eq1
        mock_client.table.return_value.select.return_value = mock_select

        with patch('services.supabase_client.get_supabase_client', return_value=mock_client):
            from services.supabase_client import get_org_by_slug
            result = get_org_by_slug('almatychess')

        assert result is not None
        assert result['slug'] == 'almatychess'

    def test_returns_none_for_unknown_slug(self):
        mock_client = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=None)
        mock_eq2 = MagicMock()
        mock_eq2.single.return_value = mock_single
        mock_eq1 = MagicMock()
        mock_eq1.eq.return_value = mock_eq2
        mock_select = MagicMock()
        mock_select.eq.return_value = mock_eq1
        mock_client.table.return_value.select.return_value = mock_select

        with patch('services.supabase_client.get_supabase_client', return_value=mock_client):
            from services.supabase_client import get_org_by_slug
            result = get_org_by_slug('nonexistent')

        assert result is None


class TestGetOrgMembers:
    """Test get_org_members helper."""

    def test_returns_members_list(self):
        mock_client = MagicMock()
        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=SAMPLE_MEMBERS)
        mock_eq = MagicMock()
        mock_eq = mock_execute
        mock_select = MagicMock()
        mock_select.eq.return_value = mock_eq
        mock_client.table.return_value.select.return_value = mock_select

        with patch('services.supabase_client.get_supabase_client', return_value=mock_client):
            from services.supabase_client import get_org_members
            result = get_org_members('org-uuid-1')

        assert len(result) == 2
        assert result[0]['role'] == 'owner'
        assert result[1]['role'] == 'student'

    def test_returns_empty_list_for_no_members(self):
        mock_client = MagicMock()
        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=[])
        mock_select = MagicMock()
        mock_select.eq.return_value = mock_execute
        mock_client.table.return_value.select.return_value = mock_select

        with patch('services.supabase_client.get_supabase_client', return_value=mock_client):
            from services.supabase_client import get_org_members
            result = get_org_members('org-uuid-nonexistent')

        assert result == []
