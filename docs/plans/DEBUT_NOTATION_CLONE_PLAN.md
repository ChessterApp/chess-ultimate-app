# Debut Notation Clone Plan — Match Analysis Board Styling

## 1. Analysis Board Architecture Summary

### File Map

| File | Purpose |
|------|---------|
| `src/app/position/page.tsx` | **Analysis page** — orchestrator. Owns `game` (Chess), `fen`, and wires up `AiChessboardPanel` + `ChessterAnalysisView`. |
| `src/components/analysis/AiChessboard.tsx` | **Board + notation panel** (~2000 lines). Contains: chessboard, control bar, settings dialog, FEN display, piece analysis, **PGNView embedding**. Manages `moveHistory` (array of FENs), `currentMoveIndex`, navigation callbacks. |
| `src/components/tabs/PgnView.tsx` | **Notation renderer** — the core component we want to clone from. Two view modes: inline PGN (wrap) and table move list. Supports move analysis annotations, context-menu comments, AI annotation, download. |
| `src/components/analysis/EvalBar.tsx` | Eval bar widget (not notation-related). |
| `src/components/analysis/ChessterAnalysisView.tsx` | Right panel tabs (Stockfish, openings, chat, etc.) — does NOT contain notation. |

### Current Debut Architecture

| File | Purpose |
|------|---------|
| `src/app/debut/page.tsx` | **Debut page** — orchestrator. Owns `selectedNode` (OpeningNode), `boardFen`, tree navigation, keyboard shortcuts, game viewer tabs. |
| `src/components/openings/DebutBoard.tsx` | Board + ChessBase control bar. Clean, focused (~200 lines). Handles drop/click moves, forwards navigation callbacks to parent. |
| `src/components/openings/MoveNotation.tsx` | **Current notation** — renders tree with branches using recursive `renderNode()`. Inline layout with parenthesized variations indented by depth. |
| `src/components/openings/GameViewerPanel.tsx` | Notation for opened master games — simple inline move pairs with click selection. |
| `src/hooks/useOpeningRepertoire.ts` | Data hook — Supabase CRUD for repertoires, tree, import/export, game search. |

---

## 2. How the Analysis Notation (PgnView) Works

### Data Model
- **Linear**: `moves: string[]` — flat array of SAN strings (e.g. `["e4", "e5", "Nf3", "Nc6"]`)
- `currentMoveIndex: number` — 0-based index into moves array; the currently highlighted move
- `moveAnalysis: MoveAnalysis[] | null` — parallel array with quality/eval per move
- `goToMove(index: number)` — callback; index is **1-based** (maps to `moveHistory[index]` FENs)

### Rendering
Two modes toggled by `viewMode` (`'pgn'` | `'movelist'`), stored in `useLocalStorage("pgn_view_mode")`:

1. **PGN mode** (`renderPGNText()`): Flexbox wrap layout. For each pair:
   - `<Typography>` for move number (e.g. `1.`)
   - `<Button>` for white move — onClick triggers `goToMove(whiteIndex + 1)`
   - `<Button>` for black move
   - Spacer `<Box>` between pairs
   - Selected move: `backgroundColor: '#555'`, `color: '#fff'`
   - Unselected: `color: '#ccc'`, transparent bg
   - Analysis icons via `startIcon` + `getMoveClassificationStyle()`

2. **Move list mode** (`renderMoveList()`): Column layout. Each row:
   - 32px move number column
   - 80px white move button
   - 80px black move button
   - Comment indicator icons
   - Row border: `1px solid #333`

### Selection/Highlighting
- `currentMoveIndex` compared to move's 0-based index
- Selected: `backgroundColor: '#555'`, `color: '#fff'`
- Unselected: `backgroundColor: 'transparent'`, `color: '#ccc'`
- Hover: `backgroundColor: '#333'` (unselected) or `'#666'` (selected)
- Comment border: `1px solid #4FC3F7`

