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
