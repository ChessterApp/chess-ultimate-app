# PRD: Hermes Agent — AI Chess Coach for Chesster

**Version:** 1.1
**Author:** Alex + Clawdbot
**Date:** 2026-04-23
**Status:** Draft
**Changelog:** v1.1 — Added dedicated `/coach` page with interactive chessboard, board control protocol, puzzle mode, expanded Phase 3

---

## 1. Executive Summary

Integrate [Hermes Agent](https://github.com/nousresearch/hermes-agent) into Chesster (chesster.io) as a **personalized AI chess coach** for premium users. Each user gets a persistent coaching experience — the AI remembers their games, openings, weaknesses, and goals across sessions. It has access to 3.4M master games, Stockfish analysis, the user's personal data, and external chess platforms (Lichess, Chess.com).

**What changes:**
- Premium users get "Coach" mode in the existing ChatTab — a persistent, tool-equipped AI coach
- New **dedicated `/coach` page** with interactive chessboard + chat — the AI has full board control
- Free users keep the current Mastra-based stateless chat (unchanged)
- New Python service (Hermes) runs alongside existing Next.js + Flask stack

**What doesn't change:**
- Free tier chat (Mastra + Gemini Flash)
- All existing features (courses, puzzles, openings explorer, repertoire builder)
- Auth (Clerk), database (Supabase), frontend framework (Next.js)

---

## 2. Architecture Overview

### Current State

```
User → ChatTab → /api/chat/stream (Next.js)
                       ↓
                 Mastra Agent (Gemini Flash, 10 tools)
                       ↓ (fire-and-forget save)
                 Flask /api/chat/analysis → Supabase
```

- Stateless: no memory across sessions
- No user modeling (treats every user identically)
- 10 chess tools (Stockfish WASM, theme scoring, knowledge base)
- No premium/free gating (all users = premium)

### Target State

```
User → ChatTab
         ├── Free mode → /api/chat/stream → Mastra (unchanged)
         └── Coach mode → /api/coach/chat → Hermes Agent (port 8642)
                                               ├── Session memory (FTS5)
                                               ├── User chess profile
                                               ├── 16+ chess tools
                                               ├── Lichess/Chess.com APIs
                                               └── Smart model routing

User → /coach (dedicated page)
         ├── Interactive chessboard (left 55%)
         │     ├── AI-controlled via board_actions protocol
         │     ├── Puzzle mode (set + validate solutions)
         │     ├── Game navigation (PGN walk-through)
         │     ├── Arrows / highlights (visual teaching)
         │     └── Move controls (◄◄ ◄ ► ►► ↻ flip)
         └── Coach chat (right 45%)
               ├── Same Hermes backend
               ├── Current board FEN sent with each message
               └── Board actions parsed from AI response envelope
```

### Services on VPS

| Service | Port | Process | Role |
|---------|------|---------|------|
| Next.js frontend | 3000 | PM2: chess-frontend | UI + API proxy |
| Flask backend | 5001 | PM2: chess-backend | Free chat, non-chat APIs |
| **Hermes Agent** | **8642** | **PM2: hermes-chess** | **Premium coach engine** |
| Chesster Gateway | 19789 | systemd | Optional AI gateway |

---

## 3. User Experience

### 3.1 Two Coach Surfaces

Premium users access the AI coach through **two surfaces**, each suited for different use cases:

| Surface | URL | Board | Best For |
|---------|-----|-------|----------|
| **ChatTab Coach mode** | `/dashboard` (toggle) | No board (text-only) | Quick questions, casual chat, opening advice |
| **Dedicated Coach page** | `/coach` | Full interactive board | Game review, puzzles, position study, visual teaching |

Non-premium users see Coach mode grayed out with "Upgrade to Premium" tooltip. The `/coach` page redirects non-premium users to `/dashboard` with an upgrade prompt.

### 3.2 ChatTab Coach Mode (Text-Only)

In the existing ChatTab, premium users see a toggle: **"Chat" ↔ "Coach"**

- **Chat mode** (free) — current behavior, Mastra + Gemini Flash, stateless
- **Coach mode** (premium) — Hermes-backed, persistent memory, full tools (no board)
- Tooltip in Coach mode: "For full board control, try the Coach page →"

### 3.3 Dedicated Coach Page (`/coach`)

**Design vision:** Simplicity and minimalism. Lichess analysis board meets a personal tutor — clean, distraction-free, board-first.

**Layout (desktop):** Split-panel
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

**Layout (mobile):** Board stacks on top (100% width), chat slides up from bottom as a sheet.

**Theme:** Dark background (`#1a1a2e`), board stands out, chat panel slightly lighter (`#16213e`). Clean typography, no clutter.

#### 3.3.1 Board Control — What the AI Can Do

The coach doesn't just chat — it **controls the board** via a structured JSON protocol. This enables:

1. **Load a game** — from TWIC, user's saved games, or PGN paste → board shows move 1, coach walks through
2. **Set up a puzzle** — coach places a FEN position, user must find the right move(s)
3. **Set any position** — "Show me the Najdorf after 6.Bg5" → board updates to that FEN
4. **Draw arrows/highlights** — "The key idea is Nd5" → green arrow from knight to d5
5. **Navigate moves** — coach steps through a game's move list, board follows
6. **Flip the board** — orientation matches the side being discussed
7. **Show evaluation** — optional Stockfish eval bar alongside the board

#### 3.3.2 Board Control Protocol

The Hermes backend returns a structured response envelope alongside chat text:

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

The frontend `useCoachBoard` hook interprets these actions and applies them to the ChessgroundBoard.

**Key design decision:** Board control via structured actions, not FEN-in-chat-text. This is more reliable than parsing "here's the position: [FEN]" from chat messages.

#### 3.3.3 Keyboard Shortcuts

- Arrow keys: move navigation (← prev, → next, Home first, End last)
- `F`: flip board
- `Escape`: exit puzzle mode

### 3.4 Coach Mode UX (Both Surfaces)

1. **Session continuity** — "Remember last time we worked on your Sicilian? Let's pick up there."
2. **Proactive suggestions** — After analyzing a game: "I notice you struggle in rook endgames. Want to work on those?"
3. **Tool transparency** — When the coach uses a tool, it shows a subtle indicator: "Searching master games for Najdorf positions..."
4. **Session history sidebar** — List of past coaching sessions with titles, dates, searchable
5. **Chess profile card** — User can view/edit what the coach knows about them (rating, goals, preferred openings)

### 3.5 Example Interactions

**First session:**
> User: "Hi, I'm rated 1400 on Lichess and I play the Sicilian as black"
> Coach: *[calls get_player_profile for Lichess]* "Welcome! I pulled your Lichess profile — 1423 rapid, 87 games this month. I see you play 1...c5 in 62% of your black games. Your win rate is 45% in the Sicilian — there's room to grow. What's your biggest frustration with it?"

**Returning session:**
> User: "Can you find games where Carlsen plays against the Caro-Kann?"
> Coach: *[calls search_master_games]* "Found 47 games. Carlsen scores 71% against the Caro-Kann. His most common approach is the Advance Variation (3.e5) — want me to show you his key games in that line?"

**Game review (ChatTab — text only):**
> User: *[pastes PGN or loads game from My Games]*
> Coach: *[calls analyze_position, find_critical_moments]* "Three critical moments in this game. The first was 14...Nf6?! — your knight was strong on d5, and moving it gave White a tempo to play Bf4. Let me show you what Caruana did in a similar structure..."

**Game review (Coach page — with board):**
> User: "Review my last game"
> Coach: *[calls get_user_games, loads PGN onto board]* "Let me load that up."
> *Board shows the game at move 1. Coach walks through the game:*
> Coach: "The opening was fine — standard Italian. But look at move 14..." *[board navigates to move 14, arrow appears on Nf6→d5]* "Your knight was dominating on d5. Moving it to f6 gave White a free tempo for Bf4."
> Coach: *[board shows Caruana–Nepo position side by side]* "Caruana kept the knight on d5 in a similar structure and won a beautiful game. Want to play through it?"

**Puzzle session (Coach page):**
> User: "Give me some tactics to practice"
> Coach: *[sets puzzle FEN on board]* "Here's a position from Tal vs Botvinnik, 1960. White to move — find the combination."
> *User makes a move on the board*
> Coach: "That's the right first move! Now what?" *[highlights the critical square]*

---

## 4. Per-User Isolation Model

### Session Architecture

One Hermes daemon serves all users. Isolation via session IDs:

```
Clerk userId: "user_2abc123def"
      ↓
Hermes Session ID: "chesster-user_2abc123def"
      ↓
Scoped to:
  - state.db (session history, FTS5 search — filtered by session ID)
  - User chess profile (loaded from Supabase at session start)
  - Tool context (user_id injected into all tool calls)
  - Memory context (only this user's past coaching data)
```

### Per-User Memory Stack

| Layer | Source | What It Contains |
|-------|--------|-----------------|
| **System prompt** | Built at each turn | Rating, openings, goals, weaknesses, recent session summaries |
| **Session history** | Hermes state.db | Full conversation history (FTS5 searchable) |
| **Chess profile** | Supabase `user_chess_profiles` | Structured data: rating history, opening stats, weakness tags |
| **Game history** | Supabase `user_games` | User's imported/played games |
| **Repertoire** | Supabase `repertoire_*` | User's prepared opening lines |

### System Prompt Template (injected per turn)

```
You are coaching {display_name}.
Rating: {platform} {rating} ({rating_trend} over last 30 days)
Preferred openings (White): {white_openings}
Preferred openings (Black): {black_openings}
Known weaknesses: {weakness_tags}
Current goals: {goals}
Sessions together: {session_count}
Last session ({last_session_date}): {last_session_summary}
```

---

## 5. Tool Registry

### Architecture: Plugin-Based Tool Loading

Tools are Python modules in `hermes-chess/tools/`. Each module registers one or more tools with Hermes's tool registry via decorators or explicit registration. Adding new tools = dropping a new `.py` file.

```
hermes-chess/
├── tools/
│   ├── __init__.py          # Auto-discovers and loads all tool modules
│   ├── twic_search.py       # search_master_games, get_game_pgn
│   ├── stockfish.py         # analyze_position
│   ├── openings.py          # get_opening_stats, get_position_stats
│   ├── user_data.py         # get_user_repertoire, get_user_games, get_user_progress
│   ├── player_profiles.py   # get_player_profile, get_player_openings
│   ├── game_analysis.py     # find_critical_moments, compare_variations, score_position_themes
│   ├── external_apis.py     # lichess_*, chesscom_*
│   └── web_search.py        # search_web
```

### Phase 1 Tools (MVP — 8 tools)

| # | Tool | Source | Description |
|---|------|--------|-------------|
| 1 | `search_master_games` | TWIC SQLite | Search 3.4M games by player, ECO, year, result |
| 2 | `get_game_pgn` | TWIC PGN files | Retrieve full PGN for a specific game |
| 3 | `analyze_position` | Stockfish binary | Engine evaluation, best moves, top lines (depth configurable) |
| 4 | `get_opening_stats` | ECO JSON + TWIC | Opening name, main lines, master statistics |
| 5 | `get_user_repertoire` | Supabase | User's prepared opening lines (White/Black) |
| 6 | `get_user_games` | Supabase | User's imported/played game history |
| 7 | `get_player_profile` | Lichess + Chess.com API | Rating, stats, recent games for any player |
| 8 | `search_web` | Web search API | Fallback for questions outside chess data |

### Phase 2 Tools (Post-MVP — 8 tools)

| # | Tool | Source | Description |
|---|------|--------|-------------|
| 9 | `get_position_stats` | TWIC move_stats | Position frequency, win rates from 285M positions |
| 10 | `get_player_openings` | TWIC aggregation | Player's opening repertoire stats from master DB |
| 11 | `score_position_themes` | Theme engine | Material, mobility, space, king safety scores |
| 12 | `compare_variations` | Multi-line analysis | Side-by-side variation comparison |
| 13 | `find_critical_moments` | Game analysis | Detect turning points via eval + theme shifts |
| 14 | `get_user_progress` | Supabase | Course completions, puzzle performance |
| 15 | `lichess_game_import` | Lichess API | Import user's recent games from Lichess |
| 16 | `chesscom_game_import` | Chess.com API | Import user's recent games from Chess.com |

### Tool Implementation Pattern

```python
# hermes-chess/tools/twic_search.py
from hermes.tools import tool
import sqlite3

TWIC_DB = "/root/chess-app/backend/data/twic/twic_games.db"

@tool(
    name="search_master_games",
    description="Search 3.4M master games from TWIC database by player name, "
                "ECO code, opening name, result, or year range. "
                "Returns game metadata (players, result, date, event, ECO).",
    toolset="chess"
)
def search_master_games(
    player: str = None,
    eco: str = None,
    opening: str = None,
    result: str = None,  # "1-0", "0-1", "1/2-1/2"
    year_min: int = None,
    year_max: int = None,
    limit: int = 20
) -> list[dict]:
    conn = sqlite3.connect(TWIC_DB)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM games WHERE 1=1"
    params = []

    if player:
        query += " AND (white LIKE ? OR black LIKE ?)"
        params.extend([f"%{player}%", f"%{player}%"])
    if eco:
        query += " AND eco = ?"
        params.append(eco)
    if opening:
        query += " AND opening LIKE ?"
        params.append(f"%{opening}%")
    if result:
        query += " AND result = ?"
        params.append(result)
    if year_min:
        query += " AND CAST(SUBSTR(date, 1, 4) AS INTEGER) >= ?"
        params.append(year_min)
    if year_max:
        query += " AND CAST(SUBSTR(date, 1, 4) AS INTEGER) <= ?"
        params.append(year_max)

    query += f" ORDER BY date DESC LIMIT ?"
    params.append(min(limit, 50))

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

### Adding Future Tools

To add a new tool:
1. Create `hermes-chess/tools/my_tool.py`
2. Decorate function with `@tool(name=..., description=..., toolset="chess")`
3. Restart Hermes: `pm2 restart hermes-chess`

No other changes needed — tool auto-discovery handles registration.

---

## 6. External Chess Platform Integration (MVP)

### 6.1 Lichess API

No auth needed for public endpoints. Rate limit: 15 req/s.

**Tools:**
- `get_player_profile(username, platform="lichess")` — Rating, stats, game count
- `lichess_game_import(username, max_games=50)` — Import recent games as PGN

**Endpoints used:**
- `GET https://lichess.org/api/user/{username}` — Profile
- `GET https://lichess.org/api/games/user/{username}?max={n}` — Games (PGN stream)
- `GET https://lichess.org/api/user/{username}/perf/{perf_type}` — Rating history

### 6.2 Chess.com API

No auth needed. Rate limit: 200 req/min.

**Tools:**
- `get_player_profile(username, platform="chesscom")` — Rating, stats
- `chesscom_game_import(username, max_games=50)` — Import recent games

**Endpoints used:**
- `GET https://api.chess.com/pub/player/{username}` — Profile
- `GET https://api.chess.com/pub/player/{username}/stats` — Ratings
- `GET https://api.chess.com/pub/player/{username}/games/{YYYY}/{MM}` — Monthly games

### 6.3 Integration Flow

When a user connects their Lichess/Chess.com account:
1. User enters username in Chesster settings
2. Coach verifies via API: "Found your Lichess account — 1423 rapid, joined 2024. Is this you?"
3. On confirmation, stores platform username in `user_chess_profiles`
4. Coach can now pull real-time stats and import games on demand

---

## 7. LLM Model Routing

### Tiered + Smart Routing Strategy

```
┌─────────────────────────────────────┐
│ Incoming coach message              │
│                                     │
│ 1. Classify query complexity:       │
│    - QUICK: factual, lookup, simple │
│    - ANALYSIS: position eval,       │
│      game review, pattern matching  │
│    - DEEP: multi-step reasoning,    │
│      lesson planning, creative      │
│                                     │
│ 2. Apply tier ceiling:              │
│    - Free: QUICK only (Flash)       │
│    - Premium: up to ANALYSIS        │
│    - Pro: up to DEEP                │
│                                     │
│ 3. Route to model:                  │
│    QUICK    → Gemini 3 Flash        │
│    ANALYSIS → Claude Sonnet 4.5     │
│    DEEP     → Claude Opus 4.6       │
└─────────────────────────────────────┘
```

### Query Classification (Hermes middleware)

```python
def classify_query(query: str, context: dict) -> str:
    """Classify query complexity for model routing."""
    # DEEP indicators
    deep_keywords = ["lesson plan", "study plan", "prepare against",
                     "what should I focus on", "training program",
                     "analyze my last 10 games"]
    if any(k in query.lower() for k in deep_keywords):
        return "DEEP"

    # ANALYSIS indicators
    if context.get("fen") or context.get("pgn"):
        return "ANALYSIS"
    analysis_keywords = ["analyze", "evaluate", "review", "critical moment",
                         "what's wrong with", "best move", "compare"]
    if any(k in query.lower() for k in analysis_keywords):
        return "ANALYSIS"

    # Default: QUICK
    return "QUICK"
```

### Model Map

| Complexity | Model | Provider | Cost/1M tokens |
|-----------|-------|----------|----------------|
| QUICK | Gemini 3 Flash | Google via OpenRouter | ~$0.075 |
| ANALYSIS | Claude Sonnet 4.5 | Anthropic via OpenRouter | ~$3.00 |
| DEEP | Claude Opus 4.6 | Anthropic via OpenRouter | ~$15.00 |

### Subscription Tiers

| Tier | Price | Max Complexity | Daily Limit | Model Access |
|------|-------|---------------|-------------|-------------|
| Free | $0 | QUICK only | 10 queries | Flash only |
| Premium | $10/mo | ANALYSIS | Unlimited | Flash + Sonnet |
| Pro | $25/mo | DEEP | Unlimited | Flash + Sonnet + Opus |

---

## 8. Coach Persona

### SOUL.md

```markdown
# Chess Coach — Chesster

You are a world-class chess coach integrated into Chesster (chesster.io).
You combine the analytical precision of a modern engine with the pedagogical
approach of great teachers like Dvoretsky, Silman, and Yusupov.

## Coaching Method

1. **Ask before telling.** Start by understanding the student's thought process.
   "What were you considering here?" before "The best move is..."

2. **Socratic guidance.** Lead students to discover answers through questions.
   Not "Nd5 is best" but "What squares does your knight control from d5?"

3. **Real games, real patterns.** Always reference master games to illustrate
   concepts. Use your search_master_games tool — don't make up examples.

4. **Track the student.** Remember their weaknesses, celebrate their progress,
   adjust difficulty to their level. A 1200 needs different explanations than
   a 1800.

5. **Be honest about uncertainty.** If you're not sure about an evaluation,
   say so and use Stockfish to verify. Never bluff chess knowledge.

## Personality

Direct, encouraging, occasionally witty. Think: the coach who believes in you
but doesn't let you off easy. Never condescending, never patronizing.

Good:
- "Nice idea with Bg5! But check what happens after ...h6 — do you still
  want the bishop there?"
- "You found the right plan. Caruana played the exact same idea against
  Nepo in 2022."

Bad:
- "Great question! Let me explain..." (corporate speak)
- "As a chess AI, I think..." (breaking character)
- "The computer says Nd5 is +1.3" (lazy, no teaching)

## Using Tools

You have access to 3.4M master games, Stockfish, the student's repertoire,
their game history, and external platform data. USE THEM. Don't guess when
you can look it up. But explain what you found — raw data without
interpretation is useless coaching.

## Language

Match the student's language. If they write in Russian, coach in Russian.
If English, English. Never mix languages in one message.
```

---

## 9. Database Schema Changes

### New Table: `user_chess_profiles`

```sql
CREATE TABLE user_chess_profiles (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE,                    -- Clerk userId
  display_name TEXT,

  -- Ratings
  lichess_username TEXT,
  lichess_rapid_rating INTEGER,
  chesscom_username TEXT,
  chesscom_rapid_rating INTEGER,
  self_reported_rating INTEGER,

  -- Chess identity
  preferred_openings_white TEXT[],                 -- e.g., ["Italian Game", "London System"]
  preferred_openings_black TEXT[],                 -- e.g., ["Sicilian Najdorf", "Caro-Kann"]
  playing_style TEXT,                              -- e.g., "aggressive", "positional", "tactical"
  weakness_tags TEXT[],                            -- e.g., ["rook endgames", "time management", "calculation"]

  -- Goals
  goals TEXT,                                      -- free text from user
  target_rating INTEGER,

  -- Coach metadata
  total_coaching_sessions INTEGER DEFAULT 0,
  last_session_at TIMESTAMPTZ,
  last_session_summary TEXT,                       -- 1-2 sentence summary of last session

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for quick lookup by Clerk userId
CREATE INDEX idx_user_chess_profiles_user_id ON user_chess_profiles(user_id);
```

### New Table: `coaching_sessions`

```sql
CREATE TABLE coaching_sessions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id TEXT NOT NULL,                           -- Clerk userId
  hermes_session_id TEXT NOT NULL,                 -- "chesster-{userId}-{session_number}"
  title TEXT,                                      -- Auto-generated session title
  summary TEXT,                                    -- AI-generated summary

  -- Metadata
  message_count INTEGER DEFAULT 0,
  tools_used TEXT[],                               -- Which tools were called
  model_used TEXT,                                 -- Primary model used
  topics TEXT[],                                   -- e.g., ["Sicilian Najdorf", "rook endgames"]

  -- Timestamps
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,

  FOREIGN KEY (user_id) REFERENCES user_chess_profiles(user_id)
);

CREATE INDEX idx_coaching_sessions_user_id ON coaching_sessions(user_id);
```

### Existing tables (no changes needed):
- `analysis_conversations` — keep for free chat
- `analysis_chat_messages` — keep for free chat
- `user_games` — coach reads from this
- `repertoire_*` — coach reads from these
- `course_progress` — coach reads from this

---

## 10. Frontend Changes

### 10.1 Dedicated Coach Page (`/coach`)

**New page** with interactive chessboard + chat. Premium-gated at page level.

**Page files:**
- `frontend/src/app/coach/page.tsx` — The page (split-panel layout)
- `frontend/src/app/coach/layout.tsx` — Minimal layout (no sidebar clutter)

**Coach components:**
- `frontend/src/components/coach/CoachBoard.tsx` — Board panel (ChessgroundBoard wrapper)
- `frontend/src/components/coach/CoachChat.tsx` — Chat panel (simplified message list + input)
- `frontend/src/components/coach/BoardControls.tsx` — Navigation buttons (◄◄ ◄ ► ►► ↻ flip)
- `frontend/src/components/coach/ToolIndicator.tsx` — "Searching games..." status pill
- `frontend/src/components/coach/PuzzleOverlay.tsx` — Puzzle mode feedback (correct/wrong)

**State management:**
- `frontend/src/hooks/useCoachBoard.ts` — Board state hook (FEN, PGN, arrows, highlights, puzzle mode, navigation)
- `frontend/src/types/coach.ts` — TypeScript types for `BoardAction`, response envelope

**Board state hook (`useCoachBoard`) manages:**
- `fen`, `pgn`, `moveIndex`, `arrows`, `highlights`, `orientation`, `puzzleMode`
- `applyBoardAction(action)` — single action
- `applyBoardActions(actions[])` — batch actions from AI response
- Move navigation (next/prev/first/last)
- Puzzle validation (user moves vs solution sequence)
- `onBoardChange` callback — sends current FEN back to chat context

**Design specs:**
- Board: ChessgroundBoard (reuse existing), fills left 55% (desktop), 100% (mobile)
- Chat: right 45%, clean Markdown rendering, tool indicators
- Controls: ChessBase-style nav buttons (reuse existing SVG icons)
- Theme: dark bg `#1a1a2e`, chat panel `#16213e`
- Mobile: board stacks on top, chat as slide-up sheet
- Premium gate: redirect non-premium to `/dashboard` with upgrade prompt

### 10.2 ChatTab Updates

**File:** `frontend/src/components/tabs/ChatTab.tsx`

Changes:
- Add "Chat ↔ Coach" mode toggle (premium gated)
- Coach mode routes through `/api/coach/chat` (text-only, no board control)
- Tooltip: "For full board control, try the Coach page →"
- Add session history sidebar in Coach mode
- Add chess profile card (view/edit)
- Coach mode shows tool usage indicators

### 10.3 New API Routes

**`/api/coach/chat/route.ts`** — Main coaching endpoint
```typescript
export async function POST(req: Request) {
  const { userId } = await getAuth(req);
  if (!userId) return unauthorized();

  const tier = await getUserTier(userId);  // "free" | "premium" | "pro"
  if (tier === "free") return forbidden("Premium required");

  const { query, fen, pgn, sessionId } = await req.json();

  // Classify and route
  const complexity = classifyQuery(query, { fen, pgn });
  const model = selectModel(complexity, tier);

  // Build user context
  const profile = await getUserChessProfile(userId);
  const hermesSessionId = sessionId || `chesster-${userId}`;

  // Forward to Hermes
  const response = await fetch(`http://localhost:8642/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Hermes-Session-Id": hermesSessionId,
      "Authorization": `Bearer ${process.env.HERMES_API_KEY}`
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: buildCoachContext(profile, fen, pgn) },
        { role: "user", content: query }
      ],
      stream: true
    })
  });

  // Proxy SSE stream
  return new Response(response.body, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" }
  });
}
```

**`/api/coach/sessions/route.ts`** — Session history CRUD
- `GET` — List user's coaching sessions
- `GET /:id` — Get session detail
- `DELETE /:id` — Delete session

**`/api/coach/profile/route.ts`** — Chess profile management
- `GET` — Read user's chess profile
- `PUT` — Update goals, preferred openings, weaknesses

### 10.4 useChesster Hook Updates

**File:** `frontend/src/hooks/useChesster.ts`

Changes:
- New `sendCoachMessage()` function (routes to `/api/coach/chat`)
- Session management (create/switch/list sessions)
- Profile management hooks

### 10.5 Subscription Gating

**File:** `frontend/src/pages/api/subscription/status.ts`

Change from always-premium to actual tier check:
```typescript
// Check Supabase for user's subscription tier
const { data } = await supabase
  .from('user_subscriptions')
  .select('tier, status, expires_at')
  .eq('user_id', userId)
  .single();

