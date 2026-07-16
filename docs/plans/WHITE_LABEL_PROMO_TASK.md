# Task — White-label subdomain auto-registration + FREE-promo enterprise upgrade

Spec reference: `/root/.claude/plans/cosmic-mixing-wall.md` (read this FIRST before coding).

**Background (already done by operator — do NOT redo, but read for context):**
- `chess-empire.chesster.io` has been manually added to the Vercel `frontend` project (`prj_ycg49JAEzpwGdPIAO0FrH0TlVTp8`, team `team_6FoBro4yL0zJCNICQPZ8Qsjg`). Cert is live, HTTP/2 200 verified.
- Chess Empire org `52b5682c-8c60-4b66-bd19-6ff2d17214eb` was manually flipped from `starter` → `enterprise` in `organization_billing`. Confirmed via REST.

**Your job — productionize the fix so this never needs manual intervention again.**

---

## Task list (work each to verified completion; do NOT skip tests)

### T1 — Schema migration: subdomain status
File: `supabase/migrations/20260630_015_org_subdomain_status.sql`

```sql
ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS subdomain_status TEXT,
  ADD COLUMN IF NOT EXISTS subdomain_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS subdomain_vercel_id TEXT,
  ADD COLUMN IF NOT EXISTS subdomain_last_error TEXT;

ALTER TABLE organizations
  DROP CONSTRAINT IF EXISTS organizations_subdomain_status_check;

ALTER TABLE organizations
  ADD CONSTRAINT organizations_subdomain_status_check
  CHECK (subdomain_status IN ('pending','verifying','active','failed') OR subdomain_status IS NULL);

CREATE INDEX IF NOT EXISTS idx_org_subdomain_status
  ON organizations (subdomain_status) WHERE subdomain_status IS NOT NULL;
```

### T2 — Schema migration: track which promo each org redeemed
File: `supabase/migrations/20260630_016_org_billing_promo_code.sql`

```sql
ALTER TABLE organization_billing
  ADD COLUMN IF NOT EXISTS redeemed_promo_code TEXT,
  ADD COLUMN IF NOT EXISTS redeemed_promo_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_org_billing_promo_code
  ON organization_billing (redeemed_promo_code)
  WHERE redeemed_promo_code IS NOT NULL;

COMMENT ON COLUMN organization_billing.redeemed_promo_code IS
  'Promo code redeemed at signup (e.g. ''FREE''). NULL for paid (Whop) flows.';
```

Apply both migrations to the Supabase prod project (`qtzujwiqzbgyhdgulvcd`). Credentials in `/root/clawd/CREDENTIALS.md`. Direct DB URL works; or use Supabase REST + `pg` via psql. Verify column existence after applying.

### T3 — Vercel client helper
File: `backend/services/vercel_client.py`

Add near the top (after imports, before `class VercelAPIError`):

```python
APEX_DOMAIN = 'chesster.io'

def subdomain_for_slug(slug: str) -> str:
    return f'{slug}.{APEX_DOMAIN}'
```

Export from `__all__` if one exists. No behavior change yet.

### T4 — Wire `add_domain` into org creation
File: `backend/routes/onboarding.py`, function `create_org_self_serve()`.

Right after `org_id = org_row['id']` (~line 173), add a best-effort Vercel registration. Wrap in try/except. NEVER let Vercel failure crash the signup. Status mapping:

- `add_domain` success with `verified=True` → set `subdomain_status='active'`, `subdomain_verified_at=now()`, `subdomain_vercel_id=<response.id or response.name>`
- `add_domain` success with `verified=False` → `subdomain_status='pending'`, `subdomain_vercel_id=<response.id>`
- `VercelAPIError` with `code='domain_already_in_use'` → treat as success, `subdomain_status='pending'` (will be verified async)
- Any other `VercelAPIError` → `subdomain_status='failed'`, record `subdomain_last_error=str(exc)`, log loudly

Use the same pattern as `add_custom_domain` in `backend/routes/admin.py` (lines 757-812). Reuse `get_client()` from `services.vercel_client`.

Persist by `supabase.table('organizations').update({...}).eq('id', org_id).execute()`.

### T5 — Force enterprise on FREE promo redemption
File: `frontend/src/app/api/promo/redeem/route.ts`

When the promo has `discount_pct === 100`, override the requested `tier` to `'enterprise'` and the requested `cycle` to `'annual'` (max value, best for the partner). Log the override. Also stamp `redeemed_promo_code` and `redeemed_promo_at` on the billing upsert.

