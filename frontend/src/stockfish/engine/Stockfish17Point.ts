import { EngineName } from './engine';
import { UciEngine } from './UciEngine';

/**
 * Runs Stockfish 17
 */
export class Stockfish17Point extends UciEngine {
    constructor() {
        if (!Stockfish17Point.isSupported()) {
            throw new Error('Stockfish 17.1 is not supported');
        }

        const enginePath =
            '/static/engine/stockfish-17/stockfish-17.1-lite-single-03e3232.js#/static/engine/stockfish-17/stockfish-17.1-lite-single-03e3232.wasm';
        const worker = UciEngine.workerFromPath(enginePath);
        super(EngineName.Stockfish17Point, worker);
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
        await this.sendCommands(['position startpos', 'go depth 1'], 'bestmove');
    }

    /**
     * Checks if the browser supports WebAssembly + SIMD v128 opcodes,
     * which are required by the Stockfish 17.1 WASM binary.
     */
    public static isSupported() {
        return (
            typeof WebAssembly === 'object' &&
            WebAssembly.validate(Uint8Array.of(0x0, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00)) &&
            // SIMD check — stockfish-17.1 WASM requires SIMD support
            WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,10,10,1,8,0,65,0,253,15,253,98,11]))
        );
    }
}

