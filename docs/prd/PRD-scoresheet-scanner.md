# PRD: Chess Scoresheet Scanner → PGN

## Overview
Add a "Scan Scoresheet" feature to Chesster's `/position` page that converts photos of handwritten chess score sheets into PGN game records using Vision LLM + python-chess validation.

## Integration Point
**Location:** `/position` page → Analysis tab → new Accordion section "Scoresheet Scanner" (below Opening Explorer, above Chess Database)

**Why /position:** The position page already has photo-to-FEN conversion, analysis tools, and a chessboard viewer. The scoresheet scanner loads the game into the same board, enabling immediate analysis with Stockfish, AI chat, and opening explorer.

## Architecture

### Backend: `/root/chess-app/backend/api/scoresheet_to_pgn.py`

New Flask Blueprint (`scoresheet_bp`, url_prefix `/api/scoresheet`).

**Endpoint:** `POST /api/scoresheet/convert`

**Input:**
```json
{
  "images": ["<base64_image_1>", "<base64_image_2>"],
  "metadata": {
    "white": "optional player name",
    "black": "optional player name",
    "event": "optional event name",
    "date": "optional date"
  }
}
```

**Pipeline:**
1. Send each image to Gemini 2.5 Flash via OpenRouter with structured prompt
2. Parse raw move list from LLM response
3. Validate each move sequentially with python-chess (`chess.Board`)
4. For illegal moves: attempt fuzzy correction (common OCR errors: O vs 0, l vs 1, B vs 8, etc.)
5. If fuzzy fails: re-ask LLM with current FEN + "move N was illegal, what should it be?"
6. Build PGN with headers and validated moves
7. Return PGN + correction report

**Output:**
```json
{
  "pgn": "[Event \"...\"]\n[White \"...\"]\n...\n1. e4 e5 2. Nf3 ...",
  "moves_total": 42,
  "moves_corrected": 3,
  "corrections": [
    {"move_number": 15, "original": "Bf8", "corrected": "Bf6", "reason": "Bf8 illegal, piece on f8"}
  ],
  "confidence": 0.95,
  "fen_final": "..."
}
```

**Model:** `google/gemini-2.5-flash-preview` via OpenRouter (same key as photo_to_fen.py)

**LLM Prompt structure:**
```
You are a chess scoresheet OCR expert. Extract all moves from this handwritten chess score sheet.
Output format: numbered move pairs, one per line.
Example: 1. e4 e5  2. Nf3 Nc6  3. Bb5 a6
Include move numbers. Use standard algebraic notation.
If a move is unclear, give your best guess with [?] marker.
```

**Dependencies:** python-chess (already installed), requests, difflib (stdlib for fuzzy matching)

### Frontend Proxy: `/root/chess-app/frontend/src/pages/api/convert-scoresheet.ts`

Copy pattern from `convert-image.ts`. Proxies to Flask backend. 10MB body size limit (multi-page scoresheets).

### Frontend Component: `/root/chess-app/frontend/src/components/analysis/ScoresheetScanner.tsx`

**Accordion in ChessterAnalysisView** (new section):
- Upload area: drag-and-drop or file picker (accept: image/*)
- Support for 1-2 images (front + back of scoresheet)
- Optional metadata fields: White, Black, Event, Date
- "Scan" button → loading state with progress
- Result display:
  - PGN text with copy button
  - Move list with corrected moves highlighted (amber)
  - Confidence score badge
  - "Load into Board" button → sets FEN to final position, loads move history
  - "Download PGN" button
- Error states: upload failed, OCR failed, too many illegal moves

### Integration into ChessterAnalysisView

**File:** `/root/chess-app/frontend/src/components/analysis/ChessterAnalysisView.tsx`

Add new Accordion:
```tsx
<Accordion>
  <AccordionSummary>📋 Scoresheet Scanner</AccordionSummary>
  <AccordionDetails>
    <ScoresheetScanner onGameLoaded={(pgn, fen) => { /* update board */ }} />
  </AccordionDetails>
</Accordion>
```

### Proxy Route

**File:** `/root/chess-app/frontend/next.config.ts`

Add rewrite:
```
{ source: '/api/scoresheet/:path*', destination: `${backendUrl}/api/scoresheet/:path*` }
```

### Backend Registration

**File:** `/root/chess-app/backend/app.py`

Register blueprint: `app.register_blueprint(scoresheet_bp)`

## Files to Create (2)
1. `/root/chess-app/backend/api/scoresheet_to_pgn.py` — Flask Blueprint
2. `/root/chess-app/frontend/src/components/analysis/ScoresheetScanner.tsx` — React component

## Files to Modify (4)
1. `/root/chess-app/backend/app.py` — register blueprint
2. `/root/chess-app/frontend/src/components/analysis/ChessterAnalysisView.tsx` — add accordion
3. `/root/chess-app/frontend/next.config.ts` — add rewrite rule
4. `/root/chess-app/frontend/src/pages/api/convert-scoresheet.ts` — proxy (create, follows convert-image.ts pattern)

## Total: 3 new files + 3 modified files = 6 files

## i18n
Use existing `useTranslations` pattern. Add keys to en.json and ru.json for scanner labels.

## Cost Estimate
- Gemini 2.5 Flash: ~$0.001/scoresheet (2 images × ~1K input tokens)
- Re-ask fallback: +$0.001 per corrected move
- Typical game: $0.002-0.005 total

## No Auth Required
Follows existing pattern — no Clerk auth check on this endpoint (same as convert-image).
