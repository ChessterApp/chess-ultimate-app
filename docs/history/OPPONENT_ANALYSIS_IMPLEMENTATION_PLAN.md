# Opponent Analysis Feature - Implementation Plan

## Overview

Add a new **Opponent Analysis** function to the main Dashboard that allows users to:
1. Search for any player by name
2. View their recent games from multiple sources (Lichess, Chess.com, TWIC/OTB database)
3. See player profile information (age, federation, online accounts)
4. Analyze opening repertoire with win/loss/draw statistics

## Database Statistics

**TWIC Master Database:**
- **Total Games:** 4,316,196 games
- **File Size:** 3.6 GB
- **Format:** PGN (Portable Game Notation)

**Available Metadata Fields:**
| Field | Description | Example |
|-------|-------------|---------|
| White | White player name | "Carlsen,M" |
| Black | Black player name | "Caruana,F" |
| WhiteElo | White player rating | "2837" |
| BlackElo | Black player rating | "2777" |
| WhiteTitle | White player title | "GM" |
| BlackTitle | Black player title | "GM" |
| WhiteFideId | White FIDE ID | "1503014" |
| BlackFideId | Black FIDE ID | "2020009" |
| Result | Game result | "1-0", "0-1", "1/2-1/2" |
| Date | Game date | "2025.07.02" |
| ECO | Opening code | "C55" |
| Opening | Opening name | "Sicilian" |
| Variation | Opening variation | "Najdorf" |
| Event | Tournament name | "SuperUnited CRO Rapid 2025" |
| Site | Location | "Zagreb CRO" |
| Round | Round number | "1.2" |

---

## Implementation Steps

### Phase 1: Database Indexing (SQLite)

**Goal:** Create a searchable SQLite index from the 3.6GB PGN file for fast queries.

#### Step 1.1: Create SQLite Database Schema

```sql
-- games table for fast searching
CREATE TABLE games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    white_name TEXT NOT NULL,
    white_name_normalized TEXT NOT NULL,  -- lowercase, no spaces for search
    black_name TEXT NOT NULL,
    black_name_normalized TEXT NOT NULL,
    white_elo INTEGER,
    black_elo INTEGER,
    white_title TEXT,
    black_title TEXT,
    white_fide_id TEXT,
    black_fide_id TEXT,
    result TEXT,
    date TEXT,
    year INTEGER,
    eco TEXT,
    opening TEXT,
    variation TEXT,
    event TEXT,
    site TEXT,
    round TEXT,
    pgn_offset INTEGER,  -- byte offset in PGN file for fast retrieval
    pgn_length INTEGER   -- length of PGN text
);

-- Indexes for fast searching
CREATE INDEX idx_white_name ON games(white_name_normalized);
CREATE INDEX idx_black_name ON games(black_name_normalized);
CREATE INDEX idx_white_elo ON games(white_elo);
CREATE INDEX idx_black_elo ON games(black_elo);
CREATE INDEX idx_date ON games(date);
CREATE INDEX idx_year ON games(year);
CREATE INDEX idx_eco ON games(eco);
CREATE INDEX idx_result ON games(result);
CREATE INDEX idx_white_fide ON games(white_fide_id);
CREATE INDEX idx_black_fide ON games(black_fide_id);

-- Full-text search for player names
CREATE VIRTUAL TABLE games_fts USING fts5(
    white_name,
    black_name,
    content='games',
    content_rowid='id'
);

-- Players table for profile aggregation
CREATE TABLE players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    name_normalized TEXT NOT NULL,
    fide_id TEXT,
    title TEXT,
    highest_elo INTEGER,
    latest_elo INTEGER,
    total_games INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    first_game_date TEXT,
    last_game_date TEXT
);

CREATE INDEX idx_player_name ON players(name_normalized);
CREATE INDEX idx_player_fide ON players(fide_id);
```

#### Step 1.2: Create PGN Indexer Script

