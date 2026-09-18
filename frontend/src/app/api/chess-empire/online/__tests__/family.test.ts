/**
 * Tests for POST /api/chess-empire/online/family.
 *
 * The online counterpart of "add family member": it MINTS a fresh synthetic
 * online student under the caller's own Clerk account (no CE roster, no search).
 * Covers: unauthenticated (401), a non-online caller (403 not_online), a bad /
 * missing relationship (400), a missing name (400), the happy path (a verified
 * online child written through the shared `upsertMemberLink` writer with a fresh
 * 72h TTL + the chosen relationship + name), and the per-IP rate-limit (429).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

interface FakeMember {
  state: string;
  studentId: string | null;
  relationship: 'self' | 'child' | 'other';
  source: 'chess_empire' | 'online';
}
const memberStore: { members: FakeMember[]; throws: boolean } = {
  members: [],
  throws: false,
};
vi.mock('@/lib/chess-empire-member', () => ({
  getVerifiedMembersForUser: vi.fn(async () => {
    if (memberStore.throws) throw new Error('boom');
    return memberStore.members;
  }),
}));

const upsertMock = vi.fn(async () => undefined);
vi.mock('@/lib/chess-empire-jwt-link', () => ({
  upsertMemberLink: (...args: unknown[]) => upsertMock(...args),
}));

// supabaseAdmin resolves the caller's online member row → organization_id. The
// chain ends in `.limit(1)`, which awaits to `{ data, error }`.
const orgStore: { data: unknown; error: unknown } = {
  data: [{ organization_id: 'org-1' }],
  error: null,
};
vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: () => {
      const chain: Record<string, unknown> = {
        select: () => chain,
        eq: () => chain,
        limit: () => Promise.resolve({ data: orgStore.data, error: orgStore.error }),
      };
      return chain;
    },
  },
}));

import { POST } from '../family/route';
import { _resetRateLimitForTests } from '@/lib/in-memory-rate-limit';
import { NextRequest } from 'next/server';

const ONLINE_SELF: FakeMember = {
  state: 'verified',
  studentId: 'stu-self',
  relationship: 'self',
  source: 'online',
};
const BRANCH_SELF: FakeMember = {
  state: 'verified',
  studentId: 'stu-branch',
  relationship: 'self',
  source: 'chess_empire',
};

function makeReq(body: unknown): NextRequest {
  return new NextRequest('http://x/api/chess-empire/online/family', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  authStore.userId = 'user-1';
  memberStore.members = [ONLINE_SELF];
  memberStore.throws = false;
  orgStore.data = [{ organization_id: 'org-1' }];
  orgStore.error = null;
  upsertMock.mockClear();
  _resetRateLimitForTests();
});

describe('POST /api/chess-empire/online/family', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await POST(makeReq({ name: 'Sam', relationship: 'child' }));
    expect(res.status).toBe(401);
    expect(upsertMock).not.toHaveBeenCalled();
  });

  it('403 not_online when the caller has no verified online member', async () => {
    memberStore.members = [BRANCH_SELF];
    const res = await POST(makeReq({ name: 'Sam', relationship: 'child' }));
    expect(res.status).toBe(403);
    expect((await res.json()).error).toBe('not_online');
    expect(upsertMock).not.toHaveBeenCalled();
  });

  it('400 when the name is missing', async () => {
    const res = await POST(makeReq({ relationship: 'child' }));
    expect(res.status).toBe(400);
    expect(upsertMock).not.toHaveBeenCalled();
  });

  it('400 invalid_relationship for a bad relationship', async () => {
    expect((await POST(makeReq({ name: 'Sam' }))).status).toBe(400);
    expect(
      (await POST(makeReq({ name: 'Sam', relationship: 'self' }))).status,
    ).toBe(400);
    const res = await POST(makeReq({ name: 'Sam', relationship: 'cousin' }));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('invalid_relationship');
    expect(upsertMock).not.toHaveBeenCalled();
  });

  it('mints a verified online child with a fresh 72h TTL + the chosen relationship', async () => {
    const res = await POST(makeReq({ name: '  Aruzhan  ', relationship: 'child' }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      ok: boolean;
      studentId: string;
      relationship: string;
    };
    expect(body.ok).toBe(true);
    expect(body.relationship).toBe('child');
    // A synthetic UUID — its own student, not a CE record.
    expect(body.studentId).toMatch(/^[0-9a-f-]{36}$/);

    expect(upsertMock).toHaveBeenCalledTimes(1);
    const arg = upsertMock.mock.calls[0][0] as Record<string, unknown>;
    expect(arg.orgId).toBe('org-1');
    expect(arg.clerkUserId).toBe('user-1');
    expect(arg.studentId).toBe(body.studentId);
    expect(arg.linkStatus).toBe('verified');
    expect(arg.externalSource).toBe('online');
    expect(arg.accessTtlHours).toBe(72);
    expect(arg.relationship).toBe('child');
    // Name is trimmed before it is written to the roster row.
    expect(arg.name).toBe('Aruzhan');
  });

  it("mints with relationship='other' when requested", async () => {
    const res = await POST(makeReq({ name: 'Grandpa', relationship: 'other' }));
    expect(res.status).toBe(200);
    expect((upsertMock.mock.calls[0][0] as { relationship: string }).relationship).toBe(
      'other',
    );
  });

  it('500 when the caller has no resolvable org id', async () => {
    orgStore.data = [];
    const res = await POST(makeReq({ name: 'Sam', relationship: 'child' }));
    expect(res.status).toBe(500);
    expect(upsertMock).not.toHaveBeenCalled();
  });

  it('rate-limits after 20 requests from the same IP (429)', async () => {
    for (let i = 0; i < 20; i++) {
      const ok = await POST(makeReq({ name: `Kid ${i}`, relationship: 'child' }));
      expect(ok.status).toBe(200);
    }
    const res = await POST(makeReq({ name: 'Kid 21', relationship: 'child' }));
    expect(res.status).toBe(429);
  });

  it('mints each family member its own distinct synthetic student id', async () => {
    const a = (await (
      await POST(makeReq({ name: 'A', relationship: 'child' }))
    ).json()) as { studentId: string };
    const b = (await (
      await POST(makeReq({ name: 'B', relationship: 'child' }))
    ).json()) as { studentId: string };
    expect(a.studentId).not.toBe(b.studentId);
  });
});