return NextResponse.json({
  active: data?.status === 'active',
  plan: data?.tier || 'free',
  status: data?.status || 'inactive'
});
```

---

## 11. Implementation Phases

### Phase 1: Foundation (Week 1)

**Goal:** Hermes running on VPS, responding to API calls with chess coach persona.

**Tasks:**
1. Install Hermes Agent on VPS (`/root/hermes-chess`)
2. Create Python venv with uv, install Hermes + dependencies
3. Write chess coach profile (SOUL.md, config)
4. Configure OpenRouter as LLM provider (Gemini Flash default)
5. Start Hermes as PM2 service on port 8642
6. Verify via curl: `POST localhost:8642/v1/chat/completions`
7. Write health check script

**Deliverables:**
- Hermes daemon running, responding to chess questions
- PM2 config saved
- Health check endpoint working

**Acceptance criteria:**
- `curl -X POST localhost:8642/v1/chat/completions -d '{"messages": [{"role": "user", "content": "What is the Sicilian Defense?"}]}'` returns coherent chess coaching response
- Process stays up for 24h without crash

---

### Phase 2: Chess Tool Registry (Weeks 2-3)

**Goal:** 8 MVP tools registered and tested.

**Tasks:**
1. `search_master_games` — TWIC SQLite queries (player, ECO, year, result)
2. `get_game_pgn` — Retrieve full PGN from TWIC
3. `analyze_position` — Stockfish binary integration (subprocess, configurable depth)
4. `get_opening_stats` — ECO data + TWIC statistics
5. `get_user_repertoire` — Supabase repertoire tables (scoped by user_id)
6. `get_user_games` — Supabase user game history (scoped by user_id)
7. `get_player_profile` — Lichess + Chess.com public APIs
8. `search_web` — Web search fallback

**Per-tool checklist:**
- [ ] Implementation with proper error handling
- [ ] Input validation (Zod-equivalent in Python)
- [ ] Timeout handling (30s max per tool call)
- [ ] Unit tests with fixture data
- [ ] Integration test against live data
- [ ] Tool description optimized for LLM understanding

**Deliverables:**
- 8 tools registered and passing tests
- Tool docs with examples
- Performance benchmarks (response time per tool)

**Acceptance criteria:**
- Coach can answer "Find me Kasparov's games in the King's Indian" → calls `search_master_games` → returns relevant games
- Coach can answer "Analyze this position: [FEN]" → calls `analyze_position` → returns evaluation
- Coach can answer "Show me my Sicilian repertoire" → calls `get_user_repertoire` → returns user's lines (requires user_id context)

---

### Phase 3: Board Protocol, User Memory & Frontend Integration (Weeks 3-6)

**Goal:** Premium users can chat with the coach in Chesster (both ChatTab and dedicated Coach page), with persistent memory and interactive board control.

**Tasks:**

**Backend — Board Protocol:**
1. Define `BoardAction` Pydantic models in `src/board_protocol.py` (SetFen, LoadPgn, SetPuzzle, DrawArrows, HighlightSquares, Navigate, FlipBoard, ClearBoard)
2. Implement `board_control` Hermes tool — lets AI emit board actions in response envelope
3. Extend Hermes response format to include `message` + `board_actions[]` envelope

**Backend — User Memory:**
4. Create `user_chess_profiles` table in Supabase
5. Create `coaching_sessions` table in Supabase
6. Implement session ID mapping (Clerk userId → Hermes session)
7. Build system prompt injection (user profile → coach context)
8. Implement session summary generation (auto-summarize at session end)
9. Configure Hermes FTS5 memory (per-session isolation)

**Frontend — API Routes:**
10. Create `/api/coach/chat` route (auth + proxy to Hermes, SSE streaming)
11. Create `/api/coach/sessions` route (CRUD)
12. Create `/api/coach/profile` route (read/update chess profile)

**Frontend — Dedicated Coach Page (`/coach`):**
13. Create `/coach` page layout (split-panel: board left 55%, chat right 45%)
14. Build `CoachBoard.tsx` — ChessgroundBoard wrapper with arrows/highlights
15. Build `CoachChat.tsx` — message list + input (simplified ChatTab)
16. Build `BoardControls.tsx` — navigation buttons (◄◄ ◄ ► ►► ↻ flip)
17. Build `PuzzleOverlay.tsx` — correct/wrong feedback for puzzle mode
18. Build `ToolIndicator.tsx` — "Searching games..." status pill
19. Implement `useCoachBoard.ts` hook — board state, action processing, puzzle validation
20. Define `types/coach.ts` — BoardAction, ResponseEnvelope TypeScript types
21. Parse AI response envelope: stream `message` as text, apply `board_actions` from final SSE event
22. Premium gate: redirect non-premium to `/dashboard`

**Frontend — ChatTab Coach Mode:**
23. Add "Chat ↔ Coach" toggle in ChatTab (premium gated, text-only, no board)
24. Add session history sidebar (list past sessions, load on click)
25. Add chess profile card (view/edit goals, openings, weaknesses)
26. Update `useChesster.ts` with coach mode hooks
27. Implement subscription gating (replace always-premium)

**Deliverables:**
- Working coach mode in ChatTab (text-only)
- Dedicated `/coach` page with interactive chessboard + chat
- AI can load games, set puzzles, draw arrows, navigate moves on the board
- Session persistence across page reloads / days
- User chess profile creation and editing
- Premium gating functional

**Acceptance criteria:**
- New premium user opens Coach mode → creates chess profile → starts coaching session
- User asks about their repertoire → coach fetches from Supabase → responds with their lines
- User closes browser, returns next day → same session available in sidebar
- Free user sees "Upgrade to Premium" on coach toggle
- On `/coach`: user asks "Show me Kasparov vs Topalov 1999" → board loads the game → coach narrates
- On `/coach`: coach sets up a puzzle → user makes moves on board → coach validates solution
- On `/coach`: coach draws arrows and highlights to explain positional concepts
- On `/coach`: keyboard shortcuts (arrow keys, F for flip) work
- Mobile: board stacks on top, chat slides up from bottom

---

### Phase 4: External Platform Integration (Weeks 5-6)

**Goal:** Coach can pull data from Lichess and Chess.com.

**Tasks:**
1. Implement `lichess_game_import` tool (game history import)
2. Implement `chesscom_game_import` tool (game history import)
3. Implement platform username linking in chess profile
4. Add "Connect Lichess / Chess.com" UI in settings or profile card
5. Auto-sync ratings on profile load
6. Coach can reference external game data in conversations

**Deliverables:**
- Users can link Lichess/Chess.com accounts
- Coach auto-imports rating and recent games
- Game import stored in `user_games`

**Acceptance criteria:**
- User links Lichess username → coach confirms identity → rating syncs
- "Import my last 10 Lichess games" → games appear in My Games + coach can analyze them
- Coach proactively references external platform stats in coaching

---

### Phase 5: Advanced Features (Weeks 6-8)

**Goal:** Deeper coaching tools and learning loop.

**Tasks:**
1. Phase 2 tools: `score_position_themes`, `compare_variations`, `find_critical_moments`, `get_position_stats`, `get_player_openings`, `get_user_progress`
2. Opponent preparation: "I'm playing against [username] tomorrow — help me prepare"
3. Weakness tracking: auto-detect weaknesses from analyzed games, update profile
4. Training recommendations: suggest puzzles/courses based on weakness analysis
5. Learning loop: Hermes auto-creates coaching "skills" from repeated successful teaching patterns
6. Session summary emails (optional)

**Deliverables:**
- 16 total tools
- Opponent prep workflow
- Auto weakness detection
- Learning loop active

---

### Phase 6: Polish & Scale (Weeks 8-10)

**Goal:** Production hardening.

**Tasks:**
1. Rate limiting per tier (enforce at Next.js API layer)
2. Cost monitoring dashboard (track LLM spend per user)
3. Error handling + graceful degradation (Hermes down → show message, don't crash)
4. Load testing (simulate 50 concurrent coaching sessions)
5. Monitoring (PM2 metrics, Hermes health endpoint, alert on crash)
6. Stripe/payment integration for Premium/Pro tiers
7. Usage analytics (popular tools, session length, retention)

---

## 12. File Structure

### New Files

```
/root/hermes-chess/                  # Hermes Agent instance
├── .env                             # API keys, config
├── profiles/
│   └── chess-coach/
│       ├── SOUL.md                  # Coach persona
│       └── config.yaml              # Model routing, tool config
├── src/
│   └── board_protocol.py           # Board action types + validation (Pydantic)
├── tools/
│   ├── __init__.py                  # Auto-discovery loader
│   ├── twic_search.py              # search_master_games, get_game_pgn
│   ├── stockfish.py                # analyze_position
│   ├── openings.py                 # get_opening_stats, get_position_stats
│   ├── user_data.py                # get_user_repertoire, get_user_games, get_user_progress
│   ├── player_profiles.py          # get_player_profile, get_player_openings
│   ├── game_analysis.py            # find_critical_moments, compare_variations, score_position_themes
│   ├── external_apis.py            # lichess_*, chesscom_*
│   ├── board_control.py            # Hermes tool that emits board_actions
│   └── web_search.py              # search_web
├── middleware/
│   └── model_router.py             # Query classification + model selection
├── tests/
│   ├── test_tools.py
│   ├── test_board_protocol.py      # Board action validation tests
│   └── fixtures/
└── state.db                         # Hermes session storage (auto-created)

