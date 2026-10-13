"""Tests for backend.services.welcome_drip and the welcome-emails CLI (P4).

No real email is sent: Resend's HTTP layer (``services.email._post_json``) is
patched in every test that reaches it.
"""

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from flask import Flask

from services import welcome_drip as svc


NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('WELCOME_DRIP_ENABLED', '1')
    monkeypatch.setenv('RESEND_API_KEY', 're_test')
    monkeypatch.setenv('EMAIL_UNSUB_SECRET', 'unsub-secret')
    monkeypatch.delenv('WELCOME_FROM', raising=False)


def row(**over):
    base = {
        'id': 'r1', 'user_id': 'user_1', 'email': 'kid@x.io', 'first_name': 'Aru',
        'locale': 'en', 'step': 1, 'scheduled_for': (NOW - timedelta(minutes=5)).isoformat(),
        'sent_at': None, 'skipped_reason': None, 'attempts': 0,
    }
    base.update(over)
    return base


@pytest.fixture
def db():
    """Patch the DB helpers; ``updates`` records every update_row call."""
    state = {'rows': [], 'opted_out': set(), 'earlier_unsent': set(), 'updates': []}
    with patch.object(svc, 'fetch_due', side_effect=lambda now, limit: state['rows']), \
         patch.object(svc, 'opted_out_emails', side_effect=lambda emails: state['opted_out']), \
         patch.object(svc, 'has_unsent_earlier_step',
                      side_effect=lambda uid, step: (uid, step) in state['earlier_unsent']), \
         patch.object(svc, 'update_row',
                      side_effect=lambda rid, fields: state['updates'].append((rid, fields))):
        yield state


@pytest.fixture
def resend():
    with patch('services.email._post_json', return_value={'id': 're_123'}) as post:
        yield post


# ─── Flag + config guards ────────────────────────────────────────────────


class TestGuards:
    @pytest.mark.parametrize('value', [None, '', '0', 'true', '1 '])
    def test_flag_not_exactly_1_sends_nothing(self, monkeypatch, db, resend, value):
        if value is None:
            monkeypatch.delenv('WELCOME_DRIP_ENABLED')
        else:
            monkeypatch.setenv('WELCOME_DRIP_ENABLED', value)
        db['rows'] = [row()]
        assert svc.send_due(now=NOW) == {'disabled': True}
        resend.assert_not_called()
        assert db['updates'] == []

    def test_refuses_to_send_without_unsub_secret(self, monkeypatch, db, resend):
        monkeypatch.delenv('EMAIL_UNSUB_SECRET')
        db['rows'] = [row()]
        summary = svc.send_due(now=NOW)
        assert 'EMAIL_UNSUB_SECRET' in summary['error']
        resend.assert_not_called()
        assert db['updates'] == []


# ─── Skips ───────────────────────────────────────────────────────────────


class TestSkips:
    def test_opted_out(self, db, resend):
        db['rows'] = [row(email='Kid@X.io')]
        db['opted_out'] = {'kid@x.io'}
        summary = svc.send_due(now=NOW)
        assert summary['opted_out'] == 1
        assert db['updates'] == [('r1', {'skipped_reason': 'opted_out'})]
        resend.assert_not_called()

    def test_stale_more_than_48h_overdue(self, db, resend):
        db['rows'] = [row(scheduled_for=(NOW - timedelta(hours=49)).isoformat())]
        summary = svc.send_due(now=NOW)
        assert summary['stale'] == 1
        assert db['updates'] == [('r1', {'skipped_reason': 'stale'})]
        resend.assert_not_called()

    def test_47h_overdue_still_sends(self, db, resend):
        db['rows'] = [row(scheduled_for=(NOW - timedelta(hours=47)).isoformat())]
        assert svc.send_due(now=NOW)['sent'] == 1

    def test_out_of_order_sends_nothing_for_that_user(self, db, resend):
        db['rows'] = [
            row(id='a2', step=2),
            row(id='a3', step=3),
            row(id='b1', user_id='user_2', email='other@x.io'),
        ]
        db['earlier_unsent'] = {('user_1', 2)}
        summary = svc.send_due(now=NOW)
        assert summary['out_of_order'] == 2
        assert summary['sent'] == 1
        # Only user_2 got an email; user_1's rows stay due (no DB write).
        assert resend.call_count == 1
        assert resend.call_args[0][2]['to'] == ['other@x.io']
        assert [u[0] for u in db['updates']] == ['b1']


