/**
 * Tests for the member-lookup helpers. Mocks `@supabase/supabase-js` so we can
 * record the filter chain and inject the (multi-)row responses. The helpers now
 * fetch ALL of a user's rows (family multi-link) and pick a deterministic
 * primary for the single-row helpers; `getVerifiedMembersForUser` returns the
 * full verified allowlist.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

interface RowsResponse {
  data: Array<Record<string, unknown>> | null;
  error: { message: string } | null;
}

type Recorded = {
  eq: Array<[string, unknown]>;
  in: Array<[string, unknown]>;
  order: Array<[string, unknown]>;
  table: string | null;
  select: string | null;
};

const recorded: Recorded = {
  eq: [],
  in: [],
  order: [],
  table: null,
  select: null,
};
let nextResponse: RowsResponse = { data: null, error: null };

vi.mock('@supabase/supabase-js', () => {
  // The builder is a thenable so `await query.order(...)` resolves the scripted
  // rows response — matching the fetch-all query shape (no .maybeSingle()).
  const builder = {
    select(columns: string) {
      recorded.select = columns;
      return builder;
    },
    eq(column: string, value: unknown) {
      recorded.eq.push([column, value]);
      return builder;
    },
    in(column: string, value: unknown) {
      recorded.in.push([column, value]);
      return builder;
    },
    order(column: string, opts: unknown) {
      recorded.order.push([column, opts]);
      return builder;
    },
    then<T>(resolve: (v: RowsResponse) => T) {
      return Promise.resolve(nextResponse).then(resolve);
    },
  };
  return {
    createClient: vi.fn(() => ({
      from(table: string) {
        recorded.table = table;
        return builder;
      },
    })),
  };
});

import {
  getLinkedStudentId,
  getMembershipState,
  getMembershipStateForUser,
  getVerifiedMembersForUser,
} from '../chess-empire-member';

/** Build a member row with sensible defaults. */
function row(overrides: Record<string, unknown> = {}) {
  return {
    id: 'mem-1',
    external_student_id: 'stu-1',
    link_status: 'verified',
    role: 'student',
    external_source: 'chess_empire',
    access_expires_at: null,
    relationship: 'self',
    organization_id: 'org-1',
    ...overrides,
  };
}

beforeEach(() => {
  recorded.eq = [];
  recorded.in = [];
  recorded.order = [];
  recorded.table = null;
  recorded.select = null;
  nextResponse = { data: null, error: null };
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://chesster.example.com';
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'srv-key';
});
afterEach(() => {
  delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  delete process.env.SUPABASE_SERVICE_ROLE_KEY;
});

describe('getLinkedStudentId', () => {
  it('returns the external_student_id when the verified row exists', async () => {
    nextResponse = {
      data: [row({ id: 'mem-1', external_student_id: 'stu-1' })],
      error: null,
    };
    const id = await getLinkedStudentId({ orgId: 'org-1', clerkUserId: 'user-1' });
    expect(id).toBe('stu-1');
    expect(recorded.table).toBe('organization_members');
    const eqMap = Object.fromEntries(recorded.eq);
    expect(eqMap.organization_id).toBe('org-1');
    expect(eqMap.user_id).toBe('user-1');
    // Both onboarding tracks (branch + online) are matched via an IN filter.
    const inMap = Object.fromEntries(recorded.in);
    expect(inMap.external_source).toEqual(['chess_empire', 'online']);
    // Ordered deterministically by id (no created_at column on the table).
    expect(recorded.order[0][0]).toBe('id');
    // relationship is selected so family links can be labelled.
    expect(recorded.select).toContain('relationship');
    // organization_id is selected so the in-app link flow can scope by the
    // caller's OWN org without a public token.
    expect(recorded.select).toContain('organization_id');
  });

  it('returns null when no row matches', async () => {
    nextResponse = { data: [], error: null };
    const id = await getLinkedStudentId({
      orgId: 'org-1',
      clerkUserId: 'user-unknown',
    });
    expect(id).toBeNull();
  });

  it('returns null for pending_confirm rows (verified-only wrapper)', async () => {
    nextResponse = {
      data: [row({ id: 'mem-2', external_student_id: 'stu-2', link_status: 'pending_confirm' })],
      error: null,
    };
    const id = await getLinkedStudentId({
      orgId: 'org-1',
      clerkUserId: 'user-pending',
    });
    expect(id).toBeNull();
  });

  it('returns null for frozen rows', async () => {
    nextResponse = {
      data: [row({ id: 'mem-3', external_student_id: 'stu-3', link_status: 'frozen' })],
      error: null,
    };
    const id = await getLinkedStudentId({
      orgId: 'org-1',
      clerkUserId: 'user-frozen',
    });
    expect(id).toBeNull();
  });

  it('scopes the lookup to the chess_empire + online tracks only', async () => {
    nextResponse = { data: [], error: null };
    await getLinkedStudentId({ orgId: 'org-1', clerkUserId: 'user-1' });
    const inMap = Object.fromEntries(recorded.in);
    expect(inMap.external_source).toEqual(['chess_empire', 'online']);
  });

  it('throws on Supabase error', async () => {
    nextResponse = { data: null, error: { message: 'boom' } };
    await expect(
      getLinkedStudentId({ orgId: 'org-1', clerkUserId: 'user-1' }),
    ).rejects.toThrow(/boom/);
  });

  it('returns null when orgId or userId is missing', async () => {
    expect(await getLinkedStudentId({ orgId: '', clerkUserId: 'u' })).toBeNull();
    expect(await getLinkedStudentId({ orgId: 'o', clerkUserId: '' })).toBeNull();
  });
});