**File:** `backend/scripts/index_pgn_database.py`

```python
"""
PGN Database Indexer
Parses the TWIC master database and creates SQLite index for fast searching.
Processes ~4.3M games, estimated time: 15-30 minutes.
"""

import sqlite3
import re
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

PGN_PATH = "data/twic/twic_master_database.pgn"
DB_PATH = "data/twic/games_index.db"

def normalize_name(name: str) -> str:
    """Normalize player name for searching."""
    return name.lower().replace(",", "").replace(" ", "").strip()

def parse_headers(lines: list) -> Dict[str, str]:
    """Parse PGN headers into dictionary."""
    headers = {}
    for line in lines:
        match = re.match(r'\[(\w+)\s+"([^"]*)"\]', line)
        if match:
            headers[match.group(1)] = match.group(2)
    return headers

def index_database():
    """Main indexing function."""
    # Implementation details...
    pass
```

#### Step 1.3: Indexing Statistics Storage

**Estimated Index Size:** ~500MB SQLite database
**Indexing Time:** 15-30 minutes (one-time)

---

### Phase 2: Backend API Endpoints

**File:** `backend/api/opponent_analysis.py`

#### API Endpoints:

```
GET /api/opponent/search?q={name}&limit={20}
    Search for players by name (autocomplete)
    Returns: [{name, fide_id, title, elo, total_games}]

GET /api/opponent/{player_name}/profile
    Get player profile with aggregated stats
    Returns: {name, title, elo_history, total_games, win_rate, openings}

GET /api/opponent/{player_name}/games?
    page={1}&
    limit={20}&
    color={white|black|both}&
    result={win|loss|draw|all}&
    min_elo={0}&
    max_elo={3000}&
    min_opp_elo={0}&
    max_opp_elo={3000}&
    eco={code}&
    from_date={YYYY-MM-DD}&
    to_date={YYYY-MM-DD}

    Get filtered games for a player
    Returns: {games: [...], total, page, pages}

GET /api/opponent/{player_name}/openings?color={white|black|both}
    Get opening statistics for player
    Returns: [{eco, opening, games, wins, draws, losses, win_rate}]

GET /api/opponent/{player_name}/opponents
    Get most frequent opponents
    Returns: [{name, games, wins, draws, losses}]

GET /api/game/{game_id}/pgn
    Get full PGN for a specific game
    Returns: {pgn: "..."}
```

---

### Phase 3: Frontend Components

#### 3.1: Dashboard Integration

**File:** `frontend/src/app/dashboard/page.tsx`

Add new analysis tool card:
```tsx
{
  id: 'opponent',
  title: t('dashboard.opponentAnalysis'),
  description: t('dashboard.opponentAnalysisDesc'),
  icon: '🔍',
  href: '/opponent',
  color: 'from-orange-500 to-orange-700'
}
```

#### 3.2: New Page Structure

**File:** `frontend/src/app/opponent/page.tsx`

```
/opponent
├── PlayerSearch (autocomplete input)
├── PlayerProfile (when player selected)
│   ├── ProfileHeader (name, title, elo, federation)
│   ├── StatsOverview (games, win rate, performance)
│   ├── OnlineAccounts (lichess, chess.com links)
│   └── EloChart (rating history)
├── OpeningAnalysis
│   ├── OpeningTable (ECO, name, games, win/draw/loss)
│   └── OpeningChart (pie chart by ECO)
├── GameFilters
│   ├── ColorFilter (white/black/both)
│   ├── ResultFilter (win/loss/draw/all)
│   ├── EloRangeFilter (player & opponent)
│   ├── DateRangeFilter
│   └── ECOFilter
└── GamesList
    ├── GameCard (opponent, result, date, opening)
    └── Pagination
```

#### 3.3: Component Files

