# Phase 3 — Self-Serve School Onboarding (Scale-up) Completion Report

**Date:** 2026-06-03
**Branch:** main
**Scope:** PRD §11.3 (Phase 3 — five features)

---

## 1. Summary per scope item

### #1 Enterprise tier self-serve
- Plan-page gating relaxed (`canAdvance` now allows `tier='enterprise'`)
  while the **Talk-to-sales Calendly** link remains as an alternate CTA
  on the enterprise card.
- New SSO toggle on the enterprise card (`sso-enabled-toggle`) wired into
  the wizard state and stamped into Whop checkout metadata.
- `frontend/src/app/api/whop/org-checkout/route.ts` accepts
  `tier='enterprise'` + `sso_enabled` and forwards them in
  `metadata[sso_enabled]`.
- Backend `services/enterprise.py`: `is_enterprise`, `enforce_uncapped`,
  `activate_enterprise`, `configure_sso`, `disable_sso`.
- Migration `20260603_012_org_enterprise_sso.sql`: nullable `sso_enabled`,
  `sso_provider`, `sso_metadata`, `enterprise_activated_at` columns +
  `sso_provider IN ('saml','oidc')` check.

### #2 Multi-branch support
- Migration `20260603_010_org_branches.sql`:
  `organization_branches` table + `organization_members.branch_id` FK +
  RLS policies that **deny branch_admin access to sibling-branch rows**.
- `services/branches.py`: CRUD + `assert_branch_access()` scoping helper
  + `list_members_for_caller()`.
- `routes/branches.py`: full CRUD with org-admin gating; member-assign
  endpoint enforces branch-admin scoping at the route layer (matches RLS).
- Admin UI:
  - `/admin/settings/branches` — create + list branches.
  - Branches link added to `AdminSidebar` (owner/admin only).
- Branch admins see only their own branch entry in the list endpoint.

### #3 Ownership transfer flow
- Migration `20260603_013_ownership_transfers.sql`:
  `organization_ownership_transfers` table with 5-state CHECK
  (`invite_pending | accepted | revoked | expired | completed`) + RLS
  scoped to org owner.
- `services/ownership_transfer.py`:
  - Pure transition guards — invalid moves raise typed
    `OwnershipTransferError(code, message)`.
  - Auto-expire on read for stale `invite_pending` rows.
  - `confirm_transfer` is atomic: demotes current owner to `admin` and
    promotes invitee to `owner` in the same call. Covers the
    director-hands-off-to-assistant edge case from PRD §7.
- `routes/ownership_transfer.py`: owner CRUD + public token endpoints.
  Resend invite email is best-effort (token survives email failure).
- Frontend:
  - `/admin/settings/team` — owner page to invite + revoke + confirm.
  - `/admin/settings/team/accept-transfer?token=…` — invitee accept page.
  - Proxy routes: list/create + revoke + confirm + by-token lookup +
    by-token accept.

### #4 Refund automation
- Migration `20260603_011_org_refunds.sql`:
  - `organization_refunds` with `UNIQUE(whop_event_id)` — idempotency at
    the DB level.
  - `organization_billing_audit` with `UNIQUE(event_kind, event_source_id)`.
  - `organization_billing.last_refund_at/last_refund_amount_cents` for
    the owner-facing summary.
- `services/refunds.py`: extractors + `process_refund_event(payload)`.
  Replay-safe by design — fetches existing row by `whop_event_id` and
  returns `already_processed` without writing.
- `routes/refunds.py`: owner-only list endpoint + internal
  `/api/webhooks/whop-refund` trampoline guarded by
  `WHOP_REFUND_INTERNAL_SECRET`.
- Frontend webhook (`frontend/src/app/api/whop/webhook/route.ts`) now
  branches on `isRefundEvent(event)` and runs the **same idempotent
  pipeline** via `lib/refunds.ts` — both paths produce identical DB state.

### #5 Loom + Intercom support
- `lib/intercom.ts`: paying-tier gate (`growth | pro | enterprise`) +
  pure `buildBootSettings()`.
- `components/support/IntercomWidget.tsx`: client-side boot — no-op for
  free tiers or missing `NEXT_PUBLIC_INTERCOM_APP_ID`.
- Mounted in `AdminShell`; the layout now resolves the plan via the
  existing checklist endpoint and passes it through.
- `lib/loom.ts`: share/embed URL normaliser + tier-aware
  `pickLoomForTier()`.
- `components/support/LoomEmbed.tsx`: responsive iframe (16:9 by
  default; supports 4:3 and 1:1).
