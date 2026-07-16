# PRD: My Games Board Entry Integration

## Goal
Integrate the main board on the "My Games" tab as the primary game entry method. Remove the "Enter on Board" option from the AddGameModal. Add a move notation panel with per-move commentary support below the board.

## Current State
- `page.tsx` tracks `myGamesMoveHistory` (FEN array) and `myGamesMoveIndex` for the My Games tab board
- `handleMyGamesBoardMove` receives: `(from, to, piece, newFen, moveSan, moveUci)` from DebutBoard
- Currently only FENs are stored — SAN moves are discarded
- `AddGameModal.tsx` has 3 method tabs: "Enter on Board" (with its own mini chessboard), "Upload Scoresheet", "Import PGN"
- `MyGamesPanel.tsx` renders the AddGameModal with `onSave={handleSaveGame}` which calls `createGame(pgn, metadata)`

## Changes Required

### 1. page.tsx — Track SAN moves + per-move comments

**Add new state:**
```typescript
const [myGamesSanMoves, setMyGamesSanMoves] = useState<string[]>([]); // SAN notation: ['e4', 'e5', 'Nf3', ...]
const [myGamesComments, setMyGamesComments] = useState<Record<number, string>>({}); // move index → comment text
```

**Update `handleMyGamesBoardMove`:**
- In addition to pushing newFen to history, also push `moveSan` to `myGamesSanMoves`
- When truncating history on new branch (the `prev.slice(0, myGamesMoveIndex + 1)` part), also truncate SAN moves and remove comments for deleted moves

**Update `handleMyGamesReset`:**
- Also clear `myGamesSanMoves` and `myGamesComments`

**Add comment handler:**
```typescript
const handleMyGamesComment = useCallback((moveIndex: number, comment: string) => {
  setMyGamesComments(prev => {
    if (!comment.trim()) {
      const next = { ...prev };
      delete next[moveIndex];
      return next;
    }
    return { ...prev, [moveIndex]: comment };
  });
}, []);
```

**Add PGN builder:**
Build PGN string from `myGamesSanMoves` + `myGamesComments` using chess.js format with `{comment}` annotations. Example: `1. e4 {Strong opening} e5 2. Nf3 Nc6 {Solid reply} *`

**Render MyGamesMoveList below the board** when `activeTab === 'my-games' && !activeGame`, right after the DebutBoard component (in the same column, before Stockfish section):

```tsx
{activeTab === 'my-games' && !activeGame && (
  <MyGamesMoveList
    moves={myGamesSanMoves}
    currentIndex={myGamesMoveIndex}
    comments={myGamesComments}
    onNavigate={(index) => setMyGamesMoveIndex(index)}
    onComment={handleMyGamesComment}
    onUndo={() => {
      // Remove last move
      setMyGamesSanMoves(prev => prev.slice(0, -1));
      setMyGamesMoveHistory(prev => prev.slice(0, -1));
      setMyGamesMoveIndex(prev => Math.max(0, prev - 1));
      // Remove comment for deleted move
      setMyGamesComments(prev => {
        const next = { ...prev };
        delete next[myGamesSanMoves.length - 1];
        return next;
      });
    }}
    onReset={handleMyGamesReset}
  />
)}
```

**Pass board data to MyGamesPanel:**
The MyGamesPanel needs to receive the board's PGN + comments so it can pass them to AddGameModal. Add props to MyGamesPanel:
```typescript
boardPgn={buildMyGamesPgn()} // the PGN string built from sanMoves + comments
boardHasMoves={myGamesSanMoves.length > 0}
onBoardReset={handleMyGamesReset}
```

### 2. NEW: MyGamesMoveList.tsx

Location: `src/components/openings/MyGamesMoveList.tsx`

A compact move notation panel styled consistently with the app's dark theme.

**Props:**
```typescript
interface MyGamesMoveListProps {
  moves: string[];              // SAN moves array
  currentIndex: number;         // 0 = starting pos, 1 = after first move, etc.
  comments: Record<number, string>; // moveIndex (1-based, matching move) → comment
  onNavigate: (moveIndex: number) => void; // click a move to jump to that position
  onComment: (moveIndex: number, comment: string) => void;
  onUndo: () => void;
  onReset: () => void;
}
```

