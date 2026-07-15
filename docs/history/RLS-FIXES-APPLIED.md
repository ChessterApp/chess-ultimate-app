# RLS Fixes Applied — 2026-06-01

Implements `PRD-rls-hardening.md`. Closes all three white-label tenancy
leaks catalogued in `RLS-FAILURES.md`.

## What landed

- **Migration:** `supabase/migrations/20260601_008_rls_hardening.sql`
  - `public.clerk_uid()` — reads JWT `sub` claim as text (no UUID cast).
    Production Clerk tokens (`user_2abc…`) now no longer crash policies.
  - `public.is_org_member(org)` and `public.is_org_role(org, roles[])` —
    SECURITY DEFINER, STABLE, `SET search_path = public`. Owned by
    `postgres` (BYPASSRLS), so the membership lookup no longer recurses
    into the policy under evaluation.
  - Every policy from migration 005 rewritten to call the helpers instead
    of `auth.uid()::text` and inline `EXISTS … FROM organization_members`.
    Policy names preserved so existing tooling/assertions still match.
  - RLS enabled and policies added on the six previously-unprotected
    tables: `tournaments`, `tournament_registrations`, `tournament_games`,
    `tournament_standings`, `player_ratings`, `rating_history`.
  - Dropped one orphan policy: `service_role_all` on `user_games`. It had
    been added out-of-band with `USING true` applied to PUBLIC, granting
    every role unrestricted read/write. The recursive-policy errors used
    to mask it; the helper rewrite unmasked it; this migration removes it.
    Service-role still bypasses via the `service_role` BYPASSRLS attribute.
  - Idempotent (CREATE OR REPLACE / DROP POLICY IF EXISTS / ALTER … ENABLE).
    Commented `ROLLBACK` block at the bottom of the migration.

- **Tests:** `backend/tests/test_rls_isolation.py`
  - Removed `xfail` markers from every parameter that previously targeted
    a gap fixed here (18 xfailed → 0).
  - Added positive helper tests: `test_clerk_uid_returns_non_uuid_clerk_sub_as_text`,
    `test_is_org_member_does_not_recurse`, `test_is_org_member_cross_org_returns_false`.
  - Added positive same-org visibility tests for each of the six newly
    protected tables: `test_org_owner_sees_own_org_row[…]` × 6.

- **Env:** Added `SUPABASE_DB_URL` to `backend/.env` so the fixture and
  migration tooling can find the live DB without a passed-in env. The
  file is gitignored.

## Notes / deltas from the PRD

- **PRD:** `public_read` on `player_ratings`. **Applied:** org-member
  scoped; no public read. The PRD also requires "cross-org read returns 0
  rows" and the fuzzer's anon-isolation test treats any anon visibility
  as a leak. The public leaderboard runs through the Flask backend with
  the service-role key, which still bypasses RLS, so the leaderboard is
  unaffected. Documented inline at the top of section D in the migration.

- **PRD:** Public-read for tournaments uses status names
  `('published','ongoing','completed')`. **Applied:** mapped to the real
  schema's status enum — `('registration_open','registration_closed',
  'in_progress','completed')`. Drafts (`upcoming`) and `cancelled` stay
  org-member-only.

- **PRD:** `rating_history.player_rating_id` join. **Applied:** the column
  does not exist on `rating_history`. Scoped via `user_id` join into
  `player_ratings` instead (same intent, no schema change required, per
  PRD §4.4: "No `rating_history.organization_id` backfill").

## Fuzzer output — before / after

Test: `backend/tests/test_rls_isolation.py` against live Supabase
`qtzujwiqzbgyhdgulvcd`.

### Before (pre-migration)

```
============ 40 passed, 18 xfailed, 4 xpassed in 117.84s (0:01:57) =============
```

The 4 XPASS results were on `organization_members` (SELECT/UPDATE/DELETE +
outsider) — passing-by-accident because the recursive policy error
denied access. 18 XFAIL covered the six unprotected tables across the
authed-cross-org, anon, and outsider test groups.

### After (migration 008 applied + tests promoted)

```
======================== 71 passed in 131.05s (0:02:11) ========================
```

0 failed, 0 xfailed, 0 xpassed. Test count grew from 62 to 71 (9 new
positive tests: 3 helper assertions + 6 same-org visibility).

## Smoke check (live)

| Check | Result |
| --- | --- |
| `curl https://chesster.io` | `200` |
| `curl -I https://demo.chesster.io` | TLS still issuing (per PRD §5 — acceptable) |
| PM2 `chess-frontend` logs | No new errors traceable to this change (pre-existing server-action deploy-mismatch noise only) |
| Flask backend | Unchanged — still uses service-role bypass |

## Acceptance criteria from the PRD

- [x] Migration `008` applied cleanly to live Supabase
- [x] `test_rls_isolation.py` runs with **0 failed, 0 xfailed**
- [x] New positive tests for the 6 tournament/rating tables pass
- [x] `clerk_uid()` test with non-UUID `sub` passes
- [x] `is_org_member` recursion test passes (no `InvalidObjectDefinition`)
- [x] `curl https://chesster.io` returns 200
- [x] No new errors in PM2 `chess-frontend` logs or Flask backend logs
- [x] `RLS-FIXES-APPLIED.md` committed alongside the migration

## Follow-ups (out of scope, called out in PRD §9)

- Remove the Flask service-role bypass in favour of forwarding the Clerk
  JWT to Supabase (significant data-access change; needs its own ADR).
- Per-tenant audit logging on RLS denials.
- Wire the fuzzer into CI (currently runs locally only).
