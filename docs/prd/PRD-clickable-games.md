# PRD: Clickable Game Results in Coach Chat

## Goal
When the AI coach returns game search results from the TWIC database, render them as clickable rows in the chat. Clicking a game opens it on the `/database` page in a new browser tab, where it loads into the existing tab-based game viewer.

## Current State
- `search_master_games` tool returns JSON array of game objects (id, white_name, black_name, result, date, eco, opening, event, white_elo, black_elo)
- The tool result is passed to the AI model which formats it as markdown text in the chat
- The `/database` page has a multi-tab game viewer with `handleOpenGame()` that fetches PGN and shows games
- `fetchGamePgn(gameId)` already exists in `useOpeningRepertoire` hook — calls `/games/<id>/pgn` on the Flask backend

## Architecture

### 1. Hermes Backend — Extract game_results from tool output

**File:** `hermes/src/middleware/response_envelope.py`

The `_on_tool_complete` callback in `server.py` already captures tool results as strings. The `wrap_response()` function processes them for board actions.

**Changes to `response_envelope.py`:**
- Add a new function `extract_game_results(tool_results)` that:
  - Iterates over `tool_results` list
  - For each result string, tries `json.loads(result)`
  - If it parses to a list of dicts where each dict has `id`, `white_name`, `black_name` keys → it's a game search result
  - Returns the list of game dicts (or empty list)
- Modify `wrap_response()` to also call `extract_game_results()` and include `game_results` in the returned dict

**File:** `hermes/src/server.py`

**Changes to `coach_chat()` endpoint (line ~385):**
- Include `game_results` from envelope in the response JSON:
```python
return {
    "message": envelope["message"],
    "board_actions": envelope.get("board_actions", []),
    "game_results": envelope.get("game_results", []),
    "session_id": session.id,
}
```

### 2. Frontend API Route — Forward game_results SSE event

**File:** `frontend/src/app/api/coach/chat/route.ts`

**Changes (line ~103-112, the JSON response handler):**
- After sending `board_actions`, also send `game_results`:
```typescript
if (data.game_results && data.game_results.length > 0) {
  sendEvent({ game_results: data.game_results });
}
```

### 3. TypeScript Types — Add GameResult interface

**File:** `frontend/src/types/coach.ts`

Add after the BoardAction types:
```typescript
export interface GameResult {
  id: number;
  white_name: string;
  black_name: string;
  result: string;
  date: string;
  eco: string;
  opening: string;
  event: string;
  white_elo: number;
  black_elo: number;
}
```

Add to CoachMessage interface:
```typescript
export interface CoachMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  fen?: string;
  timestamp: Date;
  boardActions?: BoardAction[];
  gameResults?: GameResult[];  // <-- NEW
}
```

### 4. CoachChat Component — Render clickable game table + handle SSE

**File:** `frontend/src/components/coach/CoachChat.tsx`

**SSE handling changes (around line 115-124):**
Add a new handler for `data.game_results`:
```typescript
if (data.game_results) {
  setMessages((prev) =>
    prev.map((m) =>
      m.id === assistantId
        ? { ...m, gameResults: data.game_results }
        : m
    )
  );
}
```

**Rendering changes (around line 230-237):**
After the boardActions indicator, render the game results table:
```tsx
{msg.gameResults && msg.gameResults.length > 0 && (
  <div className="mt-3 rounded-lg overflow-hidden border border-white/10">
    <table className="w-full text-xs">
      <thead>
        <tr className="bg-white/5 text-gray-400">
          <th className="px-2 py-1.5 text-left">Date</th>
          <th className="px-2 py-1.5 text-left">White</th>
          <th className="px-2 py-1.5 text-left">Black</th>
          <th className="px-2 py-1.5 text-center">Result</th>
          <th className="px-2 py-1.5 text-left">ECO</th>
        </tr>
      </thead>
      <tbody>
        {msg.gameResults.map((game) => (
          <tr
            key={game.id}
            onClick={() => window.open(`/database?game=${game.id}&source=twic`, '_blank')}
            className="hover:bg-white/10 cursor-pointer transition-colors border-t border-white/5"
          >
            <td className="px-2 py-1.5 text-gray-400">{game.date}</td>
            <td className="px-2 py-1.5 text-gray-200">
              {game.white_name} <span className="text-gray-500">{game.white_elo}</span>
            </td>
            <td className="px-2 py-1.5 text-gray-200">
              {game.black_name} <span className="text-gray-500">{game.black_elo}</span>
            </td>
            <td className="px-2 py-1.5 text-center">
              <span className={
                game.result === '1-0' ? 'text-green-400' :
                game.result === '0-1' ? 'text-red-400' :
                'text-gray-400'
              }>{game.result}</span>
            </td>
            <td className="px-2 py-1.5 text-gray-400">{game.eco}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)}
```

### 5. Database Page — Handle ?game= URL parameter

**File:** `frontend/src/app/database/page.tsx`

Add URL param handling at the top of the component:
- Import `useSearchParams` from `next/navigation`
- On mount, check for `?game=<id>&source=twic` params
- If present, fetch the PGN via the existing `fetchGamePgn()` and call `handleOpenGame()` to open it in a tab
- This should happen in a `useEffect` that runs once on mount

The effect should:
1. Read `searchParams.get('game')` and `searchParams.get('source')`
2. If `game` exists and source is `twic`:
   - Fetch game metadata from `/games/<id>/pgn` (the existing backend endpoint)
   - Call `handleOpenGame()` with the game object
3. Clean up the URL params after loading (optional, nice-to-have)

### 6. Sync hermes copy in chess-app

After all changes, copy the modified hermes files from `/root/hermes-chess/` to `/root/chess-app/hermes/` (or vice versa — check which is the source of truth). Restart PM2 `hermes-chess`.

### 7. Commit and push

Stage specific files, commit with clear message, push.

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `hermes/src/middleware/response_envelope.py` | Modify | Extract game_results from tool output |
| `hermes/src/server.py` | Modify | Include game_results in response |
| `frontend/src/app/api/coach/chat/route.ts` | Modify | Forward game_results SSE event |
| `frontend/src/types/coach.ts` | Modify | Add GameResult type + gameResults field |
| `frontend/src/components/coach/CoachChat.tsx` | Modify | Render clickable game table + handle SSE |
| `frontend/src/app/database/page.tsx` | Modify | Handle ?game= URL param on load |

## Testing
1. Ask coach "Find Sindarov's games from the Candidates" → should see clickable table in chat
2. Click a game row → new tab opens at `/database?game=123&source=twic`
3. Database page loads → game appears in tab viewer with PGN
4. Verify existing database page functionality still works (no regressions)
