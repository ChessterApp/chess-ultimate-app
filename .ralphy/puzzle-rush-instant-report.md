# Puzzle Rush — Instant Moves (client-side run engine) — report

Branch `feat/puzzle-rush-instant` (cut from `main` @ 5610a3b1). **Not pushed, not deployed. Migration 050 NOT applied.**
Spec: `/root/clawd/memory/reference/puzzle-rush-instant-moves-plan.md` (v2). §7.9 "validate on server" dropped, no anti-cheat added.

## Commits
| SHA | |
|---|---|
| f6a17a33 | feat: stateless `GET /pack` + `POST /runs/finish` (migration 050) |
| 8f6123aa | feat: client-side run engine, zero network during a run |
| b1540bcf | perf: keep the run board under the results modal |
| a84ab39c | perf: no state updates before paint when a run ends |
| f15add61 | perf: focus Play Again after the results modal paints |

## Result vs goal
- **Zero `/api` requests between Go! and run end:** 0 in all 8 Playwright runs (300 ms injected on every `/api` route).
- **✓/✕ in the same frame as the drop:** the verdict is computed inside the `USER_MOVED` reducer step, so the badge commits in the same React update as the piece. Measured drop→badge **5–22.5 ms** (max 22.5 over 8 runs × 5 moves; target < 50).
- **Results after 3rd strike:** **11–22.5 ms** (target < 100). The modal commits in the same update as the final ✕.

## Files changed
**Backend**
- `services/puzzle_rush_source.py`: picks now also return `themes`.
- `services/puzzle_rush.py`: `pack(seed, from, count)` is deterministic. Puzzle *i* = `pick(i)` with the per-index RNG and every earlier id of the seed excluded, so any slice equals the same slice of one big pack and ids never repeat within a seed. The prefix is replayed per request. Also `finish_run()` (validation, stats recomputed from attempts, `served_at` reconstructed, one RPC call) and `run_stats()`. The legacy v1 engine is untouched.
- `api/puzzle_rush.py`: `GET /api/puzzlerush/pack` (public, `Cache-Control: public, max-age=86400, immutable`) and `POST /api/puzzlerush/runs/finish` (Bearer only). The old `/runs`, `/move`, `/quit` and `GET /runs/<id>` routes are kept.
- `supabase/migrations/20261012_050_puzzle_rush_finish.sql`: `puzzle_rush_finish_run(jsonb)` (SECURITY DEFINER, service_role only).

**Frontend.** Shared engine files are framework-free: only chess.js, no React/DOM/Next imports.
- `lib/puzzle-rush/validate.ts` (new, shared): `judgeMove`. A move is correct if it reaches the same position as the expected move or delivers any mate. Promotion is compared as a move; an omitted piece defaults to a queen.
- `lib/puzzle-rush/runReducer.ts` (rewritten, shared): owns clock (monotonic `now` passed in), score, strikes, streaks, attempts, pack, stall/top-up and coach cues. Also `finishRequest()`, `reviewAttempts()` and `resultTiles()`.
- `lib/puzzle-rush/pack.ts` (new, shared): seed / UUID v4 generation (no `crypto` needed), `topUpFrom` (< 15 left), retry backoff.
- `lib/puzzle-rush/outbox.ts` (new, shared): finish outbox over any sync key-value store. Entries are per user, permanent 4xx responses are dropped, capped at 20.
- `lib/puzzle-rush/api.ts` (shared): `createRushApi(base)` with `pack` / `finish` / `bests` / `leaderboard`. The v1 client calls and the guest token are removed.
- `lib/puzzle-rush/types.ts` (shared): pack / finish types plus a `Square` type, so the engine no longer imports chessground.
- `lib/puzzle-rush/storage.ts` (web only): guest token removed; added `localStore()` and the pure `applyGuestScore()`.
- `hooks/usePuzzleRush.ts`: rewritten on top of the reducer. It handles prefetch, countdown, §3 timers, sounds, top-up and `/finish`.
- `components/puzzle-rush/*`: ResultsModal (guest tiles, pending ranks, deferred focus), RunSummary (offline review), RushBoard (stall spinner), RunTiles (monotonic timer), PuzzleRush (wiring, run board kept under the modal).
- `messages/{en,ru,kz}.json`: removed now-unused keys `errors.rate_limited`, `summary.loading`, `summary.error`, `results.end.abandoned`.

