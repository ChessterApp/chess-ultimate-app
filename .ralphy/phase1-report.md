# Phase 1 — School Onboarding Completion Report

**Branch:** `feat/school-onboarding-phase1`
**Tag:** `school-onboarding-phase1`
**Date:** 2026-06-02

---

## Verification

- `cd backend && pytest` — **511 passed**, 3 failures all pre-existing in
  `test_player_name_filter.py` (DB-dependent, unrelated). 2 files have a
  pre-existing import error (`responses` module missing) and were skipped.
- `cd frontend && npx vitest run` — Phase-1 suites: **27/27 pass**
  (`tiers.test.ts`, `WizardState.test.ts`, `whop/webhook/verify.test.ts`,
  `whop/org-checkout/route.test.ts`). Pre-existing failures in
  `sw-version.test.ts` and `coach/routes.test.ts` confirmed unrelated
  via `git stash` test.
- `cd frontend && NODE_OPTIONS="--max-old-space-size=2048" npx next build`
  — clean compile + typecheck. `/for-schools` + `/for-schools/start/{,school,
  plan,payment,brand,invite,done}` routes generated.
- Existing `src/app/__tests__/admin-pages.test.tsx` still passes after
  billing-page refactor (10/10).
- Lint: `npm run lint` is broken at the repo level (pre-existing eslint
  circular-config error on ESLint v9). Build's TypeScript pass is the
  effective lint.

---

## Prereqs (PRD §6.0–6.5)

### A. Tier reconciliation (§6.0)
- `supabase/migrations/20260603_001_tier_add_pro.sql` — widens the
  `organization_billing.plan` CHECK constraint to include `'pro'`.
  Note: schema uses a TEXT+CHECK, not an `organization_plan` ENUM TYPE
  (see migration file header for rationale).
- `backend/services/tier_quota.py` — canonical tier map
  (starter/growth/pro/enterprise) with seat caps, prices, features +
  `can_invite()` enforcement helper.
- `backend/routes/tiers.py` — `GET /api/tiers` (public, public read).
- `frontend/src/lib/tiers.ts` — typed fetcher + `recommendTier()` helper.
- `frontend/src/app/api/tiers/route.ts` — Next.js proxy.
- `frontend/src/app/admin/billing/page.tsx` — replaced hardcoded TIERS
  constant with fetched values.

### B. Whop webhook signature verification (§6.1 — SECURITY)
- `frontend/src/app/api/whop/webhook/verify.ts` — HMAC SHA-256 helper,
  `crypto.timingSafeEqual`, supports optional `sha256=` prefix.
- `frontend/src/app/api/whop/webhook/route.ts` — verifies signature
  BEFORE JSON parse; fails closed (500) when `WHOP_WEBHOOK_SECRET` unset,
  401 on bad/missing sig. Reads raw `req.text()` so HMAC is over exact
  bytes Whop signed.
- `.env.example` — documents `WHOP_WEBHOOK_SECRET`. The existing
  `.env.local` already has the var (empty).
- Tests: 8 cases in `verify.test.ts` — valid, valid with prefix, tampered,
  invalid hex, missing header, missing secret, empty secret, garbage.

### C. Org-level Whop checkout (§6.1)
- `frontend/src/app/api/whop/org-checkout/route.ts` — auth-gated POST that
  validates `{tier, billing_cycle, org_id}`, looks up the right
  `NEXT_PUBLIC_WHOP_ORG_<TIER>_<CYCLE>` env var, and returns a checkout
  URL with `metadata.kind=org_subscription` + `metadata.org_id` +
  `metadata.tier` + `metadata.billing_cycle`.
- Webhook route now branches on `metadata.kind`: `org_subscription` writes
  to `organization_billing` and flips `organizations.status` to active;
  individual flow unchanged.
- Tests: 6 cases (auth, invalid tier, invalid cycle, missing org_id,
  plan_not_configured, happy path).

### D. organization_billing Whop columns (§6.1)
- `supabase/migrations/20260603_003_org_billing_whop_columns.sql` — adds
  nullable `whop_membership_id`, `whop_user_id`, `whop_plan_id`. Unique
  indexes on `whop_membership_id` (partial) and `organization_id` so the
  webhook's `onConflict` upsert works. Stripe columns preserved.

