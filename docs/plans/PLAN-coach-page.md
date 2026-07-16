# Plan: Dedicated AI Coach Page with Interactive Chessboard

**Context:** The PRD currently has Coach mode as a toggle within the existing ChatTab. Alex wants an additional **dedicated page** (`/coach`) with a full-screen chess board + chat window where the AI Coach has complete control over the board.

---

## Design Vision

**Inspiration:** Simplicity and minimalism. Think Lichess analysis board meets a personal tutor — clean, distraction-free, board-first.

**Layout:** Split-panel, responsive:
```
┌─────────────────────────────────────┐
│  /coach                             │
├──────────────────┬──────────────────┤
│                  │  Coach Chat      │
│                  │  ┌────────────┐  │
│   Chess Board    │  │ messages   │  │
│   (full height)  │  │ ...        │  │
│                  │  │ tool hints │  │
│                  │  └────────────┘  │
│  ─── controls ── │  [input box]     │
│  ◄◄ ◄ ► ►►  ↻   │                  │
├──────────────────┴──────────────────┤
│ (optional bottom bar: session list) │
└─────────────────────────────────────┘
```

**Mobile:** Board stacks on top, chat slides up from bottom (sheet-style).

---

## What the AI Coach Can Do With the Board

The coach isn't just chatting — it **controls the board state** via structured tool responses:

1. **Load a game** — from TWIC database, user's saved games, or PGN paste → board shows move 1, coach can walk through moves
2. **Set up a puzzle** — coach places a position (FEN), user must find the right move(s)
3. **Set up any position** — "Show me the Najdorf Sicilian after 6.Bg5" → board updates to that FEN
4. **Draw arrows/highlights** — "The key idea is Nd5" → arrow from knight to d5
5. **Navigate moves** — coach can step through a game's move list, board follows
6. **Flip the board** — coach can flip orientation to match the side being discussed
7. **Show evaluation** — optional Stockfish eval bar alongside the board

### Board Control Protocol

The Hermes backend returns structured JSON alongside chat text:

```json
{
  "message": "Here's Kasparov vs Topalov, 1999. A beautiful attacking game...",
  "board_actions": [
    {"type": "set_fen", "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"},
    {"type": "load_pgn", "pgn": "1. e4 c5 2. Nf3 d6 ..."},
    {"type": "set_puzzle", "fen": "...", "solution": ["e2e4", "d7d5"]},
    {"type": "draw_arrows", "arrows": [{"from": "g1", "to": "f3", "brush": "green"}]},
    {"type": "highlight_squares", "squares": ["d5", "e4"], "color": "yellow"},
    {"type": "navigate", "move_index": 15},
    {"type": "flip_board"},
    {"type": "clear_board"}
  ]
}
```

The frontend `CoachBoardController` component interprets these actions and applies them to the ChessgroundBoard.

---

## Implementation Steps

### Step 1: Board Control Protocol (Backend — Hermes)

**Files:**
- `/root/hermes-chess/src/board_protocol.py` — Define action types + validation
- `/root/hermes-chess/src/tools/board_control.py` — Hermes tool that emits board actions

**What it does:**
- Defines `BoardAction` Pydantic models (SetFen, LoadPgn, SetPuzzle, DrawArrows, HighlightSquares, Navigate, FlipBoard, ClearBoard)
- The Hermes response envelope wraps `message` + `board_actions[]`
- Board control tool lets the AI decide when to manipulate the board (e.g., "let me show you this position" triggers `set_fen`)

**Tests (8):**
- Valid/invalid FEN validation
- PGN parsing to move list
- Puzzle solution format validation
- Arrow/highlight coordinate validation
- Response envelope serialization
- Empty board_actions = chat-only message

### Step 2: Coach API Route (Frontend — Next.js)

**Files:**
- `/root/chess-app/frontend/src/app/api/coach/chat/route.ts` — Proxies to Hermes port 8642
- `/root/chess-app/frontend/src/app/api/coach/sessions/route.ts` — Session CRUD
- `/root/chess-app/frontend/src/app/api/coach/profile/route.ts` — Chess profile

**What it does:**
- SSE streaming from Hermes → client (same pattern as existing `/api/chat/stream`)
- Passes Clerk user token for session scoping
- Parses the response envelope to separate `message` (streamed as text) from `board_actions` (sent as a final SSE event)

**Tests (6):**
- Proxy forwards to correct port
- Auth header passthrough
- SSE stream format
- Board actions arrive as final event
- Session ID header handling
- Error response handling

### Step 3: CoachBoardController Hook (Frontend)

**Files:**
- `/root/chess-app/frontend/src/hooks/useCoachBoard.ts` — Board state management
- `/root/chess-app/frontend/src/types/coach.ts` — TypeScript types for board actions

**What it does:**
- Maintains board state: `fen`, `pgn`, `moveIndex`, `arrows`, `highlights`, `orientation`, `puzzleMode`
- Exposes `applyBoardAction(action: BoardAction)` — applies a single action
- Exposes `applyBoardActions(actions: BoardAction[])` — applies a batch
- Handles move navigation (next/prev/first/last)
- Puzzle mode: validates user moves against solution, tracks progress
- Emits `onBoardChange` callbacks for the chat to reference current position

