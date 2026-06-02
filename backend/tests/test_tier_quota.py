"""
Tests for backend.services.tier_quota and routes.tiers.

Covers:
  - canonical tier map shape
  - can_invite() seat-cap enforcement
  - GET /api/tiers endpoint
"""

import pytest
from unittest.mock import patch, MagicMock

from services import tier_quota


# ─── Tier map ────────────────────────────────────────────────────────────────


class TestTierMap:
    def test_all_four_tiers_present(self):
        tiers = tier_quota.get_tiers()
        assert set(tiers.keys()) == {'starter', 'growth', 'pro', 'enterprise'}

    def test_starter_caps(self):
        starter = tier_quota.get_tier('starter')
        assert starter['seat_cap'] == 25
        assert starter['price_usd_monthly'] == 49

    def test_growth_caps(self):
        growth = tier_quota.get_tier('growth')
        assert growth['seat_cap'] == 100
        assert growth['price_usd_monthly'] == 129

    def test_pro_caps(self):
        pro = tier_quota.get_tier('pro')
        assert pro['seat_cap'] == 300
        assert pro['price_usd_monthly'] == 299

    def test_enterprise_is_unlimited(self):
        ent = tier_quota.get_tier('enterprise')
        assert ent['seat_cap'] is None
        assert ent['price_usd_monthly'] is None

    def test_unknown_tier_returns_none(self):
        assert tier_quota.get_tier('platinum_plus_diamond') is None


# ─── can_invite() ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_supabase():
    """Patch the supabase client used inside tier_quota."""
    with patch('services.tier_quota._get_supabase') as m:
        yield m


def _wire_plan_and_count(mock_supabase, plan: str, count: int):
    """Helper: configure mock to return (plan, count) for the two calls."""
    def fake_table(name):
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.neq.return_value = builder
        if name == 'organization_billing':
            builder.single.return_value = builder
            builder.execute.return_value = MagicMock(data={'plan': plan}, count=None)
        elif name == 'organization_members':
            builder.execute.return_value = MagicMock(data=[], count=count)
        return builder
    mock_supabase.return_value.table.side_effect = fake_table


class TestCanInvite:
    def test_starter_under_cap_allowed(self, mock_supabase):
        _wire_plan_and_count(mock_supabase, 'starter', 10)
        allowed, info = tier_quota.can_invite('org-1', n=1)
        assert allowed is True
        assert info['seat_cap'] == 25
        assert info['current_count'] == 10

    def test_starter_at_cap_blocked(self, mock_supabase):
        _wire_plan_and_count(mock_supabase, 'starter', 25)
        allowed, info = tier_quota.can_invite('org-1', n=1)
        assert allowed is False
        assert info['code'] == 'tier_limit_exceeded'
        assert info['seat_cap'] == 25
        assert info['current_count'] == 25
        assert 'upgrade_url' in info

    def test_growth_bulk_invite_over_cap_blocked(self, mock_supabase):
        _wire_plan_and_count(mock_supabase, 'growth', 95)
        allowed, info = tier_quota.can_invite('org-1', n=10)
        assert allowed is False
        assert info['attempted'] == 10

    def test_enterprise_unlimited_allowed(self, mock_supabase):
        _wire_plan_and_count(mock_supabase, 'enterprise', 10_000)
        allowed, info = tier_quota.can_invite('org-1', n=1000)
        assert allowed is True
        assert info['seat_cap'] is None


# ─── GET /api/tiers ──────────────────────────────────────────────────────────


@pytest.fixture
def client():
    from flask import Flask
    from routes.tiers import tiers_bp
    app = Flask(__name__)
    app.register_blueprint(tiers_bp)
    return app.test_client()


class TestTiersEndpoint:
    def test_returns_all_tiers(self, client):
        resp = client.get('/api/tiers')
        assert resp.status_code == 200
        body = resp.get_json()
        assert 'tiers' in body
        assert set(body['tiers'].keys()) == {'starter', 'growth', 'pro', 'enterprise'}
        assert body['tiers']['growth']['seat_cap'] == 100
