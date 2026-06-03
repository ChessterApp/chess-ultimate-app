import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';

const ORG = 'org-xyz';

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

describe('GET /api/admin/organizations/[orgId]/branches', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 when not authed', async () => {
    mockAuth(null);
    const { GET } = await import('../route');
    const r = await GET(
      new Request('http://localhost') as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(401);
  });

  it('forwards to backend with X-User-Id', async () => {
    mockAuth('user_1');
    const spy = mockFetch(200, { branches: [] });
    global.fetch = spy as unknown as typeof fetch;
    const { GET } = await import('../route');
    const r = await GET(
      new Request('http://localhost') as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(200);
    const init = spy.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers['X-User-Id']).toBe('user_1');
  });
});

describe('POST /api/admin/organizations/[orgId]/branches', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 when not authed', async () => {
    mockAuth(null);
    const { POST } = await import('../route');
    const r = await POST(
      new Request('http://localhost', { method: 'POST', body: '{}' }) as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(401);
  });

  it('forwards body and returns 201', async () => {
    mockAuth('user_1');
    const spy = mockFetch(201, { branch: { id: 'b1', name: 'X' } });
    global.fetch = spy as unknown as typeof fetch;
    const { POST } = await import('../route');
    const r = await POST(
      new Request('http://localhost', {
        method: 'POST',
        body: JSON.stringify({ name: 'X', slug: 'x' }),
      }) as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(201);
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ name: 'X', slug: 'x' });
  });

  it('forwards 403 from backend', async () => {
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
