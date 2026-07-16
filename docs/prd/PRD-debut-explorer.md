# PRD: Multi-Source Opening Explorer for /debut Page

**Project:** Chesster (chesster.io)
**Page:** `/debut` — Opening Repertoire Builder
**Date:** 2026-03-17
**Status:** Approved — Ready for Implementation

---

## Summary

Add Lichess Opening Explorer and Chess.com player search as additional data sources to the `/debut` page's existing TWIC master games panel. Users can browse games from three sources (TWIC, Lichess, Chess.com) via sub-tabs, and switch the Move Tree's statistical source between Masters (TWIC), Lichess Masters, and Lichess Players.

---

## Decisions Log (Q1–Q18)

| # | Question | Decision |
|---|----------|----------|
| Q1 | Chess.com position search? | No. Lichess only for position search. Chess.com tab for player search only. |
| Q2 | Lichess tab layout? | A) Same layout as TWIC — move stats table + filterable games list |
| Q3 | Chess.com tab on position change? | A) Show "Position search not available for Chess.com" with player search form |
| Q4 | Lichess Masters vs Players DB? | B) Both Masters + Lichess Players as sub-tabs |
| Q5 | Auto-fetch on position change? | A) Auto-fetch immediately |
| Q6 | Tab ordering? | A) `TWIC` \| `Lichess` \| `Chess.com` |
| Q7 | Clicking a Lichess game? | A) Open in built-in GameViewerPanel |
| Q8 | Rate limiting / caching? | B) Server-side proxy with caching — **DONE** (deployed `explorer-cache.ts`) |
| Q9 | Chess.com player search data loading? | C) Progressive loading — most recent month first, background-fetch older months |
| Q10 | Chess.com proxy vs direct? | A) Server-side proxy (same pattern as Lichess) |
| Q11 | Game viewer for Chess.com games? | C) GameViewerPanel with source badge (Lichess/Chess.com/TWIC) |
| Q12 | Empty states / loading UX? | C) Progressive reveal — show structure immediately, fill data as it arrives |
| Q13 | Error handling? | A) Inline error + retry button per tab. Other tabs keep working. |
| Q14 | Mobile responsiveness? | A) Horizontal scrollable tab pills + card layout (one game per card) on mobile |
| Q15 | Data persistence? | B+C) Session storage for cache + URL state for shareability (`?tab=lichess&db=masters`) |
| Q16 | Tab structure on /debut? | A) Sub-tabs inside existing Master Games panel: `TWIC \| Lichess \| Chess.com` |
| Q17 | Move Tree enrichment? | C) Switchable source toggle — "Masters (TWIC)" / "Lichess Masters" / "Lichess Players" |
| Q18 | Implementation phasing? | C) Three phases |

---

## Architecture

### Current State

```
/debut page
├── DebutBoard (interactive chessground)
├── RepertoireSelector (CRUD repertoires)
├── MoveTree (candidate moves from TWIC — SAN, games, %, W/D/L, AvElo, AvYear)
├── PositionSummary (ECO code, opening name, aggregate W/D/L)
├── NodeDetailsPanel ("Master Games" — TWIC games for current position)
│   └── MasterGamesFilter (player name, opponent, color, sort)
├── GameSearchPanel (modal — search TWIC/Lichess/Chess.com, link games to nodes)
├── GameViewerPanel (tabs for opened games)
└── MoveNotation
```

### Target State

```
/debut page
├── DebutBoard (unchanged)
├── RepertoireSelector (unchanged)
├── MoveTree (candidate moves — switchable source: TWIC / Lichess Masters / Lichess Players)
│   └── Source toggle dropdown
├── PositionSummary (unchanged)
├── NodeDetailsPanel → renamed to "Games Explorer"
│   ├── Sub-tab: TWIC (existing master games, same layout)
│   ├── Sub-tab: Lichess (position search — Masters + Players sub-tabs)
│   │   ├── Auto-fetch on position change
│   │   ├── Move stats table + filterable games list
│   │   └── Masters / Players toggle
│   └── Sub-tab: Chess.com (player search only)
│       ├── Username input + search
│       ├── Progressive loading (recent month first, background-fetch older)
│       └── "Position search not available" notice
├── GameViewerPanel (opens games from any source — with source badge)
└── MoveNotation (unchanged)
```

