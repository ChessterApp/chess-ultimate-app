# Voice/Text AI Coach Parity Fixes — Results

Implements `VOICE_TEXT_PARITY_SPEC.md`. All four tasks landed with passing tests
and a successful frontend build. Committed locally only (no push, no deploy, per
constraints). `/root/hermes-chess` was not touched.

## Test results (summary)

| Suite | Result |
|---|---|
| Hermes unit suite (`tests/unit`) | **590 passed, 23 failed** |
| — 23 failures | Pre-existing, environment-only: TWIC 42GB SQLite DB absent (`test_tool_twic_search`, `test_tool_get_pgn`, `test_setup`) + board-tool framework version drift (`test_board_control_tool`, `test_board_protocol`). Baseline per project memory was ~27 env-only failures; none are in files touched here. |
| — new Hermes tests added | **30** (all passing) |
| Frontend vitest suite (full) | **2466 passed / 271 files** |
| — new/updated frontend tests | 4 new + 1 updated (all passing) |
| `npm run build` (frontend) | **succeeds** |

Run Hermes tests with the framework on PYTHONPATH (source repo has no venv):
```bash
export HOME=/root && cd /root/chess-app/hermes
SP=/root/hermes-chess/.venv/lib/python3.12/site-packages
PYTHONPATH=$SP python3 -m pytest -q tests/unit
```

---

## Task 1 — Rate limiting + usage metering on the voice path

**Voice tool path rate limiting** — reuses the exact text-chat mechanism
(`SlidingWindowRateLimiter`, free/premium/pro tiers) with a dedicated limiter
instance (higher ceilings, since one spoken turn fires several tool calls).
Enforced in Hermes' tool bridge (matching where text enforces — server-side),
returning the same 429 payload shape. The Next `/api/coach/tool` proxy now
forwards a clear error payload; the voice hook already feeds tool errors back to
the model as a `functionResponse`, so the coach says it's busy and the session
never crashes.

**Live-token mint rate limiting** — a per-user/hour, tier-based limit
(`voice_token_rate_limiter`, 1-hour window) enforced by the new
`/api/coach/voice/prompt` endpoint the mint path already calls. On 429 the
live-token route refuses to mint and returns 429 (so sessions can't be spawned
unboundedly).

**Metering** — voice usage recorded to Supabase `token_usage` with
`surface="voice"`: one row per tool call (`tool_name`) from the tool bridge, and
one row per session with `duration_ms` on session end. Audio token counts aren't
available server-side, so voice rows carry 0 tokens; duration + per-call rows let
spend be estimated. The client now emits a session-end (`end`) beacon on
disconnect with `session_ms`; the metrics endpoint meters from it. JSONL voice
telemetry is preserved (the `end`/`session_ms` fields were added to it, not
replaced).

Files changed:
- `hermes/src/middleware/rate_limiter.py` — `enforce_rate_limit(request, limiter=…)`; `voice_tool_rate_limiter`, `voice_token_rate_limiter` + their tier tables.
- `hermes/src/tool_bridge.py` — enforce voice-tool limit + meter each dispatch.
- `hermes/src/cost_monitor.py` — nullable `tool_name`/`duration_ms` columns in the record/persist path; `record_voice_event()` fire-and-forget helper; `VOICE_MODEL`.
- `hermes/src/voice_metrics.py` — accept `end` event + `session_ms` (1h ceiling).
- `hermes/src/server.py` — metrics endpoint meters a voice session row on `end`.
- `hermes/migrations/005_token_usage_voice.sql` — new nullable `tool_name`, `duration_ms` columns (additive; NOT applied to prod — deploy handled separately).
- `frontend/src/app/api/coach/tool/route.ts` — forward Hermes 429/error payload with `rate_limited`/`retry_after`.
- `frontend/src/hooks/useGeminiLive.ts` — session-start anchor + `end` duration beacon on disconnect.