## Tests
| Suite | Result |
|---|---|
| pytest `test_puzzle_rush_instant.py` (new) + `_api` + `_source` | **104 passed** (44 new) |
| pytest full backend (4 modules with pre-existing collection errors excluded: custom_domain_routes, middleware_custom_domain, rls_cross_org_fuzzer, rls_isolation) | **1233 passed, 2 skipped, 1 failed**. The failure is `test_player_name_filter::test_player_name_carlsen_returns_games`, a TWIC query timeout against the 42 GB DB; unrelated to this branch. |
| vitest Puzzle Rush (lib + hook + components) | **80 passed** (final HEAD) |
| vitest full frontend | **3588 passed, 1 failed** (run before the perf commits). The failure is `MyGamesPanel-shared-db` "token revoked (404)", which is untouched by this branch and passes 3/3 in isolation, so it is flaky under full-suite load. |
| `npx tsc --noEmit` | clean |
| `npm run lint` (worktree) | 1 error / 155 warnings, all in files this branch doesn't touch. The error is in `components/review/__tests__/ReviewBoard.test.tsx`, which is on main. Changed files: 0 errors / 0 warnings. |
| `npm run build` (worktree `/var/tmp/pr-instant-build-wt`, hardlinked node_modules) | **success**, run 4× as fixes landed; worktree removed afterwards |

pytest coverage includes:
- pack determinism (same seed gives the same payload; another seed differs), ramp ±30, top-up slices equal one big pack, 300 ids with no duplicates;
- themes, 500 cap, validation (7 cases), exhausted DB → 503, no DB writes, Cache-Control;
- finish: Bearer records as that user, unauthenticated → 401, guest token is not auth, invalid JWT → 401;
- score/streaks recomputed (client totals ignored), `served_at` reconstruction, idempotent on run_id (the stored result wins over the retry body), someone else's run_id → 409;
- PB upsert (ties keep the earlier run, per-mode), zero score is never a PB, ranks, finished run feeds bests/leaderboard/`GET /runs/<id>`;
- 10 body + 7 attempt validation cases, 500 attempts OK, missing RPC → logged 503.

The RPC is mocked in pytest by a Python mirror over the fake tables. **The SQL itself was run** against a throwaway Postgres 16 cluster (049 + 050 applied twice for idempotency): created / duplicate / conflict, PB upsert and tie handling, ranks, 9 attempt rows, and `authenticated` gets "permission denied".

vitest coverage includes:
- validator: exact move, alt mate, promotion (explicit / omitted / under-promotion), wrong, illegal, castling;
- reducer: multi-move line, strikes → end, clock → end with the unfinished puzzle kept, move after deadline, streaks / longest / highest, per-puzzle ms, quit, stall + top-up, finish body, review attempts, coach cues;
- pack top-up threshold and backoff, ids;
- outbox: resend on load, transient vs permanent errors, per-user isolation, cap;
- hook: prefetch on mount, no request at Start, countdown, zero requests during the run, results in the same update as the 3rd strike, guest PB / non-PB, local timeout, signed-in `/finish` + merge + outbox clear, failed `/finish` resent on next load, instant Play Again, background top-up with silent retry, start failure;
- components: guest tiles, pending ranks, deferred focus.

## Playwright (local worktree build, `next start` on :3107)
- Script `/tmp/pr-instant/play.js`, logs `/tmp/pr-instant/run{1..8}.log`, screenshots `/tmp/pr-instant/shots/` (01 mode select … 07 Play Again countdown).
- Setup:
  - Every `/api/**` route gets +300 ms. `/api/puzzlerush/*` is fulfilled by a local Flask that serves only the Puzzle Rush blueprint over the real puzzles DB (read-only).
  - The live backend on :5001 doesn't have `/pack` loaded, and I must not restart it.
  - First packs are pinned to one seed so the harness knows the sequence.
