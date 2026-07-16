# PRD: Stockfish Crash Fix — Phase 2 (Remaining Files)

Phase 1 (done) fixed `useReplayStockfish`. This phase completes the remaining 4 files.

**IMPORTANT: Do NOT touch useReplayStockfish.ts — it's already done. Do NOT add PowerSync or any unrelated changes. ONLY modify the 4 files below.**

## File 1: `src/stockfish/engine/Stockfish17.ts`

1. **Add SIMD v128 check to `isSupported()`** — same pattern as Stockfish16.ts line 49:
   ```ts
   public static isSupported() {
       return (
           typeof WebAssembly === 'object' &&
           WebAssembly.validate(Uint8Array.of(0x0, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00)) &&
           WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,10,10,1,8,0,65,0,253,15,253,98,11]))
       );
   }
   ```

2. **Wire `onCrash` handler in constructor** — pass onCrash to `workerFromPath`:
   ```ts
   const onCrash = (err: unknown) => this.handleCrash(err);
   const worker = UciEngine.workerFromPath(enginePath, onCrash);
   ```

3. **Add `smokeTestSimd()` static method** — port from Stockfish16.ts lines 61-122.

## File 2: `src/stockfish/engine/Stockfish17Point.ts`

Same 3 changes as Stockfish17.ts above:
1. SIMD v128 check in `isSupported()`
2. `onCrash` handler in constructor
3. `smokeTestSimd()` static method

## File 3: `src/stockfish/engine/UciEngine.ts`

1. **Add public `sendUciCommands` wrapper** to the base class:
   ```ts
   public async sendUciCommands(
       commands: string[],
       finalMessage: string,
       onNewMessage?: (messages: string[]) => void,
   ): Promise<string[]> {
       return this.sendCommands(commands, finalMessage, onNewMessage);
   }
   ```
2. Then remove the duplicate `sendUciCommands` from `Stockfish16.ts` (it should inherit from base).

## File 4: `src/hooks/useStockfishPlay.ts`

1. **Import SF17Point and SF11**
2. **Add fallback chain**: SF17.1 → SF16 → SF11
3. **Update `engineRef` type** to `UciEngine` (currently `Stockfish16`)
4. Keep existing `getMove()` logic — just ensure `sendUciCommands` is called via the base class method (works after File 3 changes)

## File 5: `src/stockfish/hooks/useEngine.ts`

1. **Add fallback on init failure** — if selected engine fails, try next in chain:
   ```ts
   const FALLBACK_ORDER = [
     EngineName.Stockfish17Point,
     EngineName.Stockfish17,
     EngineName.Stockfish16,
     EngineName.Stockfish11,
   ];
   ```
2. Try selected engine first, then fall through the chain on failure.

## DO NOT TOUCH
- `useReplayStockfish.ts` (already fixed in phase 1)
- Any PowerSync files
- Any files not listed above

## Testing
- Run `npm run build` to verify no TypeScript errors
- Run existing tests if any exist for these files

## Verification Checklist
After implementation, verify:
- [x] Stockfish17.isSupported() includes SIMD check
- [x] Stockfish17Point.isSupported() includes SIMD check
- [x] Both SF17 constructors pass onCrash to workerFromPath
- [x] UciEngine has public sendUciCommands
- [x] Stockfish16 no longer has its own sendUciCommands (inherits from base)
- [ ] useStockfishPlay tries SF17.1 → SF16 → SF11
- [ ] useEngine has fallback chain on init failure
- [ ] `npm run build` passes
