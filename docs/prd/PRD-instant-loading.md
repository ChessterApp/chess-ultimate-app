# PRD: Chesster Instant Loading Architecture
## Whop-Style Local-First Sync Engine for chesster.io

**Author:** clawdbot | **Date:** 2026-04-15 | **Status:** Draft

---

## 1. Problem Statement

Chesster pages load in 200-800ms due to network-dependent data fetching on every navigation. Every page transition triggers fresh API calls to the Flask backend and Supabase. Users see loading spinners between pages, especially on the data-heavy openings explorer, dashboard, and game analysis pages.

**Target:** Sub-50ms page transitions for all pages. Zero loading spinners after initial app load.

---

## 2. Architecture Overview (Whop Pattern Adapted for Chesster)

### What Whop Does
1. On app launch → observe local SQLite DB → render sidebar instantly
2. Background task → fetch snapshots for each "whop" section in a prioritized queue (most-used first)
3. On click → render from snapshot → then stream live data from local DB

### What Chesster Will Do
1. On app launch → PowerSync streams user data into browser SQLite (OPFS) → TanStack DB provides sub-ms reactive queries
2. Background prefetch → priority queue loads: dashboard data → last-visited page → most-used pages → everything else
3. On navigation → render instantly from local SQLite → background sync keeps data fresh
4. Lite offline → cached data renders without network; "You're offline" banner; no write queue

### Architecture Diagram
```
┌─────────────────────────────────────────────────────────┐
│                    BROWSER (Client)                      │
│                                                          │
│  ┌──────────┐    ┌─────────────┐    ┌────────────────┐  │
│  │ React UI │◄──►│ TanStack DB │◄──►│ PowerSync SDK  │  │
│  │ (hooks)  │    │ (sub-ms     │    │ (wa-sqlite +   │  │
│  │          │    │  reactive)  │    │  OPFS worker)  │  │
│  └──────────┘    └─────────────┘    └───────┬────────┘  │
│                                             │            │
│  ┌──────────────────┐  ┌────────────────┐   │            │
│  │ Service Worker   │  │ Prefetch Queue │   │            │
│  │ (API cache:      │  │ (Whop-style    │   │            │
│  │  Lichess, SF,    │  │  prioritized)  │   │            │
│  │  Chess.com)      │  │               │   │            │
│  └──────────────────┘  └────────────────┘   │            │
└─────────────────────────────────────────────┼────────────┘
                                              │ WebSocket/RSocket
                                              ▼
                                    ┌──────────────────┐
                                    │  PowerSync Cloud │
                                    │  (sync service)  │
                                    └────────┬─────────┘
                                             │ CDC (WAL)
                                             ▼
                                    ┌──────────────────┐
                                    │    Supabase      │
                                    │   PostgreSQL     │
                                    └──────────────────┘
```

---

## 3. Technology Stack

| Component | Tool | Why |
|-----------|------|-----|
| Sync engine | **PowerSync Cloud** (@powersync/web) | Built for Supabase. Handles CDC, delta sync, OPFS/wa-sqlite out of the box. Free tier to start. |
| Reactive queries | **TanStack DB** (@tanstack/db + @tanstack/powersync-db-collection) | Sub-ms incremental query updates via differential dataflow. Direct PowerSync integration. |
| Browser SQLite | **wa-sqlite + OPFS** (bundled in PowerSync SDK) | Near-native SQLite perf in browser. Dedicated Web Worker. No IndexedDB bottleneck. |
| API caching | **Service Worker** (enhanced sw.js) | Cache-first for Lichess explorer, Chess.com, Stockfish WASM. Stale-while-revalidate for Flask API. |
| Prefetch engine | **Custom priority queue** | Whop's pattern: load most-used pages first, learn from navigation patterns. |

---

## 4. Current State Analysis

### Data Flow Today
```
User clicks page → React renders skeleton → useEffect fires fetch() →
Network request to Flask/Supabase → Wait 200-800ms → Update state → Re-render
```

### Data Fetching Hooks (all need migration)

