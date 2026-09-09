# Phase 0 — Feedback UX Results (log-only)

Implements `HERMES_CL_PHASE0_FEEDBACK_SPEC.md` (Tasks F1–F6): capture explicit
👍/👎 on AI Coach answers as a **LOG-ONLY** training signal. Feedback is never
read in the serving path and never alters prompts, routing, memory, or rewards
(sycophancy guard: raw thumbs are not a reward). Branch: `feat/hermes-cl-phase0`.

## What shipped

- **F1 — Migration (written, NOT applied).** `hermes/migrations/009_coach_feedback.sql`
  creates `coach_feedback` (uuid pk, `user_id`, `session_id`, `turn_id`, `rating`
  smallint `CHECK (rating IN (-1,1))`, `comment`, `surface` default `'text'`,
  `client_ts`, `created_at`, `updated_at`), a unique index on `(user_id, turn_id)`
  (the UPSERT conflict target), plus `(turn_id)` and `(user_id, created_at)`
  indexes. Additive + idempotent, style-matched to migrations 007/008.
- **F2 — Hermes endpoint.** `POST /api/coach/feedback` in `hermes/src/server.py`,
  backed by the best-effort helper `hermes/src/coach_feedback.py`.
  - Auth via `X-User-Id` (missing → 401), same as `/api/coach/chat`.
  - Validation → 400: missing/`>64`-char `turn_id`, `rating ∉ {1,-1,0}`, invalid
    `surface`, comment `>2000` chars pre-truncation, body `>8KB`.
  - `rating 1|-1` → Supabase UPSERT on `(user_id, turn_id)` via
    `Prefer: resolution=merge-duplicates` + `on_conflict=user_id,turn_id`; comment
    truncated to 500. `rating 0` → DELETE (retraction).
  - Always `log_event("feedback", …)` (spool + `coach_events` dual sink) with
    `{rating, surface, has_comment}` only — **no comment text** in the event.
  - Fail-open: Supabase down → still `200 {ok:true, persisted:false}` after
    spooling; the endpoint never 500s on a sink failure.
- **F3 — turn_id to the client.** The final SSE frame of `/api/coach/chat` now
  includes `turn_id` (additive). The Next.js proxy already forwards SSE frames
  verbatim (no change needed). `CoachChat.tsx` stores `turnId` on the assistant
  message when the `done` frame arrives; `CoachMessage.turnId?: string` added.
- **F4 — Next.js route.** `frontend/src/app/api/coach/feedback/route.ts`: POST
  only, Clerk `auth()` → 401, validates `turn_id` + `rating ∈ {1,-1,0}`, proxies
  to Hermes with `X-User-Id` and a 10s timeout; Hermes unreachable/non-ok → 502
  `{ok:false}` (client treats as silent failure).
- **F5 — UI.** `frontend/src/components/coach/FeedbackButtons.tsx` renders
  lucide `ThumbsUp`/`ThumbsDown` (14px, muted `text-gray-500`, hover-brighten)
  under each **completed** assistant message that has a `turnId` (never on user
  messages, never while streaming). Optimistic highlight; re-click retracts
  (rating 0), other thumb switches; network failure reverts silently (no toast).
  `aria-label` + `aria-pressed` on both; labels via the existing coach i18n
  (`feedbackGood` / `feedbackBad` added to en/ru/kz).

## File list

Added:
- `hermes/migrations/009_coach_feedback.sql`
- `hermes/src/coach_feedback.py`
- `hermes/tests/unit/test_coach_feedback.py`
- `frontend/src/app/api/coach/feedback/route.ts`
- `frontend/src/app/api/coach/__tests__/feedback-route.test.ts`
- `frontend/src/components/coach/FeedbackButtons.tsx`
- `frontend/src/components/coach/__tests__/FeedbackButtons.test.tsx`

Modified:
- `hermes/src/server.py` (import, `CoachFeedbackRequest`, `POST /api/coach/feedback`, `turn_id` on the final SSE frame)
- `frontend/src/components/coach/CoachChat.tsx` (store `turnId` on `done`; render `FeedbackButtons`)
- `frontend/src/types/coach.ts` (`CoachMessage.turnId?`)
- `frontend/messages/{en,ru,kz}.json` (`coach.feedbackGood` / `coach.feedbackBad`)

## Test counts

- **Hermes (pytest, offline):** new `test_coach_feedback.py` = **15 passed**
  (auth, validation, upsert body/args, retraction, comment truncation, fail-open;
  helper upsert/delete incl. merge-duplicates + eq filters + error paths).
  Full suite: **820 passed / 27 failed** — the 27 are the documented
  environment-only pre-existing failures (missing 42 GB TWIC SQLite DB +
  board-tool framework version drift: `test_tool_twic_search`, `test_tool_get_pgn`,
  `test_setup`, `test_board_control_tool`, `test_board_protocol`, integration).
  **Zero feedback-related failures**; `test_coach_routes.py` / `test_coach_chat_events.py`
  stay green (F3 SSE change is additive).
- **Frontend (vitest, offline):** new tests = **17 passed** — `FeedbackButtons`
  (6: render/aria, optimistic vote, retract, switch, silent revert, surface),
  `feedback-route` (7: 401, 400×2, proxy body + `X-User-Id`, rating 0, 502×2),
  `coach-i18n` (4, validates the new keys across en/ru/kz).
  `CoachChat.test.tsx` = 29 passed / 2 failed — both failures **pre-existing**
  (voice-transcript `client_ts` assertion, unrelated to this change; confirmed by
  running the untouched component).

Lint (`eslint`) clean on all touched frontend files; `tsc --noEmit` reports no
errors in touched files; `py_compile` clean on the new/modified Python.

## Operator step

Apply migration 009 to Supabase prod (NOT applied by this change):

```bash
# SUPABASE_DB_URL is in backend/.env; migrations live at the repo root.
psql "$SUPABASE_DB_URL" -f hermes/migrations/009_coach_feedback.sql
```

Until applied, the endpoint fail-opens: it returns `200 {persisted:false}` and
the feedback event is still spooled to `metrics/coach-events-*.jsonl` (and
`coach_events` once the row exists), so no client flow breaks. No deploy/push was
performed.
