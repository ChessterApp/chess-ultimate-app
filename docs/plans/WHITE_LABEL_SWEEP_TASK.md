# Task: White-Label Branding Full Sweep + Onboarding Persistence Fix

Repo root: `/root/chess-app`
Frontend: `frontend/` (Next.js 16, deploy via `bash deploy.sh`)
Backend: `backend/` (Flask, systemd unit `chess-backend.service`)
Supabase project ref: `qtzujwiqzbgyhdgulvcd`

## Why this matters

`chess-empire.chesster.io` is a white-label partner-school tenant. The previous fix (commit `e41756d`) wired CORS + Sidebar/Navbar branding. User reports the dashboard STILL shows Chesster branding everywhere — because ~25 more files contain hardcoded "Chesster" / hardcoded logo paths. White-label is the whole point — tenant users must see Chess Empire branding throughout.

Additionally: the onboarding wizard has two persistence bugs that lost Chess Empire's submitted brand data. Must be fixed so future schools don't have the same problem.

## Locked decisions (DO NOT deviate)

1. **AI Coach name on tenants** = `${orgName} Coach` (e.g. "Chess Empire Coach"). NO "Sir" prefix on tenants. Apex still says "Sir Chesster"/"Chesster Coach".
2. **"Powered by Chesster" footer + attribution = KEEPS, DO NOT STRIP.** Both in `TenantLanding.tsx` and in `org-metadata.ts:65` description ("powered by Chesster" stays).
3. **Logo: already uploaded** for Chess Empire by Alex on 2026-06-30 (URL stored at `organizations.logo_url`). Don't try to upload it again. Don't gate any Phase on logo URL being null — if `branding.logoUrl` exists, use it; otherwise neutral fallback.

## Background state (assume true; verify if you must)

- Backend Supabase: `organizations` row for `chess-empire` (id `52b5682c-8c60-4b66-bd19-6ff2d17214eb`) has: `name='Chess Empire'`, `slug='chess-empire'`, `primary_color='#5e1b2c'`, `secondary_color='#ffffff'`, `accent_color='#c2a37f'`, `logo_url='https://qtzujwiqzbgyhdgulvcd.supabase.co/storage/v1/object/public/org-branding/52b5682c-8c60-4b66-bd19-6ff2d17214eb/logo.jpg'`, `status='active'`, `subdomain_status='active'`.
- Branding pipeline (middleware → headers → layout → OrganizationProvider → useBranding) is WORKING. Don't touch middleware or OrganizationProvider.
- CORS is fixed (commit `e41756d`). Don't touch CORS.
- `frontend/.env.local` exists; do NOT regenerate or commit it.
- Build memory cap is 2048MB: `NODE_OPTIONS="--max-old-space-size=2048"`.

## Phase 0 — Onboarding persistence fix (ship FIRST)

**Bug A:** `frontend/src/app/for-schools/start/brand/page.tsx` `saveBrandToOrg()` whitelists only `primary_color, secondary_color, accent_color, favicon_url, custom_css` — omits `logo_url`. Result: any logo collected by `LogoDropzone` on the school page is lost.

Fix: include `logo_url: payload.logo_url ?? null` in the PUT body to `/api/admin/organizations/:id/settings`.

**Bug B:** `backend/routes/onboarding.py` `create_org_self_serve()` inserts only `name, slug, status, contact_email`. Brand fields land via a separate PUT call later, which can race or fail silently.

Fix: at insert time, fetch the caller's `pending_onboarding` row by `clerk_user_id`, merge brand fields from `payload` into the insert: `logo_url, primary_color, secondary_color, accent_color, favicon_url, custom_css, landing_page_config`. Use `.get()` with sane defaults; if `pending_onboarding` row is missing, fall back to current behavior (no crash).

**UX fix:** in the brand-page color pickers in `frontend/src/app/for-schools/start/brand/page.tsx`, add sublabels under each picker label so schools don't invert them:
- Primary: "Buttons, links, headers, highlights"
- Secondary: "Backgrounds, cards"
- Accent: "Badges, accents"

**Tests:**
- Jest: `saveBrandToOrg(payload)` with `payload.logo_url='https://x/logo.png'` → fetch mock receives `logo_url='https://x/logo.png'` in body.
- Pytest: `create_org_self_serve()` with a `pending_onboarding` row containing brand fields → resulting `organizations` row has those brand fields set (mock supabase, assert insert payload).

## Phase 1 — i18n placeholder pattern

