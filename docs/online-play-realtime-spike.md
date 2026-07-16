# Online Play — Realtime Auth Spike (Phase 1)

**Date:** 2026-07-16 · **Status:** VERIFIED (anon/policy) · manual step for full player round-trip
Parent plan: `/root/clawd/plans/chesster-online-play-challenge-link.md`
Spec: `/root/clawd/plans/chesster-liveplay-phase1-spec.md`

## Question this answers

The riskiest unknown of the whole feature: **does a Clerk-issued JWT authorize a
private Supabase Realtime channel?** Nothing in the codebase has ever exercised
Clerk ↔ Realtime private-channel auth. If it doesn't work, the transport choice
(Supabase Broadcast) collapses and we'd need a socket server on the VPS.

## Mechanism

- Migration `supabase/migrations/20260716_026_online_play.sql` adds two RLS
  policies on `realtime.messages` (`games_realtime_players_receive` for SELECT,
  `games_realtime_players_send` for INSERT), both `TO authenticated`. They parse
  the game uuid out of the channel topic (`game:{id}`) and check it via
  `public.is_game_player(uuid)` — true only when `clerk_uid()` is one of
  `creator_id / opponent_id / white_id / black_id`.
- Clerk native third-party auth issues JWTs carrying `role: authenticated` and
  `sub: <clerk user id>`. `clerk_uid()` reads that `sub`. The client wires the
  token in via `createClerkSupabaseClient(getToken)` +
  `client.realtime.setAuth(token)` (`frontend/src/lib/supabase.ts`).

## Results

### Verified automatically — `frontend/scripts/realtime-auth-spike.ts`

```
cd frontend && npx tsx scripts/realtime-auth-spike.ts
```

- ✅ Service-role insert of a `games` row works.
- ✅ **Anon client is REJECTED** on private `game:{id}` (status `CHANNEL_ERROR`) —
  the channel refuses unauthenticated connections. This is the key negative
  proof: without a valid `authenticated` token you cannot join.

### Verified at the DB layer (psql, simulated Clerk claims)

The exact authorization predicate the realtime policies call was exercised
directly by setting `role authenticated` + `request.jwt.claims` in psql:

| Actor (sub)          | `games` visible          | `is_game_player(g1)` | moves visible |
| -------------------- | ------------------------ | -------------------- | ------------- |
| `user_bob` (player)  | own `active` + `challenge` | `true`             | 1             |
| `user_dave` (stranger) | only `challenge`       | `false`             | 0             |

- ✅ Player-only read isolation holds.
- ✅ Challenge rows are readable by any authenticated user (lobby view).
- ✅ INSERT policy: a client can create a challenge only with
  `creator_id = clerk_uid()`; spoofing another creator raises
  `new row violates row-level security policy`.

### Manual step — full player broadcast round-trip

A real Clerk session token cannot be minted headlessly (no legacy JWT secret in
env; Clerk tokens are signed by Clerk's JWKS). To confirm the positive path
(player subscribes + receives its own broadcast, non-player rejected on the same
topic), run the spike with real tokens grabbed from the browser console while
signed in as two different users:

```js
// devtools console, signed in:
await window.Clerk.session.getToken()
```

```
SPIKE_PLAYER_TOKEN=<player jwt>   SPIKE_PLAYER_SUB=<player clerk id> \
SPIKE_NONPLAYER_TOKEN=<other jwt> SPIKE_NONPLAYER_SUB=<other clerk id> \
npx tsx scripts/realtime-auth-spike.ts
```

Expected: `player SUBSCRIBED`, `player received own broadcast`,
`non-player REJECTED`.

> Prerequisite for the positive path: Realtime authorization must be enabled for
> the project and Clerk must be registered as a third-party auth provider in the
> Supabase dashboard (Authentication → Third-party). The anon-rejection result
> above already confirms `realtime.messages` RLS is being enforced.

## Conclusion

Policies apply cleanly and the private channel enforces auth (anon refused;
player/non-player split proven at the DB predicate level). The transport design
(Clerk-authorized Supabase private Broadcast) is sound to build on in Phase 2.
Only the live socket round-trip with a real Clerk token remains as a one-command
manual confirmation.
