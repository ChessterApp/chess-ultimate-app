# Family Registration — Phase 2 Report

Frontend surfacing of the Phase 1 multi-student backend: a family (2+ verified
Chess Empire links) parent can now see per-child registration state on the
tournaments page, pick which child to register/cancel, and link an additional
child from the app. **Single-student users see zero change** (the regression
bar). Zero Chess Empire-side changes.

## What changed

### 1. Multi-member tournament snapshot — `frontend/src/lib/ce-tournaments-data.ts`
- Resolves the viewer via `getVerifiedMembersForUser` (the Phase 1 allowlist)
  instead of the single-member helper.
- New snapshot field `members: { studentId, name, relationship }[]` — names via
  `getStudentDisplayName`, fetched in parallel, best-effort `null` on failure.
- New per-card field `registrations: { studentId, registrationId }[]` — every
  family member registered for that tournament, fetched via
  `getStudentTournamentRegistrations` per member in parallel, each best-effort
  (`[]` on failure).
- The legacy single-link fields (`studentName`, per-card `registration_id`,
  `is_registered`) are still populated from the **deterministic primary** member
  (`relationship='self'` wins, else the first verified row — matching
  `pickPrimaryState`), so the poll route and any other consumer stay
  byte-compatible.
- Membership stays `'verified'` when ≥1 verified member exists.

### 2. Student picker + per-member UI — `frontend/src/app/tournaments/CETournamentsView.tsx`
- `CEViewer.verified` gained an optional `members: CEMember[]`; wired through
  `ChessEmpireTournaments.tsx`.
- **1 member (or the legacy `members`-absent shape): identical to today** — the
  one-click Register/Cancel button, and register/cancel send **no request body**
  (byte-compatible with the Phase 1 route's single-link path). This is the
  regression bar and is asserted by a test.
- **2+ members:**
  - Register opens a compact picker of the still-unregistered members (name +
    relationship tag) → `POST { student_id }`.
  - Each registered child shows a `✓ Name` chip with its own cancel control →
    `DELETE { student_id }` (this is how the user "picks which registration to
    cancel").
  - A family bar above the schedule lists every member with its relationship tag
    and hosts the "Add family member" affordance.
- Optimistic register/cancel now also update the per-card `registrations[]` for a
  family pick; the single-link path is unchanged. `400 student_required` /
  `403 forbidden_student` map to localized messages (never raw errors).

### 3. Add-family-member flow — `frontend/src/app/tournaments/AddFamilyMember.tsx` (new)
- A lightweight inline panel reusing the existing public onboarding endpoints —
  `students/search` → `students/verify` → `link/claim` — rather than
  copy-pasting the welcome flow (WelcomeFlow.tsx is untouched, so the no-link /
  onboarding pages carry zero regression risk).
- New links are written with `relationship='child'` (a Child/Other toggle lets
  the user pick 'other'); the parent is already signed in, so the claim writes
  the member row server-side immediately and the page `router.refresh()`es to
  pick up the new child.
- Branch context is recovered from the durable branch-welcome URL the parent's
  own onboarding stashed (`readBranchWelcomeUrl`). If it isn't present on the
  device, the panel explains how to proceed instead of failing silently.

### Relationship threading (backend plumbing for the child link)
To write `relationship='child'` end-to-end without touching the Phase 1 register
route, the relationship now rides the invite JWT:
- `invite-jwt.ts`: optional `relationship` on `InviteJwtPayload`; `verifyInviteJwt`
  normalizes a missing/unknown value to `'self'` (never forges a guardian link).
  Absent → the token stays byte-identical to legacy self-claims (back-compat).
- `students/verify/route.ts`: accepts `relationship` in the body, honours only
  `'child'`/`'other'`, and signs it into the JWT (omitted for self-claims).
- `chess-empire-jwt-link.ts`: `upsertMemberLink` writes `relationship` only for a
  `'child'`/`'other'` link, so `'self'`/omitted leaves the DB default (`'self'`)
  on insert and never clobbers an existing value on conflict;
  `linkMemberViaInviteJwt` threads the claim through.

The Phase 1 register route (`tournaments/[id]/register`) was **not** modified —
it already validates `student_id` against the caller's verified allowlist.

### 4. i18n
Added the new `ceTournaments` keys (`familyTitle`, `relationship.*`,
`pickMember`, the `addMember*` set) and two new `errors` codes
(`student_required`, `forbidden_student`) to **en / ru / kz** — the locale-parity
guard (`ceTournaments-messages.test.ts`) passes.

## Tests

New / updated (all passing):
- `src/lib/__tests__/ce-tournaments-data.test.ts` (new) — logged-out, single
  verified (legacy shape), family (members[] + per-card registrations[], primary
  fields from the self row), primary registration still fills legacy fields, and
  per-member fetch-failure graceful degradation.
- `src/app/tournaments/__tests__/CETournamentsView.test.tsx` — added a family
  suite: no picker for a single member (regression bar), single-member register
  sends no body, picker opens for 2+ and POSTs the picked `student_id`,
  per-member chips, cancel targets the picked member (DELETE + body),
  `forbidden_student` localized message, family bar renders members + add
  affordance. Existing `makeCard` gained `registrations: []`.
- `src/app/tournaments/__tests__/AddFamilyMember.test.tsx` (new) — search →
  confirm → verify(`relationship='child'`) → claim → refresh; and the
  no-branch-context explanation.
- `src/app/api/chess-empire/students/__tests__/verify.test.ts` — relationship
  carried into the JWT, defaulted to `self` when absent, and coerced to `self`
  for an unexpected value.
- `src/app/api/chess-empire/students/__tests__/search.test.ts` — an explicit
  add-family-member exclusion case (already-linked child filtered, new sibling
  kept).
- `src/lib/__tests__/chess-empire-jwt-link.test.ts` — relationship threaded into
  the upsert; omitted/`self` leaves the key off.
- `src/app/api/chess-empire/tournaments/__tests__/list.test.ts` — updated its
  member mock to `getVerifiedMembersForUser` (the snapshot's new dependency).

### Test counts
- Full suite (`vitest run`): **301 files passed, 2772 tests passed, 0 failed**
  (exit 0). Baseline was 2747 passing; +25 new tests, all green.
- Lint (`eslint`) on all touched files: **pass** (0 errors, 0 warnings).

### Pre-existing failures
- None. The full run was clean. (The Phase 1 report had noted 2 flaky
  `CoachChat.test.tsx` assertions; they did not reproduce in this run and no
  coach files were touched.)

## Follow-ups (expected, flagged only)
- The CE **online** section and gamification surfaces remain primary-member-only
  — that is EXPECTED per the brief; not addressed here.
- The add-family-member flow depends on the branch-welcome URL being present in
  the device's storage. A server-side branch-token resolution (from the caller's
  existing verified branch) would make it robust across devices — a reasonable
  Phase 3 hardening, not required now.

## Constraints honored
- No `git add -A` — only the specific changed files were staged. Conventional
  commit. Committed, **not pushed**, no deploy.
- No changes to `backend/data/twic/`, `.env.local`, the Chess Empire DB / edge
  functions, `chess-empire-client.ts`'s API surface, or the Phase 1 register
  route. No new DB migrations (the `relationship` column already exists).
