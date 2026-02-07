# Debut (My Openings) — Implementation Plan

**Created:** 2026-02-07  
**Status:** Plan Only — Do Not Implement  
**Feature:** Opening repertoire manager with own board, tree view, game search  
**Route:** `/debut` (replaces "Learn" in bottom navigation)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Assessment](#current-state-assessment)
3. [Phase 1 — Database (Already Done)](#phase-1--database-already-done)
4. [Phase 2 — Backend API](#phase-2--backend-api)
5. [Phase 3 — Frontend Hook](#phase-3--frontend-hook)
6. [Phase 4 — UI Components](#phase-4--ui-components)
7. [Phase 5 — Debut Page](#phase-5--debut-page)
8. [Phase 6 — Navigation Integration](#phase-6--navigation-integration)
9. [Phase 7 — Polish & Testing](#phase-7--polish--testing)
10. [File Inventory](#file-inventory)
11. [Complexity Estimates](#complexity-estimates)

---

## Executive Summary

Rebuild the "My Openings" feature as a standalone page called **Debut** at `/debut`. The user navigates there via the bottom nav bar (replacing "Learn"). The page has its own chessboard (left) and repertoire tree + details panel (right), with mobile stacking. Users create repertoires, build move trees, import PGN, annotate positions, and search games by position in TWIC, Lichess, and Chess.com.

### Key Differences from Previous Implementation

| Aspect | Previous (Jan 29-30) | New (Debut) |
|--------|----------------------|-------------|
| Location | Tab inside `/position` page | Standalone page `/debut` |
| Board | Shared with analysis page | Own dedicated board |
| Navigation | Hidden in position tabs | Primary bottom nav item |
| Route | None (tab only) | `/debut` |

---

## Current State Assessment

### Database Tables — ✅ ALL EXIST
All 4 Supabase tables are intact with existing data:

| Table | Status | Sample Data |
|-------|--------|-------------|
| `opening_repertoires` | ✅ HTTP 200 | 5 repertoires exist ("My White 1.e4", "Caro-Kann", etc.) |
| `opening_nodes` | ✅ HTTP 200 | 19 nodes exist |
| `opening_game_links` | ✅ HTTP 200 | Game links with full PGN exist |
| `opening_arrows` | ✅ HTTP 200 | Empty (no arrows yet) |

### Actual Table Schemas (from Supabase REST API)

**`opening_repertoires`:**
```
id: uuid (PK)
user_id: text
name: text
color: text ('w' or 'b')
description: text (nullable)
is_primary: boolean (default false)
created_at: timestamptz
updated_at: timestamptz
starting_fen: text (nullable)
starting_move_line: text (nullable)
```

**`opening_nodes`:**
```
id: uuid (PK)
repertoire_id: uuid (FK → opening_repertoires)
parent_id: uuid (nullable, self-ref FK)
fen: text
move_san: text (nullable — null for root)
move_uci: text (nullable)
move_number: integer (default 0)
is_white_move: boolean (nullable)
opening_name: text (nullable)
eco_code: text (nullable)
notes: text (nullable)
priority: integer (default 0)
is_critical: boolean (default false)
times_trained: integer (default 0)
times_correct: integer (default 0)
last_trained_at: timestamptz (nullable)
next_review_at: timestamptz (nullable)
ease_factor: float (default 2.5)
interval_days: integer (default 1)
created_at: timestamptz
updated_at: timestamptz
```

**`opening_game_links`:**
```
id: uuid (PK)
node_id: uuid (FK → opening_nodes)
game_source: text ('internal', 'lichess', 'chesscom', 'pgn', 'user')
game_id: text (nullable)
game_pgn: text (nullable — full PGN stored)
white_player: text (nullable)
black_player: text (nullable)
white_elo: integer (nullable)
black_elo: integer (nullable)
result: text (nullable)
date_played: text (nullable)
event_name: text (nullable)
move_reached: text (nullable)
user_outcome: text (nullable)
notes: text (nullable)
created_at: timestamptz
```

**`opening_arrows`:**
```
id: uuid (PK)
node_id: uuid (FK → opening_nodes)
from_square: text
to_square: text
color: text
opacity: float (nullable)
created_at: timestamptz
```

### Backend — ❌ `api/openings.py` MISSING (bytecode exists)
- Source file `/root/chess-app/backend/api/openings.py` is gone
- Bytecode `/root/chess-app/backend/api/__pycache__/openings.cpython-312.pyc` exists (110KB)
- Full function signatures, string constants, and API routes recovered via `dis` module
- Blueprint was NOT registered in current `app.py` (no import/register for openings)

### Frontend — ❌ ALL FILES MISSING
- `/root/chess-app/frontend/src/components/openings/` — directory does not exist
- `/root/chess-app/frontend/src/hooks/useOpeningRepertoire.ts` — does not exist
- `/root/chess-app/frontend/src/app/debut/` — does not exist

---

## Phase 1 — Database (Already Done)

**Complexity:** None — tables already exist with correct schemas.

No SQL migrations needed. All 4 tables are live in Supabase with data.

If you need to recreate from scratch (disaster recovery), here is the SQL:

```sql
-- opening_repertoires
CREATE TABLE IF NOT EXISTS opening_repertoires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    color TEXT NOT NULL CHECK (color IN ('w', 'b')),
    description TEXT,
    is_primary BOOLEAN DEFAULT false,
    starting_fen TEXT,
    starting_move_line TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_repertoires_user_id ON opening_repertoires(user_id);

-- opening_nodes
CREATE TABLE IF NOT EXISTS opening_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repertoire_id UUID NOT NULL REFERENCES opening_repertoires(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES opening_nodes(id) ON DELETE CASCADE,
    fen TEXT NOT NULL,
    move_san TEXT,
    move_uci TEXT,
    move_number INTEGER DEFAULT 0,
    is_white_move BOOLEAN,
    opening_name TEXT,
    eco_code TEXT,
    notes TEXT,
    priority INTEGER DEFAULT 0,
    is_critical BOOLEAN DEFAULT false,
    times_trained INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0,
    last_trained_at TIMESTAMPTZ,
    next_review_at TIMESTAMPTZ,
    ease_factor FLOAT DEFAULT 2.5,
    interval_days INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_nodes_repertoire ON opening_nodes(repertoire_id);
CREATE INDEX idx_nodes_parent ON opening_nodes(parent_id);
CREATE INDEX idx_nodes_fen ON opening_nodes(fen);

-- opening_game_links
CREATE TABLE IF NOT EXISTS opening_game_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES opening_nodes(id) ON DELETE CASCADE,
    game_source TEXT NOT NULL,
    game_id TEXT,
    game_pgn TEXT,
    white_player TEXT,
    black_player TEXT,
    white_elo INTEGER,
    black_elo INTEGER,
    result TEXT,
    date_played TEXT,
    event_name TEXT,
    move_reached TEXT,
    user_outcome TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_game_links_node ON opening_game_links(node_id);

-- opening_arrows
CREATE TABLE IF NOT EXISTS opening_arrows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES opening_nodes(id) ON DELETE CASCADE,
    from_square TEXT NOT NULL,
    to_square TEXT NOT NULL,
    color TEXT DEFAULT 'green',
    opacity FLOAT DEFAULT 0.8,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_arrows_node ON opening_arrows(node_id);

-- RLS Policies (enable RLS on all tables)
ALTER TABLE opening_repertoires ENABLE ROW LEVEL SECURITY;
ALTER TABLE opening_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE opening_game_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE opening_arrows ENABLE ROW LEVEL SECURITY;
```

---

## Phase 2 — Backend API

**File to create:** `/root/chess-app/backend/api/openings.py`  
**File to modify:** `/root/chess-app/backend/app.py` (register blueprint)  
**Complexity:** HIGH — ~40 functions, ~800-1000 lines  
**Dependencies:** `python-chess`, `requests`, `flask`, `supabase` client

### Blueprint Registration

Add to `app.py` after the existing blueprint registrations:

```python
try:
    from api.openings import openings_bp
    app.register_blueprint(openings_bp)
    logger.info("✅ Openings API registered (repertoire management)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import openings API: {e}")
```

### API Endpoints Specification

All endpoints are prefixed with `/api/openings` and require Clerk JWT auth via `@verify_clerk_token`.

#### Repertoire CRUD

| Method | Path | Description | Request Body | Response |
|--------|------|-------------|-------------|----------|
| `GET` | `/repertoires` | List user's repertoires (auto-creates defaults for new users) | — | `{ "repertoires": [...] }` |
| `POST` | `/repertoires` | Create repertoire | `{ "name": str, "color": "w"|"b", "description"?: str, "startingFen"?: str, "startingMoveLine"?: str }` | `{ "repertoire": {...}, "root_node": {...} }` |
| `GET` | `/repertoires/<id>` | Get repertoire with full tree | — | `{ "repertoire": {...}, "tree": {...} }` |
| `PUT` | `/repertoires/<id>` | Update repertoire metadata | `{ "name"?: str, "description"?: str, "startingFen"?: str, "startingMoveLine"?: str }` | `{ "repertoire": {...} }` |
| `DELETE` | `/repertoires/<id>` | Delete repertoire + all nodes | — | `{ "success": true }` |
| `PUT` | `/repertoires/<id>/starting-position` | Set starting FEN + create move line nodes | `{ "fen": str, "moveLine"?: str }` | `{ "repertoire": {...} }` |
| `GET` | `/repertoires/<id>/pgn` | Export as PGN file | Query: `?include_notes=true` | `application/x-chess-pgn` |
| `POST` | `/repertoires/<id>/import` | Import PGN with variations | `{ "pgn": str, "maxPly"?: int }` | `{ "imported": int, "skipped": int, "errors": [...] }` |
| `POST` | `/repertoires/<id>/repair-tree` | Repair tree from move line | — | `{ "created_nodes": [...] }` |

#### Node Operations

| Method | Path | Description | Request Body | Response |
|--------|------|-------------|-------------|----------|
| `POST` | `/nodes` | Add move to tree | `{ "parentId": uuid, "moveSan": str, "moveUci"?: str, "newFen": str, "isCritical"?: bool }` | Node object |
| `PUT` | `/nodes/<id>` | Update node | `{ "notes"?: str, "priority"?: int, "isCritical"?: bool }` | Node object |
| `DELETE` | `/nodes/<id>` | Delete node + children (not root) | — | `{ "success": true }` |

#### Arrow Annotations

| Method | Path | Description | Request Body | Response |
|--------|------|-------------|-------------|----------|
| `POST` | `/nodes/<id>/arrows` | Add arrow to node | `{ "fromSquare": str, "toSquare": str, "color"?: str }` | Arrow object |
| `DELETE` | `/nodes/<id>/arrows/<arrow_id>` | Remove arrow | — | `{ "success": true }` |

#### Spaced Repetition Training

| Method | Path | Description | Request Body | Response |
|--------|------|-------------|-------------|----------|
| `GET` | `/training/due` | Get nodes due for review | Query: `?repertoire_id=&limit=20` | `{ "nodes": [...], "total_due": int }` |
| `POST` | `/training/result` | Record training result (SM-2) | `{ "nodeId": uuid, "correct": bool, "timeMs"?: int }` | Updated node |
| `GET` | `/training/stats` | Overall training stats | Query: `?repertoire_id=` | Stats object |

#### Game Search & Linking

| Method | Path | Description | Request Body | Response |
|--------|------|-------------|-------------|----------|
| `GET` | `/nodes/<id>/games` | Get games linked to node | — | `{ "games": [...] }` |
| `POST` | `/nodes/<id>/games` | Link game to node | `{ "gameSource": str, "gameId"?: str, "gamePgn"?: str, ... }` | Game link object |
| `DELETE` | `/games/<id>` | Remove game link | — | `{ "success": true }` |
| `GET` | `/games/search` | Search games (non-streaming) | Query: `?source=&fen=&username=&max_games=` | `{ "games": [...] }` |
| `GET` | `/games/search/stream` | SSE streaming game search | Query: `?source=&fen=&eco=&min_rating=` | `text/event-stream` |
| `GET` | `/games/internal/status` | Check TWIC DB status | — | Status object |

### Helper Functions

```python
def build_tree(nodes: list) -> dict:
    """Build nested tree from flat node list. Returns root node with 'children'."""

def detect_opening(fen: str) -> dict | None:
    """Query Lichess masters DB for opening name. Returns {'name': ..., 'eco': ...}."""

def detect_eco_for_search(fen: str) -> tuple[str | None, str | None]:
    """Get (eco_code, eco_name) for FEN from Lichess Explorer. Used for DB pre-filtering."""

def validate_move(fen: str, move_san: str) -> tuple[str, str, bool]:
    """Validate move is legal. Returns (new_fen, move_uci, is_white_move). Raises ValueError."""

def create_default_repertoires(user_id: str) -> list:
    """Auto-create 'White Repertoire' and 'Black Repertoire' for new users."""

def build_pgn_moves(tree: dict, include_notes: bool) -> str:
    """Recursively build PGN notation from tree (with variations)."""

def generate_repertoire_pgn(repertoire, tree, eco_info, include_notes) -> str:
    """Generate complete PGN with headers for export."""

def check_game_reaches_fen(pgn_text, target_fen, debug_game_id) -> bool:
    """Check if a game passes through a specific FEN position."""

def find_moves_to_fen(target_fen, max_depth) -> list[str]:
    """BFS through Lichess opening book to find move sequence to target FEN."""

# Internal TWIC database helpers
def get_internal_db_connection() -> sqlite3.Connection
def check_internal_db_exists() -> bool
def fetch_internal_games(search_query, max_games, filter_fen, eco_filter) -> list
def fetch_internal_games_progressive(filter_fen, eco_filter, min_rating, max_games, stop_after) -> generator
def fetch_lichess_games(username, since, max_games, filter_fen) -> list
def fetch_lichess_games_progressive(username, filter_fen, min_rating, max_games) -> generator
def fetch_chesscom_games(username, since, max_games, filter_fen) -> list
def fetch_chesscom_games_progressive(username, filter_fen, min_rating, max_games) -> generator
```

### Key Implementation Notes

1. **Auth pattern:** Every route uses `@verify_clerk_token` then `user_id = get_current_user_id()`
2. **Ownership checks:** All repertoire/node operations verify `user_id` ownership via Supabase joins
3. **Supabase client:** Import from `services.supabase_client import supabase`
4. **TWIC database:** Uses `data/twic/games_index.db` (SQLite) and `data/twic/twic_master_database.pgn`
5. **SSE streaming:** The `/games/search/stream` endpoint uses Flask's `stream_with_context` + `Response` with `text/event-stream` content type
6. **python-chess:** Required for PGN parsing, move validation, FEN manipulation

---

## Phase 3 — Frontend Hook

**File to create:** `/root/chess-app/frontend/src/hooks/useOpeningRepertoire.ts`  
**Complexity:** MEDIUM — ~300-400 lines  
**Dependencies:** `@clerk/nextjs` (for auth token)

### Hook Interface

```typescript
interface Repertoire {
  id: string;
  name: string;
  color: 'w' | 'b';
  description: string | null;
  is_primary: boolean;
  starting_fen: string | null;
  starting_move_line: string | null;
  created_at: string;
  updated_at: string;
  node_count?: number;
}

interface OpeningNode {
  id: string;
  repertoire_id: string;
  parent_id: string | null;
  fen: string;
  move_san: string | null;
  move_uci: string | null;
  move_number: number;
  is_white_move: boolean | null;
  opening_name: string | null;
  eco_code: string | null;
  notes: string | null;
  priority: number;
  is_critical: boolean;
  times_trained: number;
  times_correct: number;
  last_trained_at: string | null;
  next_review_at: string | null;
  ease_factor: number;
  interval_days: number;
  created_at: string;
  updated_at: string;
  // UI fields
  children?: OpeningNode[];
  arrows?: ArrowAnnotation[];
}

interface ArrowAnnotation {
  id: string;
  node_id: string;
  from_square: string;
  to_square: string;
  color: string;
  opacity: number;
}

interface GameLink {
  id: string;
  node_id: string;
  game_source: 'internal' | 'lichess' | 'chesscom' | 'pgn' | 'user';
  game_id: string | null;
  game_pgn: string | null;
  white_player: string | null;
  black_player: string | null;
  white_elo: number | null;
  black_elo: number | null;
  result: string | null;
  date_played: string | null;
  event_name: string | null;
  created_at: string;
}

interface ImportPgnResult {
  imported: number;
  skipped: number;
  errors: string[];
  nodes?: Partial<OpeningNode>[];
}

interface TrainingStats {
  total_nodes: number;
  trained_nodes: number;
  due_nodes: number;
  total_reviews: number;
  accuracy: number;
}

interface GameSearchResult {
  id: string | number;
  source: string;
  white: string;
  black: string;
  white_elo: number | null;
  black_elo: number | null;
  result: string;
  date: string;
  eco: string | null;
  opening: string | null;
  event: string | null;
  pgn?: string;
  url?: string;
}

// Hook return type
interface UseOpeningRepertoireReturn {
  // Repertoire CRUD
  repertoires: Repertoire[];
  loading: boolean;
  error: string | null;
  fetchRepertoires: () => Promise<void>;
  createRepertoire: (name: string, color: 'w' | 'b', opts?: { description?: string; startingFen?: string; startingMoveLine?: string }) => Promise<Repertoire>;
  updateRepertoire: (id: string, data: Partial<Repertoire>) => Promise<void>;
  deleteRepertoire: (id: string) => Promise<void>;
  
  // Tree operations
  currentTree: OpeningNode | null;
  treeLoading: boolean;
  fetchTree: (repertoireId: string) => Promise<void>;
  addNode: (parentId: string, moveSan: string, moveUci: string, newFen: string) => Promise<OpeningNode>;
  updateNode: (nodeId: string, data: { notes?: string; priority?: number; isCritical?: boolean }) => Promise<void>;
  deleteNode: (nodeId: string) => Promise<void>;
  
  // Starting position
  setStartingPosition: (repertoireId: string, fen: string, moveLine?: string) => Promise<void>;
  
  // PGN import/export
  importPgn: (repertoireId: string, pgn: string, maxPly?: number) => Promise<ImportPgnResult>;
  exportPgn: (repertoireId: string, includeNotes?: boolean) => Promise<string>;
  
  // Arrow annotations
  addArrow: (nodeId: string, fromSquare: string, toSquare: string, color?: string) => Promise<ArrowAnnotation>;
  deleteArrow: (nodeId: string, arrowId: string) => Promise<void>;
  
  // Game search & linking
  searchGames: (source: string, fen: string, opts?: { username?: string; maxGames?: number }) => Promise<GameSearchResult[]>;
  searchGamesStream: (source: string, fen: string, opts?: { eco?: string; minRating?: number }, onGame: (game: GameSearchResult) => void, onProgress: (progress: any) => void) => () => void; // returns abort function
  linkGame: (nodeId: string, data: Partial<GameLink>) => Promise<void>;
  getNodeGames: (nodeId: string) => Promise<GameLink[]>;
  deleteGameLink: (gameLinkId: string) => Promise<void>;
  
  // Training
  getDueNodes: (repertoireId?: string, limit?: number) => Promise<OpeningNode[]>;
  recordTrainingResult: (nodeId: string, correct: boolean, timeMs?: number) => Promise<void>;
  getTrainingStats: (repertoireId?: string) => Promise<TrainingStats>;
}

export function useOpeningRepertoire(): UseOpeningRepertoireReturn;
```

### Implementation Notes

1. **API base URL:** Use `process.env.NEXT_PUBLIC_API_URL` + `/api/openings/...`
2. **Auth headers:** Get token from Clerk's `useAuth().getToken()` and pass as `Authorization: Bearer <token>`
3. **SSE for streaming search:** Use `EventSource` or `fetch` with `ReadableStream` for `/games/search/stream`
4. **State management:** Internal `useState` for `repertoires`, `currentTree`, loading states
5. **Error handling:** Return error strings, throw on critical failures
6. **Cache invalidation:** Re-fetch tree after add/update/delete operations

---

## Phase 4 — UI Components

**Directory:** `/root/chess-app/frontend/src/components/openings/`  
**Complexity:** HIGH — 5 components, ~1500-2000 lines total

### 4.1 `RepertoireSelector.tsx`

**Props Interface:**
```typescript
interface RepertoireSelectorProps {
  repertoires: Repertoire[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate: (name: string, color: 'w' | 'b') => Promise<void>;
  onRename: (id: string, name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  loading: boolean;
}
```

**Functionality:**
- Dropdown/select with repertoire names + color indicator (♔ white / ♚ black)
- "New Repertoire" button opens dialog:
  - Name field (required)
  - Color toggle: White / Black
  - Optional: Starting FEN input, Move line input
- Right-click or kebab menu: Rename, Delete (with confirm dialog)
- Show node count badge per repertoire
- MUI components: `Select`, `MenuItem`, `Dialog`, `TextField`, `ToggleButton`

### 4.2 `OpeningTree.tsx`

**Props Interface:**
```typescript
interface OpeningTreeProps {
  tree: OpeningNode | null;
  selectedNodeId: string | null;
  onNodeSelect: (node: OpeningNode) => void;
  onNodeDelete?: (nodeId: string) => void;
  loading: boolean;
}
```

**Functionality:**
- Recursive tree rendering with expand/collapse
- Status indicators per node:
  - ★ (yellow) — `is_critical === true`
  - 🔴 (red Schedule icon) — `next_review_at <= now` (needs review)
  - ✓ (green) — `times_trained >= 5` AND accuracy >= 80% (`times_correct / times_trained >= 0.8`)
- Move numbering: `1. e4 e5 2. Nf3` format
- ECO code chips on opening name lines
- Toolbar: "Expand All" / "Collapse All" buttons
- Legend bar at bottom showing indicator meanings
- Descendant count on collapsed nodes ("+12")
- Auto-expand path to selected node
- Click node → calls `onNodeSelect` (parent syncs board FEN)
- `React.memo` on tree nodes for performance

**Internal Components:**
```typescript
// Recursive tree item — memoized
const TreeNodeItem = React.memo(({ node, depth, selectedId, onSelect, expandedIds, onToggle }: TreeNodeItemProps) => { ... })
```

### 4.3 `NodeDetailsPanel.tsx`

**Props Interface:**
```typescript
interface NodeDetailsPanelProps {
  node: OpeningNode | null;
  onUpdateNotes: (nodeId: string, notes: string) => Promise<void>;
  onToggleCritical: (nodeId: string, isCritical: boolean) => Promise<void>;
  onDeleteNode: (nodeId: string) => Promise<void>;
  onSearchGames: (fen: string) => void;
  gameLinks: GameLink[];
  gameLinksLoading: boolean;
}
```

**Functionality:**
- Shows when a node is selected
- **Opening info:** Name + ECO code chip (e.g., "Caro-Kann Defense" `B10`)
- **Move display:** Formatted "2. Nf3" with move number
- **FEN display:** Monospace, copyable
- **Notes section:**
  - Read-only by default, click edit icon to toggle textarea
  - Save/Cancel buttons when editing
  - Auto-save on blur (debounced)
- **Training stats:**
  - Accuracy progress bar (green >80%, yellow >60%, red <60%)
  - "Trained 5 times, 4 correct" display
  - Status chip: "Mastered" / "Due for Review" / "Untrained"
  - Next review date
- **Actions:**
  - ⭐ Mark Critical toggle button
  - 🗑️ Delete Move button with confirmation dialog ("This will delete all child moves")
  - 🔍 Search Games button (triggers game search for this position)
- **Game links list:**
  - Shows linked games with player names, elo, result, date
  - Source badge (TWIC / Lichess / Chess.com)
  - Click to view PGN
  - Delete link button

### 4.4 `PgnImporter.tsx`

**Props Interface:**
```typescript
interface PgnImporterProps {
  open: boolean;
  onClose: () => void;
  onImport: (pgn: string, maxPly: number) => Promise<ImportPgnResult>;
  repertoireName: string;
}
```

**Functionality:**
- Modal dialog (MUI `Dialog`, fullWidth, maxWidth "md")
- **PGN textarea:** 10 rows, monospace font, placeholder text
- **"Load Example" button:** Inserts sample Caro-Kann PGN
- **Max Ply slider:** Range 5-50, default 30, marks at 10/20/30/40/50
- **Info box:** Explains handling of variations, transpositions, deduplication
- **Import button:** Calls `onImport`, shows loading spinner
- **Results display (after import):**
  - Success/warning alert
  - Chips: "15 imported" / "3 skipped" / "0 errors"
  - Expandable list of sample imported nodes
  - Error details if any
  - "Import More" button to reset form

### 4.5 `GameSearchPanel.tsx` (NEW — not in previous impl)

**Props Interface:**
```typescript
interface GameSearchPanelProps {
  fen: string;
  onLinkGame: (game: GameSearchResult) => Promise<void>;
  open: boolean;
  onClose: () => void;
}
```

**Functionality:**
- Modal/slide panel for searching games by position
- **Source tabs:** Internal (TWIC) / Lichess / Chess.com
- **Search controls:**
  - Username field (for Lichess/Chess.com)
  - Min rating slider
  - Max results slider
- **Streaming results:** Uses SSE, games appear one-by-one
- **Progress indicator:** "Checked 150 games, found 3 matches"
- **Results list:**
  - Player names + elos
  - Result + date
  - ECO + opening name
  - "Link to Position" button per game
  - "View PGN" expandable section
- **ECO auto-detection:** Shows detected ECO for position

---

## Phase 5 — Debut Page

**File to create:** `/root/chess-app/frontend/src/app/debut/page.tsx`  
**Complexity:** HIGH — main orchestrator, ~400-500 lines

### Page Layout

```
┌─────────────────────────────────────────────────────────┐
│  Desktop (lg+)                                          │
│  ┌──────────────────┐  ┌────────────────────────────┐   │
│  │                  │  │  RepertoireSelector         │   │
│  │   Chessboard     │  │  ──────────────────────────  │   │
│  │   (ChessBase     │  │  OpeningTree                │   │
│  │    theme +       │  │                              │   │
│  │    Fritz         │  │                              │   │
│  │    pieces)       │  │  ──────────────────────────  │   │
│  │                  │  │  NodeDetailsPanel            │   │
│  │  [Control Bar]   │  │                              │   │
│  └──────────────────┘  └────────────────────────────┘   │
│                                                          │
│  Mobile (< lg)                                           │
│  ┌──────────────────┐                                    │
│  │   Chessboard     │                                    │
│  │  [Control Bar]   │                                    │
│  ├──────────────────┤                                    │
│  │  RepertoireSelect│                                    │
│  │  OpeningTree     │                                    │
│  │  NodeDetails     │                                    │
│  └──────────────────┘                                    │
└─────────────────────────────────────────────────────────┘
```

### Page Component Structure

```typescript
'use client';

import dynamic from 'next/dynamic';

// Dynamic imports to avoid SSR issues with chess.js / react-chessboard / useLocalStorage
const DebutBoard = dynamic(() => import('@/components/openings/DebutBoard'), { ssr: false });
const RepertoireSelector = dynamic(() => import('@/components/openings/RepertoireSelector'), { ssr: false });
const OpeningTree = dynamic(() => import('@/components/openings/OpeningTree'), { ssr: false });
const NodeDetailsPanel = dynamic(() => import('@/components/openings/NodeDetailsPanel'), { ssr: false });
const PgnImporter = dynamic(() => import('@/components/openings/PgnImporter'), { ssr: false });
const GameSearchPanel = dynamic(() => import('@/components/openings/GameSearchPanel'), { ssr: false });

export default function DebutPage() {
  // Auth check
  // Hook: useOpeningRepertoire()
  // State: selectedRepertoireId, selectedNode, boardFen, boardOrientation
  // State: pgnImporterOpen, gameSearchOpen
  
  // Effects: fetch repertoires on mount, fetch tree when repertoire selected
  // Handler: onNodeSelect → set board FEN
  // Handler: onMoveOnBoard → add node to tree
  // Handler: navigation (prev/next/start/end) through tree siblings/children
  
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', backgroundColor: '#1a1a1a' }}>
      {/* Left: Board */}
      <Box sx={{ flex: '0 0 auto' }}>
        <DebutBoard ... />
      </Box>
      
      {/* Right: Tree + Details */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <RepertoireSelector ... />
        <OpeningTree ... />
        <NodeDetailsPanel ... />
      </Box>
      
      {/* Modals */}
      <PgnImporter ... />
      <GameSearchPanel ... />
    </Box>
  );
}
```

### 5.1 `DebutBoard.tsx` — Dedicated Board Component

**File:** `/root/chess-app/frontend/src/components/openings/DebutBoard.tsx`  
**Complexity:** MEDIUM — ~200-300 lines (simplified version of AiChessboard)

**Props Interface:**
```typescript
interface DebutBoardProps {
  fen: string;
  orientation: 'white' | 'black';
  onMove: (from: string, to: string, newFen: string) => void;
  customArrows?: Arrow[];
  customSquareStyles?: Record<string, React.CSSProperties>;
  onFlip: () => void;
}
```

**What to reuse from `AiChessboard`:**
- Board rendering with `react-chessboard`
- ChessBase theme + Fritz pieces (same `useLocalStorage` keys)
- CB-style SVG control bar icons (reset, start, prev, next, end, flip)
- Responsive sizing logic
- Coordinate toggle from settings

**What to NOT include:**
- Stockfish integration
- Eval bar
- FEN input field
- Photo-to-FEN
- Settings dialog (board already uses shared localStorage settings)
- Editor mode
- Game review mode

**Control bar behavior in Debut context:**
- **Reset:** Go to repertoire starting position
- **Start:** Go to root node of tree
- **Prev:** Go to parent node in tree
- **Next:** Go to first child node (or next sibling?)
- **End:** Go to deepest node in main line
- **Flip:** Toggle board orientation

### State Management in Debut Page

```typescript
// Core state
const [selectedRepertoireId, setSelectedRepertoireId] = useState<string | null>(null);
const [selectedNode, setSelectedNode] = useState<OpeningNode | null>(null);
const [boardFen, setBoardFen] = useState('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
const [boardOrientation, setBoardOrientation] = useState<'white' | 'black'>('white');

// Derived from hook
const {
  repertoires, currentTree, loading, treeLoading,
  fetchRepertoires, fetchTree, addNode, updateNode, deleteNode,
  importPgn, exportPgn, addArrow, deleteArrow,
  searchGames, searchGamesStream, linkGame, getNodeGames, deleteGameLink,
} = useOpeningRepertoire();

// Effects
useEffect(() => { fetchRepertoires(); }, []);
useEffect(() => {
  if (selectedRepertoireId) {
    fetchTree(selectedRepertoireId);
    // Set board orientation based on repertoire color
    const rep = repertoires.find(r => r.id === selectedRepertoireId);
    if (rep) setBoardOrientation(rep.color === 'b' ? 'black' : 'white');
  }
}, [selectedRepertoireId]);

// When user clicks a tree node
const handleNodeSelect = (node: OpeningNode) => {
  setSelectedNode(node);
  setBoardFen(node.fen);
};

// When user makes a move on board
const handleBoardMove = async (from: string, to: string, newFen: string) => {
  if (!selectedNode) return;
  // Check if this move already exists as a child
  const existingChild = selectedNode.children?.find(c => c.fen === newFen);
  if (existingChild) {
    handleNodeSelect(existingChild);
  } else {
    // Add new node
    const newNode = await addNode(selectedNode.id, moveSan, moveUci, newFen);
    await fetchTree(selectedRepertoireId!);
    handleNodeSelect(newNode);
  }
};
```

---

## Phase 6 — Navigation Integration

**Complexity:** LOW — ~30 min of work

### 6.1 Bottom Navigation

**File to modify:** `/root/chess-app/frontend/src/components/ui/BottomNavigation.tsx`

**Changes:**
1. Replace the `learn` nav item with `debut`:

```typescript
// Change in NavItem interface
labelKey: 'home' | 'debut' | 'puzzles' | 'analyze' | 'profile';

// Replace the learn entry in navItems array:
{
  href: '/debut',
  labelKey: 'debut',
  icon: (
    // Chess opening book icon (outline)
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
    </svg>
  ),
  activeIcon: (
    // Same icon but filled
    <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
      <path d="M11.25 4.533A9.707 9.707 0 006 3a9.735 9.735 0 00-3.25.555.75.75 0 00-.5.707v14.25a.75.75 0 001 .707A8.237 8.237 0 016 18.75c1.995 0 3.823.707 5.25 1.886V4.533zM12.75 20.636A8.214 8.214 0 0118 18.75c.966 0 1.89.166 2.75.47a.75.75 0 001-.708V4.262a.75.75 0 00-.5-.707A9.735 9.735 0 0018 3a9.707 9.707 0 00-5.25 1.533v16.103z" />
    </svg>
  ),
},
```

> **Note:** The book icon is already the exact same SVG as the current "Learn" icon. This is intentional — it represents study/learning which matches "Debut" (opening study). Could also use a chess knight or custom opening-book icon if preferred.

2. Update `isActive` to handle `/debut`:
```typescript
const isActive = (href: string) => {
  if (!pathname) return false;
  if (href === '/dashboard') return pathname === '/' || pathname === '/dashboard';
  if (href === '/debut') return pathname.startsWith('/debut');
  return pathname.startsWith(href);
};
```

### 6.2 i18n Translations

**Files to modify:**
- `/root/chess-app/frontend/messages/en.json`
- `/root/chess-app/frontend/messages/ru.json`
- `/root/chess-app/frontend/messages/kk.json`

**Keys to add/modify:**

**`en.json` changes:**
```json
{
  "navigation": {
    "home": "Home",
    "debut": "Debut",
    "puzzles": "Puzzles",
    "analyze": "Analyze",
    "profile": "Profile"
  },
  "debut": {
    "title": "My Openings",
    "subtitle": "Build and study your opening repertoire",
    "newRepertoire": "New Repertoire",
    "selectRepertoire": "Select a repertoire",
    "noRepertoires": "No repertoires yet. Create your first one!",
    "repertoireName": "Repertoire Name",
    "colorWhite": "White",
    "colorBlack": "Black",
    "create": "Create",
    "rename": "Rename",
    "delete": "Delete",
    "deleteConfirm": "Delete this repertoire and all its moves?",
    "importPgn": "Import PGN",
    "exportPgn": "Export PGN",
    "tree": {
      "expandAll": "Expand All",
      "collapseAll": "Collapse All",
      "emptyTree": "No moves yet. Make a move on the board to start building your repertoire.",
      "legend": {
        "critical": "Critical position",
        "needsReview": "Needs review",
        "mastered": "Mastered"
      }
    },
    "node": {
      "opening": "Opening",
      "move": "Move",
      "notes": "Notes",
      "notesPlaceholder": "Add notes about this position...",
      "save": "Save",
      "cancel": "Cancel",
      "markCritical": "Mark Critical",
      "unmarkCritical": "Unmark Critical",
      "deleteMove": "Delete Move",
      "deleteMoveConfirm": "Delete this move and all child moves?",
      "searchGames": "Search Games",
      "training": {
        "untrained": "Untrained",
        "mastered": "Mastered",
        "dueForReview": "Due for Review",
        "accuracy": "Accuracy",
        "timesTrained": "Times Trained",
        "nextReview": "Next Review"
      }
    },
    "pgn": {
      "title": "Import PGN",
      "paste": "Paste your PGN here...",
      "loadExample": "Load Example",
      "maxPly": "Max Ply Depth",
      "import": "Import",
      "importing": "Importing...",
      "importMore": "Import More",
      "imported": "imported",
      "skipped": "skipped",
      "errors": "errors",
      "info": "Variations will be imported as separate branches. Duplicate positions are automatically skipped."
    },
    "games": {
      "title": "Search Games",
      "source": "Source",
      "internal": "TWIC Database",
      "lichess": "Lichess",
      "chesscom": "Chess.com",
      "username": "Username",
      "minRating": "Min Rating",
      "search": "Search",
      "searching": "Searching...",
      "checked": "Checked {count} games",
      "found": "Found {count} matches",
      "noResults": "No games found for this position",
      "linkToPosition": "Link to Position",
      "viewPgn": "View PGN"
    },
    "signInRequired": "Sign in to manage your opening repertoire"
  }
}
```

**`ru.json` changes:**
```json
{
  "navigation": {
    "debut": "Дебют"
  },
  "debut": {
    "title": "Мои дебюты",
    "subtitle": "Создавайте и изучайте свой дебютный репертуар",
    "newRepertoire": "Новый репертуар",
    "selectRepertoire": "Выберите репертуар",
    "noRepertoires": "Репертуаров пока нет. Создайте первый!",
    "repertoireName": "Название репертуара",
    "colorWhite": "Белые",
    "colorBlack": "Чёрные",
    "create": "Создать",
    "rename": "Переименовать",
    "delete": "Удалить",
    "deleteConfirm": "Удалить этот репертуар и все его ходы?",
    "importPgn": "Импорт PGN",
    "exportPgn": "Экспорт PGN",
    "tree": {
      "expandAll": "Развернуть все",
      "collapseAll": "Свернуть все",
      "emptyTree": "Ходов пока нет. Сделайте ход на доске, чтобы начать.",
      "legend": {
        "critical": "Критическая позиция",
        "needsReview": "Требует повторения",
        "mastered": "Освоено"
      }
    },
    "node": {
      "opening": "Дебют",
      "move": "Ход",
      "notes": "Заметки",
      "notesPlaceholder": "Добавьте заметки о позиции...",
      "save": "Сохранить",
      "cancel": "Отмена",
      "markCritical": "Отметить как критическую",
      "unmarkCritical": "Снять отметку",
      "deleteMove": "Удалить ход",
      "deleteMoveConfirm": "Удалить этот ход и все дочерние ходы?",
      "searchGames": "Поиск партий",
      "training": {
        "untrained": "Не изучено",
        "mastered": "Освоено",
        "dueForReview": "Требует повторения",
        "accuracy": "Точность",
        "timesTrained": "Количество тренировок",
        "nextReview": "Следующее повторение"
      }
    },
    "pgn": {
      "title": "Импорт PGN",
      "paste": "Вставьте PGN...",
      "loadExample": "Загрузить пример",
      "maxPly": "Максимальная глубина",
      "import": "Импортировать",
      "importing": "Импорт...",
      "importMore": "Импортировать ещё",
      "imported": "импортировано",
      "skipped": "пропущено",
      "errors": "ошибок",
      "info": "Варианты будут импортированы как отдельные ветви. Дублирующиеся позиции пропускаются автоматически."
    },
    "games": {
      "title": "Поиск партий",
      "source": "Источник",
      "internal": "База TWIC",
      "lichess": "Lichess",
      "chesscom": "Chess.com",
      "username": "Имя пользователя",
      "minRating": "Мин. рейтинг",
      "search": "Поиск",
      "searching": "Поиск...",
      "checked": "Проверено {count} партий",
      "found": "Найдено {count} совпадений",
      "noResults": "Партий для этой позиции не найдено",
      "linkToPosition": "Привязать к позиции",
      "viewPgn": "Показать PGN"
    },
    "signInRequired": "Войдите, чтобы управлять дебютным репертуаром"
  }
}
```

**`kk.json` changes:**
```json
{
  "navigation": {
    "debut": "Дебют"
  },
  "debut": {
    "title": "Менің дебюттерім",
    "subtitle": "Дебюттік репертуарыңызды құрыңыз және зерттеңіз",
    "newRepertoire": "Жаңа репертуар",
    "selectRepertoire": "Репертуарды таңдаңыз",
    "noRepertoires": "Репертуар жоқ. Біріншісін жасаңыз!",
    "repertoireName": "Репертуар атауы",
    "colorWhite": "Ақ",
    "colorBlack": "Қара",
    "create": "Жасау",
    "rename": "Атын өзгерту",
    "delete": "Жою",
    "deleteConfirm": "Бұл репертуарды және барлық жүрістерді жою?",
    "importPgn": "PGN импорты",
    "exportPgn": "PGN экспорты",
    "tree": {
      "expandAll": "Барлығын ашу",
      "collapseAll": "Барлығын жабу",
      "emptyTree": "Жүрістер жоқ. Репертуарды бастау үшін тақтада жүріс жасаңыз.",
      "legend": {
        "critical": "Маңызды позиция",
        "needsReview": "Қайталау қажет",
        "mastered": "Меңгерілген"
      }
    },
    "node": {
      "opening": "Дебют",
      "move": "Жүріс",
      "notes": "Жазбалар",
      "notesPlaceholder": "Позиция туралы жазба қосыңыз...",
      "save": "Сақтау",
      "cancel": "Бас тарту",
      "markCritical": "Маңызды деп белгілеу",
      "unmarkCritical": "Белгіні алу",
      "deleteMove": "Жүрісті жою",
      "deleteMoveConfirm": "Бұл жүрісті және барлық бала жүрістерді жою?",
      "searchGames": "Партия іздеу",
      "training": {
        "untrained": "Оқытылмаған",
        "mastered": "Меңгерілген",
        "dueForReview": "Қайталау қажет",
        "accuracy": "Дәлдік",
        "timesTrained": "Жаттығу саны",
        "nextReview": "Келесі қайталау"
      }
    },
    "pgn": {
      "title": "PGN импорты",
      "paste": "PGN қойыңыз...",
      "loadExample": "Мысал жүктеу",
      "maxPly": "Максималды тереңдік",
      "import": "Импорттау",
      "importing": "Импорттау...",
      "importMore": "Тағы импорттау",
      "imported": "импортталды",
      "skipped": "өткізілді",
      "errors": "қателер",
      "info": "Нұсқалар бөлек тармақтар ретінде импортталады. Қайталанатын позициялар автоматты түрде өткізіледі."
    },
    "games": {
      "title": "Партия іздеу",
      "source": "Дереккөз",
      "internal": "TWIC базасы",
      "lichess": "Lichess",
      "chesscom": "Chess.com",
      "username": "Пайдаланушы аты",
      "minRating": "Мин. рейтинг",
      "search": "Іздеу",
      "searching": "Іздеу...",
      "checked": "{count} партия тексерілді",
      "found": "{count} сәйкестік табылды",
      "noResults": "Бұл позиция бойынша партия табылмады",
      "linkToPosition": "Позицияға байланыстыру",
      "viewPgn": "PGN көру"
    },
    "signInRequired": "Дебюттік репертуарды басқару үшін кіріңіз"
  }
}
```

### 6.3 Route Configuration

**File to check/create:** `/root/chess-app/frontend/src/app/debut/page.tsx` (already covered in Phase 5)

The Next.js App Router auto-creates the route based on the directory structure. No additional routing config needed.

**Optional:** If `/learn` should redirect to `/debut`, add:
```typescript
// /root/chess-app/frontend/src/app/learn/page.tsx — add redirect
// OR keep the existing learn page as-is (it still works independently)
```

---

## Phase 7 — Polish & Testing

**Complexity:** MEDIUM

### 7.1 Mobile Responsiveness

- **Board sizing:** Use same responsive logic as `AiChessboard` (`windowWidth` breakpoints)
  - `< 400px`: board = `windowWidth - 40`
  - `< 600px`: board = `windowWidth - 32`
  - `< 768px`: board = `windowWidth - 48`
- **Layout:** Stack vertically on `< lg` breakpoints
- **Tree view:** Full width on mobile, scrollable
- **Node details:** Collapsible accordion on mobile
- **Bottom nav spacer:** Ensure content isn't hidden behind nav bar
- **Touch targets:** Min 44px for tree node tap targets

### 7.2 Board Arrow Rendering

- Arrows from `opening_arrows` table should render on the board
- Map to `react-chessboard` Arrow type: `[fromSquare, toSquare, color]`
- Different colors: green (main line), blue (alternative), red (avoid), yellow (interesting)

### 7.3 Theme Consistency

- Use same dark theme (`#1a1a1a` background, `purpleTheme`)
- Same board theme settings from localStorage (`board_theme`, `board_piece_type`)
- Same control bar SVG icons (`CBResetIcon`, `CBGoToStartIcon`, etc.)

### 7.4 Error Handling

- API failures: Show toast/snackbar with error message
- Network errors: Retry button
- Auth failures: Redirect to sign-in
- Invalid FEN: Show warning, don't crash

---

## File Inventory

### Files to CREATE (11 files)

| # | File Path | Phase | Lines (est.) |
|---|-----------|-------|-------------|
| 1 | `backend/api/openings.py` | 2 | ~1000 |
| 2 | `frontend/src/hooks/useOpeningRepertoire.ts` | 3 | ~350 |
| 3 | `frontend/src/components/openings/RepertoireSelector.tsx` | 4 | ~200 |
| 4 | `frontend/src/components/openings/OpeningTree.tsx` | 4 | ~350 |
| 5 | `frontend/src/components/openings/NodeDetailsPanel.tsx` | 4 | ~300 |
| 6 | `frontend/src/components/openings/PgnImporter.tsx` | 4 | ~250 |
| 7 | `frontend/src/components/openings/GameSearchPanel.tsx` | 4 | ~300 |
| 8 | `frontend/src/components/openings/DebutBoard.tsx` | 5 | ~300 |
| 9 | `frontend/src/app/debut/page.tsx` | 5 | ~400 |
| 10 | `frontend/src/components/openings/index.ts` | 4 | ~10 |
| **Total** | | | **~3,460** |

### Files to MODIFY (5 files)

| # | File Path | Phase | Changes |
|---|-----------|-------|---------|
| 1 | `backend/app.py` | 2 | Add openings blueprint import + register (~5 lines) |
| 2 | `frontend/src/components/ui/BottomNavigation.tsx` | 6 | Replace 'learn' with 'debut' in navItems + labelKey type |
| 3 | `frontend/messages/en.json` | 6 | Add `"debut"` section + update `navigation.learn` → `navigation.debut` |
| 4 | `frontend/messages/ru.json` | 6 | Add `"debut"` section + update `navigation.learn` → `navigation.debut` |
| 5 | `frontend/messages/kk.json` | 6 | Add `"debut"` section + update `navigation.learn` → `navigation.debut` |

### Files NOT Changed (reference only)

- `frontend/src/app/learn/page.tsx` — Keep as-is (learn page still accessible via URL)
- `frontend/src/app/position/page.tsx` — Keep as-is (no tabs added)
- `frontend/src/components/analysis/AiChessboard.tsx` — Reference only for DebutBoard

---

## Complexity Estimates

| Phase | Description | Estimated Time | Difficulty | Dependencies |
|-------|-------------|---------------|------------|--------------|
| 1 | Database | 0h (done) | — | — |
| 2 | Backend API (`openings.py`) | 4-6h | HIGH | Phase 1 |
| 3 | Frontend Hook | 2-3h | MEDIUM | Phase 2 |
| 4 | UI Components (5 components) | 5-7h | HIGH | Phase 3 |
| 5 | Debut Page + DebutBoard | 3-4h | HIGH | Phase 4 |
| 6 | Navigation + i18n | 0.5-1h | LOW | Phase 5 |
| 7 | Polish + Testing | 2-3h | MEDIUM | Phase 6 |
| **Total** | | **16.5-24h** | | |

### Recommended Implementation Order

1. **Phase 2** (Backend) — Can be fully tested independently via curl/Postman
2. **Phase 3** (Hook) — Depends on backend being live
3. **Phase 6** (Nav + i18n) — Quick win, can be done alongside Phase 4
4. **Phase 5** (Page skeleton) — Create page with empty layout
5. **Phase 4** (Components) — Build components one at a time:
   - RepertoireSelector first (simple, enables testing flow)
   - DebutBoard (from Phase 5) next (need to see the board)
   - OpeningTree (core feature)
   - NodeDetailsPanel (requires tree to be working)
   - PgnImporter (independent modal)
   - GameSearchPanel (last, most complex)
6. **Phase 7** (Polish)

### Bytecode Recovery Note

The `.pyc` file at `backend/api/__pycache__/openings.cpython-312.pyc` contains the complete original code in bytecode form. The dis analysis above captured:
- All 40+ function names and their argument signatures
- All string constants (SQL table names, error messages, API URLs, docstrings)
- All imported modules and method calls
- All variable names used in each function

This is sufficient to reconstruct the entire API. A developer could also try:
- `pip install decompyle3` or `uncompyle6` (may not support 3.12)
- Use `pycdc` (C++ decompiler) if available
- Manual reconstruction from the dis output (recommended — all the data is there)

---

## Appendix: Bytecode-Recovered Function Signatures

Extracted from `openings.cpython-312.pyc` via Python's `marshal` + `types.CodeType`:

```
build_tree(nodes)
detect_opening(fen)
detect_eco_for_search(fen)
validate_move(fen, move_san)
create_default_repertoires(user_id)
list_repertoires()
create_repertoire()
get_repertoire(repertoire_id)
build_pgn_moves(tree, include_notes) → nested: traverse(node, is_main, force_move_number)
generate_repertoire_pgn(repertoire, tree, eco_info, include_notes)
export_repertoire_pgn(repertoire_id)
update_repertoire(repertoire_id)
update_starting_position(repertoire_id)
delete_repertoire(repertoire_id)
add_node()
update_node(node_id)
delete_node(node_id)
add_arrow(node_id)
delete_arrow(node_id, arrow_id)
get_due_nodes()
record_training_result()
get_training_stats()
get_node_games(node_id)
link_game_to_node(node_id)
delete_game_link(game_link_id)
search_games()
fetch_lichess_games(username, since, max_games, filter_fen)
fetch_chesscom_games(username, since, max_games, filter_fen)
check_game_reaches_fen(pgn_text, target_fen, debug_game_id)
get_internal_db_connection()
check_internal_db_exists()
fetch_internal_games(search_query, max_games, filter_fen, eco_filter)
internal_db_status()
import_pgn(repertoire_id) → nested: get_or_create_node(), import_game_node(), import_variation()
fetch_internal_games_progressive(filter_fen, eco_filter, min_rating, max_games, stop_after)
fetch_lichess_games_progressive(username, filter_fen, min_rating, max_games)
fetch_chesscom_games_progressive(username, filter_fen, min_rating, max_games)
search_games_stream() → nested: generate()
find_moves_to_fen(target_fen, max_depth)
repair_repertoire_tree(repertoire_id)
```

All route decorators recovered:
```
/repertoires                    [GET, POST]
/repertoires/<repertoire_id>    [GET, PUT, DELETE]
/repertoires/<repertoire_id>/pgn          [GET]
/repertoires/<repertoire_id>/starting-position  [PUT]
/repertoires/<repertoire_id>/import       [POST]
/repertoires/<repertoire_id>/repair-tree  [POST]
/nodes                          [POST]
/nodes/<node_id>                [PUT, DELETE]
/nodes/<node_id>/arrows         [POST]
/nodes/<node_id>/arrows/<arrow_id>  [DELETE]
/training/due                   [GET]
/training/result                [POST]
/training/stats                 [GET]
/nodes/<node_id>/games          [GET, POST]
/games/<game_link_id>           [DELETE]
/games/search                   [GET]
/games/search/stream            [GET]
/games/internal/status          [GET]
```
