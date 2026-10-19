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
  buildRatingPackUrl,
  fetchRatingPack,
  prefetchAdaptive,
  refillAdaptive,
  prefetchBot,
  refillBot,
  fallbackPoolNearRating,
  ADAPTIVE_BATCH,
  BOT_SPREAD,
  ADAPTIVE_REFILL_THRESHOLD,
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

describe('rating-targeted packs (Adaptive)', () => {
  const query = (url: string) => new URLSearchParams(url.split('?')[1]);

  it('builds a rating= / spread= / count= URL, no level', () => {
    const q = query(buildRatingPackUrl(1340.6, 10, ['a1', 'b2']));
    expect(q.get('rating')).toBe('1341');
    expect(q.get('spread')).toBe('75');
    expect(q.get('count')).toBe('10');
    expect(q.get('exclude')).toBe('a1,b2');
    expect(q.has('level')).toBe(false);
    expect(query(buildRatingPackUrl(1000, 10, [], 150)).get('spread')).toBe('150');
  });

  it('clamps the rating to the backend range', () => {
    expect(query(buildRatingPackUrl(120, 10)).get('rating')).toBe('400');
    expect(query(buildRatingPackUrl(3100, 10)).get('rating')).toBe('2800');
  });

  it('fetches a rating pack and drops excluded ids', async () => {
    const { impl, urls } = mockFetch({ puzzles: [packPuzzle({ id: 'x' }), packPuzzle({ id: 'y' })] });
    const out = await fetchRatingPack({ rating: 900, count: 10, exclude: ['x'], fetchImpl: impl });
    expect(out?.map((p) => p.id)).toEqual(['y']);
    expect(query(urls[0]).get('rating')).toBe('900');
  });

  it('opens with two batches of 10 split between the sides', async () => {
    const { impl, urls } = mockFetch({ puzzles: pack(ADAPTIVE_BATCH * 2) });
    const res = await prefetchAdaptive({ rating: 820, fetchImpl: impl, rng: () => 0.5 });
    expect(query(urls[0]).get('count')).toBe(String(ADAPTIVE_BATCH * 2));
    expect(res.usedFallback).toBe(false);
    expect(res.queueA.length + res.queueB.length).toBe(ADAPTIVE_BATCH * 2);
  });

  it('refills one batch of 10 around the current target, excluding what was dealt', async () => {
    const { impl, urls } = mockFetch({ puzzles: pack(ADAPTIVE_BATCH, 'r') });
    const deltas = await refillAdaptive({ rating: 1150, exclude: ['p0', 'p1'], fetchImpl: impl });
    const q = query(urls[0]);
    expect([q.get('rating'), q.get('count'), q.get('exclude')]).toEqual(['1150', '10', 'p0,p1']);
    expect(deltas!.queueA.length + deltas!.queueB.length).toBe(ADAPTIVE_BATCH);
    expect(await refillAdaptive({ rating: 1150, exclude: [], fetchImpl: rejectingFetch })).toBeNull();
  });

  it('refills sooner than the fixed modes (small queues follow the target)', () => {
    const board = (left: number) => ({ puzzles: pack(10), index: 10 - left });
    expect(needsRefill([board(4), board(5)], ADAPTIVE_REFILL_THRESHOLD)).toBe(false);
    expect(needsRefill([board(3), board(5)], ADAPTIVE_REFILL_THRESHOLD)).toBe(true);
  });

  it('falls back offline to the bundled puzzles nearest the rating', async () => {
    const res = await prefetchAdaptive({ rating: 700, fetchImpl: rejectingFetch });
    expect(res.usedFallback).toBe(true);
    expect(res.themesUnavailable).toBe(false);
    const dealt = [...res.queueA, ...res.queueB];
    expect(dealt.length).toBe(ADAPTIVE_BATCH * 2);
    const worstDealt = Math.max(...dealt.map((p) => Math.abs(p.rating - 700)));
    const dealtIds = new Set(dealt.map((p) => p.id));
    for (const p of TUG_PUZZLES) {
      if (!dealtIds.has(p.id)) expect(Math.abs(p.rating - 700)).toBeGreaterThanOrEqual(worstDealt);
    }
  });

  it('nearest-rating pool is sorted by distance and sized', () => {
    const pool = fallbackPoolNearRating(1600, 5);
    expect(pool).toHaveLength(5);
    const d = pool.map((p) => Math.abs(p.rating - 1600));
    expect(d).toEqual([...d].sort((a, b) => a - b));
  });
});

describe('fixed-rank bot packs (rating=, ±150)', () => {
  const query = (url: string) => new URLSearchParams(url.split('?')[1]);

  it('opens with a full match pack within ±150 of the bot rating', async () => {
    const { impl, urls } = mockFetch({ puzzles: pack(START_PER_TEAM * 2) });
    const res = await prefetchBot({ rating: 1400, fetchImpl: impl, rng: () => 0.5 });
    const q = query(urls[0]);
    expect([q.get('rating'), q.get('spread'), q.get('count'), q.has('level')]).toEqual([
      '1400',
      String(BOT_SPREAD),
      String(START_PER_TEAM * 2),
      false,
    ]);
    expect(BOT_SPREAD).toBe(150);
    expect(res.usedFallback).toBe(false);
    expect(res.queueA.length + res.queueB.length).toBe(START_PER_TEAM * 2);
  });

  it('refills a full pack near the same rating, excluding what was dealt', async () => {
    const { impl, urls } = mockFetch({ puzzles: pack(REFILL_COUNT, 'r') });
    const deltas = await refillBot({ rating: 800, exclude: ['p0'], fetchImpl: impl });
    const q = query(urls[0]);
    expect([q.get('rating'), q.get('spread'), q.get('count'), q.get('exclude')]).toEqual([
      '800',
      '150',
      String(REFILL_COUNT),
      'p0',
    ]);
    expect(deltas!.queueA.length + deltas!.queueB.length).toBe(REFILL_COUNT);
    expect(await refillBot({ rating: 800, exclude: [], fetchImpl: rejectingFetch })).toBeNull();
  });

  it('falls back offline to the bundled puzzles closest to the bot rating', async () => {
    const res = await prefetchBot({ rating: 1700, fetchImpl: rejectingFetch });
    expect(res.usedFallback).toBe(true);
    const dealt = [...res.queueA, ...res.queueB];
    expect(dealt.map((p) => p.id).sort()).toEqual(fallbackPoolNearRating(1700, START_PER_TEAM * 2).map((p) => p.id).sort());
  });
});
