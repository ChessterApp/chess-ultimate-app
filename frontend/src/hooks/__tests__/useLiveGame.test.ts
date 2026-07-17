/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { HydrationPayload } from '@/lib/live-game/types';

// ─── Clerk auth mock ─────────────────────────────────────────────────────────
let mockUserId = 'creator';
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({
    userId: mockUserId,
    isLoaded: true,
    getToken: () => Promise.resolve('fake-jwt'),
  }),
}));

// ─── Supabase client mock (no live socket) ───────────────────────────────────
type Handler = (msg: { payload: unknown }) => void;
const handlers: Record<string, Handler> = {};
let subscribeCb: ((s: string) => void) | null = null;

const fakeChannel = {
  on(type: string, filter: { event: string }, cb: Handler) {
    handlers[`${type}:${filter.event}`] = cb;
    return fakeChannel;
  },
  subscribe(cb: (s: string) => void) {
    subscribeCb = cb;
    return fakeChannel;
  },
  track: () => Promise.resolve('ok'),
  presenceState: () => ({}),
};

const fakeClient = {
  channel: () => fakeChannel,
  removeChannel: () => Promise.resolve('ok'),
  realtime: { setAuth: () => {} },
};

vi.mock('@/lib/supabase', () => ({
  createClerkSupabaseClient: () => fakeClient,
  setRealtimeAuth: () => Promise.resolve(),
}));

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';

function activePayload(): HydrationPayload {
  return {
    game: {
      id: 'g1',
      status: 'active',
      colorChoice: 'white',
      initialSec: 300,
      incrementSec: 2,
      fen: START_FEN,
      ply: 0,
      whiteMs: 300000,
      blackMs: 300000,
      result: null,
      winnerId: null,
      endReason: null,
      creatorId: 'creator',
      whiteId: 'creator',
      blackId: 'joiner',
      opponentId: 'joiner',
    },
    moves: [],
  };
}

function challengePayload(): HydrationPayload {
  return {
    game: {
      id: 'g1',
      status: 'challenge',
      colorChoice: 'white',
      initialSec: 300,
      incrementSec: 2,
      fen: START_FEN,
      ply: 0,
      whiteMs: 300000,
      blackMs: 300000,
      result: null,
      winnerId: null,
      endReason: null,
      creatorId: 'creator',
      whiteId: null,
      blackId: null,
      opponentId: null,
    },
    moves: [],
  };
}

function mockFetch(routes: Record<string, () => unknown>) {
  global.fetch = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    const key = `${method} ${url.replace(/^.*\/api/, '/api')}`;
    const match = Object.keys(routes).find((k) => key.startsWith(k));
    const body = match ? routes[match]() : {};
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    });
  }) as unknown as typeof fetch;
}

// Import after mocks are registered.
import { useLiveGame } from '../useLiveGame';

beforeEach(() => {
  vi.useRealTimers();
  mockUserId = 'creator';
  for (const k of Object.keys(handlers)) delete handlers[k];
  subscribeCb = null;
});

describe('useLiveGame', () => {
  it('hydrates from GET and exposes derived state', async () => {
    mockFetch({ 'GET /api/live-games/g1': activePayload });
    const { result } = renderHook(() => useLiveGame('g1'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.status).toBe('active');
    expect(result.current.fen).toBe(START_FEN);
    expect(result.current.myColor).toBe('white');
    expect(result.current.orientation).toBe('white');
    expect(result.current.isMyTurn).toBe(true);
    expect(result.current.isCreator).toBe(true);
  });

  it('applies a broadcast game.move through the reducer', async () => {
    mockFetch({ 'GET /api/live-games/g1': activePayload });
    const { result } = renderHook(() => useLiveGame('g1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      handlers['broadcast:game.move']?.({
        payload: {
          ply: 1,
          uci: 'e2e4',
          san: 'e4',
          fenAfter: AFTER_E4,
          whiteMs: 302000,
          blackMs: 300000,
        },
      });
    });

    expect(result.current.fen).toBe(AFTER_E4);
    expect(result.current.ply).toBe(1);
    expect(result.current.isMyTurn).toBe(false); // black to move now
  });

  it('makeMove POSTs and reconciles from the response', async () => {
    mockFetch({
      'GET /api/live-games/g1': activePayload,
      'POST /api/live-games/g1/move': () => ({
        ply: 1,
        uci: 'e2e4',
        san: 'e4',
        fenAfter: AFTER_E4,
        whiteMs: 302000,
        blackMs: 300000,
      }),
    });
    const { result } = renderHook(() => useLiveGame('g1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      const ok = await result.current.makeMove('e2e4');
      expect(ok).toBe(true);
    });

    expect(result.current.fen).toBe(AFTER_E4);
    expect(result.current.ply).toBe(1);
  });

  it('re-hydrates on SUBSCRIBED (reconnect resync)', async () => {
    const spy = vi.fn(activePayload);
    mockFetch({ 'GET /api/live-games/g1': spy });
    renderHook(() => useLiveGame('g1'));
    await waitFor(() => expect(subscribeCb).not.toBeNull());

    const before = spy.mock.calls.length;
    await act(async () => {
      subscribeCb?.('SUBSCRIBED');
    });
    await waitFor(() => expect(spy.mock.calls.length).toBeGreaterThan(before));
  });

  it('surfaces an error when the subscription reports CHANNEL_ERROR', async () => {
    mockFetch({ 'GET /api/live-games/g1': challengePayload });
    const { result } = renderHook(() => useLiveGame('g1'));
    await waitFor(() => expect(subscribeCb).not.toBeNull());
    expect(result.current.error).toBeNull();

    await act(async () => {
      subscribeCb?.('CHANNEL_ERROR');
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toBe('realtime_error');
  });

  it('polls hydrate while waiting on challenge, and stops once active', async () => {
    vi.useFakeTimers();
    let live = false;
    const spy = vi.fn(() => (live ? activePayload() : challengePayload()));
    mockFetch({ 'GET /api/live-games/g1': spy });

    const { result } = renderHook(() => useLiveGame('g1'));
    // Flush the immediate mount hydration.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status).toBe('challenge');

    const afterMount = spy.mock.calls.length;

    // One poll interval (~5s) → at least one more authoritative re-fetch.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(spy.mock.calls.length).toBeGreaterThan(afterMount);

    // DB flips to active; the next poll observes it and clears the interval.
    live = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(result.current.status).toBe('active');

    // Polling has stopped — advancing further produces no more hydrate fetches.
    const afterActive = spy.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(spy.mock.calls.length).toBe(afterActive);

    vi.useRealTimers();
  });
});
