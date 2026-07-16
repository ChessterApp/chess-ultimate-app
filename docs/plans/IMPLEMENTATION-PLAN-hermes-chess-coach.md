# Implementation Plan: Hermes Chess Coach for Chesster

**Based on:** `../prd/PRD-hermes-chess-coach.md`
**Date:** 2026-04-23
**Principle:** Every phase ends with green tests. No phase starts until the previous phase's tests pass.

---

## Test Infrastructure Setup (Phase 0 — prerequisite)

Before any feature code, establish the test foundations for both the new Hermes service and the frontend additions.

### 0.1 Backend (Hermes) Test Setup

```
/root/hermes-chess/
├── pytest.ini
├── conftest.py                    # Shared fixtures (fake Supabase, fake TWIC, mock Stockfish)
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Test-scoped fixtures
│   ├── unit/                      # Pure function tests (no I/O)
│   │   └── __init__.py
│   ├── integration/               # Tests that hit real local resources (SQLite, Stockfish binary)
│   │   └── __init__.py
│   └── e2e/                       # Full API round-trip tests against running Hermes
│       └── __init__.py
```

**pytest.ini:**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: pure logic, no I/O
    integration: hits local resources (SQLite, Stockfish)
    e2e: full API round-trip (requires running Hermes daemon)
    slow: takes >5s
addopts = -v --tb=short
```

**conftest.py (shared fixtures):**
- `fake_twic_db` — in-memory SQLite with 50 fixture games
- `mock_stockfish` — subprocess mock returning canned evaluations
- `fake_supabase` — reuse pattern from existing backend `tests/` (FakeQueryBuilder, StatefulFakeTable)
- `hermes_client` — HTTP test client for Hermes API
- `sample_fens` — 10 standard test positions
- `sample_pgns` — 5 complete games

### 0.2 Frontend Test Setup

Add to existing Vitest config. New test directories:

```
/root/chess-app/frontend/
├── __tests__/
│   ├── coach/                     # All coach-related tests
│   │   ├── CoachToggle.test.tsx
│   │   ├── SessionSidebar.test.tsx
│   │   ├── ChessProfileCard.test.tsx
│   │   ├── ToolIndicator.test.tsx
│   │   └── api/
│   │       ├── coach-chat.test.ts
│   │       ├── coach-sessions.test.ts
│   │       └── coach-profile.test.ts
│   └── hooks/
│       └── useChessterCoach.test.ts
```

**vitest.config.ts update:**
- Add coverage reporting: `@vitest/coverage-v8`
- Keep existing environment settings

### 0.3 Deliverables
- [ ] `hermes-chess/pytest.ini` with markers
- [ ] `hermes-chess/conftest.py` with shared fixtures
- [ ] `hermes-chess/tests/` directory structure
- [ ] Frontend `__tests__/coach/` directory structure
- [ ] Verify: `cd /root/hermes-chess && pytest --collect-only` shows test discovery
- [ ] Verify: `cd /root/chess-app/frontend && npx vitest run --reporter=verbose` runs existing tests

---

## Phase 1: Foundation — Install & Configure Hermes (Week 1)

### 1.1 Install Hermes Agent

**Steps:**
1. Create `/root/hermes-chess/` directory
2. Create Python venv: `cd /root/hermes-chess && uv venv && source .venv/bin/activate`
3. Install Hermes: `uv pip install hermes-agent`
4. Install additional deps: `uv pip install python-chess stockfish httpx pydantic`
5. Verify import: `uv run python -c "import hermes; print(hermes.__version__)"`

### 1.2 Configure Chess Coach Profile

**Files to create:**
- `profiles/chess-coach/SOUL.md` — Coach persona (from PRD Section 8)
- `profiles/chess-coach/config.yaml` — Model routing, port, tool dirs
- `.env` — API keys (OpenRouter, Supabase, Hermes internal key)

**config.yaml structure:**
```yaml
profile: chess-coach
port: 8642
api_key: "${HERMES_API_KEY}"

