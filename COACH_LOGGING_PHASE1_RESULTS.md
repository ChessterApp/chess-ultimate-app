# AI Coach Logging System — Phase 1 Results

Implemented per `COACH_LOGGING_PHASE1_SPEC.md`. Hermes-only (`/root/chess-app/hermes`).
No migrations applied, nothing pushed, `/root/hermes-chess` untouched.

## Task 1 — Migrations (SQL written, NOT applied)

Operator applies these to Supabase (in order):

- `hermes/migrations/007_coach_events.sql` — `coach_events` table + 4 indexes
  (`session_id`; `user_id, created_at`; `event_type, created_at`; partial
  `created_at WHERE severity='error'`). Matches the spec schema exactly.
- `hermes/migrations/008_coach_messages_enrich.sql` — 7 additive/nullable columns
  on `coach_messages` (`turn_id`, `model`, `prompt_version`, `latency_ms`,
  `client_ts`, `prompt_tokens`, `completion_tokens`) + index on `(turn_id)`.

## Task 2 — Event logger

- `hermes/src/event_logger.py` (new) — `log_event(...)` + `new_turn_id()`.
  - **Dual sink, local-first:** spool `metrics/coach-events-YYYYMMDD.jsonl`
    written synchronously first (durable even if Supabase is down), then a
    best-effort enqueue to a bounded (1000) daemon-drained queue → Supabase REST
    `coach_events`. Queue-full drops the OLDEST event and counts drops, logging
    the count at most once/minute. Follows the `session_persistence` /
    `cost_monitor` fail-open daemon-thread pattern.
  - Never raises: every sink is wrapped; a broken logger can't break a turn.
  - Truncation: string payload fields > 2000 chars → `…[truncated]`; total
    serialized payload > 8 KB → `{"truncated": true, "keys": [...]}`.
  - `new_turn_id()` → 12-char uuid4 hex.

## Task 3 — Prompt versioning

