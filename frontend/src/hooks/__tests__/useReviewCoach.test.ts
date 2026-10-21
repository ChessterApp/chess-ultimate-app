/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { REVIEW_FIXTURE } from '@/components/review/__tests__/fixture';
import {
  useReviewCoach,
  explainCacheKey,
  summaryCacheKey,
  pgnHash,
  formatEval,
  buildExplainQuery,
  buildRecapQuery,
} from '../useReviewCoach';
import type { ReviewMove } from '@/components/review/types';

vi.mock('next-intl', () => ({ useLocale: () => 'en' }));

const MOVE: ReviewMove = {
  ply: 5,
  san: 'cxd4',
  uci: 'c5d4',
  fen: 'rnbqkb1r/pp1p1ppp/4pn2/8/3pP3/2N2N2/PPP2PPP/R1BQKB1R w KQkq - 0 5',
  eval: { type: 'cp', value: 320 },
  best: { uci: 'b8c6', eval: { type: 'cp', value: -10 } },
  second: { uci: 'g8f6', eval: { type: 'cp', value: -20 } },
  winPercent: 79.0,
  accuracy: 12.0,
  classification: 'blunder',
  phase: 'middlegame',
};

// ── SSE stream + fetch scaffolding ──────────────────────────────────────────

/** Build a fake fetch Response whose body streams the given SSE lines. */
function sseResponse(lines: string[]) {
  const enc = new TextEncoder();
  const chunks = lines.map((l) => enc.encode(l));
  let i = 0;
  return {
    ok: true,
    status: 200,
    body: {
      getReader() {
        return {
          read() {
            if (i < chunks.length) {
              return Promise.resolve({ done: false, value: chunks[i++] });
            }
            return Promise.resolve({ done: true, value: undefined });
          },
        };
      },
    },
  };
}

const STREAM_LINES = [
  'data: {"delta":"Because "}\n',
  'data: {"delta":"it drops a pawn."}\n',
  'data: {"model":"claude-opus","done":true}\n',
];

interface FetchOpts {
  /** GET /review-cache response content (null = cache miss). */
  cacheContent?: string | null;
  onStream?: () => void;
  /** SSE lines the stream endpoint returns (default STREAM_LINES). */
  streamLines?: string[];
}

/** Route by URL + method: review-cache GET/POST + analysis/stream. */
function installFetch(opts: FetchOpts = {}) {
  const posts: Array<{ url: string; body: unknown }> = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/coach/review-cache') && method === 'GET') {
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: opts.cacheContent ?? null, model: null }),
      });
    }
    if (url.includes('/api/coach/analysis/stream')) {
      opts.onStream?.();
      return Promise.resolve(sseResponse(opts.streamLines ?? STREAM_LINES));
    }
    if (url.includes('/api/coach/review-cache') && method === 'POST') {
      posts.push({ url, body: init?.body ? JSON.parse(init.body) : null });
      return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
    }
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, posts };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

// ── Pure helpers ─────────────────────────────────────────────────────────────

