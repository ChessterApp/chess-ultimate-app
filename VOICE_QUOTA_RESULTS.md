# Voice Minutes Quota + Tier Wire-Up — Results

Implemented per `VOICE_QUOTA_SPEC.md`. Voice Mode is now metered at 30 minutes /
calendar month (UTC) by default; text chat is unlimited (abuse-guard windows
only); subscription tier is resolved server-side through one shared helper and
forwarded to Hermes as `x-subscription-tier` on every coach proxy.

## Task 1 — Tier resolution helper (frontend)
- **Added** `frontend/src/lib/subscription-tier.ts` — `resolveUserTier(userId): Promise<'free'|'premium'|'pro'>`. Mirrors the stub today but reads env `COACH_DEFAULT_TIER` (default `'free'`); lazy-init only (no module-level Supabase client, per the standalone-mode crash note); TODO marker for the real Supabase/Whop lookup.
- **Wired into** all coach proxies, each now sends `x-subscription-tier`:
  - `frontend/src/app/api/coach/chat/route.ts`
  - `frontend/src/app/api/coach/tool/route.ts`
  - `frontend/src/app/api/coach/live-token/route.ts` (also on the voice/prompt + quota calls)
  - `frontend/src/app/api/coach/voice-usage/route.ts` (new — Task 4)

