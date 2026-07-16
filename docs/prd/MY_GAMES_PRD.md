# My Games — PRD

## Overview
Add a "My Games" feature to the Database page as a peer chip tab next to the existing "📖 Database" chip. Users can save, manage, and browse their own chess games.

## Architecture

### Database Table
Create `user_games` table in Supabase via the backend migration script:

```sql
CREATE TABLE IF NOT EXISTS user_games (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    white TEXT,
    black TEXT,
    white_elo INTEGER,
    black_elo INTEGER,
    result TEXT,
    date TEXT,
    event TEXT,
    eco TEXT,
    opening_name TEXT,
    pgn TEXT NOT NULL,
    notes TEXT,
    tags TEXT[] DEFAULT '{}',
    is_favorite BOOLEAN DEFAULT FALSE,
    source TEXT DEFAULT 'manual',
    deleted_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_user_games_user_id ON user_games(user_id);
CREATE INDEX idx_user_games_deleted ON user_games(deleted_at) WHERE deleted_at IS NULL;
```

### Backend API
New blueprint file: `/root/chess-app/backend/api/user_games.py`

Register in `app.py` alongside `openings_bp`.

Endpoints (all require auth via `get_user_id()` from openings.py pattern):

- `GET /api/games` — List user's games (pagination: `?page=1&per_page=20`, filters: `?q=search&result=1-0&favorite=true&tag=blitz`)
- `POST /api/games` — Create game (body: `{pgn, title?, white?, black?, ...metadata}`)
- `GET /api/games/<id>` — Get single game
- `PUT /api/games/<id>` — Update game metadata/notes/tags/favorite
- `DELETE /api/games/<id>` — Soft delete (set `deleted_at`)
- `POST /api/games/import-local` — Bulk import from localStorage format (body: `{games: SavedGameReview[]}`)

Auth pattern — copy from `openings.py`:
```python
from api.openings import get_user_id  # reuse existing auth helper
```

### Frontend

#### 1. Hook: `useUserGames.ts`
New file: `/root/chess-app/frontend/src/hooks/useUserGames.ts`

```typescript
interface UserGame {
  id: string;
  title: string | null;
  white: string;
  black: string;
  white_elo: number | null;
  black_elo: number | null;
  result: string;
  date: string | null;
  event: string | null;
  eco: string | null;
  opening_name: string | null;
  pgn: string;
  notes: string | null;
  tags: string[];
  is_favorite: boolean;
  source: string;
  created_at: string;
  updated_at: string;
}

// Methods: fetchGames, createGame, updateGame, deleteGame, importFromLocal, toggleFavorite
```

Use the same fetch pattern as `useOpeningRepertoire.ts` — `fetch()` with auth token from Clerk.

#### 2. Component: `MyGamesPanel.tsx`
New file: `/root/chess-app/frontend/src/components/openings/MyGamesPanel.tsx`

Content when "📁 My Games" chip is active:
- Search bar (by player name, title, opening)
- Filter chips: All / Favorites / By result (1-0, 0-1, 1/2) / By tag
- Game list (cards or rows): title, white vs black, result, date, source badge
- Each game card: click → opens as game tab (same as master games)
- Each game card: favorite toggle, edit button, delete button
- "+ Add Game" FAB or button at top-right
- Empty state: "No saved games yet. Add your first game!"
- localStorage migration banner (if old data detected)

#### 3. Add Game Modal
Triggered by "+ Add Game" button. Three tabs:
1. **Enter on board** — opens analysis board in entry mode, user plays moves, then saves
2. **Upload scoresheet** — reuse `ScoresheetScanner` component
3. **Import PGN** — text area to paste PGN, parse and save

For "Enter on board": reuse `AiChessboard` in a simplified mode. After entering moves, show a save form (title, players, result, date, notes).

For "Upload scoresheet": wrap existing `ScoresheetScanner`, on success → auto-fill the save form with parsed PGN.

For "Import PGN": simple textarea + parse button. Validate PGN with chess.js, extract headers, show preview, save.

#### 4. Database Page Integration (`page.tsx`)

In the chip bar area (around line 1028-1072 of `page.tsx`):

```tsx
{mode === 'repertoire' && (
  <Box sx={{ display: 'flex', gap: 0.5, overflowX: 'auto', pb: 0.5 }}>
    <Chip label={t('debutTab')} onClick={() => setActiveTab('debut')} sx={...} />
    <Chip label={t('myGamesTab')} onClick={() => setActiveTab('my-games')} sx={...} />
    {openedGames.map(g => (
      <Chip key={g.id} ... />
    ))}
  </Box>
)}
```

In the content area, when `activeTab === 'my-games'`, render `<MyGamesPanel />` instead of the repertoire content.

When a user clicks a game in MyGamesPanel, call the existing `handleOpenGame()` function to create a game tab chip (same as opening a master game from the database).

#### 5. "Save to My Games" button in GameViewerPanel
Add a small bookmark/save icon in the `GameViewerPanel.tsx` header bar. When clicked:
- Extract game metadata from current game
- Call `createGame()` from the hook
- Show snackbar "Game saved to My Games!"

#### 6. Localization
Add to all 3 locale files (`en.json`, `ru.json`, `kz.json`) under the `debut` namespace:

```json
{
  "myGamesTab": "📁 My Games",
  "myGames": {
    "title": "My Games",
    "addGame": "Add Game",
    "enterOnBoard": "Enter on Board",
    "uploadScoresheet": "Upload Scoresheet",
    "importPgn": "Import PGN",
    "noGames": "No saved games yet",
    "noGamesSubtitle": "Add your first game!",
    "savedSuccessfully": "Game saved!",
    "deletedSuccessfully": "Game deleted",
    "searchPlaceholder": "Search by player, title, opening...",
    "filterAll": "All",
    "filterFavorites": "Favorites",
    "migrateTitle": "Import old games?",
    "migrateDescription": "Found {count} games saved locally. Import them to your account?",
    "migrateButton": "Import",
    "saveTip": "Save to My Games",
    "editGame": "Edit Game",
    "deleteGame": "Delete Game",
    "confirmDelete": "Delete this game?",
    "gameDetails": "Game Details",
    "titleLabel": "Title",
    "whiteName": "White",
    "blackName": "Black",
    "resultLabel": "Result",
    "dateLabel": "Date",
    "eventLabel": "Event",
    "notesLabel": "Notes",
    "tagsLabel": "Tags",
    "save": "Save",
    "cancel": "Cancel"
  }
}
```

Russian and Kazakh translations should follow.

## Checklist
- [x] Create backend migration script for `user_games` table
- [x] Create `/api/games` blueprint with CRUD + import endpoints
- [x] Register blueprint in `app.py`
- [x] Create `useUserGames.ts` frontend hook
- [x] Create `MyGamesPanel.tsx` component with game list, search, filters
- [x] Create Add Game modal with 3 input methods (board, scoresheet, PGN)
- [x] Integrate "📁 My Games" chip tab into Database page
- [x] Add "Save to My Games" bookmark button in GameViewerPanel
- [x] Add localization strings (EN, RU, KZ)
- [x] Test: create game via PGN import, verify it appears in list
- [x] Test: open saved game as tab, verify game viewer works
- [x] Test: save game from GameViewerPanel bookmark button
- [x] Test: localStorage migration flow
- [x] Git commit and push
