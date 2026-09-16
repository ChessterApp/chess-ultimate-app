import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import {
  mapApiPuzzle,
  buildPuzzleUrl,
  fallbackPool,
  fallbackPoolWithMeta,
  prefetchPuzzles,
  TUG_LEVELS,
  type PuzzleApiData,
} from '../prefetch';
import { TUG_PUZZLES } from '../puzzles';
import type { TugPuzzle } from '../types';

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

describe('prefetchPuzzles — early start + background top-up', () => {
  it('starts the match as soon as minUsable puzzles arrive (not the full count)', async () => {
    const pool = Array.from({ length: 60 }, (_, i) => apiPuzzle({ lichessId: `e${i}` }));
    const { queueA, queueB, usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      count: 60,
      batchSize: 8,
      minUsable: 8,
      fetchImpl: mockFetch(pool),
      rng: () => 0.42,
    });
    expect(usedFallback).toBe(false);
    // Started on the first batch of 8 — not after collecting all 60.
    expect(queueA.length + queueB.length).toBe(8);
  });

  it('streams the remaining puzzles to onTopUp after the early start', async () => {
    const pool = Array.from({ length: 24 }, (_, i) => apiPuzzle({ lichessId: `t${i}` }));
    const deltas: TugPuzzle[] = [];
    const { queueA, queueB, usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      count: 24,
      batchSize: 8,
      minUsable: 8,
      fetchImpl: mockFetch(pool),
      onTopUp: (a, b) => deltas.push(...a, ...b),
    });
    // Let the background batches drain.
    await new Promise((r) => setTimeout(r, 50));
    expect(usedFallback).toBe(false);
    const initial = queueA.length + queueB.length;
    expect(initial).toBe(8);
    expect(deltas.length).toBe(16); // the other two batches streamed in
    // Initial queues and top-ups are all distinct puzzles.
    const allIds = new Set([...queueA, ...queueB, ...deltas].map((p) => p.id));
    expect(allIds.size).toBe(24);
  });
});

describe('prefetchPuzzles — per-request timeout', () => {
  it('aborts a request that exceeds the per-request timeout', async () => {
    // Every request hangs until aborted; only the per-request timeout can rescue
    // us. If it did not fire, this test would hang until the runner times out.
    const hangingFetch = ((_url: string, init?: { signal?: AbortSignal }) =>
      new Promise<Response>((_resolve, reject) => {
        const s = init?.signal;
        if (s) s.addEventListener('abort', () => reject(new Error('aborted')));
      })) as unknown as typeof fetch;

    const { usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      count: 8,
      batchSize: 8,
      requestTimeoutMs: 20,
      fetchImpl: hangingFetch,
    });
    expect(usedFallback).toBe(true);
  });

  it('does not abort fast requests under a generous timeout', async () => {
    const pool = Array.from({ length: 20 }, (_, i) => apiPuzzle({ lichessId: `f${i}` }));
    const { usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      requestTimeoutMs: 1000,
      fetchImpl: mockFetch(pool),
    });
    expect(usedFallback).toBe(false);
  });
});

describe('prefetchPuzzles — fallback only on real failure', () => {
  it('falls back immediately when the first batch is entirely unusable', async () => {
    // First 8 requests fail, later ones would succeed — but a dead first batch
    // means the API is down, so we fall back rather than grind through 60 calls.
    const pool = Array.from({ length: 24 }, (_, i) => apiPuzzle({ lichessId: `r${i}` }));
    let call = 0;
    const failFirstBatch = (async () => {
      const failing = call < 8;
      call += 1;
      const data = failing ? null : pool[call % pool.length];
      return {
        ok: data !== null,
        json: async () => (data ? { success: true, data } : { success: false }),
      } as Response;
    }) as unknown as typeof fetch;

    const { usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      count: 24,
      batchSize: 8,
      fetchImpl: failFirstBatch,
    });
    expect(usedFallback).toBe(true);
  });

  it('does NOT fall back when the API is slow-but-working (threshold met later)', async () => {
    // Alternating hits/misses: the first batch yields 4 usable (below the
    // threshold of 8) but the second batch pushes it over — a working API, so no
    // fallback even though 20 never arrived.
    let call = 0;
    const alternating = (async () => {
      const hit = call % 2 === 0;
      const data = hit ? apiPuzzle({ lichessId: `a${call}` }) : null;
      call += 1;
      return {
        ok: data !== null,
        json: async () => (data ? { success: true, data } : { success: false }),
      } as Response;
    }) as unknown as typeof fetch;

    const { usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      count: 24,
      batchSize: 8,
      minUsable: 8,
      fetchImpl: alternating,
    });
    expect(usedFallback).toBe(false);
  });

  it('flags themesUnavailable when the offline fallback cannot honor the theme', async () => {
    // Queen band + fork: the live API fails and the bundled set has no forks in
    // that band, so the result honestly flags the theme as unavailable.
    const { usedFallback, themesUnavailable } = await prefetchPuzzles({
      level: 'queen',
      themes: ['fork'],
      fetchImpl: mockFetch([null]),
    });
    expect(usedFallback).toBe(true);
    expect(themesUnavailable).toBe(true);
  });

  it('does not flag themesUnavailable when the fallback can honor the theme', async () => {
    const { usedFallback, themesUnavailable } = await prefetchPuzzles({
      level: 'pawn',
      themes: ['fork'],
      fetchImpl: mockFetch([null]),
    });
    expect(usedFallback).toBe(true);
    expect(themesUnavailable).toBe(false);
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

  it('offers a varied pool for the default (no-theme) Knight band', () => {
    // The Knight band (800–1200) now catches the rating-900 mate-in-2s AND the
    // rating-1000 tactics, so it has genuine variety without widening to the
    // whole set. Players are never trapped on a single puzzle shape.
    const pool = fallbackPool('knight', []);
    expect(new Set(pool.map((p) => p.rating)).size).toBeGreaterThan(1);
    expect(pool.some((p) => p.themes.includes('mateIn2'))).toBe(true);
    expect(pool.some((p) => p.themes.includes('fork'))).toBe(true);
  });
});

describe('fallbackPoolWithMeta — theme honesty', () => {
  it('honors a theme filter that the bundled band can satisfy', () => {
    for (const level of ['pawn', 'knight', 'rook'] as const) {
      for (const theme of ['fork', 'pin', 'skewer']) {
        const { pool, themesHonored } = fallbackPoolWithMeta(level, [theme]);
        expect(themesHonored, `${level}/${theme} should be honored`).toBe(true);
        expect(pool.length, `${level}/${theme} pool`).toBeGreaterThan(0);
        // Every returned puzzle actually carries the requested theme.
        expect(pool.every((p) => p.themes.includes(theme)), `${level}/${theme}`).toBe(true);
      }
    }
  });

  it('signals — rather than silently discards — when a theme cannot be honored', () => {
    // The Queen band (1600–2400) has no bundled tactics, so a fork filter there
    // cannot be honored; the pool is still playable but the flag says so.
    const { pool, themesHonored } = fallbackPoolWithMeta('queen', ['fork']);
    expect(themesHonored).toBe(false);
    expect(pool.length).toBeGreaterThan(0);
  });

  it('reports themes vacuously honored when none were requested', () => {
    expect(fallbackPoolWithMeta('pawn', []).themesHonored).toBe(true);
  });
});
