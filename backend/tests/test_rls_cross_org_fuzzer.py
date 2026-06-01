"""
Introspection-driven cross-org RLS fuzzer (ADR-0005 follow-up).

The existing backend/tests/test_rls_isolation.py exhaustively tests cross-org
SELECT / UPDATE / DELETE for a *hardcoded* list of multi-tenant tables. That
suite is the human-readable inventory of the white-label schema, but it has
one structural blind spot: when someone adds a new table with an
`organization_id` column and forgets to enable RLS or define a policy, the
existing suite will NOT catch it — the new table simply is not in any of the
parametrize lists, so nothing is checked.

This fuzzer is the regression net for that gap. Tables are discovered from
`information_schema.columns`; four properties are asserted on every one:

  1. RLS enabled — pg_class.relrowsecurity must be true. Catches the
     "added an org_id column, forgot ALTER TABLE … ENABLE RLS" footgun.
  2. Policy presence — at least one row in pg_policies on the table must
     reference `organization_id` or `is_org_member`. RLS-enabled without
     an org-scoping policy effectively denies all reads; RLS-enabled with
     only role-blind policies silently leaks across orgs.
  3. Cross-org CUD isolation — an authed user from org-A must not see,
     update, or delete any row owned by org-B. Probe rows come from the
     `tenants` fixture when the table is known; for newly-discovered
     tables, a probe row is inserted as the superuser (BYPASSRLS) and
     cleaned up in a finally block.
  4. Drift detector (soft fail) — emits a UserWarning if discovery finds
     tables that are not in the hardcoded ORG_SCOPED list in
     test_rls_isolation.py. Does NOT hard-fail: the fuzzer is the safety
     net, the hardcoded list is the human inventory, and keeping the two
     in sync is a maintainer task we surface but do not block on.

Skips cleanly with the same SUPABASE_DB_URL gate used by test_rls_isolation.
"""

from __future__ import annotations

import warnings

import psycopg2
import pytest

# Reuse the connection plumbing, role helpers, and shared `tenants` fixture
# from the existing isolation suite. `open_conn` / `set_role` / `can_connect`
# are public re-exports added at the bottom of test_rls_isolation.py for this
# fuzzer — semantics are unchanged, only the names are exposed.
from tests.test_rls_isolation import (  # noqa: F401  — `tenants` is used as a fixture
    ORG_SCOPED,
    _DB_URL,
    authed,
    can_connect,
    open_conn,
    tenants,
)


pytestmark = pytest.mark.skipif(
    not _DB_URL or not can_connect(),
    reason=(
        "Live Supabase DB unreachable. Set SUPABASE_DB_URL (or DATABASE_URL, "
        "or SUPABASE_DB_PASSWORD + SUPABASE_PROJECT_REF) in backend/.env."
    ),
)


# ─── Discovery ──────────────────────────────────────────────────────────────


def _discover_org_scoped_tables() -> list[str]:
    """Every public.* base table that has a column named `organization_id`,
    minus throwaway tables created by RLS fixtures."""
    conn = open_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema
             AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND c.column_name = 'organization_id'
              AND t.table_type = 'BASE TABLE'
            ORDER BY c.table_name
            """
        )
        return [
            row[0] for row in cur.fetchall()
            if not row[0].startswith("rls_test_")
        ]
    finally:
        conn.close()


# Discovery runs at import time so pytest can parametrize over the result.
# If the DB is unreachable, pytestmark skips the whole module before any test
# body runs; we still guard against import-time errors to keep collection
# side-effect-free in adversarial environments.
try:
    DISCOVERED: list[str] = (
        _discover_org_scoped_tables() if can_connect() else []
    )
except Exception:  # noqa: BLE001
    DISCOVERED = []


# ─── Assertion 1: RLS enabled on every discovered table ────────────────────


@pytest.mark.parametrize("table", DISCOVERED)
def test_discovered_table_has_rls_enabled(table: str) -> None:
    """Coverage gate. If someone adds an `organization_id` column and forgets
    `ALTER TABLE … ENABLE ROW LEVEL SECURITY`, this names the table and fails.
    That is the entire reason this fuzzer exists."""
    conn = open_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = %s
            """,
            (table,),
        )
        row = cur.fetchone()
        assert row is not None, f"Table {table} unexpectedly missing from pg_class"
        assert row[0] is True, (
            f"RLS NOT enabled on org-scoped table `{table}`. "
            f"Add `ALTER TABLE {table} ENABLE ROW LEVEL SECURITY` "
            f"to a migration before onboarding another org."
        )
    finally:
        conn.close()


# ─── Assertion 2: at least one org-scoping policy on every table ───────────


