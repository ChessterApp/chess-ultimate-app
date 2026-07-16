# PRD — Self-Serve School Onboarding & White-Label Activation

**Owner:** Alex (Kuroki)
**Author:** clawdbot
**Status:** Draft v1.0
**Created:** 2026-06-02
**Target launch:** Phase 1 (MVP) — 4 weeks from approval; Phase 2 (polish) — 8 weeks
**Codebase:** `/root/chess-app/` (Next.js 16 frontend + Flask backend)
**Related PRD:** `PRD-whitelabel-ratings-calendar.md` (foundation already built)

---

## 0. TL;DR

Today a partner school becomes a Chesster tenant only if Alex personally hits the super-admin API and hand-holds them through branding. We're going to replace that with a self-serve flow that takes a school director from "I just heard about Chesster" → "my fully-branded chess platform is live with my logo, my colors, my domain, and 50 of my students invited" — in under **15 minutes**, with **zero human in the loop on our side**.

The bar is Linear/Vercel/Notion-tier polish. Every screen is opinionated, beautiful, and feels obvious. No empty states without illustrations. No "submit" without a live preview of what just changed. No payment screen without a clear "what you get / what you pay" recap.

---

## 0.5 What's Already Built (REUSE — do not rebuild)

A previous white-label backend PRD already shipped substantial infrastructure. The wizard described below **wraps and orchestrates** these existing surfaces — it does not reimplement them. Audit confirmed (2026-06-02):

| Capability | Where it lives | How the wizard uses it |
|---|---|---|
| **Org creation API** | `POST /api/super-admin/organizations` (`backend/routes/super_admin.py:778-847`) — creates `organizations` + `organization_members` + syncs to Clerk | Step 2 (after payment) calls this server-side; wizard does not duplicate the insert logic |
| **Logo upload + storage** | `POST /api/admin/organizations/<id>/branding/upload` (`backend/routes/admin.py:322-382`) — Supabase `org-branding/<org_id>/`, MIME-validated, 1 MiB cap | Step 2 + Step 5 hit this endpoint directly |
| **Brand fields (DB)** | `organizations` table: `primary_color`, `secondary_color`, `accent_color`, `custom_css`, `favicon_url`, `landing_page_config` JSONB | Step 5 writes via existing `PUT /api/admin/organizations/<id>/settings` |
| **Brand settings UI** | `frontend/src/app/admin/settings/page.tsx:130-326` (full form) — saves via existing settings API | Step 5 reuses the same field components inside the wizard shell |
| **Runtime branding** | `<BrandingInjector>` swaps `--brand-primary/--brand-secondary/--brand-accent` CSS vars on mount (`frontend/src/components/BrandingInjector.tsx:10-26`) | Live preview applies brand instantly with zero rebuild |
| **Custom domain (Pro+)** | **Fully wired** — UI states pending→verifying→active→failed (`frontend/src/app/admin/settings/domain/page.tsx:181-302`), Vercel API integration (`backend/routes/admin.py:552-732`, `backend/services/vercel_client.py`), migration `20260601_009_org_custom_domain.sql` | Step 5 embeds the existing `/admin/settings/domain` flow as a collapsed sub-step |
| **Subdomain routing** | `frontend/src/middleware.ts:50-213` — resolves subdomain + custom domain + apex with 5-min cache; injects `x-org-id`/`x-org-slug` headers; super-admin gated to apex (line 164-170) | Live preview iframe loads at `<slug>.chesster.io` — routing already handles it |
| **Role gating** | `frontend/src/app/admin/layout.tsx:8` — allows `owner | admin | teacher` only | No change; wizard delivers `owner` on org creation |
| **Whop individual checkout (template)** | `frontend/src/app/api/whop/checkout/route.ts` — works, passes `metadata[clerk_user_id]` | Step 4's new org-checkout route is modeled on this — minimal new code |
| **PostHog instrumentation** | Wired in `frontend/src/instrumentation-client.ts` | §6.8 just adds event names; no SDK install |

**What this means for scope:** Step 5 ("Brand customization") and the custom-domain flow are **integration work**, not greenfield. The biggest new builds are the wizard shell itself, the org-level Whop checkout/webhook, tier enforcement, real invite emails, and `pending_onboarding` state.

---

## 1. Goals & Non-Goals

### Goals
1. **Time-to-first-student-invited < 15 min** for a school director who's never seen Chesster.
2. **Zero manual provisioning** from our side for tiers Starter → Pro. (Enterprise stays sales-led.)
3. **Activation rate ≥ 60%** of signups complete payment + brand setup + first invite in the same session.
4. **NPS ≥ 60** on a 1-question post-onboarding survey ("How likely are you to recommend Chesster to another school?").
5. **Refund/regret rate < 5%** in first 14 days.

### Non-goals (v1)
- Multi-currency / localized pricing beyond USD + KZT (Kazakhstan is primary market — Whop supports both).
- Self-serve plan downgrade. Upgrades automatic, downgrades require email to support (prevents abuse).
- Marketplace of plug-in features (course bundles, additional analytics modules). Future PRD.
- White-label mobile apps. Web only for now.
- Migration importer from competitor LMS (Chess.com, ChessKid, etc.). Backlog.

