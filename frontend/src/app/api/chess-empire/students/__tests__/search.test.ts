/**
 * Tests for /api/chess-empire/students/search.
 *
 * Mocks the Supabase admin client (table-driven), the CE client, and the
 * rate limiter. Validates: invalid/revoked tokens 401, empty q short-
 * circuits, valid q returns filtered + last-name-redacted rows, already-
 * linked + inactive students stripped.
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

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => makeBuilder(table),
  },
}));

vi.mock('@/lib/chess-empire-client', () => ({
  searchStudentsByBranch: vi.fn(),
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
import { searchStudentsByBranch } from '@/lib/chess-empire-client';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { NextRequest } from 'next/server';

const ceSearch = searchStudentsByBranch as unknown as ReturnType<typeof vi.fn>;
const rl = rateLimit as unknown as ReturnType<typeof vi.fn>;

function makeReq(url: string): NextRequest {
  return new NextRequest(url);
}

const VALID_TOKEN = {
  id: 'token-1',
  organization_id: 'org-1',
  external_branch_id: 'br-1',
  branch_name: 'Debut',
  expires_at: null,
  revoked_at: null,
};

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  recorded.length = 0;
  ceSearch.mockReset();
  rl.mockReturnValue({ allowed: true, remaining: 99, retryAfterSeconds: 0 });
});

describe('GET /api/chess-empire/students/search', () => {
  it('400 when branchToken missing', async () => {
    const res = await GET(makeReq('http://x/api/?q=ali'));
    expect(res.status).toBe(400);
  });

  it('401 when token not found', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: null, error: null }];
    const res = await GET(makeReq('http://x/api/?branchToken=zzz&q=ali'));
    expect(res.status).toBe(401);
  });

  it('401 when token revoked', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: { ...VALID_TOKEN, revoked_at: '2026-01-01T00:00:00Z' }, error: null },
    ];
    const res = await GET(makeReq('http://x/api/?branchToken=t&q=ali'));
    expect(res.status).toBe(401);
  });

  it('401 when token expired', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: { ...VALID_TOKEN, expires_at: '2020-01-01T00:00:00Z' }, error: null },
    ];
    const res = await GET(makeReq('http://x/api/?branchToken=t&q=ali'));
    expect(res.status).toBe(401);
  });

  it('returns empty when q is blank', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    const res = await GET(makeReq('http://x/api/?branchToken=t&q='));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.results).toEqual([]);
    expect(ceSearch).not.toHaveBeenCalled();
  });

  it('returns filtered results, redacting last name to initial', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    ceSearch.mockResolvedValue([
      { id: 'stu-1', first_name: 'Aiman', last_name: 'Kassymova', branch_id: 'br-1', status: 'active' },
      { id: 'stu-2', first_name: 'Aida', last_name: 'Bekova', branch_id: 'br-1', status: 'active' },
      // inactive should be filtered defensively
      { id: 'stu-3', first_name: 'Adi', last_name: 'Frozen', branch_id: 'br-1', status: 'frozen' },
    ]);
    // already-linked check returns stu-2 as linked
    scripts['organization_members.select'] = [
      { data: [{ external_student_id: 'stu-2' }], error: null },
    ];
    const res = await GET(makeReq('http://x/api/?branchToken=t&q=ai'));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.results).toEqual([
      {
        studentId: 'stu-1',
        firstName: 'Aiman',
        lastNameInitial: 'K',
        branchName: 'Debut',
        coachName: null,
      },
    ]);
    expect(ceSearch).toHaveBeenCalledWith('br-1', 'ai', 20);
  });

  it('429 when rate-limited', async () => {
    rl.mockReturnValueOnce({ allowed: false, remaining: 0, retryAfterSeconds: 42 });
    const res = await GET(makeReq('http://x/api/?branchToken=t&q=ai'));
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBe('42');
  });

  it('502 when CE API throws', async () => {
    const { ChessEmpireAPIError } = await import('@/lib/chess-empire-client');
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: VALID_TOKEN, error: null }];
    ceSearch.mockRejectedValue(new ChessEmpireAPIError(500, 'boom'));
    const res = await GET(makeReq('http://x/api/?branchToken=t&q=ai'));
    expect(res.status).toBe(502);
  });
});
