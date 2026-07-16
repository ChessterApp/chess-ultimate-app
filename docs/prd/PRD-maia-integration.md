# PRD: Integrate Maia Bot into Chesster

## Goal
Add a "Play vs Maia Bot" feature to Chesster. Maia is a human-like chess AI that runs entirely client-side via ONNX Runtime WebAssembly. Unlike Stockfish which plays the strongest move, Maia predicts what a human at a given rating (1100-1900) would actually play, including realistic mistakes.

## Reference Implementation
The Maia platform frontend at `/tmp/maia-platform-frontend/` has a complete working implementation. Key files to port:

### Engine Layer (port these)
1. **`/tmp/maia-platform-frontend/public/maia-worker.js`** — Web Worker that loads ONNX model, handles inference. Uses IndexedDB for caching the 45MB model.
2. **`/tmp/maia-platform-frontend/src/lib/engine/maia.ts`** — Main Maia class that communicates with the worker. Handles model download, inference requests, status tracking.
3. **`/tmp/maia-platform-frontend/src/lib/engine/tensor.ts`** — FEN to tensor conversion, legal move masks, move mirroring for black. Contains `preprocessMaia3()` and `allPossibleMovesMaia3Reversed`.
4. **`/tmp/maia-platform-frontend/src/lib/engine/storage.ts`** — IndexedDB wrapper for model caching.
5. **`/tmp/maia-platform-frontend/src/lib/engine/data/all_moves_maia3.json`** and **`all_moves_maia3_reversed.json`** — Move index mappings (4352 moves).

### Static Assets (copy these)
6. **`/tmp/maia-platform-frontend/public/maia3/maia3_simplified.onnx`** — The 45MB ONNX model file.
7. **`/tmp/maia-platform-frontend/public/ort/`** — ONNX Runtime WASM files (ort.wasm.min.js, ort-wasm-simd-threaded.wasm, ort-wasm-simd-threaded.mjs).
8. **`/tmp/maia-platform-frontend/public/maia-worker.js`** — Copy to Chesster's public folder.

## Chesster Context
- **Stack:** Next.js 16, TypeScript, Tailwind CSS, chess.js v1.4.0, chessground v9.2.1, react-chessboard v4.7.3
- **Repo:** `/root/chess-app/`
- **Frontend:** `/root/chess-app/frontend/`
- **Existing chess board:** `react-chessboard` component used in analysis views
- **No existing play page:** Need to create `/app/play/` route
- **Package manager:** Check `package-lock.json` vs `yarn.lock` to determine

## Implementation Steps

### Phase 1: Engine Layer
1. Copy ONNX Runtime WASM files from `/tmp/maia-platform-frontend/public/ort/` to `/root/chess-app/frontend/public/ort/`
2. Copy the Maia model from `/tmp/maia-platform-frontend/public/maia3/maia3_simplified.onnx` to `/root/chess-app/frontend/public/maia3/maia3_simplified.onnx`
3. Copy `maia-worker.js` to `/root/chess-app/frontend/public/maia-worker.js`
4. Copy the JSON data files (`all_moves_maia3.json`, `all_moves_maia3_reversed.json`) to `/root/chess-app/frontend/src/lib/maia/data/`
5. Port `tensor.ts` to `/root/chess-app/frontend/src/lib/maia/tensor.ts` — adapt imports to use chess.js instead of chess.ts
6. Port `storage.ts` to `/root/chess-app/frontend/src/lib/maia/storage.ts`
7. Port `maia.ts` to `/root/chess-app/frontend/src/lib/maia/maia.ts`
8. Install `onnxruntime-web` as a dependency (needed for Tensor type)

### Phase 2: React Hook
9. Create `useMaia` hook at `/root/chess-app/frontend/src/hooks/useMaia.ts`:
   - Manages Maia instance lifecycle
   - Exposes: `status`, `progress`, `error`, `evaluatePosition(fen, eloSelf, eloOppo)`, `downloadModel()`
   - Returns move probabilities from which the caller picks a move

### Phase 3: Play Page
10. Create `/root/chess-app/frontend/src/app/play/page.tsx`:
    - **Pre-game setup:** Rating slider (1100-1900), color picker (white/black/random)
    - **Game board:** Use `react-chessboard` or `chessground` (match existing app pattern)
    - **Game state:** Managed with chess.js
    - **Maia integration:** After user moves, call `evaluatePosition()`, select move via temperature sampling, apply with 0.5-2s delay
    - **Move selection logic:** Temperature-based sampling from probability distribution (not always top-1) for human-like variety
    - **Game over:** Show result, option to play again or analyze with Stockfish
    - **Model download:** On first visit, show download prompt with progress bar (45MB one-time download, cached in IndexedDB)

### Phase 4: Navigation
11. Add "Play" link to the Navbar component at `/root/chess-app/frontend/src/components/Navbar.tsx`

## Key Technical Notes

### Move Selection (Temperature Sampling)
```typescript
function selectMove(moveProbs: Record<string, number>, temperature: number = 1.0): string {
  const moves = Object.keys(moveProbs);
  const probs = moves.map(m => moveProbs[m]);

  // Apply temperature
  const scaled = probs.map(p => Math.pow(p, 1 / temperature));
  const sum = scaled.reduce((a, b) => a + b, 0);
  const normalized = scaled.map(p => p / sum);

  // Weighted random selection
  let r = Math.random();
  for (let i = 0; i < moves.length; i++) {
    r -= normalized[i];
    if (r <= 0) return moves[i];
  }
  return moves[moves.length - 1];
}
```

### chess.ts vs chess.js
The reference code uses `chess.ts` (a fork). Chesster uses `chess.js`. The API is nearly identical:
- `new Chess(fen)` — same
- `.moves({ verbose: true })` — same
- `.fen()` — same
- Move format `{ from, to, promotion }` — same

Just change the import from `chess.ts` to `chess.js`.

### Model URL
The worker fetches the model from `modelUrl`. In Chesster, set this to `/maia3/maia3_simplified.onnx` (relative to public dir). The worker's `importScripts('/ort/ort.wasm.min.js')` loads ONNX Runtime from the same public dir.

### Important: 'use client' Directive
The play page and useMaia hook use browser APIs (Web Worker, IndexedDB). Mark them with `'use client'`.

## What NOT to Do
- Don't add a backend endpoint — everything runs client-side
- Don't modify existing pages or components (purely additive)
- Don't add Stockfish integration to the play page (that's a separate feature)
- Don't add user accounts/game history persistence (keep it simple for v1)

## Testing
- Verify the model downloads and caches in IndexedDB
- Verify Maia returns valid moves for various positions
- Verify the game loop works: user move → Maia response → board updates
- Verify temperature sampling produces varied moves (not always the same move for the same position)
- Test with both colors (white and black)
- Run `npm run build` to ensure no type errors