/root/chess-app/frontend/src/
├── app/coach/
│   ├── page.tsx                    # Dedicated coach page (split-panel)
│   └── layout.tsx                  # Minimal layout (no sidebar)
├── app/api/coach/
│   ├── chat/route.ts               # Main coaching endpoint (proxy to Hermes)
│   ├── sessions/route.ts           # Session history CRUD
│   └── profile/route.ts            # Chess profile CRUD
├── components/tabs/
│   └── ChatTab.tsx                 # Updated: coach mode toggle
├── components/coach/
│   ├── CoachBoard.tsx              # Board panel (ChessgroundBoard wrapper)
│   ├── CoachChat.tsx               # Chat panel (message list + input)
│   ├── BoardControls.tsx           # Navigation buttons + flip/reset
│   ├── CoachToggle.tsx             # Chat/Coach mode switch (for ChatTab)
│   ├── SessionSidebar.tsx          # Past sessions list
│   ├── ChessProfileCard.tsx        # View/edit chess profile
│   ├── ToolIndicator.tsx           # "Searching games..." indicator
│   └── PuzzleOverlay.tsx           # Puzzle mode feedback UI
├── hooks/
│   ├── useChesster.ts              # Updated: coach mode hooks
│   └── useCoachBoard.ts            # Board state management for /coach
└── types/
    └── coach.ts                    # BoardAction, ResponseEnvelope types