- Loom embedded in:
  - Wizard step 6 (`/for-schools/start/invite`) — "Alex's 90-second tour".
  - Post-onboarding checklist (admin dashboard) — fallback to welcome
    URL when no tier-specific URL is set.

---

## 2. Phase 3 test gates (PRD §11.3)

| Gate | Status |
|---|---|
| Multi-branch scoping (branch admin denied on sibling-branch rows) | ✅ `test_branches_service.py::TestAssertBranchAccess::test_branch_admin_denied_on_sibling_branch` |
| Ownership-transfer state machine — invite_pending / accepted / revoked / expired | ✅ `test_ownership_transfer_service.py::TestFullStateMachine::test_all_four_states_reachable` |
| Refund idempotency — replay webhook twice → 1 DB write | ✅ `test_refunds_service.py::TestProcessRefundEvent::test_replay_same_event_does_not_double_write` (backend) + `frontend/src/lib/__tests__/refunds.test.ts` (frontend) |
| Enterprise tier-quota — uncapped under realistic load | ✅ `test_enterprise_tier_quota_load.py` (parametrised 1 → 1,000,000) |

---

## 3. Backend pytest output

```
cd /root/chess-app/backend && source venv/bin/activate \
  && python3 -m pytest tests/ --tb=line -q
```

Final line:
```
1 failed, 770 passed, 1 skipped, 1 warning in 211.55s (0:03:31)
```

**770 passing** (Phase 2 baseline was 606 → +164 this phase).

The 1 failure is the carried-over Phase-2 RLS migration that requires
the SQL to be applied in Supabase (`20260603_009_invite_email_failures_rls.sql`).
Not a Phase 3 regression — the test is asserting a state that needs the
migration applied, the migration file has been shipped.

Phase 3 *new* test files (all green):

```
tests/test_branches_service.py                 24 passed
tests/test_branches_routes.py                  15 passed
tests/test_refunds_service.py                  25 passed
tests/test_refunds_routes.py                    9 passed
tests/test_enterprise_service.py               15 passed
tests/test_enterprise_tier_quota_load.py       17 passed
tests/test_ownership_transfer_service.py       25 passed
tests/test_ownership_transfer_routes.py        16 passed
                                              ---
                                              146 new tests (≥ 70 required ✓)
```

---

## 4. Frontend vitest output

```
cd /root/chess-app/frontend && NODE_OPTIONS="--max-old-space-size=2048" npx vitest run
```

Final line:
```
 Test Files  2 failed | 94 passed (96)
      Tests  2 failed | 1072 passed (1074)
   Duration  42.38s
```

**1072 passing** (Phase 2 baseline was 980 → +92 this phase). The 2
failures are the same pre-existing ones from the Phase 2 report
(`sw-version.test.ts` cache version mismatch; `coach/__tests__/routes.test.ts`
Next-16 cookie mock shape) — both untouched by Phase 3.

Phase 3 *new* test files (all green):

```
src/lib/__tests__/refunds.test.ts                                          23 passed
src/lib/__tests__/enterprise.test.ts                                        9 passed
src/lib/__tests__/ownership-transfer.test.ts                               15 passed
src/lib/__tests__/intercom.test.ts                                         12 passed
src/lib/__tests__/loom.test.ts                                             16 passed
src/app/api/admin/organizations/[orgId]/ownership-transfers/__tests__/...   6 passed
src/app/api/admin/organizations/[orgId]/branches/__tests__/route.test.ts    5 passed
src/app/api/admin/organizations/[orgId]/refunds/__tests__/route.test.ts     4 passed
src/app/api/whop/org-checkout/__tests__/route.test.ts                      +4 passed (enterprise / sso)
                                                                          ---
                                                                          ≥ 94 new tests (≥ 60 required ✓)
```

---

## 5. New files added

### Migrations
- `supabase/migrations/20260603_010_org_branches.sql`
- `supabase/migrations/20260603_011_org_refunds.sql`
- `supabase/migrations/20260603_012_org_enterprise_sso.sql`
- `supabase/migrations/20260603_013_ownership_transfers.sql`

### Backend services
- `backend/services/branches.py`
- `backend/services/refunds.py`
- `backend/services/enterprise.py`
- `backend/services/ownership_transfer.py`

### Backend routes
- `backend/routes/branches.py`
- `backend/routes/refunds.py`
- `backend/routes/ownership_transfer.py`

### Backend tests
- `backend/tests/test_branches_service.py`
- `backend/tests/test_branches_routes.py`
- `backend/tests/test_refunds_service.py`
- `backend/tests/test_refunds_routes.py`
- `backend/tests/test_enterprise_service.py`
- `backend/tests/test_enterprise_tier_quota_load.py`
- `backend/tests/test_ownership_transfer_service.py`
- `backend/tests/test_ownership_transfer_routes.py`