models:
  default: google/gemini-3-flash-preview
  analysis: anthropic/claude-sonnet-4.5
  deep: anthropic/claude-opus-4.6
  provider: openrouter
  api_key: "${OPENROUTER_API_KEY}"

memory:
  backend: sqlite
  path: ./state.db
  fts5: true

tools:
  auto_discover: true
  tool_dir: ./tools
```

### 1.3 Start as PM2 Service

**PM2 ecosystem entry:**
```json
{
  "name": "hermes-chess",
  "script": ".venv/bin/python",
  "args": ["-m", "hermes", "--profile", "chess-coach"],
  "cwd": "/root/hermes-chess",
  "env": { "HOME": "/root" }
}
```

Start: `pm2 start ecosystem.config.js --only hermes-chess`
Verify: `curl -s http://localhost:8642/health`

### 1.4 Health Check Script

`scripts/healthcheck.sh`:
```bash
#!/bin/bash
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8642/health)
if [ "$response" != "200" ]; then
  echo "FAIL: Hermes health check returned $response"
  exit 1
fi
echo "OK: Hermes is healthy"
```

### 1.5 Phase 1 Tests

#### Unit Tests (`tests/unit/test_config.py`)
```
test_config_loads_from_yaml         — config.yaml parses without errors
test_config_env_substitution        — ${VAR} placeholders resolve from .env
test_coach_persona_loads            — SOUL.md is non-empty and loaded into profile
test_model_routing_config           — default/analysis/deep models are set
test_port_config                    — port is 8642
```

#### Integration Tests (`tests/integration/test_hermes_boot.py`)
```
test_hermes_starts_and_responds     — daemon starts, /health returns 200
test_hermes_chat_completions_basic  — POST /v1/chat/completions with simple chess question → 200 + valid response
test_hermes_session_id_header       — X-Hermes-Session-Id header is accepted and creates scoped session
test_hermes_persona_applied         — Response reflects chess coach persona (not generic assistant)
test_hermes_invalid_api_key         — Wrong API key → 401
test_hermes_model_override          — Explicit model param routes to that model
```

#### E2E Smoke Test (`tests/e2e/test_smoke.py`)
```
test_full_coaching_exchange          — Send 3 messages in sequence, verify conversation continuity
test_session_isolation               — Two different session IDs get independent histories
test_daemon_stability_under_load    — Send 10 concurrent requests, all return 200
```

### 1.6 Acceptance Gate

Run:
```bash
cd /root/hermes-chess
pytest tests/unit/ tests/integration/ -m "not slow"
pytest tests/e2e/test_smoke.py
```

**All tests must pass before proceeding to Phase 2.**

---

## Phase 2: Chess Tool Registry (Weeks 2–3)

### 2.1 Tool Auto-Discovery Loader

`tools/__init__.py` — Scans `tools/` dir, imports all modules, registers `@tool`-decorated functions with Hermes.

### 2.2 Implement 8 MVP Tools (one at a time, test each before next)

**Order of implementation** (simplest → most complex):

#### Tool 1: `search_web` (`tools/web_search.py`)
- Wraps a web search API call
- Input: `query: str`
- Output: list of `{title, url, snippet}`
- **Tests:** `tests/unit/test_tool_web_search.py`
  ```
  test_search_returns_results           — valid query → non-empty list
  test_search_empty_query               — "" → empty or error
  test_search_result_schema             — each result has title, url, snippet
  test_search_timeout_handling          — slow API → graceful timeout error
  ```

#### Tool 2: `get_opening_stats` (`tools/openings.py`)
- Reads ECO JSON + TWIC stats
- Input: `eco: str` or `opening_name: str`
- Output: `{eco, name, main_line, games_count, white_win_pct, draw_pct, black_win_pct}`
- **Tests:** `tests/unit/test_tool_openings.py`
  ```
  test_get_opening_by_eco              — "B90" → Sicilian Najdorf
  test_get_opening_by_name             — "Sicilian" → returns matches
  test_opening_stats_schema            — all expected fields present
  test_unknown_eco_returns_empty       — "Z99" → empty/null
  test_case_insensitive_search         — "sicilian" = "Sicilian"
  ```

