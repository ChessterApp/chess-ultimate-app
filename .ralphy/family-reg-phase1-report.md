# Family Registration — Phase 1 Report

Backend multi-link support + validated tournament register/cancel route. UI picker
is deferred to Phase 2 as specified. Zero Chess Empire-side changes.

## What changed

### 1. Migration (file only — NOT applied anywhere)
`supabase/migrations/20260917_040_family_relationship.sql`
- `ALTER TABLE organization_members ADD COLUMN IF NOT EXISTS relationship text NOT NULL DEFAULT 'self'`.
- Named `CHECK (relationship IN ('self','child','other'))` constraint (dropped-if-exists then
  re-added, so re-running is idempotent). Plain CHECK — the table is small, no NOT VALID/VALIDATE split.
- `COMMENT ON COLUMN` explaining self = account owner is the student; child/other = guardian-managed.

**Path note:** the brief specified `frontend/supabase/migrations/`, but that directory does not
exist. The real migrations live at the **repo root** `supabase/migrations/` (latest before this was
`20260914_039_wheel_presets.sql`), which matches the project's memory note. The file was placed there.

### 2. `frontend/src/lib/chess-empire-member.ts` — multi-member support
- Added `relationship` to `SELECT_COLUMNS`, `MemberRow`, and a new
  `relationship: 'self' | 'child' | 'other'` field on `MembershipStateResult`
  (new exported `MemberRelationship` type). `coerceRelationship()`: null/missing → `'self'`,
  known value passes through, anything else → `'other'`.
- New `fetchMemberRows()` helper fetches **ALL** of a user's rows (no `.limit(1)`), ordered by
  `id` ascending. Ordering rationale: `organization_members` has **no `created_at` column**
  (it has `joined_at`, but the brief's `created_at`-or-`id` rule + safety against a query error
  on a non-existent column made `id` the correct deterministic choice). Documented in-code.
- New exported `getVerifiedMembersForUser(clerkUserId)` (wrapped in `cache()`): maps all rows
  through the existing row→state logic and returns only `state === 'verified'` entries
  (per-row expiry applied, same as before).
- `getMembershipState` / `getMembershipStateForUser` / `getLinkedStudentId` now delegate to
  `fetchMemberRows` + a new **deterministic** `pickPrimaryState()`: a verified row beats
  pending_confirm; among verified, `relationship='self'` wins, then earliest (id order); with no
  verified/pending the earliest row's state stands (e.g. a lone expired row); empty → `no_link`.
  Behavior is identical for single-link users (one row → that row).

### 3. `frontend/src/app/api/chess-empire/tournaments/[id]/register/route.ts` — validated `student_id`
- POST and DELETE now resolve the caller's verified allowlist via `getVerifiedMembersForUser`
  and share one `resolveTargetStudent()` gate:
  - Unauthenticated → 401.
  - No verified members → 403 `forbidden`.
  - `student_id` present but NOT in the caller's verified set → 403 `{ error: 'forbidden_student' }`,
    and the CE client is **never** called.
  - `student_id` absent + exactly one verified member → uses it (unchanged single-link behavior).
  - `student_id` absent + 2+ members → 400 `{ error: 'student_required', message: 'Specify which family member to register.' }`.
- `readRequestedStudentId()` tolerates empty/absent/malformed bodies; reads JSON body for POST/DELETE
  and also `?student_id=` query param for DELETE.
- DELETE keeps the existing find-registration-and-cancel flow, now scoped to the validated student.
- File doc comment rewritten to describe the family-allowlist invariant.

### 4. `frontend/src/lib/ce-tournaments-data.ts` — no regression
- No change required. It calls `getMembershipStateForUser`, whose signature is unchanged and which now
  returns the deterministic primary member. No multi-member UI data shapes were added (Phase 2).

## Tests

New/updated (all passing):
- `frontend/src/lib/__tests__/chess-empire-member.test.ts` — rewritten mock to the fetch-all query
  shape (thenable builder, `.order()`, array responses). Covers: 0 rows, 1 verified, 2+ verified
  (family), verified+pending mix, expired row filtered, relationship coercion
  (missing/null → self, unknown → other, child passes through), and deterministic primary
  (verified beats earlier pending; self beats earlier child; earliest verified wins with no self).
- `frontend/src/app/api/chess-empire/tournaments/__tests__/register.test.ts` — rewritten to mock
  `getVerifiedMembersForUser`. Covers brief cases (a) no body + 1 member → registers;
  (b) no body + 2 → 400 student_required; (c) valid child id → registers that id; (d) foreign id →
  403 forbidden_student + CE never called; (e) unauthenticated → 401. Plus 403 no-members, CE error
  mapping, 500 on lookup throw, and DELETE variants: cancel by body id, cancel by query-param id,
  forbidden id → 403, and family-no-id → 400.

### Test counts
- Targeted files: **56 passed** (both files).
- Full suite (`npm test` / `vitest run`): **2745 passed, 2 failed** (298 files).
- Lint (`eslint`) on all four touched files: **pass**.
- `tsc --noEmit`: **no errors in any file touched by this change** (see pre-existing note).

### Pre-existing failures (NOT caused by this change, NOT fixed)
- `src/components/coach/__tests__/CoachChat.test.tsx` — 2 failing assertions expecting a coach
  transcript object without a `client_ts` timestamp field that the component now emits. Unrelated to
  family registration (no coach files were touched).
- `tsc --noEmit` reports pre-existing type errors in test files unrelated to this work:
  `src/components/openings/__tests__/GameViewerPanel-save.test.ts` (vitest Mock type mismatches) and
  `src/lib/__tests__/org-metadata.test.ts` (`Twitter.card` property). Neither is a file this change touched.

## Sync script assessment (task 6)
`sync-chesster-registration.mjs` lives **outside** this repo, at
`/root/clawd/chess-empire-database/scripts/sync-chesster-registration.mjs` (Chess Empire side).
Reviewed, not changed. It **iterates verified membership rows per external_student_id**
(`for (const m of members)` over all `link_status='verified'` rows, grouped by `external_student_id`),
NOT one-row-per-user — so a family account's multiple verified links each map to the correct student.
It does **not** assume one membership per user. **No Phase 3 fix needed** for family multi-link.

The in-repo `scripts/sync-chess-empire-members.mjs` is a different (link-direction) sync and is
likewise row-oriented; no one-per-user assumption relevant to this feature.

## Constraints honored
- No `git add -A`; only the specific changed files staged. Conventional commit. Committed, **not pushed**,
  no deploy.
- No changes to `backend/data/twic/`, `.env.local`, or any Chess Empire DB/edge function.
- Migration is a file only — not applied to any database.
