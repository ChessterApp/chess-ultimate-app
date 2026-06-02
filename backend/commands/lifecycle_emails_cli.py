"""Flask CLI commands for the lifecycle-email scheduler (PRD §11.2 #6).

Register with::

    from commands.lifecycle_emails_cli import register_cli
    register_cli(app)

Then run from cron::

    flask lifecycle-emails send-due
"""

from __future__ import annotations

import click
from flask.cli import AppGroup

from services import lifecycle_emails as svc


lifecycle_group = AppGroup('lifecycle-emails', help='Lifecycle email scheduler.')


@lifecycle_group.command('send-due')
@click.option('--limit', default=100, show_default=True,
              help='Maximum number of rows to attempt per run.')
def send_due_cmd(limit: int) -> None:
    """Send all lifecycle emails whose scheduled_for is now or earlier."""
    summary = svc.send_due(limit=limit)
    click.echo(
        f"sent={summary['sent']} skipped={summary['skipped']} "
        f"errored={summary['errored']}"
    )


@lifecycle_group.command('schedule-for-org')
@click.argument('org_id')
def schedule_for_org_cmd(org_id: str) -> None:
    """Schedule the standard day-1/3/7 emails for an org."""
    rows = svc.schedule_for_org(org_id)
    click.echo(f"scheduled {len(rows)} rows for org={org_id}")


def register_cli(app) -> None:
    app.cli.add_command(lifecycle_group)
