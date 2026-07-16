# PRD: Universal GameTable Component

## Goal
Extract a shared `GameTable` component from the MyGamesPanel table design and apply it to all game list renderings across the database page (TWIC master, Lichess, Chess.com explorers).

## Current State
- `MyGamesPanel.tsx` has the new compact table design (Year | White | Elo | Black | Elo | Result | ECO) — this is the reference
- `NodeDetailsPanel.tsx` (TWIC master games) uses `List`/`ListItem` on desktop, `GameCard` on mobile
- `LichessExplorerTab.tsx` uses `List`/`ListItem` on desktop, `GameCard` on mobile  
- `ChessComExplorerTab.tsx` uses `List`/`ListItem` on desktop, `GameCard` on mobile

## Requirements

### 1. Create `GameTable.tsx` shared component
- Location: `src/app/database/components/GameTable.tsx`
- Props: `games: GameSearchResult[]`, `onOpenGame?: (game: GameSearchResult) => void`, `loading?: boolean`, `selectedGameId?: string`
- Columns: Year | White | Elo | Black | Elo | Result | ECO
- Same compact MUI Table style as MyGamesPanel (copy thSx/tdSx styles)
- Clickable rows with hover highlight
- Selected row highlighted
- Horizontal scroll on mobile via `TableContainer` with `overflow-x: auto`
- Handle field name differences: `white_name || white`, `black_name || black`, `white_elo || whiteElo`, `black_elo || blackElo`
- Year extracted from `date` field (first 4 chars) or `year` field
- Result shows color-coded chip (1-0 green, 0-1 red, 1/2-1/2 or draw gray)
- ECO code only (no full opening name)
- Empty state: "No games found" message
- Loading state: skeleton or spinner

### 2. Update `NodeDetailsPanel.tsx`
- Replace the desktop `List`/`ListItem` game list AND mobile `GameCard` rendering with `<GameTable>`
- Remove unused imports (`GameCard`, `List`, `ListItem`, `ListItemText`, `useMediaQuery`, `useTheme` if no longer needed)
- Keep the "Master Games" section header and game count display
- Pass `onOpenGame` handler that calls existing game open logic

### 3. Update `LichessExplorerTab.tsx`
- Replace the desktop `List`/`ListItem` game list AND mobile `GameCard` rendering with `<GameTable>`
- Remove unused imports
- Keep the "Recent Games" section header
- Pass `onOpenGame` handler

### 4. Update `ChessComExplorerTab.tsx`
- Replace the desktop `List`/`ListItem` game list AND mobile `GameCard` rendering with `<GameTable>`
- Remove unused imports
- Keep the "Recent Games" section header
- Pass `onOpenGame` handler

### 5. Optionally refactor `MyGamesPanel.tsx`
- If practical, refactor to use `<GameTable>` as the base and extend with the actions column
- If too complex (due to hover-reveal actions, favorite indicator), leave MyGamesPanel with its own table but ensure styles match

## Important Notes
- Do NOT modify `TwicExplorer.tsx` — its table shows candidate moves, not game rows
- Do NOT delete `GameCard.tsx` — it may be used elsewhere
- The `GameSearchResult` type is defined in `src/app/database/types/` — check it for field names
- All database tabs are in `src/app/database/components/`
- Build must pass: `cd /root/chess-app/frontend && npm run build`
- After changes, verify the build succeeds

## Data Shape Reference
```typescript
interface GameSearchResult {
  id?: string;
  white?: string;
  white_name?: string;
  black?: string;
  black_name?: string;
  white_elo?: number;
  black_elo?: number;
  result?: string;
  date?: string;
  year?: number;
  eco?: string;
  pgn?: string;
  source?: string;
}
```
Check the actual type definition in the codebase — the above is approximate.
