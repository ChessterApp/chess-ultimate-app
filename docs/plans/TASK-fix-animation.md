# Fix Mobile Chess Animation Speed

## Problem
Pieces feel sluggish on mobile. Three root causes stacking.

## Root Causes

1. **CSS transition: transform 0.2s on all pieces** (frontend/src/styles/chessground-theme.css line 49)
   Chessground animates pieces via JS requestAnimationFrame setting style.transform each frame. But this CSS transition ALSO smooths between those JS values, adding ~200ms of visual lag. Remove the transform part of the transition (keep opacity transition for fading).

2. **CSS transition: transform on .piece:active/:not(:active)** (frontend/src/styles/chess-animations.css lines 474-483)
   Same problem — more CSS transitions fighting the JS animation. Remove these touch transition rules entirely.

3. **AnimatedChessBoard ignores user speed setting** (frontend/src/components/chess/AnimatedChessBoard.tsx)
   Uses getChessgroundConfig() which hardcodes duration: 200 in chessgroundConfig.ts line 67. Should read from localStorage like DebutBoard and ChessgroundBoard do.

## Exact Changes Required

### File 1: frontend/src/styles/chessground-theme.css
Line 49: Change `transition: transform 0.2s, opacity 0.2s;` to `transition: opacity 0.2s;`
(Remove transform from the transition — chessground handles that via JS)

### File 2: frontend/src/styles/chess-animations.css
Lines 474-483: Remove the entire .piece:active and .piece:not(:active) blocks (lines 474-483)

### File 3: frontend/src/lib/chess/chessgroundConfig.ts
Line 67: Change hardcoded `duration: 200` to accept a parameter.
Add animationDuration to ChessgroundConfigOptions interface and use it.
Default value should be 150.

### File 4: frontend/src/components/chess/AnimatedChessBoard.tsx
In the useEffect that initializes the board (around line 156), read animation speed from localStorage key "chesster-animation-speed" and pass it as animationDuration to getChessgroundConfig call. Default to 150 if not set.

## Verification
After changes, run: npm run build
Make sure no TypeScript errors.

## Important
- Do NOT touch any other files
- Do NOT add new features
- Keep changes minimal and focused
- The default animation speed should be 150ms (fast, snappy feel)
