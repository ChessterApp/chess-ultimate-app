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

const GID = '22222222-2222-2222-2222-222222222222';

function params() {
  return { params: Promise.resolve({ gameId: GID }) };
}

function req(): Request {
  return new Request(`https://chesster.io/api/live-games/${GID}/join`, {
    method: 'POST',
  });
}

function challengeRow(over: Record<string, unknown> = {}) {
  return {
    id: GID,
    creator_id: 'user_creator',
    opponent_id: null,
    white_id: null,
    black_id: null,
    status: 'challenge',
    color_choice: 'white',
    initial_sec: 300,
    increment_sec: 3,
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    ply: 0,
    white_ms: null,
    black_ms: null,
    last_move_at: null,
    result: null,
    winner_id: null,
    end_reason: null,
    expires_at: '2999-01-01T00:00:00Z',
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
    ...over,
  };
}

describe('POST /api/live-games/[gameId]/join', () => {
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
    mockAuth('user_joiner');
    scripts['games.select'] = [{ data: null, error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(404);
  });

  it('403 when the creator tries to join their own challenge', async () => {
    mockAuth('user_creator');
    scripts['games.select'] = [{ data: challengeRow(), error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(403);
    expect((await r.json()).error).toBe('cannot_join_own');
  });

  it('409 when the game is not an open challenge', async () => {
    mockAuth('user_joiner');
    scripts['games.select'] = [
      { data: challengeRow({ status: 'active' }), error: null },
    ];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('not_open');
  });

  it('410 when the challenge has expired', async () => {
    mockAuth('user_joiner');
    scripts['games.select'] = [
      { data: challengeRow({ expires_at: '2020-01-01T00:00:00Z' }), error: null },
    ];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(410);
    expect((await r.json()).error).toBe('expired');
  });

  it('happy path: 200, flips to active, resolves colors, broadcasts game.start', async () => {
    mockAuth('user_joiner');
    scripts['games.select'] = [{ data: challengeRow(), error: null }];
    scripts['games.update'] = [
      {
        data: challengeRow({
          status: 'active',
          opponent_id: 'user_joiner',
          white_id: 'user_creator',
          black_id: 'user_joiner',
          white_ms: 300_000,
          black_ms: 300_000,
          last_move_at: '2026-07-16T10:00:00Z',
        }),
        error: null,
      },
    ];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.status).toBe('active');
    // color_choice 'white' → creator is white, joiner is black.
    expect(body.whiteId).toBe('user_creator');
    expect(body.blackId).toBe('user_joiner');
    expect(body.whiteMs).toBe(300_000);

    // The accept UPDATE must be race-guarded on status='challenge'.
    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    expect(upd!.filters).toEqual(
      expect.arrayContaining([
        ['id', GID],
        ['status', 'challenge'],
      ]),
    );
    const payload = upd!.payload as Record<string, unknown>;
    expect(payload.status).toBe('active');
    expect(payload.white_ms).toBe(300_000);

    expect(broadcastGameEvent).toHaveBeenCalledWith(
      GID,
      'game.start',
      expect.objectContaining({ status: 'active' }),
    );
  });

  it('double-join race: the second clicker gets 409 (0 rows updated)', async () => {
    mockAuth('user_joiner2');
    scripts['games.select'] = [{ data: challengeRow(), error: null }];
    // Conditional UPDATE affected 0 rows — someone already accepted.
    scripts['games.update'] = [{ data: null, error: null }];
    const { POST } = await import('../route');
    const r = await POST(req() as never, params());
    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe('already_taken');
    expect(broadcastGameEvent).not.toHaveBeenCalled();
  });
});
