# Coach Logging — Phase 2 Results

Voice-path instrumentation into the unified `coach_events` stream (migration 007)
plus the first-turn persistence race fix. Built on Phase 1 (`18cfd22`): reuses
`event_logger.log_event()` — no parallel logging mechanism was added. All logging
is fail-open; no new migrations (008's `client_ts`/`turn_id` columns already
exist). Work confined to `/root/chess-app` (SOURCE repo); `/root/hermes-chess`
was never touched.

## Test summary

| Suite | Baseline | After Phase 2 | Delta |
|-------|----------|---------------|-------|
| Hermes `pytest tests/` | 703 passed / **27 failed** | 736 passed / **27 failed** | +33 passed, **0 new failures** |
| Frontend (targeted: `src/hooks/__tests__/useGeminiLive.test.ts` + `src/app/api/coach`) | — | **110 passed** (7 files) | +10 new tests |

- The 27 Hermes failures are the pre-existing TWIC-DB / board-tool env baseline
  (`test_tool_twic_search`, `test_setup`, `board_control_tool`, `board_protocol`,
  etc.) — identical set before and after this change. Zero new failures.
- Frontend uses **vitest** (`npm test` → `vitest run`), so the Definition-of-Done
  `npx jest …` was run as the project-equivalent `npx vitest run <paths>`.
- Affected Hermes files alone: **150 passed** (`test_voice_metrics`,
  `test_voice_quota`, `test_tool_bridge`, `test_session_persistence`,
  `test_coach_routes`).

## Per-task implementation

### Task 1 — Voice metrics sanitizer fix + enriched beacons
- `hermes/src/voice_metrics.py` — sanitizer now **retains** the `error` cause
  string (capped at 500 chars) and keeps `turn_id`, `ok`, `error_code`,
  `end_reason`, `reason` when present; still strictly typed (no arbitrary
  passthrough — unknown keys dropped). New beacon events accepted: `reconnect`,
  `tool_timeout`, `barge_in`, `drop`, `session_end`, `mint_rejected`.
- `frontend/src/hooks/useGeminiLive.ts` —
  - tool beacon now carries `ok` + `error_code` (`http_<status>` / `network`);
  - a `tool_timeout` beacon fires when the 10s client abort trips (and the plain
    `tool` beacon is suppressed for that call, to avoid double-logging);
  - a `barge_in` beacon fires when local-RMS barge-in interrupts coach audio
    (the server-`interrupted` path does **not** emit — spec says local RMS only);
  - every beacon carries `session_id` (already present) and a per-utterance
    client-generated `turn_id` (`crypto.randomUUID`, minted on user speech / a
    tool call, cleared at turn end);
  - a `session_end` beacon carries `session_ms` + `end_reason`
    (`user_stop | quota_exhausted | error | drop`).

### Task 2 — Persist voice beacons to `coach_events`
- `hermes/src/voice_metrics.py` — new pure mapper `beacon_to_event(payload,
  user_id)` returning `log_event(...)` kwargs (or `None`). Mapping: `connect`→
  `voice_connect`, `reconnect`→`voice_reconnect`, `error`/`drop`→`voice_drop`
  (cause in payload), `tool`→`tool_call` (surface=voice, ok/error_code/duration),
  `tool_timeout`→`tool_timeout`, `barge_in`→`barge_in`, `turn`→`turn_end`
  (ttfa in payload), `session_end`→`session_end`, `mint_rejected`→`mint_rejected`.
- `hermes/src/server.py` — `/api/coach/metrics` handler, after the existing
  sanitize + JSONL append + `end`-beacon metering, maps the beacon and calls
  `log_event(**evt)` wrapped in try/except (an event-log failure never 500s the
  endpoint). At most one coach event per request → no double-log within a request.

### Task 3 — Server-side voice failure events
- `frontend/src/app/api/coach/live-token/route.ts` — on every mint rejection
  emits `mint_rejected` (POST to Hermes `/api/coach/metrics` with `X-User-Id`,
  the simplest existing path) distinguishing `quota_exhausted` / `rate_limited`
  / `error`; each lands in `coach_events` with the user id. Also now passes
  `enforce=true` on the quota lookup.
- `hermes/src/tool_bridge.py` — `coach_tool_dispatch` now times the dispatch and
  emits the **authoritative** `tool_call` event (surface=voice, ok/error_code/
  duration_ms, `check_moves` verdict folded in via `_classify_tool_result`).
  Beacon-sourced tool events are marked `payload.source: "beacon"` and only the
  client-observed **failures** map (successful `tool` beacons return `None`), so
  a server-executed call is never double-logged.
- `hermes/src/voice_quota.py` — new `check_exhausted()` emits `quota_exhausted`
  when the enforcement check rejects; wired into `/internal/voice/quota` behind
  `enforce=true` (`server.py`) so plain display reads never spam the event.

