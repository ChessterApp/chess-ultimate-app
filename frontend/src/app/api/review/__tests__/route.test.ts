import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { NextRequest } from 'next/server';

const authMock = vi.fn();
vi.mock('@clerk/nextjs/server', () => ({ auth: () => authMock() }));

import { POST } from '../route';

const fetchMock = vi.fn();

function req(body: unknown) {
  return new NextRequest('http://localhost/api/review', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

function forwarded() {
  return JSON.parse(fetchMock.mock.calls[0][1].body as string);
}

describe('POST /api/review', () => {
  beforeEach(() => {
    fetchMock.mockReset().mockResolvedValue(
      new Response(JSON.stringify({ review_id: 'r1', status: 'queued' })),
    );
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('forwards the Clerk id as analytics_user_id plus source', async () => {
    authMock.mockResolvedValue({ userId: 'user_9' });
    const res = await POST(req({ pgn: '1. e4', source: 'bot', user_id: 'spoofed' }));
    expect(res.status).toBe(200);
    expect(forwarded()).toEqual({ pgn: '1. e4', analytics_user_id: 'user_9', source: 'bot' });
  });

  it('forwards only the pgn for anonymous callers', async () => {
    authMock.mockResolvedValue({ userId: null });
    await POST(req({ pgn: '1. e4' }));
    expect(forwarded()).toEqual({ pgn: '1. e4' });
  });

  it('rejects a missing pgn', async () => {
    authMock.mockResolvedValue({ userId: 'user_9' });
    const res = await POST(req({}));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