```
frontend/src/components/opponent/
├── PlayerSearch.tsx          # Autocomplete search
├── PlayerProfile.tsx         # Profile header & stats
├── OpeningAnalysis.tsx       # Opening repertoire table
├── OpeningChart.tsx          # Pie/bar chart visualization
├── GameFilters.tsx           # Filter controls
├── GamesList.tsx             # Paginated game list
├── GameCard.tsx              # Individual game display
├── OnlineAccountsCard.tsx    # Lichess/Chess.com links
└── index.ts                  # Exports
```

---

### Phase 4: External API Integration

#### 4.1: Lichess API (existing)
- Already implemented in `UserLichessGames.tsx`
- Endpoint: `https://lichess.org/api/user/{username}/games`

#### 4.2: Chess.com API (existing)
- Already implemented in `UserChessDotComGameSelect.tsx`
- Endpoint: `https://api.chess.com/pub/player/{username}/games`

#### 4.3: FIDE API (new)
- Get player profile: `https://ratings.fide.com/profile/{fide_id}`
- Web scraping may be needed (no official API)

---

## Implementation Order

### Step 1: Database Indexing (Backend)
1. Create SQLite schema
2. Write PGN parser/indexer script
3. Run indexer on TWIC database (~30 min)
4. Verify index integrity

### Step 2: Backend API (Backend)
1. Create `api/opponent_analysis.py` blueprint
2. Implement player search endpoint
3. Implement player profile endpoint
4. Implement games list with filters
5. Implement opening statistics endpoint
6. Add pagination support

### Step 3: Frontend Structure (Frontend)
1. Add dashboard card for Opponent Analysis
2. Create `/opponent` page layout
3. Implement PlayerSearch component
4. Implement PlayerProfile component

### Step 4: Filters & Games (Frontend)
1. Implement GameFilters component
2. Implement GamesList component
3. Connect to backend API
4. Add loading states and error handling

### Step 5: Opening Analysis (Frontend)
1. Implement OpeningAnalysis table
2. Add chart visualization (Chart.js/Recharts)
3. Color-coded win/draw/loss percentages

### Step 6: External Integration (Frontend)
1. Link to Lichess profile if username matches
2. Link to Chess.com profile if username matches
3. Add combined view showing games from all sources

---

## Technical Considerations

### Performance
- SQLite with proper indexes handles 4M+ games efficiently
- Use byte offsets to retrieve PGN on-demand (not stored in SQLite)
- Pagination mandatory for large result sets
- Consider Redis caching for frequent player lookups

### Search Optimization
- Normalize names for fuzzy matching (remove accents, lowercase)
- FTS5 for full-text search on player names
- Autocomplete with debounce (300ms delay)

### Data Freshness
- TWIC updates weekly
- Create script to incrementally update index
- Track last indexed TWIC issue number

---

## Estimated Effort

| Phase | Task | Estimate |
|-------|------|----------|
| 1 | SQLite schema & indexer | 2-3 hours |
| 2 | Backend API endpoints | 3-4 hours |
| 3 | Frontend page structure | 2-3 hours |
| 4 | Filters & game list | 3-4 hours |
| 5 | Opening analysis | 2-3 hours |
| 6 | External integration | 1-2 hours |
| - | Testing & polish | 2-3 hours |
| **Total** | | **15-22 hours** |

---

## Files to Create/Modify

### New Files:
```
backend/
├── scripts/index_pgn_database.py     # PGN indexer
├── api/opponent_analysis.py          # API blueprint
└── data/twic/games_index.db          # SQLite index (generated)

frontend/src/
├── app/opponent/page.tsx             # Main page
├── components/opponent/
│   ├── PlayerSearch.tsx
│   ├── PlayerProfile.tsx
│   ├── OpeningAnalysis.tsx
│   ├── GameFilters.tsx
│   ├── GamesList.tsx
│   └── GameCard.tsx
└── locales/translations.ts           # Add translations
```

### Modified Files:
```
frontend/src/app/dashboard/page.tsx   # Add opponent card
backend/app.py                        # Register blueprint
```
