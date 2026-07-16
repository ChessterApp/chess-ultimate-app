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

const GID = '77777777-7777-7777-7777-777777777777';
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function params() {
  return { params: Promise.resolve({ gameId: GID }) };
}
function req(body: unknown): Request {
  return new Request(`https://chesster.io/api/live-games/${GID}/draw`, {
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
    ply: 6,
    white_ms: 200_000,
    black_ms: 200_000,
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

describe('POST /api/live-games/[gameId]/draw', () => {
  beforeEach(() => {
    resetSupabaseMock();
    vi.clearAllMocks();
  });

  it('401 when unauthenticated', async () => {
    mockAuth(null);
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'offer' }) as never, params());
    expect(r.status).toBe(401);
  });

  it('400 for a bad action', async () => {
    mockAuth('user_white');
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'nope' }) as never, params());
    expect(r.status).toBe(400);
    expect((await r.json()).error).toBe('bad_action');
  });

  it('409 when the game is not active', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: activeRow({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'offer' }) as never, params());
    expect(r.status).toBe(409);
  });

  it('403 when a non-player acts', async () => {
    mockAuth('user_stranger');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'offer' }) as never, params());
    expect(r.status).toBe(403);
  });

  it('offer: records the offerer and broadcasts game.draw_offer', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: activeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'offer' }) as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body).toEqual({ action: 'offer', by: 'user_white' });

    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    expect((upd!.payload as Record<string, unknown>).draw_offer_by).toBe('user_white');
    expect(broadcastGameEvent).toHaveBeenCalledWith(
      GID,
      'game.draw_offer',
      expect.objectContaining({ by: 'user_white' }),
    );
  });

  it('decline: clears the offer and broadcasts game.draw_decline', async () => {
    mockAuth('user_black');
    scripts['games.select'] = [{ data: activeRow({ draw_offer_by: 'user_white' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'decline' }) as never, params());
    expect(r.status).toBe(200);
    expect((await r.json()).action).toBe('decline');

    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    expect((upd!.payload as Record<string, unknown>).draw_offer_by).toBeNull();
    expect(broadcastGameEvent).toHaveBeenCalledWith(GID, 'game.draw_decline', { gameId: GID });
  });

  it('accept: the OTHER player accepts → draw, broadcasts game.end', async () => {
    mockAuth('user_black');
    scripts['games.select'] = [{ data: activeRow({ draw_offer_by: 'user_white' }), error: null }];
    scripts['games.update'] = [{ data: activeRow({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'accept' }) as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.result).toBe('1/2-1/2');
    expect(body.winnerId).toBeNull();
    expect(body.reason).toBe('draw');

    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    const p = upd!.payload as Record<string, unknown>;
    expect(p.status).toBe('finished');
    expect(p.draw_offer_by).toBeNull();
    expect(broadcastGameEvent).toHaveBeenCalledWith(
      GID,
      'game.end',
      expect.objectContaining({ reason: 'draw' }),
    );
  });

  it('accept: 409 when there is no standing offer', async () => {
    mockAuth('user_black');
    scripts['games.select'] = [{ data: activeRow({ draw_offer_by: null }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'accept' }) as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('no_offer');
  });

  it('accept: 409 when you try to accept your OWN offer', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: activeRow({ draw_offer_by: 'user_white' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'accept' }) as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('no_offer');
    expect(broadcastGameEvent).not.toHaveBeenCalled();
  });
});