### Resizable Container
- `useLocalStorage("pgn_view_ui_dimensions")` — persisted width/height
- Drag handle in bottom-left corner
- Min/max: width 550–715, height 80–715
- Scrollbar: 6px, `#555` thumb, `#1a1a1a` track

### View Toggle
- `ToggleButtonGroup` with two buttons (PGN icon, list icon)
- Selected: `color: '#4FC3F7'`, `backgroundColor: '#333'`, `borderColor: '#4FC3F7'`

### CSS/Styling Constants
- Font: `monospace`, 12px
- Button: `minWidth: 'auto'`, `padding: '1px 3px'` (PGN) or `'2px 6px'` (list), `height: '20px'` (PGN) or `'24px'` (list)
- Container bg: `#2a2a2a`, border: `1px solid #444`, borderRadius: 1
- Game result: `#FFD700`, bold, bg `#333`, rounded

---

## 3. How the Current Debut Notation (MoveNotation) Works

### Data Model
- **Tree**: `OpeningNode` with recursive `children: OpeningNode[]`
- Each node has: `id`, `move_san`, `move_number`, `is_white_move`, `parent_id`, `fen`
- `selectedNodeId: string | null` — ID of the currently selected node
- `onNodeSelect(node: OpeningNode)` — callback to navigate

### Rendering (recursive)
`renderTree()` → `renderNode()`:
- Main line: first child at each level, rendered inline
- Branches: `children[1..n]` wrapped in `( ... )` parentheses, indented by `pl: ${Math.min((depth + 1) * 10, 40)}px`
- `MoveSpan`: `<Typography component="span">` with click handler
- `MoveNumber`: move number prefix (e.g. `1.` or `1…`)

### Selection/Highlighting
- Selected: `bgcolor: '#5c6bc0'`, `color: '#fff'`, `fontWeight: 600`
- Unselected: `color: '#d4d4d4'`, transparent bg
- Hover: `bgcolor: 'rgba(255,255,255,0.06)'`

### Container Styling
- Font: `"Roboto Mono", "SF Mono", "Fira Code", monospace`, 12.5–13px
- Line height: 1.65, letter-spacing: -0.01em
- Padding: 1–1.5 horizontal, 0.5–0.75 vertical
- Max height: 88px (mobile) / 240px (desktop)
- Background: `rgba(255,255,255,0.07)`, border: `1px solid rgba(255,255,255,0.1)`, borderRadius: 8px

### Action Bar
- Delete last / delete all buttons at bottom
- Icons: `<Backspace>`, `<DeleteSweep>`, size 15px
- Border top: `1px solid rgba(255,255,255,0.06)`

### Auto-scroll
- `selectedRef` on the selected move, `scrollIntoView({ block: 'nearest', behavior: 'smooth' })`

---

## 4. Key Differences: Analysis vs Debut

| Aspect | Analysis (PgnView) | Debut (MoveNotation) |
|--------|-------------------|---------------------|
| **Data** | Linear `string[]` | Tree `OpeningNode` with children |
| **Navigation callback** | `goToMove(index: number)` | `onNodeSelect(node: OpeningNode)` |
| **Selected state** | Integer index comparison | String ID comparison |
| **Move analysis** | `MoveAnalysis[]` with icons/colors | None (could add later) |
| **View modes** | PGN inline + table list | Inline only (with variations) |
| **Branches** | None (linear) | Recursive `( ... )` parenthesized |
| **Resizable** | Yes (drag handle) | No (fixed max-height) |
| **Comments/annotations** | Context menu + dialog | Via `notes` field in NodeDetailsPanel |
| **Download** | Annotated PGN export | Via exportPgn() in hook |
| **Container style** | `#2a2a2a` bg, `#444` border | `rgba(255,255,255,0.07)` bg, semi-transparent border |
| **Selection color** | `#555` bg | `#5c6bc0` bg |
| **Font** | `monospace` 12px | `"Roboto Mono"` family 12.5–13px |

---

## 5. What We Need to Clone

### Goal
Make the Debut MoveNotation look and feel like the Analysis PgnView — same fonts, same spacing, same highlight colors, same container styling — while preserving the tree-based branching logic.

