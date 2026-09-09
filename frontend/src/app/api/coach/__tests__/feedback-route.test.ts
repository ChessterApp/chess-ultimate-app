import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock Clerk auth
vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';

async function postFeedback(body: unknown) {
  const { POST } = await import('../../coach/feedback/route');
  const { NextRequest } = await import('next/server');
  const request = new NextRequest('http://localhost:3000/api/coach/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return POST(request as never);
}

describe('POST /api/coach/feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    (auth as never as ReturnType<typeof vi.fn>).mockResolvedValue({ userId: null });
    const res = await postFeedback({ turn_id: 't1', rating: 1 });
    expect(res.status).toBe(401);
    expect((await res.json()).error).toBe('Unauthorized');
  });

  it('returns 400 when turn_id is missing', async () => {
    (auth as never as ReturnType<typeof vi.fn>).mockResolvedValue({ userId: 'u1' });
    const res = await postFeedback({ rating: 1 });
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('Missing turn_id');
  });

  it('returns 400 on an invalid rating', async () => {
    (auth as never as ReturnType<typeof vi.fn>).mockResolvedValue({ userId: 'u1' });
    const res = await postFeedback({ turn_id: 't1', rating: 5 });
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('Invalid rating');
  });

  it('proxies to Hermes with X-User-Id and returns its body', async () => {
    (auth as never as ReturnType<typeof vi.fn>).mockResolvedValue({ userId: 'u1' });
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ ok: true, persisted: true }),
    }));
    global.fetch = fetchMock as never;

    const res = await postFeedback({
      turn_id: 't1',
      rating: -1,
      session_id: 's1',
      surface: 'text',
    });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, persisted: true });

    const [url, opts] = fetchMock.mock.calls[0] as never as [string, Record<string, never>];
    expect(url).toContain('/api/coach/feedback');
    expect((opts.headers as Record<string, string>)['X-User-Id']).toBe('u1');
    expect(JSON.parse(opts.body as never)).toEqual({
      turn_id: 't1',
      rating: -1,
      session_id: 's1',
      comment: undefined,
      surface: 'text',
      client_ts: undefined,
    });
  });

  it('accepts rating 0 (retraction)', async () => {
    (auth as never as ReturnType<typeof vi.fn>).mockResolvedValue({ userId: 'u1' });
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ ok: true, persisted: true }),
    })) as never;
    const res = await postFeedback({ turn_id: 't1', rating: 0 });
    expect(res.status).toBe(200);
  });

  it('returns 502 when Hermes is unreachable', async () => {
    (auth as never as ReturnType<typeof vi.fn>).mockResolvedValue({ userId: 'u1' });
    global.fetch = vi.fn(async () => {
      throw new Error('ECONNREFUSED');
    }) as never;
    const res = await postFeedback({ turn_id: 't1', rating: 1 });
    expect(res.status).toBe(502);
    expect((await res.json()).ok).toBe(false);
  });

  it('returns 502 when Hermes responds non-ok', async () => {
    (auth as never as ReturnType<typeof vi.fn>).mockResolvedValue({ userId: 'u1' });
    global.fetch = vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })) as never;
    const res = await postFeedback({ turn_id: 't1', rating: 1 });
    expect(res.status).toBe(502);
  });
});