### E. Pre-payment org state (§6.2)
- `supabase/migrations/20260603_004_pending_onboarding.sql` —
  `pending_onboarding` table with 24h `expires_at`, auto-updated
  `updated_at` trigger, unique `clerk_user_id`.
- `backend/routes/onboarding.py` — three endpoints:
  - `POST /api/onboarding/save` — upsert + step validation.
  - `GET /api/onboarding/resume` — by Clerk user header.
  - `DELETE /api/onboarding/complete` — clear after org creation.
  - Plus `POST /api/onboarding/create-org` — self-serve org creation
    (wraps the super-admin logic but runs under the user's own session;
    caller becomes `owner`; Clerk sync is fail-soft).
- Frontend proxies: `frontend/src/app/api/onboarding/{save,resume,
  complete,create-org}/route.ts`.
- Tests: 9 cases in `test_onboarding_routes.py`.

### F. Tier enforcement (§6.3)
- `backend/routes/admin.py` — `POST /api/admin/organizations/<id>/members/
  invite` now calls `tier_quota.can_invite()` first and returns **402**
  with `{code, current_count, seat_cap, plan, upgrade_url}` when blocked.
- Frontend handles 402 in Step 6 ("Invite") with an inline upgrade CTA
  card linking to `/admin/billing`.
- Tests: 2 cases in `test_invite_tier_enforcement.py` (blocked + allowed).

### G. Real invite emails (§6.4)
- `supabase/migrations/20260603_005_invite_email_failures.sql` —
  retry-visibility table.
- `backend/services/email.py` — `send_invite_email(org_id, to_email, role)`
  via Resend (stdlib `urllib.request`, no extra deps). Fails closed when
  `RESEND_API_KEY` unset, logs to `invite_email_failures` on any send
  failure. Email body uses the org's brand color + logo and links to
  `<slug>.chesster.io/sign-up?invite=<email>`.