#### Tool 3: `search_master_games` (`tools/twic_search.py`)
- Queries TWIC SQLite (3.4M games)
- Input: `player, eco, opening, result, year_min, year_max, limit`
- Output: list of game metadata dicts
- **Tests:** `tests/unit/test_tool_twic_search.py` (uses `fake_twic_db` fixture)
  ```
  test_search_by_player                — "Carlsen" → games with Carlsen
  test_search_by_eco                   — "B90" → games with ECO B90
  test_search_by_year_range            — year_min=2020, year_max=2023 → filtered
  test_search_by_result                — "1-0" → only decisive for white
  test_search_combined_filters         — player + eco + year → intersection
  test_search_limit_enforced           — limit=5 → max 5 results
  test_search_limit_capped_at_50       — limit=1000 → capped to 50
  test_search_no_filters               — no params → returns recent games
  test_search_nonexistent_player       — "zzzzNotAPlayer" → empty
  test_sql_injection_safe              — player="'; DROP TABLE--" → no crash
  ```

#### Tool 4: `get_game_pgn` (`tools/twic_search.py`)
- Retrieves full PGN for a game by ID
- Input: `game_id: int`
- Output: `{pgn: str, headers: dict}`
- **Tests:** `tests/unit/test_tool_get_pgn.py`
  ```
  test_get_pgn_valid_id                — known fixture game_id → full PGN string
  test_get_pgn_invalid_id              — -1 → null/error
  test_pgn_parseable                   — returned PGN parses with python-chess
  test_headers_extracted               — White, Black, Date, Result present
  ```

#### Tool 5: `analyze_position` (`tools/stockfish.py`)
- Runs Stockfish binary via subprocess
- Input: `fen: str, depth: int = 20, multipv: int = 3`
- Output: `{evaluation: float, best_move: str, lines: [{pv, score, depth}]}`
- **Tests:** `tests/unit/test_tool_stockfish.py` (uses `mock_stockfish` fixture)
  ```
  test_analyze_starting_position       — standard FEN → eval near 0.0
  test_analyze_mate_in_one             — known mate → score = "M1"
  test_analyze_custom_depth            — depth=10 → respects depth param
  test_analyze_multipv                 — multipv=3 → 3 lines returned
  test_analyze_invalid_fen             — "not a fen" → error message
  test_analyze_timeout                 — extremely deep analysis → timeout after 30s
  test_fen_validation                  — malformed FEN rejected before calling engine
  ```
  **Integration test:** `tests/integration/test_stockfish_live.py`
  ```
  test_stockfish_binary_exists         — /usr/games/stockfish is executable
  test_live_analysis_returns_eval      — real Stockfish analyzes known position
  test_live_analysis_performance       — depth=15 completes in <5s
  ```

#### Tool 6: `get_user_repertoire` (`tools/user_data.py`)
- Reads from Supabase `repertoire_*` tables
- Input: `user_id: str, color: "white" | "black" | None`
- Output: list of `{name, eco, moves, color}`
- **Tests:** `tests/unit/test_tool_user_data.py` (uses `fake_supabase` fixture)
  ```
  test_get_repertoire_white            — user has white lines → returns them
  test_get_repertoire_black            — user has black lines → returns them
  test_get_repertoire_all              — no color filter → both colors
  test_get_repertoire_empty_user       — new user → empty list
  test_user_id_scoping                 — user A can't see user B's repertoire
  ```

#### Tool 7: `get_user_games` (`tools/user_data.py`)
- Reads from Supabase `user_games` table
- Input: `user_id: str, limit: int = 20`
- Output: list of game records
- **Tests:** `tests/unit/test_tool_user_games.py`
  ```
  test_get_user_games_returns_list     — user with games → non-empty list
  test_get_user_games_empty            — user with no games → empty list
  test_get_user_games_limit            — limit=5 → max 5
  test_user_id_scoping                 — isolation between users
  test_game_record_schema              — each game has id, pgn, date, result
  ```

