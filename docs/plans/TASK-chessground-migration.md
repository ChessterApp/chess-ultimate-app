# Task: Migrate Debut & Analysis boards from react-chessboard to chessground

## Goal
Replace `react-chessboard` with `chessground` in DebutBoard and AiChessboard components for Lichess-quality move animations (RAF-driven, capture fades, smooth interruption).

## Context
- `chessground` v9.2.1 is already installed (see `package.json`)
- The learning board (`AnimatedChessBoard.tsx`) already uses chessground successfully
- Existing chessground config: `src/lib/chess/chessgroundConfig.ts`
- Existing chessground CSS: `src/app/globals.css` (`.chessground-wrapper`, `.cg-wrap` styles)
- Chessground base+theme CSS: `chessground/assets/chessground.base.css`, `chessground/assets/chessground.brown.css`

## Files to Modify

### 1. Create: `src/components/chess/ChessgroundBoard.tsx`
A shared wrapper component that:
- Takes props: `fen`, `orientation`, `onMove(from, to)`, `boardSize`, `customArrows?`, `squareHighlights?`, `showCoordinates`, `animationDuration`, `pieceTheme`, `boardTheme`, `movable` (boolean), `interactive` (boolean)
- Initializes `Chessground` in a `useEffect` with a container ref
- Provides a resize observer to handle responsive sizing
- Maps our piece themes (Fritz, Cburnett, etc.) to CSS `background-image` sprites pointing to `/static/pieces/` folder
- Maps our board themes (chessbase, lichess, etc.) to chessground square colors via CSS
- Handles arrows by converting `[from, to, color]` tuples to chessground `drawable.autoShapes`
- Handles square highlights via chessground's `highlight` config
- Supports click-to-move: on square click, show legal moves as dots, then complete move on second click
- Exposes the chessground `Api` via `useImperativeHandle` (or a ref callback) so parent can call `.set()`, `.move()`, etc.

### 2. Modify: `src/components/openings/DebutBoard.tsx` (277 lines)
- Replace `import { Chessboard } from 'react-chessboard'` with the new `ChessgroundBoard`
- Remove `Arrow`, `BoardOrientation` imports from react-chessboard
- Keep all existing logic: `handleSquareClick`, `handleDrop`, control bar
- Map `handleDrop(source, target, piece)` → chessground's `onMove(orig, dest)` (validate with chess.js, call parent `onMove` with san/uci)
- Keep: responsive `boardSize`, `customPieces`, `moveSquares` (legal move indicators), `customArrows`, `showCoordinates`, `animationDuration`

### 3. Modify: `src/components/analysis/AiChessboard.tsx` (2009 lines)
- Replace `import { Chessboard } from "react-chessboard"` with `ChessgroundBoard`
- Remove `Arrow`, `BoardOrientation` imports from react-chessboard (keep the types, just redefine locally if needed)
- The `<Chessboard>` JSX is at ~line 1195. Replace with `<ChessgroundBoard>` and map props:
  - `position={fen}` → `fen={fen}`
  - `onPieceDrop` → `onMove` (adapter needed for puzzle vs analysis vs play modes)
  - `onSquareClick` → handle via chessground events
  - `customSquareStyles` → chessground highlight API
  - `customDarkSquareStyle/customLightSquareStyle` → CSS variables or chessground theme
  - `customArrows` → `drawable.autoShapes`
  - `boardWidth` → `boardSize`
  - `boardOrientation` → `orientation`
  - `customPieces` → CSS piece sprites
- Has 3 modes that need individual attention:
  - **Analysis mode**: `handlePlayerMove` + `handleSquareClick` — standard move with validation
  - **Puzzle mode**: `onDropPuzzle` + `handleSquarePuzzleClick` — external validation
  - **Play mode**: `handlePlayerMove` with turn restrictions + engine thinking indicator
- Keep ALL surrounding UI: EvalBar, control bar, settings panel, PGN view, board editor, player info bars

### 4. Add CSS: `src/app/globals.css`
- Add piece sprite CSS for all piece sets (Fritz, Cburnett, etc.) using `background-image: url('/static/pieces/...')`
- Chessground needs piece images as CSS backgrounds on elements like `cg-board piece.white.king`
- Add capture fade animation (`.fading { opacity: 0.5; transition: opacity 200ms }`)
- Add z-index layering: fading=1, normal=2, animating=8, dragging=11
- Board theme colors should be applied via CSS on `.cg-board square` elements

## Important Notes
- **Do NOT break existing functionality.** Every mode (analysis, puzzle, play, game review) must work after migration.
- **chess.js validation stays** — chessground is UI only, validation happens in chess.js
- **Piece assets** are at `/static/pieces/{folder}/{piece}.{svg|png}` (e.g., `/static/pieces/Fritz/wK.png`)
- **Board themes** use `getCurrentThemeColors(boardTheme)` from `@/libs/setting/helper` — these return `{ darkSquareColor, lightSquareColor }`
- The `animationDuration` setting is stored in localStorage key `board_ui_animation_duration` (default 200ms)
- After all changes, run `NODE_OPTIONS="--max-old-space-size=2048" npm run build` to verify compilation
- Test with `curl localhost:3000` after deployment

## Verification
1. Build must pass: `npm run build`
2. Debut page: pieces render, drag/drop works, click-to-move works, control bar works, arrows display
3. Analysis page: all 3 modes work (analysis drop, puzzle validation, play mode)
4. Settings: piece theme change, board theme change, animation duration, coordinates toggle
5. No console errors on any page
