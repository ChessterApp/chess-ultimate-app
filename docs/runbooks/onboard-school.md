# Runbook: Onboard a new school to Chesster

- **Audience:** Chesster operator (Alex, or any platform admin)
- **Time:** ~10 minutes hands-on, plus 3–10 min cert cold-start
- **Outcome:** A working white-labelled URL `<slug>.chesster.io` handed to the school's owner
- **Reference:** ADR-0005 (subdomain-per-tenant), `supabase/migrations/20260428_001_organizations.sql`, `frontend/src/middleware.ts`

## When to use

A new chess school has agreed to come on the platform and you need to give them a URL the same day. Use this for the default subdomain path — `school.chesster.io`. For a custom domain (`chess.schoolname.com`), see the custom-domain follow-up (deferred until first request per ADR-0005).

## Prerequisites

- Supabase service-role key for the Chesster project (`qtzujwiqzbgyhdgulvcd`) — in `frontend/.env.local` as `SUPABASE_SERVICE_ROLE_KEY`
- Slug picked with the school (lowercase, alphanumeric + hyphen, ≤ 30 chars)
- Slug not in the reserved set: `www`, `api`, `app`, `admin`, `mail`, `staging`, `demo` (demo is in use as a fixture)
- Owner email + display name from the school
- Brand colors (optional — table has sensible defaults)
- The school's owner has, or is willing to create, a Clerk account on `chesster.io`

## Step 1 — Pick and validate the slug

```bash
# from any shell with the service-role key exported:
curl -s \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  "https://qtzujwiqzbgyhdgulvcd.supabase.co/rest/v1/organizations?slug=eq.<slug>&select=slug"
```

Expect `[]`. Non-empty means the slug is taken — pick another.

Also check it doesn't collide with a reserved subdomain (`www`, `api`, `app`, `admin`, `mail`, `staging`, `demo`). The middleware silently returns `null` for those, so the tenant URL would land on the apex marketing page.

## Step 2 — Insert the organization row

```bash
curl -s -X POST \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -H "Prefer: return=representation" \
  "https://qtzujwiqzbgyhdgulvcd.supabase.co/rest/v1/organizations" \
  -d '{
    "slug": "<slug>",
    "name": "<School Display Name>",
    "contact_email": "<owner@school.example>",
    "status": "trial",
    "trial_ends_at": "<YYYY-MM-DDT00:00:00Z, ~30 days out>",
    "primary_color": "#1a73e8",
    "secondary_color": "#ffffff",
    "accent_color": "#ffd700"
  }'
```

Copy the returned `id` (UUID) — you need it for the owner membership in step 4.

Defaults that fire automatically: `created_at`, `updated_at`, branding colours (override if the school sent a palette).

## Step 3 — Warm the SSL certificate

Vercel issues a per-subdomain Let's Encrypt cert via HTTP-01 on first hit. The first request takes 3–10 minutes; subsequent requests are instant. Warm it now so the school's first impression isn't a TLS error:

```bash
# Plain HTTP first — Vercel responds with the redirect even before the cert is issued
curl -sI "http://<slug>.chesster.io/" | head -5

# Then HTTPS — first call may stall or 526; keep polling until it returns 200
until curl -sI -o /dev/null -w "%{http_code}\n" "https://<slug>.chesster.io/" | grep -q "^200$"; do
  echo "waiting for cert…"; sleep 30
done
echo "cert ready"
```

`<slug>.chesster.io` resolves via the wildcard CNAME `* → cname.vercel-dns.com` already configured at Hostinger — no DNS change is needed per tenant.

## Step 4 — Create the owner membership

The school's owner needs a Clerk account (they'll sign up at `chesster.io/sign-up` if they don't have one yet). Once they have a Clerk `user_id` (`user_…`), wire them into the org as owner:

```bash
curl -s -X POST \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  "https://qtzujwiqzbgyhdgulvcd.supabase.co/rest/v1/organization_members" \
  -d '{
    "organization_id": "<org-uuid-from-step-2>",
    "user_id": "<clerk-user-id>",
    "role": "owner",
    "invited_by": "platform"
  }'
```

If the owner doesn't have a Clerk account yet: skip this for now, hand them the URL in step 6 with instructions to sign up first, then come back and run this step.

## Step 5 — Verify

```bash
# 1. Subdomain serves 200
curl -sI "https://<slug>.chesster.io/" | head -3

# 2. Middleware resolves slug → org (lookup hits backend /api/orgs/<slug>)
curl -s "https://<slug>.chesster.io/api/orgs/<slug>" | jq

# 3. Admin shell redirects unauth'd users to apex sign-in (clerk-bypass middleware behaviour)
curl -sI "https://<slug>.chesster.io/admin/dashboard" | grep -i location
# expect: location: https://chesster.io/sign-in?redirect_url=https%3A%2F%2F<slug>.chesster.io%2Fadmin%2Fdashboard
```

If step 2 returns 404 or empty, the row exists but the middleware's 5-minute org cache hasn't expired yet. Either wait 5 min or restart PM2 on the VPS fallback (`pm2 restart chess-frontend`). Vercel pods cycle naturally and don't need this.

## Step 6 — Hand off

Send the school:

