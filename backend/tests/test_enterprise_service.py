"""Tests for enterprise tier service — PRD §11.3 #1."""

from unittest.mock import MagicMock, patch

import pytest

from services import enterprise as svc


class TestIsEnterprise:
    def test_enterprise_string(self):
        assert svc.is_enterprise('enterprise') is True

    def test_enterprise_case_insensitive(self):
        assert svc.is_enterprise('Enterprise') is True
        assert svc.is_enterprise('ENTERPRISE') is True

    def test_starter_not_enterprise(self):
        assert svc.is_enterprise('starter') is False
        assert svc.is_enterprise('growth') is False
        assert svc.is_enterprise('pro') is False

    def test_none_and_empty(self):
        assert svc.is_enterprise(None) is False
        assert svc.is_enterprise('') is False


class TestEnforceUncapped:
    def test_enterprise_permits_any_n(self):
        # No supabase mocking — get_seat_limit only reads the in-memory map.
        assert svc.enforce_uncapped('enterprise', 1) is True
        assert svc.enforce_uncapped('enterprise', 1000) is True
        # PRD test gate: tier-quota for `enterprise` confirms uncapped behavior
        # under realistic loads.
        assert svc.enforce_uncapped('enterprise', 100_000) is True

    def test_starter_blocks_above_cap(self):
        # starter cap is 25
        assert svc.enforce_uncapped('starter', 25) is True
        assert svc.enforce_uncapped('starter', 26) is False

    def test_growth_blocks_above_cap(self):
        assert svc.enforce_uncapped('growth', 100) is True
        assert svc.enforce_uncapped('growth', 101) is False

    def test_pro_blocks_above_cap(self):
        assert svc.enforce_uncapped('pro', 300) is True
        assert svc.enforce_uncapped('pro', 301) is False


class TestActivateEnterprise:
    def test_activate_writes_sso_flag(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[{'id': 'org-1'}])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.activate_enterprise('org-1', sso_enabled=True)
        update_call = builder.update.call_args[0][0]
        assert update_call['sso_enabled'] is True
        assert 'enterprise_activated_at' in update_call

    def test_activate_defaults_sso_false(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[{'id': 'org-1'}])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.activate_enterprise('org-1')
        update_call = builder.update.call_args[0][0]
        assert update_call['sso_enabled'] is False

    def test_activate_uses_supplied_timestamp(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[{'id': 'org-1'}])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.activate_enterprise(
                'org-1', activated_at='2026-06-04T00:00:00+00:00',
            )
        update_call = builder.update.call_args[0][0]
        assert update_call['enterprise_activated_at'] == '2026-06-04T00:00:00+00:00'


class TestConfigureSso:
    def test_saml_accepted(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[{'id': 'org-1'}])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.configure_sso(
                'org-1', provider='saml', metadata={'entity_id': 'x'},
            )
        update_call = builder.update.call_args[0][0]
        assert update_call['sso_provider'] == 'saml'
        assert update_call['sso_enabled'] is True

    def test_oidc_accepted(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[{'id': 'org-1'}])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            svc.configure_sso('org-1', provider='oidc')
        update_call = builder.update.call_args[0][0]
        assert update_call['sso_provider'] == 'oidc'

    def test_invalid_provider_rejected(self):
        with pytest.raises(svc.EnterpriseConfigError) as exc:
            svc.configure_sso('org-1', provider='ldap')
        assert exc.value.code == 'invalid_provider'

    def test_empty_provider_rejected(self):
        with pytest.raises(svc.EnterpriseConfigError):
            svc.configure_sso('org-1', provider='')


class TestDisableSso:
    def test_disable_clears_all_sso_fields(self):
        mock_sb = MagicMock()
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value = builder
        with patch.object(svc, '_get_supabase', return_value=mock_sb):
            ok = svc.disable_sso('org-1')
        assert ok is True
        update_call = builder.update.call_args[0][0]
        assert update_call == {
            'sso_enabled': False,
            'sso_provider': None,
            'sso_metadata': None,
        }
