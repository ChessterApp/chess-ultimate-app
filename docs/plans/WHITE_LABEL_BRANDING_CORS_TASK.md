# White-Label Branding + CORS Fixes for tenant subdomains

## Context

After the white-label auto-provisioning work shipped (commit `eb7be79`), tenant subdomains like `https://chess-empire.chesster.io` now serve TLS-valid 200s. But two production bugs remain:

1. **CORS rejects every backend API call** from tenant subdomains.
   The backend at `api.chesster.io` uses a static origin whitelist seeded only from `CORS_ALLOWED_ORIGINS` (`chesster.io`, `www.chesster.io`, `vps.chesster.io`). Any tenant subdomain — including `chess-empire.chesster.io` — is silently dropped during preflight. The user dashboard renders as an empty shell with console full of `No 'Access-Control-Allow-Origin' header` errors.

2. **The regular user shell ignores tenant branding.**
   The org IS resolved end-to-end (middleware extracts slug, backend lookup works, `OrganizationProvider` mounts, HTML for `/` contains "Chess Empire", brand CSS vars set). But two visible chrome components hardcode `/static/images/chesster-logo-v3.png` and the literal text `"Chesster"`:
   - `frontend/src/components/ui/DesktopSidebar.tsx:151-152` (desktop user dashboard sidebar)
   - `frontend/src/components/Navbar.tsx:28` (mobile top bar)

   `AdminSidebar.tsx` already consumes `useBranding()` correctly — use it as the template.

The data-side color swap and Vercel domain registration are already done — those are not Ralph's job.

## Files to Change

### 1. Backend CORS — `/root/chess-app/backend/app.py`

Lines 98-111 currently:
```python
# Configure CORS with environment-based origins
flask_env = os.getenv('FLASK_ENV', 'production')
cors_origins_str = os.getenv('CORS_ALLOWED_ORIGINS', 'https://chesster.io,https://www.chesster.io')
cors_origins = [origin.strip() for origin in cors_origins_str.split(',')]

# Allow localhost in development only
if flask_env == 'development':
    if 'http://localhost:3000' not in cors_origins:
        cors_origins.append('http://localhost:3000')
    logger.info(f"CORS enabled for development origins: {cors_origins}")
else:
    logger.info(f"CORS enabled for production origins: {cors_origins}")

CORS(app, origins=cors_origins, supports_credentials=True)
```

Replace with (use Flask-CORS regex support — `origins=` accepts compiled patterns):
```python
import re  # if not already imported at top of file — move to module imports

# Configure CORS with environment-based origins + tenant-subdomain wildcard.
flask_env = os.getenv('FLASK_ENV', 'production')
cors_origins_str = os.getenv('CORS_ALLOWED_ORIGINS', 'https://chesster.io,https://www.chesster.io')
cors_origins = [o.strip() for o in cors_origins_str.split(',') if o.strip()]

# White-label tenant subdomains: every {slug}.chesster.io is self-provisioned via
# onboarding, so a static whitelist doesn't scale. A regex covers the whole namespace
# (excluding the apex, which is already listed explicitly).
cors_origins.append(re.compile(r'^https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.chesster\.io$'))

if flask_env == 'development':
    if 'http://localhost:3000' not in cors_origins:
        cors_origins.append('http://localhost:3000')
    logger.info(f"CORS enabled for development origins: {cors_origins}")
else:
    logger.info(f"CORS enabled for production origins: {cors_origins}")

CORS(app, origins=cors_origins, supports_credentials=True)
```