#### Tool 8: `get_player_profile` (`tools/player_profiles.py`)
- Calls Lichess + Chess.com public APIs
- Input: `username: str, platform: "lichess" | "chesscom"`
- Output: `{username, platform, ratings: {rapid, blitz, bullet}, games_played, member_since}`
- **Tests:** `tests/unit/test_tool_player_profiles.py` (mocked HTTP)
  ```
  test_lichess_profile_fetch           — mocked API → parsed profile
  test_chesscom_profile_fetch          — mocked API → parsed profile
  test_unknown_player_lichess          — 404 → "Player not found"
  test_unknown_player_chesscom         — 404 → "Player not found"
  test_invalid_platform                — platform="chess24" → error
  test_profile_schema                  — all expected fields present
  test_api_timeout_handling            — slow API → graceful error
  test_rate_limit_handling             — 429 → retry or error message
  ```

### 2.3 Tool Integration Tests (`tests/integration/test_tools_with_hermes.py`)

Test that Hermes actually calls tools when prompted:

```
test_hermes_calls_search_games       — "Find Carlsen's games" → tool call observed in response
test_hermes_calls_analyze            — "Analyze this position: [FEN]" → Stockfish tool called
test_hermes_calls_opening_stats      — "Tell me about the Najdorf" → opening stats tool called
test_hermes_multi_tool_chain         — Complex query → multiple tools called in sequence
test_hermes_tool_error_graceful      — Tool returns error → coach explains gracefully, no crash
test_hermes_tool_timeout_graceful    — Tool times out → coach says "analysis is taking longer"
```

### 2.4 Acceptance Gate

```bash
cd /root/hermes-chess
# Unit tests for all 8 tools
pytest tests/unit/test_tool_*.py -v

# Integration tests (requires TWIC DB + Stockfish binary)
pytest tests/integration/ -v -m "not slow"

# Tool-calling integration (requires running Hermes)
pytest tests/integration/test_tools_with_hermes.py -v
```

**All tests must pass. Coverage target: >80% on tools/ directory.**

---

## Phase 3: User Memory & Frontend Integration (Weeks 3–5)

### 3.1 Backend — Database & Session Management

**Steps:**
1. Create `user_chess_profiles` table in Supabase (SQL from PRD §9)
2. Create `coaching_sessions` table in Supabase (SQL from PRD §9)
3. Implement `middleware/session_manager.py`:
   - `get_or_create_session(clerk_user_id)` → Hermes session ID
   - `build_system_prompt(user_profile)` → dynamic coach context
   - `save_session_summary(session_id)` → auto-summarize on session end
4. Implement `middleware/model_router.py`:
   - `classify_query(query, context)` → QUICK | ANALYSIS | DEEP
   - `select_model(complexity, tier)` → model ID

**Tests:** `tests/unit/test_session_manager.py`
```
test_session_id_format               — "chesster-{userId}" pattern
test_new_user_creates_profile        — first request → profile auto-created
test_system_prompt_includes_rating   — profile with rating → prompt contains it
test_system_prompt_includes_openings — profile with openings → prompt lists them
test_system_prompt_includes_goals    — profile with goals → prompt includes them
test_system_prompt_empty_profile     — new user → generic welcome prompt
test_session_summary_generation      — multi-message session → coherent summary
test_query_classification_quick      — "What is the Italian Game?" → QUICK
test_query_classification_analysis   — "Analyze e4 e5 Nf3" + FEN → ANALYSIS
test_query_classification_deep       — "Create a study plan for me" → DEEP
test_model_selection_free_tier       — free + ANALYSIS → capped to Flash
test_model_selection_premium_tier    — premium + ANALYSIS → Sonnet
test_model_selection_pro_tier        — pro + DEEP → Opus
```

