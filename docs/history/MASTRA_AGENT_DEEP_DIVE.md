# Mastra Chess Agent — Deep Dive Investigation

**Date:** 2026-02-12  
**Author:** clawdbot (for Alex)  
**Scope:** Full analysis of the "Chess Empire" Mastra agent — architecture, tools, capabilities, and transferability to Clawdbot

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [The Agent Core](#3-the-agent-core)
4. [Tools — Complete Inventory](#4-tools--complete-inventory)
5. [The Protocol Layer (Position Intelligence)](#5-the-protocol-layer-position-intelligence)
6. [Theme Calculators](#6-theme-calculators)
7. [System Prompts (4 Modes)](#7-system-prompts-4-modes)
8. [Knowledge Base](#8-knowledge-base)
9. [External Dependencies](#9-external-dependencies)
10. [Frontend Integration (stream.ts)](#10-frontend-integration-streamts)
11. [Routing Logic](#11-routing-logic)
12. [Can Clawdbot Absorb All of This?](#12-can-clawdbot-absorb-all-of-this)
13. [Hidden/Unclear Inner Workings](#13-hiddenunclear-inner-workings)
14. [Recommendations](#14-recommendations)

---

## 1. Executive Summary

The Mastra agent ("Chess Empire") is a **stateless, tool-augmented chess analysis engine**. It has no memory, no persistent user model, and no coaching personality beyond its system prompt. What it *does* have is an impressive **position intelligence pipeline** — a chain of TypeScript classes that parse FEN strings into rich natural-language board descriptions covering 8+ chess themes (material, mobility, space, king safety, tactics, pawn structure, square control, piece placement).

**Key findings:**
- **10 tools** registered, all pure TypeScript except Stockfish (external API) and web search (Tavily)
- **4 operating modes**: position analysis, puzzle solving, game annotation, Socratic questioning
- **Multi-provider LLM support**: OpenAI, Anthropic, Google, Ollama, OpenRouter, and "Chesster Cloud" (free models via OpenRouter)
- **Zero state**: No user profiles, no conversation memory, no progress tracking
- The **position analysis pipeline** (BoardState → PositionPrompter → XML-tagged prompt) is the real crown jewel
- **Clawdbot can absorb ~90% of capabilities** — the remaining 10% would need the TacticalBoard and PositionPrompter to be ported or called as a service

---

## 2. Architecture Overview

```
User Query + FEN
       │
       ▼
┌─────────────────┐
│  stream.ts API   │  (Next.js API route)
│  - Auth (Clerk)  │
│  - Route decision│
│  - SSE streaming │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Router  │  routeRequest() → 'mastra' | 'chesster' | 'clawdbot'
    └────┬────┘
         │
   ┌─────┼──────────────────┐
   │     │                  │
   ▼     ▼                  ▼
Mastra  Chesster         Python Backend
Agent   Gateway          (fallback)
   │    (port 19789)     (port 5001)
   │
   ├── getBoardState(fen) ────── chess.js parsing
   ├── PositionPrompter ──────── XML-tagged natural language
   ├── RuntimeContext ─────────── model/provider/mode
   └── agent.stream() ────────── LLM + tools
         │
         ├── isLegalMoveTool
         ├── getStockfishAnalysisTool ── stockfish.online API
         ├── getStockfishMoveAnalysisTool
         ├── chessKnowledgeBaseTool
         ├── searchWeb (Tavily)
         ├── getThemeProgressionTool
         ├── getThemeScoresTool
         ├── analyzeVariationThemesTool
         ├── compareVariationsTool
         └── findCriticalMomentsTool
```

---

## 3. The Agent Core

**File:** `src/server/mastra/agents/index.ts`

```typescript
export const chessChesster = new Agent({
  name: "Chess Empire",
  instructions: ({ runtimeContext }) => createAgentInstruction(runtimeContext),
  model: ({ runtimeContext }) => createModelFromContext(runtimeContext),
  tools: ChessterTools,
});
```

**Key characteristics:**
- **Dynamic model selection** — provider/model/apiKey injected via `RuntimeContext` at request time
- **Dynamic system prompt** — switches between 4 modes based on `context_type` ("position", "puzzle", "annotation", "question")
- **Multi-provider factory** — supports OpenAI, Anthropic, Google, Ollama (local), OpenRouter, and "agineCloud" (free models)
- **No memory** — each request is independent; no conversation history carried between calls
- **All 10 tools always available** — no conditional tool loading

**Supported Model IDs** (from `agents/types.ts`):
- OpenAI: gpt-4, gpt-4-turbo, gpt-4o, gpt-4o-mini, o1, o3, gpt-5, gpt-4.1, etc.
- Anthropic: claude-sonnet-4, claude-opus-4, claude-3.7-sonnet, claude-opus-4.1, etc.
- Google: gemini-1.5-pro, gemini-2.0-flash, gemini-2.5-flash, gemini-2.5-pro
- Ollama: qwen3:8b/4b/30b, gpt-oss:20b/120b, deepseek-v3.1
- Chesster Cloud (free via OpenRouter): deepseek-chat-v3.1, gemini-2.0-flash-exp, llama-4-maverick, etc.

---

## 4. Tools — Complete Inventory

**File:** `src/server/mastra/tools/index.ts`

| # | Tool | Input | What It Does | External? |
|---|------|-------|-------------|-----------|
| 1 | `isLegalMoveTool` | FEN + move (SAN) | Validates if a move is legal using chess.js | No |
| 2 | `getStockfishAnalysisTool` | FEN + depth (1-15) | Gets top 3 engine lines from stockfish.online API | **Yes** — `stockfish.online/api/s/v2.php` |
| 3 | `getStockfishMoveAnalysisTool` | FEN + move + depth | Evaluates a specific move by playing it, then analyzing the resulting position | **Yes** — stockfish.online |
| 4 | `chessKnowledgeBaseTool` | (none) | Returns a 170-line static knowledgebase of chess principles (Silman, Fine's 30, endgame rules, pawn structures) | No |
| 5 | `searchWeb` | query string | Web search via Tavily API (includes answer synthesis) | **Yes** — Tavily API |
| 6 | `getThemeProgressionTool` | FEN + moves[] + side | Tracks how 8 chess themes evolve move-by-move through a sequence | No |
| 7 | `getThemeScoresTool` | FEN + side | Calculates theme scores for a single position (material, mobility, space, positional, king safety, tactical, light/dark square control) | No |
| 8 | `analyzeVariationThemesTool` | FEN + moves[] + side | Full variation analysis — strongest improvement, biggest decline, overall trajectory | No |
| 9 | `compareVariationsTool` | FEN + 2 move sequences + side | Compares two lines theme-by-theme to show which is better and why | No |
| 10 | `findCriticalMomentsTool` | FEN + moves[] + side + threshold | Identifies moves that caused dramatic theme changes (turning points) | No |

### Tool Call Flow (Stockfish)

```
FEN → HTTP GET stockfish.online/api/s/v2.php?fen=...&depth=...&mode=eval
     → Returns: { success, evaluation, mate, bestmove, continuation, ... }
     → Parsed into: evaluation + bestMove + lines + win/draw/loss %
     → UCI notation converted to SAN for human readability
```

**Important:** The Stockfish API is the **only computational chess engine** in the stack. Everything else is heuristic scoring computed in TypeScript.

---

## 5. The Protocol Layer (Position Intelligence)

This is the most sophisticated part of the Mastra agent. Three key classes:

### 5.1 `getBoardState(fen)` — State Calculator

**File:** `tools/protocol/state.ts`

Takes a FEN string and computes a comprehensive `BoardState` object for both sides:

```typescript
interface BoardState {
  fen, validfen, legalMoves,
  white: SideStateScores,    // 8 scoring categories
  black: SideStateScores,    // 8 scoring categories
  whitepieceattackerdefenderinfo,
  blackpieceattackerdefenderinfo,
  isCheckmate, isStalemate, isGameOver,
  moveNumber, sidetomove, gamePhase
}
```

Each `SideStateScores` contains:
- `castlingScore` — can castle kingside/queenside
- `materialScore` — piece counts, values, bishop pair, material advantage
- `spaceScore` — center control, flank control, total space advantage
- `pieceplacementScore` — exact squares of all pieces by type
- `positionalScore` — doubled/isolated/backward/passed pawn counts
- `squareControlScore` — light vs dark square control with advantages
- `kingSafetyScore` — attackers/defenders around king, pawn shield, castling status
- `pieceMobilityScore` — mobility per piece type, total, advantage

### 5.2 `PositionPrompter` — Board-to-Language Converter

**File:** `tools/protocol/positionPrompter.ts`

Converts the `BoardState` into a rich **XML-tagged natural language prompt** that becomes context for the LLM. Sections include:

```xml
<game_status>Move 15, middlegame, White to move, 32 legal moves</game_status>
<material_analysis>White: 39pts (1Q,2R,2B,1N,8P) | Black: 35pts...</material_analysis>
<piece_positions>White king: g1, queen: d1, rooks: a1,f1...</piece_positions>
<king_safety_analysis>White king safety: +3 (well shielded)...</king_safety_analysis>
<castling_rights>White: can castle kingside...</castling_rights>
<space_control>White controls 55% of center...</space_control>
<piece_mobility>White total mobility: 42, advantage: +8...</piece_mobility>
<pawn_structure_analysis>White: 1 isolated, 0 doubled, 1 passed...</pawn_structure_analysis>
<square_color_control>White controls 12 light squares...</square_color_control>
<attack_defense_details>White knight: 3 attackers, 2 defenders...</attack_defense_details>
<tactical_information>[from TacticalBoard — hanging pieces, pins, forks]</tactical_information>
```

**This is the key innovation** — the LLM receives pre-computed position intelligence rather than having to "see" the board from raw FEN.

### 5.3 `TacticalBoard` — Tactical Pattern Detector

**File:** `tools/themes/tacticalBoard.ts` (~650 lines)

A custom chess engine that computes:

1. **Hanging pieces** — undefended pieces under attack (immediate threats)
2. **Semi-protected pieces** — pieces where attackers = defenders (contested)
3. **Pin detection** — absolute pins (to king) and relative pins (to higher-value pieces)
4. **Fork detection** — deadly forks (profitable captures guaranteed) and regular forks
5. **Tactical score** — numerical score combining all tactical factors with weighted scoring:
   - Hanging piece: ±10 points
   - Semi-protected: ±3 points
   - Absolute pin: ±5 points
   - Relative pin: ±3 points
   - Deadly fork: ±8 points
   - Regular fork: ±4 points

It implements its own attack/defense maps, x-ray calculation, sliding piece logic, and pin detection — all from scratch using raw FEN parsing. This is **not** using chess.js for tactics; it's a parallel implementation.

---

## 6. Theme Calculators

**Directory:** `tools/themes/`

| Calculator | File | What It Computes |
|-----------|------|-----------------|
| Material | `material.ts` | Piece counts, values, bishop pair, material advantage |
| King Safety | `kingSafety.ts` | Attackers, defenders, pawn shield (3 ranks deep), castling bonus, comparative safety score |
| Mobility | `pieceMobility.ts` | Legal moves per piece type, total mobility, comparative advantage |
| Space Control | `spaceControl.ts` | Center squares (c4-f5) and flank squares controlled, comparative advantage |
| Piece Placement | `piecePlacement.ts` | Exact square locations grouped by piece type |
| Positional (Pawns) | `positional.ts` | Doubled, isolated, backward, passed pawn counts |
| Square Control | `sqaureControl.ts` | Light vs dark square control, per-color advantage |
| Attacker/Defender | `attackerDefender.ts` | Per-piece attack/defense counts using chess.js `.attackers()` |
| Game Phase | `gamePhase.ts` | Opening/middlegame/endgame detection based on material and move number |
| Tactical Board | `tacticalBoard.ts` | Hanging pieces, pins, forks, tactical score (see §5.3) |

### The OVP Framework (Theme Tracking Over Time)

**File:** `tools/protocol/ovp.ts`

"OVP" tracks how themes evolve across a sequence of moves. Key functions:

- `getThemeProgression(fen, moves, side)` → move-by-move theme scores
- `analyzeVariationThemes(fen, moves, side)` → strongest improvement, biggest decline, overall trajectory
- `compareVariations(fen, line1, line2, side)` → side-by-side theme comparison
- `findCriticalMoments(fen, moves, side, threshold)` → turning points where themes shifted dramatically

This powers the game review system (`protocol/review.ts`) which produces full game reports with white/black analyses, critical moments, average theme scores, and strategic insights.

---

## 7. System Prompts (4 Modes)

**File:** `agents/prompt.ts`

| Mode | Variable | Length | Purpose |
|------|----------|--------|---------|
| **position** | `agineSystemPrompt` | ~200 lines | General analysis — warm, friendly coach personality. Includes engine evaluation translation guide (+0.15 to +3.00+ scale), move quality definitions (best/very good/good/dubious/mistake/blunder), tool usage rules |
| **puzzle** | `aginePuzzleSystemPrompt` | ~120 lines | Puzzle-solving assistant — hints/analysis/solutions based on what user requests. Uses `searchWeb` for finding puzzle resources |
| **annotation** | `chessChessterAnnoPrompt` | ~100 lines | Game annotation expert — uses "Pump Up Your Rating" framework for mistake categorization (Opening/Tactics/Positional/Thinking/Mental). Generates concise 2-4 sentence annotations with standard symbols (!, ??, etc.) |
| **question** | `agineQuestionMode` | ~250 lines | **Socratic questioning mode** — never gives direct answers unless user explicitly says "tell me" or "I give up". Uses 4-level question framework (Observation → Positional → Evaluation → Planning) |

### Mode Selection Logic

In `stream.ts`:
```typescript
const mode = contextType === "puzzle" ? "puzzle" : contextType === "game" ? "position" : "position";
```
So currently: `context_type="puzzle"` → puzzle mode, everything else → position mode. The "annotation" and "question" modes exist in code but the frontend selection mechanism was not visible in the stream handler (may be triggered differently).

---

## 8. Knowledge Base

**File:** `agents/knowlegebase.ts` (171 lines)

A static text blob containing:
- **Silman Imbalances** (10 categories: minor pieces, pawn structure, space, material, files, holes, development, initiative, king safety, statics vs dynamics)
- **Fine's 30 Chess Principles** (10 opening, 10 middlegame, 10 endgame)
- **23 additional endgame principles** with quotes from Capablanca, Nimzowitsch, Benko, Botvinnik, Keres, Kotov
- **Pawn structure definitions** (isolated, doubled, backward, passed, chains, etc.)

This is returned verbatim by `chessKnowledgeBaseTool` whenever the agent decides it needs chess principles as context.

---

## 9. External Dependencies

| Dependency | Type | Required? | Notes |
|-----------|------|----------|-------|
| **stockfish.online** | HTTP API | Critical | Only real engine evaluation. Free, no auth, rate limits unknown |
| **Tavily** | HTTP API | Optional | Web search. Requires `TAVILY_API_KEY` env var. Not set in current `.env` files |
| **chess.js** | npm package | Critical | Board state, move validation, FEN parsing. Used everywhere |
| **@mastra/core** | npm package | Critical | Agent framework, tool creation, RuntimeContext |
| **@ai-sdk/**** | npm packages | Critical | LLM provider SDKs (OpenAI, Anthropic, Google, OpenRouter) |
| **ollama-ai-provider-v2** | npm package | Optional | Local model support via Ollama |

---

## 10. Frontend Integration (stream.ts)

**File:** `pages/api/chat/stream.ts`

The endpoint handles the complete request lifecycle:

1. **Auth** — Clerk JWT verification (`getAuth(req)`)
2. **Input** — `{ fen, query, conversation_id, context_type }` from POST body
3. **Routing** — `routeRequest(query, context)` decides target
4. **Position enrichment** — `getBoardState(fen)` → `PositionPrompter` → XML-tagged prompt appended to user query
5. **Streaming** — SSE (Server-Sent Events) with `sendEvent({ delta: chunk })`
6. **Fallback chain** — Primary route fails → try alternative → try Python backend
7. **Conversation save** — fire-and-forget to Python backend (currently TODO/no-op for Mastra responses)

### Fallback Chain

```
Chesster (OpenClaw gateway) fails → try Mastra
Mastra fails → try Chesster
Both fail → try Python backend (port 5001, raw LLM)
All fail → "All response methods failed"
```

---

## 11. Routing Logic

**File:** `src/lib/router/index.ts`

Keyword-based routing:

| Route | Trigger Keywords |
|-------|-----------------|
| **clawdbot** (coaching) | review, lesson, study, progress, improve, teach, practice, strategy, coach, help, better, learn, remember, my games, weakness |
| **mastra** (analysis) | best move, evaluate, this position, should I, what if, explain move, check, threat, tactic, right now, analyze, calculate |
| **default** | If no keywords match → `mastra` (for speed) |

Additional rules:
- `context.explicitCoaching` flag → always clawdbot
- No FEN + general how/why question → clawdbot
- `isChessterAvailable()` checks for `CHESSTER_GATEWAY_ENABLED=true` + URL/token configured

---

## 12. Can Clawdbot Absorb All of This?

### ✅ YES — Easily Transferable (Clawdbot can do today)

| Capability | How Clawdbot Does It |
|-----------|---------------------|
| **LLM chess chat** | Already has Claude with chess expertise |
| **Move legality checking** | Can use chess.js or python-chess |
| **Stockfish analysis** | Can call `stockfish.online` API directly via curl/fetch |
| **Knowledge base** | Can embed the 171-line knowledgebase into its context/skills |
| **Web search** | Already has `web_search` tool (Brave API) |
| **Game review/annotation** | Can replicate the annotation framework from the system prompts |
| **Socratic questioning** | System prompt technique — Clawdbot can adopt this mode |
| **Multi-mode operation** | Clawdbot can switch personalities per request |
| **Conversation memory** | Clawdbot is **better** — has persistent user profiles, history, MEMORY.md |
| **User progress tracking** | Clawdbot is **better** — has workspace files per user |

### ⚠️ PARTIALLY — Needs Work to Transfer

| Capability | What's Needed |
|-----------|--------------|
| **PositionPrompter** (FEN → rich natural language) | This is ~400 lines of TypeScript. Would need to be: (a) ported to Python, (b) exposed as an API endpoint from the Next.js app, or (c) reimplemented as a Clawdbot skill |
| **TacticalBoard** (hanging pieces, pins, forks) | ~650 lines of custom tactical engine. Same options as above. This is the hardest piece to replicate |
| **Theme scoring** (8 theme calculators) | Moderate complexity. Each is 50-100 lines. Could be approximated by good prompting, but exact numerical scores need the code |
| **OVP framework** (theme evolution over move sequences) | Depends on theme scoring. If that's available, OVP is straightforward |

### ❌ NOT TRANSFERABLE (Mastra-specific)

| Capability | Why |
|-----------|-----|
| **Mastra Agent framework** | Clawdbot uses OpenClaw, not Mastra. Different tool/agent abstraction |
| **RuntimeContext dynamic model switching** | Clawdbot has its own model selection via OpenClaw config |
| **SSE streaming from agent** | Clawdbot gateway returns complete responses, not streams |

### The Verdict

**Clawdbot can be a better chess coach than Mastra already.** Mastra's advantage is its position intelligence pipeline (BoardState → PositionPrompter → enriched prompt). Without that, Clawdbot's LLM has to "figure out" the position from raw FEN, which is significantly less reliable.

**Recommended approach:** Expose the PositionPrompter and TacticalBoard as a lightweight API endpoint on the existing Next.js server (or a standalone microservice). Then Clawdbot calls it like it calls Stockfish — HTTP request with FEN, gets back enriched position description. This gives Clawdbot the position intelligence without duplicating 1000+ lines of TypeScript.

---

## 13. Hidden/Unclear Inner Workings

### Things that ARE clear:
- ✅ All source code is readable — no obfuscation
- ✅ All tools are fully documented with Zod schemas
- ✅ System prompts are verbose and well-structured
- ✅ No hidden API calls or side effects
- ✅ No telemetry or analytics beyond conversation save (which is currently a no-op)

### Things that are UNCLEAR or potentially broken:

1. **Tavily API key not configured** — `TAVILY_API_KEY` not found in any `.env` file. The `searchWeb` tool will throw "TAVILY_API_KEY environment variable is not set" if the agent tries to use it.

2. **"annotation" and "question" modes unreachable** — `stream.ts` only maps `context_type` to "puzzle" or "position". The code for "annotation" and "question" prompts exists but there's no frontend path that triggers them (unless there's another API route not in `stream.ts`).

3. **Conversation persistence is a no-op** — `saveConversation()` has a TODO comment. Mastra/Clawdbot responses are NOT saved to Supabase. Only Python backend fallback responses get persisted.

4. **`agineCloud` model provider** — Uses `AGINE_KEY` env var (not found in `.env` files). This is a separate OpenRouter key for "free" models. If not set, the `createChessterCloudModel` will fail silently.

5. **Game phase detection** — `gamePhase.ts` was not fully inspected, but it feeds into `BoardState.gamePhase` which affects the system prompt's behavior ("opening", "middlegame", "endgame").

6. **TacticalBoard x-ray logic** — The attack map counts x-rays through same-color sliding pieces (e.g., rook x-rays through own queen on same file). This is sophisticated but may produce unusual vulnerability counts in rare positions.

7. **Pawn direction in TacticalBoard** — White pawns attack at `y-1` (upward on the board array). This depends on the FEN parsing orientation being correct. A subtle board-flip bug could cause all pawn attacks to be computed backwards.

---

## 14. Recommendations

### Short Term (Fix the broken chat)
1. **Start Python backend** — `systemctl start chess-backend` (needed for fallback route)
2. **Enable agent-to-agent in chess gateway** — add `"agentToAgent": {"enabled": true}` to config
3. **Fix Clerk secretKey** — ensure `CLERK_SECRET_KEY` loads in edge runtime (may need rebuild)
4. **Test Mastra alone** — with backend running, the Mastra→Stockfish→LLM chain should work even if Chesster gateway is down

### Medium Term (Consolidate architecture)
1. **Expose PositionPrompter as API** — `GET /api/position/analyze?fen=...` returning the XML-tagged prompt
2. **Give Clawdbot a chess skill** that calls both `stockfish.online` and the new position API
3. **Set `TAVILY_API_KEY`** or replace web search in Mastra with a backend proxy to Brave Search
4. **Enable conversation persistence** — implement the `saveConversation()` function

### Long Term (Simplify)
1. **Consider retiring Mastra** once Clawdbot can handle all chess analysis with the position API
2. **Keep the theme scoring code** — it's genuinely useful for tracking improvement over time
3. **Port the OVP framework** to a Python chess coaching service that both Clawdbot and the frontend can use

---

## File Reference

| Path | Purpose |
|------|---------|
| `src/server/mastra/agents/index.ts` | Agent definition, model factory |
| `src/server/mastra/agents/prompt.ts` | 4 system prompts (position/puzzle/annotation/question) |
| `src/server/mastra/agents/knowlegebase.ts` | Static chess principles (171 lines) |
| `src/server/mastra/agents/types.ts` | Model type definitions |
| `src/server/mastra/tools/index.ts` | All 10 tool definitions |
| `src/server/mastra/tools/fish.ts` | Stockfish online API client |
| `src/server/mastra/tools/search.ts` | Tavily web search |
| `src/server/mastra/tools/types.ts` | Shared TypeScript interfaces |
| `src/server/mastra/tools/protocol/state.ts` | FEN → BoardState calculator |
| `src/server/mastra/tools/protocol/positionPrompter.ts` | BoardState → XML prompt |
| `src/server/mastra/tools/protocol/ovp.ts` | Theme tracking over move sequences |
| `src/server/mastra/tools/protocol/positionScorer.ts` | Theme score calculator |
| `src/server/mastra/tools/protocol/review.ts` | Full game review generator |
| `src/server/mastra/tools/themes/*.ts` | 10 theme calculators |
| `src/pages/api/chat/stream.ts` | API endpoint (auth, routing, streaming) |
| `src/lib/router/index.ts` | Request routing logic |
| `src/lib/clawdbot/gateway.ts` | Gateway client (for Chesster/Clawdbot routes) |

---

*End of investigation. The Mastra agent is a well-built stateless analysis tool. Its real value is the position intelligence pipeline, not the agent framework. Clawdbot's persistent memory and coaching personality make it the better chess coach — it just needs the position intelligence fed to it.*
