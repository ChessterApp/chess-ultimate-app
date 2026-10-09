# Database Management — Phase 2 Report

Task tag: `db-mgmt-p2-20261009` · Branch: `feat/db-management` (continued, not re-branched).

## Summary
Wired `database_id` through the `user_games` backend and built the **Variation B
pill-row UI** in the Database page header (Master + user databases, inline rename,
+ New). Selecting a user database scopes the My Games list to that `database_id`.
Delete/restore + cleanup cron remain Phase 3 (not built).

## Files changed
**Backend**
- `backend/api/user_games.py`
  - Added `DATABASES_TABLE` + helpers `_fetch_owned_database(user_id, id)` and
    `_default_database_id(user_id)` (both re-check id/user_id/deleted_at in Python
    so they're correct under the filter-agnostic Supabase mock).
  - **List** `GET /api/games`: optional `?database_id=` → `query.eq('database_id', …)`.
    The query is already user-scoped, so an unowned id simply returns no rows.
    Absent → unchanged (all games) = back-compat.
  - **Create** `POST /api/games`: optional `database_id` in body. Explicit id must
    be owned (else **404**); omitted → falls back to the caller's **default** db id.
    If no default resolves, the game is created unstamped (back-compat, never 500s).
  - **Import** `POST /api/games/import-local`: stamps the caller's default db on
    every imported row (resolved once) so bulk imports aren't orphaned.
- `backend/tests/test_user_games_api.py`
  - Added `_make_multi_table` (per-table seed) + `DEFAULT_DB_ROW`/`OTHER_DB_ROW`.
  - New classes: `TestListGamesDatabaseScope` (with/without `database_id`) and
    `TestCreateGameDatabaseStamp` (default stamp, explicit owned stamp, unowned→404,
    no-default-still-succeeds).

**Frontend**
- `frontend/next.config.ts` — added `/api/databases` + `/api/databases/:path*`
  rewrites (the Phase 1 blueprint had no rewrite, so the relative-path hook calls
  would 404 without this).
- `frontend/src/hooks/useDatabases.ts` *(new)* — mirrors `useUserGames` legacy
  conventions (Clerk bearer token, shared `apiFetch`, optimistic list mutations
  with rollback). Exposes `databases`, `loading`, `error`, `refresh()`,
  `createDatabase(name)`, `renameDatabase(id, name)`. 409 duplicate → friendly
  inline `error` string (never throws). State mirrored into a ref so the optimistic
  rename can read the prior name synchronously for rollback. Delete/restore omitted
  (Phase 3).
- `frontend/src/hooks/__tests__/useDatabases.test.ts` *(new)* — 7 tests: load,
  optimistic create, 409 inline error, empty-name guard, optimistic rename +
  rollback-on-409.
- `frontend/src/components/openings/DatabasePillRow.tsx` *(new)* — the Variation B
  row (see Hallmark note below).
- `frontend/src/components/openings/MyGamesPanel.tsx` — new optional `databaseId`
  prop: added to `buildFilters` (scopes the list) and merged into `createGame`
  metadata (new games land in the active db).
- `frontend/src/hooks/useUserGames.ts` — `database_id?` added to `UserGame` +
  `rowToUserGame`; `database_id?` added to `ListGamesFilters`; legacy `fetchGames`
  sets the `database_id` query param.
- `frontend/src/app/database/page.tsx` — replaced the static "Master Database"
  badge (old L1845–1867) with `<DatabasePillRow>`; added `selectedDatabaseId`
  state; passes `databaseId` to `MyGamesPanel`. Reserved-height container switched
  from fixed `height` to `minHeight` so the row can wrap on mobile without
  reintroducing the board-shift bug the fixed height guarded against.

## How selection / scoping is wired
`DatabasePillRow` owns `useDatabases` and calls back `onSelect(databaseId | null)`.
`page.tsx` stores it in `selectedDatabaseId`:
- `null` (Master) → `activeTab = 'debut'` (the default/master view, unchanged).
- a user db id → `activeTab = 'my-games'` and the id flows to `MyGamesPanel.databaseId`.

`MyGamesPanel.buildFilters()` adds `database_id` when the prop is set, so the
existing legacy `fetchGames` sends `?database_id=…`; changing the prop re-triggers
the panel's debounced fetch (page 1). New games added while a db is active are
POSTed with that `database_id`.

## The "My Games" fold decision
I took the brief's lower-risk fallback: the existing **My Games** tab/chip is left
in place (reachable as before) and the pill row is **additive**. The default user
database pill ("My Games") and the legacy chip both land on the scoped list; they
are not merged, to avoid destabilising the heavily-entangled `activeTab` machinery
in this ~2,400-line file. Selecting the default db pill scopes to it; the legacy
chip (no selection) shows all games (back-compat).

## Hallmark (design) note
Component-scope run — macrostructure skipped. The pill row reuses the page's exact
existing tab-chip tokens (`borderRadius '9999px'`, `rgba(255,255,255,0.95)` bg,
`1px solid rgba(31,41,55,0.1)` border, active `primary.main`/`#fff`, hover
`var(--surface-card-hover)`); no new colors introduced, so no `tokens.css` (this
codebase styles via MUI `sx`, not a CSS token file). States shipped: default ·
hover · `:focus-visible` · active · editing (inline input) · error (inline 409).
Keyboard: pills are buttons / `role=button` + `tabIndex`; inputs handle
Enter (save) / Escape (cancel); row is `flex-wrap`.

## Verify — results
- Backend: `venv/bin/python -m pytest tests/test_user_games_api.py
  tests/test_user_databases_api.py tests/test_collection_share.py -q` →
  **99 passed**.
- Frontend build: `NODE_OPTIONS=--max-old-space-size=2048 npm run build` →
  **success (exit 0)**, type-check clean.
- Frontend tests: `useDatabases` (7), `useUserGames` + `MyGamesPanel` +
  `open-saved-game-tab` (89 total), `useUserGames-pgn-import-flow` /
  `-powersync` / `EditGameModal` (32) → all pass. ESLint on changed files: 0 errors.

## Deferred / out of scope (Phase 3)
- Delete confirmation modal, Recently-deleted/Restore panel, 30-day hard-delete cron.
- `useDatabases` deliberately omits delete/restore actions.
- **PowerSync path**: `database_id` list scoping is applied only on the legacy
  fetch path (the default; `NEXT_PUBLIC_LOCAL_FIRST_GAMES` is off). The PowerSync
  local-query path (`SELECT * FROM user_games WHERE user_id = ?`) does not yet
  filter by `database_id` — noted for a follow-up if the flag is enabled.
- Deploy/push handled by the main session (not pushed here).