- **URL:** `https://<slug>.chesster.io`
- **Admin URL:** `https://<slug>.chesster.io/admin/dashboard`
- **Sign-in:** done on `chesster.io` (apex), redirects back to their subdomain automatically
- **Trial expiry:** the date from step 2

## Step 7 — Log it

Append an entry to `/root/clawd/memory/projects/2026-MM-DD.md` with:

- Slug, org UUID, owner Clerk user_id, trial expiry
- Branding overrides if any (the school's palette)

This is what we grep when a school later asks about their account.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `https://<slug>.chesster.io/` returns 526 / TLS error for >15 min | Let's Encrypt rate-limited or DNS not propagated | Check the wildcard CNAME at Hostinger; `dig <slug>.chesster.io`; if rate-limited, retry tomorrow |
| Subdomain serves the apex marketing page, not the school's branded shell | Slug is in the reserved set, or middleware returned `null` | Re-pick slug (avoid `www`/`api`/`app`/`admin`/`mail`/`staging`/`demo`); restart PM2 if recently inserted |
| `/api/orgs/<slug>` returns 404 | Backend `BACKEND_URL` misconfigured, or row missing | Verify the row from step 2 exists; check `frontend/.env.local` has `BACKEND_URL` pointed at the right host |
| Owner signs in on apex, returns to subdomain, sees student shell instead of admin | `organization_members.role` is wrong, or membership row was never created | Re-run step 4 with `role: "owner"`; user re-signs in to refresh session |
| Admin pages 404 on subdomain instead of redirecting to apex sign-in | `frontend/middleware.ts` (root) has resurfaced and is shadowing `frontend/src/middleware.ts` | `ls frontend/middleware.ts` — should not exist; if it does, move it back to `.trash/` and rebuild |

## Rollback

To remove a school (e.g. trial expired, no conversion):

```bash
# 1. Set status to suspended (preserves data for revival)
curl -s -X PATCH \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  "https://qtzujwiqzbgyhdgulvcd.supabase.co/rest/v1/organizations?id=eq.<org-uuid>" \
  -d '{"status": "suspended"}'

# 2. Hard delete (cascades to organization_members, organization_content, organization_billing)
#    Use only after confirming no recoverable data:
# curl -s -X DELETE \
#   -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
#   -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
#   "https://qtzujwiqzbgyhdgulvcd.supabase.co/rest/v1/organizations?id=eq.<org-uuid>"
```

Subdomain DNS / SSL doesn't need teardown — Vercel garbage-collects unused per-subdomain certs.

## Open follow-ups (from ADR-0005)

- Automated cert-warmup (replace manual step 3 with a script triggered on org INSERT)
- RLS cross-org fuzzer in CI before school #3 — already has a placeholder Ralph job referenced in the recap; revisit before scaling onboarding

## Appendix — Upgrade to a custom domain (paid)

When a school asks to move from `<slug>.chesster.io` to their own host
(e.g. `chess.schoolname.com`), the entire flow is admin-self-serve. See
`docs/prd/custom-domain-flow.md` for the implementation details.

### Prerequisites

- The org row exists (this runbook's main flow has been completed).
- The school's owner can edit DNS at their registrar.
- `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`, `VERCEL_TEAM_ID`, and
  `VERCEL_WEBHOOK_SECRET` are populated in the backend `.env`.

### Walkthrough for the school owner

1. Owner signs in at `<slug>.chesster.io`, navigates to **Admin → Settings →
   Custom Domain**.
2. They enter the domain (lowercase, no `https://`, no trailing dot) and
   submit. The backend calls `POST /v10/projects/.../domains` on Vercel and
   stores `organizations.custom_domain_status = 'pending'`.
3. The page shows the Vercel-returned DNS records (CNAME or A + TXT). Owner
   copies these into their registrar.
4. Once DNS has propagated, owner clicks **"I added the records — verify
   now"**. The backend calls Vercel's verify endpoint; on success the row
   flips to `active` and the page goes green.
5. From this point both `<slug>.chesster.io` *and* the custom host serve the
   tenant. Vercel issues the Let's Encrypt cert on first HTTPS hit
   (same ~3–10 min cold-start as the subdomain path; the verify-success
   poll typically masks the wait).

### Operator checks

```bash
# Confirm the row was updated
curl -s \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  "https://qtzujwiqzbgyhdgulvcd.supabase.co/rest/v1/organizations?id=eq.<org-uuid>&select=custom_domain,custom_domain_status,custom_domain_verified_at" | jq

# Confirm middleware now resolves the custom host to the org
curl -s -H "host: chess.schoolname.com" https://chesster.io/api/admin/organizations/by-custom-domain/chess.schoolname.com | jq
```

### Webhook reception

Vercel posts `domain.verified`, `domain.cert.issued`, and `domain.cert.failed`
events to `https://api.chesster.io/api/webhooks/vercel`. Signature
verification uses HMAC-SHA1 with `VERCEL_WEBHOOK_SECRET`. If the school's
domain is stuck on `pending`, check the backend logs for failed signature
verifications first — that's the usual cause of webhooks being dropped.

### Removing a custom domain

The owner can remove it from the same page (confirms via modal). The backend
calls `DELETE /v9/projects/.../domains/<domain>` on Vercel and nulls the
four custom-domain columns. The school falls back to its `<slug>.chesster.io`
URL automatically.