describe('pure helpers', () => {
  it('builds distinct, versioned cache keys', () => {
    expect(explainCacheKey('FEN', 'e2e4', 'en')).toBe('v1:explain:FEN|e2e4|en');
    expect(summaryCacheKey('abc123', 'ru')).toBe('v1:summary:abc123|ru');
    expect(explainCacheKey('FEN', 'e2e4', 'en')).not.toBe(
      explainCacheKey('FEN', 'e2e4', 'ru'),
    );
  });

  it('pgnHash is stable and order-sensitive', () => {
    const a = pgnHash(REVIEW_FIXTURE.moves);
    const b = pgnHash(REVIEW_FIXTURE.moves);
    expect(a).toBe(b);
    expect(a).toMatch(/^[0-9a-f]{8}$/);
    expect(pgnHash([{ uci: 'e2e4' }, { uci: 'e7e5' }])).not.toBe(
      pgnHash([{ uci: 'e7e5' }, { uci: 'e2e4' }]),
    );
  });

  it('formatEval renders centipawns and mate', () => {
    expect(formatEval({ type: 'cp', value: 120 })).toBe('+1.2');
    expect(formatEval({ type: 'cp', value: -40 })).toBe('−0.4');
    expect(formatEval({ type: 'mate', value: 3 })).toBe('#3');
    expect(formatEval(null)).toBe('n/a');
  });

  it('buildExplainQuery grounds the prompt in the engine truth', () => {
    const q = buildExplainQuery(MOVE, null, undefined, 'en');
    expect(q).toContain('blunder');
    expect(q).toContain('b8c6'); // engine best move must be named
    expect(q).toContain('English');
    expect(q).toContain(MOVE.fen);
  });

  it('buildRecapQuery grounds the recap in the aggregates', () => {
    const q = buildRecapQuery(REVIEW_FIXTURE, 'ru');
    expect(q).toContain('Russian');
    expect(q).toContain('French Defense: Classical Variation');
    expect(q).toContain('5, 6'); // key-moment plies
  });
});

// ── Hook behavior ────────────────────────────────────────────────────────────

describe('useReviewCoach.explainMove', () => {
  it('streams a fresh explanation and writes through to the cache (happy path)', async () => {
    const { fetchMock, posts } = installFetch({ cacheContent: null });
    const { result } = renderHook(() => useReviewCoach());

    await act(async () => {
      await result.current.explainMove(MOVE, null);
    });

    const key = explainCacheKey(MOVE.fen, MOVE.uci, 'en');
    const entry = result.current.explainByKey[key];
    expect(entry.status).toBe('done');
    expect(entry.content).toBe('Because it drops a pawn.');
    expect(entry.error).toBeNull();

    // Stream endpoint was hit, and the result was persisted with model+kind.
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/coach/analysis/stream',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({ cache_key: key, kind: 'explain', model: 'claude-opus' });
  });

  it('serves a persistent-cache hit without calling the stream endpoint', async () => {
    const { fetchMock } = installFetch({ cacheContent: 'Cached explanation.' });
    const { result } = renderHook(() => useReviewCoach());

    await act(async () => {
      await result.current.explainMove(MOVE, null);
    });

    const key = explainCacheKey(MOVE.fen, MOVE.uci, 'en');
    expect(result.current.explainByKey[key].status).toBe('done');
    expect(result.current.explainByKey[key].content).toBe('Cached explanation.');

    const streamCalls = fetchMock.mock.calls.filter((c) =>
      String(c[0]).includes('/api/coach/analysis/stream'),
    );
    expect(streamCalls).toHaveLength(0);
  });

  it('the in-memory layer skips all fetches on a same-session repeat', async () => {
    const { fetchMock } = installFetch({ cacheContent: null });
    const { result } = renderHook(() => useReviewCoach());

    await act(async () => {
      await result.current.explainMove(MOVE, null);
    });
    const callsAfterFirst = fetchMock.mock.calls.length;

    await act(async () => {
      await result.current.explainMove(MOVE, null);
    });
    // No new network activity on the second call.
    expect(fetchMock.mock.calls.length).toBe(callsAfterFirst);
  });

  it('surfaces an error status when the stream request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: { method?: string }) => {
        const method = init?.method ?? 'GET';
        if (url.includes('/api/coach/review-cache') && method === 'GET') {
          return Promise.resolve({ ok: true, json: async () => ({ content: null }) });
        }
        if (url.includes('/api/coach/analysis/stream')) {
          return Promise.resolve({ ok: false, status: 500, body: null, json: async () => ({ error: 'boom' }) });
        }
        return Promise.reject(new Error(`unexpected: ${url}`));
      }),
    );
    const { result } = renderHook(() => useReviewCoach());

    await act(async () => {
      await result.current.explainMove(MOVE, null);
    });

    const key = explainCacheKey(MOVE.fen, MOVE.uci, 'en');
    expect(result.current.explainByKey[key].status).toBe('error');
    expect(result.current.explainByKey[key].error).toBe('boom');
  });
});

