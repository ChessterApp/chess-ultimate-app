# Fix: Master Games Not Loading on /debut and /position

## Problem

The `/api/openings/games/by-position` endpoint hangs for common positions because:

1. `game_positions` table stores every position from every game (~billions of rows)
2. Starting position alone has **3,345,153 matching rows** (every game starts there)
3. The probe query does `INNER JOIN game_positions gp JOIN games g ON g.id = gp.game_id WHERE gp.board_hash = ?` — this JOIN on 3.3M rows hangs
4. The backend was also in a crash loop (port conflict) — now fixed

The `move_stats` table (100M pre-computed aggregate rows) works instantly for candidate moves. But individual game listings still need the `game_positions` → `games` path.

## Fix Strategy: Query Timeout + ROWID-Based Fast Path

### Changes to `/root/chess-app/backend/api/openings.py`

**1. Add a query timeout (3 seconds)**
- Wrap the probe and ID-fetch queries with a 3-second SQLite timeout
- If timeout hits, return `{ games: [], total: -1, indexed: true, timeout: true }`
- Frontend shows "Too many games for this position" instead of infinite spinner

**2. Replace expensive probe with move_stats lookup**
- For total count estimation, query `move_stats` instead of `game_positions`
- `SELECT SUM(games) FROM move_stats WHERE board_hash = ?` — instant
- This gives us total games count without touching `game_positions`

**3. Use ROWID-based ID fetch with timeout**
- Replace the JOIN-based ID fetch with: `SELECT game_id FROM game_positions WHERE board_hash = ? ORDER BY game_id DESC LIMIT ?`
- No JOIN needed — just get game IDs from the indexed `board_hash` column
- Then fetch game details separately: `SELECT * FROM games WHERE id IN (...) ORDER BY ...`
- Add `PRAGMA busy_timeout = 3000` on connection

**4. For very common positions (>100K games), use direct games table scan**
- If `move_stats` shows >100K games for a position, skip `game_positions` entirely
- Sort by `COALESCE(white_elo, 0) + COALESCE(black_elo, 0) DESC LIMIT N` on the `games` table directly
- This gives "highest rated games overall" which is a reasonable default for starting-like positions

### Changes to frontend

**5. Handle timeout response in `useTwicGames.ts`**
- Add `timeout` field to `TwicGamesResponse`
- When `timeout: true`, show "Position has too many games. Use player search to narrow results." instead of error

**6. Handle timeout in `useOpeningRepertoire.ts`**
- Same timeout handling for the repertoire-mode game search

## Files Changed

1. `/root/chess-app/backend/api/openings.py` — Fix `games_by_position()` endpoint
2. `/root/chess-app/frontend/src/hooks/useTwicGames.ts` — Handle timeout response
3. `/root/chess-app/frontend/src/hooks/useOpeningRepertoire.ts` — Handle timeout response (if it renders master games)
4. `/root/chess-app/frontend/src/components/analysis/TwicExplorer.tsx` — Show timeout message in UI

## Expected Result

- Common positions (starting pos, 1.e4, 1.d4): instant response with top-rated games
- Rare positions: fast query via game_positions as before
- Player search: still works (already has fast path)
- No more infinite spinners or timeouts
