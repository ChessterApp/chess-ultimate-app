# Plan: Lichess/Chess.com Games as Clickable Cards

## Problem
When Lichess games are imported, the model calls `board_control(load_pgn)` which loads the game directly on the inline board. But Alex wants the same UX as Master DB search — games appear as clickable cards in chat, and clicking opens in a separate replay tab.

## Root Cause
1. `lichess_game_import` returns a summary dict, not a `game_results` array
2. The `response_envelope.py` only detects `game_results` when tool output is a JSON array with `{id, white_name, black_name}` keys
3. Even if we add `game_results` to the return, `handleOpenGame` fetches PGN from `/api/openings/games/{id}/pgn` — this only works for TWIC integer IDs, not Lichess games
4. The prompt tells the model to chain `import → board_control(load_pgn)` — needs to stop doing that

## Fix — 3 files

### 1. `external_apis.py` — Return `game_results` array format

Both `lichess_game_import` and `chesscom_game_import` must return the tool result as a **JSON array** (not a dict with summary) matching the `game_results` detection format:

```python
[
  {
    "id": "lichess_AbCdEf12",      # Prefixed platform game ID
    "white_name": "Player1",
    "black_name": "Player2",
    "result": "1-0",
    "date": "2026.04.25",
    "eco": "B90",                   # Extract from PGN ECO header
    "opening": "Sicilian Najdorf",  # Extract from PGN Opening header
    "event": "Rated Blitz",
    "white_elo": 1800,              # Extract from WhiteElo header
    "black_elo": 1750,              # Extract from BlackElo header
    "pgn": "1. e4 c5 2. Nf3...",   # Full PGN — needed for tab opening
    "source": "lichess"             # Distinguish from TWIC
  }
]
```

Key changes:
- `_parse_pgn_stream()` — extract ECO, Opening, WhiteElo, BlackElo from PGN headers
- Return format: the handler returns `json.dumps(game_results_array)` — a JSON array, not a dict
- The `extract_game_results()` in response_envelope will auto-detect this array
- Keep the summary text in a separate key or let the model generate it from the array

**Actually simpler approach:** Keep the dict return but add a `game_results` key that's a properly formatted array. Then modify `extract_game_results()` to also check for `game_results` key inside dict tool results.

### 2. `response_envelope.py` — Detect `game_results` inside dict returns

Current `extract_game_results()` only finds top-level JSON arrays. Add detection for dicts that contain a `game_results` key:

```python
def extract_game_results(tool_results):
    for result in tool_results:
        # Existing: top-level array
        obj = json.loads(result)
        if isinstance(obj, list) and has_required_keys(obj[0]):
            return obj
        # NEW: dict with game_results key
        if isinstance(obj, dict) and "game_results" in obj:
            gr = obj["game_results"]
            if isinstance(gr, list) and gr and has_required_keys(gr[0]):
                return gr
```

### 3. `coach/page.tsx` — Handle non-TWIC game opening

Current `handleOpenGame` always fetches PGN from `/api/openings/games/{id}/pgn`. For Lichess/Chess.com games, the PGN is already in the `game_results` data (we include it). Need to:

- Extend `GameResult` type to include optional `pgn?: string` and `source?: string`
- In `handleOpenGame`: if `game.pgn` exists (Lichess/Chess.com source), parse it directly instead of fetching from API
- If `game.pgn` is missing (TWIC source), keep existing fetch behavior

```typescript
const handleOpenGame = useCallback(async (game: GameResult) => {
  // ... existing dedup/max check ...

  let pgn: string;
  if (game.pgn) {
    // Lichess/Chess.com — PGN already available
    pgn = game.pgn;
  } else {
    // TWIC — fetch from backend
    const res = await fetch(`/api/openings/games/${game.id}/pgn`, ...);
    pgn = (await res.json()).pgn;
  }

  const { moves, fens, startingFen } = parseGamePgn(pgn);
  // ... create tab ...
});
```

### 4. `prompt_builder.py` — Remove load_pgn chaining instruction

Remove the workflow instruction that tells the model to chain `import → board_control(load_pgn)`. The model should let the game_results render as cards, not load on board.

### 5. `types/coach.ts` — Extend GameResult

Add optional fields:
```typescript
export interface GameResult {
  id: number | string;  // string for Lichess IDs
  white_name: string;
  black_name: string;
  result: string;
  date: string;
  eco: string;
  opening: string;
  event: string;
  white_elo: number;
  black_elo: number;
  pgn?: string;         // NEW: full PGN for non-TWIC sources
  source?: string;       // NEW: 'twic' | 'lichess' | 'chesscom'
}
```

## Files Changed
1. `/root/chess-app/hermes/src/tools/external_apis.py` — return game_results array format
2. `/root/chess-app/hermes/src/middleware/response_envelope.py` — detect game_results in dicts
3. `/root/chess-app/frontend/src/app/coach/page.tsx` — handle inline PGN for non-TWIC games
4. `/root/chess-app/frontend/src/types/coach.ts` — extend GameResult type
5. `/root/chess-app/hermes/src/prompt_builder.py` — remove load_pgn chaining instruction

## Testing
1. "Find recent games by CheckmateComedian on Lichess" → should show game cards in chat
2. Click a game card → should open in separate replay tab
3. "Search for Kasparov games" (Master DB) → should still work as before
4. Verify no regressions in board_control for other use cases
