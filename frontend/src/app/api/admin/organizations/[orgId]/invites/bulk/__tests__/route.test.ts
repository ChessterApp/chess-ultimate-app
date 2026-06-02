import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';

describe('POST /api/admin/organizations/<id>/invites/bulk', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function req(body: unknown) {
    return new Request('http://localhost/api/admin/organizations/abc/invites/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  it('returns 401 when unauthenticated', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: null });
    const { POST } = await import('../route');
    const r = await POST(req({ invites: [] }) as never, {
      params: Promise.resolve({ orgId: 'abc' }),
    });
    expect(r.status).toBe(401);
  });

  it('proxies the request to backend with X-User-Id', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_1' });
    const captured: { url?: string; init?: RequestInit } = {};
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (url: unknown, init: unknown) => {
      captured.url = url as string;
      captured.init = init as RequestInit;
      return new Response(
        JSON.stringify({ accepted: [], rejected: [], remaining_seats: 5 }),
        { status: 201, headers: { 'Content-Type': 'application/json' } },
      );
    }) as typeof fetch;

    try {
      const { POST } = await import('../route');
      const r = await POST(req({ invites: [{ email: 'a@x.com' }] }) as never, {
        params: Promise.resolve({ orgId: 'org-123' }),
      });
      expect(r.status).toBe(201);
      const data = await r.json();
      expect(data.remaining_seats).toBe(5);
      expect(captured.url).toContain('/api/admin/organizations/org-123/invites/bulk');
      const headers = captured.init?.headers as Record<string, string>;
      expect(headers['X-User-Id']).toBe('user_1');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('passes backend errors through with status code', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_1' });
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ error: 'bulk_insert_failed' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    ) as typeof fetch;
    try {
      const { POST } = await import('../route');
      const r = await POST(req({ invites: [{ email: 'a@x.com' }] }) as never, {
        params: Promise.resolve({ orgId: 'org-123' }),
      });
      expect(r.status).toBe(500);
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});
