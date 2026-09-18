/**
 * Tests for POST /api/chess-empire/link/invite — cross-branch "join family"
 * invite creation + email send. Covers: unauthenticated (401), bad body (400),
 * missing name+email (400), invalid email (400), unlinked inviter (403), and the
 * happy paths (email → invite created + email sent; name-only → created, no send).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'inviter-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

interface FakeMember {
  studentId: string | null;
  relationship: 'self' | 'child' | 'other';
}
const memberStore: { members: FakeMember[] } = {
  members: [{ studentId: 'stu-self', relationship: 'self' }],
};
vi.mock('@/lib/chess-empire-member', () => ({
  getVerifiedMembersForUser: vi.fn(async () => memberStore.members),
}));

vi.mock('@/lib/chess-empire-client', () => ({
  getStudentDisplayName: vi.fn(async () => 'Alex Parent'),
}));

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: () => {
      const chain = {
        select: () => chain,
        eq: () => chain,
        limit: async () => ({ data: [{ organization_id: 'org-1' }], error: null }),
      };
      return chain;
    },
  },
}));

const createSpy = vi.fn(async () => ({ id: 'inv-1', token: 'tok-abc' }));
vi.mock('@/lib/family-link-invite', () => ({
  createFamilyLinkInvite: (...args: unknown[]) => createSpy(...args),
}));

const emailSpy = vi.fn(async () => true);
vi.mock('@/lib/family-invite-email', () => ({
  sendFamilyInviteEmail: (...args: unknown[]) => emailSpy(...args),
  familyInviteAcceptUrl: (token: string) => `https://ce/family/join/${token}`,
}));

import { POST } from '../invite/route';
import { _resetRateLimitForTests } from '@/lib/in-memory-rate-limit';

function makeReq(body: unknown, ip = '3.3.3.3'): Request {
  return new Request('https://x/api/chess-empire/link/invite', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-forwarded-for': ip },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

beforeEach(() => {
  _resetRateLimitForTests();
  authStore.userId = 'inviter-1';
  memberStore.members = [{ studentId: 'stu-self', relationship: 'self' }];
  createSpy.mockClear();
  emailSpy.mockClear();
});

describe('POST /api/chess-empire/link/invite', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await POST(makeReq({ email: 'a@b.com' }) as never);
    expect(res.status).toBe(401);
    expect(createSpy).not.toHaveBeenCalled();
  });

  it('400 on invalid JSON body', async () => {
    const res = await POST(makeReq('not-json') as never);
    expect(res.status).toBe(400);
  });

  it('400 when neither name nor email is provided', async () => {
    const res = await POST(makeReq({}) as never);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'missing_fields' });
  });

  it('400 on a malformed email', async () => {
    const res = await POST(makeReq({ email: 'not-an-email' }) as never);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'invalid_email' });
  });

  it('403 when the inviter is not a verified member', async () => {
    memberStore.members = [];
    const res = await POST(makeReq({ email: 'a@b.com' }) as never);
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ error: 'not_linked' });
    expect(createSpy).not.toHaveBeenCalled();
  });

  it('creates the invite and sends the email on the happy path', async () => {
    const res = await POST(
      makeReq({ email: 'kid@example.com', relationship: 'other' }) as never,
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      ok: true,
      emailSent: true,
      targetEmail: 'kid@example.com',
    });
    expect(createSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        inviterUserId: 'inviter-1',
        inviterOrgId: 'org-1',
        inviterStudentId: 'stu-self',
        targetEmail: 'kid@example.com',
        relationship: 'other',
      }),
    );
    expect(emailSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        toEmail: 'kid@example.com',
        acceptUrl: 'https://ce/family/join/tok-abc',
      }),
    );
  });

  it('creates a name-only invite without sending an email', async () => {
    const res = await POST(makeReq({ name: 'Cousin Bo' }) as never);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      ok: true,
      emailSent: false,
      targetEmail: null,
    });
    expect(createSpy).toHaveBeenCalledWith(
      expect.objectContaining({ targetName: 'Cousin Bo', targetEmail: null }),
    );
    expect(emailSpy).not.toHaveBeenCalled();
  });
});
