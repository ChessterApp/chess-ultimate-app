"""Time budget for the TWIC SQLite queries (a 42 GB database on the coach host).

A ``LIKE '%name%'`` search over the games table is a full scan — tens of seconds
on the production database, while the model waits and the student sees nothing
(the persona asks for master games on most turns). A progress handler aborts
the statement once the budget is spent; the tools then return an error the
model answers around. ``TWIC_QUERY_TIMEOUT_S`` changes the budget without a deploy.

The leading underscore keeps ``discover_and_register`` from importing this as a tool.
"""

import os
import sqlite3
import time

QUERY_TIMEOUT_S = float(os.environ.get("TWIC_QUERY_TIMEOUT_S", "3"))

TIMEOUT_ERROR = (
    "The master games database did not answer in time; "
    "answer without master-game data this turn."
)


def install_timeout(conn: sqlite3.Connection, seconds: float = QUERY_TIMEOUT_S) -> None:
    """Abort any statement on *conn* that runs past *seconds* from now."""
    started = time.monotonic()

    def _handler():
        return 1 if time.monotonic() - started > seconds else 0

    conn.set_progress_handler(_handler, 10_000)


def is_timeout(exc: BaseException) -> bool:
    """True for the error SQLite raises when the progress handler aborts a statement."""
    return isinstance(exc, sqlite3.OperationalError) and "interrupt" in str(exc).lower()