**Tests:** `tests/integration/test_session_persistence.py`
```
test_session_persists_across_requests — send msg, new request same session → history includes first msg
test_session_isolation_between_users  — user A and user B get separate histories
test_profile_update_reflected         — update profile → next system prompt reflects change
test_session_fts5_search              — search past session for keyword → found
```

### 3.2 Frontend — Coach Mode UI

**Steps (each has corresponding test):**

1. **CoachToggle component** (`components/coach/CoachToggle.tsx`)
   - Premium user: clickable toggle between Chat/Coach
   - Free user: disabled with "Upgrade" tooltip

   **Test:** `__tests__/coach/CoachToggle.test.tsx`
   ```
   test_renders_toggle_for_premium      — premium user → toggle visible + enabled
   test_toggle_switches_mode            — click → mode changes from "chat" to "coach"
   test_disabled_for_free               — free user → toggle disabled
   test_shows_upgrade_tooltip_free      — free user hover → "Upgrade to Premium"
   ```

2. **SessionSidebar component** (`components/coach/SessionSidebar.tsx`)
   - Lists past coaching sessions with titles and dates
   - Click to load session

   **Test:** `__tests__/coach/SessionSidebar.test.tsx`
   ```
   test_renders_session_list            — 3 sessions → 3 items rendered
   test_sessions_sorted_by_date        — most recent first
   test_click_loads_session            — click item → onSelectSession called with id
   test_empty_state                    — no sessions → "Start your first session" message
   test_delete_session                 — delete button → onDeleteSession called
   ```

3. **ChessProfileCard component** (`components/coach/ChessProfileCard.tsx`)
   - View/edit chess identity (rating, openings, goals, weaknesses)

   **Test:** `__tests__/coach/ChessProfileCard.test.tsx`
   ```
   test_displays_profile_data          — profile loaded → shows rating, openings, goals
   test_edit_mode                      — click edit → fields become editable
   test_save_profile                   — edit + save → onSave called with updated data
   test_empty_profile                  — new user → prompts to fill in profile
   ```

4. **ToolIndicator component** (`components/coach/ToolIndicator.tsx`)
   - Shows "Searching master games..." during tool calls

   **Test:** `__tests__/coach/ToolIndicator.test.tsx`
   ```
   test_shows_indicator_when_active    — toolName provided → renders indicator
   test_hides_when_inactive            — no toolName → nothing rendered
   test_displays_tool_name             — "search_master_games" → "Searching master games..."
   test_animated                       — indicator has loading animation class
   ```

5. **API route: `/api/coach/chat`** (`pages/api/coach/chat/route.ts`)
   - Auth check (Clerk) → tier check → classify → proxy to Hermes → SSE stream

   **Test:** `__tests__/coach/api/coach-chat.test.ts`
   ```
   test_unauthenticated_returns_401    — no auth → 401
   test_free_tier_returns_403          — free user → 403 "Premium required"
   test_premium_user_proxies_to_hermes — premium + valid query → 200 SSE stream
   test_session_id_forwarded           — X-Hermes-Session-Id header set correctly
   test_model_routing_applied          — ANALYSIS query + premium → Sonnet model used
   test_hermes_down_returns_503        — Hermes unreachable → 503 + friendly error
   ```

6. **API route: `/api/coach/sessions`** (`pages/api/coach/sessions/route.ts`)

   **Test:** `__tests__/coach/api/coach-sessions.test.ts`
   ```
   test_list_sessions                  — GET → returns user's sessions
   test_list_sessions_other_user       — can't see other user's sessions
   test_delete_session                 — DELETE → session removed
   ```

7. **API route: `/api/coach/profile`** (`pages/api/coach/profile/route.ts`)

   **Test:** `__tests__/coach/api/coach-profile.test.ts`
   ```
   test_get_profile                    — GET → returns profile
   test_create_profile_on_first_access — GET with no profile → auto-creates
   test_update_profile                 — PUT → profile updated
   test_profile_isolation              — user A can't read user B's profile
   ```

