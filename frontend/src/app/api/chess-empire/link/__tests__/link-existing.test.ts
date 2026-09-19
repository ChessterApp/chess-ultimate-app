/**
 * Tests for POST /api/chess-empire/link/link-existing — same-branch instant
 * family link. Covers: unauthenticated (401), bad body (400), invalid/expired
 * token (401), duplicate student (409 ALREADY_REGISTERED), branch mismatch and
 * inactive (401), not-found student (404), and the happy path writing a verified
 * `relationship='child'|'other'` member row via `upsertMemberLink`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'parent-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

const db: {
  tokenRow: Record<string, unknown> | null;
  existingMember: Record<string, unknown> | null;
} = { tokenRow: null, existingMember: null };
vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => {
      const chain = {
        select: () => chain,
        eq: () => chain,
        in: () => chain,
        maybeSingle: async () => {
          if (table === 'branch_invite_tokens') {
            return { data: db.tokenRow, error: null };
          }
          if (table === 'organization_members') {
            return { data: db.existingMember, error: null };
          }
          return { data: null, error: null };
        },
      };
      return chain;
    },
  },
}));

const profileStore: {
  branchId: string;
  status: string;
  throwStatus: number | null;
  branchById: Record<string, string> | null;
} = {
  branchId: 'branch-1',
  status: 'active',
  throwStatus: null,
  branchById: null,
};
vi.mock('@/lib/chess-empire-client', () => {
  class ChessEmpireAPIError extends Error {
    statusCode: number;
    constructor(statusCode: number) {
      super('ce');
      this.statusCode = statusCode;
      this.name = 'ChessEmpireAPIError';
    }
  }
  return {
    ChessEmpireAPIError,
    getStudentProfile: vi.fn(async (id: string) => {
      if (profileStore.throwStatus) throw new ChessEmpireAPIError(profileStore.throwStatus);
      const branch_id = profileStore.branchById?.[id] ?? profileStore.branchId;
      return { branch_id, status: profileStore.status };
    }),
    getStudentDisplayName: vi.fn(async () => 'Aruzhan A'),
  };
});

// The token-less path derives the caller's org + branch from their verified
// membership; the token path never touches this.
const membersStore: { members: Array<Record<string, unknown>> } = { members: [] };
vi.mock('@/lib/chess-empire-member', () => ({
  getVerifiedMembersForUser: vi.fn(async () => membersStore.members),
}));

const upsertSpy = vi.fn(async () => {});
vi.mock('@/lib/chess-empire-jwt-link', () => ({
  upsertMemberLink: (...args: unknown[]) => upsertSpy(...args),
}));

import { POST } from '../link-existing/route';
import { _resetRateLimitForTests } from '@/lib/in-memory-rate-limit';

function makeReq(body: unknown, ip = '2.2.2.2'): Request {
  return new Request('https://x/api/chess-empire/link/link-existing', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-forwarded-for': ip },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

const goodToken = {
  id: 'bt-1',
  organization_id: 'org-1',
  external_branch_id: 'branch-1',
  expires_at: null,
  revoked_at: null,
};

const SELF_MEMBER = {
  state: 'verified',
  studentId: 'stu-self',
  memberId: 'm-1',
  role: 'student',
  source: 'chess_empire',
  relationship: 'self',
  orgId: 'org-1',
};

beforeEach(() => {
  _resetRateLimitForTests();
  authStore.userId = 'parent-1';
  db.tokenRow = { ...goodToken };
  db.existingMember = null;
  profileStore.branchId = 'branch-1';
  profileStore.status = 'active';
  profileStore.throwStatus = null;
  profileStore.branchById = null;
  membersStore.members = [{ ...SELF_MEMBER }];
  upsertSpy.mockClear();
});

describe('POST /api/chess-empire/link/link-existing', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await POST(makeReq({ branchToken: 'tok', studentId: 's' }) as never);
    expect(res.status).toBe(401);
    expect(upsertSpy).not.toHaveBeenCalled();
  });

  it('400 on invalid JSON body', async () => {
    const res = await POST(makeReq('not-json') as never);
    expect(res.status).toBe(400);
  });

  it('400 when fields are missing', async () => {
    const res = await POST(makeReq({ branchToken: 'tok' }) as never);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'missing_fields' });
  });

  it('an unresolvable token falls back to caller membership (rejects when none)', async () => {
    // A supplied-but-unresolvable token no longer hard-fails: the request falls
    // through to the token-less path, which requires a verified membership.
    db.tokenRow = null;
    membersStore.members = [];
    const res = await POST(makeReq({ branchToken: 'tok', studentId: 'stu-1' }) as never);
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: 'no_membership' });
    expect(upsertSpy).not.toHaveBeenCalled();
  });

  it('409 when the student is already linked', async () => {
    db.existingMember = { id: 'm-1' };
    const res = await POST(makeReq({ branchToken: 'tok', studentId: 'stu-1' }) as never);
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: 'ALREADY_REGISTERED' });
    expect(upsertSpy).not.toHaveBeenCalled();
  });

  it('401 on branch mismatch', async () => {
    profileStore.branchId = 'branch-OTHER';
    const res = await POST(makeReq({ branchToken: 'tok', studentId: 'stu-1' }) as never);
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: 'branch_mismatch' });
  });

  it('401 when the student is inactive', async () => {
    profileStore.status = 'frozen';
    const res = await POST(makeReq({ branchToken: 'tok', studentId: 'stu-1' }) as never);
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: 'inactive' });
  });

  it('404 when the student is not found in Chess Empire', async () => {
    profileStore.throwStatus = 404;
    const res = await POST(makeReq({ branchToken: 'tok', studentId: 'stu-1' }) as never);
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: 'not_found' });
  });

  it('links instantly with relationship=child on the happy path', async () => {
    const res = await POST(makeReq({ branchToken: 'tok', studentId: 'stu-1' }) as never);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      ok: true,
      studentId: 'stu-1',
      relationship: 'child',
    });
    expect(upsertSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        orgId: 'org-1',
        clerkUserId: 'parent-1',
        studentId: 'stu-1',
        linkStatus: 'verified',
        relationship: 'child',
        externalSource: 'chess_empire',
        name: 'Aruzhan A',
      }),
    );
  });

  it('honours relationship=other', async () => {
    const res = await POST(
      makeReq({ branchToken: 'tok', studentId: 'stu-1', relationship: 'other' }) as never,
    );
    expect(res.status).toBe(200);
    expect(upsertSpy).toHaveBeenCalledWith(
      expect.objectContaining({ relationship: 'other' }),
    );
  });

  describe('token-less path (branch + org derived from caller membership)', () => {
    it('links a same-branch active student with NO branch token supplied', async () => {
      // Caller (stu-self) and target (stu-1) both in branch-1 → link succeeds
      // using the caller's OWN org, no branch token in the request.
      profileStore.branchById = { 'stu-self': 'branch-1', 'stu-1': 'branch-1' };
      const res = await POST(makeReq({ studentId: 'stu-1' }) as never);
      expect(res.status).toBe(200);
      expect(await res.json()).toEqual({
        ok: true,
        studentId: 'stu-1',
        relationship: 'child',
      });
      expect(upsertSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          orgId: 'org-1',
          clerkUserId: 'parent-1',
          studentId: 'stu-1',
          linkStatus: 'verified',
          externalSource: 'chess_empire',
        }),
      );
    });

    it('rejects branch_mismatch for a student in a different branch', async () => {
      // Caller in branch-1, target in branch-2 → cross-branch link refused.
      profileStore.branchById = { 'stu-self': 'branch-1', 'stu-1': 'branch-2' };
      const res = await POST(makeReq({ studentId: 'stu-1' }) as never);
      expect(res.status).toBe(401);
      expect(await res.json()).toEqual({ error: 'branch_mismatch' });
      expect(upsertSpy).not.toHaveBeenCalled();
    });

    it('rejects with no_membership when the caller has no verified membership', async () => {
      membersStore.members = [];
      const res = await POST(makeReq({ studentId: 'stu-1' }) as never);
      expect(res.status).toBe(401);
      expect(await res.json()).toEqual({ error: 'no_membership' });
      expect(upsertSpy).not.toHaveBeenCalled();
    });
  });
});
