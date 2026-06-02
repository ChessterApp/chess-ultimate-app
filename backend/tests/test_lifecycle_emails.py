"""Tests for backend.services.lifecycle_emails (PRD §11.2 #6)."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from services import lifecycle_emails as svc


ORG_ID = 'org-life-1234'


# ─── Template renderer ───────────────────────────────────────────────────


class TestTemplateRendering:
    def test_render_substitutes_placeholders(self):
        html = svc._render_template('welcome_day1', {
            'school_name': 'Almaty',
            'primary_color': '#0066ff',
            'logo_url': '',
            'dashboard_url': 'https://demo.chesster.io/admin',
            'slug': 'demo',
            'upgrade_url': '',
        })
        assert 'Almaty' in html
        assert '#0066ff' in html
        assert 'https://demo.chesster.io/admin' in html

    def test_template_snapshot_day3(self):
        html = svc._render_template('nudge_day3', {
            'school_name': 'Almaty', 'primary_color': '#0066ff',
            'dashboard_url': 'x', 'logo_url': '', 'slug': '',
            'upgrade_url': '',
        })
        # Snapshot-y assertion — body should contain the headline + dashboard link.
        assert 'Almaty' in html
        assert 'dashboard' in html.lower() or 'setup' in html.lower()

    def test_template_snapshot_day7(self):
        html = svc._render_template('success_day7', {
            'school_name': 'Almaty', 'primary_color': '#0066ff',
            'dashboard_url': 'x', 'logo_url': '', 'slug': '',
            'upgrade_url': 'https://chesster.io/admin/billing?upgrade=pro',
        })
        assert 'week' in html.lower()
        assert 'upgrade' in html.lower() or 'pro' in html.lower()


# ─── Scheduler ───────────────────────────────────────────────────────────


class TestScheduleForOrg:
    def test_schedules_three_rows_at_correct_offsets(self):
        captured = {}
        builder = MagicMock()

        def fake_upsert(rows, **kwargs):
            captured['rows'] = rows
            return builder

        builder.execute.return_value = MagicMock(data=[])
        sb = MagicMock()
        sb.table.return_value.upsert = MagicMock(side_effect=fake_upsert)

        with patch.object(svc, '_supabase', return_value=sb):
            base = datetime(2026, 6, 2, tzinfo=timezone.utc)
            svc.schedule_for_org(ORG_ID, activated_at=base)

        rows = captured['rows']
        kinds = {r['kind'] for r in rows}
        assert kinds == {'welcome_day1', 'nudge_day3', 'success_day7'}
        # day1 row should land at base + 24h
        day1 = next(r for r in rows if r['kind'] == 'welcome_day1')
        assert day1['scheduled_for'].startswith('2026-06-03')


# ─── send_due iteration ──────────────────────────────────────────────────


class TestSendDue:
    @pytest.fixture(autouse=True)
    def set_api_key(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_test')
        yield

    def test_marks_row_sent_on_successful_post(self):
        row = {
            'id': 'r1', 'kind': 'welcome_day1', 'org_id': ORG_ID,
            'scheduled_for': datetime.now(timezone.utc).isoformat(),
            'sent_at': None,
        }
        org = {
            'id': ORG_ID, 'name': 'Almaty', 'slug': 'almaty',
            'contact_email': 'director@almaty.com',
            'primary_color': '#0066ff', 'logo_url': '',
            'onboarding_checklist': None,
        }
        with patch.object(svc, 'fetch_due', return_value=[row]), \
             patch.object(svc, '_get_org_with_director', return_value=org), \
             patch.object(svc, 'mark_sent') as ms, \
             patch.object(svc, 'mark_error') as me, \
             patch('services.email._post_json', return_value={}):
            summary = svc.send_due()
            assert summary['sent'] == 1
            assert summary['errored'] == 0
            ms.assert_called_once_with('r1')
            me.assert_not_called()

    def test_skips_day3_when_checklist_complete(self):
        row = {
            'id': 'r2', 'kind': 'nudge_day3', 'org_id': ORG_ID,
            'scheduled_for': datetime.now(timezone.utc).isoformat(),
            'sent_at': None,
        }
        org = {
            'id': ORG_ID, 'name': 'Almaty', 'slug': 'almaty',
            'contact_email': 'director@almaty.com',
            'primary_color': '#0066ff', 'logo_url': '',
            'onboarding_checklist': {'all_completed': True},
        }
        with patch.object(svc, 'fetch_due', return_value=[row]), \
             patch.object(svc, '_get_org_with_director', return_value=org), \
             patch.object(svc, 'mark_sent') as ms, \
             patch.object(svc, 'mark_error') as me:
            summary = svc.send_due()
            assert summary['skipped'] == 1
            assert summary['sent'] == 0
            # skipped → still marks sent (so it doesn't re-fire)
            ms.assert_called_once_with('r2')
            me.assert_not_called()

    def test_marks_error_when_send_fails(self):
        row = {
            'id': 'r3', 'kind': 'welcome_day1', 'org_id': ORG_ID,
            'scheduled_for': datetime.now(timezone.utc).isoformat(),
            'sent_at': None,
        }
        org = {
            'id': ORG_ID, 'name': 'Almaty', 'slug': 'almaty',
            'contact_email': 'director@almaty.com',
            'primary_color': '#0066ff', 'logo_url': '',
            'onboarding_checklist': None,
        }

        def boom(*a, **kw):
            raise RuntimeError('Resend exploded')

        with patch.object(svc, 'fetch_due', return_value=[row]), \
             patch.object(svc, '_get_org_with_director', return_value=org), \
             patch.object(svc, 'mark_sent') as ms, \
             patch.object(svc, 'mark_error') as me, \
             patch('services.email._post_json', side_effect=boom):
            summary = svc.send_due()
            assert summary['errored'] == 1
            me.assert_called_once()
            ms.assert_not_called()


# ─── Should-skip predicate ───────────────────────────────────────────────


class TestShouldSkip:
    def test_skips_day3_when_all_completed(self):
        assert svc.should_skip(
            {'kind': 'nudge_day3'}, {'onboarding_checklist': {'all_completed': True}},
        )

    def test_does_not_skip_day3_when_pending(self):
        assert not svc.should_skip(
            {'kind': 'nudge_day3'}, {'onboarding_checklist': {'all_completed': False}},
        )

    def test_does_not_skip_other_kinds_blindly(self):
        assert not svc.should_skip(
            {'kind': 'welcome_day1'}, {'onboarding_checklist': {'all_completed': True}},
        )

    def test_handles_missing_checklist_field(self):
        assert not svc.should_skip({'kind': 'nudge_day3'}, {})


# ─── Subject lines ───────────────────────────────────────────────────────


class TestSubjects:
    def test_subjects_include_school_name(self):
        for kind in ('welcome_day1', 'nudge_day3', 'success_day7'):
            s = svc._subject_for(kind, {'name': 'Almaty'})
            assert 'Almaty' in s

    def test_custom_domain_subjects_distinct(self):
        active = svc._subject_for('custom_domain_active', {'name': 'X'})
        failed = svc._subject_for('custom_domain_failed', {'name': 'X'})
        assert active != failed