```

### Modified Files

```
/root/chess-app/frontend/src/
├── components/tabs/ChatTab.tsx     # Add coach toggle + session sidebar
├── hooks/useChesster.ts            # Add coach mode branching
├── pages/api/subscription/status.ts # Real tier check (not always-premium)
```

---

## 13. Environment Variables

### Hermes (`.env` in `/root/hermes-chess/`)

```env
# LLM
OPENROUTER_API_KEY=sk-or-v1-...
HERMES_DEFAULT_MODEL=google/gemini-3-flash-preview
HERMES_ANALYSIS_MODEL=anthropic/claude-sonnet-4.5
HERMES_DEEP_MODEL=anthropic/claude-opus-4.6

# Hermes API
HERMES_API_PORT=8642
HERMES_API_KEY=chesster-internal-...   # shared secret with Next.js

# Supabase (for user data tools)
SUPABASE_URL=https://qtzujwiqzbgyhdgulvcd.supabase.co
SUPABASE_SERVICE_KEY=eyJ...

# Stockfish
STOCKFISH_PATH=/usr/games/stockfish

# TWIC
TWIC_DB_PATH=/root/chess-app/backend/data/twic/twic_games.db
```

### Next.js (add to `.env.local`)

```env
# Hermes
HERMES_API_URL=http://localhost:8642
HERMES_API_KEY=chesster-internal-...   # must match Hermes
```

---

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Hermes doesn't support true multi-tenant session isolation | High | Test in Phase 1 — if broken, fork and add session scoping to state.db queries |
| LLM cost overrun from premium users | Medium | Enforce per-user daily token limits at API proxy layer. Monitor costs daily. |
| Stockfish tool hangs (infinite analysis) | Medium | 30s subprocess timeout. Kill process on timeout. |
| Hermes daemon crashes | High | PM2 auto-restart + health check cron. Graceful fallback to Mastra in frontend. |
| TWIC database lock (concurrent reads) | Low | SQLite WAL mode. Connection pooling. Read-only for Hermes tools. |
| External API rate limits (Lichess/Chess.com) | Low | Cache player profiles for 1h. Batch game imports. Respect rate headers. |
| AI generates invalid board actions (bad FEN, invalid squares) | Medium | Pydantic validation in board_protocol.py. Frontend silently ignores invalid actions, logs warning. |
| Board state desync between AI and frontend | Medium | FEN sent with every message. Frontend is source of truth for current position. |
| Puzzle mode race conditions (rapid user moves) | Low | Debounce move validation. Queue actions sequentially. |

---

## 15. Open Questions

1. **Stripe integration timing** — Should payment/subscription be Phase 3 (MVP) or Phase 6 (polish)? Current: Phase 6. Could move earlier if we want to gate access sooner.

2. **Hermes fork or upstream** — If multi-tenant isolation needs changes, do we fork Hermes or contribute upstream? Decision: start with upstream, fork only if blocked.

3. **Mastra tool parity** — Port all 10 Mastra tools to Hermes (Python) or HTTP-bridge some? Recommendation: port to Python for reliability and latency. The Mastra frontend tools (Stockfish WASM) should be re-implemented as server-side Stockfish binary calls.

4. **Coach conversation storage** — Store in Hermes state.db only, Supabase only, or both? Recommendation: Hermes state.db for session context + Supabase for long-term analytics. Dual-write.

---

## 16. Success Metrics

| Metric | Target (3 months) |
|--------|-------------------|
| Premium conversion rate | 5% of active users |
| Avg coaching sessions per premium user per week | 3+ |
| Session length (messages) | 8+ messages average |
| User retention (premium, 30-day) | 70% |
| Coach response latency (p95) | < 5s for QUICK, < 15s for ANALYSIS |
| Tool call success rate | > 95% |
| User satisfaction (in-app rating) | 4.2+ / 5.0 |
