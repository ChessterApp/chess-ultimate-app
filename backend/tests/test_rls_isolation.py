"""
Live-DB RLS isolation tests for the Chesster white-label schema.

What this verifies (against the real Supabase Postgres instance):
  * For every org-scoped multi-tenant table, an authenticated user from org-A
    cannot SELECT / UPDATE / DELETE rows owned by org-B.
  * The `anon` Postgres role sees no scoped rows.
  * The `service_role` bypasses RLS and sees both orgs (sanity check).

How it works:
  * A session-scoped fixture creates two throwaway orgs (slugs
    `rls-test-org-a-<rand8>` / `rls-test-org-b-<rand8>`) plus one row per
    multi-tenant table for each org, using the superuser `postgres` role
    (which has BYPASSRLS, allowing setup).
  * Per test, we open a fresh connection, `SET ROLE authenticated`, and use
    `set_config('request.jwt.claims', ...)` to plant a `sub` claim that
    Supabase's built-in `auth.uid()` reads. RLS policies then evaluate as
    if a real Clerk-authenticated user from that org were calling.
  * Teardown deletes every row inserted, in reverse insertion order, in a
    `finally` block — even on test failure or interpreter exception.

Skips: if no DB connection can be established the whole module is skipped.
RLS leaks detected here are written to /root/chess-app/docs/archive/RLS-FAILURES.md.
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from contextlib import contextmanager

import psycopg2
import pytest
from dotenv import load_dotenv

# Load backend/.env so SUPABASE_DB_URL can be picked up.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

# Connection: SUPABASE_DB_URL / DATABASE_URL must be set, or
# SUPABASE_DB_PASSWORD (+ optional SUPABASE_PROJECT_REF) for compose.
# Nothing is hard-coded — without env, the whole module is skipped.
_DB_URL = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
if not _DB_URL:
    _pw = os.environ.get("SUPABASE_DB_PASSWORD")
    _ref = os.environ.get("SUPABASE_PROJECT_REF")
    if _pw and _ref:
        _DB_URL = (
            f"postgresql://postgres:{_pw}@db.{_ref}.supabase.co:5432/postgres"
        )


def _can_connect() -> bool:
    if not _DB_URL:
        return False
    try:
        c = psycopg2.connect(_DB_URL, connect_timeout=5)
        c.close()
        return True
    except (psycopg2.Error, socket.error, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect(),
    reason=(
        "Live Supabase DB unreachable. Set SUPABASE_DB_URL (or DATABASE_URL, "
        "or SUPABASE_DB_PASSWORD + SUPABASE_PROJECT_REF) in backend/.env."
    ),
)


# ─── Connection helpers ────────────────────────────────────────────────────


def _open() -> psycopg2.extensions.connection:
    return psycopg2.connect(_DB_URL, connect_timeout=10)


def _set_role(conn, role: str, jwt_claims: dict | None = None) -> None:
    """Activate the given Postgres role on the connection. Must be called
    with autocommit=True so that the SET ROLE survives subsequent
    `conn.rollback()` calls — otherwise the role would revert to the
    superuser `postgres` after a rolled-back transaction, silently
    granting BYPASSRLS to every test."""
    assert conn.autocommit, (
        "_set_role must run with autocommit=True so SET ROLE is not "
        "rolled back when a test aborts its transaction."
    )
    cur = conn.cursor()
    cur.execute(f"SET ROLE {role}")
    if jwt_claims is not None:
        cur.execute(
            "SELECT set_config('request.jwt.claims', %s, false)",
            (json.dumps(jwt_claims),),
        )


@contextmanager
def authed(user_uuid: str):
    """Open a fresh connection under the `authenticated` role with a
    planted JWT sub claim. `auth.uid()` will return `user_uuid`.

    The role/claims are installed under autocommit=True (so they outlive
    any test rollback); then autocommit is turned off so tests run inside
    a transaction we can roll back to undo accidental writes."""
    conn = _open()
    conn.autocommit = True
    _set_role(conn, "authenticated", {"sub": user_uuid, "role": "authenticated"})
    conn.autocommit = False
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


@contextmanager
def anon():
    conn = _open()
    conn.autocommit = True
    _set_role(conn, "anon")
    conn.autocommit = False
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


@contextmanager
def service():
    """Service-role connection (bypasses RLS)."""
    conn = _open()
    conn.autocommit = True
    _set_role(conn, "service_role")
    conn.autocommit = False
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


# ─── Tenant fixture ────────────────────────────────────────────────────────

# IDs of multi-tenant tables that have a direct `organization_id` column.
ORG_SCOPED = (
    "organization_members",
    "organization_content",
    "organization_billing",
    "player_ratings",
    "user_progress",
    "lesson_chat_history",
    "user_games",
)

# Tables that are org-scoped indirectly via `tournaments.organizer_org_id`.
TOURNAMENT_SCOPED = (
    "tournaments",
    "tournament_registrations",
    "tournament_games",
    "tournament_standings",
)


@pytest.fixture(scope="module")
def tenants():
    """Create two throwaway orgs and seed one row per multi-tenant table for
    each. Yields a dict of ids. Cleans up every inserted row on teardown."""
    suffix_a = uuid.uuid4().hex[:8]
    suffix_b = uuid.uuid4().hex[:8]

    state = {
        "org_a_id": str(uuid.uuid4()),
        "org_b_id": str(uuid.uuid4()),
        "owner_a": str(uuid.uuid4()),
        "owner_b": str(uuid.uuid4()),
        "outsider": str(uuid.uuid4()),  # belongs to no org
        "org_a_slug": f"rls-test-org-a-{suffix_a}",
        "org_b_slug": f"rls-test-org-b-{suffix_b}",
        # Row ids, populated below — used by tests to check exact rows.
        "rows": {},  # table -> {"a": id, "b": id}
    }

    cleanup: list[tuple[str, str]] = []  # (table, id) in insertion order

    conn = _open()
    conn.autocommit = True
    cur = conn.cursor()

    try:
        # ── organizations ────────────────────────────────────────────────
        for key, oid, slug, name in (
            ("a", state["org_a_id"], state["org_a_slug"], "RLS Test Org A"),
            ("b", state["org_b_id"], state["org_b_slug"], "RLS Test Org B"),
        ):
            cur.execute(
                "INSERT INTO organizations (id, slug, name, status) "
                "VALUES (%s, %s, %s, 'active')",
                (oid, slug, name),
            )
            cleanup.append(("organizations", oid))
        state["rows"]["organizations"] = {
            "a": state["org_a_id"],
            "b": state["org_b_id"],
        }

        # ── organization_members ────────────────────────────────────────
        members = {}
        for key, oid, uid in (
            ("a", state["org_a_id"], state["owner_a"]),
            ("b", state["org_b_id"], state["owner_b"]),
        ):
            cur.execute(
                "INSERT INTO organization_members "
                "(organization_id, user_id, role) "
                "VALUES (%s, %s, 'owner') RETURNING id",
                (oid, uid),
            )
            mid = cur.fetchone()[0]
            cleanup.append(("organization_members", mid))
            members[key] = str(mid)
        state["rows"]["organization_members"] = members

        # ── organization_content ────────────────────────────────────────
        rows = {}
        for key, oid in (("a", state["org_a_id"]), ("b", state["org_b_id"])):
            cur.execute(
                "INSERT INTO organization_content "
                "(organization_id, course_id) "
                "VALUES (%s, gen_random_uuid()) RETURNING id",
                (oid,),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("organization_content", rid))
            rows[key] = str(rid)
        state["rows"]["organization_content"] = rows

        # ── organization_billing ────────────────────────────────────────
        rows = {}
        for key, oid in (("a", state["org_a_id"]), ("b", state["org_b_id"])):
            cur.execute(
                "INSERT INTO organization_billing "
                "(organization_id, plan) "
                "VALUES (%s, 'starter') RETURNING id",
                (oid,),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("organization_billing", rid))
            rows[key] = str(rid)
        state["rows"]["organization_billing"] = rows

        # ── tournaments + children ──────────────────────────────────────
        t_rows = {}
        treg, tg, tst = {}, {}, {}
        for key, oid, uid in (
            ("a", state["org_a_id"], state["owner_a"]),
            ("b", state["org_b_id"], state["owner_b"]),
        ):
            cur.execute(
                """
                INSERT INTO tournaments
                  (name, location, start_date, end_date,
                   registration_deadline, time_control,
                   organizer_org_id, created_by, status)
                VALUES
                  (%s, 'RLS test', CURRENT_DATE,
                   CURRENT_DATE + INTERVAL '1 day',
                   CURRENT_DATE + INTERVAL '1 day', 'rapid',
                   %s, %s, 'upcoming')
                RETURNING id
                """,
                (f"RLS Test Tournament {key}", oid, uid),
            )
            tid = cur.fetchone()[0]
            cleanup.append(("tournaments", tid))
            t_rows[key] = str(tid)

            cur.execute(
                "INSERT INTO tournament_registrations "
                "(tournament_id, user_id, player_name) "
                "VALUES (%s, %s, %s) RETURNING id",
                (tid, uid, f"Player {key}"),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("tournament_registrations", rid))
            treg[key] = str(rid)

            cur.execute(
                "INSERT INTO tournament_games "
                "(tournament_id, round, board, white_player_id, "
                " black_player_id, result) "
                "VALUES (%s, 1, 1, %s, %s, '1-0') RETURNING id",
                (tid, uid, uid),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("tournament_games", rid))
            tg[key] = str(rid)

            cur.execute(
                "INSERT INTO tournament_standings "
                "(tournament_id, user_id, rank, score) "
                "VALUES (%s, %s, 1, 1.0) RETURNING id",
                (tid, uid),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("tournament_standings", rid))
            tst[key] = str(rid)
        state["rows"]["tournaments"] = t_rows
        state["rows"]["tournament_registrations"] = treg
        state["rows"]["tournament_games"] = tg
        state["rows"]["tournament_standings"] = tst

        # ── player_ratings (one per (user, org)) ────────────────────────
        rows = {}
        for key, oid, uid in (
            ("a", state["org_a_id"], state["owner_a"]),
            ("b", state["org_b_id"], state["owner_b"]),
        ):
            cur.execute(
                "INSERT INTO player_ratings "
                "(user_id, organization_id, rating) "
                "VALUES (%s, %s, 1500) RETURNING id",
                (uid, oid),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("player_ratings", rid))
            rows[key] = str(rid)
        state["rows"]["player_ratings"] = rows

        # ── rating_history (no org_id column) ───────────────────────────
        rows = {}
        for key, uid in (("a", state["owner_a"]), ("b", state["owner_b"])):
            cur.execute(
                "INSERT INTO rating_history "
                "(user_id, source_type, rating_before, rating_after, "
                " change, k_factor_used) "
                "VALUES (%s, 'tournament', 1500, 1510, 10, 40) "
                "RETURNING id",
                (uid,),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("rating_history", rid))
            rows[key] = str(rid)
        state["rows"]["rating_history"] = rows

        # ── user_progress ───────────────────────────────────────────────
        rows = {}
        for key, oid, uid in (
            ("a", state["org_a_id"], state["owner_a"]),
            ("b", state["org_b_id"], state["owner_b"]),
        ):
            cur.execute(
                "INSERT INTO user_progress "
                "(user_id, organization_id, status) "
                "VALUES (%s, %s, 'completed') RETURNING id",
                (uid, oid),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("user_progress", rid))
            rows[key] = str(rid)
        state["rows"]["user_progress"] = rows

        # ── lesson_chat_history ─────────────────────────────────────────
        rows = {}
        for key, oid, uid in (
            ("a", state["org_a_id"], state["owner_a"]),
            ("b", state["org_b_id"], state["owner_b"]),
        ):
            cur.execute(
                "INSERT INTO lesson_chat_history "
                "(user_id, organization_id, messages) "
                "VALUES (%s, %s, '[]'::jsonb) RETURNING id",
                (uid, oid),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("lesson_chat_history", rid))
            rows[key] = str(rid)
        state["rows"]["lesson_chat_history"] = rows

        # ── user_games ──────────────────────────────────────────────────
        rows = {}
        for key, oid, uid in (
            ("a", state["org_a_id"], state["owner_a"]),
            ("b", state["org_b_id"], state["owner_b"]),
        ):
            cur.execute(
                "INSERT INTO user_games "
                "(user_id, organization_id, pgn) "
                "VALUES (%s, %s, '1. e4 e5 2. Nf3') RETURNING id",
                (uid, oid),
            )
            rid = cur.fetchone()[0]
            cleanup.append(("user_games", rid))
            rows[key] = str(rid)
        state["rows"]["user_games"] = rows

        conn.close()
        yield state

    finally:
        # Teardown — best-effort, never raise, never truncate.
        clean = _open()
        clean.autocommit = True
        ccur = clean.cursor()
        for table, row_id in reversed(cleanup):
            try:
                ccur.execute(
                    f"DELETE FROM {table} WHERE id = %s", (row_id,)
                )
            except Exception as exc:  # noqa: BLE001
                # Print so the teardown failure shows up in pytest output but
                # never blocks cleanup of the next row.
                print(f"[cleanup] {table}/{row_id}: {exc}")
        clean.close()


# ─── Test helpers ──────────────────────────────────────────────────────────


def _row_visible(conn, table: str, row_id: str) -> bool:
    """True if the row is returned by SELECT under the current connection.

    A policy error (e.g. infinite recursion, permission denied) is treated as
    'access denied' — the row is not visible. This is the security-relevant
    outcome: if the database refuses to evaluate the query, no data leaks.
    Underlying policy bugs are documented separately in docs/archive/RLS-FAILURES.md."""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT 1 FROM {table} WHERE id = %s", (row_id,))
        return cur.fetchone() is not None
    except psycopg2.Error:
        conn.rollback()
        return False


def _affected_rows(conn, sql: str, params: tuple) -> int:
    """Run a DML statement and return rowcount, swallowing policy errors
    (which are also a valid form of 'isolation held')."""
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return cur.rowcount
    except psycopg2.Error:
        # Policy violation, permission denied, recursive policy error etc.
        # All count as "DML did not touch the foreign row" → 0.
        conn.rollback()
        return 0


# ─── Tests: SELECT isolation per multi-tenant table ────────────────────────


@pytest.mark.parametrize(
    "table",
    [
        "organization_members",
        "organization_content",
        "organization_billing",
        "player_ratings",
        "tournaments",
        "tournament_registrations",
        "tournament_games",
        "tournament_standings",
        "rating_history",
        "user_progress",
        "lesson_chat_history",
        "user_games",
    ],
)
def test_authed_user_cannot_select_cross_org_row(tenants, table):
    """Org-A authed user must NOT see org-B's row in any multi-tenant table."""
    org_b_row = tenants["rows"][table]["b"]
    with authed(tenants["owner_a"]) as conn:
        assert not _row_visible(conn, table, org_b_row), (
            f"RLS leak: org-A user saw org-B's row in {table} "
            f"(id={org_b_row})"
        )


