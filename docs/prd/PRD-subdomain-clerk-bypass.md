# PRD: Subdomain Clerk Bypass + Shared Session

**Status:** Draft
**Date:** 2026-06-01
**Author:** Alex + clawdbot
**Scope:** Unblock `*.chesster.io` tenant routing without per-tenant Clerk satellite config.

---

## Problem

`demo.chesster.io` returns HTTP 404 (`x-matched-path: /_not-found`) on every Clerk-middleware-touched path. Apex `chesster.io` works. Static asset paths (`/static/*`, `/_next/*`) work on subdomains because the middleware matcher excludes them.

Root cause: `frontend/src/middleware.ts` line 118 calls `await clerk(request, event)` unconditionally. Clerk production instance is registered for `chesster.io` only (one domain, `is_satellite: false`). On a non-registered host, Clerk middleware short-circuits to not-found instead of either pass-through or satellite handoff.

Verified by:
- `curl -H "Host: demo.chesster.io" https://chesster.io/` → 404 (same as direct subdomain hit) — proves host-based 404, not DNS/Vercel routing
- Clerk Domains API: `GET /v1/domains` returns one entry, `chesster.io`, no satellites
- Static asset `/manifest.json` returns 200 only on apex, 404 on subdomain — middleware matcher excludes most static paths but `manifest.json` runs through middleware

## Decision

**B-ii: Skip Clerk middleware on tenant subdomains. Share Clerk session across apex + subdomains via cookie domain `.chesster.io`. Auth-required pages on subdomains redirect to apex sign-in.**

Reasoning vs B-i (Clerk satellite domains): satellite requires per-tenant Dashboard registration + 2 DNS records per tenant + custom cookie config. Doesn't scale to N schools without per-tenant ops. B-ii is one code change that scales forever — onboard a school by inserting one Supabase row.

## Out of Scope

- Tenant-scoped sign-up/sign-in flows on subdomains. Sign-in always happens on apex; after auth, redirect back to subdomain.
- Custom-domain support (`chess.schoolname.com`). Tracked separately in ADR-0005.
- Clerk JWT template for Supabase RLS. Not needed today; current code uses anon/service-role keys (see commit `befd93a` thread).

## Scope of Change

### 1. `frontend/src/middleware.ts`

**Current behavior (line 105–140):** Runs `clerk()` for every request that passes the matcher, regardless of host.

**New behavior:**
- If `isApexHost(request)` → run `clerk()` as today. No change.
- If subdomain (i.e., `extractOrgSlug` returns non-null):
  - **Skip `clerk()` entirely.** Build a plain `NextResponse.next()` instead.
  - Inject `x-org-id` and `x-org-slug` headers via `lookupOrg(slug)` (existing helper).
  - For `isSuperAdminRoute` → already handled (line 112–115), redirect to apex. Keep as-is.
  - For other auth-required routes on subdomain: do NOT call `auth.protect()`. Instead, the page-level SSR check (see §3) decides whether to redirect to apex sign-in.

**Why:** Clerk's middleware is the part that 404s on non-registered hosts. Pages and SSR session reads via `auth()` helper work fine off cookies — those don't require the host to be Clerk-registered.

### 2. Cookie domain — `frontend/src/app/layout.tsx` (ClerkProvider)

Verify `<ClerkProvider>` is configured with a cookie that's readable across `.chesster.io`. Clerk's production cookies (`__session`, `__client`, `__clerk_db_jwt`) are issued by `clerk.chesster.io` (the Clerk FAPI) — Clerk sets them with `domain=.chesster.io` by default when the FAPI lives on `clerk.<apex>`. **Verify this by inspecting `Set-Cookie` headers after a real sign-in.** If they're scoped to `chesster.io` only (no leading dot), the session won't be readable from `demo.chesster.io` and we need to explicitly set the cookie domain.

