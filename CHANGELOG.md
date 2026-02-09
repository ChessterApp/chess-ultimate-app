# Changelog

All notable changes to Chesster are documented here.

---

## [2026-02-09] — Debut Page Overhaul

### Notation System
- **`85c0220`** — Created `MoveNotation.tsx` replacing old `OpeningTree` component with Lichess-style inline notation. Recursive rendering: main line inline, variations indented in `( )`. Selected move highlighted, auto-scroll.
- **`391c8fd`** — Restyled notation: Roboto Mono font, 12.5px size, 80px mobile height (was 150px), thin custom scrollbar, subtle border-top separator.
- **`4490542`** — Notation container redesign: 8px rounded box with visible border (`rgba(255,255,255,0.1)`), width matched to board via `calc()`, semi-transparent background.
- **`f4c10fc`** — Added delete last move (⌫ Backspace) and delete all (🧹 DeleteSweep) buttons on notation action bar. Bottom-right placement, red hover, confirmation dialog for delete all.

### Notation/Board Sync Fix (Critical)
- **`6cac79d`** — Fixed root cause of notation desync. Added `selectedNodeId` state that tracks desired node by ID string. `useEffect` re-resolves `selectedNode` from `currentTree` whenever tree is re-fetched. Previously, `selectedNode` held a stale flat API response after `addNode` → `fetchTree`, causing broken arrow navigation, duplicate node creation, and orphaned state. Inspired by Lichess's path-based architecture.

### Master Games
- **`5f5bb04`** — Auto-fetch master games from TWIC database when a node is selected in Debut page.
- **`ddd54b1`** — Removed Training and Actions panels from NodeDetailsPanel, increased games from 5 to 15.
- **`cef7b6e`** — Paginated master games: 10 per page with ◀ 1/5 ▶ navigation, fetch 50 per position.
- **`5d2771d`** — Deferred COUNT query: games load in ~286ms (was ~720ms). Count fetched asynchronously in background, cached in-memory. New `/games/position-count` endpoint.

### Layout & Mobile
- **`1ce9f78`** — Removed Notes section and Starting Position display from NodeDetailsPanel. Master Games section moved to top.
- **`af34667`** — Debut tab bar always visible (not conditional on opened games).
- **`b60de42`** — Fixed mobile dead space: removed `minHeight: 100vh` on mobile, disabled flex stretch.
- **`d53da35`** — Right panel `flex: none` on mobile to prevent stretching.
- **`91bce1a`** — Removed double bottom padding (was `pb: 80px` + `BottomNavSpacer` = 128px gap).
- **`41f6e86`** — Mobile background matched to app theme (`#1a0d2e` instead of `#1a1a1a`).

### Control Bar
- **`e69f3e0`** — Matched DebutBoard control bar to Analysis board: `#2a2a2a` bg, 38px height, no border-radius, flex proportions (reset/start/end/flip=1, prev/next=1.42), matching icon sizes and hover effects.

### Internationalization
- **`99be835`** — Full i18n localization of Debut page (EN/RU/KK). 5 components localized, 41 new keys per language.
- **`9d40adf`** — Localized "(starting position)" text.

### Bug Fixes
- **`05c3726`** — `GET /nodes/{id}/games` returns `{games: []}` instead of 404 for deleted/missing nodes. Fixes console 404 errors.
- **`b7a9a5f`** — Board snaps back on move fixed with optimistic FEN update.

---

## [2026-02-08] — Game Viewer & Debut Features

### Game Viewer
- **`b791e91`** — Tabbed game viewer in Debut: click master games to replay with full PGN, move-by-move navigation, tab management.

---

## [2026-02-07] — Backend & Database

### TWIC Database Integration
- **`7a29811`** — Position hash indexer + fast path search using `game_positions` table.
- **`198935e`** — Rebuilt TWIC index: robust indexer, fix OOM, position indexer fixes.
- **`23b0ebe`** — Fix `add_node`: handle duplicate moves gracefully (check by UCI + catch 23505 constraint violation).

### API & Routing
- **`0b48256`** — Debut uses relative API URLs (nginx proxy), fix piece folder case mapping, cache busting.
- **`e6ff6e3`** — Replaced Opponent Analysis with Debut on dashboard Quick Actions.

---

## [2026-02-06] — Initial Debut Page

### Core Implementation
- Opening repertoire CRUD (create/rename/delete repertoires)
- Tree-based move management (add/delete nodes via Supabase)
- Board integration with `react-chessboard`
- ECO code + opening name detection
- PGN import/export
- Arrow annotations on board

---

## Architecture Notes

### Notation Rendering (`MoveNotation.tsx`)
- Recursive tree walker: `renderTree()` → `renderNode()`
- Main line rendered inline, variations wrapped in `( )` with indentation
- Each move is a clickable `MoveSpan` with highlight on selection
- Auto-scrolls to selected move

### State Management (`debut/page.tsx`)
- `selectedNodeId` (string) — single source of truth for current position
- `selectedNode` (object) — derived from `currentTree` via `useEffect`
- `currentTree` — nested tree fetched from backend's `build_tree()`
- Board FEN always derived from `selectedNode.fen`

### Backend Tree (`openings.py`)
- Flat nodes in Supabase linked by `parent_id`
- `build_tree()` nests them into `{...node, children: [...]}` structure
- `addNode` returns node with `children: []` for frontend compatibility
- Deferred position count with in-memory cache
