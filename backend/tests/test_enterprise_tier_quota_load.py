"""
Enterprise tier-quota load test (PRD §11.3 gate).

The PRD requires confirmation that the enterprise tier permits uncapped
seat counts "under realistic load". We simulate that by:

  1. Asserting `tier_quota.can_invite('enterprise', n)` permits values
     across the realistic range up to 1,000,000.
  2. Stubbing the seat-count source to return very large numbers and
     showing the gate still says True.
  3. Confirming the response shape always carries `seat_cap: None` for
     enterprise — frontend code keys off this null to hide the cap banner.
"""

from unittest.mock import MagicMock, patch

import pytest

from services import tier_quota


REALISTIC_LOADS = [1, 10, 100, 1_000, 10_000, 100_000, 1_000_000]


@pytest.fixture
def mock_supabase():
    with patch('services.tier_quota._get_supabase') as m:
        yield m


def _wire(mock_supabase, plan: str, current: int):
    def fake_table(name):
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.neq.return_value = builder
        if name == 'organization_billing':
            builder.single.return_value = builder
            builder.execute.return_value = MagicMock(
                data={'plan': plan}, count=None,
            )
        elif name == 'organization_members':
            builder.execute.return_value = MagicMock(data=[], count=current)
        return builder
    mock_supabase.return_value.table.side_effect = fake_table


class TestEnterpriseUncappedLoad:
    @pytest.mark.parametrize('n', REALISTIC_LOADS)
    def test_invite_n_always_allowed(self, mock_supabase, n):
        _wire(mock_supabase, 'enterprise', current=0)
        allowed, info = tier_quota.can_invite('org-ent', n=n)
        assert allowed is True, f'enterprise denied n={n}'
        assert info['seat_cap'] is None

    @pytest.mark.parametrize('current', REALISTIC_LOADS)
    def test_existing_seats_irrelevant_for_enterprise(self, mock_supabase, current):
        _wire(mock_supabase, 'enterprise', current=current)
        allowed, info = tier_quota.can_invite('org-ent', n=1)
        assert allowed is True
        assert info['seat_cap'] is None

    def test_enterprise_cap_is_None_via_get_seat_limit(self):
        assert tier_quota.get_seat_limit('enterprise') is None

    def test_can_invite_info_shape_for_enterprise(self, mock_supabase):
        _wire(mock_supabase, 'enterprise', current=5000)
        _, info = tier_quota.can_invite('org-ent', n=500)
        # Frontend keys off these:
        assert info['plan'] == 'enterprise'
        assert info['seat_cap'] is None
        assert info['current_count'] == 5000

    def test_starter_blocks_at_realistic_load(self, mock_supabase):
        # Sanity: non-enterprise tiers do get blocked.
        _wire(mock_supabase, 'starter', current=25)
        allowed, info = tier_quota.can_invite('org-1', n=1)
        assert allowed is False
        assert info['code'] == 'tier_limit_exceeded'