### Components to Clone/Adapt

1. **Container styling** — copy PgnView's container: `#2a2a2a` bg, `#444` border, scrollbar styles, resizable dimensions
2. **Move rendering** — use `<Button>` elements like PgnView instead of `<Typography>` spans
3. **Selection highlight** — change from `#5c6bc0` to `#555`/`#fff` (Analysis style)
4. **View mode toggle** — add PGN (inline) vs move list (table) toggle
5. **Font** — `monospace` 12px (matching PgnView)
6. **Move number styling** — `#888` color, monospace (matching PgnView)
7. **Variation styling** — keep indentation/parentheses but match the PgnView color scheme

### What to Keep from Debut
- Tree-based recursive rendering logic (`renderNode`, `renderTree`)
- `OpeningNode` data model and `onNodeSelect` callback
- Auto-scroll behavior
- Delete last/all action bar
- Branch indentation with `( ... )` parentheses

---

## 6. Implementation Plan

### Step 1: Update MoveNotation Container Styling

**File:** `src/components/openings/MoveNotation.tsx`

Change the outer container in `MoveNotation` component:
- Background: `rgba(255,255,255,0.07)` → `#2a2a2a`
- Border: `rgba(255,255,255,0.1)` → `#444`
- Border radius: `8px` → `4px` (standard `borderRadius: 1`)
- Add scrollbar styling matching PgnView:
  ```
  '&::-webkit-scrollbar': { width: '6px' }
  '&::-webkit-scrollbar-track': { background: '#1a1a1a', borderRadius: '3px' }
  '&::-webkit-scrollbar-thumb': { background: '#555', borderRadius: '3px', '&:hover': { background: '#666' } }
  ```

**Also update in `debut/page.tsx`** — the wrapper Box around `<MoveNotation>`:
- Remove the `bgcolor`, `border`, `borderRadius` from the wrapper (move to component)
- Or keep wrapper for sizing but update colors

### Step 2: Update MoveSpan to Use Button-Style

**File:** `src/components/openings/MoveNotation.tsx`

Replace `MoveSpan`'s `<Typography>` with styled clickable element matching PgnView's `<Button>`:

```tsx
// Current:
<Typography component="span" sx={{
  color: isSelected ? '#fff' : '#d4d4d4',
  bgcolor: isSelected ? '#5c6bc0' : 'transparent',
  ...
}}>

// New (matching PgnView):
<Typography component="span" sx={{
  color: isSelected ? '#fff' : '#ccc',
  bgcolor: isSelected ? '#555' : 'transparent',
  fontFamily: 'monospace',
  fontSize: '12px',
  px: '3px',
  py: '1px',
  borderRadius: '2px',
  cursor: 'pointer',
  '&:hover': {
    bgcolor: isSelected ? '#666' : '#333',
    color: '#fff',
  },
}}>
```

### Step 3: Update MoveNumber Styling

```tsx
// Current:
<Typography component="span" sx={{ color: '#666', ... }}>

// New (matching PgnView):
<Typography component="span" sx={{
  color: '#888',
  fontFamily: 'monospace',
  fontSize: '12px',
  mr: 0.3,
  flexShrink: 0,
  userSelect: 'none',
}}>
```

### Step 4: Update Overall Font/Layout

In the notation content Box:
```tsx
// Current:
fontSize: { xs: 12.5, lg: 13 },
fontFamily: '"Roboto Mono", "SF Mono", "Fira Code", monospace',
lineHeight: 1.65,

// New:
fontSize: '12px',
fontFamily: 'monospace',
lineHeight: 1.2,
gap: '0.2px',
```

### Step 5: Update Variation (Branch) Styling

For parenthesized variations:
```tsx
// Parentheses color: '#555' → '#888' (slightly lighter for PgnView feel)
// Branch indentation remains but with updated colors
<Typography component="span" sx={{
  color: '#555',  // Keep as is, or lighten to '#666'
  fontSize: 'inherit',
  fontFamily: 'inherit',
  userSelect: 'none',
}}>
```

