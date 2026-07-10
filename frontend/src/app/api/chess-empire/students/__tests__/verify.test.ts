/**
 * Tests for /api/chess-empire/students/verify.
 *
 * Covers: missing fields (400), invalid token (401), already-registered
 * (409), branch mismatch (401), inactive (401), success (JWT returned,
 * JWT verifies), rate-limit (429).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const scripts: Record<string, ScriptedResponse[]> = {};
const inserted: Array<{ table: string; payload: unknown }> = [];

function nextScript(table: string, op: string): ScriptedResponse {
  const queue = scripts[`${table}.${op}`];
  if (!queue || queue.length === 0) return { data: null, error: null };
  return queue.shift() as ScriptedResponse;
}

function makeBuilder(table: string) {
  const rec = { table, op: 'select', filters: [] as Array<[string, unknown]> };
  const finalize = (op: string) => {
    rec.op = op;
    return Promise.resolve(nextScript(table, op));
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
    insert(payload: unknown) {
      inserted.push({ table, payload });
      return Promise.resolve(nextScript(table, 'insert'));
    },
    then(onFulfilled: (v: ScriptedResponse) => unknown) {
      return finalize('select').then(onFulfilled);
    },
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => makeBuilder(table),
  },
}));

vi.mock('@/lib/chess-empire-client', () => ({
  getStudentProfile: vi.fn(),
  getCoachProfile: vi.fn(),
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

vi.mock('@/lib/in-memory-rate-limit', () => {
  const fn = vi
    .fn()
    .mockReturnValue({ allowed: true, remaining: 99, retryAfterSeconds: 0 });
  return { rateLimit: fn };
});

import { POST } from '../verify/route';
import { getStudentProfile, getCoachProfile } from '@/lib/chess-empire-client';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { verifyInviteJwt } from '@/lib/invite-jwt';
import { NextRequest } from 'next/server';

const ceProfile = getStudentProfile as unknown as ReturnType<typeof vi.fn>;
const ceCoachProfile = getCoachProfile as unknown as ReturnType<typeof vi.fn>;
const rl = rateLimit as unknown as ReturnType<typeof vi.fn>;

const VALID_TOKEN = {
  id: 'token-1',
  organization_id: 'org-1',
  external_branch_id: 'br-1',
  branch_name: 'Debut',
  expires_at: null,
  revoked_at: null,
};

function makeReq(body: unknown): NextRequest {
  return new NextRequest('http://x/api/chess-empire/students/verify', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  inserted.length = 0;
  ceProfile.mockReset();
  ceCoachProfile.mockReset();
  rl.mockReturnValue({ allowed: true, remaining: 99, retryAfterSeconds: 0 });
  process.env.INVITE_JWT_SECRET = 'unit-test-secret';
});

describe('POST /api/chess-empire/students/verify', () => {
  it('400 on missing fields', async () => {
    const res = await POST(makeReq({}));
    expect(res.status).toBe(400);
  });

  it('401 on invalid token', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: null, error: null }];
    const res = await POST(
      makeReq({ branchToken: 'bad', studentId: 's' }),
    );
    expect(res.status).toBe(401);
  });

  it('409 when already registered', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    scripts['organization_members.maybeSingle'] = [
      { data: { id: 'mem-1' }, error: null },
    ];
    scripts['student_verify_attempts.insert'] = [{ data: null, error: null }];
    const res = await POST(
      makeReq({ branchToken: 't', studentId: 'stu-1' }),
    );
    expect(res.status).toBe(409);
    const body = await res.json();
    expect(body.error).toBe('ALREADY_REGISTERED');
    expect(
      inserted.find((i) => i.table === 'student_verify_attempts'),
    ).toBeTruthy();
  });

  it('401 on branch mismatch', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    scripts['organization_members.maybeSingle'] = [{ data: null, error: null }];
    ceProfile.mockResolvedValue({
      id: 'stu-1',
      first_name: 'A',
      last_name: 'B',
      branch_id: 'br-OTHER',
      status: 'active',
      date_of_birth: '2014-06-15',
    });
    const res = await POST(
      makeReq({ branchToken: 't', studentId: 'stu-1' }),
    );
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toBe('branch_mismatch');
  });

  it('401 when student inactive', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    scripts['organization_members.maybeSingle'] = [{ data: null, error: null }];
    ceProfile.mockResolvedValue({
      id: 'stu-1',
      first_name: 'A',
      last_name: 'B',
      branch_id: 'br-1',
      status: 'frozen',
      date_of_birth: '2014-06-15',
    });
    const res = await POST(
      makeReq({ branchToken: 't', studentId: 'stu-1' }),
    );
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toBe('inactive');
  });

  it('returns a verifiable JWT on success', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    scripts['organization_members.maybeSingle'] = [{ data: null, error: null }];
    ceProfile.mockResolvedValue({
      id: 'stu-1',
      first_name: 'A',
      last_name: 'B',
      branch_id: 'br-1',
      status: 'active',
      date_of_birth: '2014-06-15',
    });
    const res = await POST(
      makeReq({ branchToken: 't', studentId: 'stu-1' }),
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(typeof body.inviteJwt).toBe('string');
    const claims = verifyInviteJwt(body.inviteJwt);
    expect(claims.student_id).toBe('stu-1');
    expect(claims.branch_id).toBe('br-1');
    expect(claims.org_id).toBe('org-1');
    expect(claims.branch_token_id).toBe('token-1');
    const attempt = inserted.find((i) => i.table === 'student_verify_attempts');
    expect((attempt!.payload as { success: boolean }).success).toBe(true);
  });

  it('429 when rate-limit triggers', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    rl.mockReturnValueOnce({ allowed: false, remaining: 0, retryAfterSeconds: 3600 });
    const res = await POST(
      makeReq({ branchToken: 't', studentId: 'stu-1' }),
    );
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBe('3600');
  });

  it('coach happy path: uses getCoachProfile, skips status, signs member_type=coach JWT', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    scripts['organization_members.maybeSingle'] = [{ data: null, error: null }];
    ceCoachProfile.mockResolvedValue({
      id: 'co-1',
      first_name: 'Anna',
      last_name: 'Petrova',
      branch_id: 'br-1',
      email: 'anna@example.com',
    });
    const res = await POST(
      makeReq({ branchToken: 't', studentId: 'co-1', type: 'coach' }),
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    const claims = verifyInviteJwt(body.inviteJwt);
    expect(claims.student_id).toBe('co-1');
    expect(claims.member_type).toBe('coach');
    // The student-profile path must not run for coaches.
    expect(ceProfile).not.toHaveBeenCalled();
    expect(ceCoachProfile).toHaveBeenCalledWith('co-1');
    const attempt = inserted.find((i) => i.table === 'student_verify_attempts');
    expect((attempt!.payload as { success: boolean }).success).toBe(true);
  });

  it('coach branch mismatch → 401', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    scripts['organization_members.maybeSingle'] = [{ data: null, error: null }];
    ceCoachProfile.mockResolvedValue({
      id: 'co-1',
      first_name: 'Anna',
      last_name: 'Petrova',
      branch_id: 'br-OTHER',
      email: null,
    });
    const res = await POST(
      makeReq({ branchToken: 't', studentId: 'co-1', type: 'coach' }),
    );
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toBe('branch_mismatch');
  });

  it('coach duplicate link → 409', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    scripts['organization_members.maybeSingle'] = [
      { data: { id: 'mem-1' }, error: null },
    ];
    scripts['student_verify_attempts.insert'] = [{ data: null, error: null }];
    const res = await POST(
      makeReq({ branchToken: 't', studentId: 'co-1', type: 'coach' }),
    );
    expect(res.status).toBe(409);
    const body = await res.json();
    expect(body.error).toBe('ALREADY_REGISTERED');
    // Duplicate is caught before we ever hit the CE API.
    expect(ceCoachProfile).not.toHaveBeenCalled();
  });
});