### Frontend libs
- `frontend/src/lib/refunds.ts`
- `frontend/src/lib/ownership-transfer.ts`
- `frontend/src/lib/intercom.ts`
- `frontend/src/lib/loom.ts`

### Frontend components
- `frontend/src/components/support/IntercomWidget.tsx`
- `frontend/src/components/support/LoomEmbed.tsx`

### Frontend pages
- `frontend/src/app/admin/settings/team/page.tsx`
- `frontend/src/app/admin/settings/team/accept-transfer/page.tsx`
- `frontend/src/app/admin/settings/branches/page.tsx`

### Frontend API proxies
- `frontend/src/app/api/admin/organizations/[orgId]/ownership-transfers/route.ts`
- `frontend/src/app/api/admin/organizations/[orgId]/ownership-transfers/[transferId]/revoke/route.ts`
- `frontend/src/app/api/admin/organizations/[orgId]/ownership-transfers/[transferId]/confirm/route.ts`
- `frontend/src/app/api/admin/organizations/[orgId]/branches/route.ts`
- `frontend/src/app/api/admin/organizations/[orgId]/refunds/route.ts`
- `frontend/src/app/api/ownership-transfers/by-token/[token]/route.ts`
- `frontend/src/app/api/ownership-transfers/by-token/[token]/accept/route.ts`

### Frontend tests
- `frontend/src/lib/__tests__/refunds.test.ts`
- `frontend/src/lib/__tests__/enterprise.test.ts`
- `frontend/src/lib/__tests__/ownership-transfer.test.ts`
- `frontend/src/lib/__tests__/intercom.test.ts`
- `frontend/src/lib/__tests__/loom.test.ts`
- `frontend/src/app/api/admin/organizations/[orgId]/ownership-transfers/__tests__/route.test.ts`
- `frontend/src/app/api/admin/organizations/[orgId]/branches/__tests__/route.test.ts`
- `frontend/src/app/api/admin/organizations/[orgId]/refunds/__tests__/route.test.ts`

---

## 6. Files modified

### Backend
- `backend/app.py` — registers branches / ownership-transfer / refunds blueprints.

### Frontend
- `frontend/src/app/api/whop/webhook/route.ts` — refund event branching.
- `frontend/src/app/api/whop/org-checkout/route.ts` — enterprise tier + sso metadata.
- `frontend/src/app/for-schools/start/plan/page.tsx` — enterprise self-serve, sso toggle, sales-assist CTA.
- `frontend/src/components/school-onboarding/WizardState.tsx` — `sso_enabled` payload field.
- `frontend/src/app/for-schools/start/invite/page.tsx` — Loom embed.
- `frontend/src/app/admin/layout.tsx` — fetch + pass plan to AdminShell.
- `frontend/src/app/admin/AdminShell.tsx` — mounts IntercomWidget.
- `frontend/src/app/admin/AdminSidebar.tsx` — Team & Branches links.
- `frontend/src/app/admin/dashboard/page.tsx` — Loom embed in dashboard.
- `frontend/src/app/api/whop/org-checkout/__tests__/route.test.ts` — 4 new enterprise cases.

---

## 7. Environment variables introduced

- `WHOP_REFUND_INTERNAL_SECRET` — bearer for the internal `/api/webhooks/whop-refund` trampoline (optional in dev).
- `NEXT_PUBLIC_WHOP_ORG_ENTERPRISE_MONTHLY` / `..._ANNUAL` — Whop plan ids for enterprise self-serve.
- `NEXT_PUBLIC_INTERCOM_APP_ID` — gates the Intercom widget (paying tiers only).
- `NEXT_PUBLIC_LOOM_WELCOME_URL` / `..._STARTER_URL` / `..._GROWTH_URL` / `..._PRO_URL` / `..._ENTERPRISE_URL` — Loom share/embed URLs (any form normalised).

---

## 8. Migrations still pending in Supabase

Apply in order (each is idempotent — safe to re-run):

1. `20260603_009_invite_email_failures_rls.sql` (Phase 2 carryover — unblocks the 1 RLS fuzzer failure)
2. `20260603_010_org_branches.sql`
3. `20260603_011_org_refunds.sql`
4. `20260603_012_org_enterprise_sso.sql`
5. `20260603_013_ownership_transfers.sql`

---

**Phase 3 gate: passed.** 770/771 backend + 1072/1074 frontend, all
four PRD §11.3 test gates green.
