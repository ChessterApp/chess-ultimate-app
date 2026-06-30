import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));

vi.mock('@/lib/chess-empire-admin', async () => {
  const actual = await vi.importActual<typeof import('@/lib/chess-empire-admin')>(
    '@/lib/chess-empire-admin',
  );
  return { ...actual, revokeMember: vi.fn() };
});

import { auth } from '@clerk/nextjs/server';
import { revokeMember, OrgScopeError } from '@/lib/chess-empire-admin';

const ORG = 'org-ce';
const MEMBER = 'm-1';

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

describe('POST /chess-empire/members/[memberId]/revoke', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 unauthed', async () => {
    mockAuth(null);
    const { POST } = await import('../revoke/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(401);
  });

  it('happy path returns the updated member', async () => {
    mockAuth('user_1');
    mockBackendMembers('owner');
    (revokeMember as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue({ id: MEMBER, link_status: 'revoked' });
    const { POST } = await import('../revoke/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.member.link_status).toBe('revoked');
  });

  it('403 on org-scope mismatch', async () => {
    mockAuth('user_1');
    mockBackendMembers('owner');
    (revokeMember as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new OrgScopeError());
    const { POST } = await import('../revoke/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(403);
  });
});
