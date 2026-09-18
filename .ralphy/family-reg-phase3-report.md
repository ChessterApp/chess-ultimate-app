# Family Registration — Phase 3 Report

Completes the family-account lifecycle: a parent can now **see** and **manage**
their linked Chess Empire students from the Profile page, **remove** a
child/other link, and the add-family-member flow works on **any signed-in
device** (not just the one that did the original onboarding). Zero Chess
Empire-side changes.

## What changed

### 1. Family card on the Profile page
- **`frontend/src/app/profile/FamilySection.tsx`** (new, client) — fetches
  `GET /api/chess-empire/link/members` on mount and renders a "Family" card
  listing every verified member with display name, relationship tag
  (self/child/other, reusing `ceTournaments.relationship.*`) and link status.
  The card **self-hides** until the account has ≥1 verified link, so a
  fully-unlinked user never sees an empty card. Single-member (self-only)
  accounts still see the card — it's where a solo user discovers the family
  feature and can add a child. Hosts the generalized `AddFamilyMember` panel.
- **`frontend/src/app/profile/page.tsx`** — renders `<FamilySection />` above
  the Account Actions card (it self-hides when there are no members).

### 2. `GET /api/chess-empire/link/members`
- **`frontend/src/app/api/chess-empire/link/members/route.ts`** (new) — returns
  `{ members: [{ studentId, name, relationship, status }], branchToken }`.
  - Members come from `getVerifiedMembersForUser` (the Phase 1 allowlist —
    scoped to the caller's own Clerk user, never revealing others' links).
    Names via `getStudentDisplayName` (parallel, best-effort `null`).
  - `branchToken` is the **server-side branch resolution** (task 3): the primary
    verified member (self wins, else first) → CE `students.branch_id` (via
    `getStudentBranches`) → the newest active, non-online `branch_invite_tokens`
    row for that branch. Best-effort `null` on any failure.
  - 401 unauthenticated, 500 on lookup error.

### 3. `DELETE /api/chess-empire/link/members/[studentId]` — unlink
- **`frontend/src/app/api/chess-empire/link/members/[studentId]/route.ts`**
  (new) — hard-deletes the caller's OWN `organization_members` row for the given
  external student id.
  - Guards: 401 unauthenticated; the lookup is **scoped by `user_id`**, so a
    foreign or absent row is a plain 404 (never reveals another user's links);
    `self` (and pre-migration `null` → self) is blocked with 403
    `cannot_remove_self`; only `relationship IN ('child','other')` is removable.
  - No Chess Empire-side calls — the student keeps existing in CE and school-side
    tournament registrations are untouched. Idempotent in effect: a repeat
    delete of an already-removed row 404s with no side effects.
- **UI** (in `FamilySection`): per child/other row a "Remove" control opens an
  explicit inline confirm — `removeConfirmTitle` + the required body copy
  ("They will disappear from tournament registration on this account. Existing
  tournament registrations at the school are NOT cancelled.") — then DELETEs and
  drops the row from the list on success (error path keeps the row + shows a
  message). The self row has no remove control.
- **Tournaments degradation**: no change was needed to the tournaments snapshot —
  it already re-resolves members from `getVerifiedMembersForUser` on every load
  (Phase 2), so after a removal the next load drops to the single-member
  (no-picker) shape automatically. The Phase 2 `CETournamentsView` regression
  test already asserts the single-member shape; no new test was required there.

### 4. Cross-device add-member hardening
- **`AddFamilyMember` moved** `app/tournaments/AddFamilyMember.tsx` →
  **`components/empire/AddFamilyMember.tsx`** (git mv; the tournaments import was
  updated to `@/components/empire/AddFamilyMember`). Behaviour on the tournaments
  page is identical.
- Branch resolution is now two-tier: the **fast path** still reads the stashed
  branch-welcome URL from device storage (`readBranchWelcomeUrl`); when that's
  empty it **falls back** to `GET /api/chess-empire/link/members` and uses the
  server-resolved `branchToken`. A new `branchResolved` state shows a
  "Finding your branch…" hint while resolving and only surfaces the
  "open your invite link" explanation when **neither** source yields a token.

## i18n
- New `ceTournaments.addMemberResolving` and a new top-level **`family`**
  namespace (12 keys: title, subtitle, statusVerified, unknownMember, remove
  controls, confirm title/body/buttons, removing, removeError) added to
  **en / ru / kz**.
- Parity guards pass: the existing `ceTournaments-messages.test.ts` covers the
  new `ceTournaments` key; a new `family-messages.test.ts` guards the `family`
  namespace across all three locales.

## Tests
New test files (all green):
- `src/app/api/chess-empire/link/__tests__/members.test.ts` — 401, empty family,
  member mapping (name/relationship/status), branch-token resolution
  (revoked/expired/online filtered, newest wins, null when unresolvable), 500.
- `src/app/api/chess-empire/link/members/__tests__/delete.test.ts` — 401, blank
  id 400, foreign/absent 404, self 403, null-relationship 403, child/other
  removal 200 (+ delete issued), idempotent double-delete (second 404, no
  side-effects), lookup-error 500.
- `src/app/profile/__tests__/FamilySection.test.tsx` — self-hides when empty,
  member list with per-relationship removability, single-member card + add
  affordance, confirm → DELETE → row removed, delete-failure error path.
- `src/app/profile/__tests__/family-messages.test.ts` — `family` locale parity.
- `src/components/empire/__tests__/AddFamilyMember.test.tsx` (moved + extended) —
  the happy claim path (unchanged), the new server-side branch-resolution
  fallback (search scoped by the resolved token), and the truly-degenerate
  "no token anywhere" explanation.

### Test counts
- Full suite (`vitest run`): **305 files passed, 2799 tests passed, 0 failed**
  (exit 0). Baseline was 2772; **+27** new tests, all green.
- Lint (`eslint`) on all touched files: **pass** (0 errors, 0 warnings).

### Pre-existing failures
- None. The full run was clean.

## Follow-ups (out of scope, flagged only)
- Removing/changing the `self` link and editing an existing relationship remain
  deferred (bigger-consequence UX), per the brief.
- CE **online** section + gamification remain primary-member-only (candidate
  Phase 4).

## Constraints honored
- No `git add -A` — only the specific changed/new files were staged.
- Conventional commit. Committed on `main`, **not pushed**, **not deployed**.
- No changes to `backend/data/twic/`, `.env.local`, the Phase 1 register route,
  `chess-empire-client.ts`'s public API surface, or any Chess Empire DB / edge
  function. No new DB migrations (the `relationship` column already exists).