### Task 4 — True utterance timestamps for voice messages
- `frontend/src/hooks/useGeminiLive.ts` — `onTranscript` now carries `turnId`
  (the utterance's correlation id).
- `frontend/src/components/coach/CoachChat.tsx` — voice transcript write-back
  now sends `client_ts` (`new Date().toISOString()` at utterance completion) and
  `turn_id` (captured at the utterance's first chunk).
- `frontend/src/app/api/coach/sessions/[id]/messages/route.ts` — forwards
  `client_ts` + `turn_id` to Hermes.
- `hermes/src/server.py` — `CoachMessageRequest` accepts `client_ts` + `turn_id`;
  `coach_append_message` threads them as `extra` to `add_message` →
  `persist_message` → `coach_messages.client_ts` / `.turn_id` (migration 008).
  Fail-soft: the existing missing-column retry drops them on pre-migration prod.

### Task 5 — First-turn persistence race fix
- `hermes/src/session_persistence.py` — root cause: `coach_messages` insert and
  `coach_sessions` upsert were independent background threads; the message could
  win and FK-violate. Fix (spec approach **(a)**, per-session sequencing): a
  readiness `threading.Event` is registered **synchronously** in
  `persist_session()` (on the request thread, before the write thread spawns, so
  it always exists by the time `add_message` follows `create()`); `_persist_session`
  sets it in a `finally`; `_persist_message` calls `_await_session_ready()`
  (bounded by `TIMEOUT`) before inserting. The existing retry + `persistence_failure`
  emission for genuine failures is preserved unchanged. Gate is dropped on
  `delete_session` (bounded memory).

### Task 6 — Tests
- Hermes:
  - `tests/unit/test_voice_metrics.py` — sanitizer keeps error cause + drops junk;
    `beacon_to_event` mapping for every type; `mint_rejected` classification;
    endpoint maps a beacon to `coach_events` and never 500s on a logger failure.
  - `tests/unit/test_tool_bridge.py` — voice `tool_call` emitted (ok=true) on
    success, ok=false on error, `check_moves` verdict in the payload.
  - `tests/unit/test_voice_quota.py` — `quota_exhausted` emitted when exhausted,
    not when within quota / unlimited; endpoint emits only with `enforce=true`.
  - `tests/unit/test_coach_routes.py` — `client_ts`/`turn_id` reach
    `persist_message` as `extra`.
  - `tests/unit/test_session_persistence.py` — Task-5 race regression (slow
    session insert → message still lands **after** it) + a message with no pending
    session write does not hang.
- Frontend (`vitest`):
  - `src/hooks/__tests__/useGeminiLive.test.ts` — tool beacon ok=true+turn_id,
    tool beacon ok=false+error_code, `tool_timeout` (and no `tool`) on abort,
    `barge_in`, `session_end` (`user_stop`) + `end` on disconnect, `reconnect`
    vs `connect` beacon, `session_end` (`quota_exhausted`) on countdown zero.
  - `src/app/api/coach/__tests__/live-token.test.ts` — `enforce=true` on the
    quota check; `mint_rejected(quota_exhausted)` with `X-User-Id`;
    `mint_rejected(error)` on a mint throw.
  - `src/app/api/coach/sessions/[id]/messages/__tests__/route.test.ts` —
    `client_ts` + `turn_id` forwarded.

## Deviations from spec (with rationale)

1. **Two lifecycle beacons, not a renamed one.** Task 1 asks for a `session_end`
   beacon; a metering `end` beacon already exists (the server meters a voice row
   from it, and existing tests key on `event=="end"`). Rather than rename `end`
   (which would break metering + tests), the client emits **both** on teardown:
   `end` (metering, unchanged → no coach event) and `session_end` (event-log
   lifecycle, carries `end_reason` → `session_end` coach event). This matches the
   Task 2 taxonomy exactly and keeps the baseline green.

2. **`quota_exhausted` gated behind `enforce=true`.** `get_quota()` is also used
   for plain display reads, so emitting on every remaining≤0 read would spam the
   event. The emission lives in `voice_quota.check_exhausted()` (per Task 3.3)
   and only runs when the mint path calls the endpoint with `enforce=true`. It
   intentionally coexists with the client-side `mint_rejected(quota_exhausted)`
   (Task 3.1) — the spec lists both as separate deliverables (one is the
   client-facing mint decision, one is the ledger's enforcement record).

3. **Task 5 uses approach (a), not (b).** Approach (b) (upsert the session on FK
   retry) needs the `user_id` + `board_state` that `persist_message` does not
   have. Per-session sequencing (a) is deterministic, needs no extra data, and
   fully closes the race; the genuine-failure retry + `persistence_failure`
   emission is untouched.

4. **Successful `tool` beacons are not mapped to `coach_events`.** The server-side
   `tool_bridge` execution event is authoritative; only client-observed tool
   failures (and timeouts, via the dedicated `tool_timeout`) map from the beacon,
   marked `payload.source: "beacon"`, so no call is double-logged (Task 3 rule).

5. **Frontend runner is vitest, not jest** — DoD command run as the project
   equivalent `npx vitest run <paths>`.

## Files changed
- `hermes/src/voice_metrics.py`
- `hermes/src/tool_bridge.py`
- `hermes/src/voice_quota.py`
- `hermes/src/session_persistence.py`
- `hermes/src/server.py`
- `frontend/src/hooks/useGeminiLive.ts`
- `frontend/src/components/coach/CoachChat.tsx`
- `frontend/src/app/api/coach/live-token/route.ts`
- `frontend/src/app/api/coach/sessions/[id]/messages/route.ts`
- Tests: `hermes/tests/unit/{test_voice_metrics,test_voice_quota,test_tool_bridge,test_session_persistence,test_coach_routes}.py`,
  `frontend/src/hooks/__tests__/useGeminiLive.test.ts`,
  `frontend/src/app/api/coach/__tests__/live-token.test.ts`,
  `frontend/src/app/api/coach/sessions/[id]/messages/__tests__/route.test.ts`
