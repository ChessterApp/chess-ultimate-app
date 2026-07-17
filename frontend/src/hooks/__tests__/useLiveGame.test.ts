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
// Mutable presence state the tests drive directly (keys other than the caller
// count as "opponent present").
let presenceStateValue: Record<string, unknown> = {};

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
  presenceState: () => presenceStateValue,
};

const channelSpy = vi.fn(() => fakeChannel);
const setAuthSpy = vi.fn();
const fakeClient = {
  channel: channelSpy,
  removeChannel: () => Promise.resolve('ok'),
  realtime: { setAuth: setAuthSpy },
};

vi.mock('@/lib/supabase', () => ({
  createClerkSupabaseClient: () => fakeClient,
  setRealtimeAuth: () => Promise.resolve(),
}));

/** Invoke every registered presence handler (sync/join/leave) once. */
function firePresence() {
  handlers['presence:sync']?.({ payload: {} });
  handlers['presence:join']?.({ payload: {} });
  handlers['presence:leave']?.({ payload: {} });
}

/** How many telemetry POSTs (to the /telemetry route) fetch has seen so far. */
function telemetryCalls(action?: string): number {
  const f = global.fetch as unknown as {
    mock?: { calls: Array<[string, RequestInit?]> };
  };
  const calls = f.mock?.calls ?? [];
  return calls.filter(([url, init]) => {
    if (!url.includes('/telemetry') || (init?.method ?? 'GET') !== 'POST') {
      return false;
    }
    if (!action) return true;
    return typeof init?.body === 'string' && init.body.includes(`"${action}"`);
  }).length;
}

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
  presenceStateValue = {};
  channelSpy.mockClear();
  setAuthSpy.mockClear();
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

  it('polls hydrate while waiting on challenge, then keeps polling once active (safety net)', async () => {
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

    // DB flips to active; the next poll observes it.
    live = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(result.current.status).toBe('active');

    // Task 6: while active, the safety-net poll KEEPS re-hydrating every 5s so a
    // silently-dead socket can't freeze the board.
    const afterActive = spy.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(spy.mock.calls.length).toBeGreaterThan(afterActive);

    vi.useRealTimers();
  });

  it('refreshes the Realtime auth token every 30s (setAuth)', async () => {
    vi.useFakeTimers();
    mockFetch({ 'GET /api/live-games/g1': activePayload });
    renderHook(() => useLiveGame('g1'));

    // Flush mount + initial connect (setAuth is NOT called on connect — that
    // path uses the mocked setRealtimeAuth helper, not client.realtime.setAuth).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(setAuthSpy).not.toHaveBeenCalled();

    // One refresh interval → a fresh token is pushed onto the socket.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(setAuthSpy).toHaveBeenCalledTimes(1);
    expect(setAuthSpy).toHaveBeenCalledWith('fake-jwt');
    expect(telemetryCalls('token_refresh')).toBeGreaterThan(0);

    // A second interval → refreshed again.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(setAuthSpy).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('resubscribes with backoff after a channel error (new channel + hydrate)', async () => {
    vi.useFakeTimers();
    const spy = vi.fn(activePayload);
    mockFetch({ 'GET /api/live-games/g1': spy });
    const { result } = renderHook(() => useLiveGame('g1'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const channelsAfterConnect = channelSpy.mock.calls.length;
    expect(channelsAfterConnect).toBeGreaterThan(0);

    // Socket drops.
    await act(async () => {
      subscribeCb?.('CHANNEL_ERROR');
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toBe('realtime_error');
    expect(telemetryCalls('resubscribe')).toBeGreaterThan(0);

    // Backoff is 1s for the first retry → a fresh channel is opened.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(channelSpy.mock.calls.length).toBeGreaterThan(channelsAfterConnect);

    // The reconnected channel subscribes successfully → re-hydrate to catch
    // anything missed while the socket was down, and clear the error banner.
    const hydratesBeforeRecovery = spy.mock.calls.length;
    await act(async () => {
      subscribeCb?.('SUBSCRIBED');
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(spy.mock.calls.length).toBeGreaterThan(hydratesBeforeRecovery);
    expect(result.current.error).toBeNull();

    vi.useRealTimers();
  });

  it('presence: shows the disconnect banner only after a 7s grace period', async () => {
    vi.useFakeTimers();
    mockFetch({ 'GET /api/live-games/g1': activePayload });
    const { result } = renderHook(() => useLiveGame('g1'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Opponent joins.
    presenceStateValue = { joiner: [{ userId: 'joiner' }] };
    await act(async () => {
      firePresence();
    });
    expect(result.current.opponentConnected).toBe(true);

    // Opponent leaves — banner must NOT show immediately (grace period).
    presenceStateValue = {};
    await act(async () => {
      firePresence();
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(result.current.opponentConnected).toBe(true);

    // After a full 7s of continuous absence, the banner shows.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.opponentConnected).toBe(false);
    expect(telemetryCalls('disconnect_shown')).toBeGreaterThan(0);

    vi.useRealTimers();
  });

  it('presence: a rejoin within the grace period cancels the disconnect', async () => {
    vi.useFakeTimers();
    mockFetch({ 'GET /api/live-games/g1': activePayload });
    const { result } = renderHook(() => useLiveGame('g1'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    presenceStateValue = { joiner: [{ userId: 'joiner' }] };
    await act(async () => {
      firePresence();
    });
    expect(result.current.opponentConnected).toBe(true);

    // Leave, wait part of the grace window, then rejoin before it fires.
    presenceStateValue = {};
    await act(async () => {
      firePresence();
      await vi.advanceTimersByTimeAsync(4000);
    });
    presenceStateValue = { joiner: [{ userId: 'joiner' }] };
    await act(async () => {
      firePresence();
    });

    // Advancing past the original 7s must NOT flip to disconnected — the timer
    // was cancelled by the rejoin.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(result.current.opponentConnected).toBe(true);

    vi.useRealTimers();
  });

  it('sends channel_status telemetry on subscription status changes', async () => {
    mockFetch({ 'GET /api/live-games/g1': activePayload });
    renderHook(() => useLiveGame('g1'));
    await waitFor(() => expect(subscribeCb).not.toBeNull());

    await act(async () => {
      subscribeCb?.('SUBSCRIBED');
    });
    await waitFor(() =>
      expect(telemetryCalls('channel_status')).toBeGreaterThan(0),
    );
  });
});
