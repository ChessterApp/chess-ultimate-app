#!/usr/bin/env python3
"""
Run SQL migrations against the Supabase database.

Usage:
    # With DATABASE_URL env var:
    DATABASE_URL=postgresql://... python run_migration_direct.py 012_create_user_chess_profiles.sql

    # With psql directly:
    psql $DATABASE_URL < 012_create_user_chess_profiles.sql

    # Via Supabase Dashboard:
    Copy the SQL file contents into the SQL Editor at:
    https://supabase.com/dashboard/project/qtzujwiqzbgyhdgulvcd/sql
"""

import os
import sys
import subprocess


def run_migration(sql_file: str):
    """Run a SQL migration file against the database."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print(f"No DATABASE_URL set. Please apply manually:")
        print(f"  psql $DATABASE_URL < {sql_file}")
        print(f"  Or paste into Supabase Dashboard SQL Editor")
        sys.exit(1)

    sql_path = os.path.join(os.path.dirname(__file__), sql_file)
    if not os.path.exists(sql_path):
        print(f"Migration file not found: {sql_path}")
        sys.exit(1)

    print(f"Running migration: {sql_file}")
    result = subprocess.run(
        ["psql", db_url, "-f", sql_path],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    print(f"Migration {sql_file} applied successfully.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_migration_direct.py <migration_file.sql>")
        sys.exit(1)
    run_migration(sys.argv[1])
