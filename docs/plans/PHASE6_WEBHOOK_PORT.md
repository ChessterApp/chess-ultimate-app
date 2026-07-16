# Phase 6 — Port Chess Empire user.created handler from Flask to Next.js

## Why
The Chesster architecture is Gateway → Next.js frontend (Mastra) → Python Flask backend. Flask is the fallback layer, not primary. The Clerk `user.created` webhook currently only exists in Flask (Phase 5). This port moves it to Next.js so Clerk dashboard can point at the primary URL. Flask handler stays intact as a defense-in-depth fallback (do NOT delete it).

## Constraints
- Working directory: `/root/chess-app/frontend`
- Do NOT touch anything under `/root/chess-app/backend/` — Flask stays as-is.
- Do NOT edit env files. `INVITE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `CLERK_SECRET_KEY`, `NEXT_PUBLIC_SUPABASE_URL` are already set in `frontend/.env.local`.
- Preserve existing Listmonk subscriber sync for `user.created` and `user.deleted` — those must keep working.
- Node/TypeScript only. No new runtime dependencies unless strictly needed (svix, @clerk/nextjs, @supabase/supabase-js already installed).

## Files you WILL touch
1. `frontend/src/lib/invite-jwt.ts` — add `jwtJtiHash(token: string): string` (sha256 hex of raw JWT). Mirror of Python `jwt_jti_hash` in `backend/services/invite_jwt.py`.
2. `frontend/src/lib/__tests__/invite-jwt.test.ts` — add cases matching `backend/tests/test_invite_jwt_hash.py` (deterministic, differs when token differs, hex length 64).
3. `frontend/src/app/api/webhooks/clerk/route.ts` — extend the existing `user.created` case with Chess Empire onboarding completion (see "Retry story" below).
4. `frontend/src/app/api/webhooks/clerk/__tests__/route.test.ts` — NEW file. Vitest coverage mirroring `backend/tests/test_webhooks_user_created.py`.

## Reference reads (SOURCE OF TRUTH)
- `backend/routes/webhooks.py:388-551` — the Python `_handle_user_created` you're porting. Follow its logic literally, comments included.
- `backend/services/invite_jwt.py:100-108` — the `jwt_jti_hash` you're porting.
- `backend/tests/test_webhooks_user_created.py` — the test cases you must mirror.
- `frontend/src/lib/invite-jwt.ts` — existing `verifyInviteJwt`; add hash helper next to it.
- `frontend/src/lib/supabase-admin.ts` — the existing Supabase service-role client. Reuse it, do NOT create a new one.

## Retry story (must preserve — same as Python)
On `user.created` with `unsafe_metadata.inviteJwt`:
1. **Verify JWT** — `verifyInviteJwt(raw)`. On `InviteJwtError`: log warn + return 200 (silent skip, no retry — token is unusable).
2. **Compute hash** — `jwtJtiHash(raw)`.
3. **Replay check** — select from `invite_jwts_consumed` by `jti_hash`. If row exists: log info + return 200 (idempotent replay).
4. **Token validity** — select `branch_invite_tokens` by `claims.branch_token_id`. If row missing OR `revoked_at` set: log warn + return 200 (refuse silently).
5. **Org lookup** — select `organizations` by `claims.org_id`. If missing: log error + return 200. Capture `clerk_org_id`.
6. **Upsert member** — into `organization_members` with the payload the Python code builds (see `webhooks.py:495-512`). Use `onConflict: 'organization_id,external_student_id,external_source'`.
7. **Clerk create membership** — call `clerkClient().organizations.createOrganizationMembership({ organizationId: clerk_org_id, userId: clerk_user_id, role: 'org:member' })`. On 422 error: log info + continue. On any other error: throw so the webhook returns 500 and Svix retries — and step 8 does NOT run.
8. **Record consumption LAST** — insert into `invite_jwts_consumed` with the fields from Python code. If steps 6/7 threw, step 8 doesn't run and JWT stays unconsumed, safe to retry.

Signups without `unsafe_metadata.inviteJwt` are non-CE and get the Listmonk-only path (already exists).

## Non-CE + Listmonk co-existence
The current route.ts calls `createSubscriber(...)` for every `user.created`. Keep that call — it should run in ADDITION to the CE flow (or before, same as today). Whether CE onboarding succeeds or fails, Listmonk subscriber sync must not regress.

## Clerk backend SDK notes
- Import: `import { clerkClient } from '@clerk/nextjs/server';`
- Call is async: `await (await clerkClient()).organizations.createOrganizationMembership({...})`.
- 422 already-member detection: catch the error, inspect `err.status === 422` OR `err.errors?.[0]?.code === 'already_a_member_of_organization'` (either signal counts). If you're unsure of the exact shape, catch it broadly and log the response body for triage.
- Role literal: `'org:member'` (matches `_map_clerk_role` reverse — Clerk basic member).

## Test cases (mirror `test_webhooks_user_created.py`)
Use vitest with `vi.mock` for `@supabase/supabase-js` and `@clerk/nextjs/server`. Cover:
1. **happy path** — verify → upsert → Clerk membership → consumption row written.
2. **replay** — invite_jwts_consumed hit → short-circuit, no upsert, no Clerk call, no insert.
3. **non-CE signup** — no inviteJwt in unsafe_metadata → Listmonk still called, no CE writes.
4. **invalid JWT** — bad signature or expired → silent skip, no writes.
5. **revoked branch token** — `revoked_at` set → refuse, no writes.
6. **Clerk 422 already-member** — succeeds, consumption still recorded.
7. **Clerk 500** — throws, response is 500-ish, `invite_jwts_consumed` NOT written.

Also: keep or extend the existing Listmonk test if there is one, so it still passes.

## Definition of done
- `cd frontend && npm run test -- src/app/api/webhooks/clerk src/lib/invite-jwt` all green.
- `cd frontend && npm run lint` clean on the touched files.
- `cd frontend && NODE_OPTIONS="--max-old-space-size=2048" npm run build` completes without errors.
- Retry ordering matches the Python. If steps 5/6/7 fail, `invite_jwts_consumed` insert must not run.
- Git: commit each logical chunk (jti hash helper, webhook logic, tests) separately with conventional messages. Do not push.

## Verification you should run yourself before saying done
```
cd /root/chess-app/frontend
export HOME=/root
npm run test -- src/lib/__tests__/invite-jwt.test.ts
npm run test -- src/app/api/webhooks/clerk
npm run lint
NODE_OPTIONS="--max-old-space-size=2048" npm run build
git log --oneline -5
```
Report the pass/fail counts and the last 5 commit shas. If the build fails, fix it, do not report success.
