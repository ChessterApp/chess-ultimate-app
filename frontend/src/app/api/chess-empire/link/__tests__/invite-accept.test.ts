/**
 * Tests for POST /api/chess-empire/link/invite/accept — the consent step of the
 * cross-branch "join family" flow. Covers: unauthenticated (401), bad body /
 * missing token (400), reject action, unlinked accepter (403), the happy accept
 * path (edge stamped with the accepter's real student/org), and the mapped
 * errors: not-found (404), not-pending (409), email mismatch (403).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'target-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
  clerkClient: async () => ({
    users: {
      getUser: async () => ({
        primaryEmailAddressId: 'e1',
        emailAddresses: [{ id: 'e1', emailAddress: 'target@example.com' }],
      }),
    },
  }),
}));

interface FakeMember {
  studentId: string | null;
  relationship: 'self' | 'child' | 'other';
}
const memberStore: { members: FakeMember[] } = {
  members: [{ studentId: 'stu-target', relationship: 'self' }],
};
vi.mock('@/lib/chess-empire-member', () => ({
  getVerifiedMembersForUser: vi.fn(async () => memberStore.members),
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

// The error classes are defined inside the factory (referenced eagerly), then
// re-imported below so the route's `instanceof` checks hold.
const acceptControl = {
  current: async (..._args: unknown[]) => ({ inviterUserId: 'inviter-1' }),
};
const acceptSpy = vi.fn((...args: unknown[]) => acceptControl.current(...args));
const rejectSpy = vi.fn(async () => {});
vi.mock('@/lib/family-link-invite', () => {
  class InviteNotFoundError extends Error {}
  class InviteNotPendingError extends Error {}
  class InviteEmailMismatchError extends Error {}
  return {
    InviteNotFoundError,
    InviteNotPendingError,
    InviteEmailMismatchError,
    acceptFamilyLinkInvite: (...args: unknown[]) => acceptSpy(...args),
    rejectFamilyLinkInvite: (...args: unknown[]) => rejectSpy(...args),
  };
});

import { POST } from '../invite/accept/route';
import {
  InviteNotFoundError,
  InviteNotPendingError,
  InviteEmailMismatchError,
} from '@/lib/family-link-invite';
import { _resetRateLimitForTests } from '@/lib/in-memory-rate-limit';

function makeReq(body: unknown): Request {
  return new Request('https://x/api/chess-empire/link/invite/accept', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

beforeEach(() => {
  _resetRateLimitForTests();
  authStore.userId = 'target-1';
  memberStore.members = [{ studentId: 'stu-target', relationship: 'self' }];
  acceptControl.current = async () => ({ inviterUserId: 'inviter-1' });
  acceptSpy.mockClear();
  rejectSpy.mockClear();
});

describe('POST /api/chess-empire/link/invite/accept', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await POST(makeReq({ token: 't' }) as never);
    expect(res.status).toBe(401);
  });

  it('400 on invalid JSON body', async () => {
    const res = await POST(makeReq('nope') as never);
    expect(res.status).toBe(400);
  });

  it('400 when the token is missing', async () => {
    const res = await POST(makeReq({}) as never);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'missing_token' });
  });

  it('rejects an invite without touching the accept path', async () => {
    const res = await POST(makeReq({ token: 'tok', action: 'reject' }) as never);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, status: 'rejected' });
    expect(rejectSpy).toHaveBeenCalledWith('tok');
    expect(acceptSpy).not.toHaveBeenCalled();
  });

  it('403 when the accepter has no verified link of their own', async () => {
    memberStore.members = [];
    const res = await POST(makeReq({ token: 'tok' }) as never);
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ error: 'accepter_not_linked' });
    expect(acceptSpy).not.toHaveBeenCalled();
  });

  it('accepts and stamps the accepter real student/org on the happy path', async () => {
    const res = await POST(makeReq({ token: 'tok' }) as never);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, status: 'accepted' });
    expect(acceptSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        token: 'tok',
        accepterUserId: 'target-1',
        accepterEmail: 'target@example.com',
        accepterStudentId: 'stu-target',
        accepterOrgId: 'org-1',
      }),
    );
  });

  it('404 when the invite does not exist', async () => {
    acceptControl.current = async () => {
      throw new InviteNotFoundError();
    };
    const res = await POST(makeReq({ token: 'tok' }) as never);
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: 'not_found' });
  });

  it('409 when the invite is no longer pending', async () => {
    acceptControl.current = async () => {
      throw new InviteNotPendingError();
    };
    const res = await POST(makeReq({ token: 'tok' }) as never);
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: 'not_pending' });
  });

  it('403 when the accepter email does not match the invite', async () => {
    acceptControl.current = async () => {
      throw new InviteEmailMismatchError();
    };
    const res = await POST(makeReq({ token: 'tok' }) as never);
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ error: 'email_mismatch' });
  });
});
