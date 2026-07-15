# Changes — Subdomain Clerk Bypass

Implements PRD-subdomain-clerk-bypass.md.

## Files modified

- `frontend/src/middleware.ts` — split Clerk middleware into two variants:
  `clerk` (apex; enforces `auth.protect()`) and `clerkPassThrough` (tenant
  subdomain; no `auth.protect()`). The Clerk context still runs on subdomains
  so server components can call `auth()`. `/super-admin/*` redirect to apex
  is preserved. `x-pathname` is forwarded so the admin layout can build the
  apex return URL.
- `frontend/src/app/admin/layout.tsx` — when running on a tenant subdomain
  and the user has no session, redirect to
  `https://chesster.io/sign-in?redirect_url=<full-tenant-url>` instead of the
  relative `/sign-in` path (which would 404 since sign-in is only registered
  on the apex Clerk instance).
- `frontend/src/__tests__/middleware.test.ts` — new vitest suite covering
  host detection, the subdomain branch, the super-admin redirect, and
  matcher config.

## File removed

- `frontend/middleware.ts` (old root-level middleware from Phase 1) was
  shadowing `frontend/src/middleware.ts`. It rewrote every tenant subdomain
  request to `/tenant/<slug><pathname>`, but no `/tenant/*` route exists in
  the App Router — every subdomain therefore 404'd. This was the actual
  root cause of the symptoms described in the PRD ("404 on every
  middleware-touched path on `demo.chesster.io`"). The Clerk-on-non-
  registered-host theory in the PRD turned out to be a misread: with the
  shadowing middleware gone, Clerk handles subdomains without 404'ing.

  Backed up to `.trash/frontend-middleware-ts.bak` rather than git-deleted
  in case any of its logic (the `org-role` cookie shortcut, the
  `RESERVED_SUBDOMAINS` set) is wanted later.

## Verification (against local PM2 server via `Host:` header)

```
[#1] subdomain root → HTTP 200 (was 404)
$ curl -sI -H 'Host: demo.chesster.io' http://localhost:3000/
HTTP/1.1 200 OK

[#2] /admin/dashboard on subdomain, unauth → redirect to apex sign-in
$ curl -s -o /tmp/r.html -w "HTTP %{http_code}\n" \
    -H "Host: demo.chesster.io" http://localhost:3000/admin/dashboard
HTTP 200
$ grep -oE 'NEXT_REDIRECT;[^"]*' /tmp/r.html
NEXT_REDIRECT;replace;https://chesster.io/sign-in?redirect_url=https%3A%2F%2Fdemo.chesster.io%2Fadmin%2Fdashboard;307;\

[#3] /tournaments on subdomain (public) → 200
$ curl -sI -H 'Host: demo.chesster.io' http://localhost:3000/tournaments
HTTP/1.1 200 OK

[#5] x-org-id / x-org-slug headers present on subdomain
$ curl -sI -H 'Host: demo.chesster.io' http://localhost:3000/ | grep ^x-org
x-org-id: 08653c5f-ac6b-4f63-83c4-edecf0f91207
x-org-slug: demo

[#6] Apex unchanged → 200
$ curl -sI http://localhost:3000/
HTTP/1.1 200 OK

[#7] /super-admin on subdomain → 308 to apex
$ curl -sI -H 'Host: demo.chesster.io' http://localhost:3000/super-admin
HTTP/1.1 308 Permanent Redirect
location: https://chesster.io/super-admin
```

Note on criterion #2: App Router `redirect()` from a server component
returns HTTP 200 with an embedded `NEXT_REDIRECT` payload on full-document
loads (the browser executes the redirect client-side); RSC requests get a
307. The PRD's "307/308" wording reflects pre-App-Router middleware
behavior — the functional outcome (browser ends up at apex sign-in with
the correct return URL) is what matters and is confirmed in the body
payload.

Criterion #4 (cross-domain session after apex sign-in) requires manual
browser verification on the deployed environment — flagged as a follow-up.

## Tests

```
$ npx vitest run src/__tests__/middleware.test.ts
Test Files  1 passed (1)
     Tests  13 passed (13)
```

---

# Per-org branding completion (2026-06-01)

Implements `docs/prd/per-org-branding-completion.md` (Phase 3 of the white-label arc).

## Files added

- `supabase/migrations/20260601_010_org_branding_storage.sql` — creates the
  public-read `org-branding` Supabase Storage bucket plus SELECT/INSERT/UPDATE/
  DELETE RLS policies on `storage.objects` scoped to the bucket. Writes are
  gated by `is_org_role(<uuid>, ['owner','admin'])` where `<uuid>` is the first
  path segment, so an owner of org A cannot overwrite org B's logo.
- `backend/tests/test_branding_upload.py` — 13 tests covering happy-path uploads
  for png/jpeg/webp/svg/ico, oversize (413), unsupported MIME (415), missing
  file/kind (400), non-member (403), student (403), teacher-as-admin (201, matches
  existing settings PUT gate), and object-key shape (`<org_id>/<kind>.<ext>`).
- `frontend/src/app/api/admin/organizations/[orgId]/branding/upload/route.ts` —
  Clerk-authed Next proxy that forwards multipart bodies to the Flask backend
  with `X-User-Id` injected.
- `frontend/src/lib/org-metadata.ts` — exports `buildMetadata(org)` as a pure
  function so `generateMetadata()` can be unit-tested without spinning Next.
- `frontend/src/lib/__tests__/org-metadata.test.ts` — 3 tests for the metadata
  builder (Chesster defaults survive byte-for-byte when org is null; tenant
  builds title/OG/Twitter/theme-color; OG falls back to default image when no
  logo).
- `frontend/src/app/__tests__/CustomCssInjection.test.tsx` — 6 tests asserting
  the layout's custom_css branch renders `<style>` only when org has CSS, and
  that the server validator contract (the same regex used in the backend)
  rejects `</style>`, `<script>`, and `javascript:` payloads.
- `frontend/src/app/__tests__/SignInTenantBranding.test.tsx` — 2 tests asserting
  the Chesster logo + default heading appear on the apex; tenant logo + name
  appear on a white-label sign-in page.

## Files modified

- `backend/routes/admin.py` — added `_validate_custom_css()` (rejects
  `</style>`, `<script>`, `javascript:`, control chars, ≤50000 chars) called
  from `update_settings()` when `custom_css` is in the body; added
  `POST /api/admin/organizations/<id>/branding/upload` for multipart logo/
  favicon upload (MIME allowlist, 1 MiB cap, stores at `<org_id>/<kind>.<ext>`
  in the `org-branding` bucket via supabase-py service-role client).
- `backend/tests/test_admin_api.py` — extended `TestUpdateSettings` with 5 new
  cases for `favicon_url` (accepted), `custom_css` (accepted when benign,
  rejected for `</style>`, `<script>`, `javascript:`).
- `frontend/src/contexts/organization-types.ts` &
  `frontend/src/contexts/OrganizationContext.tsx` — added `customCss: string |
  null` to the `Organization` type and `DEFAULT_BRANDING`.
- `frontend/src/app/layout.tsx` — replaced the static `metadata` export with
  `generateMetadata()` (via the new `buildMetadata` helper); hoisted
  `fetchOrgData()` and `loadOrgFromHeaders()` into `React.cache()` so a single
  request shares the fetch between `generateMetadata()` and `RootLayout`;
  injects `<style dangerouslySetInnerHTML={{ __html: org.customCss }}/>` into
  `<head>` only when `org !== null` and `customCss` is non-empty (never poisons
  the Chesster apex).
- `frontend/src/app/admin/settings/page.tsx` — added Favicon URL field +
  Upload buttons for both logo and favicon (POSTs to the new upload endpoint
  and auto-saves the returned URL into the org's settings); added a Custom
  CSS `<textarea>` (8 rows, monospace) with the "Advanced — applied site-wide.
  Use at your own risk." help text.
- `frontend/src/app/sign-in/[[...sign-in]]/page.tsx` &
  `frontend/src/app/sign-up/[[...sign-up]]/page.tsx` — switched the hardcoded
  Chesster logo `<Image>` to a conditional that renders `branding.logoUrl`
  when available and falls back to the Chesster logo on the apex; appended `·
  ${branding.name}` to the heading when `isWhiteLabel === true`; replaced the
  hardcoded `colorPrimary: '#9333ea'` in Clerk's `appearance.variables` with
  `branding.primaryColor`.
- `frontend/src/components/__tests__/BrandingInjector.test.tsx` — extended
  with a render test that asserts `--brand-primary` / `--brand-secondary` /
  `--brand-accent` are written on mount and reverted on unmount.

## Test results

- Backend: `pytest -q backend/tests/test_branding_upload.py
  backend/tests/test_admin_api.py` → **37 passed**.
- Backend full suite (excluding two pre-existing collection errors in
  `test_custom_domain_routes.py` / `test_middleware_custom_domain.py`
  caused by an unrelated missing `responses` package, and the live-DB-gated
  RLS suites): **376 passed, 1 skipped**.
- Frontend: 4 new test files = **19 passed** (org-metadata, BrandingInjector
  extension, CustomCssInjection, SignInTenantBranding). Full suite **888
  passed, 2 failed** — both pre-existing on `main` and unrelated to branding
  (sw-version mismatch, coach-route cookies mock).
- Build: `NODE_OPTIONS="--max-old-space-size=2048" npm run build` → success
  (standalone output, includes new
  `/api/admin/organizations/[orgId]/branding/upload` route).

## Manual verification needed (Ralph cannot deploy)

```
curl -s https://acme.chesster.io/sign-in | grep -E \
  '(<title>|theme-color|<link rel="icon"|<style)'
# Expect:
#   <title>Acme Chess — Chess Training</title>
#   <meta name="theme-color" content="#<acme primary>">
#   <link rel="icon" href="https://...supabase.../org-branding/<acme_uuid>/favicon.<ext>">
#   <style>:root { --brand-radius: 12px; … }</style>     (org.custom_css)
#   <img src="https://...supabase.../org-branding/<acme_uuid>/logo.<ext>" alt="Acme Chess">
```

After applying migration 010, an owner of an org must be able to:
1. POST a 50 KB png to `/api/admin/organizations/<id>/branding/upload` with
   `kind=logo` and receive `{ url, key: "<id>/logo.png", kind: "logo" }`.
2. See the URL appear in the Settings form's Logo URL field within ~1 s.
3. Refresh and see `<meta name="theme-color">` + `<link rel="icon">` reflect
   the new branding.