---

## 2. Personas

| Persona | Description | What they care about |
|---|---|---|
| **Director Dinara** (primary) | Runs Almaty Chess Academy, 80 students, 6 coaches. Non-technical. Has tried Google Classroom + a WhatsApp group, hates both. | "Will my parents think this is *my* app?" — branding is emotional, not cosmetic. Price clarity. Easy student invites. |
| **Founder Farid** (secondary) | Solo chess coach launching an online school. 12 students today, wants to grow. | Cheap entry tier. Pro tools available as he scales. |
| **Operations Olya** (assistant) | The director's assistant doing the actual setup work on the director's behalf. | Step-by-step clarity. Ability to save & resume. Bulk import for student lists. |

---

## 3. Pricing & Tier Matrix

Tiered by **max student seats + features**. Billed via **Whop** (already integrated for individual plans — extend to orgs).

**Tier identifiers match the codebase** — the existing `organization_billing.plan` enum is `starter | growth | enterprise` and the placeholder UI at `frontend/src/app/admin/billing/page.tsx:5-10` already lists `Starter / Growth / Pro / Enterprise`. We adopt those names verbatim (only DB change: ADD VALUE `'pro'`) so we never have to rename across the codebase. Pricing + seat limits below are the proposed anchors — open for review (see §12).

| Tier (code id) | Display name | Max students | Price/mo (USD) | White-label features | Best for |
|---|---|---|---|---|---|
| `starter` | **Starter** | 25 | $49 | Logo + colors + subdomain (`yourschool.chesster.io`) | Solo coaches, micro-schools |
| `growth` | **Growth** | 100 | $129 | + Custom CSS + favicon + branded login page | Growing schools |
| `pro` *(new enum value)* | **Pro** | 300 | $299 | + Custom domain (`yourdomain.com`) + branded email sender + landing-page hero | Established academies |
| `enterprise` | **Enterprise** | Unlimited | Contact sales | + SSO + multi-branch + dedicated CSM + SLA | Multi-location franchises |

> ⚠️ The placeholder UI ships `Starter $0 / Growth $29 / Pro $79 / Enterprise null`. Those numbers are placeholders disconnected from the DB. The numbers above replace them, but the **tier identifiers stay** to avoid touching every file that imports the placeholder constants.

**Annual billing:** −15% (push hard in UI — improves cash + reduces churn).

**Free 14-day trial?** No — paid upfront per Alex's decision. **However:** 30-day money-back guarantee is offered, prominent on checkout. Lowers psychological friction to "yes" without giving away the product.

**Overage policy:** When school is at 90% of seat limit, banner appears in admin dashboard suggesting upgrade. At 100%, invite button disables with a "Tier limit reached — upgrade?" CTA. **No hidden charges, no surprise upgrades.**

---

## 4. The Self-Serve Onboarding Flow (the spine of this PRD)

Top-of-funnel entry: `chesster.io/for-schools` (new marketing page) → CTA "Launch your school in 15 minutes" → starts the wizard at `chesster.io/for-schools/start`.

> **Route choice — why not `/onboard`?** The path `/onboarding` is already claimed by the 1,261-line **player** onboarding wizard at `frontend/src/app/onboarding/page.tsx` (skill assessment, Chess.com import, Whop paywall). A one-letter difference (`/onboard` vs `/onboarding`) is a footgun for analytics + marketing links + middleware rules. We namespace the school wizard under the existing `/for-schools` marketing surface instead, leaving the player flow untouched.

The wizard is a **6-step single-page application** with a persistent right-side **live preview panel** that updates as the user types. Left rail = form, right rail = what their school will look like.

### Visual structure (every step)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Chesster logo  [Progress: ●●●○○○ Step 3 of 6]   Save & exit  →     │
├──────────────────────────────────┬──────────────────────────────────┤
│                                  │                                  │
│   FORM (left, 45%)               │   LIVE PREVIEW (right, 55%)      │
│                                  │                                  │
│   - Single focus per step        │   - Real subdomain preview        │
│   - Big inputs, generous space   │   - Updates on every keystroke    │
│   - Inline validation            │   - Mobile/desktop toggle         │
│   - "Why we ask" tooltips        │   - Skeleton placeholders         │
│                                  │     where input is missing        │
│                                  │                                  │
├──────────────────────────────────┴──────────────────────────────────┤
│  [← Back]                                            [Continue →]   │
└─────────────────────────────────────────────────────────────────────┘
```

Persistent rules:
- **Autosave on every field blur** to `localStorage` + (post-signup) `pending_onboarding` table. User can close the tab and resume from anywhere.
- **Progress bar** is clickable; can jump back to completed steps.
- **No modal popups.** Inline validation, inline errors.
- **Big primary button** at bottom-right (44px tall, brand color), disabled until step is valid.
- **Keyboard shortcuts:** `Enter` advances, `Esc` saves & closes.

---

### Step 1 — Account creation

**Goal:** identify the director.

```
Welcome. Let's launch your chess school.

[Sign up with Google]   [Sign up with email]

