/**
 * Tests for GET /api/chess-empire/link/search — the authenticated,
 * branch-scoped member search that backs the profile avatar "Добавить члена
 * семьи" sub-view.
 *
 * The branch is derived from the caller's OWN verified membership (never a
 * request param), so these cover the security contract the spec requires:
 *   (a) returns only same-branch members,
 *   (b) rejects unauthenticated requests,
 *   (c) never leaks another branch's members — the CE search is only ever
 *       issued against the branch bound to the caller's membership.
 *
 * Mocks Clerk auth, the membership lib, the CE client, the Supabase admin
 * client (table-driven), and the rate limiter.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const scripts: Record<string, ScriptedResponse[]> = {};
const recorded: Array<{ table: string; filters: Array<[string, unknown]>; op: string }> = [];

function nextScript(table: string, op: string): ScriptedResponse {
  const queue = scripts[`${table}.${op}`];
  if (!queue || queue.length === 0) return { data: null, error: null };
  return queue.shift() as ScriptedResponse;
}

function makeBuilder(table: string) {
  const rec = { table, op: 'select', filters: [] as Array<[string, unknown]> };
  let pushed = false;
  const finalize = (op: string) => {
    rec.op = op;
    const r = nextScript(table, op);
    if (!pushed) {
      recorded.push(rec);
      pushed = true;
    }
    return Promise.resolve(r);
  };
  const chain: Record<string, unknown> = {
    select() {
      return chain;
    },
    eq(col: string, val: unknown) {
      rec.filters.push([col, val]);
      return chain;
    },
    in(col: string, val: unknown) {
      rec.filters.push([col, val]);
      return chain;
    },
    is(col: string, val: unknown) {
      rec.filters.push([col, val]);
      return chain;
    },
    maybeSingle() {
      return finalize('maybeSingle');
    },
    single() {
      return finalize('single');
    },
    then(onFulfilled: (v: ScriptedResponse) => unknown, onRejected?: (e: unknown) => unknown) {
      return finalize('select').then(onFulfilled, onRejected);
    },
  };
  return chain;
}

const authStore = { userId: null as string | null };
vi.mock('@clerk/nextjs/server', () => ({
  auth: () => Promise.resolve({ userId: authStore.userId }),
}));

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => makeBuilder(table),
  },
}));

vi.mock('@/lib/chess-empire-member', () => ({
  getVerifiedMembersForUser: vi.fn(),
}));

vi.mock('@/lib/chess-empire-client', () => ({
  getStudentProfile: vi.fn(),
  searchStudentsByBranch: vi.fn(),
  searchCoachesByBranch: vi.fn(),
  ChessEmpireAPIError: class extends Error {
    statusCode = 500;
    body: unknown = null;
    constructor(s: number, b: unknown) {
      super(`${s}`);
      this.statusCode = s;
      this.body = b;
    }
  },
}));

vi.mock('@/lib/in-memory-rate-limit', () => ({
  rateLimit: vi.fn().mockReturnValue({ allowed: true, remaining: 99, retryAfterSeconds: 0 }),
}));

import { GET } from '../search/route';
import { getVerifiedMembersForUser } from '@/lib/chess-empire-member';
import {
  getStudentProfile,
  searchStudentsByBranch,
  searchCoachesByBranch,
} from '@/lib/chess-empire-client';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { NextRequest } from 'next/server';

const members = getVerifiedMembersForUser as unknown as ReturnType<typeof vi.fn>;
const profile = getStudentProfile as unknown as ReturnType<typeof vi.fn>;
const ceSearch = searchStudentsByBranch as unknown as ReturnType<typeof vi.fn>;
const ceCoachSearch = searchCoachesByBranch as unknown as ReturnType<typeof vi.fn>;
const rl = rateLimit as unknown as ReturnType<typeof vi.fn>;

function makeReq(url: string): NextRequest {
  return new NextRequest(url);
}

const ACTIVE_TOKEN = {
  token: 'tok-1',
  organization_id: 'org-1',
  external_branch_id: 'br-1',
  kind: null,
  expires_at: null,
  revoked_at: null,
  created_at: '2026-01-01T00:00:00Z',
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
  for (const k of Object.keys(scripts)) delete scripts[k];
  recorded.length = 0;
  authStore.userId = 'user-1';
  members.mockReset();
  profile.mockReset();
  ceSearch.mockReset();
  ceCoachSearch.mockReset();
  ceSearch.mockResolvedValue([]);
  ceCoachSearch.mockResolvedValue([]);
  members.mockResolvedValue([SELF_MEMBER]);
  profile.mockResolvedValue({ branch_id: 'br-1', branch_name: 'Debut', status: 'active' });
  rl.mockReturnValue({ allowed: true, remaining: 99, retryAfterSeconds: 0 });
});

describe('GET /api/chess-empire/link/search', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await GET(makeReq('http://x/api/?q=ai'));
    expect(res.status).toBe(401);
    // No membership lookup or CE call is attempted for an anonymous caller.
    expect(members).not.toHaveBeenCalled();
    expect(ceSearch).not.toHaveBeenCalled();
  });

  it('429 when rate-limited', async () => {
    rl.mockReturnValueOnce({ allowed: false, remaining: 0, retryAfterSeconds: 30 });
    const res = await GET(makeReq('http://x/api/?q=ai'));
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBe('30');
  });

  it('empty results + branch chip when caller has no membership', async () => {
    members.mockResolvedValue([]);
    const res = await GET(makeReq('http://x/api/?q=ai'));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ results: [], branchName: null, branchToken: null });
    expect(ceSearch).not.toHaveBeenCalled();
  });

  it('returns branch chip + token but no results for a blank query', async () => {
    scripts['branch_invite_tokens.select'] = [{ data: [ACTIVE_TOKEN], error: null }];
    const res = await GET(makeReq('http://x/api/?q='));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.results).toEqual([]);
    expect(body.branchName).toBe('Debut');
    expect(body.branchToken).toBe('tok-1');
    expect(ceSearch).not.toHaveBeenCalled();
  });

  it('returns only the caller-branch members and searches ONLY that branch', async () => {
    scripts['branch_invite_tokens.select'] = [{ data: [ACTIVE_TOKEN], error: null }];
    ceSearch.mockResolvedValue([
      { id: 'stu-1', first_name: 'Aiman', last_name: 'Kassymova', branch_id: 'br-1', status: 'active' },
      // defensive: an inactive row is dropped
      { id: 'stu-3', first_name: 'Adi', last_name: 'Frozen', branch_id: 'br-1', status: 'frozen' },
    ]);
    const res = await GET(makeReq('http://x/api/?q=ai'));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.results).toEqual([
      { studentId: 'stu-1', firstName: 'Aiman', lastName: 'Kassymova', branchName: 'Debut', type: 'student' },
    ]);
    expect(body.branchName).toBe('Debut');
    expect(body.branchToken).toBe('tok-1');
    // The branch is bound to the caller's own membership — the search is issued
    // against br-1 only, never any other branch (no cross-branch leak).
    expect(ceSearch).toHaveBeenCalledWith('br-1', 'ai', 20);
    expect(ceCoachSearch).toHaveBeenCalledWith('br-1', 'ai', 20);
  });

  it('binds the branch to the caller — a member in br-9 searches br-9, not a param', async () => {
    members.mockResolvedValue([{ ...SELF_MEMBER, studentId: 'stu-other' }]);
    profile.mockResolvedValue({ branch_id: 'br-9', branch_name: 'Endgame', status: 'active' });
    scripts['branch_invite_tokens.select'] = [
      { data: [{ ...ACTIVE_TOKEN, external_branch_id: 'br-9', organization_id: 'org-9' }], error: null },
    ];
    ceSearch.mockResolvedValue([
      { id: 's9', first_name: 'Bek', last_name: 'N', branch_id: 'br-9', status: 'active' },
    ]);
    // A stray branchToken/branch param in the URL must be ignored entirely.
    const res = await GET(makeReq('http://x/api/?q=be&branchToken=br-1&branch=br-1'));
    const body = await res.json();
    expect(body.branchName).toBe('Endgame');
    expect(ceSearch).toHaveBeenCalledWith('br-9', 'be', 20);
    expect(body.results).toEqual([
      { studentId: 's9', firstName: 'Bek', lastName: 'N', branchName: 'Endgame', type: 'student' },
    ]);
  });

  it('surfaces already-linked (foreign-owned) members with flags, not stripped', async () => {
    scripts['branch_invite_tokens.select'] = [{ data: [ACTIVE_TOKEN], error: null }];
    ceSearch.mockResolvedValue([
      { id: 'stu-linked', first_name: 'Alikhan', last_name: 'A', branch_id: 'br-1', status: 'active' },
      { id: 'stu-new', first_name: 'Aruzhan', last_name: 'A', branch_id: 'br-1', status: 'active' },
    ]);
    // Row owned by a DIFFERENT account → alreadyLinked but not ownedBySelf, so
    // the UI can still offer "Add to my family" (auto-accept edge).
    scripts['organization_members.select'] = [
      { data: [{ external_student_id: 'stu-linked', user_id: 'someone-else' }], error: null },
    ];
    const res = await GET(makeReq('http://x/api/?q=a'));
    const body = await res.json();
    expect(body.results).toEqual([
      {
        studentId: 'stu-linked',
        firstName: 'Alikhan',
        lastName: 'A',
        branchName: 'Debut',
        type: 'student',
        alreadyLinked: true,
        ownedBySelf: false,
      },
      { studentId: 'stu-new', firstName: 'Aruzhan', lastName: 'A', branchName: 'Debut', type: 'student' },
    ]);
  });

  it('flags a student the caller already owns as ownedBySelf', async () => {
    scripts['branch_invite_tokens.select'] = [{ data: [ACTIVE_TOKEN], error: null }];
    ceSearch.mockResolvedValue([
      { id: 'stu-mine', first_name: 'Aруз', last_name: 'A', branch_id: 'br-1', status: 'active' },
    ]);
    // Row owned by the caller (user-1) → ownedBySelf true (disabled add in UI).
    scripts['organization_members.select'] = [
      { data: [{ external_student_id: 'stu-mine', user_id: 'user-1' }], error: null },
    ];
    const res = await GET(makeReq('http://x/api/?q=a'));
    const body = await res.json();
    expect(body.results).toEqual([
      {
        studentId: 'stu-mine',
        firstName: 'Aруз',
        lastName: 'A',
        branchName: 'Debut',
        type: 'student',
        alreadyLinked: true,
        ownedBySelf: true,
      },
    ]);
  });

  it('merges same-branch coaches with type:coach', async () => {
    scripts['branch_invite_tokens.select'] = [{ data: [ACTIVE_TOKEN], error: null }];
    ceCoachSearch.mockResolvedValue([
      { id: 'co-1', first_name: 'Anna', last_name: 'Petrova', full_name: 'Anna Petrova', branch_id: 'br-1' },
    ]);
    const res = await GET(makeReq('http://x/api/?q=an'));
    const body = await res.json();
    expect(body.results).toEqual([
      { studentId: 'co-1', firstName: 'Anna', lastName: 'Petrova', branchName: 'Debut', type: 'coach' },
    ]);
  });

  it('still returns roster results when the branch has NO active token (token null)', async () => {
    // The caller is authenticated and their branch+org come from their own
    // verified membership, so a missing public token must NOT gate the search.
    scripts['branch_invite_tokens.select'] = [
      { data: [{ ...ACTIVE_TOKEN, revoked_at: '2026-02-01T00:00:00Z' }], error: null },
    ];
    ceSearch.mockResolvedValue([
      { id: 'stu-1', first_name: 'Aiman', last_name: 'Kassymova', branch_id: 'br-1', status: 'active' },
    ]);
    const res = await GET(makeReq('http://x/api/?q=ai'));
    const body = await res.json();
    expect(body.branchName).toBe('Debut');
    expect(body.branchToken).toBeNull();
    expect(body.results).toEqual([
      { studentId: 'stu-1', firstName: 'Aiman', lastName: 'Kassymova', branchName: 'Debut', type: 'student' },
    ]);
    // The search is still issued against the caller's own branch.
    expect(ceSearch).toHaveBeenCalledWith('br-1', 'ai', 20);
  });

  it('scopes the already-linked filter to the caller-derived org, not the token', async () => {
    // No token at all: the org used by fetchLinkedStudentIds must be the
    // caller's own membership org (org-1), never a token-derived org.
    scripts['branch_invite_tokens.select'] = [{ data: [], error: null }];
    ceSearch.mockResolvedValue([
      { id: 'stu-linked', first_name: 'Alikhan', last_name: 'A', branch_id: 'br-1', status: 'active' },
      { id: 'stu-new', first_name: 'Aruzhan', last_name: 'A', branch_id: 'br-1', status: 'active' },
    ]);
    scripts['organization_members.select'] = [
      { data: [{ external_student_id: 'stu-linked', user_id: 'someone-else' }], error: null },
    ];
    const res = await GET(makeReq('http://x/api/?q=a'));
    const body = await res.json();
    expect(body.branchToken).toBeNull();
    expect(body.results).toEqual([
      {
        studentId: 'stu-linked',
        firstName: 'Alikhan',
        lastName: 'A',
        branchName: 'Debut',
        type: 'student',
        alreadyLinked: true,
        ownedBySelf: false,
      },
      { studentId: 'stu-new', firstName: 'Aruzhan', lastName: 'A', branchName: 'Debut', type: 'student' },
    ]);
    const orgFilter = recorded.find((r) => r.table === 'organization_members');
    expect(orgFilter?.filters).toContainEqual(['organization_id', 'org-1']);
  });

  it('502 when the CE profile lookup errors', async () => {
    const { ChessEmpireAPIError } = await import('@/lib/chess-empire-client');
    profile.mockRejectedValue(new ChessEmpireAPIError(500, 'boom'));
    const res = await GET(makeReq('http://x/api/?q=ai'));
    expect(res.status).toBe(502);
  });
});
