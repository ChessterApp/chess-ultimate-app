# PRD: Stockfish Crash Fix — Phase 3 (Final 2 Items)

Phase 1 fixed `useReplayStockfish`. Phase 2 fixed engine classes + UciEngine base. This phase finishes the last 2 items.

**SCOPE: ONLY these 2 tasks. Do NOT touch any other files. Do NOT add PowerSync, feature flags, or anything unrelated.**

## Task 1: Commit the existing `useStockfishPlay.ts` changes

The code in `frontend/src/hooks/useStockfishPlay.ts` and `frontend/src/hooks/__tests__/useStockfishPlay.test.ts` is ALREADY WRITTEN from Phase 2 but was never committed because tests failed.

Steps:
1. Read the current `useStockfishPlay.ts` and its test file
2. Run the test: `npx vitest run frontend/src/hooks/__tests__/useStockfishPlay.test.ts`
3. If tests fail, fix ONLY the test issues (the implementation code is correct)
4. Run `npm run build` to verify no TypeScript errors
5. Git commit ONLY these 2 files:
   - `frontend/src/hooks/useStockfishPlay.ts`
   - `frontend/src/hooks/__tests__/useStockfishPlay.test.ts`
6. Commit message: `feat: add SF17.1 → SF16 → SF11 fallback chain to useStockfishPlay`

**IMPORTANT:** There are other uncommitted files (useOpeningRepertoire.ts, useSubscription.ts, useUserGames.ts, feature-flags.ts, powersync/). Do NOT commit those — they are from a different task. Only commit the 2 files above.

## Task 2: Add fallback chain to `useEngine.ts`

File: `frontend/src/stockfish/hooks/useEngine.ts`

Current behavior: `pickEngine()` creates the selected engine, `init()` is called, if it fails → empty catch → no engine. User gets nothing.

Required change: If the selected engine fails to init, try the next engine in the fallback chain.

```ts
const FALLBACK_ORDER: EngineName[] = [
    EngineName.Stockfish17Point,
    EngineName.Stockfish17,
    EngineName.Stockfish16,
    EngineName.Stockfish11,
];

async function initWithFallback(selectedEngine: EngineName): Promise<UciEngine | undefined> {
    // Build chain: selected engine first, then remaining in FALLBACK_ORDER
    const chain = [selectedEngine, ...FALLBACK_ORDER.filter(e => e !== selectedEngine)];

    for (const name of chain) {
        const engine = pickEngine(name);
        try {
            await engine.init();
            if (!engine.crashed) return engine;
            engine.shutdown();
        } catch {
            engine.shutdown();
            console.warn(`${name} init failed, trying next...`);
        }
    }
    return undefined;
}
```

Update the `useEffect` to call `initWithFallback(engineName)` instead of `pickEngine(engineName)` + `engine.init()`.

Keep `pickEngine` as-is (it's still used by `initWithFallback`).

After implementing:
1. Write a test file: `frontend/src/stockfish/hooks/__tests__/useEngine.test.ts`
2. Test cases:
   - Selected engine works → uses it
   - Selected engine fails → falls back to next
   - All SIMD engines fail → falls back to SF11
3. Run tests
4. Run `npm run build`
5. Git commit ONLY:
   - `frontend/src/stockfish/hooks/useEngine.ts`
   - `frontend/src/stockfish/hooks/__tests__/useEngine.test.ts`
6. Commit message: `feat: add auto-fallback chain to useEngine hook`

## DO NOT TOUCH
- `useReplayStockfish.ts` (done in Phase 1)
- `Stockfish17.ts`, `Stockfish17Point.ts`, `UciEngine.ts` (done in Phase 2)
- Any PowerSync files
- Any files not listed above

## Verification
After both tasks:
- [x] `useStockfishPlay.ts` committed with fallback chain
- [x] `useEngine.ts` committed with fallback chain
- [x] All tests pass
- [x] `npm run build` passes