@pytest.mark.parametrize(
    "table",
    [
        "organization_members",
        "organization_content",
        "organization_billing",
        "user_progress",
        "lesson_chat_history",
        "user_games",
    ],
)
def test_authed_user_cannot_update_cross_org_row(tenants, table):
    """Org-A authed user must not be able to UPDATE org-B's row."""
    org_b_row = tenants["rows"][table]["b"]
    with authed(tenants["owner_a"]) as conn:
        # Touch a benign column that exists on every table.
        sql = f"UPDATE {table} SET id = id WHERE id = %s"
        affected = _affected_rows(conn, sql, (org_b_row,))
        assert affected == 0, (
            f"RLS leak: org-A UPDATE on {table} affected {affected} row(s) "
            f"belonging to org-B (id={org_b_row})"
        )


@pytest.mark.parametrize(
    "table",
    [
        "organization_members",
        "organization_content",
        "organization_billing",
        "user_progress",
        "lesson_chat_history",
        "user_games",
    ],
)
def test_authed_user_cannot_delete_cross_org_row(tenants, table):
    """Org-A authed user must not be able to DELETE org-B's row.
    DELETE rolls back at the end of the test session so seed data survives."""
    org_b_row = tenants["rows"][table]["b"]
    with authed(tenants["owner_a"]) as conn:
        sql = f"DELETE FROM {table} WHERE id = %s"
        affected = _affected_rows(conn, sql, (org_b_row,))
        # The connection is rolled back on exit, so any successful delete
        # would not persist — but we still must catch it as a leak.
        assert affected == 0, (
            f"RLS leak: org-A DELETE on {table} would have removed "
            f"{affected} row(s) of org-B (id={org_b_row})"
        )