Already have a Chesster account?  Sign in →
```

- Clerk handles auth. Email magic-link or Google OAuth.
- After signup, immediately ask for **full name** + **phone number** (used for support + WhatsApp activation handoff in KZ). Phone is optional with explanation.
- **Right preview:** Shows a "Welcome, [Name]" mockup of their admin dashboard with their avatar in the corner. The visual reward for typing.

**Conversion trick:** Before showing the form, headline says: *"You're 4 minutes away from a branded chess platform."* Set the expectation.

---

### Step 2 — School identity

**Goal:** name + subdomain + logo.

Form fields:
1. **School name** — text input, e.g. "Almaty Chess Academy"
2. **Choose your URL** — input with `[slug].chesster.io` shown live. Auto-generated from school name (slugified, lowercased, hyphenated), editable.
   - Inline check: green ✓ "available" or red ✗ "taken — try [suggestion]"
   - Reserved slugs blocked (admin, super-admin, www, app, api, etc.)
3. **Upload logo** — drag-and-drop + click. PNG/SVG recommended. Live cropper if non-square. Skippable but greyed-out CTA encourages it.
4. **What kind of school are you?** (single-select chips: Offline school · Online school · Solo coach · Tournament organizer) — used for personalized post-onboarding content + analytics.

**Right preview:** A live mockup of `[slug].chesster.io` homepage showing the logo + school name in the header, default Chesster colors. As they upload the logo, it slides into the preview header.

**The "wow" moment of step 2:** The first time they see their logo on a real-looking dashboard, before paying. This converts.

---

### Step 3 — Tier selection

**Goal:** pick a plan, anchored to their student count.

Top of step: **Student count slider** — "How many students will you have on Chesster?" 1 → 500+. As they slide, the tier card matching their need lights up.

```
   ░░░░▓▓░░░░░░░░░░░░░░  ←─ 80 students
   
   ✨ We recommend the Growth plan.
```

Below: 4 tier cards horizontally. Recommended tier has a glowing border + "Most popular" ribbon if it's Growth.

Each card shows:
- Tier name + price (toggle: monthly / annual −15%)
- "Up to X students"
- Bulleted feature list with ✓
- Soft-disabled features (greyed) from higher tiers for upsell intent
- Big "Select [Tier]" button

**Annual toggle** at top of grid — defaults to monthly, but annual savings number animates when toggled.

**Enterprise** card has "Talk to sales" button → opens Calendly inline.

**Right preview:** swaps to a feature-comparison mockup specific to the hovered tier — "With Growth, you'd get this branded login screen ↓"

---

### Step 4 — Payment

**Goal:** charge the card via Whop.

```
You're signing up for:  Growth · monthly
$129 / month · billed today

[Logo of school]  Almaty Chess Academy
                  almatychess.chesster.io

✓ Up to 100 students
✓ Custom CSS + favicon
✓ Branded login page

──────────────────────────────────
Pay with card                     [Whop checkout iframe]
──────────────────────────────────

🛡️ 30-day money-back guarantee. Cancel anytime.
🇰🇿 Also accept Kaspi (KZT) — toggle below.
```

- **Whop checkout** embedded inline (don't redirect — keep them in the wizard).
- **Trust signals:** money-back guarantee, "Used by 200+ schools" (when true), small logos of partner schools (when we have them).
- **Receipt preview:** Below the payment form, a small "What you'll be billed today" recap so there's zero surprise.
- **On success:** Whop webhook fires → backend marks `organizations.status='active'` + `organization_billing.plan='growth'` + `organization_billing.student_count=100`. Wizard advances.

**Codebase touch points:**
- New endpoint: `POST /api/whop/org-checkout` (frontend) — extends existing `/api/whop/checkout/route.ts` to accept `organization_id` + `tier` and pass to Whop with org metadata.
- Webhook update: `frontend/src/app/api/whop/webhook/route.ts` — handle `membership.went_valid` events where metadata.kind === "org" — upsert `organization_billing` instead of `subscriptions`.
- New env vars: `NEXT_PUBLIC_WHOP_ORG_STARTER_PLAN`, `..._GROWTH_PLAN`, `..._PRO_PLAN`, monthly + annual variants.

---

### Step 5 — Brand customization (the magic step)

**Goal:** make their app feel like *their* app, with instant gratification.

Split-screen, but the **preview becomes interactive**: they can click around their own dashboard preview, switch pages (Home / Courses / Puzzles / Login), and watch their branding apply everywhere.

Left rail controls:
1. **Brand colors** — primary / secondary / accent
   - 12 preset palettes (chess-themed: classic, royal, forest, midnight, sunrise, etc.) → one click applies a curated combo.
   - "Custom" reveals 3 color pickers + a "Generate from logo" button (extracts dominant colors from uploaded logo — uses `node-vibrant` or similar).
   - Live preview updates instantly.
2. **Favicon** — auto-generated from logo or upload custom.
3. **Hero headline** — text input, defaults to "Welcome to {school name} — your chess journey starts here." Editable inline in the preview itself (click-to-edit).
4. **Custom CSS** (Growth+ only) — collapsed by default. Monaco editor with autocomplete + a "What variables can I use?" link → tooltip with `--brand-primary`, etc. Has a "Reset" button.
5. **Custom domain** (Pro+ only) — collapsed by default. Input field + step-by-step DNS instructions with copy-to-clipboard for CNAME values. Status pill: `Pending → Verifying → Active`. (Backend: existing custom-domain flow in `admin.py` + Vercel API — already wired, just embed it.)

**Right preview behaviors:**
- Top toolbar: `Desktop | Tablet | Mobile` toggle
- Quick-nav chips below the preview: `Dashboard · Courses · Puzzles · Login` (Phase 1) → adds `Home` (public landing) in Phase 2
- Frame chrome: shows `https://almatychess.chesster.io` in a stylized browser bar — drives home that this is THEIR real URL.