8. **useChesster hook updates**

   **Test:** `__tests__/hooks/useChessterCoach.test.ts`
   ```
   test_sendCoachMessage               — sends to /api/coach/chat
   test_coach_mode_state               — toggleMode() switches between chat/coach
   test_session_management             — createSession, switchSession, listSessions
   test_profile_hooks                  — getProfile, updateProfile
   ```

### 3.3 Acceptance Gate

```bash
# Backend
cd /root/hermes-chess
pytest tests/unit/test_session_manager.py -v
pytest tests/integration/test_session_persistence.py -v

# Frontend
cd /root/chess-app/frontend
npx vitest run __tests__/coach/ --reporter=verbose
npx vitest run __tests__/hooks/useChessterCoach.test.ts --reporter=verbose

# E2E smoke (manual or scripted)
# 1. Login as premium user
# 2. Toggle to Coach mode
# 3. Send message → get response with tool indicators
# 4. Refresh page → session still in sidebar
# 5. Switch to free account → Coach toggle disabled
```

**All tests must pass before proceeding to Phase 4.**

---

## Phase 4: External Platform Integration (Weeks 5–6)

### 4.1 Implement Platform API Tools

1. **`lichess_game_import`** (`tools/external_apis.py`)
   - Fetches user's recent games from Lichess API
   - Parses PGN stream, stores in `user_games`
   - Input: `username: str, max_games: int = 50`

2. **`chesscom_game_import`** (`tools/external_apis.py`)
   - Fetches user's recent games from Chess.com API
   - Input: `username: str, max_games: int = 50`

3. **Platform linking in chess profile**
   - Add "Connect Lichess" / "Connect Chess.com" in profile card
   - Verification flow: enter username → coach confirms via API → stores in profile

4. **Auto-sync ratings on profile load**
   - When profile loads and platform username is set, fetch latest rating
   - Cache for 1 hour

### 4.2 Phase 4 Tests

**Unit tests:** `tests/unit/test_tool_external_apis.py`
```
test_lichess_import_parses_pgn       — mocked API response → games extracted
test_lichess_import_respects_limit   — max_games=10 → requests 10
test_lichess_import_stores_games     — imported games written to Supabase mock
test_chesscom_import_parses_json     — mocked monthly archive → games extracted
test_chesscom_import_pagination      — multiple months → all fetched
test_import_deduplication            — same game imported twice → no duplicate
test_import_rate_limit_respected     — 429 → backs off and retries
test_import_invalid_username         — unknown user → "Player not found"
test_auto_sync_rating                — profile with lichess_username → rating updated
test_auto_sync_caching               — second call within 1h → cached value returned
```

**Integration tests:** `tests/integration/test_external_platforms.py`
```
test_lichess_api_live                — real API call to Lichess for known user → profile returned
test_chesscom_api_live               — real API call to Chess.com for known user → profile returned
test_game_import_end_to_end          — import 5 games → stored in DB → coach can reference them
```

**Frontend tests:** `__tests__/coach/PlatformLinking.test.tsx`
```
test_connect_lichess_button          — renders "Connect Lichess" button
test_connect_flow                    — enter username → verify → success message
test_disconnect_button               — connected → "Disconnect" button visible
test_rating_display_after_connect    — connected → rating shown in profile card
```

### 4.3 Acceptance Gate

```bash
# Backend unit
cd /root/hermes-chess
pytest tests/unit/test_tool_external_apis.py -v

# Backend integration (hits live APIs — mark as slow, run explicitly)
pytest tests/integration/test_external_platforms.py -v -m "not slow"

# Frontend
cd /root/chess-app/frontend
npx vitest run __tests__/coach/PlatformLinking.test.tsx --reporter=verbose
```

---

## Phase 5: Advanced Features (Weeks 6–8)

### 5.1 Implement 8 Phase-2 Tools

Each tool follows the same pattern: implement → unit test → integration test.