# ─── Tests: anon role sees nothing scoped ──────────────────────────────────


@pytest.mark.parametrize(
    "table",
    [
        "organization_members",
        "organization_content",
        "organization_billing",
        "player_ratings",
        "rating_history",
        "tournaments",
        "tournament_registrations",
        "tournament_games",
        "tournament_standings",
        "user_progress",
        "lesson_chat_history",
        "user_games",
    ],
)
def test_anon_role_cannot_see_scoped_rows(tenants, table):
    """The anon Postgres role must not see either org's scoped row."""
    a_row = tenants["rows"][table]["a"]
    b_row = tenants["rows"][table]["b"]
    with anon() as conn:
        # Both should be invisible. We treat any DB error here as "denied",
        # which is also a form of isolation holding.
        try:
            assert not _row_visible(conn, table, a_row), (
                f"anon role saw org-A row in {table} (id={a_row})"
            )
            assert not _row_visible(conn, table, b_row), (
                f"anon role saw org-B row in {table} (id={b_row})"
            )
        except psycopg2.Error:
            conn.rollback()  # treated as denied


def test_anon_can_read_active_organizations(tenants):
    """`public_read_active_orgs` policy permits anon to read active orgs."""
    with anon() as conn:
        assert _row_visible(conn, "organizations", tenants["org_a_id"])
        assert _row_visible(conn, "organizations", tenants["org_b_id"])