describe('useReviewCoach board marks (raw [[arrows]] leak, 2026-10-21)', () => {
  const key = explainCacheKey(MOVE.fen, MOVE.uci, 'en');

  it('a cached explanation with raw marks shows clean text and draws its arrows', async () => {
    installFetch({
      cacheContent:
        '[[arrows: c6d4 green, d4e2 red]]. Из центра конь бьёт по b3. Взятие на d5 слабее [[arrows: d8d5 blue]],',
    });
    const { result } = renderHook(() => useReviewCoach());
    await act(async () => {
      await result.current.explainMove(MOVE, null);
    });

    const entry = result.current.explainByKey[key];
    expect(entry.content).not.toContain('[[');
    expect(entry.content.startsWith('Из центра')).toBe(true);
    expect(entry.arrows).toEqual([
      { from: 'c6', to: 'd4', brush: 'green' },
      { from: 'd4', to: 'e2', brush: 'red' },
      { from: 'd8', to: 'd5', brush: 'blue' },
    ]);
  });

  it('board_actions frames become arrows and are cached with the text', async () => {
    const { posts } = installFetch({
      cacheContent: null,
      streamLines: [
        'data: {"delta":"The knight jumps in."}\n',
        'data: {"board_actions":[{"type":"draw_arrows","arrows":[{"from":"c6","to":"d4","brush":"green"}]}]}\n',
        'data: {"board_actions":[{"type":"draw_arrows","arrows":[{"from":"c6","to":"d4","brush":"green"},{"from":"d4","to":"e2","brush":"red"}]}]}\n',
        'data: {"done":true}\n',
      ],
    });
    const { result } = renderHook(() => useReviewCoach());
    await act(async () => {
      await result.current.explainMove(MOVE, null);
    });

    const entry = result.current.explainByKey[key];
    expect(entry.content).toBe('The knight jumps in.');
    expect(entry.arrows).toHaveLength(2);

    // The cached string carries the arrows, so a later cache hit draws them too.
    const cached = (posts[0].body as { content: string }).content;
    installFetch({ cacheContent: cached });
    const { result: again } = renderHook(() => useReviewCoach());
    await act(async () => {
      await again.current.explainMove(MOVE, null);
    });
    expect(again.current.explainByKey[key].content).toBe('The knight jumps in.');
    expect(again.current.explainByKey[key].arrows).toEqual(entry.arrows);
  });
});

describe('useReviewCoach.recapGame', () => {
  it('streams a whole-game recap grounded in the result (happy path)', async () => {
    const { fetchMock, posts } = installFetch({ cacheContent: null });
    const { result } = renderHook(() => useReviewCoach());

    await act(async () => {
      await result.current.recapGame(REVIEW_FIXTURE);
    });

    expect(result.current.recap.status).toBe('done');
    expect(result.current.recap.content).toBe('Because it drops a pawn.');

    // Recap streams with the game context_type.
    const streamCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes('/api/coach/analysis/stream'),
    );
    expect(JSON.parse((streamCall![1] as { body: string }).body)).toMatchObject({
      context_type: 'game',
    });

    const key = summaryCacheKey(pgnHash(REVIEW_FIXTURE.moves), 'en');
    expect(posts[0].body).toMatchObject({ cache_key: key, kind: 'summary' });
  });

  it('serves a persistent-cache hit for the recap', async () => {
    const { fetchMock } = installFetch({ cacheContent: 'Cached recap.' });
    const { result } = renderHook(() => useReviewCoach());

    await act(async () => {
      await result.current.recapGame(REVIEW_FIXTURE);
    });

    expect(result.current.recap.status).toBe('done');
    expect(result.current.recap.content).toBe('Cached recap.');
    const streamCalls = fetchMock.mock.calls.filter((c) =>
      String(c[0]).includes('/api/coach/analysis/stream'),
    );
    expect(streamCalls).toHaveLength(0);
  });
});
