# My Games: Card → Table Layout + Game Viewer Actions

## Part 1 — Table layout (Option A: hover-reveal actions)

File: `src/components/database/MyGamesPanel.tsx`
- Replace the `GameRow` card component with an MUI `Table`
- Columns: Year | White | Elo | Black | Elo | Result | ECO
- Compact rows, hover highlight, clickable to open game via `onOpenGame`
- Actions column (star/edit/delete) hidden by default, fades in on row hover using CSS `opacity: 0` → `opacity: 1` on `tr:hover`
- Mobile: actions always visible (no hover on touch), table scrolls horizontally with `overflow-x: auto`
- Remove MUI Card/CardContent imports, add Table/TableHead/TableBody/TableRow/TableCell imports
- Year: extract first 4 chars from `game.date` (format `YYYY.MM.DD`)
- Elo: show `—` when null/undefined
- Result: color-coded text (green for 1-0, red for 0-1, gray for draw)
- ECO: show code only (e.g. "B12"), no full opening name
- Keep existing filter/sort/search controls above the table
- Keep pagination controls below
- Starred games: show small star icon in the row (always visible) to indicate favorites

## Part 2 — Game viewer actions (Option C)

File: `src/components/openings/GameViewerPanel.tsx`
- Add new optional props: `onToggleFavorite?: () => void`, `onDeleteGame?: () => void`, `isFavorite?: boolean`
- Add Star (filled/unfilled based on `isFavorite`) and Delete icons next to existing Edit button in the toolbar area
- Delete should show a confirmation dialog before executing
- Star icon: use `Star` / `StarBorder` from MUI icons
- Delete icon: use `Delete` from MUI icons
- Only show these new buttons when the props are provided (they won't be passed for TWIC/explorer games)

File: `src/app/[locale]/database/page.tsx`
- Pass `onToggleFavorite`, `onDeleteGame`, `isFavorite` to GameViewerPanel when viewing a user game (check `openedGame?.source === 'user'`)
- Wire `onToggleFavorite` to the existing `toggleFavorite` function from `useUserGames` hook
- Wire `onDeleteGame` to the existing `deleteGame` function from `useUserGames` hook, then close the viewer after delete
- `isFavorite` comes from the game's `is_favorite` field

## Important constraints
- Do NOT break existing functionality (filters, search, pagination, game opening, add game modal)
- Do NOT modify the board interaction or move entry features
- Keep the existing `useUserGames` hook — only consume its existing functions
- Match the dark theme of the app (dark backgrounds, light text)
- Build must pass with zero TypeScript errors
