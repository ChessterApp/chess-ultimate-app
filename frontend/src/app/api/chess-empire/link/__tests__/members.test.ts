/**
 * Tests for GET /api/chess-empire/link/members.
 *
 * Covers: unauthenticated (401), verified members mapped with name +
 * relationship + status, empty family, server-side branch-token resolution
 * (revoked/expired/online filtered, newest wins), and a lookup error (500).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

interface MemberState {
  state: string;
  studentId: string | null;
  relationship: 'self' | 'child' | 'other';
}
const memberStore: { members: MemberState[]; throws: boolean } = {
  members: [],
  throws: false,
};
vi.mock('@/lib/chess-empire-member', () => ({
  getVerifiedMembersForUser: vi.fn(async () => {
    if (memberStore.throws) throw new Error('boom');
    return memberStore.members;
  }),
}));

const nameStore: Record<string, string | null> = {};
const branchStore: Record<string, string | null> = {};
vi.mock('@/lib/chess-empire-client', () => ({
  getStudentDisplayName: vi.fn(async (id: string) => nameStore[id] ?? null),
  getStudentBranches: vi.fn(
    async (ids: string[]) => new Map(ids.map((id) => [id, branchStore[id] ?? null])),
  ),
}));

interface TokenRow {
  token: string;
  kind: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
}
const tokenStore: { rows: TokenRow[]; error: unknown } = { rows: [], error: null };
vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: () => {
      const chain = {
        select: () => chain,
        eq: () => chain,
        then: (
          onFulfilled: (v: { data: unknown; error: unknown }) => unknown,
          onRejected?: (e: unknown) => unknown,
        ) =>
          Promise.resolve({ data: tokenStore.rows, error: tokenStore.error }).then(
            onFulfilled,
            onRejected,
          ),
      };
      return chain;
    },
  },
}));

import { GET } from '../members/route';

beforeEach(() => {
  authStore.userId = 'user-1';
  memberStore.members = [];
  memberStore.throws = false;
  for (const k of Object.keys(nameStore)) delete nameStore[k];
  for (const k of Object.keys(branchStore)) delete branchStore[k];
  tokenStore.rows = [];
  tokenStore.error = null;
});

describe('GET /api/chess-empire/link/members', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it('returns an empty family with no branch token', async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ members: [], branchToken: null });
  });

  it('maps verified members with name, relationship and status', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self' },
      { state: 'verified', studentId: 'stu-kid', relationship: 'child' },
    ];
    nameStore['stu-self'] = 'Alex Parent';
    nameStore['stu-kid'] = 'Aruzhan Kid';
    branchStore['stu-self'] = 'branch-1';
    tokenStore.rows = [
      {
        token: 'tok-new',
        kind: 'branch',
        expires_at: null,
        revoked_at: null,
        created_at: '2026-02-01',
      },
    ];

    const res = await GET();
    const body = await res.json();
    expect(body.members).toEqual([
      { studentId: 'stu-self', name: 'Alex Parent', relationship: 'self', status: 'verified' },
      { studentId: 'stu-kid', name: 'Aruzhan Kid', relationship: 'child', status: 'verified' },
    ]);
    // Branch resolved from the primary (self) member.
    expect(body.branchToken).toBe('tok-new');
  });

  it('resolves the newest active branch token, ignoring revoked/expired/online', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-kid', relationship: 'child' },
    ];
    branchStore['stu-kid'] = 'branch-9';
    tokenStore.rows = [
      { token: 'tok-old', kind: 'branch', expires_at: null, revoked_at: null, created_at: '2026-01-01' },
      { token: 'tok-revoked', kind: 'branch', expires_at: null, revoked_at: '2026-02-01', created_at: '2026-03-01' },
      { token: 'tok-expired', kind: 'branch', expires_at: '2000-01-01', revoked_at: null, created_at: '2026-03-02' },
      { token: 'tok-online', kind: 'online', expires_at: null, revoked_at: null, created_at: '2026-03-03' },
      { token: 'tok-newest', kind: 'branch', expires_at: null, revoked_at: null, created_at: '2026-02-15' },
    ];

    const res = await GET();
    const body = await res.json();
    // No 'self' row → primary is the first verified member (the child).
    expect(body.branchToken).toBe('tok-newest');
  });

  it('returns null branch token when the student has no resolvable branch', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-kid', relationship: 'child' },
    ];
    // branchStore has no entry → branch id null → no token.
    const res = await GET();
    expect((await res.json()).branchToken).toBeNull();
  });

  it('500 when the membership lookup throws', async () => {
    memberStore.throws = true;
    const res = await GET();
    expect(res.status).toBe(500);
  });
});
