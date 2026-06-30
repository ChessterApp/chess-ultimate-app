import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));

vi.mock('@/lib/chess-empire-admin', async () => {
  const actual = await vi.importActual<typeof import('@/lib/chess-empire-admin')>(
    '@/lib/chess-empire-admin',
  );
  return { ...actual, revokeBranchToken: vi.fn() };
});

import { auth } from '@clerk/nextjs/server';
import { revokeBranchToken, OrgScopeError } from '@/lib/chess-empire-admin';

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

describe('POST /chess-empire/branch-tokens/[tokenId]/revoke', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 unauthed', async () => {
    mockAuth(null);
    const { POST } = await import('../revoke/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, tokenId: TOKEN }),
    });
    expect(r.status).toBe(401);
  });

  it('happy path returns revoked row', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (revokeBranchToken as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue({ id: 't-1', revoked_at: '2026-06-30T19:00:00Z' });
    const { POST } = await import('../revoke/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, tokenId: TOKEN }),
    });
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.revoked.id).toBe('t-1');
  });

  it('403 org-scope mismatch', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (revokeBranchToken as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new OrgScopeError());
    const { POST } = await import('../revoke/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, tokenId: TOKEN }),
    });
    expect(r.status).toBe(403);
  });
});