- Flow: guest, 3 min. Solve, miss, solve, miss, miss (three strikes). Then close the modal and open a missed puzzle in the drawer, then Play Again.

| Metric (8 runs) | Target | Measured |
|---|---|---|
| drop → ✓/✕ badge (mousedown → DOM insert) | < 50 ms | 5.1 – 22.5 ms |
| `/api` requests Go! → run end | 0 | 0 in every run |
| 3rd-strike drop → results modal in DOM | < 100 ms | 11.0 – 22.5 ms |
| Play Again → "3" on screen | instant | ~820 ms (= the 750 ms §3 lead-in), no pack wait |

- Non-`/api` requests in the run window: the lazily loaded `puzzle-solved.mp3` on the first solve, and the logo PNG.
- During the review drawer: no Puzzle Rush call. One `POST /api/errors` came from the app's error reporter (see below).
- Before the perf commits the run-ending ✕ took 40–67 ms. A CPU profile showed 42 ms in `focus()` from `autoFocus` on Play Again (forced layout during the commit). Two more costs: a `setState` in the run-over layout effect, which flushed passive effects before paint, and remounting chessground for the summary layout. All three are fixed (commits b1540bcf, a84ab39c, f15add61).

## API contract for mobile
Base `https://chesster.io/api/puzzlerush` (Vercel rewrite to Flask). No cookies anywhere. Use `createRushApi(base)` from `lib/puzzle-rush/api.ts`.

### `GET /pack?seed=<hex>&from=<i>&count=<n>`
No auth. `seed`: 8–64 lowercase hex chars (the client makes 16 with `newSeed()`, a new one per run). `from`: 0–500, default 0. `count`: 1–100, default 40. Indices are capped at 499. Response is `Cache-Control: public, max-age=86400, immutable`.
```json
200 {
  "seed": "a1b2c3d4e5f60718", "from": 0, "count": 40,
  "puzzles": [
    { "index": 0, "id": "00JET", "fen": "<FEN before the setup move>",
      "moves": ["d8d6", "c1c8", "d6d8", "c8d8"],
      "rating": 399, "themes": ["mate", "short"], "color": "white" }
  ]
}
```
- `moves[0]` is the opponent's setup move. User moves sit at odd indices, opponent replies at even indices ≥ 2.
- `color` is the side the user plays.
- The same `(seed, from, count)` always returns the same puzzles, and slices are consistent, so top up with `from = pack.length`.

Errors: `400 {"error": "invalid_seed" | "invalid_from" | "invalid_count"}`, `503 {"error": "no_puzzles"}`.

### `POST /runs/finish?tz=<IANA zone>`
`Authorization: Bearer <Clerk session JWT>` is required. `tz` (query or body) sets the day/week for `global_rank.daily/weekly` and defaults to Asia/Almaty.
```json
{ "run_id": "<client UUID v4>", "mode": "3min" | "5min" | "survival",
  "seed": "<the pack seed>", "started_at": "<ISO-8601, Go!>", "ended_at": "<ISO-8601>",
  "end_reason": "strikes" | "timeout" | "quit",
  "attempts": [
    { "index": 0, "puzzle_id": "00JET", "rating": 399, "result": "solved" | "failed" | "unfinished",
      "user_moves": ["c1c8", "c8d8"], "ms": 4200 } ] }
```
- Rules: `index` = 0..n-1 in order, ≤ 500 attempts, ≤ 3 `failed`, and only the last may be `unfinished` (with `ms: null`).
- `ms` runs from the previous answer (or Go!) to this answer.
- `ended_at` must be ≥ `started_at` and no more than 5 min in the future.
- Score, strikes and streaks are recomputed server-side; any totals the client sends are ignored.
```json
200 { "run_id": "…", "duplicate": false, "score": 2, "is_new_pb": true, "longest_streak": 1,
      "highest_solved_rating": 519, "avg_ms_per_puzzle": 3100, "duration_ms": 41000,
      "personal_rank": 1, "global_rank": { "daily": 3, "weekly": 5, "all": 40 } }
```
- Idempotent on `run_id`: a retry returns the stored result with `"duplicate": true`. Safe to resend from an outbox.