| Hook | Endpoint(s) | Current Cache | Priority |
|------|------------|---------------|----------|
| `useLichessExplorer` | `/api/explorer/*` | sessionStorage 5min | P1 - heaviest usage |
| `useChessComExplorer` | `/api/chesscom/*` | sessionStorage 10min | P2 |
| `useOpeningRepertoire` | `/api/openings/*` (20+ endpoints) | None | P1 - user's own data |
| `useUserGames` | `/api/games/*` | None | P1 |
| `useTwicGames` | `/api/openings/games/by-position` | None | P2 - large dataset |
| `useChesster` | `/api/chat/stream` | None | P3 - streaming, special handling |
| `useSubscription` | `/api/subscription/status` | None | P1 - gates features |
| `useChatSessions` | localStorage | localStorage | Already local-first |

### State Management Today
- No Redux/Zustand — all `useState` + `useEffect` in custom hooks
- 3 Context providers: Subscription, GameData, Toast
- `useLocalStorage` from usehooks-ts for preferences
- `sessionStorage` for explorer caches (explorerSessionCache)
- SWR installed but **never used** (dead dependency)

### Existing Service Worker (`/public/sw.js`)
- Cache v7
- Network-first for navigation/API
- Cache-first for static assets
- Excludes .wasm, .onnx (COEP headers)

---

## 5. Implementation Phases

### Phase 1: Foundation — PowerSync + TanStack DB Setup
**Goal:** Install the local-first stack. Nothing breaks — purely additive.

**Tasks:**
1. **PowerSync Cloud setup**
   - Create PowerSync Cloud project → connect to Supabase (ref: `qtzujwiqzbgyhdgulvcd`)
   - Define sync rules (bucket definitions) for all user-scoped data:
     ```yaml
     bucket_definitions:
       user_data:
         parameters: SELECT request.user_id() as user_id
         data:
           - SELECT * FROM user_games WHERE user_id = bucket.user_id
           - SELECT * FROM repertoires WHERE user_id = bucket.user_id
           - SELECT * FROM repertoire_nodes WHERE repertoire_id IN (SELECT id FROM repertoires WHERE user_id = bucket.user_id)
           - SELECT * FROM chat_sessions WHERE user_id = bucket.user_id
           - SELECT * FROM user_progress WHERE user_id = bucket.user_id
       global_data:
         data:
           - SELECT * FROM courses
           - SELECT * FROM puzzles
           - SELECT * FROM lessons
     ```
   - Configure JWT integration with Clerk (PowerSync supports custom JWT providers)

2. **Install packages**
   ```bash
   npm install @powersync/web @powersync/react @tanstack/db @tanstack/react-db @tanstack/powersync-db-collection
   ```

3. **Create PowerSync schema** (`/src/lib/powersync/schema.ts`)
   - Define AppSchema matching Supabase tables
   - Configure column types for each synced table

4. **Create PowerSync provider** (`/src/lib/powersync/PowerSyncProvider.tsx`)
   - Initialize PowerSync database with OPFS backend
   - Connect to PowerSync Cloud with Clerk JWT
   - Wrap app in provider (alongside ClerkProvider)

5. **Create TanStack DB collections** (`/src/lib/powersync/collections.ts`)
   - Define PowerSync-backed collections for each data type
   - Set up reactive query subscriptions

6. **Verification:**
   - PowerSync dashboard shows connected client
   - Browser DevTools → Application → OPFS shows SQLite file
   - Console log confirms sync status: "connected", "syncing", "synced"

**Files touched:** ~5 new files, 1 modified (root layout for provider)
**Risk:** Zero — additive only, no existing code changed

---

### Phase 2: Migrate Hooks — Replace fetch+useState with Live Queries
**Goal:** One hook at a time, replace network fetches with local SQLite queries. Each hook migration is independently deployable.

**Migration pattern per hook:**
```typescript
// BEFORE (useUserGames.ts)
const [games, setGames] = useState<Game[]>([]);
useEffect(() => {
  fetch('/api/games', { headers: { Authorization: `Bearer ${token}` } })
    .then(r => r.json())
    .then(setGames);
}, [token]);

// AFTER (useUserGames.ts)
import { useQuery } from '@tanstack/react-db';
import { gamesCollection } from '@/lib/powersync/collections';

const games = useQuery({
  collection: gamesCollection,
  filter: { user_id: userId },
  orderBy: { created_at: 'desc' },
});
// Renders in <1ms from local SQLite. PowerSync keeps it synced in background.
```