- Audit `frontend/src/messages/{en,ru,kz}.json` for literal `"Chesster"` (case-sensitive). Expect ~40 keys × 3 locales.
- Replace literal `"Chesster"` strings with the ICU placeholder `{appName}` ONLY in keys consumed at runtime by `useTranslations()`. Skip docs strings that are inside `t.rich(...)` calls if they break — audit those individually.
- In `frontend/src/app/layout.tsx`, on `<NextIntlClientProvider>` add `defaultTranslationValues={{ appName: org?.name ?? 'Chesster' }}`. (`org` is already resolved in this layout via `loadOrgFromHeaders()`.)
- Apex `chesster.io` continues to show "Chesster" because `org` is null → fallback fires.
- Tenant `chess-empire.chesster.io` shows "Chess Empire" everywhere these strings render.

**Test:** snapshot test that `t('home.hero.title')` resolves to "Chess Empire ..." when `appName='Chess Empire'`, "Chesster ..." when default.

## Phase 2 — Tenant-visible UI surfaces (highest payoff)

Files to modify (consume `useBranding()` from `@/contexts/OrganizationContext` for `name`, `logoUrl`):

- `frontend/src/components/mascot/ChessterMascot.tsx`
- `frontend/src/components/mascot/SpeechBubble.tsx`
- `frontend/src/components/tabs/ChatTab.tsx` — 4 hardcoded logos + "Chesster" coach header
- `frontend/src/app/sign-in/[[...sign-in]]/page.tsx`
- `frontend/src/app/sign-up/[[...sign-up]]/page.tsx`
- `frontend/src/app/not-found.tsx`

Each: replace hardcoded `/static/images/chesster-logo-v3.png` + `alt="Chesster"` with `branding.logoUrl` + `alt={branding.name}` (or with a Server Component equivalent that reads org from headers/context).

KEEP fallback: when `branding === DEFAULT_BRANDING` (apex / no host match), continue rendering Chesster mascot/logo.

`frontend/src/components/tenant/TenantLanding.tsx:156` — DO NOT REMOVE the "Powered by Chesster" footer.

**Verify after this phase:** `curl -s -H "Host: chess-empire.chesster.io" http://localhost:3000/dashboard | grep -oE 'chesster-logo-v3' | wc -l` should drop sharply (ideally 0 for tenant-visible surfaces; >0 on apex is fine).

## Phase 3 — Dynamic PWA manifest + neutral favicon fallback + neutral OG fallback

- Delete `frontend/public/manifest.json` (if present).
- Create `frontend/src/app/manifest.ts` that reads `headers()` → calls existing `fetchOrgData()` (or whatever the layout uses) → returns org-aware MetadataRoute.Manifest with `name`, `theme_color = org.primaryColor`, `background_color = org.secondaryColor`, `icons` (org logo or neutral default).
- Response should include `Vary: Host` + `Cache-Control: max-age=60` to prevent PWA cache poisoning across tenants on the same browser.
- Ship 2 new assets in `frontend/public/static/images/`:
  - `default-favicon.ico` — neutral favicon (white BG, generic crown or empty — NO Chesster mascot)
  - `default-og.png` — 1200×1200, neutral fallback OG image (white BG, generic, NO Chesster mascot)
- Update `frontend/src/lib/org-metadata.ts` so the OG fallback URL is `/static/images/default-og.png` instead of any `chesster-*` path.
- Update `frontend/src/app/layout.tsx` `<link rel="icon">` to use `org?.faviconUrl ?? '/static/images/default-favicon.ico'`.

If you can't easily create neutral PNG/ICO assets in the Ralph loop, create minimal placeholders (1×1 transparent PNG for OG; tiny ICO) and add a TODO comment — these can be re-uploaded by Alex later.

**Test:**
```
curl -s -H "Host: chess-empire.chesster.io" http://localhost:3000/manifest.webmanifest | jq .name
# Expected: "Chess Empire"
curl -s http://localhost:3000/manifest.webmanifest | jq .name
# Expected: "Chesster"
```

## Phase 4 — Clerk dynamic localization

- In `frontend/src/app/layout.tsx`, before `<ClerkProvider>`, build `clerkLocalization` dynamically from `org?.name ?? 'Chesster'`. Use `.replace('${appName}', appName)` against locale string templates so "Sign in to ${appName}", "Sign up for ${appName}", etc. get interpolated.
- Pass dynamic object to `<ClerkProvider localization={...}>`.
- Verify across en/ru/kz where these strings exist.

**Test:** Render `/sign-in` page on `chess-empire.chesster.io`, assert Clerk modal title contains "Chess Empire" (or that the localization object passed to ClerkProvider has `appName` interpolated).

## Phase 5 — Mastra AI coach + metadata

