import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));

vi.mock('@/lib/chess-empire-admin', async () => {
  const actual = await vi.importActual<typeof import('@/lib/chess-empire-admin')>(
    '@/lib/chess-empire-admin',
  );
  return { ...actual, freezeMember: vi.fn(), unfreezeMember: vi.fn() };
});

import { auth } from '@clerk/nextjs/server';
import {
  freezeMember,
  unfreezeMember,
  OrgScopeError,
} from '@/lib/chess-empire-admin';

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

describe('POST /chess-empire/members/[memberId]/freeze', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 unauthed', async () => {
    mockAuth(null);
    const { POST } = await import('../freeze/route');
    const r = await POST(new Request('http://localhost', { method: 'POST' }) as never, {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(401);
  });

  it('freezes when body has no unfreeze flag', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (freezeMember as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue({ id: 'm-1', link_status: 'frozen' });
    const { POST } = await import('../freeze/route');
    const r = await POST(
      new Request('http://localhost', { method: 'POST', body: '{}' }) as never,
      { params: Promise.resolve({ orgId: ORG, memberId: MEMBER }) },
    );
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.frozen).toBe(true);
    expect(data.member.link_status).toBe('frozen');
    expect(freezeMember).toHaveBeenCalled();
    expect(unfreezeMember).not.toHaveBeenCalled();
  });

  it('unfreezes when body has unfreeze=true', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (unfreezeMember as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue({ id: 'm-1', link_status: 'verified' });
    const { POST } = await import('../freeze/route');
    const r = await POST(
      new Request('http://localhost', {
        method: 'POST',
        body: JSON.stringify({ unfreeze: true }),
      }) as never,
      { params: Promise.resolve({ orgId: ORG, memberId: MEMBER }) },
    );
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.frozen).toBe(false);
    expect(data.member.link_status).toBe('verified');
    expect(unfreezeMember).toHaveBeenCalled();
  });

  it('403 on org-scope mismatch', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (freezeMember as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new OrgScopeError());
    const { POST } = await import('../freeze/route');
    const r = await POST(
      new Request('http://localhost', { method: 'POST', body: '{}' }) as never,
      { params: Promise.resolve({ orgId: ORG, memberId: MEMBER }) },
    );
    expect(r.status).toBe(403);
  });
});
