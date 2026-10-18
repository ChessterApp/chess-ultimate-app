import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import {
  mapPackPuzzle,
  buildPackUrl,
  fetchPack,
  fallbackPool,
  fallbackPoolWithMeta,
  prefetchPuzzles,
  refillQueues,
  START_PER_TEAM,
  REFILL_COUNT,
  TUG_LEVELS,
  TUG_THEMES,
} from '../prefetch';
import { needsRefill } from '../queues';
import { TUG_PUZZLES } from '../puzzles';
import type { TugPuzzle } from '../types';

/** A pack puzzle in the backend's solving-position shape. */
function packPuzzle(over: Partial<TugPuzzle> = {}): TugPuzzle {
  return {
    id: 'abc12',
    fen: '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1',
    moves: ['a1a8'],
    rating: 1100,
    themes: ['backRankMate', 'mateIn1'],
    ...over,
  };
}

function pack(n: number, prefix = 'p'): TugPuzzle[] {
  return Array.from({ length: n }, (_, i) => packPuzzle({ id: `${prefix}${i}` }));
}

/** Mock fetch that records requested URLs and answers with `body` (null = HTTP 500). */
function mockFetch(body: unknown | null) {
  const urls: string[] = [];
  const impl = (async (url: string) => {
    urls.push(url);
    return { ok: body !== null, json: async () => body } as Response;
  }) as unknown as typeof fetch;
  return { impl, urls };
}

const rejectingFetch = (async () => {
  throw new Error('offline');
}) as unknown as typeof fetch;

describe('buildPackUrl', () => {
  it('targets the backend pack with level, count, themes and exclude', () => {
    const url = buildPackUrl('rook', ['fork', 'pin'], 60, ['a1', 'b2']);
    expect(url.startsWith('/api/puzzles/tug/pack?')).toBe(true);
    const q = new URLSearchParams(url.split('?')[1]);
    expect(q.get('level')).toBe('rook');
    expect(q.get('count')).toBe('60');
    expect(q.get('themes')).toBe('fork,pin');
    expect(q.get('exclude')).toBe('a1,b2');
  });

  it('omits empty themes and exclude', () => {
    const url = buildPackUrl('pawn', [], 60);
    expect(url).not.toContain('themes=');
    expect(url).not.toContain('exclude=');
  });
});

describe('mapPackPuzzle', () => {
  it('keeps the solving-position puzzle as-is', () => {
    const mapped = mapPackPuzzle(packPuzzle())!;
    expect(mapped).toEqual(packPuzzle());
    const chess = new Chess(mapped.fen);
    // Solver is to move and the first solution move is legal there.
    expect(chess.turn()).toBe('w');
    expect(chess.moves({ verbose: true }).some((m) => m.lan === mapped.moves[0])).toBe(true);
  });

  it('rejects payloads missing id, fen or moves', () => {
    expect(mapPackPuzzle(null)).toBeNull();
    expect(mapPackPuzzle({ ...packPuzzle(), moves: [] })).toBeNull();
    expect(mapPackPuzzle({ ...packPuzzle(), fen: undefined })).toBeNull();
    expect(mapPackPuzzle({ ...packPuzzle(), id: 7 })).toBeNull();
  });
});

describe('fetchPack', () => {
  it('drops duplicates and excluded ids', async () => {
    const { impl } = mockFetch({ puzzles: [...pack(3), packPuzzle({ id: 'p1' })], source: 'lichess' });
    const out = await fetchPack({ level: 'knight', themes: [], count: 4, exclude: ['p0'], fetchImpl: impl });
    expect(out!.map((p) => p.id)).toEqual(['p1', 'p2']);
  });

  it('returns null on HTTP errors, network errors and malformed bodies', async () => {
    expect(await fetchPack({ level: 'pawn', themes: [], count: 1, fetchImpl: mockFetch(null).impl })).toBeNull();
    expect(await fetchPack({ level: 'pawn', themes: [], count: 1, fetchImpl: rejectingFetch })).toBeNull();
    expect(await fetchPack({ level: 'pawn', themes: [], count: 1, fetchImpl: mockFetch({}).impl })).toBeNull();
  });

  it('aborts a request that exceeds the timeout', async () => {
    const hangingFetch = ((_url: string, init?: { signal?: AbortSignal }) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
      })) as unknown as typeof fetch;
    const out = await fetchPack({ level: 'pawn', themes: [], count: 1, timeoutMs: 20, fetchImpl: hangingFetch });
    expect(out).toBeNull();
  });
});

describe('prefetchPuzzles — live path', () => {
  it('makes ONE pack request and starts with 30 disjoint puzzles per team', async () => {
    const { impl, urls } = mockFetch({ puzzles: pack(START_PER_TEAM * 2), source: 'lichess' });
    const { queueA, queueB, usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: ['fork'],
      fetchImpl: impl,
      rng: () => 0.42,
    });
    expect(urls).toHaveLength(1);
    const q = new URLSearchParams(urls[0].split('?')[1]);
    expect(q.get('count')).toBe(String(START_PER_TEAM * 2));
    expect(q.get('themes')).toBe('fork');
    expect(usedFallback).toBe(false);
    expect(queueA).toHaveLength(START_PER_TEAM);
    expect(queueB).toHaveLength(START_PER_TEAM);
    const aIds = new Set(queueA.map((p) => p.id));
    expect(queueB.some((p) => aIds.has(p.id))).toBe(false);
  });

  it('still plays live when a rare theme returns a thin pack', async () => {
    const { impl } = mockFetch({ puzzles: pack(6), source: 'lichess' });
    const { queueA, queueB, usedFallback } = await prefetchPuzzles({ level: 'queen', themes: ['pin'], fetchImpl: impl });
    expect(usedFallback).toBe(false);
    expect(queueA.length + queueB.length).toBe(6);
  });
});

