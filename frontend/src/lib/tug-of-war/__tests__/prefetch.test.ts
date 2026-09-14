import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import {
  mapApiPuzzle,
  buildPuzzleUrl,
  fallbackPool,
  prefetchPuzzles,
  TUG_LEVELS,
  type PuzzleApiData,
} from '../prefetch';
import { TUG_PUZZLES } from '../puzzles';

/** A realistic API payload: `FEN` is the solver-to-move position (after the
 * opponent's `preMove`), `moves` is the solution from that turn. */
function apiPuzzle(over: Partial<PuzzleApiData> = {}): PuzzleApiData {
  return {
    lichessId: 'abc12',
    previousFEN: '5rk1/5ppp/8/8/8/8/5PPP/R5K1 b - - 0 1',
    FEN: '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1',
    moves: 'a1a8',
    preMove: 'f8f6',
    rating: 1100,
    themes: ['backRankMate', 'mateIn1'],
    gameURL: 'https://lichess.org/abc12',
    ...over,
  };
}

/** Build a mock fetch that returns the given sequence of puzzles (cycling). */
function mockFetch(puzzles: (PuzzleApiData | null)[]): typeof fetch {
  let i = 0;
  return (async () => {
    const data = puzzles[i % puzzles.length];
    i += 1;
    return {
      ok: data !== null,
      json: async () => (data ? { success: true, data } : { success: false }),
    } as Response;
  }) as unknown as typeof fetch;
}

describe('mapApiPuzzle', () => {
  it('maps the API shape onto the internal puzzle type', () => {
    const mapped = mapApiPuzzle(apiPuzzle());
    expect(mapped).not.toBeNull();
    expect(mapped!.id).toBe('abc12');
    expect(mapped!.fen).toBe('6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1');
    expect(mapped!.moves).toEqual(['a1a8']);
    expect(mapped!.rating).toBe(1100);
    expect(mapped!.themes).toContain('backRankMate');
  });

  it('uses FEN (not previousFEN) and keeps the solver to move — never prepends preMove', () => {
    const data = apiPuzzle();
    const mapped = mapApiPuzzle(data)!;
    // The shown position is exactly the API FEN, not the pre-setup position.
    expect(mapped.fen).toBe(data.FEN);
    expect(mapped.fen).not.toBe(data.previousFEN);

    const chess = new Chess(mapped.fen);
    // Solver is to move in the shown position.
    expect(chess.turn()).toBe('w');
    // The first solution move is legal from the shown position...
    const first = mapped.moves[0];
    const legal = chess
      .moves({ verbose: true })
      .some((m) => `${m.from}${m.to}` === first.slice(0, 4));
    expect(legal).toBe(true);
    // ...and it is the solver's move, not the opponent's setup move.
    expect(first).not.toBe(data.preMove);
  });

  it('splits multi-move UCI strings into an array', () => {
    const mapped = mapApiPuzzle(apiPuzzle({ moves: 'e2e4 e7e5 g1f3' }))!;
    expect(mapped.moves).toEqual(['e2e4', 'e7e5', 'g1f3']);
  });

  it('returns null for payloads missing FEN or moves', () => {
    expect(mapApiPuzzle(null)).toBeNull();
    expect(mapApiPuzzle(apiPuzzle({ moves: '' }))).toBeNull();
    expect(mapApiPuzzle({ ...apiPuzzle(), FEN: undefined as unknown as string })).toBeNull();
  });
});

describe('buildPuzzleUrl', () => {
  it('maps a level to its rating band and joins themes with commas', () => {
    const url = buildPuzzleUrl('rook', ['fork', 'pin']);
    expect(url).toContain('/api/puzzle?');
    expect(url).toContain('ratingFrom=1200');
    expect(url).toContain('ratingTo=1600');
    expect(url).toContain('themes=fork%2Cpin');
  });

  it('omits themes when none are selected', () => {
    const url = buildPuzzleUrl('pawn', []);
    expect(url).not.toContain('themes=');
    expect(url).toContain('ratingFrom=400');
    expect(url).toContain('ratingTo=800');
  });
});

describe('prefetchPuzzles — live path', () => {
  it('returns two disjoint queues from live puzzles', async () => {
    const pool = Array.from({ length: 50 }, (_, i) =>
      apiPuzzle({ lichessId: `id${i}` }),
    );
    const { queueA, queueB, usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      fetchImpl: mockFetch(pool),
      rng: () => 0.42,
    });
    expect(usedFallback).toBe(false);
    const aIds = new Set(queueA.map((p) => p.id));
    expect(queueB.some((p) => aIds.has(p.id))).toBe(false); // disjoint
    expect(queueA.length).toBeGreaterThanOrEqual(1);
    expect(queueB.length).toBeGreaterThanOrEqual(1);
  });

  it('deduplicates by lichessId', async () => {
    // Every call returns the SAME puzzle → only one usable → fallback triggers,
    // proving the dedupe collapsed the duplicates.
    const { usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      fetchImpl: mockFetch([apiPuzzle({ lichessId: 'dup' })]),
    });
    expect(usedFallback).toBe(true);
  });
});

describe('prefetchPuzzles — fallback path', () => {
  it('falls back when every request fails', async () => {
    const { queueA, queueB, usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      fetchImpl: mockFetch([null]),
    });
    expect(usedFallback).toBe(true);
    expect(queueA.length + queueB.length).toBeGreaterThan(0);
    // Fallback queues are still disjoint.
    const aIds = new Set(queueA.map((p) => p.id));
    expect(queueB.some((p) => aIds.has(p.id))).toBe(false);
  });

  it('falls back when fewer than the minimum usable puzzles are returned', async () => {
    const pool = Array.from({ length: 5 }, (_, i) => apiPuzzle({ lichessId: `x${i}` }));
    const { usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      count: 5,
      fetchImpl: mockFetch(pool),
    });
    expect(usedFallback).toBe(true);
  });

  it('honors a lower minUsable so a small live batch is accepted', async () => {
    const pool = Array.from({ length: 6 }, (_, i) => apiPuzzle({ lichessId: `y${i}` }));
    const { usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      count: 6,
      minUsable: 4,
      fetchImpl: mockFetch(pool),
    });
    expect(usedFallback).toBe(false);
  });
});

describe('fallbackPool', () => {
  it('filters the bundled set by rating band', () => {
    const pool = fallbackPool('pawn', []);
    const band = TUG_LEVELS.find((l) => l.id === 'pawn')!;
    expect(pool.length).toBeGreaterThan(0);
    for (const p of pool) {
      expect(p.rating).toBeGreaterThanOrEqual(band.ratingFrom);
      expect(p.rating).toBeLessThanOrEqual(band.ratingTo);
    }
  });

  it('never returns an empty pool even for an out-of-range band', () => {
    // The bundled set tops out well below the Queen band, so this must widen
    // back to the full set rather than stall the game.
    const pool = fallbackPool('queen', []);
    expect(pool.length).toBe(TUG_PUZZLES.length);
  });
});