@pytest.mark.parametrize("table", DISCOVERED)
def test_discovered_table_has_org_scoped_policy(table: str) -> None:
    """RLS enabled with zero policies = denies all; RLS with only role-blind
    policies = silently leaks across orgs. Either way is broken. Require at
    least one policy that references organization_id or is_org_member."""
    conn = open_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT policyname,
                   COALESCE(qual, '') || ' ' || COALESCE(with_check, '') AS expr
            FROM pg_policies
            WHERE schemaname = 'public' AND tablename = %s
            """,
            (table,),
        )
        policies = cur.fetchall()
        assert policies, (
            f"Table `{table}` has RLS enabled but ZERO policies — RLS is "
            f"deny-all without a policy. Add at least one org-scoping policy."
        )
        relevant = [
            name for name, expr in policies
            if "organization_id" in expr or "is_org_member" in expr
        ]
        assert relevant, (
            f"Table `{table}` has policies but NONE reference "
            f"`organization_id` or `is_org_member`. Existing policies "
            f"({[p[0] for p in policies]}) appear to be role-blind, which "
            f"silently leaks cross-org rows. Add an org-scoping policy."
        )
    finally:
        conn.close()


# ─── Assertion 3: cross-org SELECT / UPDATE / DELETE all affect zero rows ──


def _probe_row(table: str, tenants_state: dict) -> tuple[str, bool]:
    """Return (row_id, inserted_by_fuzzer).

    Prefers the `tenants` fixture's pre-seeded org-B row when available.
    For newly-discovered tables not covered by the fixture, inserts a
    minimal probe row as the superuser (BYPASSRLS) — the caller is
    responsible for deleting it via _delete_probe()."""
    rows = tenants_state["rows"].get(table)
    if rows is not None:
        return rows["b"], False

    conn = open_conn()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {table} (organization_id) VALUES (%s) RETURNING id",
            (tenants_state["org_b_id"],),
        )
        return str(cur.fetchone()[0]), True
    finally:
        conn.close()


def _delete_probe(table: str, row_id: str) -> None:
    conn = open_conn()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table} WHERE id = %s", (row_id,))
    finally:
        conn.close()


def _affected(conn, sql: str, params: tuple) -> int:
    """Run DML, return rowcount, treat policy errors as 'isolation held' (0)."""
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return cur.rowcount
    except psycopg2.Error:
        conn.rollback()
        return 0


@pytest.mark.parametrize("table", DISCOVERED)
def test_cross_org_cud_isolation(tenants, table: str) -> None:
    """Org-A authed user must not SELECT, UPDATE, or DELETE org-B's row.

    Fixture-seeded rows are reused; newly-discovered tables get a probe
    row inserted (and cleaned up) by this test. A NOT NULL constraint
    that blocks the minimal probe insert is reported as a skip — the
    coverage assertions (1 and 2) still hold for that table, and the
    next maintainer can add it to the `tenants` fixture properly."""
    try:
        org_b_row, inserted = _probe_row(table, tenants)
    except psycopg2.Error as exc:
        pytest.skip(
            f"Could not seed probe row in `{table}` (likely NOT NULL "
            f"columns beyond organization_id): {exc}. Add `{table}` to the "
            f"`tenants` fixture in test_rls_isolation.py to cover it. "
            f"Assertions 1 & 2 still verified this table."
        )

    try:
        with authed(tenants["owner_a"]) as conn:
            cur = conn.cursor()

            # SELECT must see zero rows.
            try:
                cur.execute(
                    f"SELECT 1 FROM {table} WHERE id = %s", (org_b_row,)
                )
                seen = cur.fetchall()
            except psycopg2.Error:
                conn.rollback()
                seen = []
            assert seen == [], (
                f"RLS leak: org-A user SELECTed org-B's row in `{table}` "
                f"(id={org_b_row})"
            )

            # UPDATE must affect zero rows.
            affected = _affected(
                conn,
                f"UPDATE {table} SET id = id WHERE id = %s",
                (org_b_row,),
            )
            assert affected == 0, (
                f"RLS leak: org-A UPDATE on `{table}` touched {affected} "
                f"row(s) of org-B (id={org_b_row})"
            )

            # DELETE must affect zero rows. (Transaction rolls back on exit,
            # so a successful DELETE would not persist — but it's still a leak.)
            affected = _affected(
                conn,
                f"DELETE FROM {table} WHERE id = %s",
                (org_b_row,),
            )
            assert affected == 0, (
                f"RLS leak: org-A DELETE on `{table}` would have removed "
                f"{affected} row(s) of org-B (id={org_b_row})"
            )
    finally:
        if inserted:
            try:
                _delete_probe(table, org_b_row)
            except Exception as exc:  # noqa: BLE001
                # Never let cleanup mask the real test outcome.
                print(f"[fuzzer cleanup] {table}/{org_b_row}: {exc}")


# ─── Assertion 4: drift detector — warn (don't fail) on uncovered tables ───


def test_drift_against_hardcoded_org_scoped_list() -> None:
    """Soft fail: emit a warning if discovery finds org-scoped tables that
    the hardcoded ORG_SCOPED tuple in test_rls_isolation.py does not list.

    Rationale: the fuzzer is self-updating and is the actual regression
    net. The hardcoded list is the human-readable inventory used for
    exhaustive per-role tests. Keeping them in sync is a maintainer
    task — we surface it as a warning so the fuzzer itself never
    requires manual upkeep to keep passing."""
    missing = sorted(set(DISCOVERED) - set(ORG_SCOPED))
    if missing:
        warnings.warn(
            "Cross-org fuzzer found org-scoped tables not in "
            f"test_rls_isolation.ORG_SCOPED: {missing}. Add them to that "
            "tuple (and seed rows in the `tenants` fixture) so the "
            "human-readable isolation suite covers them too.",
            UserWarning,
            stacklevel=2,
        )
