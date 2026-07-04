/**
 * Tests for the Phase 3 member-lookup helper. Mocks `@supabase/supabase-js`
 * so we can record the filter chain and inject row / error responses.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

interface MaybeSingleResponse<T> {
  data: T | null;
  error: { message: string } | null;
}

type Recorded = {
  eq: Array<[string, unknown]>;
  table: string | null;
  select: string | null;
};

const recorded: Recorded = { eq: [], table: null, select: null };
let nextResponse: MaybeSingleResponse<unknown> = { data: null, error: null };

vi.mock('@supabase/supabase-js', () => {
  const builder = {
    select(columns: string) {
      recorded.select = columns;
      return builder;
    },
    eq(column: string, value: unknown) {
      recorded.eq.push([column, value]);
      return builder;
    },
    limit() {
      return builder;
    },
    maybeSingle() {
      return Promise.resolve(nextResponse);
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

import { getLinkedStudentId, getMembershipState } from '../chess-empire-member';

beforeEach(() => {
  recorded.eq = [];
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
      data: {
        id: 'mem-1',
        external_student_id: 'stu-1',
        link_status: 'verified',
      },
      error: null,
    };
    const id = await getLinkedStudentId({ orgId: 'org-1', clerkUserId: 'user-1' });
    expect(id).toBe('stu-1');
    expect(recorded.table).toBe('organization_members');
    const eqMap = Object.fromEntries(recorded.eq);
    expect(eqMap.organization_id).toBe('org-1');
    expect(eqMap.user_id).toBe('user-1');
    expect(eqMap.external_source).toBe('chess_empire');
  });

  it('returns null when no row matches', async () => {
    nextResponse = { data: null, error: null };
    const id = await getLinkedStudentId({
      orgId: 'org-1',
      clerkUserId: 'user-unknown',
    });
    expect(id).toBeNull();
  });

  it('returns null for pending_confirm rows (verified-only wrapper)', async () => {
    nextResponse = {
      data: {
        id: 'mem-2',
        external_student_id: 'stu-2',
        link_status: 'pending_confirm',
      },
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
      data: {
        id: 'mem-3',
        external_student_id: 'stu-3',
        link_status: 'frozen',
      },
      error: null,
    };
    const id = await getLinkedStudentId({
      orgId: 'org-1',
      clerkUserId: 'user-frozen',
    });
    expect(id).toBeNull();
  });

  it('excludes rows with a different external_source', async () => {
    nextResponse = { data: null, error: null };
    await getLinkedStudentId({ orgId: 'org-1', clerkUserId: 'user-1' });
    const eqMap = Object.fromEntries(recorded.eq);
    expect(eqMap.external_source).toBe('chess_empire');
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
      data: {
        id: 'mem-v',
        external_student_id: 'stu-v',
        link_status: 'verified',
      },
      error: null,
    };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'user-v',
    });
    expect(result.state).toBe('verified');
    expect(result.studentId).toBe('stu-v');
    expect(result.memberId).toBe('mem-v');
  });

  it('returns state=pending_confirm with studentId when link_status=pending_confirm', async () => {
    nextResponse = {
      data: {
        id: 'mem-p',
        external_student_id: 'stu-p',
        link_status: 'pending_confirm',
      },
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
    nextResponse = { data: null, error: null };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'nobody',
    });
    expect(result.state).toBe('no_link');
    expect(result.studentId).toBeNull();
    expect(result.memberId).toBeNull();
  });

  it('returns state=no_link when link_status is frozen (never surface personalized data)', async () => {
    nextResponse = {
      data: {
        id: 'mem-f',
        external_student_id: 'stu-f',
        link_status: 'frozen',
      },
      error: null,
    };
    const result = await getMembershipState({
      orgId: 'org-1',
      clerkUserId: 'user-f',
    });
    expect(result.state).toBe('no_link');
    expect(result.studentId).toBeNull();
  });

  it('returns state=no_link when external_student_id is null (placeholder row)', async () => {
    nextResponse = {
      data: {
        id: 'mem-placeholder',
        external_student_id: null,
        link_status: 'pending',
      },
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
});
