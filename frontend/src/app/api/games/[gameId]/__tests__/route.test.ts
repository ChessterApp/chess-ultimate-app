import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));

vi.mock('@/lib/supabase-admin', async () => {
  const m = await import('@/test/liveGameSupabaseMock');
  return { supabaseAdmin: { from: (t: string) => m.makeBuilder(t) } };
});

import { auth } from '@clerk/nextjs/server';
import { scripts, recorded, resetSupabaseMock } from '@/test/liveGameSupabaseMock';

function mockAuth(userId: string | null) {
  (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
    userId,
  });
}

const GID = '44444444-4444-4444-4444-444444444444';
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function params() {
  return { params: Promise.resolve({ gameId: GID }) };
}
function req() {
  return new Request(`https://chesster.io/api/games/${GID}`);
}

function row(over: Record<string, unknown> = {}) {
  return {
    id: GID,
    creator_id: 'user_creator',
    opponent_id: 'user_joiner',
    white_id: 'user_creator',
    black_id: 'user_joiner',
    status: 'active',
    color_choice: 'white',
    initial_sec: 300,
    increment_sec: 3,
    fen: START,
    ply: 0,
    white_ms: 300_000,
    black_ms: 300_000,
    last_move_at: new Date(Date.now() - 4_000).toISOString(),
    result: null,
    winner_id: null,
    end_reason: null,
    expires_at: null,
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
    ...over,
  };
}

describe('GET /api/games/[gameId]', () => {
  beforeEach(() => {
    resetSupabaseMock();
    vi.clearAllMocks();
  });

  it('401 when unauthenticated', async () => {
    mockAuth(null);
    const { GET } = await import('../route');
    const r = await GET(req() as never, params());
    expect(r.status).toBe(401);
  });

  it('404 when the game does not exist', async () => {
    mockAuth('user_creator');
    scripts['games.select'] = [{ data: null, error: null }];
    const { GET } = await import('../route');
    const r = await GET(req() as never, params());
    expect(r.status).toBe(404);
  });

  it('404 when a non-player fetches a non-challenge game', async () => {
    mockAuth('user_stranger');
    scripts['games.select'] = [{ data: row(), error: null }];
    const { GET } = await import('../route');
    const r = await GET(req() as never, params());
    expect(r.status).toBe(404);
  });

  it('any authenticated user may read an open challenge; player ids withheld', async () => {
    mockAuth('user_stranger');
    scripts['games.select'] = [
      {
        data: row({
          status: 'challenge',
          white_id: null,
          black_id: null,
          opponent_id: null,
        }),
        error: null,
      },
    ];
    const { GET } = await import('../route');
    const r = await GET(req() as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.game.status).toBe('challenge');
    expect(body.game.creatorId).toBe('user_creator');
    expect('whiteId' in body.game).toBe(false);
  });

  it('lazily flips a stale challenge to expired on read', async () => {
    mockAuth('user_creator');
    scripts['games.select'] = [
      {
        data: row({
          status: 'challenge',
          expires_at: '2020-01-01T00:00:00Z',
          white_id: null,
          black_id: null,
          opponent_id: null,
        }),
        error: null,
      },
    ];
    scripts['games.update'] = [{ data: null, error: null }];
    scripts['game_moves.select'] = [{ data: [], error: null }];
    const { GET } = await import('../route');
    const r = await GET(req() as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.game.status).toBe('expired');
    // The lazy flip is a conditional update guarded on status='challenge'.
    const upd = recorded.find((x) => x.table === 'games' && x.op === 'update');
    expect(upd!.filters).toEqual(
      expect.arrayContaining([
        ['id', GID],
        ['status', 'challenge'],
      ]),
    );
    expect((upd!.payload as Record<string, unknown>).status).toBe('expired');
  });

  it('player hydration: recomputes clocks and returns the move list', async () => {
    mockAuth('user_joiner');
    scripts['games.select'] = [{ data: row(), error: null }];
    scripts['game_moves.select'] = [
      {
        data: [
          {
            game_id: GID,
            ply: 1,
            uci: 'e2e4',
            san: 'e4',
            fen_after: START,
            move_time_ms: 1200,
            created_at: '2026-07-16T00:00:01Z',
          },
        ],
        error: null,
      },
    ];
    const { GET } = await import('../route');
    const r = await GET(req() as never, params());
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.game.whiteId).toBe('user_creator');
    expect(body.game.blackId).toBe('user_joiner');
    // White is to move and ~4s have elapsed → its bank is debited below 300000.
    expect(body.game.whiteMs).toBeLessThan(300_000);
    expect(body.game.whiteMs).toBeGreaterThan(290_000);
    expect(body.game.blackMs).toBe(300_000);
    expect(body.moves).toHaveLength(1);
    expect(body.moves[0].san).toBe('e4');
  });
});
