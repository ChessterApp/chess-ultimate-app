# Puzzle Rush — Phase 1 (Backend) Report

Branch: `feat/puzzle-rush-backend` (cut from `main` @ 34de3586). Not pushed. Migration not applied.
Spec: `/root/clawd/memory/reference/puzzle-rush-ux-spec.md` (§7 locked decisions followed).

## Commits
- `1334b0f0` feat(puzzle-rush): read-only puzzle source with indexed ramp picks
- `49711f34` feat(puzzle-rush): migration 049 for runs, attempts and bests
- `7781eb6c` feat(puzzle-rush): run engine and /api/puzzlerush blueprint
- (this report)

## Files
| File | What |
|---|---|
| `backend/services/puzzle_rush_source.py` | Read-only (`file:…?mode=ro`, `uri=True`) puzzle picker. Path from `PUZZLE_RUSH_DB_PATH`, default `/root/hermes-chess/data/puzzles.db`. |
| `backend/services/puzzle_rush.py` | Run engine: lifecycle, clock, move validation, stats, bests, ranks, leaderboards. |
| `backend/api/puzzle_rush.py` | Blueprint `puzzle_rush_bp`: optional auth, ownership, guest token, guest rate limit. |
| `backend/app.py` | Registers the blueprint (same try/except pattern as the others). |
| `supabase/migrations/20261012_049_puzzle_rush.sql` | `puzzle_rush_runs`, `puzzle_rush_attempts`, `puzzle_rush_bests` + indexes + RLS. **Not applied.** |
| `backend/scripts/bench_puzzle_rush_pick.py` | Pick micro-benchmark against the real DB (read-only). |
| `backend/tests/test_puzzle_rush_source.py` | 11 tests. |
| `backend/tests/test_puzzle_rush_api.py` | 48 tests. |

## Endpoints
Auth is optional everywhere except `/bests`. A bearer token makes the run the user's run. If a token is sent but is invalid, the response is **401**; it never silently becomes a guest run. Guest calls send the token as the `X-Guest-Token` header, or as `guest_token` in the body or query. All endpoints accept `tz` (IANA name, default `Asia/Almaty`).

- `POST /api/puzzlerush/runs {mode}` → 201 `{run_id, mode, started_at, deadline, server_now, puzzle, guest_token?}`
  - `puzzle` = `{id, index, fen, setup_move, rating, color}`.
  - Guests are rate-limited per IP (429).
- `POST /api/puzzlerush/runs/<id>/move {uci}` → `{result: correct|wrong|solved, reply?, next_puzzle?, score, strikes, streak, run_over, end_reason?, results?, started_at, deadline, server_now}`
  - An illegal or unparseable move returns 400 with no strike.
  - A move on an ended run, or after the deadline, returns **409** `{error: run_over, end_reason, …, results}`. A move that arrives after the deadline also ends the run as `timeout` at that point.
  - Two concurrent writes to the same run: the loser gets 409 `conflict`.
- `POST /api/puzzlerush/runs/<id>/quit` → state + `results`. It is idempotent.
- `GET /api/puzzlerush/runs/<id>` → summary + `attempts[]`.
  - While the run is active: `current_puzzle` (public fields + `played`, which contains only the setup move and the replies already revealed).
  - Once ended: each attempt gains `fen` + `solution`, and `results` is included.
- `GET /api/puzzlerush/bests` (auth required) → `{3min|5min|survival: {top_score, top_run_id, achieved_at, best_today}}`.
- `GET /api/puzzlerush/leaderboard?mode=&period=daily|weekly|all&scope=global|personal`
  - Returns `{entries: [{rank, user_id, display_name, score, run_id, ended_at}], me: {score, rank}|null}`.
  - Personal scope returns the user's top 10 runs and requires auth.
  - Ties share a rank (competition ranking). Daily = local day; weekly = local ISO week starting Monday.
- **Results payload** (§7.5), included whenever a run has ended: `{score, is_new_pb, longest_streak, highest_solved_rating, avg_ms_per_puzzle, duration_ms, personal_rank, global_rank: {daily, weekly, all}}`. Guests get `null` ranks and `is_new_pb: false`.

## Tests
- `tests/test_puzzle_rush_api.py` + `tests/test_puzzle_rush_source.py` + `tests/test_puzzles_api.py`: **67 passed, 0 failed** (48 + 11 + 8).
- The `app.py` registration test imports the real `app.py` in a subprocess and checks all six rules on `url_map`.
- Coverage:
  - Ramp formula; band selection, widening, and quality fallback; exclusions/no repeats; read-only connection.
  - Correct, wrong, multi-move, alternate mate, and early mate in a multi-mover.
  - Illegal moves; 3 strikes; timeout via frozen clock (boundary and rejection; the rejected move is not recorded); lazy timeout on GET.
  - Abandoned at 10 min idle; stale runs closed on a new run; quit (idempotent).
  - Solution never in active-run payloads (create, move, reply, GET); solution present after the run ends.
  - Guest token (header and body, wrong token, missing token); cross-user ownership; guest-token hijack of a user run; unknown or malformed ids; CAS conflict.
  - PB strictly-higher with ties kept on the earlier run; zero score is never a PB; guests never touch bests or ranks.
  - Best Today across the Almaty midnight boundary vs `tz=UTC`; invalid tz.
  - Leaderboard daily/weekly/all, week boundary, ties, personal scope, auth, invalid params; results ranks.
