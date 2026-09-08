# AI Coach Logging — Phase 3 Results

Implements analytics, retention, deletion cascade, and daily digest per
`COACH_LOGGING_PHASE3_SPEC.md`. All work is in `/root/chess-app`
(`frontend/` + `hermes/`); `/root/hermes-chess` was never touched.

## Task 1 — DB-backed analytics endpoint
`GET /api/coach/analytics` now aggregates from Supabase instead of the
process-memory list (which reset on every restart).

Files:
- `hermes/src/analytics_db.py` (new) — bounded, time-filtered, column-projected
  PostgREST fetches (paged via `Range`, hard `_MAX_ROWS` cap); pure
  `aggregate_events()` core; 7d + 24h windows (24h derived in-memory from the
  7d slice — one round-trip per table); per-user scope; 60s in-process admin
  cache (`_AdminCache`).
- `hermes/src/server.py` (modified) — endpoint rewritten to call
  `get_admin_analytics_cached()` (admin) / `compute_user_analytics()` (user)
  off the event loop via `asyncio.to_thread`. `analytics_tracker` calls are left
  in place (other code still writes to it); only the read path changed.

Metrics returned (admin): turn counts by surface, error counts by
event_type/error_code, per-tool call count + success rate + p50/p90 duration,
illegal-move rate (check_moves `payload.check_moves_verdict.illegal > 0` / total),
barge-in count, voice session count + avg duration, mint rejections by reason,
active users, and token/cost totals by model — each for the 7d and 24h windows.
Per-user scope returns only own turn counts, tool usage, and voice minutes.

Deviation: the spec's "totals" is served as a **7d + 24h** window pair rather than
an unbounded all-time roll-up, because an all-time aggregate would require
fetching whole tables (explicitly forbidden) or PostgREST server-side aggregate
functions (disabled by default on Supabase). Windowed bounded fetches honor the
"do not fetch whole tables" constraint. Documented here as the one deviation.

## Task 2 — Retention purge job
Files:
- `hermes/src/retention.py` (new) — `_purge_table()` batch-deletes (1000
  ids/round via select-ids-then-`DELETE ... id=in.(...)`) so no statement locks
  the whole table; purges `coach_events` older than
  `COACH_EVENTS_RETENTION_DAYS` (default 90) and `analytics_events` older than
  180 days. `_purge_spool()` deletes local `coach-events-*.jsonl` /
  `voice-latency-*.jsonl` beacons older than 14 days.
  `coach_messages` / `token_usage` / `voice_usage` are never touched.
  `run_purge()` logs a `retention_purge` summary event through `event_logger`.
  `retention_loop()` runs first 10 min after boot then every 24h, guarded by the
  `RETENTION_ENABLED` kill-switch (default on). Fully fail-open.
- `hermes/src/server.py` (modified) — `retention_loop()` started as a background
  `asyncio` task in the app `lifespan`, cancelled cleanly on shutdown.

## Task 3 — Clerk deletion cascade
Files:
- `frontend/src/app/api/webhooks/clerk/route.ts` (modified) —
  `cascadeDeleteCoachData(clerkUserId)` added and wired into the `user.deleted`
  handler. `coach_messages` (no `user_id` column) is purged via the user's
  `coach_sessions` ids, then `coach_sessions`, `coach_events`, `token_usage`,
  `voice_usage`, `analytics_events` are deleted by `user_id`. Each table is
  best-effort (a failure logs and continues) and the webhook still returns 200.
  Uses the existing `supabaseAdmin` server client.

## Task 4 — Daily digest script
Files:
- `hermes/scripts/daily_digest.py` (new) — standalone
  `python scripts/daily_digest.py [--hours 24]`; loads the hermes `.env` via
  `config.load_env`, reuses `analytics_db`'s fetch + `aggregate_events` core, and
  prints a compact markdown digest (turns text/voice, top-5 errors, tool
  p50/p90 + failure rate, illegal-move rate, barge-ins, voice minutes, mint
  rejections, new-user count, cost by model). Exits 0 even on partial data;
  missing sections print `⚠️` warnings. New-user count is skipped (with a
  warning) when >300 active users to keep the `in.(...)` filter bounded. No
  crontab entry created (operator wires cron).

## Task 5 — Tests
New hermes unit tests (40 tests, all passing):
- `hermes/tests/unit/test_analytics_db.py` (20) — percentiles, full
  `aggregate_events` coverage (turns, tools, errors, barge-in, voice, mint,
  illegal-move, tokens, user-scope hiding), paged/`_fetch` behavior + fail-open,
  window orchestration, 60s cache memoisation.
- `hermes/tests/unit/test_retention.py` (12) — env config + kill-switch, single
  & multi-batch deletes (asserts exact `id=in.(...)`), fail-open, spool rotation
  (keeps recent/unrelated), `run_purge` summary + `retention_purge` event.
- `hermes/tests/unit/test_daily_digest.py` (8) — digest formatting (populated +
  empty warnings + fetch failure), new-user count logic, `main` exit 0.
- `hermes/tests/unit/test_health.py` (modified) — the analytics endpoint test
  updated to the new DB-backed per-user contract (`scope`,
  `turn_counts_by_surface`, `tools`, `voice_minutes_used`).

New frontend test (5 tests, all passing):
- `frontend/src/app/api/webhooks/clerk/__tests__/route.cascade.test.ts` — full
  cascade across all tables, messages-via-sessions, per-table best-effort
  isolation, session-lookup failure, and no-user-id skip. Carries its own
  Supabase mock (select + delete + eq + in) so it stays independent of the
  existing `route.test.ts` mock.

### Test counts vs baseline
- **Hermes full suite:** `27 failed, 776 passed` (94s).
  Baseline before changes: `27 failed, 736 passed`. The 27 failures are the
  documented pre-existing env-only failures (TWIC SQLite DB absent +
  stale board-protocol tests); **zero new failures**. +40 new passing tests.
- **Frontend (touched suites):** clerk webhook — `27 passed`
  (22 existing `route.test.ts` + 5 new `route.cascade.test.ts`).
- **Lint:** `eslint` clean on the changed frontend files (exit 0). `tsc` has 75
  pre-existing errors in unrelated test files; none in the files changed here.

Run commands:
```
# hermes
cd /root/chess-app/hermes
PYTHONPATH=/root/hermes-chess/.venv/lib/python3.12/site-packages:$PWD \
  /root/hermes-chess/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
# frontend
cd /root/chess-app/frontend
npx vitest run src/app/api/webhooks/clerk/__tests__/
```
(Note: the prod venv has no `pytest-timeout`, so the spec's `--timeout=120` flag
was dropped — it is unrecognized there.)

## Migrations
None added. All tables (`coach_events`, `coach_messages`, `token_usage`,
`voice_usage`, `analytics_events`, `coach_sessions`) already exist from prior
migrations; Phase 3 is read/purge/cascade only and needs no schema change.

## Deviations summary
1. **Analytics "totals" → 7d + 24h windows** (not all-time) to honor the
   "no whole-table fetches" constraint (see Task 1).
2. **`--timeout` flag dropped** — `pytest-timeout` is not installed in the prod
   venv, so the suite was run without it (full suite, not `-x`, as specified).
