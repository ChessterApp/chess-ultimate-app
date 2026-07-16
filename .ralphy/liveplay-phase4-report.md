# Chesster Online Play — Phase 4 Report

Game lifecycle: resign / draw offer-accept-decline / claim-flag / abort, lazy
challenge expiry, auto-flag detection, and the hook/reducer/page controls for
them. Built on Phases 1–3. No Flask, commit only — not pushed, not deployed.

## Files added

### Migration
- `supabase/migrations/20260716_027_online_play_lifecycle.sql` — adds the one
  column Phase 1 lacked: `games.draw_offer_by text` (standing draw offer).
  Idempotent (`ADD COLUMN IF NOT EXISTS`). resign/flag/abort/expiry reuse
  existing columns, so no other schema change. No new RLS needed — the column is
  written only by the /draw route (service-role) and read under the existing
  player-only SELECT policy. **Not yet applied to the live DB** (commit-only per
  spec; apply with the same method Phase 1 used before the feature ships).

### Lifecycle routes (each: Clerk auth → load → authorize → conditional update → broadcast)
- `src/app/api/games/[gameId]/resign/route.ts` — active + player only; opponent
  wins; final clocks settled via `remainingMs`; conditional update guards on
  `status='active'`; broadcasts `game.end` (`reason:'resign'`).
- `src/app/api/games/[gameId]/draw/route.ts` — body `{ action: 'offer' | 'accept'
  | 'decline' }`. offer → `draw_offer_by=userId` + `game.draw_offer`; decline →
  clear + `game.draw_decline`; accept (valid only if the OTHER player offered) →
  finished draw `1/2-1/2`, winner NULL + `game.end` (`reason:'draw'`).
- `src/app/api/games/[gameId]/claim-flag/route.ts` — re-derives clocks server-side
  from stored banks + server time (`remainingMs`); the rule is "whoever is on the
  move with a spent bank loses", which makes both spec cases fall out (claimant
  wins normally; claimant's own dead clock → claimant loses). Untimed → 400;
  running clock still has time → 409 `not_flagged`.
- `src/app/api/games/[gameId]/abort/route.ts` — active with `ply < 2` (either
  player) **or** challenge (creator only, cancels it). Sets `aborted`,
  `end_reason='abort'`, no result/winner; broadcasts `game.end` with
  `status:'aborted'`. `ply >= 2` → 409 `too_late`; other statuses →
  `not_abortable`.

### Tests
- `.../resign/__tests__/route.test.ts` (7), `.../draw/__tests__/route.test.ts`
  (9), `.../claim-flag/__tests__/route.test.ts` (7),
  `.../abort/__tests__/route.test.ts` (9) — auth/non-player/wrong-status
  rejections, the full draw matrix, flag verified against server clocks, abort
  ply rule + challenge-cancel, conditional-update race guards.
- `src/hooks/__tests__/liveGameState.lifecycle.test.ts` (18) — draw_offer /
  draw_decline / move-clears-offer / end (resign+abort+default-finished), the
  `deriveDrawOffer` matrix, and the `deriveAutoFlag` derivation guard
  (both colors, floors, untimed/non-active passthrough).

## Files changed (only where the spec sanctions)
- `src/lib/live-game/types.ts` — `draw_offer_by` on `GameRow`; optional
  `drawOfferBy` on the hydration game; two new broadcast events
  (`game.draw_offer` / `game.draw_decline`) + their payload types; `GameEndPayload`
  gains optional `status` (so abort ends as `aborted`, not `finished`) and
  `result` widened to `string | null` (abort has no result).
- `src/app/api/games/[gameId]/route.ts` (GET) — **lazy expiry**: a stale
  `challenge` (`expires_at < now`) is conditionally flipped to `expired` on read
  and rendered as such; also exposes `drawOfferBy` in the payload.
- `src/app/api/games/[gameId]/move/route.ts` — clears `draw_offer_by` on every
  successful move (lichess rule). Test asserts it.
- `src/app/api/games/[gameId]/__tests__/route.test.ts` — +1 GET lazy-expiry test.
- `src/app/api/games/[gameId]/move/__tests__/route.test.ts` — +1 assertion that
  a move clears the draw offer.
- `src/hooks/liveGameState.ts` — `drawOfferBy` in state; `draw_offer` /
  `draw_decline` reducer cases; move + end clear the offer; end honours
  `payload.status`; selectors `deriveDrawOffer` and `deriveAutoFlag` (pure).
- `src/hooks/useLiveGame.ts` — subscribes to the two draw broadcasts; exposes
  `resign` / `offerDraw` / `acceptDraw` / `declineDraw` / `claimFlag` / `abort`
  (POST + reconcile via the reducer, same pattern as `makeMove`); a guarded
  effect fires `claimFlag()` once when `deriveAutoFlag` trips (quiet, so a benign
  `not_flagged` clock-drift race never surfaces an error); exposes `drawOffer`
  and `canAbort`.
- `src/app/play/live/[gameId]/page.tsx` — in-game controls while active: Resign
  (two-step confirm), Offer draw (disabled once offered), Abort (only when
  `canAbort`), and an Accept/Decline banner when the opponent offers; a
  non-blocking "opponent disconnected" banner; the terminal banner now covers
  resign/draw/flag/abort (abort → "Game aborted"); the expired screen gets a
  "Create a new challenge" link. Styling matches the existing page — no redesign.

## Disconnect handling
Presence was already wired in P3; the page now surfaces `opponentConnected` as a
non-blocking banner. Per spec there is **no auto-win on disconnect** in v1 — the
clock is the arbiter.

## Verification
- `npx vitest run` → **194 files / 1785 tests, all green** (+5 files / +51 tests
  over Phase 3's 189/1734).
- `npx tsc --noEmit` → **zero new errors** in any touched file (75 pre-existing
  errors remain, all in unrelated old test files — unchanged from Phase 3).
- `npx eslint` on every new/changed source + test file → clean.

## Notes / deviations
- **claim-flag winner rule.** The spec phrases it as "verify the opponent's clock
  ≤ 0 → winner = claimant" with a fallback for the claimant's own dead clock.
  Because only the side-to-move's clock ticks, both cases reduce to a single
  server-authoritative rule — "the side on the move with a spent bank loses" —
  which is what the route implements. In the normal case the claimant is the
  non-mover, so winner = claimant; the fallback is automatic. The endpoint does
  not need to trust *who* claims.
- **`drawOfferBy` kept optional** on the hydration payload so the Phase-3 test
  fixtures (and the defensive `?? null` reducer read) type-check untouched.
- **Migration not applied to the live DB** — commit-only. Everything else works
  against the existing schema; only the /draw route needs the new column, and its
  tests inject it via the mock.

## Out of scope (v2, per spec)
Rematch, ratings, spectators, guest access.
