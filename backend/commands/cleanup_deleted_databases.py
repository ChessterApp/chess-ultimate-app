"""Hard-delete user_databases rows soft-deleted more than 30 days ago.

Databases are soft-deleted (deleted_at) for a 30-day recovery window (see
api/user_databases.py). Once that window lapses they are permanently removed,
together with the games that rode along into them.

Safe to run repeatedly: it only ever acts on rows whose deleted_at is older than
the cutoff, so a second run in the same window is a no-op.

Run from cron::

    cd /root/chess-app/backend
    flask databases cleanup-deleted

or standalone::

    python3 -m commands.cleanup_deleted_databases
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import click
from flask.cli import AppGroup

from services.supabase_client import supabase

logger = logging.getLogger(__name__)

DATABASES_TABLE = 'user_databases'
GAMES_TABLE = 'user_games'

# Must match RETENTION_DAYS in api/user_databases.py.
RETENTION_DAYS = 30


def _parse_ts(value):
    """Parse an ISO timestamp (tolerating a trailing 'Z') into an aware datetime,
    or None if it can't be parsed."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def cleanup_deleted_databases(now=None):
    """Permanently remove databases soft-deleted before now - RETENTION_DAYS.

    For each expired database the associated user_games (FK database_id) are
    deleted first to avoid orphan rows / FK violations, then the database row
    itself. Returns a summary dict ``{'databases': N, 'games': M}``.

    ``now`` is injectable for tests; defaults to the current UTC time.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)

    result = supabase.table(DATABASES_TABLE) \
        .select('id, deleted_at') \
        .not_.is_('deleted_at', 'null') \
        .lt('deleted_at', cutoff.isoformat()) \
        .execute()

    # Re-check the cutoff in Python so the result is correct even under a
    # filter-agnostic mock (mirrors the API's defensive style).
    expired_ids = []
    for row in result.data or []:
        deleted_at = _parse_ts(row.get('deleted_at'))
        if deleted_at is None:
            continue
        if deleted_at < cutoff:
            expired_ids.append(row['id'])

    games_deleted = 0
    for db_id in expired_ids:
        games = supabase.table(GAMES_TABLE) \
            .delete() \
            .eq('database_id', db_id) \
            .execute()
        games_deleted += len(games.data or [])

        supabase.table(DATABASES_TABLE) \
            .delete() \
            .eq('id', db_id) \
            .execute()

    summary = {'databases': len(expired_ids), 'games': games_deleted}
    logger.info(f"cleaned {summary['databases']} databases, {summary['games']} games")
    return summary


databases_group = AppGroup('databases', help='User-database maintenance.')


@databases_group.command('cleanup-deleted')
def cleanup_deleted_cmd() -> None:
    """Hard-delete databases soft-deleted more than 30 days ago."""
    summary = cleanup_deleted_databases()
    click.echo(f"cleaned {summary['databases']} databases, {summary['games']} games")


def register_cli(app) -> None:
    app.cli.add_command(databases_group)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    result = cleanup_deleted_databases()
    print(f"cleaned {result['databases']} databases, {result['games']} games")
