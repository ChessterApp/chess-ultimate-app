# PRD: Universal GameTable Component

## Goal
Create a shared `GameTable` component and replace the game list rendering in 3 consumer files. The MyGamesPanel already has the target table design — extract its table pattern into a reusable component.

## Reference Implementation
The table in `frontend/src/components/openings/MyGamesPanel.tsx` (lines ~265-414) is the reference. Copy its exact styles (`thSx`, `tdSx`) and table structure.

## Step 1: Create `frontend/src/components/openings/GameTable.tsx`

A new shared component with these props:
```typescript
interface GameTableProps {
  games: GameSearchResult[];
  onOpenGame?: (game: GameSearchResult) => void;
  loading?: boolean;
  emptyMessage?: string;
}
```

Import `GameSearchResult` from `@/hooks/useOpeningRepertoire`.

Table columns: **Year | White | Elo | Black | Elo | Result | ECO**

- No actions column (that's MyGamesPanel-specific)
- No favorite indicator column (that's MyGamesPanel-specific)
- Wrapped in `<Box sx={{ overflowX: 'auto' }}>`
- Use `<Table size="small" sx={{ minWidth: 480 }}>`
- Clickable rows with hover highlight: `'&:hover': { bgcolor: 'rgba(255,255,255,0.06)' }`
- Player name fields: use `game.white_name || game.white || '?'` and same for black
- Year: `game.date ? game.date.substring(0, 4) : (game.year || '—')`
- Elo: `game.white_elo ?? '—'` and `game.black_elo ?? '—'`
- Result coloring: green `#4ade80` for `1-0`, red `#f87171` for `0-1`, gray `#9ca3af` for draws
- ECO: `game.eco || ''`
- Player name cells: `maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'`
- If `loading` is true, show a `LinearProgress` above the table
- If `games.length === 0 && !loading`, show a centered Typography with `emptyMessage || 'No games found'`

Style constants (copy exactly from MyGamesPanel):
```typescript
const thSx = {
  fontSize: 10, fontWeight: 700, color: 'text.secondary',
  textTransform: 'uppercase' as const, letterSpacing: 0.5,
  py: 0.75, px: 0.75,
  borderBottom: '1px solid rgba(255,255,255,0.08)',
  whiteSpace: 'nowrap' as const,
};
const tdSx = {
  fontSize: 12, color: 'text.primary',
  py: 0.5, px: 0.75,
  borderBottom: '1px solid rgba(255,255,255,0.04)',
  whiteSpace: 'nowrap' as const,
};
```

MUI imports needed: `Table, TableHead, TableBody, TableRow, TableCell, Box, Typography, LinearProgress`

## Step 2: Update `frontend/src/components/openings/NodeDetailsPanel.tsx`

Replace the game list rendering (both desktop List/ListItem AND mobile GameCard) with `<GameTable>`.

Current code to replace: The section that renders `masterGames` using `List`/`ListItem` (desktop) and `GameCard` (mobile). This is inside the games section around lines 110-170.

Replace with:
```tsx
<GameTable
  games={masterGames}
  onOpenGame={onOpenGame}
  loading={masterGamesLoading}
  emptyMessage="No master games found for this position"
/>
```

Keep the pagination controls (prev/next buttons) — they should remain below the GameTable.

Remove unused imports: `GameCard`, `List`, `ListItem`, `ListItemText`, `useMediaQuery`, `useTheme` (only if not used elsewhere in the same file).

## Step 3: Update `frontend/src/app/database/LichessExplorerTab.tsx`

Replace the `renderGamesList()` function's game rendering (both desktop List and mobile GameCard sections) with `<GameTable>`.

The `renderGamesList()` function around lines 269-358 currently has separate mobile/desktop paths. Replace the entire game list output with:
```tsx
<GameTable
  games={paginatedGames}
  onOpenGame={onOpenGame}
  loading={loading}
  emptyMessage="No games found"
/>
```

Keep the pagination controls that exist after the game list.

Remove unused imports: `GameCard`, `List`, `ListItem`, `ListItemText`, `useMediaQuery`, `useTheme` (only if not used elsewhere).

## Step 4: Update `frontend/src/app/database/ChessComExplorerTab.tsx`

Same as Lichess — replace the game list rendering (both desktop List and mobile GameCard) with `<GameTable>`.

The game list rendering is around lines 361-445. Replace with:
```tsx
<GameTable
  games={paginatedGames}
  onOpenGame={onOpenGame}
  loading={loading}
  emptyMessage="No games found"
/>
```

Keep pagination controls.

Remove unused imports: `GameCard`, `List`, `ListItem`, `ListItemText`, `useMediaQuery`, `useTheme` (only if not used elsewhere).

## DO NOT MODIFY
- `MyGamesPanel.tsx` — leave as-is (it has its own actions column)
- `TwicExplorer.tsx` — its table shows candidate moves, not games
- `GameCard.tsx` — keep it, might be used elsewhere
- `page.tsx` — no changes needed

## Verification
After all changes:
1. Run `cd frontend && npx next build` — must pass with zero errors
2. Verify GameTable.tsx exists and exports correctly
3. Verify NodeDetailsPanel, LichessExplorerTab, ChessComExplorerTab all import and use GameTable
4. No TypeScript errors
