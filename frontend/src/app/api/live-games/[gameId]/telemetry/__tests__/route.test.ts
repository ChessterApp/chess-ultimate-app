import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/live-game/log', () => ({ logLiveGameEvent: vi.fn() }));

import { auth } from '@clerk/nextjs/server';
import { logLiveGameEvent } from '@/lib/live-game/log';

function mockAuth(userId: string | null) {
  (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
    userId,
  });
}

const GID = '44444444-4444-4444-4444-444444444444';

function params() {
  return { params: Promise.resolve({ gameId: GID }) };
}

function req(body: unknown): Request {
  return new Request(`https://chesster.io/api/live-games/${GID}/telemetry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('POST /api/live-games/[gameId]/telemetry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('401 when unauthenticated', async () => {
    mockAuth(null);
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'channel_status' }) as never, params());
    expect(r.status).toBe(401);
    expect(logLiveGameEvent).not.toHaveBeenCalled();
  });

  it('400 when the action is not on the whitelist', async () => {
    mockAuth('user_1');
    const { POST } = await import('../route');
    const r = await POST(req({ action: 'drop_table' }) as never, params());
    expect(r.status).toBe(400);
    expect((await r.json()).error).toBe('bad_action');
    expect(logLiveGameEvent).not.toHaveBeenCalled();
  });

  it('400 on malformed JSON body', async () => {
    mockAuth('user_1');
    const bad = new Request(`https://chesster.io/api/live-games/${GID}/telemetry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{ not json',
    });
    const { POST } = await import('../route');
    const r = await POST(bad as never, params());
    expect(r.status).toBe(400);
  });

  it('202 and logs a client event for a whitelisted action', async () => {
    mockAuth('user_1');
    const { POST } = await import('../route');
    const r = await POST(
      req({ action: 'presence_leave', ply: 5 }) as never,
      params(),
    );
    expect(r.status).toBe(202);
    expect(logLiveGameEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        source: 'client',
        action: 'presence_leave',
        gameId: GID,
        userId: 'user_1',
        ply: 5,
      }),
    );
  });

  it('truncates an oversized detail payload but still logs', async () => {
    mockAuth('user_1');
    const { POST } = await import('../route');
    const huge = { blob: 'x'.repeat(2000) };
    const r = await POST(
      req({ action: 'channel_status', detail: huge }) as never,
      params(),
    );
    expect(r.status).toBe(202);
    expect(logLiveGameEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'channel_status',
        detail: { _truncated: true },
      }),
    );
  });
});