- Lint: `ruff check --isolated --select E,F,W,I --line-length 120` on all new files → clean. The repo has no linter configured; I used ruff from a throwaway venv in `/tmp`, and the project venv is unchanged.
- Full backend suite (regression check for `app.py`): **1188 passed, 1 failed, 2 skipped**. I ignored 4 modules that already fail to collect in this env: `test_rls_*` need `psycopg2`, plus `test_custom_domain_routes.py` and `test_middleware_custom_domain.py`. The one failure, `test_player_name_filter.py::test_player_name_carlsen_returns_games`, is a TWIC-DB test unrelated to this work, and it **passes when re-run alone**.

## Benchmark (real DB, 5.98M rows)
Command: `venv/bin/python scripts/bench_puzzle_rush_pick.py --runs 50 --length 60`. It simulates 50 full 60-puzzle runs, excluding ids already used.

| Metric | Value |
|---|---|
| Picks | 3000 |
| Mean | **0.283 ms** |
| p50 | 0.101 ms |
| p95 | 0.893 ms |
| p99 | 2.136 ms |
| Max | 5.862 ms |
| First pick (cold, incl. connect) | 2.6 ms |

All queries use `idx_puzzles_rating` (verified with EXPLAIN QUERY PLAN as `SEARCH … USING INDEX idx_puzzles_rating (rating=? AND rowid>?)`).

## Deviations from the spec, and why
1. **The quality filter is relaxed at the extremes.** The spec says `popularity >= 80 AND rating_deviation <= 80` leaves "plenty for every band". That is not true at the extremes. Counts of strict-quality puzzles in the real DB:
   - 400–499: **54**
   - 500–599: 2.8k
   - 2700–2799: 59
   - ≥ 2800: **0**

   With the strict filter, the ramp started near ~460–500 instead of 400, flattened at ~2750 from puzzle ~36 on, and those picks took 150–300 ms each because they scanned whole bands.

   Fix: each band is sampled once (300 rows via the index, cached per process). If fewer than 5% of the sampled rows pass the strict filter, that band uses `popularity >= 80` only. In practice the strict filter applies from ~600 to ~2500.
2. **The ramp saturates at the DB maximum (3323).** `target(i)` exceeds 3323 from i≈45. Without a clamp, a ±1920 widened band dipped back into strict-quality territory and served ~2750 puzzles.
3. **Clock includes a 3 s countdown.**
   - `started_at = created + 3 s`, and `deadline = started_at + 180/300 s`. This matches §1/§5.2 ("starts after Go!", "deadline … after the countdown"), where the brief only said "run start + mode seconds".
   - The first puzzle's `served_at` is `started_at`, so the countdown doesn't inflate avg time.
   - Responses include `server_now` so the client can correct clock skew.
4. **Extra columns beyond §5.2:** `guest_token_hash`, `display_name`, `deadline_at`, `last_activity_at`, `current_streak`, `puzzle_count`, `move_seq` (CAS), and `is_new_pb` (so a later GET still reports it).
   - `display_name` is a best-effort Clerk snapshot, cached per process, so leaderboards never call Clerk.
   - Guest tokens are stored only as SHA-256.
5. **All three tables are server-only under RLS** (rather than owner-read). Runs hold the selection seed and guest token hashes, and the frontend reads everything through Flask anyway.
6. **`/bests` does not use `@verify_clerk_token`.** That decorator's catch-all `except Exception` turns any 4xx raised inside the view (e.g. a bad `tz`) into a 500. The blueprint uses its own optional-auth helper and returns 401 itself.
7. **Guest rate limit** uses a dedicated `RateLimiter()` instance (free tier: 50 runs/hour, 200/day per IP), keyed on the first `X-Forwarded-For` hop, falling back to `remote_addr`. The global singleton is keyed by user id for LLM usage, so I didn't share it.
8. **Abandoned runs are closed lazily**: on any access to that run, or for a user's own stale runs when they start a new run. A guest run nobody touches again stays open. That's harmless, because guests are never ranked.
9. **The puzzle `id` is sent during the run**, because the brief's payload requires it. A determined cheater could look it up on lichess.org. Hiding it would mean an opaque per-run id; that is left for later if it matters.

## Out of scope / not done
- No frontend, no deploy/push, no restarts. Migration 049 was **not applied** anywhere. `/root/hermes-chess` was untouched (read-only access only).
- Phase 2 needs `/api/puzzlerush/*` rewrites in the Next.js config (like the `/api/databases` rewrites) before the frontend can reach these routes.