# ─── Send outcomes ───────────────────────────────────────────────────────


class TestSend:
    def test_success_writes_sent_at_and_resend_id(self, db, resend):
        db['rows'] = [row()]
        summary = svc.send_due(now=NOW)
        assert summary['sent'] == 1
        (rid, fields), = db['updates']
        assert rid == 'r1'
        assert fields['resend_id'] == 're_123'
        assert fields['sent_at']
        assert fields['error'] is None

    def test_request_shape_and_unsubscribe_headers(self, db, resend):
        db['rows'] = [row(locale='ru', step=2, first_name='Аня')]
        svc.send_due(now=NOW)
        url, headers, body = resend.call_args[0]
        assert url == 'https://api.resend.com/emails'
        assert headers['Authorization'] == 'Bearer re_test'
        assert body['from'] == 'Chesster <noreply@chesster.io>'
        assert body['to'] == ['kid@x.io']
        assert body['subject'] == svc.SUBJECTS['ru'][2]
        unsub = body['headers']['List-Unsubscribe']
        assert re.fullmatch(r'<https://api\.chesster\.io/api/email/unsubscribe\?t=[^>]+>', unsub)
        assert body['headers']['List-Unsubscribe-Post'] == 'List-Unsubscribe=One-Click'
        token = unsub[unsub.index('?t=') + 3:-1]
        assert svc.verify_unsubscribe_token(token) == 'kid@x.io'
        assert 'Привет, Аня!' in body['html']
        # Visible footer link too.
        assert 'Отписаться' in body['html'] and 'api/email/unsubscribe?t=' in body['html']

    def test_welcome_from_env(self, monkeypatch, db, resend):
        monkeypatch.setenv('WELCOME_FROM', 'Chesster <hi@chesster.io>')
        db['rows'] = [row()]
        svc.send_due(now=NOW)
        assert resend.call_args[0][2]['from'] == 'Chesster <hi@chesster.io>'

    def test_failure_increments_attempts_and_stays_unsent(self, db, resend):
        resend.side_effect = OSError('timeout')
        db['rows'] = [row(attempts=0)]
        summary = svc.send_due(now=NOW)
        assert summary['errored'] == 1
        (rid, fields), = db['updates']
        assert fields['attempts'] == 1
        assert 'timeout' in fields['error']
        assert 'skipped_reason' not in fields
        assert 'sent_at' not in fields

    def test_gives_up_after_third_failure(self, db, resend):
        resend.side_effect = OSError('timeout')
        db['rows'] = [row(attempts=2)]
        summary = svc.send_due(now=NOW)
        assert summary['failed'] == 1
        (_, fields), = db['updates']
        assert fields['attempts'] == 3
        assert fields['skipped_reason'] == 'failed'

    def test_failure_holds_later_steps_for_that_user(self, db, resend):
        resend.side_effect = OSError('timeout')
        db['rows'] = [row(id='a1', step=1), row(id='a2', step=2)]
        summary = svc.send_due(now=NOW)
        assert resend.call_count == 1
        assert summary['out_of_order'] == 1
        assert [u[0] for u in db['updates']] == ['a1']


# ─── Templates ───────────────────────────────────────────────────────────


