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

function req(body: unknown): Request {
  return new Request('https://chesster.io/api/games/challenge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

const GID = '11111111-1111-1111-1111-111111111111';

describe('POST /api/games/challenge', () => {
  beforeEach(() => {
    resetSupabaseMock();
    vi.clearAllMocks();
  });

  it('401 when unauthenticated', async () => {
    mockAuth(null);
    const { POST } = await import('../route');
    const r = await POST(req({ colorChoice: 'white' }) as never);
    expect(r.status).toBe(401);
  });

  it('400 for an invalid colorChoice', async () => {
    mockAuth('user_1');
    const { POST } = await import('../route');
    const r = await POST(req({ colorChoice: 'purple' }) as never);
    expect(r.status).toBe(400);
    expect((await r.json()).error).toBe('invalid_color');
  });

  it('400 for a negative time control', async () => {
    mockAuth('user_1');
    const { POST } = await import('../route');
    const r = await POST(
      req({ colorChoice: 'white', initialSec: -5 }) as never,
    );
    expect(r.status).toBe(400);
    expect((await r.json()).error).toBe('invalid_time_control');
  });

  it('201 with { gameId, url } on success and stores color + clocks', async () => {
    mockAuth('user_creator');
    scripts['games.insert'] = [{ data: { id: GID }, error: null }];
    const { POST } = await import('../route');
    const r = await POST(
      req({ colorChoice: 'random', initialSec: 300, incrementSec: 3 }) as never,
    );
    expect(r.status).toBe(201);
    const body = await r.json();
    expect(body.gameId).toBe(GID);
    expect(body.url).toBe(`https://chesster.io/play/live/${GID}`);

    const insert = recorded.find((x) => x.table === 'games' && x.op === 'insert');
    const payload = insert!.payload as Record<string, unknown>;
    expect(payload.creator_id).toBe('user_creator');
    expect(payload.status).toBe('challenge');
    expect(payload.color_choice).toBe('random');
    expect(payload.initial_sec).toBe(300);
    expect(payload.increment_sec).toBe(3);
  });

  it('stores untimed (null clocks) when no initialSec given', async () => {
    mockAuth('user_creator');
    scripts['games.insert'] = [{ data: { id: GID }, error: null }];
    const { POST } = await import('../route');
    const r = await POST(req({ colorChoice: 'white' }) as never);
    expect(r.status).toBe(201);
    const insert = recorded.find((x) => x.table === 'games' && x.op === 'insert');
    const payload = insert!.payload as Record<string, unknown>;
    expect(payload.initial_sec).toBeNull();
    expect(payload.increment_sec).toBeNull();
  });

  it('500 when the insert fails', async () => {
    mockAuth('user_creator');
    scripts['games.insert'] = [{ data: null, error: { message: 'boom' } }];
    const { POST } = await import('../route');
    const r = await POST(req({ colorChoice: 'white' }) as never);
    expect(r.status).toBe(500);
  });
});