**Migration order (by user impact):**

| Order | Hook | Reason | Complexity |
|-------|------|--------|------------|
| 1 | `useSubscription` | Gates all premium features, called on every page | Low |
| 2 | `useUserGames` | Dashboard main content | Low |
| 3 | `useOpeningRepertoire` | Core feature, 20+ endpoints, most complex | High |
| 4 | `useChatSessions` | Already localStorage, easy migration | Low |
| 5 | `useLichessExplorer` | Service Worker cache (Phase 3), not PowerSync | N/A |
| 6 | `useChessComExplorer` | Service Worker cache (Phase 3) | N/A |
| 7 | `useTwicGames` | Stays server-side (42GB DB) — SW cache only | N/A |
| 8 | `useChesster` | SSE streaming — keep network, add response cache | Special |

**Note:** Hooks 5-7 are external API proxies — they don't hit Supabase. These get Service Worker caching in Phase 3 instead of PowerSync.

**For each migrated hook:**
- Create corresponding TanStack DB collection
- Replace `useState`+`useEffect`+`fetch` with `useQuery` from `@tanstack/react-db`
- Remove manual cache logic (sessionStorage, explorerSessionCache)
- Write mutations through PowerSync upload queue (for hooks that write data)
- Keep the old fetch as a fallback for first-load before sync completes

**Verification per hook:**
- Page renders instantly on navigation (no spinner)
- Data matches what Supabase has
- Mutations (create/update/delete) propagate to Supabase within seconds
- Browser refresh → data loads from OPFS instantly (no network dependency)

**Files touched:** ~4-8 files per hook migration
**Risk:** Medium — each hook is isolated, can be rolled back independently

---

### Phase 3: Smart Caching — Service Worker + Prioritized Prefetch
**Goal:** Cache external API responses (Lichess, Chess.com, TWIC) and implement Whop's prioritized prefetch queue.

**3A. Enhanced Service Worker** (`/public/sw.js` → `/src/service-worker.ts`)

Upgrade from basic cache-first to intelligent strategies:

```
Static assets (.js, .css, images, pieces SVG) → Cache-First (immutable)
Stockfish WASM + ONNX model                   → Cache-First (versioned)
Lichess Explorer API                           → Stale-While-Revalidate (5min)
Chess.com API                                  → Stale-While-Revalidate (10min)
TWIC game queries                              → Cache-First (games don't change)
Flask backend API                              → Network-First (PowerSync handles most)
AI chat streaming                              → Network-Only (real-time)
```

**3B. Prioritized Prefetch Queue** (`/src/lib/powersync/prefetch.ts`)

Whop's key innovation — load what the user needs first:

```typescript
class PrefetchQueue {
  private queue: PrefetchTask[] = [];

  async onAppLaunch(userId: string) {
    // 1. Highest priority: subscription status (gates UI)
    this.enqueue({ type: 'subscription', priority: 0 });

    // 2. Last visited page data
    const lastPage = localStorage.getItem('chesster:lastPage');
    this.enqueue({ type: 'page-data', page: lastPage, priority: 1 });

    // 3. Dashboard data (most common landing)
    this.enqueue({ type: 'dashboard', priority: 2 });

    // 4. Usage-ranked pages (track which pages user visits most)
    const pageRanking = this.getUsageRanking(userId);
    pageRanking.forEach((page, i) => {
      this.enqueue({ type: 'page-data', page, priority: 3 + i });
    });

    // 5. Global data (courses, puzzles)
    this.enqueue({ type: 'global-catalog', priority: 100 });

    await this.processQueue();
  }
}
```

**Usage tracking:**
- Record page visits to localStorage: `{ "/dashboard": 45, "/database": 32, "/puzzle": 28, ... }`
- Prefetch queue sorts by visit frequency
- PowerSync's `priority` parameter on bucket definitions handles server-side prioritization

**Verification:**
- Network tab shows prefetch requests during idle time after app load
- Second navigation to any page = instant (0ms network wait)
- Service Worker → Cache Storage shows cached API responses

