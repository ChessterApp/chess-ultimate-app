# Welcome drip via Resend + drop Listmonk (P4) — Ralph brief

Repo worktree: /var/tmp/drip-20261013 (branch feat/welcome-drip-resend off origin/main bdca494a).
Stack: Next.js frontend (frontend/, vitest), Flask backend (backend/, pytest, venv at /root/chess-app/backend/venv), Supabase Postgres.
Decision (Alex, 2026-10-13): Listmonk is dropped. All email goes through Resend. Build a real 5-email welcome sequence.

## HARD RULES
- Do NOT apply migrations to any database, do NOT push, do NOT deploy, do NOT restart services.
- Do NOT send any real email. All Resend HTTP calls must be mocked in tests.
- Never `git add -A`; add specific files. One or more conventional commits on this branch.
- Only mascot is the Chesster zebra with glasses. No parent consent anywhere. No fox.
- Disk is nearly full: do not run `next build`, do not install packages.

## 1. Migration `supabase/migrations/20261013_055_welcome_emails.sql`
- `welcome_emails`: id uuid pk, user_id text not null, email text not null, first_name text, locale text not null default 'en' (en|ru|kk), step smallint not null check 1..5, scheduled_for timestamptz not null, sent_at timestamptz, skipped_reason text, error text, resend_id text, created_at timestamptz default now(), unique(user_id, step). Index on (scheduled_for) where sent_at is null and skipped_reason is null.
- `email_opt_outs`: email text primary key (lower-cased), user_id text, created_at timestamptz default now().
- RLS enabled on both, no anon/authenticated policies (service role only).
- `CREATE OR REPLACE` the `delete_user_data` function from migration 053 so it also deletes from `welcome_emails` and `email_opt_outs` by user_id (copy 053's body exactly, add the two deletes). Keep the security/grant settings from 053.
- Add both tables/columns to `frontend/src/lib/user-data-manifest.ts` as "delete"; the manifest test must pass.

## 2. Scheduling (Clerk webhook, frontend/src/app/api/webhooks/clerk/route.ts)
- On `user.created`: replace the Listmonk sync with `scheduleWelcomeDrip(data)` in a new `frontend/src/lib/welcome-drip.ts`. It upserts 5 rows into `welcome_emails` via `supabaseAdmin` (on conflict user_id,step do nothing): step 1 = now, 2 = +1 day, 3 = +3 days, 4 = +5 days, 5 = +7 days. Best-effort: log and swallow errors, never fail the webhook.
- Skip scheduling when: no primary email; the signup came through a Chess Empire invite/branch token (`unsafe_metadata.inviteJwt` or the branch-token path already detected in route.ts) — those are school students.
- locale: take it from the user's data if available (unsafe_metadata/public_metadata locale, else 'en'); look for how the app stores UI locale and reuse it. Allowed values en|ru|kk, fallback en.
- `user.deleted`: remove the Listmonk blocklist call. The `delete_user_data` cascade covers the new tables.

## 3. Sending (Flask)
- `backend/services/welcome_drip.py` modelled on `services/lifecycle_emails.py` (same style, plain `{{var}}` substitution, no Jinja). Send via Resend `POST https://api.resend.com/emails` with `RESEND_API_KEY`. From: env `WELCOME_FROM`, default `Chesster <noreply@chesster.io>`.
- `send_due(now, limit)`:
  - If env `WELCOME_DRIP_ENABLED` is not exactly `1`, return `{'disabled': True}` and send nothing.
  - Fetch due rows (sent_at null, skipped_reason null, scheduled_for <= now).
  - Mark skipped instead of sending when: email is in `email_opt_outs` (`opted_out`); row is more than 48h overdue (`stale` — so enabling the flag never blasts a backlog); an earlier step for the same user is still unsent and not skipped (`out_of_order`, send nothing this run for that user).
  - On success store `sent_at` + `resend_id`; on failure store `error` and leave unsent (retry next run, max 3 tries then `skipped_reason='failed'` — add an `attempts` int column for this).
- Every email: `List-Unsubscribe: <https://api.chesster.io/api/email/unsubscribe?t=TOKEN>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers, plus a visible unsubscribe link in the footer. TOKEN = HMAC-SHA256 signed email (secret env `EMAIL_UNSUB_SECRET`; refuse to send if unset).
- Route `GET|POST /api/email/unsubscribe?t=TOKEN` (new blueprint, register in app.py, no auth): verify token, upsert into `email_opt_outs`, mark that email's remaining unsent rows `skipped_reason='opted_out'`. GET returns a small localized-neutral HTML "You're unsubscribed" page; POST returns 200. Bad token → 400.
- Flask CLI `backend/commands/welcome_emails_cli.py`, registered like lifecycle_emails_cli: `flask welcome-emails send-due [--limit]` and `flask welcome-emails send-test --to EMAIL --locale en|ru|kk [--step N]` (sends real rendered emails to one address, ignores the flag, writes nothing to the DB).
- Templates `backend/templates/emails/welcome/{en,ru,kk}/step{1..5}.html` + a shared `layout.html` (light background, readable on mobile, zebra logo from `https://chesster.io/static/images/chesster-logo-v3.png`, footer with unsubscribe link and "Chesster · chesster.io"). Subjects live in a dict in welcome_drip.py per locale/step.

## 4. Copy
Source drafts (from the old Listmonk campaigns) are in /root/clawd/files/5731393254/welcome-drip/listmonk-campaign-{2..6}.html — day 0 welcome, day 1 quick win, day 3 AI analysis + puzzles, day 5 streak, day 7 one week in.
- Port them, but: remove unsupported claims ("improve 3x faster", "measurable improvement within their first month"). Every feature named must exist in the app — grep the frontend routes and link each CTA to the real page (e.g. courses, puzzles, analysis, openings), not just the homepage. Drop anything that doesn't exist.
- Greeting uses first_name, fallback "Hi there" (and RU/KK equivalents).
- Write natural Russian and Kazakh versions (informal-friendly, short). The audience includes kids: keep it plain and positive, no pressure tactics.
- Save a plain-text preview of all 15 emails (subject + body text per locale/step) to `.ralphy/welcome-drip-copy.md` for Alex's review.

## 5. Drop Listmonk from the code
- Delete `frontend/src/lib/listmonk.ts` and `frontend/scripts/sync-clerk-to-listmonk.ts`; remove all imports/mocks/assertions referencing Listmonk in the webhook tests; remove LISTMONK_* from any committed .env.example / docs env lists. grep -ri listmonk must return nothing in frontend/src, frontend/scripts, backend (excluding venv).

## 6. Tests (must pass)
- pytest: welcome_drip (flag off sends nothing; opted_out/stale/out_of_order skips; success writes sent_at+resend_id; failure increments attempts and gives up after 3; headers include List-Unsubscribe; all 15 templates render with no leftover `{{`), unsubscribe route (good token, bad token, marks rows skipped), CLI send-test does not touch the DB.
- vitest: welcome-drip scheduling (5 rows at right offsets, skips invite signups and no-email users, swallows DB errors), updated webhook tests, user-data-manifest test.
- Run: `cd backend && /root/chess-app/backend/venv/bin/python -m pytest tests/test_welcome_drip.py tests/test_welcome_unsubscribe.py tests/test_lifecycle_emails.py -q` and `cd frontend && npx vitest run src/app/api/webhooks/clerk src/lib/__tests__/user-data-manifest.test.ts src/lib/__tests__/welcome-drip.test.ts`.

## 7. Report
Write `.ralphy/welcome-drip-report.md`: commits, files, test counts, the new env vars (WELCOME_DRIP_ENABLED, WELCOME_FROM, EMAIL_UNSUB_SECRET), the cron line to add (`*/15 * * * *` running `flask welcome-emails send-due` in backend with its env), and anything you dropped from the copy and why.
