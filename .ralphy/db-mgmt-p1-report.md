# Report — Database Management, Phase 1 (BACKEND + MIGRATION ONLY)

Task tag: `db-mgmt-p1-20261009`
Branch: `feat/db-management` (off `main`). Not pushed, not deployed (main session handles that).

## Scope delivered
Data model + backend CRUD for user-owned game "databases" (collections) with
soft-delete + restore. No frontend touched. `user_games.py` list/create filtering,
the 30-day cleanup cron, and collection-share behavior are untouched (future phases).

## Files changed / added
- **Added** `backend/migrations/018_create_user_databases.sql` — `user_databases`
  table + `database_id` FK on `user_games` + idempotent backfill.
- **Added** `backend/api/user_databases.py` — `user_databases_bp` blueprint
  (`DATABASES_TABLE = 'user_databases'`), mirroring `user_games.py` style.
- **Added** `backend/tests/test_user_databases_api.py` — 33 tests (API + migration shape).
- **Modified** `backend/app.py` — registered `user_databases_bp` immediately after
  `user_games_bp` (same try/except + logger pattern).

## Endpoints (all `@verify_clerk_token`, scoped to caller's `user_id`)
| Method | Path | Behavior |
|---|---|---|
| GET | `/api/databases` | List caller's LIVE dbs, each with live `game_count`; ordered default-first then `created_at` asc; `[]` if none. |
| POST | `/api/databases` | Create a NON-default db. Trims name; 400 on empty / >80 chars; 409 on case-insensitive live duplicate. Returns row with `game_count: 0` (201). |
| PUT | `/api/databases/<id>` | Rename (default included). Same validation + 409 duplicate; 404 if not owned/missing/deleted. Touches `updated_at`. |
| DELETE | `/api/databases/<id>` | Soft-delete (`deleted_at = now()`). 404 if not owned/missing. **400 if `is_default`** ("Can't delete your default database."). Games keep their `database_id`. |
| POST | `/api/databases/<id>/restore` | Clear `deleted_at`. 404 if not owned/missing. 409 if a live db of the same (case-insensitive) name exists. |

No "Master Database" row is ever created or returned — it's a built-in TWIC frontend concept.

## Migration — before/after counts
Applied directly to prod Supabase via `psql "$SUPABASE_DB_URL" -f migrations/018_create_user_databases.sql`.

- **Before:** `user_games` = 29 rows, 13 distinct `user_id`.
- **After first apply:** `INSERT 0 13` (one default "My Games" db per existing user),
  `UPDATE 29` (every live game stamped with its default `database_id`).
- **Assertions (all pass):**
  - Users with ≠1 live default db: **0**
  - Live `user_games` rows with NULL `database_id`: **0**
  - `user_databases`: 13 total / 13 default.
- **Idempotency (re-run):** `INSERT 0 0`, `UPDATE 0` (only "already exists, skipping"
  NOTICEs for the column/index) → proven no-op.

## Tests
- New: `python -m pytest tests/test_user_databases_api.py -q` → **33 passed**.
  Covers: list empty / with game_count / auth-required; create ok / trim / duplicate 409 /
  empty 400 / missing 400 / too-long 400; rename ok / default-allowed / duplicate 409 /
  same-name-ok / missing 404 / empty 400; delete non-default ok / default 400 / missing 404;
  restore ok / name-collision 409 / missing 404; cross-user isolation (see/rename/delete);
  migration shape (8 checks).
- Regression: `python -m pytest tests/test_user_games_api.py tests/test_collection_share.py -q`
  → **60 passed** (My Games + collection share intact).

## Notes / surprises
- No linter (ruff/flake8/pyflakes) is installed in the backend venv; files
  `py_compile`-clean and import-clean.
- The test Supabase mock is filter-agnostic (eq/is_/ilike are no-ops), so the
  endpoint re-checks `id`/`user_id`/`name`/`deleted_at` in Python. This is defensive
  (DB filters still apply in prod) and makes the mocked ownership/duplicate/soft-delete
  tests meaningful.
- Duplicate detection uses a `.ilike('name', name)` query plus a Python
  `lower().strip()` comparison; the DB-level partial unique index
  `idx_user_databases_user_name_live` is the backstop.
- Deferred per brief: frontend (Phase 2), `user_games` filtering by `database_id`
  (Phase 2), 30-day hard-delete cron (Phase 3).