Likely no code change needed (Clerk's defaults handle this), but verify and document.

### 3. SSR session check for auth-required subdomain pages

Pages that today rely on middleware-enforced `auth.protect()` need a server-side replacement on subdomains. Pattern:

```tsx
// app/admin/dashboard/page.tsx (and similar)
import { auth } from '@clerk/nextjs/server'
import { redirect } from 'next/navigation'
import { headers } from 'next/headers'

export default async function AdminDashboard() {
  const { userId } = await auth()
  if (!userId) {
    const host = (await headers()).get('host') || 'chesster.io'
    const returnUrl = `https://${host}/admin/dashboard`
    redirect(`https://chesster.io/sign-in?redirect_url=${encodeURIComponent(returnUrl)}`)
  }
  // ... rest of page
}
```

**Apply to:** every page under `/admin/*` that today implicitly relied on middleware protection. `/super-admin/*` already redirects to apex (line 112) so no change needed there. Public routes (catalog, tournaments, leaderboard, etc.) stay public.

**Discovery step:** grep for pages that don't currently call `auth()` themselves but live outside `isPublicRoute`. Those are the ones that depend on middleware-level protection.

### 4. Page-level Clerk components on subdomains

`<UserButton />`, `<SignedIn />`, `<SignedOut />` etc. read session from cookies — they work on subdomains as long as cookie domain is `.chesster.io`. No code change expected, but verify the header renders correctly on `demo.chesster.io` after fix.

## Acceptance Criteria

1. `curl -I https://demo.chesster.io/` → HTTP 200 (not 404)
2. `curl -I https://demo.chesster.io/admin/dashboard` → HTTP 307/308 redirect to `https://chesster.io/sign-in?redirect_url=...` (because unauthenticated)
3. `curl -I https://demo.chesster.io/tournaments` → HTTP 200 (public, no auth required)
4. After signing in on apex, navigating to `https://demo.chesster.io/admin/dashboard` does NOT redirect to sign-in — session is shared.
5. `x-org-id` and `x-org-slug` headers are present in response when subdomain is detected.
6. Apex behavior unchanged: `chesster.io` still uses full Clerk middleware, no regression.
7. `/super-admin/*` on a subdomain still 308-redirects to apex (existing behavior preserved).

## Verification Steps

```bash
# 1. Public route on subdomain
curl -I https://demo.chesster.io/tournaments
# Expect: 200

# 2. Auth route on subdomain (unauth) → redirect to apex sign-in
curl -I https://demo.chesster.io/admin/dashboard
# Expect: 307/308 with Location: https://chesster.io/sign-in?...

# 3. Org headers present
curl -sI https://demo.chesster.io/ | grep -iE "^x-org-"
# Expect: x-org-id: 08653c5f-... and x-org-slug: demo

# 4. Apex unchanged
curl -I https://chesster.io/
# Expect: 200, no regression
```

For the cross-domain session test (criterion #4), manual browser check is required — sign in on `chesster.io`, then navigate to `demo.chesster.io/admin/dashboard`. Document result.

## Risks

- **Cookie domain mis-scoped:** If Clerk cookies are scoped to `chesster.io` only (no leading dot), session won't share. Mitigation: verify `Set-Cookie` header explicitly after sign-in; if needed, set explicit cookie domain in ClerkProvider config.
- **Page-level auth checks missed:** Some `/admin/*` page might assume middleware did the gate. Mitigation: explicit SSR `auth()` check added to every non-public page on subdomain path. Audit via grep.
- **CSRF / origin checks:** Clerk validates the request origin for some flows. Sign-in always on apex, so this is contained.
- **Public-route matcher drift:** `isPublicRoute` list in middleware.ts may not match what's actually public. Keep it as the source of truth, audit before ship.

## Implementation Notes for Ralph

- Single migration mode: code change only, no DB migration.
- Tests: add Jest/Vitest unit tests for the middleware host-detection branches if a test runner exists; otherwise lean on the curl-based verification above.
- After implementing, run the verification commands above against `demo.chesster.io` and paste results into PR description.
- If Clerk cookies turn out to be scoped without leading-dot, document the manual ClerkProvider config change required.
- Build + deploy: standard Chesster flow (`npm run build` → copy static → `pm2 restart`) only matters for the VPS fallback; Vercel auto-deploys on push to `main`.
- Commit message: `feat(middleware): bypass Clerk on tenant subdomains, share session via apex`. No `git add -A` — stage `frontend/src/middleware.ts` and any specific `page.tsx` files modified.
- Do not touch `coaching_sessions`, `user_chess_profiles` migration guards. Out of scope.
- Do not register satellite domains in Clerk. Path B-ii avoids that intentionally.

## References

- Original PRD: `PRD-whitelabel-ratings-calendar.md` §2.3 (subdomain routing requirement)
- ADR-0005: `docs/adr/0005-subdomain-per-tenant-with-optional-custom-domain.md` (multi-tenant URL strategy)
- Current middleware: `frontend/src/middleware.ts:105–140`
- Clerk Domains API check: 1 domain registered (`chesster.io`), no satellites