**Files touched:** ~3-4 new files, 1 modified (sw.js replacement)
**Risk:** Low — caching is additive, worst case is cache miss = current behavior

---

### Phase 4: Remove Spinners — Instant Page Transitions
**Goal:** Every page navigation renders content in <50ms. No loading skeletons between authenticated pages.

**Tasks:**

1. **Replace loading states with Suspense boundaries**
   - Wrap page content in `<Suspense>` with last-known-good data as fallback
   - Use `useSuspenseQuery` from `@powersync/react` for data that must be present

2. **Optimistic navigation**
   - Use Next.js `useRouter` prefetching for all sidebar links
   - On link hover → prefetch route + warm PowerSync query cache

3. **Skeleton-to-instant migration**
   - Remove all `<LoadingSkeleton>` components from pages with synced data
   - Replace with `<SyncBoundary>` that shows content or "syncing..." only on first-ever load

4. **Layout stability**
   - Ensure page dimensions don't shift when data loads
   - Pre-allocate space for chessboard, game lists, etc.

5. **First-load experience**
   - First visit (no local data): show minimal skeleton while PowerSync does initial sync
   - Subsequent visits: instant render from OPFS cache
   - Show subtle sync indicator (small dot/pulse) when background sync is active

**Verification:**
- Lighthouse Performance score > 95
- Time to Interactive < 1s on first load
- Navigation between pages: 0 visible loading states
- Record screen capture of navigation — no frame shows skeleton

**Files touched:** 10-15 page components, loading components
**Risk:** Medium — visual changes, needs QA across all pages

---

### Phase 5: Polish — Sync Indicator + Offline + Conflict Resolution
**Goal:** Production-ready local-first experience.

**5A. Sync Status Indicator**
- Small animated dot in bottom-right corner
- Green pulse = syncing, solid green = synced, gray = offline
- Click to expand: last sync time, items pending, connection status

