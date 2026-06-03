import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';

const ORG = 'org-123';

function mockAuth(userId: string | null) {
  (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
    userId,
  });
}

function mockFetch(status: number, json: Record<string, unknown>) {
  return vi.fn(() =>
    Promise.resolve({
      status,
      json: () => Promise.resolve(json),
    } as Response),
  );
}

describe('GET /api/admin/organizations/[orgId]/ownership-transfers', () => {
  const realFetch = global.fetch;
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('returns 401 when not authed', async () => {
    mockAuth(null);
    const { GET } = await import('../route');
    const r = await GET(
      new Request('http://localhost') as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(401);
  });

  it('proxies to backend with X-User-Id', async () => {
    mockAuth('user_1');
    const fetchSpy = mockFetch(200, { transfers: [] });
    global.fetch = fetchSpy as unknown as typeof fetch;
    const { GET } = await import('../route');
    const r = await GET(
      new Request('http://localhost') as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const callInit = fetchSpy.mock.calls[0][1] as RequestInit;
    const headers = callInit.headers as Record<string, string>;
    expect(headers['X-User-Id']).toBe('user_1');
  });

  it('502 on network failure', async () => {
    mockAuth('user_1');
    global.fetch = vi.fn(() => Promise.reject(new Error('boom'))) as unknown as typeof fetch;
    const { GET } = await import('../route');
    const r = await GET(
      new Request('http://localhost') as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(502);
  });
});

describe('POST /api/admin/organizations/[orgId]/ownership-transfers', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 when unauthed', async () => {
    mockAuth(null);
    const { POST } = await import('../route');
    const r = await POST(
      new Request('http://localhost', {
        method: 'POST',
        body: JSON.stringify({ invitee_email: 'a@b.com' }),
      }) as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(401);
  });

  it('forwards body + returns backend status', async () => {
    mockAuth('user_1');
    const fetchSpy = mockFetch(201, { transfer: { id: 't1', state: 'invite_pending' } });
    global.fetch = fetchSpy as unknown as typeof fetch;
    const { POST } = await import('../route');
    const r = await POST(
      new Request('http://localhost', {
        method: 'POST',
        body: JSON.stringify({ invitee_email: 'a@b.com' }),
      }) as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(201);
    expect(fetchSpy).toHaveBeenCalled();
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      invitee_email: 'a@b.com',
    });
  });

  it('forwards backend error status', async () => {
    mockAuth('user_1');
    global.fetch = mockFetch(403, { error: 'Forbidden' }) as unknown as typeof fetch;
    const { POST } = await import('../route');
    const r = await POST(
      new Request('http://localhost', { method: 'POST', body: '{}' }) as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(403);
  });
});