describe('getMembershipState', () => {
  it('returns state=verified with studentId when link_status=verified', async () => {
    nextResponse = {
      data: [row({ id: 'mem-v', external_student_id: 'stu-v' })],
      error: null,
    };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'user-v',
    });
    expect(result.state).toBe('verified');
    expect(result.studentId).toBe('stu-v');
    expect(result.memberId).toBe('mem-v');
    expect(result.relationship).toBe('self');
    expect(result.orgId).toBe('org-1');
  });

  it('exposes orgId from the row, and null when there is no row', async () => {
    nextResponse = {
      data: [row({ id: 'mem-o', external_student_id: 'stu-o', organization_id: 'org-77' })],
      error: null,
    };
    const linked = await getMembershipState({ orgId: 'org-77', clerkUserId: 'user-o' });
    expect(linked.orgId).toBe('org-77');

    nextResponse = { data: [], error: null };
    const none = await getMembershipState({ orgId: 'org-1', clerkUserId: 'nobody' });
    expect(none.orgId).toBeNull();
  });

  it('returns state=pending_confirm with studentId when link_status=pending_confirm', async () => {
    nextResponse = {
      data: [row({ id: 'mem-p', external_student_id: 'stu-p', link_status: 'pending_confirm' })],
      error: null,
    };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'user-p',
    });
    expect(result.state).toBe('pending_confirm');
    expect(result.studentId).toBe('stu-p');
    expect(result.memberId).toBe('mem-p');
  });

  it('returns state=no_link when the row is absent', async () => {
    nextResponse = { data: [], error: null };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'nobody',
    });
    expect(result.state).toBe('no_link');
    expect(result.studentId).toBeNull();
    expect(result.memberId).toBeNull();
  });

  it('returns state=frozen (with member fields) when link_status is frozen', async () => {
    nextResponse = {
      data: [
        row({
          id: 'mem-f',
          external_student_id: 'stu-f',
          link_status: 'frozen',
          relationship: 'child',
        }),
      ],
      error: null,
    };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'user-f',
    });
    // Distinct from no_link: keeps the member/name fields so the UI can greet.
    expect(result.state).toBe('frozen');
    expect(result.studentId).toBe('stu-f');
    expect(result.memberId).toBe('mem-f');
    expect(result.relationship).toBe('child');
    expect(result.orgId).toBe('org-1');
  });

  it('returns state=no_link when link_status is revoked (access removed)', async () => {
    nextResponse = {
      data: [row({ id: 'mem-r', external_student_id: 'stu-r', link_status: 'revoked' })],
      error: null,
    };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'user-r',
    });
    expect(result.state).toBe('no_link');
    expect(result.studentId).toBeNull();
  });

  it('returns state=no_link when external_student_id is null (placeholder row)', async () => {
    nextResponse = {
      data: [row({ id: 'mem-placeholder', external_student_id: null, link_status: 'pending' })],
      error: null,
    };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'user-p',
    });
    expect(result.state).toBe('no_link');
  });

  it('returns state=no_link when orgId or userId missing', async () => {
    const a = await getMembershipState({ orgId: '', clerkUserId: 'u' });
    const b = await getMembershipState({ orgId: 'o', clerkUserId: '' });
    expect(a.state).toBe('no_link');
    expect(b.state).toBe('no_link');
  });

  describe('access expiry (online invites)', () => {
    it('null access_expires_at never expires → verified', async () => {
      nextResponse = {
        data: [
          row({
            id: 'mem-online-1',
            external_student_id: 'stu-online-1',
            external_source: 'online',
            access_expires_at: null,
          }),
        ],
        error: null,
      };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-online-1',
      });
      expect(result.state).toBe('verified');
      expect(result.source).toBe('online');
      expect(result.studentId).toBe('stu-online-1');
    });

    it('future access_expires_at is still active → verified', async () => {
      const oneHourAhead = new Date(Date.now() + 60 * 60 * 1000).toISOString();
      nextResponse = {
        data: [
          row({
            id: 'mem-online-2',
            external_student_id: 'stu-online-2',
            external_source: 'online',
            access_expires_at: oneHourAhead,
          }),
        ],
        error: null,
      };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-online-2',
      });
      expect(result.state).toBe('verified');
      expect(result.source).toBe('online');
    });

    it('past access_expires_at → expired (studentId preserved, not surfaced as verified)', async () => {
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
      nextResponse = {
        data: [
          row({
            id: 'mem-online-3',
            external_student_id: 'stu-online-3',
            external_source: 'online',
            access_expires_at: oneHourAgo,
          }),
        ],
        error: null,
      };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-online-3',
      });
      expect(result.state).toBe('expired');
      expect(result.source).toBe('online');
      expect(result.memberId).toBe('mem-online-3');
    });

    it('branch members (chess_empire, null expiry) are untouched → verified', async () => {
      nextResponse = {
        data: [
          row({
            id: 'mem-branch',
            external_student_id: 'stu-branch',
            external_source: 'chess_empire',
            access_expires_at: null,
          }),
        ],
        error: null,
      };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-branch',
      });
      expect(result.state).toBe('verified');
      expect(result.source).toBe('chess_empire');
    });

    it('getLinkedStudentId returns null for an expired member (never verified)', async () => {
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
      nextResponse = {
        data: [
          row({
            id: 'mem-online-4',
            external_student_id: 'stu-online-4',
            external_source: 'online',
            access_expires_at: oneHourAgo,
          }),
        ],
        error: null,
      };
      const id = await getLinkedStudentId({
        orgId: 'org-1',
        clerkUserId: 'user-online-4',
      });
      expect(id).toBeNull();
    });
  });

  describe('relationship coercion', () => {
    it("missing relationship column value → 'self'", async () => {
      // No `relationship` key at all (pre-migration row).
      const { relationship: _omit, ...noRel } = row({ id: 'mem-norel' });
      void _omit;
      nextResponse = { data: [noRel], error: null };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-norel',
      });
      expect(result.relationship).toBe('self');
    });

    it("null relationship → 'self'", async () => {
      nextResponse = { data: [row({ relationship: null })], error: null };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-nullrel',
      });
      expect(result.relationship).toBe('self');
    });

    it("unknown relationship value coerces to 'other'", async () => {
      nextResponse = { data: [row({ relationship: 'cousin' })], error: null };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-weird',
      });
      expect(result.relationship).toBe('other');
    });

    it("known 'child' relationship passes through", async () => {
      nextResponse = { data: [row({ relationship: 'child' })], error: null };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-child',
      });
      expect(result.relationship).toBe('child');
    });
  });

  describe('deterministic primary among multiple rows', () => {
    it('a verified row wins over an earlier pending_confirm row', async () => {
      nextResponse = {
        data: [
          row({ id: 'mem-a', external_student_id: 'stu-a', link_status: 'pending_confirm', relationship: 'child' }),
          row({ id: 'mem-b', external_student_id: 'stu-b', link_status: 'verified', relationship: 'child' }),
        ],
        error: null,
      };
      const result = await getMembershipState({
        orgId: 'org-1',
        clerkUserId: 'user-mix',
      });
      expect(result.state).toBe('verified');
      expect(result.studentId).toBe('stu-b');
    });

    it("among verified rows, relationship='self' wins over an earlier child", async () => {
      nextResponse = {
        data: [
          row({ id: 'mem-a', external_student_id: 'stu-child', relationship: 'child' }),
          row({ id: 'mem-b', external_student_id: 'stu-self', relationship: 'self' }),
        ],
        error: null,
      };
      const result = await getMembershipStateForUser('user-family');
      expect(result.state).toBe('verified');
      expect(result.studentId).toBe('stu-self');
      expect(result.relationship).toBe('self');
    });

    it('with no self, the earliest verified row wins', async () => {
      nextResponse = {
        data: [
          row({ id: 'mem-a', external_student_id: 'stu-first', relationship: 'child' }),
          row({ id: 'mem-b', external_student_id: 'stu-second', relationship: 'other' }),
        ],
        error: null,
      };
      const result = await getMembershipStateForUser('user-nokids');
      expect(result.studentId).toBe('stu-first');
    });

    it('a lone frozen row resolves to frozen, never no_link', async () => {
      nextResponse = {
        data: [
          row({ id: 'mem-f', external_student_id: 'stu-f', link_status: 'frozen' }),
        ],
        error: null,
      };
      const result = await getMembershipStateForUser('user-frozen-only');
      expect(result.state).toBe('frozen');
      expect(result.studentId).toBe('stu-f');
    });

    it('a verified row wins over a frozen row', async () => {
      nextResponse = {
        data: [
          row({ id: 'mem-a', external_student_id: 'stu-frozen', link_status: 'frozen', relationship: 'child' }),
          row({ id: 'mem-b', external_student_id: 'stu-live', link_status: 'verified', relationship: 'child' }),
        ],
        error: null,
      };
      const result = await getMembershipStateForUser('user-frozen-plus-verified');
      expect(result.state).toBe('verified');
      expect(result.studentId).toBe('stu-live');
    });

    it('pending_confirm wins over a frozen row', async () => {
      nextResponse = {
        data: [
          row({ id: 'mem-a', external_student_id: 'stu-frozen', link_status: 'frozen' }),
          row({ id: 'mem-b', external_student_id: 'stu-pending', link_status: 'pending_confirm' }),
        ],
        error: null,
      };
      const result = await getMembershipStateForUser('user-frozen-plus-pending');
      expect(result.state).toBe('pending_confirm');
      expect(result.studentId).toBe('stu-pending');
    });

    it('a frozen row wins over an earlier revoked (no_link) row', async () => {
      nextResponse = {
        data: [
          row({ id: 'mem-a', external_student_id: 'stu-revoked', link_status: 'revoked' }),
          row({ id: 'mem-b', external_student_id: 'stu-frozen', link_status: 'frozen' }),
        ],
        error: null,
      };
      const result = await getMembershipStateForUser('user-revoked-plus-frozen');
      expect(result.state).toBe('frozen');
      expect(result.studentId).toBe('stu-frozen');
    });
  });
});