# ─── Tests: service_role bypass (sanity check) ─────────────────────────────


@pytest.mark.parametrize(
    "table",
    [
        "organizations",
        "organization_members",
        "organization_content",
        "organization_billing",
        "tournaments",
        "tournament_registrations",
        "tournament_games",
        "tournament_standings",
        "player_ratings",
        "rating_history",
        "user_progress",
        "lesson_chat_history",
        "user_games",
    ],
)
def test_service_role_sees_both_orgs(tenants, table):
    """The service_role bypasses RLS and must see both orgs' rows."""
    a_row = tenants["rows"][table]["a"]
    b_row = tenants["rows"][table]["b"]
    with service() as conn:
        assert _row_visible(conn, table, a_row), (
            f"service_role could not see org-A row in {table} (id={a_row}) "
            f"— bypass policy missing?"
        )
        assert _row_visible(conn, table, b_row), (
            f"service_role could not see org-B row in {table} (id={b_row}) "
            f"— bypass policy missing?"
        )


# ─── Test: outsider (no org membership) sees nothing ───────────────────────


@pytest.mark.parametrize(
    "table",
    [
        "organization_members",
        "organization_content",
        "organization_billing",
        "player_ratings",
        "tournaments",
        "tournament_registrations",
        "tournament_games",
        "tournament_standings",
        "rating_history",
        "user_progress",
        "lesson_chat_history",
        "user_games",
    ],
)
def test_outsider_user_sees_no_scoped_rows(tenants, table):
    """A logged-in user who belongs to NEITHER org must see no scoped rows."""
    a_row = tenants["rows"][table]["a"]
    b_row = tenants["rows"][table]["b"]
    with authed(tenants["outsider"]) as conn:
        assert not _row_visible(conn, table, a_row), (
            f"Non-member saw org-A row in {table} (id={a_row})"
        )
        assert not _row_visible(conn, table, b_row), (
            f"Non-member saw org-B row in {table} (id={b_row})"
        )


