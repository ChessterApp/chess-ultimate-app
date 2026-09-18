# Family Registration — Phase 3 Brief (SPEC — not yet dispatched)

Status: **SPEC ONLY.** Do not implement until Alex approves.

## Goal
Complete the family-account lifecycle: a parent can **see** and **manage** the
family's linked students from their profile, **remove** a link, and the
add-family-member flow works on **any device** (not just the one that did the
original onboarding). Phases 1–2 covered create + use; Phase 3 covers
view + remove + hardening.

## Context (what exists after Phase 2)
- `frontend/src/lib/chess-empire-member.ts` — `getVerifiedMembersForUser`
  returns the verified allowlist; rows live in `organization_members`
  (`external_student_id`, `link_status`, `relationship` self|child|other,
  `role`, `external_source`).
- Link API surface: `app/api/chess-empire/link/{claim,confirm,reject,status}`.
  **No unlink/remove endpoint exists.**
- `app/tournaments/AddFamilyMember.tsx` (Phase 2) — add-child flow, but
  depends on `readBranchWelcomeUrl` (branch-welcome URL in device storage);
  on a new device it can only show an explanation, not proceed.
- `app/profile/page.tsx` — client page (Clerk user + gamification profile);
  no family info today. `app/settings/page.tsx` is board/appearance prefs —
  wrong home for identity data.
- Phase 2 report follow-ups: server-side branch resolution flagged as the
  natural Phase 3 hardening.

## Scope

### 1. Family section on the Profile page
- New "Family" card on `app/profile/page.tsx` (client component, e.g.
  `app/profile/FamilySection.tsx`), shown only when the account has ≥1
  verified Chess Empire link.
- Lists every member: display name (via existing `getStudentDisplayName`
  path — expose through a small `GET /api/chess-empire/link/members`
  route so the client page can fetch it), relationship tag
  (self/child/other), and link status.
- Hosts "Add family member" — reuse `AddFamilyMember.tsx` (move/generalize
  it out of `app/tournaments/` if needed; the tournaments usage must keep
  working identically).
- Single-member accounts: the card still shows (their own link + add
  affordance) — this is also where a solo user discovers the family feature.

### 2. Remove (unlink) a family member
- New endpoint: `DELETE /api/chess-empire/link/members/[studentId]`.
- Guards (all tested):
  - Caller must be authed; the target row must belong to the **caller's own**
    Clerk user (404/403 otherwise — never reveal other users' links).
  - Phase 3 allows removing only `relationship IN ('child','other')`.
    Removing the `self` link is **out of scope** (it is effectively "delete my
    Chess Empire identity" — bigger consequence, different confirmation UX;
    defer).
  - No Chess Empire-side calls — this only deletes the Chesster-side link row
    (the student keeps existing in Chess Empire).
- Semantics: **hard-delete the `organization_members` row.** Re-linking later
  goes through the normal search→verify→claim flow, which already works.
  (Alternative considered: `link_status='removed'` soft delete — rejected;
  the upsert conflict path would need rework and there is no audit
  requirement today.)
- UI: remove control per child/other row in the Family card, with an explicit
  confirm step ("Remove <name>? They will disappear from tournament
  registration on this account. Existing tournament registrations at the
  school are NOT cancelled.") — that last sentence is important and true.
- After removal, tournaments page must degrade correctly: snapshot
  re-resolves members on next load; if the account drops to 1 member the UI
  reverts to the single-member (no-picker) shape. Add a test.

### 3. Cross-device add-member hardening (from Phase 2 report)
- `AddFamilyMember` currently needs the branch-welcome URL from device
  storage. Add server-side branch resolution: a small route (or extension of
  `link/members` GET) that derives the branch context from the caller's
  existing **verified** member (Chess Empire student record → branch), so the
  panel works on any signed-in device.
- Device-storage path stays as the fast path; server resolution is the
  fallback. The "can't proceed" explanation remains only for the truly
  degenerate case (no verified member at all — which shouldn't reach this
  panel anyway).

### Out of scope (explicit)
- Removing/changing the `self` link; editing relationship of an existing link.
- CE **online** section + gamification per-member switching (still
  primary-member-only — candidate Phase 4).
- Any Chess Empire DB / edge-function changes. Any registration-route changes.
- Notifying the other side / guardian consent flows.

## i18n
All new strings in **en / ru / kz** (`family*`, `removeMember*`, confirm copy,
error codes). Locale-parity tests must pass.

## Tests (gate)
- Endpoint: happy path, foreign-user 403/404, `self` blocked, unauthenticated,
  idempotent double-delete.
- Family card: renders members, remove confirm flow, single-member shape,
  add-member reuse unaffected on tournaments page (regression bar).
- Branch resolution: server fallback used when storage empty; storage fast
  path unchanged.
- Full vitest suite green (baseline **2772**); eslint clean on touched files.

## Constraints
- No `git add -A`; conventional commit; commit but **no push/deploy**.
- No changes to `backend/data/twic/`, `.env.local`, Phase 1 register route,
  `chess-empire-client.ts` public API surface.
- Estimated size: ~8–10 files touched (1 new route, 1 new component, profile
  page, AddFamilyMember generalization, i18n ×3, tests). Ralph via tmux.
