# Voice/Text AI Coach Parity Fixes — Spec

Repo: `/root/chess-app` (Next.js frontend in `frontend/`, Hermes coach service source in `hermes/`).

Background: The AI coach has two modes. Text chat: browser → `frontend/src/app/api/coach/chat` → Hermes (FastAPI, `hermes/src/server.py`) → OpenRouter, with keyword model routing (`hermes/src/model_router.py`), ~20 tools, student profile + tactical analysis in the prompt, per-tier rate limits, and cost tracking to Supabase `token_usage`. Voice mode: browser ↔ Google Gemini Live directly (`gemini-3.1-flash-live-preview`); the server only mints an ephemeral token (`frontend/src/app/api/coach/live-token`) with a hand-written spoken system prompt, and Gemini's function calls are proxied via `frontend/src/app/api/coach/tool` → Hermes tool bridge (`hermes/src/tool_bridge.py`). Voice has NO rate limiting, NO cost metering, NO student profile, and its prompt is maintained separately from Hermes' `SOUL.md` persona.

Implement the following four fixes. Read the existing code carefully before changing anything — reuse existing patterns (rate limiter, cost tracking, profile context) rather than inventing new ones.

## Task 1: Rate limiting + usage metering on the voice path
- Add per-user rate limiting to the voice tool path. Apply the SAME tier-based limits mechanism the text chat path already uses (find it — free/premium/pro tiers). Enforce at the frontend `/api/coach/tool` route and/or Hermes tool bridge — whichever matches the existing enforcement pattern for text. Return 429 with a clear error payload when exceeded; the client hook should surface it gracefully (coach says it's busy, does not crash the session).
- Add rate limiting to `/api/coach/live-token` minting itself (e.g., max N token mints per user per hour by tier) so voice sessions can't be spawned unboundedly.
- Meter voice usage: record voice tool invocations and voice session lifecycle into the existing Supabase `token_usage` table using its `surface` column (value `voice`). At minimum: one row per tool call (tool name, user_id, timestamp) and one row per session with duration when the session ends/disconnects (client already sends latency/telemetry beacons — hook session-end metering into that path or the existing `voice_metrics.py`). Exact token counts for Gemini Live audio aren't available server-side; record duration + tool-call counts so cost can be estimated. Do not break the existing `voice_metrics` JSONL telemetry.

## Task 2: Student profile in the voice system prompt
- The live-token route must include the student profile (rating, goals, weaknesses) in the system instruction it locks into the ephemeral token — the same profile context text chat gets. Hermes builds this via `hermes/src/user_profile.py` (`to_prompt_context()` or similar). Preferred: expose a small authenticated Hermes endpoint (or extend the existing prompt/profile endpoint if one exists — check `frontend/src/app/api/coach/profile` and Hermes routes) that returns the rendered profile context string for a user; the live-token route fetches it server-side and appends it to the system instruction. Must fail soft: if Hermes is down or the profile is empty, mint the token without profile exactly as today. Keep the added text compact (< ~1.5KB).

## Task 3: Single-source system prompts (stop drift)
- Today the voice prompt is hand-written in the live-token route while text uses Hermes' `SOUL.md` + prompt_builder. Refactor so both render from one source: add a voice/spoken rendering in Hermes (e.g., `prompt_builder.py` gains a `build_voice_prompt()` that takes SOUL.md persona core + a spoken-style adaptation layer: short sentences, no markdown, speak-before-tool-call rule, board-protocol notes) and expose it via an authenticated Hermes endpoint (can be the same endpoint as Task 2 — one call returning `{ system_prompt, profile_context }` is ideal).
- The live-token route fetches this at mint time with a short server-side cache (e.g., 5 min) and falls back to the current hardcoded prompt if Hermes is unreachable (keep the current prompt in code as the fallback constant). Preserve all current voice-specific behavior directives (acknowledge before tool calls, concise spoken style, no markdown).

## Task 4: Tool-activity frames + dead code cleanup
- Hermes' SSE stream for text chat must emit `tool_call` (when a tool starts, with tool name) and `tool_result` (when it completes, success/failure) frames — the frontend `CoachChat` already listens for these and has a `ToolIndicator` UI that is currently dead. Match the frame shape the frontend expects (read the frontend handler first, adapt Hermes to it, not vice versa). Verify the indicator renders during a tool-using exchange.
- Verify the old Flask `/api/chat/*` coach endpoints (Flask backend in this repo) and the separate faster-whisper push-to-talk path are truly unreferenced by the current frontend (grep for callers, check routes/nav). If genuinely orphaned, remove them (git history is the backup); if anything still references them, do NOT remove — leave a `DEPRECATED` comment and note it in the final report instead.

## Constraints (hard rules)
- NEVER run pytest inside `/root/hermes-chess` (prod dir with live .env). Run Hermes tests from `/root/chess-app/hermes` only.
- Do NOT touch `/root/hermes-chess` at all — prod deploy is handled separately after review.
- Do NOT run `frontend/deploy.sh` or push to origin. Commit locally only.
- Never `git add -A` — stage specific files. Conventional commit messages, one commit per task is fine.
- Never expose API keys in code or commits.
- Write/update unit tests for each task: rate limiter on voice path, voice prompt builder, profile-context endpoint, SSE tool frames. All Hermes unit tests and frontend tests/build must pass (`npm run build` in frontend must succeed).

## Definition of done
- All 4 tasks implemented with passing tests and a successful frontend build.
- A summary file `VOICE_TEXT_PARITY_RESULTS.md` at repo root listing: files changed per task, test results (pass/fail counts), what was removed vs deprecated in Task 4, and anything intentionally left undone with reasons.
