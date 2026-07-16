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

const GID = '88888888-8888-8888-8888-888888888888';
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function params() {
  return { params: Promise.resolve({ gameId: GID }) };
}
function req(): Request {
  return new Request(`https://chesster.io/api/live-games/${GID}/abort`, { method: 'POST' });
}

function row(over: Record<string, unknown> = {}) {
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
    draw_offer_by: null,
    expires_at: null,
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
    ...over,
  };
}

describe('POST /api/live-games/[gameId]/abort', () => {
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

  it('active + fewer than 2 plies: either player may abort', async () => {
    mockAuth('user_black');
    scripts['games.select'] = [{ data: row({ ply: 1 }), error: null }];
    scripts['games.update'] = [{ data: row({ status: 'aborted' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.status).toBe('aborted');
    expect(body.reason).toBe('abort');
    expect(body.result).toBeNull();

    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    expect(upd!.filters).toEqual(expect.arrayContaining([['status', 'active']]));
    expect((upd!.payload as Record<string, unknown>).status).toBe('aborted');
    expect(broadcastGameEvent).toHaveBeenCalledWith(
      GID,
      'game.end',
      expect.objectContaining({ reason: 'abort', status: 'aborted' }),
    );
  });

  it('active + 2+ plies: 409 too_late', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: row({ ply: 2 }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('too_late');
    expect(broadcastGameEvent).not.toHaveBeenCalled();
  });

  it('active + non-player: 403', async () => {
    mockAuth('user_stranger');
    scripts['games.select'] = [{ data: row({ ply: 1 }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(403);
    expect((await r.json()).error).toBe('not_player');
  });

  it('challenge + creator: cancels the challenge (guards on status=challenge)', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [
      { data: row({ status: 'challenge', white_id: null, black_id: null, opponent_id: null }), error: null },
    ];
    scripts['games.update'] = [{ data: row({ status: 'aborted' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(200);
    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    expect(upd!.filters).toEqual(expect.arrayContaining([['status', 'challenge']]));
  });

  it('challenge + non-creator: 403', async () => {
    mockAuth('user_joiner');
    scripts['games.select'] = [
      { data: row({ status: 'challenge', white_id: null, black_id: null, opponent_id: null }), error: null },
    ];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(403);
    expect((await r.json()).error).toBe('not_creator');
  });

  it('finished game: 409 not_abortable', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: row({ status: 'finished' }), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('not_abortable');
  });

  it('409 when the conditional update finds no matching row', async () => {
    mockAuth('user_white');
    scripts['games.select'] = [{ data: row({ ply: 0 }), error: null }];
    scripts['games.update'] = [{ data: null, error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('not_abortable');
    expect(broadcastGameEvent).not.toHaveBeenCalled();
  });
});
