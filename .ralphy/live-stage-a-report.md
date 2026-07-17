# Stage A — Live Play Stabilization + Telemetry — Report

Date: 2026-07-17. Scope: `frontend/` + one `supabase/migrations` file. **Not pushed, not deployed** (per spec).

## What changed

### 1. `live_game_logs` table + server logger
- **Migration** `supabase/migrations/20260717_028_live_game_logs.sql`: `live_game_logs(id bigint identity pk, created_at, game_id uuid, user_id text, source check('server','client'), action, ply int, outcome text, duration_ms int, stages jsonb, detail jsonb)`, index on `(game_id, created_at)`, RLS **enabled with no policies** (service-role writes only). Idempotent (`IF NOT EXISTS`).
- **Migration APPLIED** to Supabase project `qtzujwiqzbgyhdgulvcd` via `psql "$SUPABASE_DB_URL"` (URL in `backend/.env`). Verified: table + index present, `relrowsecurity = t`, `0` policies. No manual step required.
  - Observation: the table was auto-added to the existing `powersync` publication (logical replication). Harmless — RLS-with-no-policies denies all client reads regardless; noted for awareness only. Not modified.
- **`frontend/src/lib/live-game/log.ts`** (server-only): `logLiveGameEvent(entry)` — maps camelCase → snake_case and inserts via the service-role client, scheduled with Next's `after()` so it never blocks the response, and swallows **every** error (also `console.error`s). If the table is missing or the insert fails, live play is unaffected. Also exports `createStageTimer()` for per-stage `performance.now()` deltas.

### 2. Structured logging in every live-game route
`move`, `join`, `challenge`, `resign`, `draw`, `abort`, `claim-flag` each emit **one** `live_game_logs` row per request via `logLiveGameEvent`, with `source='server'`, `action`, `game_id`, `user_id`, `ply` (move), `outcome` (`'ok'` or the error code), total `duration_ms`, and a `stages` jsonb (`auth`/`load`/`write`/`insert` deltas). Every return path (including auth/validation failures) logs.

### 3. Client telemetry endpoint + hook wiring
- **`frontend/src/app/api/live-games/[gameId]/telemetry/route.ts`** — Clerk-authed `POST`, action whitelist (`channel_status`, `presence_join`, `presence_leave`, `token_refresh`, `resubscribe`, `poll_fallback_hydrate`, `disconnect_shown`), detail payload capped at 1 KB (oversized → `{_truncated:true}`), writes `source='client'`. Lightweight validation (no per-event player lookup) to keep it off any hot path.
- **`useLiveGame.ts`** fires fire-and-forget, de-duped (`≥2s`, `30s` for the poll) telemetry on: channel status changes, presence join/leave transitions, token refreshes, resubscribes, disconnect-banner-shown, and poll-fallback hydrations.

### 4. Realtime token refresh + resubscribe (`useLiveGame.ts`)
- Every **30s** while mounted: `tokenFn()` → `client.realtime.setAuth(token)` (Clerk template tokens die at ~60s — this is the root cause of the mid-game drop).
- On `CHANNEL_ERROR` / `TIMED_OUT` / `CLOSED` (when not unmounting): tear down the channel, re-hydrate from the authoritative DB, and resubscribe with a fresh token under **exponential backoff** (1s → 2s → 4s → … cap 15s). `SUBSCRIBED` resets the backoff, clears the error banner, and re-hydrates. A stale channel's callbacks are ignored (identity guard) so teardown-induced `CLOSED` can't loop.
- Note: a successful `hydrate()` no longer clears a standing `realtime_error` — only a fresh `SUBSCRIBED` does — so the socket-down banner survives the recovery poll.

### 5. Presence grace period
First presence `leave` starts a **7s** timer instead of flipping the banner instantly; a rejoin cancels it silently. The pre-join waiting state (opponent never present) shows no banner.

### 6. Active-game polling fallback
While `status === 'active'`, `hydrate()` every **5s** as a safety net against a silently-dead socket (reducer ply-guard dedupes vs broadcasts). The existing `challenge`-state poll is unchanged.

### 7. Move-route latency
- All broadcasting routes now schedule `broadcastGameEvent` with `after(...)` instead of `await` — broadcast is off the response critical path.
- Move route: the move-row insert and games update (independent, both gated only by the prior validation) now run concurrently via `Promise.all` — one fewer sequential round trip. Turn/legality/flag validation still runs strictly before any write, so correctness is unchanged (no RPC needed — the spec's `Promise.all` option).

## Tests
- **New:** `src/lib/live-game/__tests__/log.test.ts` (6) — column mapping, null defaults, graceful degradation on insert-error/throw, stage timer. `.../telemetry/__tests__/route.test.ts` (5) — auth, whitelist, bad JSON, happy log, oversized-detail truncation.
- **`useLiveGame.test.ts`** — added token-refresh interval, resubscribe-with-backoff, presence 7s grace, rejoin-cancels-grace, channel_status telemetry; updated the challenge-poll test to assert the active-state safety-net poll keeps running.
- **Updated** the 6 broadcasting route tests to run `after()` callbacks synchronously and stub the logger.
- **Full suite green:** `npx vitest run` → **201 files, 1832 tests passed**.
- **Lint:** `eslint` clean on all changed/added files.
- **`tsc --noEmit`:** all new/changed files type-clean (0 errors). The repo has **75 pre-existing tsc errors** in unrelated test files + generated `.next` types (present before this change, none in live-game code) — not addressed to keep scope focused.

## Follow-ups (not in scope)
- Consider a dashboard/query over `live_game_logs` to watch move `duration_ms` and `channel_status`/`resubscribe`/`disconnect_shown` rates in production.
- If move-write atomicity ever matters, the `Promise.all` pair could be promoted to a single transactional RPC (added to a future migration).
- Decide whether `live_game_logs` should stay in the `powersync` publication (currently harmless under RLS).
