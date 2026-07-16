# PRD: Add "Browse Database" Mode to /debut Page

## Goal
Add a "Browse Database" mode to the `/debut` page so users can explore the TWIC opening database (100M+ positions) **without** creating or selecting a repertoire first.

## Current State
- `/debut` page is fully repertoire-gated — nothing works without a selected repertoire
- `TwicExplorer` component exists (used on `/position` page) with candidate moves + game search
- `useTwicCandidates` and `useTwicGames` hooks exist and work
- `MoveTree` component has source switching (TWIC / Lichess Masters / Lichess Players)
- Backend endpoints `/positions/candidates` and `/games/by-position` are public (no auth required)

## Requirements

### 1. Add "Browse Database" Tab on /debut Page
- Add a tab/toggle at the top of the page: **"My Repertoires" | "Browse Database"**
- When "Browse Database" is active, the page shows a free-browse mode
- No repertoire selection needed
- The board starts from the standard starting position
- Users can click candidate moves to navigate through opening lines

### 2. Browse Database Mode UI
When in "Browse Database" mode, the page should show:
- **Left side:** Interactive chessboard (reuse `DebutBoard` component)
- **Right side:** The `TwicExplorer` component (candidate moves table + master games)
- **Below board:** Move notation breadcrumb showing the current line
- **Board controls:** Same ChessBase-style controls (reset, prev, next, flip)

### 3. Candidate Moves Interaction
- Display candidate moves using the existing `MoveTree` component or `TwicExplorer`
- Clicking a candidate move should:
  1. Play the move on the board
  2. Update the FEN
  3. Fetch new candidates for the resulting position
  4. Show master games for the new position
- Support the source switcher (TWIC / Lichess Masters / Lichess Players)

### 4. Master Games Section
- Show master games for the current position (reuse from TwicExplorer)
- Clicking a game should open the game viewer (GameViewerPanel)
- Support player name search and color filter

### 5. Navigation
- Maintain move history so users can go back/forward
- "Reset" button returns to starting position
- URL should NOT change (no query params needed for browse mode)

### 6. Responsive Design
- On mobile: board on top, explorer below (stacked)
- On desktop: side-by-side layout (board left, explorer right)

## Technical Implementation

### Files to Modify
1. **`/root/chess-app/frontend/src/app/debut/page.tsx`** — Add tab switcher and browse mode state. When in browse mode, render a simplified layout with DebutBoard + TwicExplorer instead of the full repertoire workflow.

### Key Points
- Reuse existing components: `DebutBoard`, `TwicExplorer`, `MoveTree`
- Reuse existing hooks: `useTwicCandidates`, `useTwicGames`
- The browse mode needs its own chess.js instance for move validation/history (not tied to any repertoire)
- Keep the repertoire mode exactly as-is — this is purely additive
- Add i18n keys for "Browse Database" / "My Repertoires" tab labels in en.json, ru.json, kz.json

### What NOT to Do
- Don't add "save to repertoire" functionality from browse mode (future feature)
- Don't change any backend endpoints
- Don't modify existing repertoire functionality
- Don't add URL routing — just client-side tab state