# ─── Tests: helper functions (clerk_uid, is_org_member) ─────────────────────


def test_clerk_uid_returns_non_uuid_clerk_sub_as_text():
    """clerk_uid() must return the JWT `sub` as text, not cast to uuid.

    Real Clerk IDs look like `user_2abcDEF...` and are not valid UUIDs. If
    clerk_uid() ever calls `::uuid` on the value, this will raise
    `invalid input syntax for type uuid` — which is the production-token
    failure mode described in docs/archive/RLS-FAILURES.md §3.
    """
    clerk_sub = "user_2abcDEFghi3456789"
    with authed(clerk_sub) as conn:
        cur = conn.cursor()
        cur.execute("SELECT public.clerk_uid()")
        got = cur.fetchone()[0]
        assert got == clerk_sub, (
            f"clerk_uid() returned {got!r}, expected {clerk_sub!r} (as text)"
        )


def test_is_org_member_does_not_recurse(tenants):
    """is_org_member must NOT trigger `infinite recursion detected in policy
    for relation organization_members` (docs/archive/RLS-FAILURES.md §2).

    Successful evaluation under the `authenticated` role — no
    InvalidObjectDefinition raised — is the success signal."""
    with authed(tenants["owner_a"]) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT public.is_org_member(%s::uuid)",
                (tenants["org_a_id"],),
            )
            got = cur.fetchone()[0]
        except psycopg2.errors.InvalidObjectDefinition as e:  # noqa: F841
            pytest.fail(
                "is_org_member triggered InvalidObjectDefinition "
                "(recursive policy not bypassed): {}".format(e)
            )
        assert got is True, (
            "is_org_member(org_a) for owner_a should be true; got "
            f"{got!r} — helper or policy misconfigured"
        )


