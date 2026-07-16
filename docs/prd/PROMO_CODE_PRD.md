# Promo Code Flow — Partner School Onboarding (v1: 100% off only)

## Goal
Add a promo-code path to the white-label school onboarding wizard at `/for-schools/start/payment`. v1 supports **100% discount only** — skip Whop entirely and activate the org. Initial code is `FREE`.

## Scope (do not exceed)

### 1. Database (Supabase)
Create migration `frontend/supabase/migrations/<timestamp>_promo_codes.sql`:
```sql
create table if not exists promo_codes (
  code text primary key,
  discount_pct int not null check (discount_pct between 1 and 100),
  max_uses int,                -- null = unlimited
  uses int not null default 0,
  active boolean not null default true,
  expires_at timestamptz,
  created_at timestamptz not null default now()
);
-- seed v1 code
insert into promo_codes (code, discount_pct, max_uses, active)
values ('FREE', 100, null, true)
on conflict (code) do nothing;
```
Apply the migration to the live Supabase project (`qtzujwiqzbgyhdgulvcd`) using the same flow other migrations in this repo use. If unsure, write SQL to a file and ask before executing.

### 2. Backend endpoint
Create `frontend/src/app/api/promo/redeem/route.ts` — `POST`:
- Body: `{ code: string, orgId: string, tier: string, cycle: 'monthly'|'annual' }`
- Auth: Clerk session required; verify caller is org owner of `orgId`
- Validate: code exists, `active=true`, not expired, `uses < max_uses` (or `max_uses` null)
- **v1 constraint:** only accept `discount_pct = 100`. If row has `discount_pct < 100`, respond `400 { error: 'partial_discount_unsupported' }`
- Atomic redeem: `update promo_codes set uses = uses + 1 where code = $1 and (max_uses is null or uses < max_uses) and active = true returning *` — must return 1 row or fail with `409 code_exhausted`
- On success (100% off): insert `org_billing` row (`org_id`, `tier`, `cycle`, `payment_method='promo'`, `promo_code=code`, `status='active'`, `started_at=now()`), update org status to active (mirror what the Whop webhook does for `kind=org_subscription`)
- Response: `{ ok: true, redirect: '/for-schools/start/brand' }`

**Important:** match the exact `org_billing` shape and org-activation side-effects from the existing Whop webhook handler (`frontend/src/app/api/whop/webhook/route.ts`). Read that file first.

### 3. UI on `/for-schools/start/payment`
File: `frontend/src/app/for-schools/start/payment/page.tsx` (or matching client component).
Add **above** the Whop checkout button:
- Heading: "Have a promo code?"
- Text input (`code`) + "Apply" button
- On submit: `fetch('/api/promo/redeem', { method: 'POST', body: JSON.stringify({ code, orgId, tier, cycle }) })`
- States: idle, loading, error (show error string), success → `router.push(data.redirect)`
- Visual: keep consistent with existing wizard styling (tailwind, same card layout)

### 4. Out of scope (do not build)
- Partial discount / Whop coupon API integration
- Admin UI for managing promo codes (manual SQL is fine for v1)
- Email notifications
- Rate-limiting (Clerk auth gate is sufficient for v1)

## Acceptance criteria
- [x] Migration applied; `select * from promo_codes where code='FREE'` returns 1 row
- [x] `POST /api/promo/redeem` with `{code:'FREE', orgId, tier:'starter', cycle:'monthly'}` from authenticated org-owner returns `{ok:true, redirect:'/for-schools/start/brand'}` and creates `org_billing` row + activates org
- [x] Second redeem with same code still works (uses increments, no max_uses cap)
- [x] Invalid code returns `404 { error: 'not_found' }`
- [x] UI on payment page shows promo input; entering `FREE` advances wizard to `/brand`
- [x] Whop button still works (no regression)
- [x] `npm run build` succeeds; lint clean
- [x] After ship: deploy via `bash /root/chess-app/frontend/deploy.sh`

## Notes
- Wizard route: `frontend/src/app/for-schools/start/*`
- Existing Whop org-checkout: `frontend/src/app/api/whop/org-checkout/route.ts`
- Existing Whop webhook (mirror org-activation logic): `frontend/src/app/api/whop/webhook/route.ts`
- Supabase client utility: search `frontend/src/lib/supabase*`
- Clerk org-owner check: search for existing usages of `auth()` + org role checks
