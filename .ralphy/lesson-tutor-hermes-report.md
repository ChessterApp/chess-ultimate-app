# Lesson Tutor → Hermes Rewire — Report

Routed the Learning-section AI tutor chat through Hermes (mirroring the AI Coach
chat), replacing the broken Flask → OpenRouter one-shot path that hardcoded the
retired model `anthropic/claude-3.5-sonnet` (404 → error string persisted as the
tutor's reply).

## What changed (files)

### Hermes (source repo `/root/chess-app/hermes` — prod `/root/hermes-chess` untouched)
- `src/server.py`
  - `LessonChatRequest` Pydantic model (`message`, `lesson_title`, `lesson_content`, `history=[]`, `locale='ru'`); user id from `X-User-Id`.
  - `_build_lesson_system_prompt(...)` — friendly, encouraging tutor persona grounded in the lesson title + content, answers in the student's locale.
  - `_lesson_chat_stream(...)` — plain streaming chat via the OpenRouter client using the router-selected model (`_resolve_model`); **raises** on API error (no error text leaked as a delta). No board tools / tool loop.
  - `POST /api/lesson/chat` — streams `{"delta": ...}` frames then `{"done": true}`; on LLM failure emits a single `{"error": ...}` frame instead (same SSE shape the coach chat emits, so the Next.js proxy pattern is reused unchanged).
- `tests/unit/test_lesson_chat_route.py` — new (5 tests).

### Next.js frontend
- `src/app/api/learn/[courseSlug]/[lessonSlug]/chat/route.ts` — new SSE proxy, mirrors `api/coach/chat`. Clerk `auth()` (401 if none), reads `{message}`, fetches lesson title/content + history from Flask (forwarding the incoming `Authorization` header), forwards to Hermes `POST ${HERMES_URL}/api/lesson/chat` with `X-User-Id`, streams SSE back. After the stream it upserts the appended conversation to Supabase `lesson_chat_history` via the service-role client (`onConflict: user_id,lesson_id`). Never persists error text; a persistence failure is logged, not surfaced.
- `src/app/api/learn/[courseSlug]/[lessonSlug]/chat/__tests__/route.test.ts` — new (4 tests).
- `src/app/learn/[courseSlug]/[lessonSlug]/page.tsx` — `sendMessage` now POSTs to the relative `/api/learn/${courseSlug}/${lessonSlug}/chat` route and consumes the SSE stream, appending deltas to an optimistic empty assistant bubble (same client pattern as `CoachChat`). Optimistic user-message append + loading state preserved; on error both optimistic bubbles are reverted. GET history load is unchanged (still Flask).

### Flask backend (legacy path defused as a non-streaming fallback)
- `llm/openrouter_llm.py` — `generate()` now **raises** on API error / None content instead of returning `"Error: OpenRouter API issue - ..."` as content. (Streaming helpers already wrap this and keep their existing behavior; `llm_session_manager`/`app.py` callers already sit inside try/except, so they degrade correctly.)
- `api/lessons.py` — both hardcoded `anthropic/claude-3.5-sonnet` tutor call sites (`lesson_chat_by_slug` and the id-based `lesson_chat`) swapped to `anthropic/claude-sonnet-4.5`. The existing `except` branches return a friendly fallback ("I'm here to help with '<lesson>'…"), so an LLM failure now persists that fallback — never a raw error string.
- `scripts/clean_lesson_chat_errors.py` — new one-off cleanup (below).
- `tests/test_lesson_chat_defused.py` — new (5 tests).

## Test results

| Suite | Result |
|---|---|
| Hermes — `tests/unit/test_lesson_chat_route.py` | **5 passed** |
| Hermes — full `tests/unit` suite | **986 passed / 23 failed** — the 23 are pre-existing, environment-only (missing 42 GB TWIC SQLite DB → twic_search/get_pgn/test_setup; board-tool framework version drift). No new failures introduced. |
| Frontend — new proxy route test | **4 passed** |
| Frontend — `npx tsc --noEmit` | New/edited files (`route.ts`, `route.test.ts`, `page.tsx`) produce **0 errors**. The 73 project-wide errors are all pre-existing, in unrelated `__tests__` files (e.g. `GameViewerPanel-save.test.ts`, `org-metadata.test.ts`). |
| Frontend — `eslint` on touched files | **0 errors** (1 pre-existing `exhaustive-deps` warning on the untouched fetch `useEffect`). |
| Backend — `tests/test_lesson_chat_defused.py` | **5 passed** (generate raises on API error / None content, returns content on success; lesson chat persists the friendly fallback, never an error string). |

## Cleanup script output

`python scripts/clean_lesson_chat_errors.py` (run once against prod Supabase):

```
=== lesson_chat_history cleanup summary ===
mode:             cleaned
rows scanned:     23
rows modified:    14
messages removed: 18
```

Removed messages were all the persisted 404 error, e.g.
`Error: OpenRouter API issue - Error code: 404 - {'error': {'message': 'No endpoints found for anthropic/claude-3.5-sonnet.', ...`.
Re-running (`--dry-run`) afterward reports **0 rows modified / 0 messages removed** — confirming the table is clean.

## Left for deploy (done separately after review)
- Changes are committed **locally only** — not pushed, no `deploy.sh`, no PM2 restart (per constraints).
- **Hermes prod (`/root/hermes-chess`) must be restarted** to expose the new `POST /api/lesson/chat` endpoint (the source-repo change is not live until deployed).
- Frontend needs `HERMES_URL` (defaults to `http://localhost:8642`) and `SUPABASE_SERVICE_ROLE_KEY` present in the runtime env for the proxy's write-back (both already used by existing coach/admin routes).
- Deploy the frontend via the standard `deploy.sh` (git push → Vercel) after review.