- `frontend/src/lib/org-metadata.ts:65` — KEEP "powered by Chesster" attribution in description. Do NOT remove. Tenant description format is `${org.name} — chess training powered by Chesster.`
- `frontend/src/lib/org-metadata.ts:47` — `keywords` array: exclude `'chessempire'` hardcoded keyword; replace with `${org.slug}` if any tenant-specific keyword is needed.
- `frontend/src/server/mastra/agents/prompt.ts` — replace literal "Chesster" / "Sir Chesster" with `{APP_NAME}` placeholder.
- `frontend/src/server/mastra/agents/index.ts` — thread `orgName` through `requestContext` (alongside provider/model/lang). In `createAgentInstruction` substitute `{APP_NAME}` → `orgName ?? 'Chesster'`. AI coach identity becomes `${orgName} Coach` on tenants (e.g. "Chess Empire Coach"); apex stays "Sir Chesster" / "Chesster Coach".
- Mastra agent `name: 'Chesster'` (internal id) — leave unchanged; not user-visible.

**Test:**
- `org-metadata.test.ts` — assert `buildMetadata(null)` contains "Chesster"; `buildMetadata({ name: 'Chess Empire', ... })` description includes "Chess Empire" and "powered by Chesster".
- `mastra/prompt.test.ts` — `createAgentInstruction({ orgName: 'Chess Empire', ... })` returns prompt containing "Chess Empire Coach" and zero hardcoded "Sir Chesster".

## Phase 6 — Docs / settings sweep

- 6 `frontend/src/components/docs/Render*.tsx` files (~50 hardcoded "Chesster" strings).
- `frontend/src/libs/docs/helper.ts` FAQ data.
- Replace each tenant-visible literal "Chesster" with `t('key', { appName })` or `useBranding().name`.
- Out-of-scope (skip): super-admin UI, apex landing page strings.

## Promo-redemption guardrail (small but important)

- Already shipped: `/api/promo/redeem` forces enterprise/annual on `discount_pct=100`. Don't change that.
- Add unit test if not already present asserting redemption with FREE code → `subscription_tier='enterprise'` AND `billing_period='annual'` AND `redeemed_promo_code='FREE'` in `organization_billing`.

## How to ship

Phases ship as atomic commits. After each phase, run quick smoke (curl + grep) before moving to the next. After all phases:

1. Build the frontend with memory cap: `cd /root/chess-app/frontend && export HOME=/root && NODE_OPTIONS="--max-old-space-size=2048" npm run build`
2. Deploy via canonical script: `cd /root/chess-app/frontend && export HOME=/root && bash deploy.sh` (handles static asset copy, .env.local copy, pm2 restart, HTTP 200 verification)
3. Backend has no changes other than Phase 0 (`onboarding.py`) and the promo redeem test. Restart backend if Phase 0 modified Python: `systemctl restart chess-backend.service`
4. Verify backend health: `curl -s http://localhost:5001/api/health` should return 200.

## Final verification (must pass before declaring done)

```bash
# Tenant should show Chess Empire everywhere on /dashboard
curl -s -H "Host: chess-empire.chesster.io" http://localhost:3000/dashboard \
  | grep -ciE '(chesster-logo|>Chesster<|alt="Chesster"|Sir Chesster)'
# Expected: very low (only fallbacks or the legit "Powered by Chesster" attribution if rendered)

# Apex still shows Chesster
curl -s http://localhost:3000/ | grep -c 'Chesster'
# Expected: > 0

# Tenant page title
curl -s -H "Host: chess-empire.chesster.io" http://localhost:3000/dashboard \
  | grep -oE '<title>[^<]*</title>'
# Expected: <title>Chess Empire — Chess Training</title>

# Dynamic manifest
curl -s -H "Host: chess-empire.chesster.io" http://localhost:3000/manifest.webmanifest | jq -r .name
# Expected: Chess Empire

# Branding endpoint still returns logo_url
curl -s -H "Origin: https://chess-empire.chesster.io" \
  https://api.chesster.io/api/admin/organizations/by-slug/chess-empire \
  | jq -r '.logo_url, .primary_color, .secondary_color, .accent_color'
# Expected: 4 lines, all non-null, primary=#5e1b2c, secondary=#ffffff, accent=#c2a37f
```

## Git conventions

- Never `git add -A`. Stage specific files.
- One conventional commit per phase. Format: `feat(white-label): phase N — <short>`.
- `export HOME=/root` before any git or pm2 command.

## Done criteria

- All 7 phases (Phase 0 + Phases 1-6) shipped as commits to `main`.
- Frontend deployed via `deploy.sh`. `chess-frontend` PM2 process online.
- Backend restarted via systemd if `onboarding.py` was touched.
- Final verification checks above all pass.
- Tests added for Phase 0, Phase 5, and the promo guardrail.
- No regressions on apex `chesster.io` — Chesster branding intact.
