# PRD: Coach Page In-Page Game Tabs

## Problem
Clicking a game result in the coach chat opens `/database?game=<id>&source=twic` in a new browser tab, navigating the user away from the coach page. The user wants games to open as tabs within the coach page itself (same pattern as the database page's internal tab system).

## Solution
Add an internal tab system to the coach page's board panel. When a game is clicked in the chat, it opens as a new tab above the board. The user can switch between tabs and the default "Coach Board" view.

## Implementation

### File 1: `frontend/src/types/coach.ts`
Add a new interface for opened coach games:

```typescript
export interface OpenedCoachGame {
  id: string;
  white: string;
  black: string;
  whiteElo?: number;
  blackElo?: number;
  result: string;
  eco?: string;
  date?: string;
  event?: string;
  pgn: string;
  moves: string[];    // SAN moves parsed from PGN
  fens: string[];     // FEN at each move index
  startingFen: string;
  source?: string;
}
```

### File 2: `frontend/src/components/coach/CoachChat.tsx`
**Change:** Replace `window.open(...)` with a callback prop.

1. Add `onOpenGame?: (game: GameResult) => void` to `CoachChatProps`
2. In the game results table `<tr onClick>`, replace:
   ```typescript
   onClick={() => window.open(`/database?game=${game.id}&source=twic`, '_blank')}
   ```
   with:
   ```typescript
   onClick={() => onOpenGame?.(game)}
   ```
3. Add `onOpenGame` to the destructured props

### File 3: `frontend/src/app/coach/page.tsx`
**Change:** Add tab state management and render GameViewerPanel when a game tab is active.

1. Add imports:
   - `import GameViewerPanel from '@/components/openings/GameViewerPanel';`
   - `import type { OpenedGame } from '@/components/openings/GameViewerPanel';`
   - `import type { GameResult } from '@/types/coach';`
   - `import { Chess } from 'chess.js';`

2. Add state:
   ```typescript
   const [openedGames, setOpenedGames] = useState<OpenedGame[]>([]);
   const [activeGameId, setActiveGameId] = useState<string | null>(null);
   const [gameLoadingId, setGameLoadingId] = useState<number | null>(null);
   const [gameMoveIndices, setGameMoveIndices] = useState<Record<string, number>>({});
   ```

3. Add `handleOpenGame` callback:
   - Takes a `GameResult` from the chat
   - If game already open, just switch to that tab (`setActiveGameId`)
   - Otherwise, fetch PGN from `/api/games/${game.id}/pgn`
   - Parse PGN with `chess.js` to get moves[] and fens[]
   - Create an `OpenedGame` object and add to `openedGames` state
   - Set `activeGameId` to the new game's id
   - Show loading state while fetching

4. Add `handleCloseGame` callback:
   - Remove game from `openedGames`
   - If it was the active tab, switch back to the coach board (set `activeGameId` to null)

5. Add tab bar above the board (inside the board panel div):
   ```tsx
   {openedGames.length > 0 && (
     <div className="flex items-center gap-1 px-2 py-1 border-b border-white/10 overflow-x-auto">
       <button
         onClick={() => setActiveGameId(null)}
         className={`px-3 py-1 text-xs rounded-t ${!activeGameId ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'}`}
       >
         Coach Board
       </button>
       {openedGames.map((game) => (
         <div key={game.id} className="flex items-center">
           <button
             onClick={() => setActiveGameId(game.id)}
             className={`px-3 py-1 text-xs rounded-t truncate max-w-[200px] ${
               activeGameId === game.id ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'
             }`}
           >
             {game.white} vs {game.black}
           </button>
           <button
             onClick={() => handleCloseGame(game.id)}
             className="text-gray-500 hover:text-white ml-1 text-xs"
           >
             ×
           </button>
         </div>
       ))}
     </div>
   )}
   ```

6. Conditionally render board vs game viewer:
   ```tsx
   {activeGameId && activeGame ? (
     <GameViewerPanel
       game={activeGame}
       currentMoveIndex={gameMoveIndices[activeGameId] ?? -1}
       onMoveIndexChange={(idx) => setGameMoveIndices(prev => ({ ...prev, [activeGameId]: idx }))}
     />
   ) : (
     <CoachBoard ... />  // existing coach board
   )}
   ```

7. Pass `onOpenGame={handleOpenGame}` to `<CoachChat>`:
   ```tsx
   <CoachChat
     currentFen={board.fen}
     sessionId={sessionId}
     onBoardActions={handleBoardActions}
     onSessionCreated={handleSessionCreated}
     onOpenGame={handleOpenGame}
   />
   ```

## Key Details
- The PGN endpoint already exists at `/api/games/[id]/pgn` (created in the previous PR)
- The `GameViewerPanel` component from the database page is fully reusable — it just needs an `OpenedGame` object
- Max 10 tabs (same as database page) — show toast or skip if limit reached
- Tab shows "Loading..." while PGN is being fetched
- The coach board keyboard shortcuts (arrow keys for navigation) should work for game viewer too — the GameViewerPanel handles its own navigation

## Files to modify
1. `frontend/src/types/coach.ts` — add `OpenedCoachGame` interface (optional, can use `OpenedGame` from GameViewerPanel directly)
2. `frontend/src/components/coach/CoachChat.tsx` — replace `window.open` with `onOpenGame` callback
3. `frontend/src/app/coach/page.tsx` — add tab state, tab bar UI, game viewer rendering, and `handleOpenGame` logic

## Testing
- Click a game result in chat → tab opens, game loads on board panel
- Multiple games → tab bar shows all, click to switch
- Close tab → returns to coach board
- Already-open game → switches to existing tab (no duplicate)
- Loading state → shows spinner while PGN fetches