**Layout:**
- Scrollable box (max-height ~120px) with compact numbered moves: `1. e4 e5 2. Nf3 Nc6 ...`
- Each move is clickable — clicking navigates the board to that position
- Current move is highlighted (slightly brighter bg or underline)
- After each move, if a comment exists, show a small filled comment icon (💬 or MUI ChatBubble icon, tiny). Hovering shows the comment text in a tooltip.
- Clicking the comment icon (or an empty comment slot) opens an inline text field RIGHT BELOW the move list for typing/editing the comment. Only one comment editor open at a time.
- Below the move list: Undo and Reset buttons (small, similar styling to existing nav buttons)

**Styling:** Match the app's existing dark theme (bgcolor: rgba(255,255,255,0.03), text.primary for moves, text.secondary for move numbers, primary.main for current move highlight). Use MUI components.

### 3. AddGameModal.tsx — Remove "Enter on Board", add board-aware behavior

**New props:**
```typescript
interface AddGameModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (pgn: string, metadata?: Partial<{...}>) => Promise<boolean>;
  boardPgn?: string;          // PGN from main board (with comments)
  boardHasMoves?: boolean;    // whether the main board has moves entered
  onBoardReset?: () => void;  // callback to clear the main board after save
}
```

**Behavior changes:**

1. **Remove the `'board'` method entirely** — delete `BoardEntryTab`, the board entry state (`boardMoves`, `boardFen`, `chessRef`), and all related handlers (`handleBoardMove`, `handleBoardUndo`, `handleBoardReset`, `buildBoardPgn`). Remove the `getLegalMoves` helper function.

2. **Method selector:** Only show 2 chips: "Upload Scoresheet" and "Import PGN". Default to 'pgn'.

3. **If `boardHasMoves` is true:**
   - Show a read-only move preview at the top of the modal (before the method selector): a small box showing the PGN moves in monospace, with a green "Moves from board" chip
   - The "Save" button uses `boardPgn` as the PGN source (not the method's pgn)
   - If the user clicks on "Upload Scoresheet" or "Import PGN" chip, show a warning: "This will replace the moves you entered on the board. Continue?" with Cancel/Continue buttons. If they continue, clear `boardPgn` usage and use the method's input instead.
   - After successful save, call `onBoardReset?.()` to clear the main board

4. **If `boardHasMoves` is false:**
   - Show method selector with just Scoresheet + PGN (current behavior minus Board)
   - Normal flow

5. **Save handler:** When boardHasMoves and user hasn't overridden with scoresheet/pgn, set `source = 'board_entry'` and use `boardPgn`.

### 4. MyGamesPanel.tsx — Pass board data through to AddGameModal

**New props:**
```typescript
interface MyGamesPanelProps {
  onOpenGame?: (game: UserGame) => void;
  boardPgn?: string;
  boardHasMoves?: boolean;
  onBoardReset?: () => void;
}
```

**Pass these through to AddGameModal:**
```tsx
<AddGameModal
  open={addModalOpen}
  onClose={() => setAddModalOpen(false)}
  onSave={handleSaveGame}
  boardPgn={boardPgn}
  boardHasMoves={boardHasMoves}
  onBoardReset={onBoardReset}
/>
```

## Files to Modify
1. `src/app/database/page.tsx` — state + handlers + render MyGamesMoveList + pass props to MyGamesPanel
2. `src/components/openings/MyGamesMoveList.tsx` — NEW component
3. `src/components/openings/AddGameModal.tsx` — remove board tab, add board-aware behavior
4. `src/components/openings/MyGamesPanel.tsx` — pass-through props

## Important Notes
- DebutBoard's `onMove` signature: `(from: string, to: string, piece: string, newFen: string, moveSan: string, moveUci: string)`
- The `myGamesMoveIndex` is 0-based where 0 = starting position, 1 = after first move
- Comments use 1-based indexing in PGN format: comment after move 1 (e4) = index 0 in the array
- Use chess.js for PGN generation/validation
- Keep all existing navigation (prev/next/reset/go-to-end) working with the DebutBoard nav buttons
- The MyGamesMoveList is ADDITIONAL UI below the board — the DebutBoard nav buttons still work independently
- Match existing app styling (dark theme, MUI components, purple gradients for primary actions)
- Translations: add any new translation keys to the English locale file only, use descriptive keys under `debut.myGames.*`

## Translation Keys Needed
Add to `messages/en.json` under `debut.myGames`:
```json
{
  "movesFromBoard": "Moves from board",
  "replaceWarning": "This will replace the moves you entered on the board. Continue?",
  "continueBtn": "Continue",
  "cancelBtn": "Cancel",
  "commentPlaceholder": "Add a comment for this move...",
  "undoMove": "Undo",
  "resetMoves": "Reset"
}
```