describe('prefetchPuzzles — offline fallback', () => {
  it('falls back to the bundled set when the backend is unreachable', async () => {
    const { queueA, queueB, usedFallback } = await prefetchPuzzles({
      level: 'knight',
      themes: [],
      fetchImpl: rejectingFetch,
    });
    expect(usedFallback).toBe(true);
    const bundled = new Set(TUG_PUZZLES.map((p) => p.id));
    expect([...queueA, ...queueB].every((p) => bundled.has(p.id))).toBe(true);
    const aIds = new Set(queueA.map((p) => p.id));
    expect(queueB.some((p) => aIds.has(p.id))).toBe(false);
  });

  it('falls back on an HTTP error or an empty pack', async () => {
    for (const body of [null, { puzzles: [] }]) {
      const { usedFallback } = await prefetchPuzzles({ level: 'pawn', themes: [], fetchImpl: mockFetch(body).impl });
      expect(usedFallback).toBe(true);
    }
  });

  it('flags themesUnavailable only when the bundled set cannot honor the theme', async () => {
    const honored = await prefetchPuzzles({ level: 'pawn', themes: ['fork'], fetchImpl: rejectingFetch });
    expect(honored.usedFallback).toBe(true);
    expect(honored.themesUnavailable).toBe(false);
    const missing = await prefetchPuzzles({ level: 'pawn', themes: ['notATheme'], fetchImpl: rejectingFetch });
    expect(missing.themesUnavailable).toBe(true);
  });
});

describe('refill', () => {
  it('needsRefill fires once either queue is within the threshold', () => {
    const full = { puzzles: pack(30), index: 0 };
    expect(needsRefill([full, full])).toBe(false);
    expect(needsRefill([full, { puzzles: pack(30), index: 20 }])).toBe(true);
    expect(needsRefill([{ puzzles: pack(30), index: 19 }, full], 10)).toBe(false);
  });

  it('requests a refill pack excluding dealt ids and splits it disjointly', async () => {
    const { impl, urls } = mockFetch({ puzzles: [...pack(REFILL_COUNT, 'r'), packPuzzle({ id: 'p0' })] });
    const deltas = await refillQueues({ level: 'rook', themes: [], exclude: ['p0', 'p1'], fetchImpl: impl });
    const q = new URLSearchParams(urls[0].split('?')[1]);
    expect(q.get('exclude')).toBe('p0,p1');
    expect(q.get('count')).toBe(String(REFILL_COUNT));
    const ids = [...deltas!.queueA, ...deltas!.queueB].map((p) => p.id);
    expect(ids).toHaveLength(REFILL_COUNT);
    expect(ids).not.toContain('p0'); // a repeat the client still filters out
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('returns null when the refill request fails', async () => {
    expect(await refillQueues({ level: 'rook', themes: [], exclude: [], fetchImpl: rejectingFetch })).toBeNull();
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

  it('has a playable pool inside every band', () => {
    for (const band of TUG_LEVELS) {
      const pool = fallbackPool(band.id, []);
      expect(pool.length, band.id).toBeGreaterThanOrEqual(70);
      expect(pool.every((p) => p.rating >= band.ratingFrom && p.rating <= band.ratingTo)).toBe(true);
    }
  });

  it('offers a varied pool for the default (no-theme) Knight band', () => {
    // Players are never trapped on a single puzzle shape.
    const pool = fallbackPool('knight', []);
    expect(new Set(pool.map((p) => p.rating)).size).toBeGreaterThan(1);
    expect(pool.some((p) => p.themes.includes('mateIn2'))).toBe(true);
    expect(pool.some((p) => p.themes.includes('fork'))).toBe(true);
  });
});

describe('fallbackPoolWithMeta — theme honesty', () => {
  it('honors every setup-screen theme in every band', () => {
    for (const { id: level } of TUG_LEVELS) {
      for (const { tag: theme } of TUG_THEMES) {
        const { pool, themesHonored } = fallbackPoolWithMeta(level, [theme]);
        expect(themesHonored, `${level}/${theme} should be honored`).toBe(true);
        expect(pool.length, `${level}/${theme} pool`).toBeGreaterThan(0);
        // Every returned puzzle actually carries the requested theme.
        expect(pool.every((p) => p.themes.includes(theme)), `${level}/${theme}`).toBe(true);
      }
    }
  });

  it('signals — rather than silently discards — when a theme cannot be honored', () => {
    // A tag the bundled set never carries: the pool is still playable but the
    // flag says so.
    const { pool, themesHonored } = fallbackPoolWithMeta('queen', ['notATheme']);
    expect(themesHonored).toBe(false);
    expect(pool.length).toBeGreaterThan(0);
  });

  it('reports themes vacuously honored when none were requested', () => {
    expect(fallbackPoolWithMeta('pawn', []).themesHonored).toBe(true);
  });
});
