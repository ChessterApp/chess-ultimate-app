# PRD — Delete School (close §7 gap)

Closes the only outstanding gap from `PRD-self-serve-school-onboarding.md` §7:

> School wants to delete their account → "Delete school" in admin settings → confirmation flow (type school name to confirm) → emails Alex + sets `organizations.deletion_requested_at = now()` (new nullable timestamptz column — added via migration `20260603_002_org_deletion_requested.sql`). Hard delete after 30d.

The PRD also justifies the timestamp choice over an enum value: the existing `organization.status` enum is `active | suspended | trial` and is read in 12+ places; extending it would force a cascade of switch updates. A nullable timestamp is additive and never collides. Honor that.

## Scope (all required)

### 1. Migration — `supabase/migrations/20260603_002_org_deletion_requested.sql`
- Adds `deletion_requested_at timestamptz NULL` column to `organizations`
- Idempotent (`IF NOT EXISTS`)
- No backfill, no default

### 2. Backend service — `backend/services/org_deletion.py`
- `request_deletion(org_id, requester_user_id) -> dict`
  - Loads org, verifies requester is owner (role check)
  - Sets `organizations.deletion_requested_at = now()` (only if currently NULL — re-requests no-op)
  - Sends email to Alex via existing `backend/services/email.py` (use Resend). Subject e.g. `[Chesster] School deletion requested: <slug>`. Body includes org slug, name, requester email, timestamp.
  - Returns `{ ok: true, deletion_requested_at }`
- Handle email failure: log + still return ok (timestamp set is the source of truth). Email retry is a nice-to-have but NOT mandatory — the queue table `invite_email_failures` is invite-specific; do not reuse.

### 3. Backend route — `backend/routes/admin.py` (or new file if cleaner)
- `POST /api/admin/organizations/<org_id>/delete-request`
- Auth: Clerk JWT required; verify caller is org owner
- Body: `{ "confirm_name": "<typed school name>" }` — server re-checks against `organizations.name`. Mismatch → 400.
- Returns service result. 401 on missing auth, 403 on non-owner, 400 on confirm mismatch.

### 4. Frontend Delete School UI — `frontend/src/app/admin/settings/page.tsx` (add section) + new component `frontend/src/components/admin/DeleteSchoolCard.tsx`
- Card at bottom of admin settings, danger styling (red border / muted destructive accent — use existing tailwind tokens)
- Heading "Delete school" + descriptive copy: "Schedules deletion in 30 days. All students, content, and billing will be removed. You can email support to cancel within that window."
- Button "Delete this school" opens modal
- Modal: shows school name, has input `Type "<name>" to confirm`, plus final "Delete school" button (disabled until exact match)
- On submit → POST the route → toast success + replace card with "Deletion scheduled on <date>. Email support@chesster.io to cancel."
- If `deletion_requested_at` already set on load → render scheduled state immediately (no button)
- Frontend should fetch deletion state from existing org-info endpoint (or extend that endpoint minimally if needed — small, additive)

### 5. Tests (mandatory — §11.0 gate)
- `backend/tests/test_org_deletion.py` — service tests: happy path sets timestamp; second call no-op; non-owner rejected; email failure does not block timestamp write
- `backend/tests/test_admin_delete_request_route.py` — route tests: 401 / 403 / 400 confirm-mismatch / 200 happy
- `frontend/src/components/admin/__tests__/DeleteSchoolCard.test.tsx` — render states, confirm-name match enables button, calls API on submit, renders scheduled state when `deletion_requested_at` is set
- `supabase/migrations/__tests__/20260603_002_org_deletion_requested.test.sql` is NOT required — assert column existence via a service test that reads/writes it

### 6. Definition of Done
- Migration committed to `supabase/migrations/`
- Backend service + route registered (check `backend/app.py` or wherever routes are wired)
- Frontend card rendered on `/admin/settings`
- All new tests pass; existing suites still green
- Commit on `main` (single commit, conventional message: `feat(admin): self-serve delete-school request flow (PRD §7)`)

## Out of scope
- Hard-delete cron after 30d — separate ops concern, not blocking
- Cancellation UI — copy says email support; that's fine for v1
- Ownership transfer (already in §7 line below)

## Reference files
- PRD: `/root/chess-app/docs/prd/PRD-self-serve-school-onboarding.md` §7
- Existing email service: `backend/services/email.py`
- Existing admin settings page: `frontend/src/app/admin/settings/page.tsx`
- Existing org-info / admin routes: `backend/routes/admin.py`, `frontend/src/app/api/admin/organizations/`
- Existing migration pattern: `supabase/migrations/20260603_001_tier_add_pro.sql`, `..._003_org_billing_whop_columns.sql`

Numbering note: the sequence currently jumps 001 → 003 → 004 …. This PR fills the missing 002 slot — that's intentional and matches the PRD filename verbatim.
