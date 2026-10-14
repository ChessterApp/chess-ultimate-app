# Coach transcript sweep

The hermes-agent library writes every coach session to `$HERMES_HOME/sessions`
(prod: `/root/hermes-chess/profiles/chess-coach/sessions`):

- `session_<coach_session_id>.json` — full transcript
- `request_dump_<coach_session_id>_<YYYYMMDD>_<HHMMSS>_<micro>.json`

Nothing in the library deletes them. Two things do now:

- `DELETE /api/coach/sessions/{id}` removes that session's files after the
  session is deleted (UUID ids only, best effort).
- `scripts/sweep_transcripts.py` removes the files of every UUID session id
  that is no longer in `coach_sessions` — e.g. after `delete_user_data`
  wiped a deleted account's sessions.

## Running the sweep

From the Hermes directory (reads `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` from `.env`):

```bash
.venv/bin/python scripts/sweep_transcripts.py           # dry run: prints what it would delete
.venv/bin/python scripts/sweep_transcripts.py --apply   # delete
```

Options: `--dir` (default `$HERMES_HOME/sessions`, else the chess-coach
profile), `--grace-min` (default 60 — sessions with any file modified more
recently are skipped), `--max-fraction` (default 0.5), `--force`.

It prints a JSON summary (`scanned`, `orphans`, `orphan_ids`, `deleted_files`,
`bytes`, `skipped_non_uuid`, `skipped_recent`, `skipped_unparsed`, `error`) and
exits 1 on error. It fails closed:

- missing Supabase config or any failed lookup → nothing is deleted;
- orphans above `--max-fraction` of the session ids → abort (likely the wrong
  database) unless `--force`;
- non-UUID ids (`test-e2e-7`, `e2e-coaching-*`, `test-lichess-pgn`) are never touched.

The first run on prod will likely find a large backlog of orphans and abort
on the fraction guard — check the dry-run output, then rerun with `--force`.

## Suggested cron (not installed)

Daily at 04:30:

```cron
30 4 * * * cd /root/hermes-chess && HERMES_HOME=/root/hermes-chess/profiles/chess-coach .venv/bin/python scripts/sweep_transcripts.py --apply >> /root/hermes-chess/logs/transcript-sweep.log 2>&1
```
