# `check_moves` — Results

Implemented the engine-free move-legality tool per `CHECK_MOVES_SPEC.md`. All
work confined to `/root/chess-app`; `/root/hermes-chess` was never touched. No
deploys, pushes, or PM2 commands. Specific-file `git add` only.

## Per-task file list

### Task 1 — Hermes tool
- **`hermes/src/tools/check_moves.py`** (new) — `check_moves(fen, moves)` +
  registry self-registration under the `chess` toolset. Pure python-chess (no
  Stockfish / network / DB). Validates FEN via `chess.Board.is_valid()`
  (`{"error": "Invalid FEN: …"}` on failure, matching the `position_themes` /
  `board_control` error style), enforces the 1–10 move bound, and returns
  `fen` / `side_to_move` / per-move `results` / full SAN `legal_moves`
  (truncated to 60 with `legal_moves_truncated: true` on freak positions).
  Best-effort `reason` per illegal move (castling, piece-can't-reach,
  leaves-king-in-check, no-piece-on-square, ambiguous SAN, unparseable).
- Auto-discovery: picked up by `hermes/src/tools/__init__.py` /
  `registry.discover_builtin_tools` (verified: `registry.get_schema` and
  `registry.dispatch` resolve `check_moves`, toolset = `chess`).

### Task 2 — Voice allowlist + tool declaration
- **`frontend/src/app/api/coach/live-token/route.ts`** — added `check_moves`
  to `VOICE_TOOL_ALLOWLIST`. Gemini function declarations are fetched from
  Hermes `/api/coach/tools` (built from the registry), so the `check_moves`
  declaration flows through automatically once registered; the allowlist gates
  which ones survive.
- Tool-bridge allowlist: **no change needed** — the frontend `tool/route.ts`
  proxies by name with no local list, and the Hermes bridge
  (`tool_bridge.coach_tool_dispatch`) admits any `chess`-toolset tool via
  `_is_chess_tool`, which now includes `check_moves`. Verified by a new route
  test that the bridge proxies `check_moves` through.

### Task 3 — Prompt updates (single source: `hermes/src/prompt_builder.py`)
- **Voice prompt** — appended a directive to `VOICE_TOOL_LAYER`: silently
  verify a spoken non-engine move with `check_moves`; if illegal, pick a legal
  move from the returned list — never speak an illegal move.
- **Text prompt** — added a `### check_moves` line in the `Tool Usage
  (MANDATORY)` section (verify non-engine move suggestions before recommending).
- **`hermes/src/tool_selector.py`** — added `check_moves` to `CORE_TOOLS` (the
  always-on subset alongside `board_control` + `analyze_position`) so text-mode
  semantic subsetting never drops it.

### Task 4 — Tests
- **`hermes/tests/unit/test_check_moves.py`** (new, 24 tests) — legal/illegal
  SAN, UCI input (legal + illegal + no-piece-on-source), castling (both
  states), promotion (SAN + UCI), en passant (SAN + UCI), ambiguous SAN,
  unparseable move, invalid FEN, structurally-invalid position, empty and
  oversized move arrays, mixed legal+illegal batch (order preserved),
  starting-position legal-move count (= 20), truncation-flag path (218-move
  position → 60 + flag), handler JSON output.
- **`hermes/tests/unit/test_prompt_builder.py`** — added text-prompt and
  voice-prompt assertions that the `check_moves` directive is present (and
  absent from the voice prompt when `tools_available=False`).
- **`hermes/tests/unit/test_tool_selector.py`**,
  **`test_create_agent_subset.py`**, **`test_mcp_tool_bridge.py`** — updated
  their tool fixtures / bounds so the now-3-member `CORE_TOOLS` is honored
  (added a `check_moves` declaration; the length caps already keyed off
  `len(CORE_TOOLS)` or were rephrased to).
- **`frontend/.../__tests__/live-token.test.ts`** — asserts `check_moves`
  survives the voice allowlist filter (and a non-allowlisted tool is dropped).
- **`frontend/.../__tests__/routes.test.ts`** — asserts `POST /api/coach/tool`
  proxies `check_moves` through to Hermes at `/api/coach/tool/check_moves`.

## Test counts

### Hermes unit suite (`PYTHONPATH=<prod venv site-packages> pytest tests/unit`)
- **After change: 636 passed / 23 failed.**
- All 23 failures are the pre-existing environment baseline (missing 42GB TWIC
  SQLite DB → `test_setup` / `tool_get_pgn` / `tool_twic_search`; board-tool
  framework version drift → `board_control_tool` / `board_protocol`). None
  reference `check_moves` or the touched modules.
- Before the fixture updates in Task 4, the run showed 25 failed / 634 passed —
  the two extra failures (`test_create_agent_subset::…keeps_core`,
  `test_mcp_tool_bridge::…combined_set`) were the direct, expected consequence
  of `CORE_TOOLS` growing from 2→3 and are now updated to match.

### Frontend (`vitest run`)
- Touched suites `live-token.test.ts` + `routes.test.ts`: **37 passed / 0
  failed** (2 files).
- ESLint on the touched TS files: clean (exit 0).

## Deviations from spec
- **SAN-vs-UCI dispatch:** the spec suggests "try SAN parse first, fall back to
  UCI." python-chess's `parse_san` already accepts coordinate/UCI notation
  (and raises `IllegalMoveError`, not `InvalidMoveError`, for illegal
  coordinate moves), which would make an explicit `from_uci` fallback
  unreachable dead code. To keep both paths genuinely exercised — and to give
  precise UCI-specific reasons ("no piece on e5", "the pawn on e2 cannot
  legally reach e5") — the tool dispatches by notation shape: strings matching
  `^[a-h][1-8][a-h][1-8][qrbn]?$` go through the UCI path, everything else
  through SAN. Behavior matches the spec (both SAN and UCI accepted, SAN
  semantics preserved); only the internal ordering differs.
- **Frontend tool-bridge allowlist:** none exists to edit (see Task 2). Covered
  by the proxy-through test instead.
