'use client';

import { useEffect, useRef, useState } from 'react';
import { EngineName } from '../engine/engine';
import { Stockfish11 } from '../engine/Stockfish11';
import { Stockfish16 } from '../engine/Stockfish16';
import { Stockfish17 } from '../engine/Stockfish17';
import { Stockfish17Point } from '../engine/Stockfish17Point';
import { UciEngine } from '../engine/UciEngine';

/** Ordered fallback chain from strongest to weakest. */
const FALLBACK_ORDER: EngineName[] = [
    EngineName.Stockfish17Point,
    EngineName.Stockfish17,
    EngineName.Stockfish16,
    EngineName.Stockfish11,
];

/**
 * Creates an engine instance for the given name, or null if unsupported.
 * Returns null (skip) instead of throwing for `isSupported()` failures.
 */
function createEngine(name: EngineName): UciEngine | null {
    switch (name) {
        case EngineName.Stockfish17Point:
            return Stockfish17Point.isSupported() ? new Stockfish17Point() : null;
        case EngineName.Stockfish17:
            return Stockfish17.isSupported() ? new Stockfish17() : null;
        case EngineName.Stockfish16:
            return Stockfish16.isSupported() ? new Stockfish16() : null;
        case EngineName.Stockfish11:
            return new Stockfish11();
    }
}

/**
 * Attempts to initialize engines starting from `preferred`, falling back
 * through weaker engines until one succeeds. SF11 is the final fallback.
 */
async function initWithFallback(preferred: EngineName): Promise<UciEngine> {
    const startIndex = FALLBACK_ORDER.indexOf(preferred);
    const candidates = FALLBACK_ORDER.slice(startIndex);

    for (const name of candidates) {
        const engine = createEngine(name);
        if (!engine) continue;

        try {
            await engine.init();
            if (!engine.crashed) return engine;
            engine.shutdown();
        } catch (err) {
            console.warn(`${name} init failed, trying next:`, err);
        }
    }

    throw new Error('All Stockfish engines failed to initialize');
}

export const useEngine = (enabled: boolean, engineName: EngineName | undefined) => {
    const [engine, setEngine] = useState<UciEngine>();
    const engineRef = useRef<UciEngine | undefined>(undefined);

    useEffect(() => {
        if (!enabled || !engineName) return;

        let cancelled = false;

        initWithFallback(engineName).then((eng) => {
            if (cancelled) {
                eng.shutdown();
                return;
            }
            engineRef.current = eng;
            setEngine(eng);
        }).catch((err) => {
            console.error('Engine fallback chain exhausted:', err);
        });

        return () => {
            cancelled = true;
            engineRef.current?.shutdown();
            engineRef.current = undefined;
            setEngine(undefined);
        };
    }, [enabled, engineName]);

    return engine;
};
