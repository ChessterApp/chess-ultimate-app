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

import { getLinkedStudentId } from '../chess-empire-member';

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
  it('returns the external_student_id when the row exists', async () => {
    nextResponse = { data: { external_student_id: 'stu-1' }, error: null };
    const id = await getLinkedStudentId({ orgId: 'org-1', clerkUserId: 'user-1' });
    expect(id).toBe('stu-1');
    expect(recorded.table).toBe('organization_members');
    const eqMap = Object.fromEntries(recorded.eq);
    expect(eqMap.organization_id).toBe('org-1');
    expect(eqMap.user_id).toBe('user-1');
    expect(eqMap.external_source).toBe('chess_empire');
    expect(eqMap.link_status).toBe('verified');
  });

  it('returns null when no row matches', async () => {
    nextResponse = { data: null, error: null };
    const id = await getLinkedStudentId({
      orgId: 'org-1',
      clerkUserId: 'user-unknown',
    });
    expect(id).toBeNull();
  });

  it('excludes pending links — the verified filter is part of the query', async () => {
    // The mock just records the filters; this test asserts that link_status=verified
    // is in the eq chain so a pending row would never be returned by Supabase.
    nextResponse = { data: null, error: null };
    await getLinkedStudentId({ orgId: 'org-1', clerkUserId: 'user-pending' });
    const eqMap = Object.fromEntries(recorded.eq);
    expect(eqMap.link_status).toBe('verified');
  });

  it('excludes frozen links via the same verified filter', async () => {
    nextResponse = { data: null, error: null };
    await getLinkedStudentId({ orgId: 'org-1', clerkUserId: 'user-frozen' });
    const eqMap = Object.fromEntries(recorded.eq);
    expect(eqMap.link_status).toBe('verified');
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