Errors:
- `401 auth_required` (no Bearer) or `invalid_token`.
- `400 invalid_run_id | invalid_mode | invalid_seed | invalid_end_reason | invalid_time | invalid_attempts` (the last one adds `index` when per-attempt).
- `409 conflict` (the run_id belongs to another user).
- `503 finish_unavailable` (RPC missing or DB error; logged). Keep it in the outbox and retry.

**Mobile reuse:** copy `types.ts`, `validate.ts`, `runReducer.ts`, `pack.ts`, `outbox.ts` and `api.ts` unchanged. Pass `performance.now()` (or any monotonic ms) as `now`. The outbox takes a *synchronous* `KeyValueStore`; with AsyncStorage, wrap it in an in-memory mirror or make the store async. `storage.ts` is web-only.

## Deviations and why
1. **`/pack` returns an object** (`{seed, from, count, puzzles}`) instead of a bare array, so the contract can grow without breaking mobile. Each puzzle also carries `color`.
2. **`/finish` response** also includes `run_id` and `duplicate`. Errors use the existing `{error: code}` shape.
3. **`served_at` / `answered_at`** are reconstructed from per-attempt `ms`, because the plan's attempt shape has no timestamps. `ms` keeps v1 semantics: previous answer → this answer, transitions included.
4. **Top-ups do happen mid-run**, as the plan allows: when < 15 puzzles remain, first after puzzle 25. They are background requests, never on the move path, so the zero-request guarantee holds for runs of up to 25 puzzles. A dead network that late shows a spinner until a retry succeeds (backoff 1/2/4/8 s).
5. **The results modal shows immediately** (no 700 ms delay) to meet < 100 ms. The frozen run board stays behind it; the summary layout appears when the modal is closed.
6. **Guest tiles** show on-device bests: Personal = top score, Today = best today, All-time = top score. Personal and All-time are the same number because only those two values exist on-device. *Alex: keep, or relabel to two tiles?*
7. **Removed client code that's no longer called:** guest token storage, rate-limit message, review loading/error states, `abandoned` end text. The Flask v1 routes are still there.
8. `/pack` replays the seed's prefix per request. Measured on the real DB:
   - warm process: 35–125 ms for 40 puzzles at from = 0–105;
   - a cold process's first request ~3.5 s (band-quality sampling plus page cache);
   - from ≈ 460: ~2.4 s, because the ramp saturates at the DB's top band. Unreachable in practice.

## For Alex's eye
- **Apply migration 050 before deploying.** Without it, signed-in runs still play and show local results, but `/finish` returns 503. Runs stay in each user's outbox and resend on the next page load once 050 is live.
- **Backend restart needed** for `/pack` and `/finish` (I didn't restart anything). The frontend must not ship before the backend: a new client against the old backend gets a 404 on `/pack`, and Start shows "Couldn't start a rush".
- The page mounts the Puzzle Rush component twice on load, so two packs are prefetched, which is harmless. The cause is outside Puzzle Rush.
- The 400-rated opening band is small, so the first puzzle often repeats across runs (e.g. 00JET). This was true in v1 too.
- In the Playwright run, React hydration error #418 came from `SyncBoundary`. It reads localStorage during render, and the harness pre-set `chesster:initial_sync_done` to skip the first-load PowerSync gate (the Phase 2 report's open item). This is existing app behaviour for returning visitors, not Puzzle Rush, and it is what triggered the `POST /api/errors`.
- Signed-in Playwright wasn't possible: production Clerk keys are domain-locked, so Clerk returns 400 on localhost. The signed-in path is covered by vitest (hook) and pytest (endpoint + RPC SQL).