**Preview scope — Phase 1 vs Phase 2:**
- **Phase 1** previews the **dashboard surface** (`/admin`, `/dashboard`, `/courses`, `/puzzles`, `/login`). These already render `<BrandingInjector>` and consume `--brand-*` CSS vars (`frontend/src/components/BrandingInjector.tsx:10-26`), so the wizard can iframe a live tenant URL and brand swaps apply instantly with no extra build.
- **Phase 2** adds the **public landing page** preview at the tenant root (`https://<slug>.chesster.io/`). The DB already stores `landing_page_config` JSONB on `organizations`, but **no public renderer exists yet** — the tenant subdomain has no `/` route that consumes those fields. Building that renderer is the gate for previewing the marketing surface, so it's deferred to Phase 2 rather than blocking the wizard MVP.

**Smart defaults:** if they skip everything, defaults are still beautiful (Chesster's design system with their logo on top). Skipping is OK — they can return to `/admin/settings` later. Encouraged to spend at least 30s here for the "wow" effect.

**End-of-step CTA:** A celebratory banner appears: *"Looking sharp. Let's get your students in →"*

---

### Step 6 — Invite students

**Goal:** get the first student in. **This is the activation event** for the whole product.

Three import paths, presented as tabs:

1. **Add one at a time** — name + email + (optional) phone. "+Add another" button. Up to 5 inline.
2. **Paste a list** — textarea. Format detected automatically (comma, newline, semicolon, tab). Live parses into a table preview below. Validates emails inline.
3. **Upload CSV** — drag-and-drop. Required columns: `email`. Optional: `first_name`, `last_name`, `rating`, `phone`. Maps columns visually (column-mapper UI like Linear). Shows a 5-row preview before commit.

Each invitee can be assigned a **role**: Student (default) / Teacher / Admin. Bulk-set via dropdown above the table.

Before sending:
- **Invitation preview** — opens a side drawer showing the exact email the student will receive, with the school's logo and brand colors applied. They can edit the subject + body inline. This is *huge* for director confidence: they see exactly what their parents/students will receive.

**Send invites** → backend:
- Creates `organization_members` rows with `user_id = "invite:<email>"` (existing pattern, `admin.py:166`).
- **NEW:** Triggers actual email via Resend (replacing the current stub at `admin.py:164`). Uses the org's branded sender (Pro+) or `noreply@chesster.io` (Starter/Growth).
- Tracks invite analytics: sent / opened / clicked / accepted.

**Tier-limit enforcement here:**
- If they try to invite more than their seat count, the over-limit invites are queued with a soft warning: *"You're inviting 110 students but Growth includes 100. Upgrade to Pro or remove 10 to send all invites."*
- "Upgrade" CTA goes directly to a one-click plan-switch in Whop.

**Final screen — the activation moment:**

```
🎉 Almaty Chess Academy is live.

Your platform:  almatychess.chesster.io
Students invited:  47
Plan:  Growth · $129/mo

[Take me to my dashboard →]

────────────────────────────────────────
Bookmark these links for later:
• Your school: https://almatychess.chesster.io
• Admin: https://almatychess.chesster.io/admin
• Support: support@chesster.io
```

Confetti animation. We've earned it.

Background side-effect: a welcome email lands in the director's inbox with the same info, plus a Loom from Alex (recorded once, reused) walking them through the dashboard.

---

## 5. Post-onboarding: the first 24h

Equally important. Most schools quit in the first 24h if they hit a wall.

- **In-dashboard onboarding checklist** (sidebar widget, dismissible per item):
  - [ ] Invite your first student ✓ (pre-checked from wizard)
  - [ ] Upload your first course
  - [ ] Customize your homepage hero
  - [ ] Set up your custom domain (Pro+)
  - [ ] Visit your school as a student (impersonation toggle)
- **Day 1 email** (24h after signup): "Have your students logged in yet?" — checks accepted-invite count, sends tips if 0.
- **Day 3 email:** "Here's how Almaty Chess Academy can run their first online tournament."
- **Day 7 email:** "Quick check-in — anything blocking you?" with a Calendly link to Alex for the first 100 schools.
- **In-app intercom-style chat** (Crisp.chat — free tier) for first-week support.

---

## 6. Backend & Infrastructure Work

Concrete changes needed, mapped to existing files.

### 6.0 Tier reconciliation (PREREQUISITE — must land first)

**Conflict found in audit:** three sources of truth disagreed on tier names.
- DB enum `organization_billing.plan` (`migrations/20260428_001:61-62`): `starter | growth | enterprise`
- Hardcoded UI placeholder (`frontend/src/app/admin/billing/page.tsx:5-10`): `Starter (0/10) · Growth (29/50) · Pro (79/200) · Enterprise (null/null)` — placeholder, disconnected from DB
- This PRD's earlier draft proposed: `Spark · Studio · Scale · Empire`

**Decision:** **Codebase names win** — the DB enum and the existing UI placeholder names stay. The PRD adopts them so nothing already shipped has to be renamed. The only DB change is adding a fourth value `'pro'` to bridge the gap between the 3-value enum and the 4-tier UI/PRD.

**Migration plan:**
1. **New migration** `20260603_001_tier_add_pro.sql`:
   ```sql
   ALTER TYPE organization_plan ADD VALUE IF NOT EXISTS 'pro';
   ```
   That's the entire schema change. No renames, no backfills, no risk to existing rows. (Postgres `ADD VALUE` is online-safe; cannot run inside a transaction block — flag for ops.)
2. **Canonical source of truth:** `backend/services/tier_quota.py` (introduced in §6.3) exports the canonical tier map keyed by enum value (`starter`, `growth`, `pro`, `enterprise`). Frontend imports via `GET /api/tiers` instead of hardcoding.
3. **Replace** the hardcoded `TIERS` constant in `frontend/src/app/admin/billing/page.tsx:5-10` with a fetch from `/api/tiers` so the placeholder prices (`$0 / $29 / $79 / null`) are superseded by the live values from §3.
4. **No search-and-replace pass needed** — the existing enum strings (`starter`, `growth`, `enterprise`) are preserved as-is across the codebase. Only new code introduces `pro`.

**Rollback:** drop the new `'pro'` value (Postgres requires recreating the type — documented in the migration file as a separate `down.sql`).

**Display vs. identifier convention:** API + DB use lowercase enum values (`starter`, `growth`, `pro`, `enterprise`). UI capitalizes for display (`Starter`, `Growth`, `Pro`, `Enterprise`). This split already exists in `billing/page.tsx` — we keep it.

### 6.1 Org-level Whop checkout (new)

**Phase 1 SECURITY blocker (also in this section):** the current Whop webhook handler at `frontend/src/app/api/whop/webhook/route.ts` has **no signature verification**. `WHOP_WEBHOOK_SECRET` is empty in `.env.local` and no HMAC check exists in code. Any caller can POST to this endpoint and forge a "membership.went_valid" event — granting themselves a paid org. **Must fix in Phase 1, not Phase 2.**

- **Add HMAC verification** at the top of the webhook handler — verify `Whop-Signature` header against `WHOP_WEBHOOK_SECRET` using `crypto.timingSafeEqual`. Reject with 401 on mismatch.
- **Set** `WHOP_WEBHOOK_SECRET` in env (rotate the value when wiring; coordinate with Whop dashboard).
- **Log + alert** on signature failures (PostHog event `whop_webhook_signature_invalid` + Sentry).
- **Test fixture:** Add `frontend/tests/whop-webhook.spec.ts` covering valid + invalid signatures.
- **Add** `frontend/src/app/api/whop/org-checkout/route.ts` — extends individual checkout. Accepts `{ tier, billing_cycle, organization_id }`. Returns Whop checkout URL with `metadata: { kind: "org", organization_id, tier }`.
- **Update** `frontend/src/app/api/whop/webhook/route.ts` — switch on `metadata.kind`:
  - `"individual"` (existing) → write `subscriptions`
  - `"org"` (new) → upsert `organization_billing` with plan, student_count from tier, status='active'. Update `organizations.status='active'`.
- **`organization_billing` schema gap.** Current columns (`migrations/20260428_001:56-70`) are **Stripe-shaped** (`stripe_customer_id`, `stripe_subscription_id`) but Whop is the actual processor. Migration `20260603_003_org_billing_whop_columns.sql` adds **nullable** `whop_membership_id`, `whop_user_id`, `whop_plan_id`, `billing_cycle` columns alongside the Stripe ones. Stripe columns are kept (not dropped, not renamed) so any code still referencing them keeps compiling — they just stay null until/unless we ever wire Stripe.

### 6.2 Pre-payment org state (new)
- **New table:** `pending_onboarding` (Supabase migration). Columns: `id`, `clerk_user_id`, `school_name`, `slug`, `logo_url`, `tier`, `billing_cycle`, `step`, `data` (JSONB), `created_at`, `updated_at`.
- Lets users save & resume the wizard before paying.
- On payment success, promote `pending_onboarding` → `organizations` + `organization_billing`.

### 6.3 Tier enforcement (NEW — current gap)
- **New module:** `backend/services/tier_quota.py`
  - `def get_seat_limit(org_id) -> int`
  - `def get_current_seat_count(org_id) -> int`
  - `def can_invite(org_id, n: int = 1) -> tuple[bool, dict]` — returns reason if false.
- **Enforcement hook** in `backend/routes/admin.py` `POST /organizations/<id>/members/invite` (line 144) — call `can_invite()` first, return 402 with body `{ "error": "tier_limit_exceeded", "limit": 100, "current": 100, "upgrade_url": "..." }` if blocked.
- **Frontend** handles 402 by showing inline upgrade CTA.

### 6.4 Real invite emails (replace stub at `admin.py:164`)
- Use **Resend** (cheap, simple, supports custom sender domains).
- New helper `backend/services/email.py` with `send_invite_email(org_id, invitee_email, role)`.
- Template uses org's brand colors + logo. Pulled from `organizations` table.
- Custom sender (e.g. `invites@yourdomain.com`) for Pro+ tier — requires Resend domain verification flow (TBD subspec).

### 6.5 Subdomain availability check (new)
- **New endpoint:** `GET /api/admin/organizations/slug-available?slug=astanachess`
- Returns `{ available: bool, suggestions?: string[] }`.
- Blocks reserved slugs (admin, api, www, app, super-admin, ...).

### 6.6 Bulk invite (new)
- **New endpoint:** `POST /api/admin/organizations/<id>/members/bulk-invite`
- Accepts `[{email, first_name, last_name, role, ...}]`. Validates all emails up-front. Atomic with tier quota check.
- Returns per-row success/failure.

### 6.7 Logo color extraction (frontend-only)
- Add `node-vibrant` dependency.
- On logo upload, run extraction, suggest a 3-color palette in step 5.

### 6.8 Analytics events (new)
Track in PostHog (or whatever's wired):
- `onboarding_started`, `onboarding_step_completed` (with step number), `onboarding_abandoned` (with last step), `org_payment_succeeded`, `org_first_invite_sent`, `org_activated` (= payment + ≥1 invite).

---

## 7. Edge Cases & Failure Modes

| Scenario | Behavior |
|---|---|
| User abandons mid-wizard | Wizard state persists in `localStorage` + `pending_onboarding`. Email at 1h/24h/7d offering "Pick up where you left off — your school name is reserved for 14 days." |
| Subdomain taken between availability check and submit | Server-side re-check on org creation. If taken, error inline with new suggestion. |
| Whop webhook fails / delayed | Wizard shows "Activating your school… (this usually takes 5s)". After 30s, fallback message: "Payment received, your school will be ready in a few minutes. We'll email you." On webhook receipt, send activation email. |
| Card declined | Inline error from Whop. Don't lose any wizard state. |
| User pays but slug becomes invalid | Block at step 2 — slug locked once they hit "Continue". |
| Custom domain DNS not propagated yet | Status pill stays "Verifying". Re-check every 30s for 1 hour, then every 5 min for 24h. Email when active. |
| Tier downgrade mid-billing-cycle | Not allowed self-serve. Email support. |
| Tier upgrade auto-prorate | Yes — Whop handles proration. |
| School wants to delete their account | "Delete school" in admin settings → confirmation flow (type school name to confirm) → emails Alex + sets `organizations.deletion_requested_at = now()` (new nullable timestamptz column — added via migration `20260603_002_org_deletion_requested.sql`). Hard delete after 30d. **Why a timestamp instead of a new enum value:** the existing `organization.status` enum is `active | suspended | trial` and is read in 12+ places; extending it would force a cascade of switch-statement updates. A nullable timestamp is additive and never collides. |
| Director leaves, hands off to assistant | Owner role can transfer ownership in `/admin/settings/team`. |

---

## 8. Design System & Component Inventory

We need (or reuse) these components — most exist in the current Chesster design system:

**Reuse:**
- Button (primary/secondary/ghost), Input, Select, Card, Toast, Drawer, Modal

**Build new:**
- `<SchoolOnboardingShell>` — wizard layout with progress bar + autosave (named to disambiguate from any reusable `OnboardingShell` the player wizard at `/onboarding/*` might later extract)
- `<LivePreviewFrame>` — iframe-based preview of subdomain with brand applied
- `<SlugAvailabilityInput>` — debounced input with availability check
- `<ColorPalettePicker>` — preset palettes + custom pickers
- `<CSVImporter>` — drag-drop + column mapper
- `<TierCard>` — pricing card with recommended badge
- `<InvitePreviewDrawer>` — branded email preview
- `<ActivationConfetti>` — final-step animation

**Design tokens:**
- Stick with Chesster's existing design system colors as the **default** preview state.
- All preview overrides use CSS custom properties so the preview iframe can swap them instantly without reload.

---

## 9. Copywriting Principles

- **Second person, present tense.** "Your school" not "the school".
- **One verb per CTA.** "Continue", "Pay & launch", "Send invites".
- **No corporate speak.** Replace "Submit" with "Looks good — let's go".
- **Specific numbers everywhere.** "Up to 100 students", not "Many students".
- **Reassurance before commitment.** "30-day money-back guarantee" appears 3 times in the flow.

---

## 10. Metrics (post-launch)

| Metric | Target | How measured |
|---|---|---|
| Onboarding completion rate | ≥ 60% | PostHog funnel: `onboarding_started` → `org_first_invite_sent` |
| Time-to-payment (median) | ≤ 7 min | `step_1_complete` → `org_payment_succeeded` |
| Time-to-first-invite (median) | ≤ 12 min | `org_payment_succeeded` → `org_first_invite_sent` |
| 7-day student-acceptance rate | ≥ 40% | `invite_sent` → `invite_accepted` in 7d |
| 30-day refund rate | < 5% | Whop refund webhooks |
| NPS | ≥ 60 | 1-question survey at day 14 |

---

## 11. Phased Rollout

### 11.0 Phase Gate: Unit Tests (compulsory, every phase)

**No phase ships without tests.** Each phase must close with a green test suite covering every new service, route, component, and migration assertion shipped in that phase. The completion report (`.ralphy/phase<N>-report.md`) must include a test-pass line copied from the runner output (e.g. `backend 47/47, frontend 38/38`). A phase with code merged but tests missing is **not** considered Done — it goes back to the implementor.

**Per-phase test requirements:**

| Surface | What must be tested |
|---|---|
| Backend service (`backend/services/*.py`) | One `test_<service>.py` covering happy path + every documented failure mode |
| Backend route (`backend/routes/*.py`) | One `test_<route>.py` with auth-required, validation-rejected, and success cases |
| Frontend API route (`frontend/src/app/api/**/route.ts`) | One `__tests__/route.test.ts` covering 200, 4xx, 5xx branches |
| Frontend state / hook / lib (`frontend/src/{components,lib,hooks}/**`) | One `__tests__/<name>.test.ts(x)` for any logic that isn't pure JSX |
| Migration (`backend/migrations/*.sql`) | A migration test or a service test that asserts the new column/enum/table is read/written correctly |
| Whop / Resend / Clerk webhook | A signature / payload-shape test using a fixture of a real provider payload |

**Run command per phase** (must be reproducible from a clean checkout):

```bash
# backend
cd /root/chess-app/backend && python3 -m pytest tests/ -v --tb=short

# frontend
cd /root/chess-app/frontend && npx vitest run
```

A phase report lacking either count is treated as a failed handoff.

### 11.1 Phase 1 — MVP (4 weeks)
Everything in §4 (the 6-step wizard) and §6.0–6.5. Tier enforcement live. Real invite emails. Starter + Growth + Pro tiers only (Enterprise = "talk to sales" button). Live preview scoped to the dashboard surface (see §5).

**Cut for v1:** public tenant landing-page renderer + preview, custom-domain status-polling polish, logo color extraction, branded email senders, in-dashboard onboarding checklist.

**Phase 1 test stamp (2026-06-02, commit `3e76cc5`):**
- Backend: **33/33 passing** — `test_tier_quota.py` (11), `test_email_service.py` (4), `test_invite_tier_enforcement.py` (2), `test_subdomains.py` (7), `test_onboarding_routes.py` (9)
- Frontend: **27/27 passing** — `api/whop/webhook/__tests__/verify.test.ts`, `api/whop/org-checkout/__tests__/route.test.ts`, `components/school-onboarding/__tests__/WizardState.test.ts`, `lib/__tests__/tiers.test.ts`
- **Gate cleared. Phase 1 unblocked for merge once §14 checklist is signed off.**

### 11.2 Phase 2 — Polish (weeks 5–8)
- Public tenant landing-page renderer at `<slug>.chesster.io/` consuming `landing_page_config` → unlocks the landing-page tab in the wizard live preview
- Custom-domain Pro-tier polish + Vercel deep integration
- Logo color extraction (`node-vibrant`)
- Branded email senders (Resend domain verification flow)
- In-dashboard 24h onboarding checklist
- Day 1 / 3 / 7 lifecycle emails
- CSV importer with smart column mapping
- Annual billing prorate

**Phase 2 test gate (must land before merge):**
- Renderer: snapshot + branding-injection test for `<slug>.chesster.io/` page
- CSV importer: unit tests for column-mapper, dedupe, and tier-cap-aware partial import
- Lifecycle emails: scheduler tests + template snapshot tests
- Domain verification: state-machine test (`pending → verifying → active → failed`) against mocked Vercel responses
- Onboarding checklist: hook test for completion-percentage calculation
- **Numeric target: backend ≥ 50 passing, frontend ≥ 45 passing** (Phase 1 baseline + Phase 2 deltas)

### 11.3 Phase 3 — Scale-up (weeks 9–12)
- Enterprise tier self-serve (with sales-assist option still)
- Multi-branch support
- Ownership transfer flow
- Refund automation
- Loom + intercom support

**Phase 3 test gate (must land before merge):**
- Multi-branch: scoping test — branch admin cannot read/write rows from sibling branches
- Ownership transfer: state-machine test covering invite-pending, accepted, revoked, expired
- Refund automation: idempotency test (replay same Whop refund webhook twice → one DB write)
- Enterprise self-serve: tier-quota test for `enterprise` confirming uncapped behavior under realistic loads
- **Numeric target: backend ≥ 70 passing, frontend ≥ 60 passing**

**Phase 3 test stamp (2026-06-03):**
- Backend: **770 passing** (Phase 2 baseline 606 → +164 this phase). Phase 3 new tests:
  `test_branches_service.py` (24), `test_branches_routes.py` (15),
  `test_refunds_service.py` (25), `test_refunds_routes.py` (9),
  `test_enterprise_service.py` (15), `test_enterprise_tier_quota_load.py` (17),
  `test_ownership_transfer_service.py` (25), `test_ownership_transfer_routes.py` (16).
- Frontend: **1072 passing** (Phase 2 baseline 980 → +92 this phase).
  `lib/__tests__/refunds.test.ts` (23), `enterprise.test.ts` (9),
  `ownership-transfer.test.ts` (15), `intercom.test.ts` (12), `loom.test.ts` (16),
  plus proxy-route tests (15) and 4 added enterprise cases on the org-checkout suite.
- All four §11.3 gates green. See `.ralphy/phase3-report.md` for details.

---

## 12. Open Questions

1. **Pricing anchor — confirm USD numbers.** $49 / $129 / $299 for Starter / Growth / Pro are my proposals based on competitor scan (Chess.com Class, ChessKid Schools, Lichess for schools is free but unbranded). The placeholder UI currently shows `$0 / $29 / $79 / null` — those are obviously placeholders, but I want explicit confirmation before we replace them. Should we A/B test or commit?
2. **Annual −15% — generous enough?** Common is 17–20%. Worth testing.
3. **Trial offer — really no trial?** A *time-limited preview* (7 days, can invite up to 3 students, no payment) might lift conversion 20–40%. Trade-off: more no-shows. Worth a Phase 2 A/B test.
4. **Enterprise pricing model** — flat fee + per-student, or pure flat? Need 2–3 reference customer conversations.
5. **Sales handoff** — when an Enterprise prospect books a call, does it go to Alex directly or eventually a junior AE? Affects Calendly setup.
6. **KZT pricing parity** — at current FX ($1 ≈ 540 KZT), Starter = 26,500 KZT. Round to local-friendly numbers (24,900 / 64,900 / 149,900)?
7. **Refund policy nuance** — full refund any time in 30 days, or prorated? Whop supports both.

---

## 13. Risks

- **Whop org-checkout endpoint doesn't exist yet** — building it is the longest-pole task. Mitigation: spike day 1 of Phase 1 to confirm Whop API supports our pattern (it should — `metadata` field is documented).
- **Subdomain DNS race conditions** — handled by middleware lookup pattern that already exists (`src/middleware.ts:50-71`).
- **Email deliverability** for invites — Resend has good defaults but custom-sender domains take effort to verify. Hence Pro+ only.
- **Director uploads bad logo** (low-res, transparent background mismatched to dark mode, etc.) — auto-detect and warn with a "Looks like your logo might not look great on dark backgrounds — preview both ↓".

---

## 14. Definition of Done (Phase 1)

- [x] **Unit tests green** — backend 33/33, frontend 27/27 on commit `3e76cc5` (see §11.1)
- [ ] A director can complete steps 1–6 in ≤ 15 minutes on the staging env, hitting real Whop + real email + real subdomain.
- [ ] All tier seat limits enforced at the API level (tested with curl against staging).
- [ ] Wizard autosaves; closing the tab and reopening resumes from the same step.
- [ ] All inline validation handles edge cases (taken slug, bad email, declined card, file too big).
- [ ] Mobile + tablet + desktop responsive in the wizard.
- [ ] Three real partner schools onboarded end-to-end in user testing.

**A test gate identical to §11.0 applies to every subsequent phase — unchecked test box = not Done.**

---

## Appendix A — Wizard URL Map

All wizard URLs live under `/for-schools/start/*` so they never collide with the existing player wizard at `/onboarding/*`.

| URL | Step |
|---|---|
| `/for-schools` | Marketing landing (CTA → wizard) |
| `/for-schools/start` | Step 1: Account |
| `/for-schools/start/school` | Step 2: Identity |
| `/for-schools/start/plan` | Step 3: Tier |
| `/for-schools/start/payment` | Step 4: Pay |
| `/for-schools/start/brand` | Step 5: Brand |
| `/for-schools/start/invite` | Step 6: Invite |
| `/for-schools/start/done` | Activation screen |

Each step deep-linkable. Auth-gated except step 1.

**Reserved for the existing player flow (do not touch):** `/onboarding/*` — 1,261-line skill-assessment + Chess.com/Lichess import + Whop paywall wizard for individual players.

## Appendix B — Suggested folder structure

```
frontend/src/app/for-schools/
  page.tsx                    # Marketing landing → CTA into wizard
  start/
    layout.tsx                # SchoolOnboardingShell (renamed from OnboardingShell to avoid collision with player flow)
    page.tsx                  # Step 1 (account)
    school/page.tsx           # Step 2
    plan/page.tsx             # Step 3
    payment/page.tsx          # Step 4
    brand/page.tsx            # Step 5
    invite/page.tsx           # Step 6
    done/page.tsx             # Activation
    _components/
      LivePreviewFrame.tsx
      SlugAvailabilityInput.tsx
      ColorPalettePicker.tsx
      TierCard.tsx
      CSVImporter.tsx
      InvitePreviewDrawer.tsx
```

> Leave `frontend/src/app/onboarding/` (the existing player wizard) and its components untouched. The `SchoolOnboardingShell` name disambiguates from any future shared `OnboardingShell` primitive.

```
backend/
  services/
    tier_quota.py
    email.py
  routes/
    onboarding.py             # pending_onboarding CRUD
    admin.py                  # extended invite + slug check
```

---

**End of PRD.**