Behavior contract:
- If `promo.code === 'FREE'` OR `promo.discount_pct === 100`: final tier = `'enterprise'`, final cycle = `'annual'`. Override is silent to the client (the response still returns `{ ok: true, redirect }`), but recorded server-side.
- Partial-discount path stays as before (already returns 400 in current code, so unaffected).

Update the test file `frontend/src/app/api/promo/redeem/__tests__/route.test.ts` to cover:
1. FREE redemption with `tier='starter'` body → DB shows `plan='enterprise'`, `billing_cycle='annual'`, `redeemed_promo_code='FREE'`.
2. FREE redemption with `tier='growth'` body → same as above.
3. (Future-proof) hypothetical 50%-off code currently returns `partial_discount_unsupported` — keep that test green.

### T6 — Admin verify-subdomain endpoint
File: `backend/routes/admin.py`

Add `POST /organizations/<org_id>/subdomain/verify` mirroring the existing `verify_custom_domain` endpoint (~line 870 area). It should:
- Resolve org by id, look up `slug`
- Call `get_client().get_domain(subdomain_for_slug(slug))`
- If `verified=True`: update `subdomain_status='active'`, `subdomain_verified_at=now()`
- Else: keep `subdomain_status='pending'`
- Return JSON with current state. Same auth gating as `verify_custom_domain`.

### T7 — Wire `remove_domain` into org deletion
File: `backend/services/org_deletion.py`

In the hard-delete finalizer, before the org row drops, call `get_client().remove_domain(subdomain_for_slug(slug))` inside try/except — failure logs but does not block deletion. Mirror pattern from `admin.py:921-927`.

### T8 — Backfill script
New file: `backend/scripts/backfill_subdomains.py`

CLI: `python scripts/backfill_subdomains.py [--dry-run] [--slug SLUG]`

Behavior:
- Query `organizations` where `status IN ('trial','active') AND deletion_requested_at IS NULL AND (subdomain_status IS NULL OR subdomain_status != 'active')`.
- For each row: try `add_domain(subdomain_for_slug(slug))`. Handle `domain_already_in_use` idempotently (then call `get_domain` to learn verified state). Update DB.
- Sleep 0.5s between rows for Vercel rate-limit safety.
- Log result per row.

Run it once after deploy: `python backend/scripts/backfill_subdomains.py`. Verify Chess Empire flips to `subdomain_status='active'`.

### T9 — Tests
- Run backend pytest suite. Add tests for `create_org_self_serve` happy path (mocking `vercel_client.get_client`) covering: domain registered + verified, domain pending, `domain_already_in_use`, generic Vercel failure → status='failed' but signup still 201.
- Run frontend `npm test` (covers the promo route override).

### T10 — Build + deploy
- Frontend: `cd frontend && export HOME=/root && NODE_OPTIONS="--max-old-space-size=2048" npm run build`
- Static asset + standalone wiring per `/root/chess-app/CLAUDE.md`
- `pm2 restart chess-frontend`
- Restart backend: `pm2 restart chess-backend` (or whatever the process name is — `pm2 list` to confirm)
- `curl localhost:3000` returns 200
- `curl https://chesster.io/api/promo/redeem -X POST` returns 401 (unauth — expected; means route is live)

### T11 — Post-deploy verification
- Apply migrations (T1+T2) IF not yet applied
- Run `python backend/scripts/backfill_subdomains.py` → Chess Empire row shows `subdomain_status='active'`
- DB SQL: `select slug, subdomain_status, subdomain_vercel_id from organizations where slug='chess-empire';` shows `active`
- DB SQL: `select plan, redeemed_promo_code from organization_billing where organization_id='52b5682c-8c60-4b66-bd19-6ff2d17214eb';` — note: redeemed_promo_code may be null for chess-empire since it was redeemed before this code shipped. That's fine — leave it null for the historical row.

---

## Constraints

- Never use `git add -A` — stage specific files
- Never commit `.env*` or any keys
- Never set `model` field on sub-agent spawns
- Test before claiming done. Use the actual pytest / npm test runners.
- Use `trash` (not `rm`) if you need to delete anything
- All file paths above are absolute; treat them as canonical

## Stack reminders

- Frontend: Next.js 16 + TypeScript, Clerk auth, Supabase via `@/lib/supabase-admin`
- Backend: Python Flask, supabase-py client, native venv (no Docker). Tests: `pytest backend/tests/`
- Vercel client: `backend/services/vercel_client.py` already has `add_domain`, `get_domain`, `verify_domain`, `remove_domain`, raises `VercelAPIError`
- DB: Supabase project `qtzujwiqzbgyhdgulvcd`. Service role key in `/root/clawd/CREDENTIALS.md` (`sb_secret_REDACTED`)

When done, write a final summary to `/root/clawd/memory/2026-06-30.md` and report exit.