Notes:
- Put `import re` with the other stdlib imports at the top of the file if not already present (don't introduce a local import inside the CORS block).
- The regex requires the subdomain label to start/end with alphanumerics — RFC-compliant slug shape, also matches what `onboarding.py` validates.
- Custom domains (`organizations.custom_domain`) are explicitly out of scope. No tenant uses one yet.

### 2. DesktopSidebar — `/root/chess-app/frontend/src/components/ui/DesktopSidebar.tsx`

Current (lines 150-153):
```tsx
<div className={`h-16 flex items-center border-b border-gray-100 dark:border-[#2a2a2a] px-3 ${collapsed ? 'justify-center' : 'gap-2'}`}>
  <Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={28} height={28} />
  {!collapsed && <span className="font-bold text-gray-900 dark:text-gray-100 text-lg">Chesster</span>}
</div>
```

Required changes:
- Add import `import { useBranding } from '@/contexts/OrganizationContext';`
- Inside the component (alongside other hook calls), `const branding = useBranding();`
- Replace the logo block:
  ```tsx
  <div className={`h-16 flex items-center border-b border-gray-100 dark:border-[#2a2a2a] px-3 ${collapsed ? 'justify-center' : 'gap-2'}`}>
    {branding.logoUrl ? (
      // Tenant logos live on Supabase Storage which isn't in next.config images.remotePatterns,
      // so use a plain <img> instead of next/image. (Out-of-scope follow-up: register the pattern.)
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={branding.logoUrl}
        alt={branding.name}
        width={28}
        height={28}
        className="h-7 w-7 rounded object-cover"
      />
    ) : (
      <Image
        src="/static/images/chesster-logo-v3.png"
        alt={branding.name}
        width={28}
        height={28}
      />
    )}
    {!collapsed && (
      <span className="font-bold text-gray-900 dark:text-gray-100 text-lg truncate">
        {branding.name}
      </span>
    )}
  </div>
  ```

### 3. Mobile Navbar — `/root/chess-app/frontend/src/components/Navbar.tsx`

Current (line 28):
```tsx
<Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={24} height={24} className="w-6 h-6" unoptimized /> Chesster
```

Same treatment:
- `import { useBranding } from '@/contexts/OrganizationContext';`
- `const branding = useBranding();` inside `NavBar()`
- Replace the logo+label inside the button:
  ```tsx
  {branding.logoUrl ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={branding.logoUrl} alt={branding.name} width={24} height={24} className="w-6 h-6 rounded object-cover" />
  ) : (
    <Image src="/static/images/chesster-logo-v3.png" alt={branding.name} width={24} height={24} className="w-6 h-6" unoptimized />
  )}{' '}
  {branding.name}
  ```

## Tests (required)

### Backend — `backend/tests/test_cors_tenant_subdomain.py` (new)
Use the existing Flask test-client pattern (look at sibling tests like `backend/tests/test_admin_routes.py` for the import pattern and fixture style). Cover:
1. Preflight OPTIONS from `https://chess-empire.chesster.io` → response has `Access-Control-Allow-Origin: https://chess-empire.chesster.io` and `Access-Control-Allow-Credentials: true`.
2. Preflight OPTIONS from arbitrary `https://random-tenant-7.chesster.io` → passes (regex hit).
3. Preflight OPTIONS from `https://chesster.io` (apex) → passes (explicit whitelist).
4. Preflight OPTIONS from `https://evil.example.com` → **no** `Access-Control-Allow-Origin` header.
5. Preflight OPTIONS from `https://chesster.io.evil.com` (suffix-spoofing attempt) → rejected.

If `pytest` is the test runner (check `backend/pytest.ini` or `backend/conftest.py`), use it. Otherwise fall back to whatever the existing tests use.

### Frontend — extend tests next to the components
Look at `frontend/src/app/__tests__/SignInTenantBranding.test.tsx` for the pattern (it already tests `useBranding` consumers). Add:
- A test for `DesktopSidebar` rendering `branding.name` from a provided `OrganizationProvider` value.
- A test for `Navbar` doing the same.
- A test confirming the default Chesster brand renders when `OrganizationProvider` value is `null` (i.e., apex domain — non-regression).

Use whatever test runner the existing frontend tests use (likely Jest + React Testing Library — `frontend/jest.config.*`).

## Deployment

After the code lands and tests pass:

1. **Backend** — restart via systemd (NOT pm2; backend is managed by `chess-backend.service`):
   ```bash
   systemctl restart chess-backend.service
   sleep 2
   systemctl is-active chess-backend.service
   ```
   Verify it came up: `curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5001/api/health` (or whatever the existing health endpoint is — check `app.py` for the route).

2. **Frontend** — use the canonical deploy script (do NOT re-implement build/copy steps):
   ```bash
   export HOME=/root && bash /root/chess-app/frontend/deploy.sh
   ```
   The script already handles build + static asset copy + .env.local + PM2 restart + HTTP 200 verify. The standalone layout is **flat** (`standalone/server.js`).

## Verification (must pass before declaring done)

Run these curl checks from the VPS and paste the relevant output lines into the final report:

1. **Tenant preflight accepted:**
   ```bash
   curl -sI -X OPTIONS \
     -H 'Origin: https://chess-empire.chesster.io' \
     -H 'Access-Control-Request-Method: GET' \
     -H 'Access-Control-Request-Headers: authorization,content-type' \
     https://api.chesster.io/api/courses | grep -i access-control
   ```
   Expect `access-control-allow-origin: https://chess-empire.chesster.io` + `access-control-allow-credentials: true`.

2. **Arbitrary tenant accepted (regex coverage):**
   ```bash
   curl -sI -X OPTIONS -H 'Origin: https://demo.chesster.io' \
     -H 'Access-Control-Request-Method: GET' \
     https://api.chesster.io/api/courses | grep -i access-control
   ```

3. **Hostile origin rejected:**
   ```bash
   curl -sI -X OPTIONS -H 'Origin: https://evil.example.com' \
     -H 'Access-Control-Request-Method: GET' \
     https://api.chesster.io/api/courses | grep -i access-control || echo "OK: no ACAO header"
   ```

4. **Suffix-spoof rejected:**
   ```bash
   curl -sI -X OPTIONS -H 'Origin: https://chesster.io.evil.com' \
     -H 'Access-Control-Request-Method: GET' \
     https://api.chesster.io/api/courses | grep -i access-control || echo "OK: no ACAO header"
   ```

5. **Tenant HTML still renders "Chess Empire":**
   ```bash
   curl -sI https://chess-empire.chesster.io/dashboard | head -5
   curl -s https://chess-empire.chesster.io/ | grep -oE '<title>[^<]+</title>'
   ```

6. **Apex still says "Chesster" (non-regression):**
   ```bash
   curl -s https://chesster.io/ | grep -oE '<title>[^<]+</title>'
   ```

## Out of Scope

- Custom-domain CORS (per-org allowlist) — defer until a tenant configures one.
- Phase-2 white-labeling of sign-in, sign-up, landing, onboarding, mascot, ChatTab AI Coach. Most are apex-domain auth flows.
- `next.config.ts` `images.remotePatterns` for Supabase Storage logo URLs (we sidestep with `<img>` fallback).
- DB seed cleanup for Chess Empire (color swap already executed; logo upload is on Alex via `/admin/settings`).

## Git Conventions

- Never `git add -A` — stage files by path.
- Commit message format: `fix(white-label): allow tenant subdomain CORS + wire branding into user shell`
- Include co-author trailer `Co-Authored-By: Ralph <ralph@anthropic.com>` if Ralph adds one by default.