**5B. Lite Offline Mode**
- Detect offline: `navigator.onLine` + PowerSync connection status
- Show banner: "You're offline — showing cached data"
- All read operations work normally from local SQLite
- Write operations: show toast "Saved locally, will sync when online" (but don't queue — discard on refresh per spec)
- Actually, simplify: disable mutation buttons when offline, show "Reconnect to save changes"

**5C. Conflict Resolution**
- Last-write-wins (PowerSync default) for all data
- Sufficient for Chesster — single-user data, no real-time collaboration
- If user edits repertoire on two devices: last save wins, no merge needed

**5D. Cleanup**
- Remove `swr` dependency (never used)
- Remove `explorerSessionCache` (replaced by Service Worker)
- Remove manual `sessionStorage` caching in hooks
- Remove legacy `apiFetch` retry logic where PowerSync handles it
- Update Service Worker version

**Verification:**
- Toggle airplane mode → app renders from cache, shows offline banner
- Go back online → sync indicator shows activity, data refreshes
- Edit data on two tabs → last write wins, no errors

**Files touched:** 5-8 files
**Risk:** Low — polish and cleanup

---

## 6. Data Architecture — What Syncs Where

| Data Type | Storage | Sync Method | Cache Duration |
|-----------|---------|-------------|----------------|
| User games | PowerSync SQLite | PowerSync CDC | Real-time |
| Repertoires + nodes | PowerSync SQLite | PowerSync CDC | Real-time |
| Chat sessions | PowerSync SQLite | PowerSync CDC | Real-time |
| User progress/XP | PowerSync SQLite | PowerSync CDC | Real-time |
| Subscription status | PowerSync SQLite | PowerSync CDC | Real-time |
| Courses catalog | PowerSync SQLite (global bucket) | PowerSync CDC | Real-time |
| Puzzles catalog | PowerSync SQLite (global bucket) | PowerSync CDC | Real-time |
| Lichess Explorer | Service Worker cache | Stale-while-revalidate | 5min |
| Chess.com games | Service Worker cache | Stale-while-revalidate | 10min |
| TWIC master games | Service Worker cache | Cache-first | 24hr (games are immutable) |
| AI chat responses | Not cached | Network-only (SSE) | N/A |
| Stockfish WASM | Service Worker cache | Cache-first | Until version change |
| Maia ONNX model | Service Worker cache | Cache-first | Until version change |
| Piece SVGs/images | Service Worker cache | Cache-first | Until version change |

---

## 7. Performance Targets

| Metric | Current | Target | How |
|--------|---------|--------|-----|
| Dashboard load (return visit) | ~800ms | <50ms | PowerSync + TanStack DB |
| Game list render | ~600ms | <10ms | Local SQLite query |
| Opening explorer (cached position) | ~200ms | <5ms | Service Worker cache |
| Page navigation (any → any) | 200-800ms | <50ms | All data local |
| First load (new user) | ~2s | ~1.5s | Initial sync + prefetch |
| Offline page render | N/A (blank) | <50ms | OPFS SQLite cache |
| TWIC game lookup | ~500ms | <100ms | SW cache-first |

---

## 8. PowerSync Cloud Configuration

**Instance:** Free tier to start (sufficient for < 1000 users)
**Database:** Connect to Supabase PostgreSQL (ref: qtzujwiqzbgyhdgulvcd)
**Auth:** Clerk JWT — configure PowerSync to validate Clerk-issued tokens
**Regions:** Auto (PowerSync Cloud manages this)

**Sync Rules (initial):**
- `user_data` bucket: per-user games, repertoires, progress, chat sessions
- `global_data` bucket: courses, puzzles, lessons (shared across all users)
- Priority: `user_data` syncs first (priority 0), `global_data` second (priority 1)

**Estimated sync payload:**
- Per user: ~50KB-500KB (depends on games/repertoires saved)
- Global catalog: ~2MB (courses + puzzles)
- Initial sync time: < 3 seconds on broadband

---

## 9. Migration Safety

### Rollback Strategy
Each phase is independently deployable and reversible:
- Phase 1: Remove provider wrapper → back to current behavior
- Phase 2: Each hook has old fetch logic as fallback; feature flag per hook
- Phase 3: Disable enhanced SW → fall back to current sw.js v7
- Phase 4: Re-add loading skeletons
- Phase 5: Remove offline banner/sync indicator

### Feature Flags
```typescript
// /src/lib/feature-flags.ts
export const FEATURES = {
  POWERSYNC_ENABLED: process.env.NEXT_PUBLIC_POWERSYNC_ENABLED === 'true',
  LOCAL_FIRST_GAMES: process.env.NEXT_PUBLIC_LOCAL_FIRST_GAMES === 'true',
  LOCAL_FIRST_REPERTOIRE: process.env.NEXT_PUBLIC_LOCAL_FIRST_REPERTOIRE === 'true',
  ENHANCED_SW: process.env.NEXT_PUBLIC_ENHANCED_SW === 'true',
  PREFETCH_QUEUE: process.env.NEXT_PUBLIC_PREFETCH_QUEUE === 'true',
};
```

### Testing Requirements per Phase
- Unit tests for each migrated hook (TanStack DB query returns expected data)
- Integration test: PowerSync sync completes, local data matches remote
- E2E test: navigate between pages, verify no loading spinners
- Offline test: airplane mode → app still renders
- Performance test: Lighthouse CI in deploy pipeline

---

## 10. Decisions Log

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Scope | All pages | User wants full Whop-style treatment |
| 2 | Offline support | Lite (read-only cache, no write queue) | Good UX without write sync complexity |
| 3 | Sync engine | PowerSync Cloud | Built for Supabase, handles hard problems, free tier |
| 4 | Reactive layer | TanStack DB | Sub-ms queries, direct PowerSync integration |
| 5 | External API cache | Service Worker | Lichess/Chess.com/TWIC aren't in Supabase |
| 6 | Conflict resolution | Last-write-wins | Single-user data, no collaboration conflicts |

---

## 11. Execution Order

**Phase 1** (Foundation) → can start immediately, no risk
**Phase 2** (Migrate hooks) → start with `useSubscription` and `useUserGames` as proof of concept
**Phase 3** (Service Worker + prefetch) → can run in parallel with Phase 2
**Phase 4** (Remove spinners) → after Phase 2 hooks are migrated
**Phase 5** (Polish) → final pass

**Estimated effort:** This is a 3+ files, multi-step task → **Ralph territory**.
Each phase should be a separate Ralph run with its own PRD section as the task description.