### Data Flow

```
Board position changes (FEN)
  ├─→ TWIC tab: fetchGamesByPosition(fen) → backend SQLite query (existing)
  ├─→ Lichess tab: /api/explorer/masters?fen=... → explorer-cache → Lichess API
  │   └─→ /api/explorer/lichess?fen=... (Players sub-tab)
  └─→ Chess.com tab: no auto-fetch (player search only)
        └─→ User enters username → /api/chesscom/player/{username}/games → Chess.com API

Move Tree source toggle
  ├─→ "Masters (TWIC)": fetchCandidateMoves(fen) → backend (existing)
  ├─→ "Lichess Masters": /api/explorer/masters?fen=... → parse top moves
  └─→ "Lichess Players": /api/explorer/lichess?fen=... → parse top moves
```

### Server-Side Infrastructure (Q8 — DONE)

Already deployed in `explorer-cache.ts`:
- **LRU Cache:** 2000 entries, 6-hour TTL, stale-while-revalidate
- **Token Bucket Rate Limiter:** 10 req/s with async queue
- **Circuit Breaker:** 5 failures / 30s → 60s cooldown, half-open recovery
- **Proxy route:** `/api/explorer/[...path]/route.ts`

Needs to be added:
- **Chess.com proxy route:** `/api/chesscom/[...path]/route.ts` (same cache/rate-limit pattern)

---

## Phase 1: Lichess Position Search + Move Tree Toggle

### Scope
- Lichess sub-tab in the games panel with Masters + Players toggle
- Auto-fetch on position change (FEN)
- Move stats table matching TWIC layout (move, games, %, W/D/L bar, avg elo)
- Filterable games list below stats
- Click game → open in GameViewerPanel
- Move Tree source toggle: TWIC / Lichess Masters / Lichess Players
- Session storage cache (browser-side)
- URL state: `?tab=lichess&db=masters`
- Progressive reveal loading UX
- Inline error with retry button
- Source badge on GameViewerPanel

### Files to Create/Modify

**New files:**
- `src/components/openings/ExplorerTabs.tsx` — Tab container with TWIC | Lichess | Chess.com sub-tabs
- `src/components/openings/LichessExplorerTab.tsx` — Lichess position search UI (Masters/Players toggle, stats table, games list)
- `src/components/openings/SourceBadge.tsx` — Small badge component (TWIC/Lichess/Chess.com)
- `src/hooks/useLichessExplorer.ts` — Hook for fetching/caching Lichess explorer data
- `src/lib/explorer-session-cache.ts` — Browser sessionStorage cache layer

**Modified files:**
- `src/app/debut/page.tsx` — Integrate ExplorerTabs, URL state params, source toggle state
- `src/components/openings/MoveTree.tsx` — Add source toggle dropdown, accept external candidate data
- `src/components/openings/NodeDetailsPanel.tsx` — Wrap in ExplorerTabs, pass TWIC content as first tab
- `src/components/openings/GameViewerPanel.tsx` — Add source badge
- `src/app/api/explorer/[...path]/route.ts` — Already done (cache/rate-limit)

### Lichess API Endpoints Used
- `GET /api/explorer/masters?fen={fen}&topGames=15&moves=12` — Masters database
- `GET /api/explorer/lichess?fen={fen}&ratings=2200,2500&speeds=rapid,classical&topGames=15&moves=12` — Lichess players database

### Move Tree Source Toggle Behavior
- Default: "Masters (TWIC)" — uses existing `fetchCandidateMoves()` backend call
- "Lichess Masters" — parses `/api/explorer/masters` response `moves[]` array into `MoveCandidate` format
- "Lichess Players" — parses `/api/explorer/lichess` response `moves[]` array
- Toggle is a small dropdown/select next to the "Move Tree" header
- Switching source re-renders the table with new stats (no page reload)

