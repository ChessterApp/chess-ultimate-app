# Lesson Tutor → Hermes Rewire

## Goal
Route the Learning-section AI tutor chat through Hermes (FastAPI on :8642), mirroring the AI Coach chat architecture. Replace the broken legacy path where Flask calls OpenRouter directly with the retired model `anthropic/claude-3.5-sonnet` (returns 404, and the error string gets saved as the tutor's reply).

## Current architecture
- **Coach (healthy, the pattern to mirror):** browser → Next.js SSE proxy `frontend/src/app/api/coach/chat/route.ts` (Clerk auth, forwards `X-User-Id`, streams SSE) → Hermes `POST /api/coach/chat` (`hermes/src/server.py:850`).
- **Tutor (broken):** lesson page `frontend/src/app/learn/[courseSlug]/[lessonSlug]/page.tsx` (~line 162) POSTs directly to Flask `${NEXT_PUBLIC_API_URL}/api/learn/<courseSlug>/<lessonSlug>/chat` → `backend/api/lessons.py` (`lesson_chat_by_slug`, ~line 638) → `llm/openrouter_llm.py` one-shot call, model hardcoded `anthropic/claude-3.5-sonnet` (retired → 404). The wrapper (`openrouter_llm.py` ~line 64) returns the API error text as the reply content instead of raising, so error strings end up persisted in Supabase `lesson_chat_history` and shown to users.
- Chat history lives in Supabase table `lesson_chat_history` (`user_id`, `lesson_id`, `messages` jsonb array of `{role, content}`, upsert on_conflict `user_id,lesson_id`). Lesson content in table `lessons` (`title`, `content`).

## Tasks (in order)

### 1. Hermes: new endpoint `POST /api/lesson/chat`
In `hermes/src/server.py` (source repo — NOT /root/hermes-chess, that's prod, do not touch it):
- Pydantic request model: `message: str`, `lesson_title: str`, `lesson_content: str`, `history: list[{role, content}] = []`, `locale: str = 'ru'`. User id from `X-User-Id` header like coach chat.
- Build a tutor system prompt: friendly, encouraging chess tutor helping a student with this specific lesson (inject title + content); answer in the user's locale/language.
- Use the same LLM invocation path / model selection the coach chat uses (model_router / existing LLM client). Do NOT hardcode a retired model. No board tools / tool loop needed — plain streaming chat with history.
- Stream SSE with the same event shape the coach chat emits (`data: {"delta": ...}` chunks, final `data: {"done": true}`), so the Next.js proxy pattern works unchanged.
- On LLM failure: emit an SSE error event / non-200 — never emit error text as a normal delta.

### 2. Next.js: SSE proxy route
New file `frontend/src/app/api/learn/[courseSlug]/[lessonSlug]/chat/route.ts`, closely mirroring `frontend/src/app/api/coach/chat/route.ts`:
- POST only. Clerk `auth()`, 401 if no user. Read `{message}` from body.
- Fetch lesson content + title and existing chat history (server-side Supabase client if one exists in the frontend codebase — check `src/lib` for a service-role client; otherwise fetch from the Flask endpoints server-side, forwarding the incoming Authorization header).
- Forward to Hermes `POST ${HERMES_URL}/api/lesson/chat` (`HERMES_URL` env, default `http://localhost:8642`) with `X-User-Id`, stream SSE back to the browser.
- After the stream completes, persist the updated messages array (append user msg + full assistant reply) to `lesson_chat_history` with the same upsert shape, so the existing GET history endpoint keeps working. If persistence fails, log but don't kill the response.

### 3. Frontend lesson page
In `frontend/src/app/learn/[courseSlug]/[lessonSlug]/page.tsx`:
- Keep the GET history load as-is (Flask).
- Change the send-message POST to the new Next.js route (relative `/api/learn/${courseSlug}/${lessonSlug}/chat`) and consume the SSE stream, appending deltas to the assistant message as they arrive (same client pattern the coach chat UI uses — find and reuse it).
- Keep optimistic user-message append + loading state working.

### 4. Flask: defuse the legacy path
- `backend/llm/openrouter_llm.py`: on non-200 / API error, RAISE an exception instead of returning the error text as content.
- `backend/api/lessons.py` `lesson_chat_by_slug` POST: swap the hardcoded model to `anthropic/claude-sonnet-4.5` so it still works as a non-streaming fallback, and ensure LLM failures return the friendly fallback message (existing except-branch) — never a raw error string, and never persist error text.

### 5. Data cleanup script
`backend/scripts/clean_lesson_chat_errors.py`: connect to Supabase (creds from backend `.env`), scan `lesson_chat_history`, remove assistant messages whose content starts with/contains `Error: OpenRouter API issue` (and the generic 404 error string), write the cleaned arrays back. Print a summary (rows scanned / messages removed). RUN it once and include the output in the report.

### 6. Tests — must pass
- Hermes: unit test for `/api/lesson/chat` (mock the LLM; assert SSE deltas + done, error path not leaking error text as delta) in the hermes source tests dir; run the hermes source test suite. NEVER run pytest in `/root/hermes-chess` (prod, live .env).
- Frontend: route test for the new proxy mirroring `src/app/api/coach/sessions/[id]/messages/__tests__/route.test.ts` style; run the frontend test suite (or at minimum the tests for touched areas) + `npx tsc --noEmit` if that's the repo norm.
- Backend: test that `openrouter_llm` raises on API error, and lesson chat POST persists no error strings.

## Constraints
- NEVER `git add -A` — add specific files. Commit locally with conventional messages. Do NOT push, do NOT run deploy.sh, do NOT touch `/root/hermes-chess` or restart any PM2 process — deploy happens separately after review.
- Never modify `backend/data/twic/`.
- No API keys in code or commits.
- Write a final report to `.ralphy/lesson-tutor-hermes-report.md`: what changed (files), test results (pass/fail counts), cleanup script output, and anything left for deploy.
