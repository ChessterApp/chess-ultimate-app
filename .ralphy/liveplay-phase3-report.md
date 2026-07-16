# Chesster Online Play — Phase 3 Report

Frontend for challenge-link live games, built on the Phase 1 (schema/RLS/realtime
auth) and Phase 2 (API routes + clock/validation libs) work. No backend, no Flask,
no DB migration. Commit only — not pushed, not deployed.

## Files added
- `frontend/src/hooks/liveGameState.ts` — pure state model: `liveGameReducer`
  (`hydrate`/`start`/`move`/`end`, all idempotent + monotonic) plus selectors
  (`deriveTurn`, `deriveMyColor`, `deriveOrientation`, `deriveIsMyTurn`,
  `deriveIsCreator`, `deriveClocks`, `deriveTerminal`). No React / no I/O so it
  unit-tests without a socket.
- `frontend/src/hooks/useLiveGame.ts` — the hook. Hydrates from
  `GET /api/games/[gameId]`, subscribes to the private `game:{id}` channel
  (`createClerkSupabaseClient` + `setRealtimeAuth`, `{ config: { private: true } }`),
  applies `game.start`/`game.move`/`game.end` broadcasts through the reducer,
  tracks opponent presence, **re-hydrates on every `SUBSCRIBED`** (reconnect
  resync), runs a cosmetic client countdown off `remainingMs`, and exposes
  `makeMove` / `join` / `refetch`. Cleans up the channel on unmount and guards
  state writes with a `mountedRef`.
- `frontend/src/app/play/live/[gameId]/page.tsx` — one route, driven by
  `useLiveGame`: **lobby** (creator waiting + copy-link with "Copied!"),
  **joining** (recipient Accept → `join()`), **playing** (`ChessgroundBoard`
  oriented to the player, movable only on their turn, both clocks,
  opponent-online chip, move list), and a **terminal** result banner
  (win/loss/draw + reason) that also renders a view-only final board. Handles
  not-found and expired. Whole route `notFound()`s when the flag is off.
- `frontend/src/components/play/PlayFriendCard.tsx` — "Play a friend" entry:
  time control (3+2, 5+0, 10+0, Untimed) + color (white/random/black) →
  `POST /api/games/challenge` → copies the invite link and navigates the creator
  to `/play/live/{gameId}`.
- `frontend/src/hooks/__tests__/liveGameState.test.ts` — 24 tests: reducer
  transitions (hydrate/start/move/end, ply-guard drops, mate→winner mapping,
  draw→null winner, start no-op when terminal) and every selector, incl. the
  cosmetic clock projection (tick, clamp-to-zero, untimed/non-active passthrough).
- `frontend/src/hooks/__tests__/useLiveGame.test.ts` — 4 tests (jsdom, mocked
  Clerk + supabase client + fetch, no live socket): GET hydration → derived
  state, broadcast `game.move` through the reducer, `makeMove` POST reconcile,
  and re-hydrate on `SUBSCRIBED`.

## Files changed
- `frontend/src/lib/feature-flags.ts` — added `ONLINE_PLAY_ENABLED`
  (`NEXT_PUBLIC_ONLINE_PLAY_ENABLED === 'true'`, default off).
- `frontend/src/middleware.ts` — added `isLiveGameRoute = /play/live(.*)` and
  OR-ed it into the `auth.protect()` condition so live-game pages are auth-gated
  even though the broader `/play(.*)` stays public. Every existing public/
  protected path is preserved (merge, not clobber).
- `frontend/src/app/play/page.tsx` — minimal edit: import `PlayFriendCard` +
  `ONLINE_PLAY_ENABLED`, render `{ONLINE_PLAY_ENABLED && <PlayFriendCard />}`
  under the bot grid in the `selecting` phase. Nothing else touched.

## Reused from Phase 1/2 (imported, not rebuilt)
`createClerkSupabaseClient` / `setRealtimeAuth`, `live-game/types.ts`,
`live-game/clocks.ts` (`remainingMs`), `live-game/validate.ts` (`turnFromFen`),
all four `/api/games/*` routes (request/response shapes read from each route file
before wiring — move route takes `{ uci }`), and `ChessgroundBoard`.

## Verification
- `npx tsc --noEmit`: **zero new errors** in touched files (75 pre-existing
  errors remain, all in unrelated old test files — untouched).
- `npx vitest run`: **189 files / 1734 tests, all green** (28 of them new).
- `npx eslint` on all new/changed source: clean.

## Notes / deviations
- The move route contract is `{ uci }` (not `{ from, to, promotion }`);
  `makeMove` accepts either and serializes to UCI, auto-queening promotions.
- `makeMove` reconciles from the POST response immediately; the matching
  broadcast is then a no-op via the reducer's strict-next-ply guard (so it works
  whether or not the mover's own broadcast round-trips).
- Invite link uses the apex `https://chesster.io/play/live/{id}` (matches spec
  and the apex-only middleware protection).

## Left for Phase 4
- Resign / offer-draw / claim-flag **controls** (this page renders an already-
  terminal game cleanly but has no in-game action buttons).
- Optimistic local move application (currently reconciles from the server
  response, which is simpler and correct but not zero-latency).
- Rematch / new-game affordance from the terminal banner.