class TestTemplates:
    @pytest.mark.parametrize('locale', svc.LOCALES)
    @pytest.mark.parametrize('step', svc.STEPS)
    def test_all_15_render_without_leftover_placeholders(self, locale, step):
        subject, html, unsub = svc.render_email(step, locale, None, 'kid@x.io')
        assert subject == svc.SUBJECTS[locale][step]
        assert '{{' not in html and '}}' not in html
        assert svc.GREETINGS[locale][1] in html
        assert 'https://chesster.io/static/images/chesster-logo-v3.png' in html
        assert 'Chesster · <a href="https://chesster.io"' in html
        assert svc.FOOTER[locale]['unsubscribe'] in html
        assert 'href="https://chesster.io/' in html  # CTA to a real page
        assert 'fox' not in html.lower()

    def test_greeting_uses_first_name_and_escapes_it(self):
        assert svc.greeting('en', 'Sam') == 'Hi Sam,'
        assert svc.greeting('en', '  ') == 'Hi there,'
        assert svc.greeting('kk', None) == 'Сәлем!'
        assert svc.greeting('en', '<b>x</b>') == 'Hi &lt;b&gt;x&lt;/b&gt;,'

    def test_unknown_locale_falls_back_to_en(self):
        subject, _, _ = svc.render_email(1, 'de', None, 'kid@x.io')
        assert subject == svc.SUBJECTS['en'][1]


class TestTokens:
    def test_round_trip_lowercases(self):
        assert svc.verify_unsubscribe_token(svc.make_unsubscribe_token('Kid@X.io')) == 'kid@x.io'

    @pytest.mark.parametrize('token', [None, '', 'abc', 'a.b.c', 'a.b'])
    def test_garbage_rejected(self, token):
        assert svc.verify_unsubscribe_token(token) is None

    def test_tampered_or_other_secret_rejected(self, monkeypatch):
        token = svc.make_unsubscribe_token('kid@x.io')
        payload, sig = token.split('.')
        forged = svc._b64(b'boss@x.io') + '.' + sig
        assert svc.verify_unsubscribe_token(forged) is None
        monkeypatch.setenv('EMAIL_UNSUB_SECRET', 'other')
        assert svc.verify_unsubscribe_token(token) is None


# ─── CLI ─────────────────────────────────────────────────────────────────


@pytest.fixture
def cli_app():
    from commands.welcome_emails_cli import register_cli
    app = Flask(__name__)
    register_cli(app)
    return app


class TestCli:
    def test_send_test_ignores_flag_and_never_touches_db(self, monkeypatch, cli_app, resend):
        monkeypatch.setenv('WELCOME_DRIP_ENABLED', '0')
        with patch.object(svc, '_supabase', side_effect=AssertionError('DB touched')) as sb:
            result = cli_app.test_cli_runner().invoke(
                args=['welcome-emails', 'send-test', '--to', 'me@x.io', '--locale', 'kk'],
            )
        assert result.exit_code == 0, result.output
        sb.assert_not_called()
        assert resend.call_count == 5
        subjects = [c[0][2]['subject'] for c in resend.call_args_list]
        assert subjects == [svc.SUBJECTS['kk'][n] for n in svc.STEPS]
        assert all(c[0][2]['to'] == ['me@x.io'] for c in resend.call_args_list)

    def test_send_test_single_step(self, cli_app, resend):
        with patch.object(svc, '_supabase', side_effect=AssertionError('DB touched')):
            result = cli_app.test_cli_runner().invoke(
                args=['welcome-emails', 'send-test', '--to', 'me@x.io',
                      '--locale', 'ru', '--step', '3'],
            )
        assert result.exit_code == 0, result.output
        assert resend.call_count == 1
        assert resend.call_args[0][2]['subject'] == svc.SUBJECTS['ru'][3]

    def test_send_due_prints_summary(self, monkeypatch, cli_app):
        monkeypatch.setenv('WELCOME_DRIP_ENABLED', '0')
        result = cli_app.test_cli_runner().invoke(args=['welcome-emails', 'send-due'])
        assert result.exit_code == 0
        assert 'disabled=True' in result.output
