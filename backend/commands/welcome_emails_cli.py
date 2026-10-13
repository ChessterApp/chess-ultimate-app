"""Flask CLI commands for the welcome drip (P4).

Register with::

    from commands.welcome_emails_cli import register_cli
    register_cli(app)

Then run from cron::

    flask welcome-emails send-due
"""

from __future__ import annotations

import click
from flask.cli import AppGroup

from services import welcome_drip as svc


welcome_group = AppGroup('welcome-emails', help='Welcome drip emails.')


@welcome_group.command('send-due')
@click.option('--limit', default=100, show_default=True,
              help='Maximum number of rows to attempt per run.')
def send_due_cmd(limit: int) -> None:
    """Send all welcome emails whose scheduled_for is now or earlier."""
    summary = svc.send_due(limit=limit)
    click.echo(' '.join(f'{k}={v}' for k, v in summary.items()))


@welcome_group.command('send-test')
@click.option('--to', 'to_email', required=True, help='Recipient address.')
@click.option('--locale', type=click.Choice(svc.LOCALES), default='en', show_default=True)
@click.option('--step', type=click.IntRange(1, 5), default=None,
              help='Send one step only (default: all five).')
@click.option('--first-name', default=None, help='Name used in the greeting.')
def send_test_cmd(to_email: str, locale: str, step: int | None, first_name: str | None) -> None:
    """Send rendered welcome emails to one address. Ignores
    WELCOME_DRIP_ENABLED and writes nothing to the database."""
    for n in ([step] if step else svc.STEPS):
        subject, html_body, unsub = svc.render_email(n, locale, first_name, to_email)
        resend_id = svc.send_email(to_email, subject, html_body, unsub)
        click.echo(f'step={n} locale={locale} resend_id={resend_id}')


def register_cli(app) -> None:
    app.cli.add_command(welcome_group)