**Tests (10):**
- `set_fen` updates board
- `load_pgn` parses and sets initial position
- `navigate` to specific move index
- Prev/next move navigation
- Puzzle mode: correct move accepted
- Puzzle mode: wrong move rejected
- `draw_arrows` applied to board
- `flip_board` toggles orientation
- `clear_board` resets to starting position
- Multiple actions applied in sequence

### Step 4: Coach Page Component (Frontend)

**Files:**
- `/root/chess-app/frontend/src/app/coach/page.tsx` — The page
- `/root/chess-app/frontend/src/app/coach/layout.tsx` — Minimal layout (no sidebar clutter)
- `/root/chess-app/frontend/src/components/coach/CoachChat.tsx` — Chat panel (simplified ChatTab)
- `/root/chess-app/frontend/src/components/coach/CoachBoard.tsx` — Board panel with controls
- `/root/chess-app/frontend/src/components/coach/BoardControls.tsx` — Navigation + action buttons
- `/root/chess-app/frontend/src/components/coach/ToolIndicator.tsx` — "Searching games..." indicator
- `/root/chess-app/frontend/src/components/coach/PuzzleOverlay.tsx` — Puzzle mode UI (correct/wrong feedback)

**Design:**
- **Board:** ChessgroundBoard, fills left 55% of screen (desktop), 100% width (mobile)
- **Chat:** Right 45%, clean message list + input. Markdown rendering. Tool indicators.
- **Controls:** Below board — ChessBase-style nav buttons (reuse existing SVG icons), flip, reset
- **Theme:** Dark background (`#1a1a2e`), board stands out, chat panel slightly lighter (`#16213e`)
- **Typography:** Clean, no clutter. Coach messages in a slightly different style than user messages.
- **Premium gate:** Page requires active subscription. Non-premium → redirect to upgrade page.

**Tests (8):**
- Page renders with board and chat
- Premium gate blocks free users
- Board receives actions from chat stream
- User can make moves on board
- Move navigation controls work
- Puzzle mode activates correctly
- Mobile layout stacks vertically
- Session persistence across page reloads

### Step 5: Integration — Wire Everything Together

**What it does:**
- Coach chat sends current board FEN with every message (so the AI knows what's on the board)
- Board actions from AI response auto-apply to the board
- User moves on the board get communicated to the chat context
- Session sidebar shows past coaching sessions (reuse `useChatSessions` pattern)
- Keyboard shortcuts: arrow keys for move nav, `f` for flip

**Tests (5):**
- Full round-trip: user sends message → AI responds with board action → board updates
- User makes move → next message includes updated FEN
- Session switch preserves board state
- Keyboard navigation works
- Multiple rapid messages don't cause race conditions

### Step 6: Existing ChatTab Enhancement

Keep the PRD's original plan too — Coach toggle in ChatTab for users who prefer the compact mode:
- `CoachToggle.tsx` in ChatTab header
- When toggled to Coach, routes through `/api/coach/chat` instead of `/api/chat/stream`
- No board control in ChatTab (text-only coaching)
- Tooltip: "For full board control, try the Coach page →"

---

## Integration With Existing Phases

This plan fits into the existing implementation plan as a **Phase 3 expansion**:

| Existing Phase | Status | Notes |
|---|---|---|
| Phase 0 — Test Infra | DONE | 5/5 tests |
| Phase 1 — Foundation | DONE | 19/19 tests |
| Phase 2 — Tool Registry | DONE | 76/76 tests |
| **Phase 3 — Coach Page + Frontend** | **NEW** | Steps 1-6 above |
| Phase 4 — External Platforms | Unchanged | Lichess/Chess.com |
| Phase 5 — Advanced Features | Unchanged | Opponent prep, weakness tracking |
| Phase 6 — Polish & Scale | Unchanged | Rate limiting, Stripe |

Phase 3 is now bigger — it includes both the existing ChatTab toggle AND the new dedicated Coach page. Estimated ~37 new tests (backend board protocol + frontend components + integration).

---

## Key Architectural Decisions

1. **Board control via structured actions, not FEN-in-chat-text** — The AI returns a clean JSON envelope. This is more reliable than parsing "here's the position: [FEN]" from chat text.

2. **Reuse ChessgroundBoard** — No new board library. Chessground already handles all the rendering, arrows, highlights, and animations.

3. **Reuse existing SVG icons** — ChessBase-style nav icons from AiChessboard.tsx.

4. **Puzzle mode is a board state, not a separate component** — The `useCoachBoard` hook manages puzzle validation internally. The PuzzleOverlay just shows visual feedback.

5. **Mobile-first responsive** — Board full-width on mobile, chat as a slide-up panel. No side-by-side on small screens.

6. **Premium gate at page level** — `/coach` requires subscription. If not premium, redirect to `/dashboard` with upgrade prompt. No partial rendering.