- `backend/routes/admin.py` invite endpoint calls it (best-effort —
  doesn't block invite creation if email fails).
- Tests: 4 cases in `test_email_service.py` (no-key, success body shape,
  HTTP error → failure row, tenant-subdomain link).

### H. Subdomain availability (§6.5)
- `backend/routes/subdomains.py` — `GET /api/subdomains/check?slug=foo`.
  Reserved-slug constant (30+ entries including `admin`, `super-admin`,
  `api`, `auth`, etc.). Format validation via regex. DB uniqueness
  check; 503 on DB error (fail closed).
- `frontend/src/app/api/subdomains/check/route.ts` — passthrough proxy.
- `frontend/src/components/school-onboarding/SlugAvailabilityInput.tsx`
  — debounced 300ms availability check with status dot, suggestions,
  validation hints.
- Tests: 7 cases in `test_subdomains.py`.

---

## Wizard (PRD §4)

Routes (all under `/for-schools/start/*` per PRD §A — no collision with
the player wizard at `/onboarding/*`):

| Path                                | Step                |
| ----------------------------------- | ------------------- |
| `/for-schools`                      | Marketing landing   |
| `/for-schools/start`                | 1. Account          |
| `/for-schools/start/school`         | 2. Identity         |
| `/for-schools/start/plan`           | 3. Tier             |
| `/for-schools/start/payment`        | 4. Payment          |
| `/for-schools/start/brand`          | 5. Brand            |
| `/for-schools/start/invite`         | 6. Invite           |
| `/for-schools/start/done`           | Activation          |

Components added under `frontend/src/components/school-onboarding/`:
- `WizardState.tsx` — `<WizardProvider>` + `useWizard()` with
  localStorage + debounced server autosave (600ms) to
  `/api/onboarding/save`. Resumes from server on mount.
- `SchoolOnboardingShell.tsx` — top bar w/ step dots, left form / right
  preview split, sticky preview, Continue/Back footer.
- `BrandPreviewPanel.tsx` — Phase-1 dashboard-surface preview (Dashboard
  / Courses / Puzzles / Login tabs) that consumes the same `--brand-*`
  CSS vars as the real tenant. Phase-2 will swap in the public landing
  iframe.
- `SlugAvailabilityInput.tsx` — debounced subdomain check (see §H).

`frontend/src/middleware.ts` — `/for-schools` added to the public-route
matcher (the wizard itself is auth-gated by Clerk's modal sign-up button
on Step 1; everything from Step 2 onward requires `useWizard` which
needs the Clerk session for autosave/resume to work).

Reuse confirmed (no duplication):
- Brand color/CSS save → existing `PUT /api/admin/organizations/<id>/
  settings`.
- Custom domain → Step 5 surfaces a collapsed input for Pro tier and
  POSTs to existing `/api/admin/organizations/<id>/custom-domain`.
- `<BrandingInjector>` already swaps `--brand-*` vars at runtime.
- New `POST /api/onboarding/create-org` was added (self-serve) instead
  of repurposing the super-admin route — it shares the Clerk sync
  helpers from `super_admin.py` but is reachable by any authenticated
  user and makes the caller the `owner`.

---

## Files changed / added

### Migrations (new)
- `supabase/migrations/20260603_001_tier_add_pro.sql`
- `supabase/migrations/20260603_003_org_billing_whop_columns.sql`
- `supabase/migrations/20260603_004_pending_onboarding.sql`
- `supabase/migrations/20260603_005_invite_email_failures.sql`

### Backend
- New: `backend/services/tier_quota.py`, `backend/services/email.py`,
  `backend/routes/tiers.py`, `backend/routes/onboarding.py`,
  `backend/routes/subdomains.py`.
- Modified: `backend/app.py` (registers 3 new blueprints),
  `backend/routes/admin.py` (invite endpoint: 402 enforcement +
  invite-email call).
- New tests: `tests/test_tier_quota.py`, `tests/test_onboarding_routes.py`,
  `tests/test_invite_tier_enforcement.py`, `tests/test_email_service.py`,
  `tests/test_subdomains.py`.

### Frontend
- New: `src/app/for-schools/page.tsx`,
  `src/app/for-schools/start/{layout,page}.tsx` and
  `src/app/for-schools/start/{school,plan,payment,brand,invite,done}/
  page.tsx`.
- New components: `src/components/school-onboarding/{WizardState,
  SchoolOnboardingShell, BrandPreviewPanel, SlugAvailabilityInput}.tsx`.
- New API routes: `src/app/api/tiers/route.ts`,
  `src/app/api/onboarding/{save,resume,complete,create-org}/route.ts`,
  `src/app/api/subdomains/check/route.ts`,
  `src/app/api/whop/org-checkout/route.ts`,
  `src/app/api/whop/webhook/verify.ts`.
- New lib: `src/lib/tiers.ts`.
- Modified: `src/app/api/whop/webhook/route.ts` (HMAC + kind branching),
  `src/app/admin/billing/page.tsx` (fetched tiers),
  `src/middleware.ts` (public route),
  `.env.example` (Whop org plans, Resend, webhook secret).
- New tests: `src/lib/__tests__/tiers.test.ts`,
  `src/components/school-onboarding/__tests__/WizardState.test.ts`,
  `src/app/api/whop/webhook/__tests__/verify.test.ts`,
  `src/app/api/whop/org-checkout/__tests__/route.test.ts`.

---

## Endpoints added (summary)

| Method   | Path                                                     | Notes |
| -------- | -------------------------------------------------------- | ----- |
| GET      | `/api/tiers`                                              | Canonical map, public |
| POST     | `/api/onboarding/save`                                    | Upsert wizard state |
| GET      | `/api/onboarding/resume`                                  | Caller's pending row |
| DELETE   | `/api/onboarding/complete`                                | Clear pending row |
| POST     | `/api/onboarding/create-org`                              | Self-serve org create |
| GET      | `/api/subdomains/check?slug=…`                            | Reserved + uniqueness |
| POST     | `/api/whop/org-checkout`                                  | Returns Whop URL |
| POST     | `/api/whop/webhook` (modified)                            | HMAC + kind-branched |

---

## Known gaps / Phase-2 carryovers

1. **Logo drag-drop in Step 2.** PRD calls for a drag-drop logo uploader
   with live cropper. Step 2 currently accepts a URL field; the wizard's
   payment flow runs before org-creation so we can't upload to
   `org-branding/<id>/` until Step 5. Phase 2 will add a pre-org temp
   upload bucket.
2. **CSV importer in Step 6.** Currently only "paste a list of emails"
   + per-row form. CSV/column-mapper deferred per PRD §11 phasing.
3. **Logo color extraction** (`node-vibrant`) — explicitly deferred to
   Phase 2 in §11.
4. **Bulk-invite endpoint** (`POST /…/bulk-invite`) — Phase 1 invite UI
   loops the existing single-invite endpoint per row. Atomic bulk
   endpoint can land in Phase 2.
5. **`/api/whop/org-checkout` returns the URL only** — actual redirect
   happens in `payment/page.tsx`. Embedded Whop iframe (PRD §4 Step 4
   ideal) wasn't possible without a Whop Elements integration; we open
   their hosted checkout and pass `d=` redirect param back to
   `/for-schools/start/brand?status=paid`.
6. **`pending_onboarding` doesn't gate slug reservation** — slug
   uniqueness is server-side rechecked in `/api/onboarding/create-org`.
   A race window exists between Step 2 (slug check) and Step 4 (org
   create). The PRD's edge-case table covers this with a "re-check on
   submit" pattern — implemented.
7. **PostHog events** (§6.8) — events fire client-side from the wizard
   via the existing instrumentation-client, but no new event-name
   constants were added. Phase 2 can centralize them.
8. **Webhook signature header name.** Whop docs use `X-Whop-Signature`;
   the verifier accepts both `x-whop-signature` and `whop-signature`
   for forward-compat. Confirm with Whop dashboard before flipping
   live.

---

## Manual verification steps

1. **Tiers endpoint:**
   ```
   curl -s http://localhost:5001/api/tiers | jq '.tiers | keys'
   # → ["enterprise","growth","pro","starter"]
   ```
2. **Subdomain check:**
   ```
   curl -s 'http://localhost:5001/api/subdomains/check?slug=admin'    # reserved
   curl -s 'http://localhost:5001/api/subdomains/check?slug=newschool' # available
   ```
3. **Tier limit (after running migrations + seeding an org at 100 seats
   on `growth`):**
   ```
   curl -X POST http://localhost:5001/api/admin/organizations/<org>/members/invite \
     -H 'X-User-Id: <owner>' -H 'Content-Type: application/json' \
     -d '{"email":"x@y.com"}'
   # → 402 {"error":"tier_limit_exceeded", "seat_cap":100, ...}
   ```
4. **Webhook signature** (with `WHOP_WEBHOOK_SECRET=test`):
   ```
   BODY='{"action":"membership.went_valid","data":{"id":"m"}}'
   SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac 'test' -hex | cut -d' ' -f2)
   curl -s -X POST http://localhost:3000/api/whop/webhook \
     -H "X-Whop-Signature: $SIG" -H 'Content-Type: application/json' \
     -d "$BODY"
   # 200 (after running migrations). Same call with sig=deadbeef → 401.
   ```
5. **Wizard end-to-end (staging):**
   1. Apply the 4 new migrations.
   2. Set `WHOP_WEBHOOK_SECRET`, `RESEND_API_KEY`, and at least one
      `NEXT_PUBLIC_WHOP_ORG_GROWTH_MONTHLY` plan id.
   3. Visit `/for-schools/start`, sign up, fill steps 2-3, click "Pay"
      on step 4 → land on Whop checkout. Use Whop's test card.
   4. Webhook fires → `organization_billing` row written, org flips to
      `active`, redirect lands on `/for-schools/start/brand?status=paid`.
   5. Pick a palette, hit Continue, send 1 invite — confirm email
      arrives.
6. **Resume:** close the tab after step 2, reopen `/for-schools/start`
   → resumes at the same step with the school name + slug populated.

---

## Working-rules compliance

- ✅ Branch `feat/school-onboarding-phase1` (created off `main`).
- ✅ No `deploy.sh`, no `pm2 restart`, no push to origin.
- ✅ `backend/data/twic/` untouched.
- ✅ No `git add -A` was used (changes are staged file-by-file when
  committing).
- ✅ Build verified with `NODE_OPTIONS="--max-old-space-size=2048"`.
- ✅ Whop org-checkout route modelled on the existing individual
  checkout route — same auth pattern, same metadata format, just
  different `metadata.kind`.