describe('getVerifiedMembersForUser', () => {
  it('returns [] when the user has no rows', async () => {
    nextResponse = { data: [], error: null };
    expect(await getVerifiedMembersForUser('nobody')).toEqual([]);
  });

  it('returns [] for a falsy user id without querying', async () => {
    nextResponse = { data: [row()], error: null };
    expect(await getVerifiedMembersForUser('')).toEqual([]);
    expect(recorded.table).toBeNull();
  });

  it('returns the single verified member', async () => {
    nextResponse = {
      data: [row({ id: 'mem-1', external_student_id: 'stu-1' })],
      error: null,
    };
    const members = await getVerifiedMembersForUser('user-1');
    expect(members).toHaveLength(1);
    expect(members[0].studentId).toBe('stu-1');
    expect(members[0].state).toBe('verified');
  });

  it('returns all verified members for a family account', async () => {
    nextResponse = {
      data: [
        row({ id: 'mem-1', external_student_id: 'stu-self', relationship: 'self' }),
        row({ id: 'mem-2', external_student_id: 'stu-kid1', relationship: 'child' }),
        row({ id: 'mem-3', external_student_id: 'stu-kid2', relationship: 'child' }),
      ],
      error: null,
    };
    const members = await getVerifiedMembersForUser('user-family');
    expect(members.map((m) => m.studentId)).toEqual([
      'stu-self',
      'stu-kid1',
      'stu-kid2',
    ]);
  });

  it('filters out pending_confirm rows, keeping only verified', async () => {
    nextResponse = {
      data: [
        row({ id: 'mem-1', external_student_id: 'stu-ok', link_status: 'verified' }),
        row({ id: 'mem-2', external_student_id: 'stu-pending', link_status: 'pending_confirm' }),
      ],
      error: null,
    };
    const members = await getVerifiedMembersForUser('user-mix');
    expect(members.map((m) => m.studentId)).toEqual(['stu-ok']);
  });

  it('filters out an expired verified row', async () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    nextResponse = {
      data: [
        row({ id: 'mem-1', external_student_id: 'stu-live', external_source: 'chess_empire' }),
        row({
          id: 'mem-2',
          external_student_id: 'stu-expired',
          external_source: 'online',
          access_expires_at: oneHourAgo,
        }),
      ],
      error: null,
    };
    const members = await getVerifiedMembersForUser('user-exp');
    expect(members.map((m) => m.studentId)).toEqual(['stu-live']);
  });

  it('throws on Supabase error', async () => {
    nextResponse = { data: null, error: { message: 'kaboom' } };
    await expect(getVerifiedMembersForUser('user-1')).rejects.toThrow(/kaboom/);
  });
});