### URL State
- `?explorer=lichess` or `?explorer=twic` or `?explorer=chesscom`
- `?db=masters` or `?db=players` (for Lichess sub-tab)
- Read on mount, update on tab/toggle change via `window.history.replaceState`

---

## Phase 2: Chess.com Player Search + Proxy

### Scope
- Chess.com sub-tab with player username search
- Server-side proxy with cache + rate limiting (same pattern as Lichess)
- Progressive loading: fetch most recent month first, display immediately, background-fetch older months
- Client-side filtering by time control + rating range
- Click game → open in GameViewerPanel with Chess.com source badge
- "Position search not available for Chess.com" notice when no username entered

### Files to Create/Modify

**New files:**
- `src/components/openings/ChessComExplorerTab.tsx` — Chess.com player search UI
- `src/hooks/useChessComExplorer.ts` — Hook for Chess.com data fetching with progressive loading
- `src/app/api/chesscom/[...path]/route.ts` — Server-side proxy for Chess.com API
- `src/lib/chesscom-cache.ts` — Cache config for Chess.com proxy (reuse explorer-cache patterns)

**Modified files:**
- `src/components/openings/ExplorerTabs.tsx` — Add Chess.com tab content
- `src/app/debut/page.tsx` — Wire up Chess.com state

### Chess.com API Endpoints Used
- `GET /pub/player/{username}/games/{YYYY}/{MM}` — Monthly game archives
- `GET /pub/player/{username}/games/archives` — List available archive months

### Progressive Loading Flow
1. Fetch `/archives` → get list of months (e.g., `["2026/03", "2026/02", ...]`)
2. Fetch most recent month → display results immediately
3. Background-fetch remaining months (newest first), append results as they arrive
4. Client-side filter: time control dropdown (all/rapid/blitz/bullet/classical), min rating input
5. Show progress indicator: "Loaded 3 of 12 months..."

---

## Phase 3: Polish — Mobile, Session Cache, Empty States

### Scope
- Mobile responsiveness: horizontal scrollable tab pills, card layout for games on small screens
- Session storage persistence for all explorer data
- Empty state components with contextual hints
- Filters collapse into dropdown on mobile
- Final QA pass across all three tabs

### Files to Create/Modify

**New files:**
- `src/components/openings/GameCard.tsx` — Mobile-friendly card layout for a single game
- `src/components/openings/EmptyState.tsx` — Contextual empty state component

**Modified files:**
- `src/components/openings/ExplorerTabs.tsx` — Responsive tab pills (horizontal scroll on mobile)
- `src/components/openings/LichessExplorerTab.tsx` — Card layout on mobile, filter dropdown
- `src/components/openings/ChessComExplorerTab.tsx` — Card layout on mobile, filter dropdown
- `src/components/openings/NodeDetailsPanel.tsx` — Responsive adjustments
- `src/lib/explorer-session-cache.ts` — Full session storage implementation for all tabs

---

## Non-Goals

- No Chess.com position search (no public API exists)
- No Redis/external cache (single PM2 instance, in-memory sufficient)
- No changes to `/position` page (separate feature)
- No changes to TWIC import/indexing pipeline
- No Stockfish engine integration in this feature
- No user accounts/preferences for default tab selection (use URL state)

---

## Technical Notes

- **Existing infrastructure:** `explorer-cache.ts` (LRU + rate limiter + circuit breaker) — deployed and live
- **Lichess rate limit:** ~15 req/s anonymous, more with token. Our rate limiter caps at 10 req/s.
- **Chess.com rate limit:** Undocumented but they throttle aggressive clients. Same 10 req/s cap.
- **GameViewerPanel:** Already supports opening games by PGN. Source badge is additive.
- **MoveTree:** Currently takes `candidates: MoveCandidate[]` prop. Source toggle changes which data fills this prop.
- **Existing GameSearchPanel:** Modal that already searches Lichess/Chess.com/TWIC. This PRD moves that functionality inline into the tab layout (non-modal).