### Step 6: Add View Mode Toggle (Optional Enhancement)

Add a `ToggleButtonGroup` header matching PgnView:
- PGN mode: inline wrap with variations (current behavior)
- Move list mode: table layout (main line only in table, variations below)

This requires:
1. Add `viewMode` state with `useLocalStorage`
2. Add toggle UI at top of component
3. Create `renderMoveList()` for table view
4. Table view: show main line in rows (like PgnView's list mode), with expandable variations

**Note:** This is an enhancement — the core task is visual parity.

### Step 7: Update Container in debut/page.tsx

Change the wrapper around `<MoveNotation>`:
```tsx
// Current:
<Box sx={{
  bgcolor: 'rgba(255,255,255,0.07)',
  borderRadius: '8px',
  border: '1px solid rgba(255,255,255,0.1)',
  ...
}}>

// New:
<Box sx={{
  bgcolor: '#2a2a2a',
  borderRadius: 1,
  border: '1px solid #444',
  ...scrollbar styles...
}}>
```

### Step 8: Action Bar Styling Update

Match the Analysis board's darker styling:
```tsx
// Border top: 'rgba(255,255,255,0.06)' → '1px solid #333'
// Button hover: 'rgba(229,115,115,0.08)' → keep as is (red tint is good)
```

---

## 7. Shared Code Analysis

### Can Be Reused Directly
- **DebutBoard.tsx** — already matches Analysis board control bar exactly (same CB icons, same flex ratios). No changes needed.
- **Board settings** (`useLocalStorage` keys for theme, pieces, coordinates, animation) — shared between both pages.
- **ChessBase SVG icons** — duplicated in both AiChessboard and DebutBoard. Could extract to shared file but not blocking.

### Needs Adaptation (Not Direct Reuse)
- **PgnView.tsx** — Cannot be used directly for Debut because:
  - It takes `moves: string[]` (linear), not `OpeningNode` (tree)
  - It relies on integer index navigation, not node ID navigation
  - It has no branch/variation rendering
  - However, its **styling patterns** should be cloned exactly

### Could Be Extracted as Shared
- Move button styling constants (colors, padding, hover states) → shared `notationStyles.ts`
- Container styling (bg, border, scrollbar) → shared constants
- View mode toggle component → reusable

---

## 8. Summary: Exact Changes Needed

### Files to Modify

| File | Changes |
|------|---------|
| `src/components/openings/MoveNotation.tsx` | Update `MoveSpan` colors/styling, `MoveNumber` colors, container font, variation parentheses, action bar border. ~30 lines changed. |
| `src/app/debut/page.tsx` | Update the `<Box>` wrapper around `<MoveNotation>` — background, border, borderRadius, scrollbar styles. ~10 lines changed. |

### Files to Create (Optional)

| File | Purpose |
|------|---------|
| `src/lib/notation/styles.ts` | Shared notation style constants (if we want DRY code across PgnView and MoveNotation) |

### Files NOT to Touch
- `PgnView.tsx` — leave as is
- `AiChessboard.tsx` — leave as is
- `DebutBoard.tsx` — already matching
- `useOpeningRepertoire.ts` — data layer, no UI changes

---

## 9. Visual Comparison Target

### Before (Current Debut)
- Blueish selection (`#5c6bc0`)
- Semi-transparent background (`rgba(255,255,255,0.07)`)
- Rounded corners (8px)
- Roboto Mono font family
- Light gray text (`#d4d4d4`)

### After (Matching Analysis)
- Gray selection (`#555`, white text)
- Solid dark background (`#2a2a2a`)
- Subtle corners (4px)
- System monospace
- Standard gray text (`#ccc`)
- Properly styled scrollbar (6px, dark track)
- Clean hover states (`#333` unselected, `#666` selected)

The tree branching with `( ... )` indentation will be preserved — this is unique to Debut and doesn't exist in Analysis. We're only cloning the **visual treatment** of individual moves and the container, not the data architecture.