| Tool | Test File | Key Tests |
|------|-----------|-----------|
| `get_position_stats` | `test_tool_position_stats.py` | returns win rates from 285M positions, handles unknown FEN |
| `get_player_openings` | `test_tool_player_openings.py` | aggregates opening stats for a player, handles no-data |
| `score_position_themes` | `test_tool_themes.py` | material/mobility/space/king-safety scores, valid ranges |
| `compare_variations` | `test_tool_compare.py` | side-by-side eval for 2+ lines, handles invalid PGN |
| `find_critical_moments` | `test_tool_critical.py` | detects eval swings >1.5, annotates turning points |
| `get_user_progress` | `test_tool_progress.py` | returns course/puzzle stats, scoped by user_id |
| `lichess_game_import` | (already done in Phase 4) | — |
| `chesscom_game_import` | (already done in Phase 4) | — |

### 5.2 Opponent Preparation Workflow

**Implementation:** `tools/game_analysis.py` — `prepare_against_opponent(username, platform, color)`
- Fetches opponent's recent games
- Analyzes their opening repertoire
- Identifies weaknesses in their play
- Suggests preparation lines from user's repertoire

**Tests:** `tests/unit/test_opponent_prep.py`
```
test_opponent_prep_fetches_games     — calls get_player_profile + search
test_opponent_prep_analyzes_openings — identifies opponent's top 5 openings
test_opponent_prep_suggests_lines    — cross-references with user repertoire
test_opponent_prep_color_specific    — preparing as white vs black differs
test_opponent_prep_unknown_player    — unknown player → "Can't find that player"
```

### 5.3 Weakness Tracking

**Implementation:** `middleware/weakness_tracker.py`
- After game analysis, auto-detect weakness patterns
- Update `user_chess_profiles.weakness_tags`
- Track weakness improvement over time

**Tests:** `tests/unit/test_weakness_tracker.py`
```
test_detect_endgame_weakness         — multiple rook endgame losses → "rook endgames" tag added
test_detect_time_trouble             — games lost on time → "time management" tag
test_detect_opening_weakness         — losing repeatedly in one opening → tag added
test_weakness_update_not_duplicate   — existing tag → not added again
test_weakness_improvement_detected   — win streak in weak area → tag removed or improved
```

### 5.4 Learning Loop (Hermes Skill Creation)

**Implementation:** Configure Hermes learning loop to auto-create coaching "skills" from successful teaching patterns.

**Tests:** `tests/integration/test_learning_loop.py`
```
test_repeated_pattern_creates_skill  — coach explains concept 5+ times → skill auto-created
test_skill_applied_to_new_student    — new user with similar weakness → skill applied
test_skill_quality_threshold         — only positive-feedback sessions → skill created
```

### 5.5 Acceptance Gate

```bash
# All Phase 2 tool tests
cd /root/hermes-chess
pytest tests/unit/test_tool_position_stats.py tests/unit/test_tool_player_openings.py \
       tests/unit/test_tool_themes.py tests/unit/test_tool_compare.py \
       tests/unit/test_tool_critical.py tests/unit/test_tool_progress.py \
       tests/unit/test_opponent_prep.py tests/unit/test_weakness_tracker.py -v

# Integration
pytest tests/integration/test_learning_loop.py -v

# Full regression (all previous phases still green)
pytest -v --tb=short
```

---

## Phase 6: Polish & Scale (Weeks 8–10)

### 6.1 Rate Limiting

**Implementation:** Next.js middleware — per-user request limits based on tier.

**Tests:** `__tests__/coach/api/rate-limiting.test.ts`
```
test_free_tier_10_queries_per_day    — 11th query → 429
test_premium_unlimited               — 100 queries → all 200
test_rate_limit_resets_daily          — next day → counter reset
test_rate_limit_response_message     — 429 → includes "upgrade" suggestion
```

### 6.2 Cost Monitoring

**Implementation:** Log token usage per user per model. Dashboard endpoint.

**Tests:** `tests/unit/test_cost_monitor.py`
```
test_token_usage_logged              — chat completion → usage recorded
test_cost_calculation                — tokens × model rate → correct cost
test_daily_cost_aggregation          — multiple requests → summed correctly
test_cost_alert_threshold            — user exceeds $5/day → alert triggered
```

