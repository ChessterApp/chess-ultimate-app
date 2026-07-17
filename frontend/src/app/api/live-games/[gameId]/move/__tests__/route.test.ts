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

const GID = '33333333-3333-3333-3333-333333333333';
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function params() {
  return { params: Promise.resolve({ gameId: GID }) };
}

function req(body: unknown): Request {
  return new Request(`https://chesster.io/api/live-games/${GID}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
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
    fen: START,
    ply: 0,
    white_ms: 300_000,
    black_ms: 300_000,
    last_move_at: new Date(Date.now() - 1000).toISOString(),
    result: null,
    winner_id: null,
    end_reason: null,
    expires_at: null,
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
    ...over,
  };
}

describe('POST /api/live-games/[gameId]/move', () => {
  beforeEach(() => {
    resetSupabaseMock();
    vi.clearAllMocks();
  });

  it('401 when unauthenticated', async () => {
    mockAuth(null);
    const { POST } = await import('../route');
    const r = await POST(req({ uci: 'e2e4' }) as never, params());
    expect(r.status).toBe(401);
  });

  it('400 when uci is missing', async () => {
    mockAuth('user_white');
    const { POST } = await import('../route');
    const r = await POST(req({}) as never, params());
    expect(r.status).toBe(400);
  });

  it('404 when the game does not exist', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: null, error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ uci: 'e2e4' }) as never, params());
    expect(r.status).toBe(404);
  });

  it('409 when the game is not active', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [
      { data: activeRow({ status: 'finished' }), error: null },
    ];
    const { POST } = await import('../route');
    const r = await POST(req({ uci: 'e2e4' }) as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('not_active');
  });

  it('403 when it is not the caller’s turn', async () => {
    // FEN says white to move, but black tries to move.
    mockAuth('user_black');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ uci: 'e7e5' }) as never, params());
    expect(r.status).toBe(403);
    expect((await r.json()).error).toBe('not_your_turn');
  });

  it('422 for an illegal move', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ uci: 'e2e5' }) as never, params());
    expect(r.status).toBe(422);
    expect((await r.json()).error).toBe('illegal_move');
  });

  it('flag-on-move: 409, finishes the game, broadcasts game.end, no move applied', async () => {
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
    // The finalising UPDATE returns the finished row.
    scripts['games.update'] = [
      { data: activeRow({ status: 'finished' }), error: null },
    ];
    const { POST } = await import('../route');
    const r = await POST(req({ uci: 'e2e4' }) as never, params());
    expect(r.status).toBe(409);
    const body = await r.json();
    expect(body.error).toBe('flagged');
    expect(body.reason).toBe('flag');
    expect(body.result).toBe('0-1'); // white flagged → black wins
    expect(body.winnerId).toBe('user_black');

    // No move row was written.
    expect(recorded.find((x) => x.table === 'game_moves')).toBeUndefined();
    expect(broadcastGameEvent).toHaveBeenCalledWith(
      GID,
      'game.end',
      expect.objectContaining({ reason: 'flag' }),
    );
  });

  it('happy path: 200, inserts the move, updates the game, broadcasts game.move', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ uci: 'e2e4' }) as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.ply).toBe(1);
    expect(body.san).toBe('e4');
    expect(body.fenAfter.split(' ')[1]).toBe('b');

    const moveRow = recorded.find((x) => x.table === 'game_moves');
    expect(moveRow!.op).toBe('insert');
    const mp = moveRow!.payload as Record<string, unknown>;
    expect(mp.ply).toBe(1);
    expect(mp.uci).toBe('e2e4');
    expect(mp.san).toBe('e4');

    const gameUpd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    const gp = gameUpd!.payload as Record<string, unknown>;
    expect(gp.ply).toBe(1);
    expect(gp.fen).toBe(body.fenAfter);
    // Every successful move clears a standing draw offer.
    expect(gp.draw_offer_by).toBeNull();

    expect(broadcastGameEvent).toHaveBeenCalledWith(
      GID,
      'game.move',
      expect.objectContaining({ ply: 1, san: 'e4' }),
    );
  });
});
