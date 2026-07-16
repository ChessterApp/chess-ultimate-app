# PRD: Fix Stockfish SIMD Crashes & Upgrade Fallback Chains

## Problem
SF17/SF17.1 crash silently on devices without full SIMD support because:
1. `isSupported()` only validates basic WASM — never checks SIMD v128
2. No `onCrash` handler wired — crashes hang silently forever
3. No SIMD smoke test (SF16 has one but it's never called)
4. SharedArrayBuffer requirement not checked (SF17 multi-threaded)

Additionally, fallback chains are incomplete:
- `useReplayStockfish`: SF16 → SF11 (skips SF17 entirely)
- `useStockfishPlay`: SF16 only, no fallback
- `useEngine`: No fallback at all — crash = silent hang

## Implementation Plan

### File 1: `src/stockfish/engine/Stockfish17.ts`
**Changes:**
1. **Add SIMD validation to `isSupported()`** — copy SF16's SIMD v128 binary check (line 49 of Stockfish16.ts):
   ```ts
   public static isSupported() {
       return (
           typeof WebAssembly === 'object' &&
           WebAssembly.validate(Uint8Array.of(0x0, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00)) &&
           // SIMD check — SF17 WASM requires SIMD support
           WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,10,10,1,8,0,65,0,253,15,253,98,11]))
       );
   }
   ```

2. **Wire `onCrash` handler in constructor** — same pattern as SF16 (line 11 of Stockfish16.ts):
   ```ts
   constructor() {
       if (!Stockfish17.isSupported()) {
           throw new Error('Stockfish 17 is not supported');
       }
       const enginePath = '/static/engine/stockfish-17/stockfish-17-lite.js#...';
       const onCrash = (err: unknown) => this.handleCrash(err);
       const worker = UciEngine.workerFromPath(enginePath, onCrash);
       super(EngineName.Stockfish17, worker);
   }
   ```

3. **Add `smokeTestSimd()` static method** — reuse SF16's exact WASM bytes (lines 61-122 of Stockfish16.ts), just change the guard to call `Stockfish17.isSupported()`.

4. **Add `sendUciCommands()` public wrapper** — same as SF16 (lines 31-37), needed if SF17 is used in play mode.

### File 2: `src/stockfish/engine/Stockfish17Point.ts`
**Same changes as Stockfish17.ts:**
1. Add SIMD v128 check to `isSupported()`
2. Wire `onCrash` in constructor
3. Add `smokeTestSimd()` static method
4. Add `sendUciCommands()` public wrapper

### File 3: `src/hooks/useReplayStockfish.ts`
**Changes:**
1. **Import SF17Point** — add `import { Stockfish17Point } from '@/stockfish/engine/Stockfish17Point'`
2. **Update `EngineVariant` type** — add `'sf17'` to the union: `'sf17' | 'sf16' | 'sf11' | null`
3. **Update `toEngineVariant()`** — add SF17Point mapping
4. **Add Tier 0 before Tier 1** — try SF17Point first (8s timeout), fall through to SF16 on failure:
   ```ts
   // Tier 0: Try SF17.1 (latest NNUE, requires SIMD)
   try {
     const engine = await tryInitEngine(
       () => new Stockfish17Point(),
       SF16_INIT_TIMEOUT_MS,
       mountedRef,
       () => { if (mountedRef.current) handleEngineFailure('...') },
     );
     if (mountedRef.current) {
       engineRef.current = engine;
       // ... set state
       return;
     }
   } catch {
     if (!mountedRef.current) return;
   }
   // Tier 1: Try SF16 (existing code)
   // Tier 2: Fallback to SF11 (existing code)
   ```

### File 4: `src/hooks/useStockfishPlay.ts`
**Changes:**
1. **Import SF17Point and SF11** — add imports
2. **Add fallback chain** — wrap init in try/catch cascade:
   ```ts
   // Try SF17.1 first (has sendUciCommands after File 2 changes)
   // If fails → try SF16 (current behavior)
   // If fails → try SF11 (basic HCE, always works)
   ```
3. **Update `engineRef` type** to `UciEngine` (currently `Stockfish16`)
4. **Add `sendUciCommands` call via type assertion or interface** — SF11 doesn't have `sendUciCommands`, so either:
   - Option A: Add `sendUciCommands` to UciEngine base class (cleanest)
   - Option B: Type-narrow in `getMove()` — check if engine has the method

   **Recommendation:** Option A — move `sendUciCommands` from Stockfish16 to UciEngine base class. It's just a public wrapper for `sendCommands`. This makes all engines usable in play mode.

### File 5: `src/stockfish/engine/UciEngine.ts` (if Option A)
**Change:**
1. **Make `sendCommands` public** by adding a public `sendUciCommands` wrapper in the base class:
   ```ts
   public async sendUciCommands(
       commands: string[],
       finalMessage: string,
       onNewMessage?: (messages: string[]) => void,
   ): Promise<string[]> {
       return this.sendCommands(commands, finalMessage, onNewMessage);
   }
   ```
   Then remove the duplicate from Stockfish16.ts.

### File 6: `src/stockfish/hooks/useEngine.ts`
**Changes:**
1. **Add fallback on init failure** — if the selected engine fails, try the next one in chain:
   ```ts
   const FALLBACK_ORDER = [
     EngineName.Stockfish17Point,
     EngineName.Stockfish17,
     EngineName.Stockfish16,
     EngineName.Stockfish11,
   ];

   // Try selected engine first, then fall through the chain
   const startIdx = FALLBACK_ORDER.indexOf(engineName);
   const candidates = startIdx >= 0
     ? FALLBACK_ORDER.slice(startIdx)
     : [engineName, ...FALLBACK_ORDER];

   for (const candidate of candidates) {
     try {
       const engine = pickEngine(candidate);
       await engine.init();
       setEngine(engine);
       return;
     } catch {
       continue;
     }
   }
   ```

## Files Changed (6 total)
1. `src/stockfish/engine/Stockfish17.ts` — SIMD check, onCrash, smokeTest
2. `src/stockfish/engine/Stockfish17Point.ts` — SIMD check, onCrash, smokeTest
3. `src/hooks/useReplayStockfish.ts` — SF17.1 → SF16 → SF11 chain
4. `src/hooks/useStockfishPlay.ts` — SF17.1 → SF16 → SF11 chain
5. `src/stockfish/engine/UciEngine.ts` — public sendUciCommands on base
6. `src/stockfish/hooks/useEngine.ts` — fallback chain on init failure

## Testing
- Existing tests in `Stockfish16.test.ts` pattern should be extended to SF17/SF17Point
- Test SIMD validation mocking
- Test crash handler wiring
- Test fallback chains in hooks (mock engine init failures)

## Risk Assessment
- **Low risk:** SIMD check and onCrash are proven patterns from SF16
- **Medium risk:** Changing useEngine fallback behavior — users who explicitly picked SF17 will now silently fall back instead of failing. This is better UX but changes expectations.
- **No breaking changes:** All existing SF16/SF11 behavior preserved as-is.
