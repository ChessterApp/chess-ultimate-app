/**
 * Tests for `createAutoAcceptedFamilyEdge` — the same-branch "trusted" shortcut
 * that grants a parent register rights over an already-owned student WITHOUT
 * minting a second member row or stealing ownership. It writes a single accepted
 * `family_link_invites` edge (the row `getFamilyLinkedStudentIds` reads) and
 * reuses an existing accepted edge instead of piling up duplicates.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface Captured {
  existing: Record<string, unknown> | null;
  inserted: Record<string, unknown> | null;
}
const cap: Captured = { existing: null, inserted: null };

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: () => {
      const chain: Record<string, unknown> = {
        select: () => chain,
        eq: () => chain,
        maybeSingle: async () => ({ data: cap.existing, error: null }),
        insert: (payload: Record<string, unknown>) => {
          cap.inserted = payload;
          return {
            select: () => ({
              single: async () => ({ data: { id: 'new-edge' }, error: null }),
            }),
          };
        },
      };
      return chain;
    },
  },
}));

// Deterministic UUIDs so the token is stable across the (mocked) run.
vi.mock('node:crypto', () => ({ randomUUID: () => 'aaaa-bbbb' }));

import { createAutoAcceptedFamilyEdge } from '../family-link-invite';

beforeEach(() => {
  cap.existing = null;
  cap.inserted = null;
});

describe('createAutoAcceptedFamilyEdge', () => {
  it('inserts an accepted edge stamping both parties, no member row', async () => {
    const res = await createAutoAcceptedFamilyEdge({
      inviterUserId: 'parent-1',
      inviterOrgId: 'org-1',
      inviterStudentId: 'stu-self',
      accepterUserId: 'other-parent',
      targetStudentId: 'stu-target',
      targetOrgId: 'org-1',
      targetName: 'Bek N',
      relationship: 'child',
    });
    expect(res).toEqual({ id: 'new-edge', reused: false });
    expect(cap.inserted).toMatchObject({
      inviter_user_id: 'parent-1',
      inviter_student_id: 'stu-self',
      accepted_by_user_id: 'other-parent',
      accepted_student_id: 'stu-target',
      accepted_org_id: 'org-1',
      status: 'accepted',
      relationship: 'child',
      target_email: null,
    });
  });

  it('reuses an existing accepted edge instead of inserting a duplicate', async () => {
    cap.existing = { id: 'edge-existing' };
    const res = await createAutoAcceptedFamilyEdge({
      inviterUserId: 'parent-1',
      inviterOrgId: 'org-1',
      inviterStudentId: 'stu-self',
      accepterUserId: 'other-parent',
      targetStudentId: 'stu-target',
      targetOrgId: 'org-1',
      targetName: 'Bek N',
      relationship: 'child',
    });
    expect(res).toEqual({ id: 'edge-existing', reused: true });
    expect(cap.inserted).toBeNull();
  });
});