### 6.3 Error Handling & Graceful Degradation

**Tests:** `__tests__/coach/api/error-handling.test.ts`
```
test_hermes_down_fallback_message    — Hermes 503 → "Coach is temporarily unavailable"
test_hermes_timeout_message          — Hermes slow → "Taking longer than usual..."
test_tool_failure_non_blocking       — tool error → coach continues without tool
test_network_error_recovery          — connection reset → retry once, then error
```

### 6.4 Load Testing

```bash
# Using k6 or wrk
k6 run --vus 50 --duration 60s loadtest/coach_chat.js
```

**Tests:** `tests/e2e/test_load.py` (marked `@pytest.mark.slow`)
```
test_50_concurrent_sessions          — 50 users chatting simultaneously → all get responses
test_response_time_p95               — p95 < 5s for QUICK, < 15s for ANALYSIS
test_no_session_crosstalk            — under load, sessions remain isolated
```

### 6.5 Stripe Integration

**Tests:** `__tests__/coach/api/subscription.test.ts`
```
test_webhook_subscription_created    — Stripe webhook → user tier updated in Supabase
test_webhook_subscription_cancelled  — cancel → tier reverts to free
test_tier_check_reads_from_db        — subscription status from Supabase, not hardcoded
test_expired_subscription            — past expires_at → treated as free
```

### 6.6 Final Acceptance Gate (Full Regression)

```bash
# ALL backend tests
cd /root/hermes-chess
pytest -v --tb=short --cov=tools --cov=middleware --cov-report=term-missing

# ALL frontend tests
cd /root/chess-app/frontend
npx vitest run --reporter=verbose --coverage

# E2E smoke (manual checklist)
# [ ] Free user: can chat, can't use Coach
# [ ] Premium user: Coach mode works, tools fire, session persists
# [ ] Pro user: DEEP queries route to Opus
# [ ] Lichess/Chess.com linking works
# [ ] Rate limiting enforced
# [ ] Hermes crash → auto-restart → coach back in <30s
# [ ] 50 concurrent users → no crashes
```

---

## Summary: Test Count by Phase

| Phase | Unit Tests | Integration Tests | E2E Tests | Frontend Tests | Total |
|-------|-----------|------------------|-----------|---------------|-------|
| 0 (Setup) | 0 | 0 | 0 | 0 | Setup only |
| 1 (Foundation) | 5 | 6 | 3 | 0 | **14** |
| 2 (Tools) | ~50 | 6 | 0 | 0 | **~56** |
| 3 (Memory + UI) | 12 | 4 | 0 | ~25 | **~41** |
| 4 (External) | 10 | 3 | 0 | 4 | **~17** |
| 5 (Advanced) | ~20 | 3 | 0 | 0 | **~23** |
| 6 (Polish) | 4 | 0 | 3 | ~12 | **~19** |
| **Total** | **~101** | **~22** | **~6** | **~41** | **~170** |

---

## Running All Tests (CI-style)

```bash
#!/bin/bash
set -e

echo "=== HERMES BACKEND ==="
cd /root/hermes-chess
source .venv/bin/activate
pytest -v --tb=short --cov=tools --cov=middleware -m "not slow"

echo "=== CHESSTER FRONTEND ==="
cd /root/chess-app/frontend
npx vitest run --reporter=verbose

echo "=== E2E (requires running services) ==="
cd /root/hermes-chess
pytest tests/e2e/ -v -m "not slow"

echo "ALL TESTS PASSED"
```

---

## Phase Gate Protocol

Before starting Phase N+1:
1. Run all Phase N tests + all previous phase tests (full regression)
2. All tests GREEN
3. Record test results in daily notes (`memory/YYYY-MM-DD.md`)
4. If any test fails: fix first, re-run, then proceed
5. Never skip a failing test — either fix it or explicitly mark it as `@pytest.mark.skip(reason="...")` with justification
