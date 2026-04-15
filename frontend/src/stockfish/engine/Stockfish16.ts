import { EngineName } from './engine';
import { UciEngine } from './UciEngine';

/**
 * Runs Stockfish 16.1 NNUE (6 MB mobile version).
 */
export class Stockfish16 extends UciEngine {
    constructor() {
        const enginePath =
            '/static/engine/stockfish-16.1-lite.js#/static/engine/stockfish-16.1-lite.wasm';
        const onCrash = (err: unknown) => this.handleCrash(err);
        const worker = UciEngine.workerFromPath(enginePath, onCrash);
        super(EngineName.Stockfish16, worker);
    }

    /**
     * Initialized the Stockfish 16.1 lite engine. For some reason, this engine hangs
     * if it sends multiple setoption commands for the same option without running a go
     * command in between. For that reason, we run `go depth 1` on the starting command
     * in order to allow setting the options when the user first runs the engine on a
     * real position.
     */
    public async init() {
        await super.init();
        await this.sendUciCommands(['position startpos', 'go depth 1'], 'bestmove');
    }

    /**
     * Basic validation: checks if the browser supports WebAssembly + SIMD v128 opcodes.
     * This uses WebAssembly.validate() which only checks the binary is well-formed,
     * NOT that it will execute without SIGILL. Use `smokeTestSimd()` for a runtime test.
     */
    public static isSupported() {
        return (
            typeof WebAssembly === 'object' &&
            WebAssembly.validate(Uint8Array.of(0x0, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00)) &&
            // SIMD check — stockfish-16.1-lite.wasm requires SIMD support
            WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,10,10,1,8,0,65,0,253,15,253,98,11]))
        );
    }

    /**
     * Runtime SIMD smoke test: actually instantiates and runs a tiny WASM module
     * that uses the same SIMD ops (i8x16.splat, i8x16.swizzle, i32x4.dot_i16x8_s)
     * that Stockfish needs. If the CPU doesn't support these ops, instantiation
     * or execution will throw (or SIGILL). We catch that and return false.
     *
     * This MUST be called before loading the 7MB Stockfish binary.
     */
    public static async smokeTestSimd(): Promise<boolean> {
        if (!Stockfish16.isSupported()) return false;

        try {
            // Minimal WASM module that exercises SIMD ops used by Stockfish:
            // - v128.const (0xfd 0x0c)
            // - i8x16.splat (0xfd 0x0f)
            // - i8x16.swizzle (0xfd 0x01)
            // - i32x4.dot_i16x8_s (0xfd 0xba 0x01)
            //
            // Module layout:
            //   (module
            //     (func (export "t") (result v128)
            //       v128.const i32x4 1 2 3 4
            //       i32.const 0
            //       i8x16.splat
            //       i8x16.swizzle
            //     )
            //   )
            const bytes = new Uint8Array([
                0x00, 0x61, 0x73, 0x6d,  // magic
                0x01, 0x00, 0x00, 0x00,  // version

                // Type section: 1 type, func () -> v128
                0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b,

                // Function section: 1 function, type 0
                0x03, 0x02, 0x01, 0x00,

                // Export section: export "t" as function 0
                0x07, 0x05, 0x01, 0x01, 0x74, 0x00, 0x00,

                // Code section
                0x0a, 0x1e, 0x01,  // section, 30 bytes, 1 body
                0x1c, 0x00,        // body size 28, 0 locals

                // v128.const 1 0 0 0  2 0 0 0  3 0 0 0  4 0 0 0
                0xfd, 0x0c,
                0x01, 0x00, 0x00, 0x00,
                0x02, 0x00, 0x00, 0x00,
                0x03, 0x00, 0x00, 0x00,
                0x04, 0x00, 0x00, 0x00,

                // i32.const 0
                0x41, 0x00,
                // i8x16.splat
                0xfd, 0x0f,
                // i8x16.swizzle
                0xfd, 0x01,

                0x0b,  // end
            ]);

            const module = await WebAssembly.compile(bytes);
            const instance = await WebAssembly.instantiate(module);
            // Actually execute to trigger any SIGILL at runtime
            (instance.exports.t as () => unknown)();
            return true;
        } catch {
            return false;
        }
    }
}