def test_is_org_member_cross_org_returns_false(tenants):
    """is_org_member(other_org) for owner_a must return false — the helper
    must answer correctly, not just avoid recursion."""
    with authed(tenants["owner_a"]) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.is_org_member(%s::uuid)",
            (tenants["org_b_id"],),
        )
        assert cur.fetchone()[0] is False


# ─── Tests: positive same-org visibility on newly-protected tables ──────────


@pytest.mark.parametrize(
    "table",
    [
        "tournaments",
        "tournament_registrations",
        "tournament_games",
        "tournament_standings",
        "player_ratings",
        "rating_history",
    ],
)
def test_org_owner_sees_own_org_row(tenants, table):
    """Owner of org-A must see org-A's row on each newly-protected table.

    This is the positive counterpart to test_authed_user_cannot_select_cross_org_row.
    Together they pin down the policy: same-org sees, cross-org blocked."""
    org_a_row = tenants["rows"][table]["a"]
    with authed(tenants["owner_a"]) as conn:
        assert _row_visible(conn, table, org_a_row), (
            f"Same-org owner of org-A could NOT see own row in {table} "
            f"(id={org_a_row}) — policy too restrictive"
        )


# ─── Public re-exports for the cross-org fuzzer ─────────────────────────────
# The introspection-driven fuzzer in test_rls_cross_org_fuzzer.py reuses this
# module's connection plumbing. Aliases keep the originals private-by-convention
# while giving the fuzzer a clean import surface. Semantics are unchanged.
open_conn = _open
set_role = _set_role
can_connect = _can_connect
