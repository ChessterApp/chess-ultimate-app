import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/live-game/broadcast', () => ({ broadcastGameEvent: vi.fn() }));

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

const GID = '55555555-5555-5555-5555-555555555555';
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function params() {
  return { params: Promise.resolve({ gameId: GID }) };
}
function req(): Request {
  return new Request(`https://chesster.io/api/live-games/${GID}/resign`, { method: 'POST' });
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
    ply: 4,
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

describe('POST /api/live-games/[gameId]/resign', () => {
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

  it('404 when the game does not exist', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: null, error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(404);
  });

  it('409 when the game is not active', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: activeRow({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('not_active');
  });

  it('403 when a non-player resigns', async () => {
    mockAuth('user_stranger');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(403);
    expect((await r.json()).error).toBe('not_player');
  });

  it('happy path: white resigns → black wins, broadcasts game.end, guards on active', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    scripts['games.update'] = [{ data: activeRow({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.result).toBe('0-1');
    expect(body.winnerId).toBe('user_black');
    expect(body.reason).toBe('resign');
    expect(body.status).toBe('finished');

    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    expect(upd!.filters).toEqual(
      expect.arrayContaining([
        ['id', GID],
        ['status', 'active'],
      ]),
    );
    const p = upd!.payload as Record<string, unknown>;
    expect(p.end_reason).toBe('resign');
    expect(p.draw_offer_by).toBeNull();

    expect(broadcastGameEvent).toHaveBeenCalledWith(
      GID,
      'game.end',
      expect.objectContaining({ reason: 'resign', winnerId: 'user_black' }),
    );
  });

  it('black resigns → white wins (1-0)', async () => {
    mockAuth('user_black');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    scripts['games.update'] = [{ data: activeRow({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    const body = await r.json();
    expect(body.result).toBe('1-0');
    expect(body.winnerId).toBe('user_white');
  });

  it('409 when the conditional update finds no active row (already ended)', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    scripts['games.update'] = [{ data: null, error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
    expect(broadcastGameEvent).not.toHaveBeenCalled();
  });
});
