# Welcome drip via Resend + drop Listmonk (P4) — report

Branch `feat/welcome-drip-resend` (off `bdca494a`). Not pushed, not deployed, migration not applied, no email sent.

## Commits
- `21874459` feat(db): welcome_emails + email_opt_outs tables for the Resend welcome drip
- `b9652c44` feat(welcome-drip): schedule the welcome drip on user.created, drop Listmonk
- `59389c01` feat(backend): send the welcome drip via Resend with one-click unsubscribe
- (this report + copy preview + brief: docs commit on top)

## Files
**DB**
- `supabase/migrations/20261013_055_welcome_emails.sql`: `welcome_emails` (includes the brief's columns plus `attempts int not null default 0`, `unique(user_id, step)`, a partial due index, and an email index), `email_opt_outs` (email PK, `CHECK email = lower(email)`). RLS is on for both with no policies. `delete_user_data` is copied from 053 with two deletes added. REVOKE/GRANT and SECURITY DEFINER are unchanged.
- `frontend/src/lib/user-data-manifest.ts`: adds `welcome_emails.user_id` and `email_opt_outs.user_id` as DELETE.
- `frontend/src/lib/__tests__/user-data-manifest.test.ts`: `DELETE_MIGRATION` now points to 055, the latest definition of `delete_user_data`. Otherwise the new entries can't pass.

**Frontend**
- `frontend/src/lib/welcome-drip.ts` (new): `scheduleWelcomeDrip(data)` and `welcomeLocale(data)`.
- `frontend/src/app/api/webhooks/clerk/route.ts`: `user.created` → `scheduleWelcomeDrip`. The Listmonk sync and the `user.deleted` blocklist call are gone.
- `frontend/src/app/sign-up/[[...sign-up]]/page.tsx`: sends `preferred_locale: <UI locale>` in `unsafeMetadata` at sign-up. Without it the webhook would almost never have a locale, because the language switcher only writes `preferred_locale` for users who are already signed in.
- Deleted `frontend/src/lib/listmonk.ts` and `frontend/scripts/sync-clerk-to-listmonk.ts`. Updated the three webhook test files.

**Backend**
- `backend/services/welcome_drip.py` (new): subjects/greetings/footer dicts, HMAC tokens, rendering, `send_email`, `send_due`, `unsubscribe`.
- `backend/routes/email_unsubscribe.py` (new): `GET|POST /api/email/unsubscribe?t=TOKEN`. Registered in `app.py`.
- `backend/commands/welcome_emails_cli.py` (new): `flask welcome-emails send-due [--limit]` and `send-test --to --locale [--step] [--first-name]`. Registered in `app.py`.
- `backend/templates/emails/welcome/layout.html` + `{en,ru,kk}/step{1..5}.html`.
- `backend/tests/test_welcome_drip.py`, `backend/tests/test_welcome_unsubscribe.py`.

## Tests
- `pytest tests/test_welcome_drip.py tests/test_welcome_unsubscribe.py tests/test_lifecycle_emails.py -q` → **63 passed**
- `npx vitest run src/app/api/webhooks/clerk src/lib/__tests__/user-data-manifest.test.ts src/lib/__tests__/welcome-drip.test.ts` → **5 files, 46 passed**
- `tsc --noEmit` on the frontend: clean. ESLint on the changed files: 0 errors. There is 1 warning in sign-up/page.tsx, on line 564, which I did not touch.
- `grep -ri listmonk frontend/src frontend/scripts backend` (excluding venv) → nothing.
- No Python linter is installed in the venv, so the Python files were only checked with `py_compile`.

## Env vars (backend, used by the cron)
- `WELCOME_DRIP_ENABLED`: must be exactly `1` to send. Leave it off until migration 055 is applied and the copy is approved.
- `WELCOME_FROM`: optional. Default is `Chesster <noreply@chesster.io>`.
- `EMAIL_UNSUB_SECRET`: required. Without it `send_due` refuses to send and the unsubscribe route rejects every token. **Rotating it invalidates the unsubscribe links in emails already sent.**
- `RESEND_API_KEY`: already used by other email code. `send_due` also refuses to send if it's missing, so retries don't use up attempts.

## Cron
```
# Chesster welcome drip (Resend) — every 15 min
*/15 * * * * /bin/bash -c 'cd /root/chess-app/backend && set -a && . ./.env && set +a && FLASK_APP=app.py /root/chess-app/backend/venv/bin/flask welcome-emails send-due' >> /var/log/welcome-drip.log 2>&1
```
Deploy order: apply 055 → deploy the backend (route + CLI) → deploy the frontend (the webhook starts writing rows) → set the env vars → test with `flask welcome-emails send-test --to <you> --locale ru` → set `WELCOME_DRIP_ENABLED=1` → add the cron.
`https://api.chesster.io/health` returns 200 from Flask, so the unsubscribe URL will resolve once the backend is deployed. Today it returns 404.

## Behaviour notes / decisions
- **`out_of_order` defers instead of skipping permanently.** If an earlier step for the same user is still unsent and not skipped, nothing is sent to that user in this run. The row is left untouched and gets picked up next run. It's counted as `out_of_order` in the run summary. If it were written as `skipped_reason`, one transient Resend failure on step 1 would also cancel step 2 for good whenever both were due in the same run. The brief says "send nothing this run for that user", which reads as a deferral.
- A failed send also holds back that user's later steps for the rest of the run.
- Emails are stored lower-cased (scheduler + opt-outs), so opt-out checks and unsubscribe updates use plain equality.
- Locale: the app's Kazakh code is `kz`. The welcome drip maps it to `kk`. The sources it reads are `unsafe_metadata.preferred_locale` / `locale`, then `public_metadata.preferred_locale` / `locale`, otherwise `en`.
- School students: any `unsafe_metadata.inviteJwt` skips scheduling. Online invites and branch tokens both arrive as an `inviteJwt`. If Google OAuth drops `unsafeMetadata`, a school student can still be scheduled, because the webhook can't tell them apart from anyone else.
- `email_opt_outs.user_id` is filled from that address's `welcome_emails` row, if there is one. Deleting the account therefore deletes the opt-out too, as the brief asked. If the same address signs up again later, it will get the drip again.
- Unsubscribe page: a single page with the message in EN, RU and KK.

## Copy: what was dropped or changed, and why
Full preview of all 15 emails: `.ralphy/welcome-drip-copy.md`. All CTAs link to real pages: `/learn`, `/puzzle`, `/game`, `/dashboard`, `/database`, `/games/puzzlerush`.
- **"Players who practice daily improve 3x faster…"** (day 5 tip): removed as an unsupported claim. Replaced with a practical tip: "Before every move, ask yourself: what is my opponent planning?"
- **"…see measurable improvement within their first month"** (day 7): removed as an unsupported claim.
- **"AI-powered chess coach"** (day 0): removed. `/coach` is behind a subscription or trial, so it isn't promised to free users anywhere.
- **"Chess Fundamentals course"** (day 1): the name is no longer used. That title only exists in `backend/schema.sql` seed data and its slug can't be confirmed in prod. The email now says "the first course" and links to `/learn`. The first course is always unlocked for regular users.
- **"Puzzle trainer serves you challenges matched to your level"** (day 3): there is no per-user puzzle rating. Difficulty is a slider the user sets. The email now says "you pick the difficulty".
- **"Solve one puzzle today to start your streak… earn XP… watch your rating climb"** (day 5): for regular users the daily streak and XP only come from **lesson** completions, and there is no user rating to climb. The email now says "finish one lesson today to start your streak", and "every lesson earns XP" with a link to `/dashboard`. The dashboard's "+5/+15 XP for puzzles" tiles don't actually award XP, so puzzles aren't promised XP.
- **"paste any chess game into Chesster"** (day 3): kept. The CTA goes to `/game`, which has PGN paste/upload, engine review of every move, and AI explanations. `/analyze` only redirects to `/position`, so it isn't used.
- **"openings explorer"** (day 7): kept. It links to `/database` (the Opening Explorer). Added Puzzle Rush (`/games/puzzlerush`), which is free and on the games hub.
- Removed "lunch break, commute" because the audience includes kids. All five emails are short and positive with no pressure. The only mascot is the zebra logo. There is no parent consent and no fox.
- Feature names follow the app's own i18n terms: RU "Обзор партий", "Обзор дебютов", "Задачи"; KK "Ойын шолуы", "Дебют шолушы", "Жұмбақтар". Russian is informal "ты" with gender-neutral wording. **The RU and KK copy has not been reviewed by a native speaker. Alex should check it, especially the Kazakh, before enabling.**
