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

describe('GET /api/admin/organizations/[orgId]/refunds', () => {
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

  it('forwards X-User-Id', async () => {
    mockAuth('user_1');
    const spy = mockFetch(200, { refunds: [{ id: 'r1', amount_cents: 12900 }] });
    global.fetch = spy as unknown as typeof fetch;
    const { GET } = await import('../route');
    const r = await GET(
      new Request('http://localhost') as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(200);
    const headers = (spy.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers['X-User-Id']).toBe('user_1');
  });

  it('forwards 403', async () => {
    mockAuth('user_1');
    global.fetch = mockFetch(403, { error: 'Forbidden' }) as unknown as typeof fetch;
    const { GET } = await import('../route');
    const r = await GET(
      new Request('http://localhost') as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(403);
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
