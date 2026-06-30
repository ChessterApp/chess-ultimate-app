import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));

vi.mock('@/lib/chess-empire-admin', async () => {
  const actual = await vi.importActual<typeof import('@/lib/chess-empire-admin')>(
    '@/lib/chess-empire-admin',
  );
  return { ...actual, rotateBranchToken: vi.fn() };
});

import { auth } from '@clerk/nextjs/server';
import { rotateBranchToken, OrgScopeError, NotFoundError } from '@/lib/chess-empire-admin';

const ORG = 'org-ce';
const TOKEN = 't-1';

function mockAuth(userId: string | null) {
  (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
    userId,
  });
}

function mockBackendMembers(role: string | null) {
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          members: role ? [{ user_id: 'user_1', role }] : [],
        }),
    } as Response),
  ) as unknown as typeof fetch;
}

describe('POST /chess-empire/branch-tokens/[tokenId]/rotate', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 when unauthed', async () => {
    mockAuth(null);
    const { POST } = await import('../rotate/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, tokenId: TOKEN }),
    });
    expect(r.status).toBe(401);
  });

  it('happy path returns revoked + created + url', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (rotateBranchToken as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue({
        revoked: { id: 't-1', revoked_at: '2026-06-30T19:00:00Z' },
        created: { id: 't-2', token: 'fresh' },
      });
    const { POST } = await import('../rotate/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, tokenId: TOKEN }),
    });
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.url).toContain('/welcome/fresh');
    expect(data.created.id).toBe('t-2');
  });

  it('403 on org-scope mismatch', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (rotateBranchToken as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new OrgScopeError());
    const { POST } = await import('../rotate/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, tokenId: TOKEN }),
    });
    expect(r.status).toBe(403);
  });

  it('404 when token missing', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (rotateBranchToken as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new NotFoundError());
    const { POST } = await import('../rotate/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, tokenId: TOKEN }),
    });
    expect(r.status).toBe(404);
  });
});
