import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/live-game/broadcast', () => ({ broadcastGameEvent: vi.fn() }));

// Stage A: run next/server `after()` callbacks synchronously so the broadcast
// assertions still fire, and stub the telemetry logger to keep it out of the way.
vi.mock('next/server', async () => {
  const actual = await vi.importActual<typeof import('next/server')>('next/server');
  return { ...actual, after: (fn: () => unknown) => { fn(); } };
});
vi.mock('@/lib/live-game/log', () => ({
  logLiveGameEvent: vi.fn(),
  createStageTimer: () => ({ stages: {}, mark: () => {}, total: () => 0 }),
}));

vi.mock('@/lib/supabase-admin', async () => {
  const m = await import('@/test/liveGameSupabaseMock');
  return { supabaseAdmin: { from: (t: string) => m.makeBuilder(t) } };
});

import { auth } from '@clerk/nextjs/server';
import { broadcastGameEvent } from '@/lib/live-game/broadcast';
import { scripts, recorded, resetSupabaseMock } from '@/test/liveGameSupabaseMock';

function mockAuth(userId: string | null) {
  (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
    userId,
  });
}

const GID = '66666666-6666-6666-6666-666666666666';
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function params() {
  return { params: Promise.resolve({ gameId: GID }) };
}
function req(): Request {
  return new Request(`https://chesster.io/api/live-games/${GID}/claim-flag`, { method: 'POST' });
}

function activeRow(over: Record<string, unknown> = {}) {
  return {
    id: GID,
    creator_id: 'user_white',
    opponent_id: 'user_black',
    white_id: 'user_white',
    black_id: 'user_black',
    status: 'active',
    color_choice: 'white',
    initial_sec: 300,
    increment_sec: 3,
    fen: START, // white to move
    ply: 2,
    white_ms: 300_000,
    black_ms: 300_000,
    last_move_at: new Date(Date.now() - 1000).toISOString(),
    result: null,
    winner_id: null,
    end_reason: null,
    draw_offer_by: null,
    expires_at: null,
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
    ...over,
  };
}

describe('POST /api/live-games/[gameId]/claim-flag', () => {
  beforeEach(() => {
    resetSupabaseMock();
    vi.clearAllMocks();
  });

  it('401 when unauthenticated', async () => {
    mockAuth(null);
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(401);
  });

  it('409 when the game is not active', async () => {
    mockAuth('user_black');
    scripts['games.select'] = [{ data: activeRow({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
  });

  it('403 when a non-player claims', async () => {
    mockAuth('user_stranger');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(403);
  });

  it('400 for an untimed game (cannot flag)', async () => {
    mockAuth('user_black');
    scripts['games.select'] = [
      { data: activeRow({ white_ms: null, black_ms: null }), error: null },
    ];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(400);
    expect((await r.json()).error).toBe('not_timed');
  });

  it('409 not_flagged when the running clock still has time', async () => {
    // White to move with a full bank and only ~1s elapsed → not flagged.
    mockAuth('user_black');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('not_flagged');
    expect(broadcastGameEvent).not.toHaveBeenCalled();
  });

  it('happy path: white (to move) flagged → black wins, broadcasts game.end', async () => {
    mockAuth('user_black');
    scripts['games.select'] = [
      {
        data: activeRow({
          white_ms: 1_000,
          last_move_at: new Date(Date.now() - 60_000).toISOString(),
        }),
        error: null,
      },
    ];
    scripts['games.update'] = [{ data: activeRow({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.result).toBe('0-1'); // white flagged → black wins
    expect(body.winnerId).toBe('user_black');
    expect(body.reason).toBe('flag');
    expect(body.whiteMs).toBe(0); // flagged bank pinned to 0

    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    expect(upd!.filters).toEqual(
      expect.arrayContaining([['status', 'active']]),
    );
    expect(broadcastGameEvent).toHaveBeenCalledWith(
      GID,
      'game.end',
      expect.objectContaining({ reason: 'flag' }),
    );
  });

  it('the player whose own clock is dead loses (whoever is on the move)', async () => {
    // White is on the move and flagged; even if WHITE claims, white loses.
    mockAuth('user_white');
    scripts['games.select'] = [
      {
        data: activeRow({
          white_ms: 1_000,
          last_move_at: new Date(Date.now() - 60_000).toISOString(),
        }),
        error: null,
      },
    ];
    scripts['games.update'] = [{ data: activeRow({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    const body = await r.json();
    expect(body.result).toBe('0-1');
    expect(body.winnerId).toBe('user_black'); // claimant (white) still loses
  });
});