## Task 2 — Voice minutes ledger (Hermes + DB)
- **Added migration** `hermes/migrations/006_voice_minutes.sql` — table `voice_usage` (id, user_id, session_id, started_at, last_heartbeat_at, seconds, month_key, created_at), `UNIQUE(user_id, session_id)`, index on `(user_id, month_key)`. Additive only.
- **Added** `hermes/src/voice_quota.py` — `VoiceQuotaLedger` (Supabase read-modify-write per session, sums monthly usage), `month_key()`, `tier_limit_seconds()`, `MAX_HEARTBEAT_DELTA=120`. In-memory per-process fallback on any Supabase failure/absence, logged; never raises.
- **Added endpoints** in `hermes/src/server.py`:
  - `POST /internal/voice/heartbeat` {user_id, session_id, seconds_delta} → accumulates (single-delta capped at 120s).
  - `GET /internal/voice/quota?user_id=&tier=` → {limit_seconds, used_seconds, remaining_seconds, month_key, unlimited}.
  - Both guarded by the existing `_verify_api_key` (Hermes' internal-auth mechanism; no-op when `HERMES_API_KEY` unset). Added `VoiceHeartbeatRequest` model and imported `DEFAULT_TIER`.

## Task 3 — Enforcement at token mint (live-token route)
- `frontend/src/app/api/coach/live-token/route.ts`: fetches the quota in parallel with the existing voice/prompt + recap + tools calls. `remaining_seconds <= 0` (and not unlimited) → HTTP 429 `{error:'voice_quota_exhausted', remainingSeconds:0, limitSeconds, resetAt}` (resetAt = first of next month UTC). Otherwise mints and returns `remainingSeconds` / `limitSeconds`. Quota lookup failure → mint anyway (fail-open, logged).

## Task 4 — Client-side minute tracking + UX (frontend)
- `frontend/src/hooks/useGeminiLive.ts`: 60s heartbeat interval posts the newly-elapsed seconds to `/api/coach/voice-usage`; residual flush on disconnect/unmount. Seeds a local countdown from the mint's `remainingSeconds`; at 0 it fires `onQuotaExhausted` and ends the session gracefully. A 429 `voice_quota_exhausted` at mint routes to `onQuotaExhausted` (not a connection error). Exposes `remainingSeconds`.
- **Added** `frontend/src/app/api/coach/voice-usage/route.ts` — Clerk-authed heartbeat proxy; user_id is set **server-side** from the Clerk session (client value ignored) and forwarded to the Hermes heartbeat endpoint. Best-effort (always 200).
- `frontend/src/components/coach/CoachChat.tsx`: "N min left" label near the voice toggle (amber warning at ≤5 min), and a "minutes used up — text chat is unlimited" banner on exhaustion.
- **i18n keys** `voiceMinutesLeft` + `voiceQuotaExhausted` added to `messages/en.json`, `messages/ru.json`, `messages/kz.json`.

## Task 5 — Text chat: unlimited
- `hermes/src/middleware/rate_limiter.py`: text `TIER_LIMITS` raised to free 30 / premium 60 / pro 120 (abuse guard only). Module docstring documents the 2026-09-08 product decision that text has NO monthly quota. `VOICE_TOOL_TIER_LIMITS` free bumped 30→60 to keep the "voice tool > text" invariant now that text free is 30.

## Tests
- **Hermes** (`cd hermes && PYTHONPATH=<prod-venv-site-packages> python -m pytest tests/unit -q`): **606 passed, 23 failed**. All 23 failures are the pre-existing environment-only baseline (missing 42GB TWIC SQLite DB → twic_search/get_pgn/test_setup; board-tool framework version drift → board_control_tool/board_protocol). No regressions.
  - Added `tests/unit/test_voice_quota.py` (16 tests: tier limits/env overrides, in-memory accumulation + per-user isolation + delta cap + remaining-never-negative + unlimited, Supabase fail-open, and the two internal endpoints).
  - Updated `tests/unit/test_rate_limiter.py` (new default limits) and `tests/unit/test_tool_bridge.py` (voice-tool free ceiling now 60).
- **Frontend** (`npx vitest run`): touched-area run **1027 passed** (90 files). New/updated suites:
  - `src/lib/__tests__/subscription-tier.test.ts` (4)
  - `src/app/api/coach/__tests__/voice-usage.test.ts` (4)
  - `src/app/api/coach/__tests__/live-token.test.ts` (+5 quota tests; updated the concurrency test 3→4 in-flight)
  - `src/hooks/__tests__/useGeminiLive.test.ts` (+4: seeds/heartbeat, countdown→exhausted, 429→onQuotaExhausted, disconnect flush)
  - `src/components/coach/__tests__/CoachChat.test.tsx` (+5: minutes label, ≤5-min warning, null-hidden, quota banner; added `remainingSeconds` to the hook mock)
- **Lint** (`eslint`) clean on all changed files. `tsc --noEmit` clean on all changed files (pre-existing unrelated errors remain in `GameViewerPanel-save.test.ts` and `org-metadata.test.ts`, untouched by this work).

## Env vars added
- Frontend: `COACH_DEFAULT_TIER` (default `free`).
- Hermes: `VOICE_MINUTES_FREE` (30), `VOICE_MINUTES_PREMIUM` (30), `VOICE_MINUTES_PRO` (30). `0` or `unlimited` ⇒ unlimited. All default to 30 because billing isn't live.

## Migration file
- `hermes/migrations/006_voice_minutes.sql` (NOT applied to prod — additive; apply via `psql "$SUPABASE_DB_URL"`).

## Deviations from spec (with reasons)
1. **kz.json also updated.** Spec said en/ru; the coach UI is localized in en/ru/kz and a parity test (`coach-i18n.test.ts`) enforces all three, so keys were added to kz too.
2. **Internal-route auth uses `_verify_api_key`.** The spec referenced "existing internal routes," but none existed under `/internal/`. `_verify_api_key` is Hermes' established auth mechanism (checks `HERMES_API_KEY`, no-op when unset — matching current frontend→Hermes calls that send only `X-User-Id`).
3. **`VOICE_TOOL_TIER_LIMITS` free 30→60.** Not requested by the spec, but raising text free to 30 collided with the documented "voice tool limit > text limit" invariant (and its test). Bumped voice-tool free to keep the invariant true; updated the two `test_tool_bridge` rate-limit tests accordingly.
4. **Countdown resolution ~60s.** The client drives the countdown from the same 60s heartbeat interval (rather than a separate fast ticker), so the displayed minutes and the local exhaustion check update once a minute. Acceptable for a 30-minute quota; the mint-time server check is the hard gate.