- `hermes/src/prompt_builder.py` (edited) — `PROMPT_TEMPLATE_VERSION = "1"`,
  `get_prompt_version()`, `_compute_prompt_version()`.
  - `prompt_version` = first 10 hex of `sha256(SOUL.md + PROMPT_TEMPLATE_VERSION)`.
  - Cached; recomputed only when SOUL.md mtime changes. Fully defensive
    (falls back to a template-only hash if SOUL.md can't be read).

## Task 4 — Text chat loop instrumentation

- `hermes/src/model_router.py` (edited) — added `explain_route()` returning
  `{model, tier, reason, matched}`; `route_model()` is now a thin wrapper (all
  existing callers unchanged).
- `hermes/src/server.py` (edited) — instrumented `POST /api/coach/chat`:
  - One `turn_id` per turn (`new_turn_id()`), threaded through every event and
    onto the coach_messages rows.
  - `turn_start` — payload: routing tier/reason/matched keyword, message length,
    FEN (when supplied), `prompt_version`, selected tool subset (names only).
  - `tool_call` — one per tool execution, off the async hot path (fired from the
    tool-complete callback): `tool_name`, `duration_ms`, `ok`, `error_code`,
    truncated args + result summary. **check_moves** rows also carry the
    legal/illegal verdict counts (hallucination metric). This closes the key gap
    — text tool calls were ephemeral SSE frames only.
  - `turn_end` — payload: prompt/completion tokens, `latency_ms`, iteration
    count, finish reason; `ok=True`.
  - `max_iterations_hit` (warn) when `_api_call_count >= max_iterations`.
  - `empty_response` (warn) when the model returns nothing usable.
  - `llm_error` (error) on the streaming agent failure — **and now also writes a
    `coach_diagnostics` record**, fixing the known bug where the streaming path
    left zero diagnostic trace.
  - `stream_disconnect` (warn) on client disconnect mid-stream (via
    `GeneratorExit` / `CancelledError` in the SSE generator); payload carries
    chars-streamed-so-far and the partial assistant text (≤2000 chars).
  - `persistence_failure` (error) when the coach_messages write-back fails.
- `hermes/src/session_persistence.py` (edited) — `persist_message()` gained
  `extra` (enrichment columns) + `evt` (event context). Fail-soft on
  pre-migration prod: a column-missing error (`PGRST204` / `42703` /
  "column … not found") triggers ONE warn log and a retry with just the base
  row; a hard failure emits `persistence_failure`. Added `_is_missing_column_error()`.
- `hermes/src/sessions.py` (edited) — `Session.add_message()` threads
  `extra`/`evt` to the persistence layer (other callers unchanged).
- Assistant + user coach_messages rows are stamped with `turn_id`, `model`,
  `prompt_version`; the assistant row additionally with `latency_ms`,
  `prompt_tokens`, `completion_tokens`.

## Task 5 — Tests

Framework runs from prod venv site-packages on PYTHONPATH (source repo has no venv):
`SP=/root/hermes-chess/.venv/lib/python3.12/site-packages; PYTHONPATH=$SP python3 -m pytest`

New / updated test files (all pass):
- `tests/unit/test_event_logger.py` (new) — 15 tests: spool write, queue drain to
  a mocked Supabase client, never-raises on sink failure, truncation (field +
  oversized-payload stub), turn_id shape/uniqueness, queue drop-oldest overflow.
- `tests/unit/test_prompt_version.py` (new) — 6 tests: 10-hex shape, stable across
  calls, changes on template-constant + SOUL content change, mtime-triggered
  recompute, read-failure fallback.
- `tests/unit/test_coach_chat_events.py` (new) — 5 tests: happy path w/ tool call
  (turn_start/tool_call/turn_end + check_moves verdict + turn_id correlation),
  llm_error (event + diagnostic), max_iterations_hit, empty_response,
  stream_disconnect (drives the SSE generator + `aclose()`).
- `tests/unit/test_model_router.py` (updated) — +5 tests for `explain_route`.
- `tests/unit/test_session_persistence.py` (updated) — +3 tests (extra columns
  sent, missing-column retry, persistence_failure emit); `FakePersistence`
  double updated for the new signature.

### Test counts
- New tests added: **34** (15 + 6 + 5 + 5 + 3).
- Full suite: **703 passed, 27 failed** in ~103s.
- Baseline before this work: **669 passed, 27 failed**.
- The 27 failures are the pre-existing environment-only set (missing 42 GB TWIC
  SQLite DB → `test_setup` / `test_tool_get_pgn` / `test_tool_twic_search`;
  board-tool framework version drift → `test_board_control_tool` /
  `test_board_protocol` / `test_tools_with_hermes`). **Zero new failures.**

Linting: no linter is configured in the repo and none is installed in the venv
(no ruff/flake8/black). Ran `python -m py_compile` over every changed source and
test file — clean.

## Deviations from spec
- **`persistence_failure` scope:** wired for the `coach_messages` write-back (the
  new instrumented path). The `token_usage` write-back goes through the existing
  `cost_monitor._persist`, which swallows its own errors and doesn't
  `raise_for_status`, so a failure there isn't observable without rewriting
  `cost_monitor` — left out of scope for Phase 1 to keep the change focused.
- **`turn_end` finish reason** is derived best-effort (`empty` / `max_iterations`
  / `stop`) from agent attributes (`_api_call_count`, `max_iterations`), since the
  agent doesn't expose a single post-run finish-reason field to the server.
- No frontend files were touched (Phase 1 is Hermes-only, as expected).

## For the operator
Apply, in order, to Supabase:
1. `hermes/migrations/007_coach_events.sql`
2. `hermes/migrations/008_coach_messages_enrich.sql`

Writes are fail-soft before the migrations land: coach_messages enrichment
columns silently fall back to a base insert, and coach_events simply spools
locally (and no-ops the Supabase POST until the table exists).
