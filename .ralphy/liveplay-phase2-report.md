# Online Play — Phase 2 Report

**Date:** 2026-07-16 · **Status:** DONE
Spec: `/root/clawd/plans/chesster-liveplay-phase2-spec.md`
Parent plan: `/root/clawd/plans/chesster-online-play-challenge-link.md`

## What was built

### 1. Shared game-logic lib — `frontend/src/lib/live-game/`
- **`types.ts`** — shared TS types: `GameRow` / `GameMoveRow` (snake_case DB
  shapes mirroring migration `20260716_026`), `HydrationPayload`, and the three
  broadcast payload types (`game.start` / `game.move` / `game.end`).
- **`clocks.ts`** — pure clock math (no I/O):
  - `computeClocksAfterMove(...)` → new banks after the mover's elapsed time is
    deducted + increment applied; `{ whiteMs, blackMs, flagged }`. Flags at the
    `bank − elapsed ≤ 0` boundary (increment withheld on flag).
  - `remainingMs(game, now)` → live banks for hydration (only the side to move
    ticks; floors at 0; non-active games don't tick).
  - Untimed games (null banks) short-circuit everywhere — never flagged.
- **`validate.ts`** — chess.js 1.4.0 (BSD-2):
  - `applyMove(fen, uci)` → `{ ok, san, fenAfter, gameOver }`; replays from the
    stored FEN, never throws on illegal input. `gameOver` classifies checkmate /
    stalemate / insufficient material / threefold / fifty-move.
  - `turnFromFen(fen)` helper.
- **`broadcast.ts`** — `broadcastGameEvent()` fires on the private Realtime topic
  `game:{id}` via Supabase's HTTP Broadcast API with the service-role key
  (serverless-friendly, no persistent socket). Failures are logged, never fatal
  (DB is truth; clients re-hydrate).

### 2. Route handlers — `frontend/src/app/api/games/`
Match the repo's established convention (Clerk `auth()` → 401, `supabaseAdmin`
service-role client, manual `typeof` body validation with specific error codes —
the codebase does not use zod in API routes).
- **`POST /challenge`** — validates colorChoice + time control, inserts a
  `status:'challenge'` row (creator_id = clerk uid, 24h `expires_at`), returns
  `{ gameId, url }` with `url = ${origin}/play/live/{id}`.
- **`POST /[gameId]/join`** — rejects own challenge (403), non-challenge (409),
  expired (410, marks row 'expired'); the conditional `UPDATE status
  'challenge'→'active' WHERE status='challenge'` is the race guard (loser gets
  0 rows → 409 `already_taken`). Resolves colors (deterministic uuid-parity coin
  flip for 'random'), initializes banks from `initial_sec*1000`, sets
  `last_move_at`, broadcasts `game.start`.
- **`POST /[gameId]/move`** — auth + active + turn-from-FEN player check; clock
  check first (flag → finish game `end_reason:'flag'`, broadcast `game.end`,
  409, move NOT applied); `applyMove` validation (illegal → 422); inserts the
  `game_moves` row then updates `games` (fen/ply/clocks/last_move_at, terminal
  state if game over); broadcasts `game.move` (+ `game.end` on mate/draw) with
  fresh server clocks.
- **`GET /[gameId]`** — hydration: game row + full move list, clocks recomputed
  via `remainingMs(now)`. Mirrors the RLS read rule — any authenticated user may
  read a 'challenge' row (player ids withheld until it leaves 'challenge');
  otherwise player-only (404 to strangers).

### 3. Unit tests (vitest) — 45 tests, all green
- `clocks.test.ts` (12) — deduction, increment, flag boundary (exact 0),
  untimed short-circuit, `remainingMs` for both colors / floor / non-active.
- `validate.test.ts` (7) — legal, illegal, malformed uci, checkmate (fool's
  mate, win assigned to mover), stalemate, promotion (`a7a8q`), castling
  (`e1g1`).
- Route tests (26) using a shared table-driven `supabaseAdmin` mock
  (`src/test/liveGameSupabaseMock.ts`, extends the promo/redeem builder pattern
  with `insert`/`order`): challenge creation (201 + url shape, untimed nulls),
  join happy path + own-challenge 403 + double-join race 409 + expired 410,
  move wrong-turn 403 + illegal 422 + flag-on-move (409, finished, `game.end`
  broadcast, no move row) + happy path (move insert + game update + `game.move`
  broadcast), GET challenge-visible-to-strangers / player-only 404 / clock
  recompute + move list.

## Verification
- `npx vitest run src/lib/live-game src/app/api/games` → **45 passed**.
- `npx tsc --noEmit` → no new errors in any touched file.
- `npx eslint` on all new paths → clean.

## Deviations from spec
- **Validation lib:** used the repo's existing manual-validation convention
  (typeof + error-code responses) rather than zod — zod is a dependency but is
  not used anywhere under `src/app/api`. This matches the spec's "or repo's
  existing validation convention — MATCH the established patterns" clause.
- **Move atomicity:** the repo has no transaction/RPC helper, so the
  `game_moves` insert and `games` update run sequentially (move row first), as
  the spec explicitly permits for v1. Flagged inline for a future single-RPC
  follow-up.
- **Broadcast:** added a small `broadcast.ts` helper (not in the literal
  deliverables list, which named only clocks/validate/types) so the routes have
  one testable, mockable broadcast path. Uses the Supabase HTTP Broadcast API
  with the service-role key — the pattern the Phase 1 realtime policy expects
  for a server-side private-channel send.
- No new migration (Phase 1 schema was sufficient). No UI (Phase 3). No
  lifecycle endpoints (Phase 4).