Tests: `test_tool_bridge.py` (+3: metering, 429 after tier limit, 429 payload),
`test_rate_limiter.py` (+4: voice limiter config + custom-limiter enforcement),
`test_cost_monitor.py` (+4: voice fields persisted/omitted, `record_voice_event`),
`test_voice_metrics.py` (+4: `end`/`session_ms` accept+clamp+JSONL),
`test_coach_routes.py` (+2: `end` beacon meters, non-`end` doesn't),
frontend `routes.test.ts` (+1: 429 payload surfaced).

## Task 2 — Student profile in the voice system prompt

New authenticated Hermes endpoint `POST /api/coach/voice/prompt` returns
`{ system_prompt, profile_context }`. It renders the same profile context text
chat gets (`UserProfile.to_prompt_context()` — rating/goals/weaknesses). The
live-token route fetches it server-side at mint time and locks the returned
prompt into the ephemeral token. **Fails soft**: on any non-429 failure/timeout
the route falls back to the hardcoded prompt and mints exactly as before; on an
empty profile the profile section is simply omitted. Added text is compact
(profile context is a few short lines).

Files changed: `hermes/src/server.py` (endpoint + 5-min profile cache),
`hermes/src/prompt_builder.py` (`build_voice_prompt`),
`frontend/src/app/api/coach/live-token/route.ts` (fetch + fail-soft fallback).

## Task 3 — Single-source system prompts (stop drift)

`build_voice_prompt()` in `prompt_builder.py` renders from the **same** SOUL.md
persona core the text path uses, plus a spoken-style adaptation layer
(`VOICE_STYLE_LAYER`, `VOICE_TOOL_LAYER`): short sentences, no markdown,
speak-before-tool-call, board-protocol notes. Exposed via the same
`/api/coach/voice/prompt` endpoint as Task 2 (one call → `{ system_prompt,
profile_context }`). The live-token route fetches it at mint time and keeps the
original hardcoded `COACH_VOICE_PROMPT` + `COACH_TOOL_GUIDANCE` constants in code
as the fallback. All prior voice-specific directives (acknowledge before tool
calls, concise spoken style, no markdown) are preserved in the shared layer.

**Cache placement note:** the spec suggested a ~5-min cache in the live-token
route. Because the same endpoint also enforces the mint rate limit (Task 1b), a
route-side cache would let cache hits bypass the limit. Instead the endpoint
enforces the limit on **every** call and caches only the expensive part (the
Supabase profile fetch) server-side for 5 min — same latency win, no bypass.

Tests: `test_prompt_builder.py` (+7: persona+spoken style, profile parity, FEN
anchor, locale directive, tools toggle, no heavy-analysis leak),
`test_coach_routes.py` (+4: endpoint returns prompt+profile, profile parity,
profile cached, mint rate-limited), frontend `live-token.test.ts` (+3: uses
Hermes prompt, propagates 429 without minting, falls back when unreachable;
1 updated for the added parallel call).

## Task 4 — Tool-activity frames + dead code cleanup

**SSE tool frames** — Hermes' `/api/coach/chat` stream now emits `{"tool_call":
"<name>"}` when a tool starts and `{"tool_result": {"tool","ok"}}` when it
completes, matching the exact shape `CoachChat` already parses (raw tool-name
string for `tool_call`; truthy value clears the spinner for `tool_result`). Wired
via the agent's existing `tool_start_callback`/`tool_complete_callback`, bridged
onto the SSE queue the same way token deltas are. The previously-dead
`ToolIndicator` now lights up during a tool-using exchange. The Next chat proxy
already forwards all SSE events, so no proxy change was needed.

Tests: `test_coach_routes.py` (+2: emits tool_call/tool_result with ok=true;
error result marks ok=false).

**Dead code — removed** (git history is the backup; also copied to
`/root/.trash-voice-parity/`):
- `backend/api/chat.py` — the orphaned Flask `/api/chat/*` coach blueprint
  (analysis, analysis/stream, history, conversations, conversation delete, usage,
  health, metrics). Reachable at runtime only through the BFF below; no frontend
  component/hook calls it. Its registration in `backend/app.py` was removed.
- `frontend/src/pages/api/chat/stream.ts` — the orphaned Clawdbot/Mastra BFF that
  was the only caller of the Flask blueprint. No component/hook fetches it; its
  only references were a service-worker path-match and that match's test.

**Dead code — kept (still referenced), NOT removed:**
- The faster-whisper push-to-talk path
  (`frontend/src/pages/api/chat/transcribe.ts` + `transcribe-worker.py` +
  `hooks/useVoiceRecorder.ts`) is live: `ChatTab → useVoiceRecorder →
  /api/chat/transcribe → transcribe-worker.py (faster_whisper)`, and `ChatTab` is
  rendered by `ChessterAnalysisView` and `puzzle/page.tsx`. It shares the
  `/api/chat/` path prefix with the removed Flask blueprint but is a separate Next
  route + Python worker.
- `backend/app.py`'s base `@app.route('/api/chat')` legacy endpoint — a different,
  intentionally-kept route (out of scope; the spec targeted the `/api/chat/*`
  blueprint).
- `frontend/public/sw.js` line excluding `/api/chat/stream` from caching — left
  as-is (harmless no-op after the BFF removal; touching the service worker is
  deploy-sensitive and the service-worker test still passes unchanged).

Also updated a now-dangling comment in `frontend/src/pages/api/position-analysis.ts`
that referenced the deleted `chat/stream.ts`.

---

## Intentionally left undone / notes

- **Migration 005 not applied to prod.** Voice metering rows with
  `tool_name`/`duration_ms` need the new columns; until applied, those two fields
  are silently dropped by PostgREST (the insert is fire-and-forget and swallows
  errors) while `surface="voice"`, `session_id`, etc. still persist. Apply with
  `psql "$SUPABASE_DB_URL" -f hermes/migrations/005_token_usage_voice.sql`. Prod
  deploy is handled separately after review, per constraints.
- **Tier resolution.** Like the existing text-chat proxy, the voice proxies don't
  yet send `x-subscription-tier`, so both voice limiters currently resolve to the
  `free` tier for everyone (the mechanism honors the header the moment billing is
  wired into it — unchanged from text). Not expanded here to keep scope minimal.
- **Session-end beacon** fires on explicit `disconnect()` (user stop). A hard
  browser kill mid-session may miss it (`keepalive` best-effort); per-tool rows
  still capture activity for those sessions.
