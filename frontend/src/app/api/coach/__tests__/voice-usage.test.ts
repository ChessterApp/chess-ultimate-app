import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';

const makeRequest = (body?: unknown) =>
  new Request('http://localhost:3000/api/coach/voice-usage', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

describe('POST /api/coach/voice-usage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    (auth as any).mockResolvedValue({ userId: null });
    const { POST } = await import('../voice-usage/route');
    const res = await POST(makeRequest({ session_id: 's1', seconds_delta: 60 }) as any);
    expect(res.status).toBe(401);
  });

  it('forwards a heartbeat to Hermes with the SERVER-side user id, not the client value', async () => {
    (auth as any).mockResolvedValue({ userId: 'clerk_user' });
    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) }));
    global.fetch = fetchSpy as any;

    const { POST } = await import('../voice-usage/route');
    const res = await POST(
      makeRequest({
        session_id: 's1',
        seconds_delta: 60,
        user_id: 'attacker_supplied', // must be ignored
      }) as any,
    );

    expect(res.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchSpy.mock.calls[0] as any[];
    expect(String(url)).toContain('/internal/voice/heartbeat');
    expect(opts.headers['X-User-Id']).toBe('clerk_user');
    const sent = JSON.parse(opts.body);
    expect(sent.user_id).toBe('clerk_user');
    expect(sent.session_id).toBe('s1');
    expect(sent.seconds_delta).toBe(60);
  });

  it('skips the forward (still 200) when there is nothing to record', async () => {
    (auth as any).mockResolvedValue({ userId: 'clerk_user' });
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as any;

    const { POST } = await import('../voice-usage/route');
    const res = await POST(makeRequest({ session_id: 's1', seconds_delta: 0 }) as any);
    expect(res.status).toBe(200);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('is best-effort: returns 200 even if the Hermes forward throws', async () => {
    (auth as any).mockResolvedValue({ userId: 'clerk_user' });
    global.fetch = vi.fn(async () => {
      throw new Error('hermes down');
    }) as any;
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const { POST } = await import('../voice-usage/route');
    const res = await POST(makeRequest({ session_id: 's1', seconds_delta: 60 }) as any);
    expect(res.status).toBe(200);
    warnSpy.mockRestore();
  });
});
