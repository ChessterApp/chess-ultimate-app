import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));

vi.mock('@/lib/chess-empire-admin', async () => {
  const actual = await vi.importActual<typeof import('@/lib/chess-empire-admin')>(
    '@/lib/chess-empire-admin',
  );
  return { ...actual, setMemberAccessExpiry: vi.fn() };
});

import { auth } from '@clerk/nextjs/server';
import {
  setMemberAccessExpiry,
  OrgScopeError,
  NotOnlineMemberError,
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

function patchReq(body: string | undefined) {
  return new Request('http://localhost', {
    method: 'PATCH',
    body,
  }) as never;
}

describe('PATCH /chess-empire/members/[memberId]/access', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 unauthed', async () => {
    mockAuth(null);
    const { PATCH } = await import('../access/route');
    const r = await PATCH(patchReq('{}'), {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(401);
  });

  it('403 when caller is not an admin', async () => {
    mockAuth('user_1');
    mockBackendMembers('student');
    const { PATCH } = await import('../access/route');
    const r = await PATCH(patchReq('{"accessExpiresAt":null}'), {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(403);
  });

  it('400 when accessExpiresAt is missing', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    const { PATCH } = await import('../access/route');
    const r = await PATCH(patchReq('{}'), {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(400);
    expect((await r.json()).error).toBe('invalid_body');
  });

  it('400 when the date is not ISO-parseable', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    const { PATCH } = await import('../access/route');
    const r = await PATCH(patchReq('{"accessExpiresAt":"not-a-date"}'), {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(400);
    expect((await r.json()).error).toBe('invalid_date');
  });

  it('200 upgrade to full (null) returns updated member', async () => {
    mockAuth('user_1');
    mockBackendMembers('owner');
    (setMemberAccessExpiry as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue({ id: 'm-1', access_expires_at: null });
    const { PATCH } = await import('../access/route');
    const r = await PATCH(patchReq('{"accessExpiresAt":null}'), {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.member.access_expires_at).toBeNull();
    const call = (setMemberAccessExpiry as unknown as { mock: { calls: unknown[][] } })
      .mock.calls[0][0] as { accessExpiresAt: string | null };
    expect(call.accessExpiresAt).toBeNull();
  });

  it('200 with a valid ISO date normalises and passes it through', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (setMemberAccessExpiry as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue({ id: 'm-1', access_expires_at: '2026-12-31T18:00:00.000Z' });
    const { PATCH } = await import('../access/route');
    const r = await PATCH(patchReq('{"accessExpiresAt":"2026-12-31T18:00:00Z"}'), {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(200);
    const call = (setMemberAccessExpiry as unknown as { mock: { calls: unknown[][] } })
      .mock.calls[0][0] as { accessExpiresAt: string | null };
    expect(call.accessExpiresAt).toBe('2026-12-31T18:00:00.000Z');
  });

  it('403 on org-scope mismatch', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (setMemberAccessExpiry as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new OrgScopeError());
    const { PATCH } = await import('../access/route');
    const r = await PATCH(patchReq('{"accessExpiresAt":null}'), {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(403);
    expect((await r.json()).error).toBe('forbidden');
  });

  it('403 for a non-online member', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (setMemberAccessExpiry as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new NotOnlineMemberError());
    const { PATCH } = await import('../access/route');
    const r = await PATCH(patchReq('{"accessExpiresAt":null}'), {
      params: Promise.resolve({ orgId: ORG, memberId: MEMBER }),
    });
    expect(r.status).toBe(403);
    expect((await r.json()).error).toBe('not_online_member');
  });
});
