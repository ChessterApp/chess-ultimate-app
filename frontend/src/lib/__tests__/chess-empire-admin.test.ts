/**
 * Phase 4 — tests for the Chesster-side service helper. Inject a fake
 * Supabase client via __setAdminClientFactoryForTests so we can record
 * select/update/insert calls and script per-table responses.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  __setAdminClientFactoryForTests,
  listOrgCeMembers,
  listBranchTokens,
  rotateBranchToken,
  revokeBranchToken,
  insertBranchToken,
  freezeMember,
  unfreezeMember,
  revokeMember,
  OrgScopeError,
  NotFoundError,
  ExistingActiveTokenError,
  type CeMemberRow,
  type BranchTokenRow,
} from '../chess-empire-admin';

type Op = {
  table: string;
  op: 'select' | 'update' | 'insert';
  filters: Record<string, unknown>;
  patch?: Record<string, unknown>;
  payload?: Record<string, unknown>;
};

interface TableScript {
  // Per-table scripted responses. `select.maybeSingle` and `select.then`
  // share the same row queue; tests can also script per-id rows.
  selectRow?: unknown;
  selectRows?: unknown[];
  updateRow?: unknown;
  insertRow?: unknown;
  selectError?: { message: string };
  updateError?: { message: string };
  insertError?: { message: string };
  // Used by insertBranchToken existing-active-token check.
  existingActiveIds?: string[];
}

function buildFakeClient(
  scripts: Record<string, TableScript>,
  ops: Op[],
) {
  return {
    from(table: string) {
      const script = scripts[table] || {};
      const op: Op = { table, op: 'select', filters: {} };

      let mutationStarted = false;
      const builder = {
        // SELECT chain — only sets op when this is the first call (mutations
        // followed by .select('*').single() should not overwrite op.op).
        select(_cols: string) {
          if (!mutationStarted) {
            op.op = 'select';
            ops.push(op);
          }
          return builder;
        },
        eq(col: string, val: unknown) {
          op.filters[col] = val;
          return builder;
        },
        is(col: string, val: unknown) {
          op.filters[`${col}__is`] = val;
          return builder;
        },
        in(col: string, vals: unknown) {
          op.filters[`${col}__in`] = vals;
          return builder;
        },
        order() {
          return builder;
        },
        limit() {
          // When insertBranchToken does .select('id').eq().eq().is().limit(1)
          // this resolves to { data: existing[], error: null }.
          const ids = (script.existingActiveIds || []).map((id) => ({ id }));
          return Promise.resolve({ data: ids, error: script.selectError ?? null });
        },
        maybeSingle() {
          return Promise.resolve({
            data: script.selectRow ?? null,
            error: script.selectError ?? null,
          });
        },
        single() {
          // single() is used after update().select() or insert().select().
          if (op.op === 'update') {
            return Promise.resolve({
              data: script.updateRow ?? null,
              error: script.updateError ?? null,
            });
          }
          if (op.op === 'insert') {
            return Promise.resolve({
              data: script.insertRow ?? null,
              error: script.insertError ?? null,
            });
          }
          return Promise.resolve({
            data: script.selectRow ?? null,
            error: script.selectError ?? null,
          });
        },
        // SELECT without single — array shape (used by listOrgCeMembers and
        // listBranchTokens at the end of the chain).
        then(resolve: (v: unknown) => void) {
          resolve({
            data: script.selectRows ?? [],
            error: script.selectError ?? null,
          });
        },

        // UPDATE chain
        update(patch: Record<string, unknown>) {
          op.op = 'update';
          op.patch = patch;
          mutationStarted = true;
          ops.push(op);
          return builder;
        },

        // INSERT chain
        insert(payload: Record<string, unknown>) {
          op.op = 'insert';
          op.payload = payload;
          mutationStarted = true;
          ops.push(op);
          return builder;
        },
      };
      return builder;
    },
  };
}

let ops: Op[] = [];
let scripts: Record<string, TableScript> = {};

beforeEach(() => {
  ops = [];
  scripts = {};
  __setAdminClientFactoryForTests(() =>
    buildFakeClient(scripts, ops) as unknown as ReturnType<
      typeof buildFakeClient
    > as never,
  );
});

afterEach(() => {
  __setAdminClientFactoryForTests(null);
  vi.useRealTimers();
});

describe('listOrgCeMembers', () => {
  it('returns rows scoped to org + chess_empire source', async () => {
    scripts.organization_members = {
      selectRows: [
        {
          id: 'm-1',
          organization_id: 'org-1',
          external_source: 'chess_empire',
          link_status: 'verified',
        },
      ],
    };
    const out = await listOrgCeMembers('org-1');
    expect(out).toHaveLength(1);
    const selectOp = ops.find(
      (o) => o.table === 'organization_members' && o.op === 'select',
    );
    expect(selectOp?.filters.organization_id).toBe('org-1');
    expect(selectOp?.filters.external_source).toBe('chess_empire');
  });

  it('returns [] for empty orgId', async () => {
    expect(await listOrgCeMembers('')).toEqual([]);
  });
});

describe('listBranchTokens', () => {
  it('returns tokens filtered by org', async () => {
    scripts.branch_invite_tokens = {
      selectRows: [
        { id: 't-1', organization_id: 'org-1' },
        { id: 't-2', organization_id: 'org-1' },
      ],
    };
    const out = await listBranchTokens('org-1');
    expect(out).toHaveLength(2);
    const selectOp = ops.find(
      (o) => o.table === 'branch_invite_tokens' && o.op === 'select',
    );
    expect(selectOp?.filters.organization_id).toBe('org-1');
  });
});

describe('rotateBranchToken', () => {
  it('writes revoke + insert and returns both rows', async () => {
    const existing: BranchTokenRow = {
      id: 't-1',
      organization_id: 'org-1',
      external_branch_id: 'br-1',
      branch_name: 'Debut',
      token: 'old-token',
      expires_at: null,
      revoked_at: null,
      created_at: '2026-06-30T18:17:00Z',
      created_by: 'user-creator',
    };
    scripts.branch_invite_tokens = {
      selectRow: existing,
      updateRow: { ...existing, revoked_at: '2026-06-30T19:00:00Z' },
      insertRow: { ...existing, id: 't-2', token: 'new-token', revoked_at: null },
    };
    const result = await rotateBranchToken({
      orgId: 'org-1',
      tokenId: 't-1',
      actorClerkUserId: 'user-x',
    });
    expect(result.revoked.revoked_at).toBe('2026-06-30T19:00:00Z');
    expect(result.created.id).toBe('t-2');
    const updateOp = ops.find((o) => o.op === 'update');
    expect(updateOp?.patch?.revoked_at).toBeTruthy();
    const insertOp = ops.find((o) => o.op === 'insert');
    expect(insertOp?.payload?.created_by).toBe('user-x');
    expect(insertOp?.payload?.external_branch_id).toBe('br-1');
  });

  it('throws OrgScopeError on org mismatch', async () => {
    scripts.branch_invite_tokens = {
      selectRow: {
        id: 't-1',
        organization_id: 'other-org',
        external_branch_id: 'br-1',
        branch_name: 'X',
        token: 'tok',
      },
    };
    await expect(
      rotateBranchToken({
        orgId: 'org-1',
        tokenId: 't-1',
        actorClerkUserId: 'user-x',
      }),
    ).rejects.toBeInstanceOf(OrgScopeError);
  });

  it('throws NotFoundError when token missing', async () => {
    scripts.branch_invite_tokens = { selectRow: null };
    await expect(
      rotateBranchToken({
        orgId: 'org-1',
        tokenId: 't-missing',
        actorClerkUserId: 'user-x',
      }),
    ).rejects.toBeInstanceOf(NotFoundError);
  });
});

describe('revokeBranchToken', () => {
  it('updates revoked_at and returns the row', async () => {
    const existing = {
      id: 't-1',
      organization_id: 'org-1',
      external_branch_id: 'br-1',
      branch_name: 'X',
      token: 'tok',
    };
    scripts.branch_invite_tokens = {
      selectRow: existing,
      updateRow: { ...existing, revoked_at: '2026-06-30T19:00:00Z' },
    };
    const out = await revokeBranchToken({
      orgId: 'org-1',
      tokenId: 't-1',
      actorClerkUserId: 'user-x',
    });
    expect(out.revoked_at).toBe('2026-06-30T19:00:00Z');
  });

  it('throws OrgScopeError on org mismatch', async () => {
    scripts.branch_invite_tokens = {
      selectRow: { id: 't-1', organization_id: 'other-org' },
    };
    await expect(
      revokeBranchToken({
        orgId: 'org-1',
        tokenId: 't-1',
        actorClerkUserId: 'user-x',
      }),
    ).rejects.toBeInstanceOf(OrgScopeError);
  });
});

describe('insertBranchToken', () => {
  it('refuses when an active token exists', async () => {
    scripts.branch_invite_tokens = { existingActiveIds: ['t-existing'] };
    await expect(
      insertBranchToken({
        orgId: 'org-1',
        branchId: 'br-1',
        branchName: 'Debut',
        actorClerkUserId: 'user-x',
      }),
    ).rejects.toBeInstanceOf(ExistingActiveTokenError);
  });

  it('inserts and returns the new row when none active', async () => {
    scripts.branch_invite_tokens = {
      existingActiveIds: [],
      insertRow: {
        id: 't-new',
        organization_id: 'org-1',
        external_branch_id: 'br-1',
        branch_name: 'Debut',
        token: 'fresh',
      },
    };
    const out = await insertBranchToken({
      orgId: 'org-1',
      branchId: 'br-1',
      branchName: 'Debut',
      actorClerkUserId: 'user-x',
    });
    expect(out.id).toBe('t-new');
    const insertOp = ops.find((o) => o.op === 'insert');
    expect(insertOp?.payload?.external_branch_id).toBe('br-1');
    expect(insertOp?.payload?.branch_name).toBe('Debut');
  });
});

describe('freezeMember / unfreezeMember / revokeMember', () => {
  function setMemberScript(row: Partial<CeMemberRow> | null) {
    scripts.organization_members = {
      selectRow: row,
      updateRow: row ? { ...row, _updated: true } : null,
    };
  }

  it('freezeMember flips link_status to frozen', async () => {
    setMemberScript({
      id: 'm-1',
      organization_id: 'org-1',
      link_status: 'verified',
    });
    await freezeMember({
      orgId: 'org-1',
      memberId: 'm-1',
      actorClerkUserId: 'u',
    });
    const updateOp = ops.find((o) => o.op === 'update');
    expect(updateOp?.patch?.link_status).toBe('frozen');
  });

  it('unfreezeMember flips back to verified and clears revoked_at', async () => {
    setMemberScript({
      id: 'm-1',
      organization_id: 'org-1',
      link_status: 'frozen',
    });
    await unfreezeMember({
      orgId: 'org-1',
      memberId: 'm-1',
      actorClerkUserId: 'u',
    });
    const updateOp = ops.find((o) => o.op === 'update');
    expect(updateOp?.patch?.link_status).toBe('verified');
    expect(updateOp?.patch?.link_verified_at).toBeTruthy();
    expect(updateOp?.patch?.link_revoked_at).toBeNull();
  });

  it('revokeMember sets link_status=revoked and stamps link_revoked_at', async () => {
    setMemberScript({
      id: 'm-1',
      organization_id: 'org-1',
      link_status: 'verified',
    });
    await revokeMember({
      orgId: 'org-1',
      memberId: 'm-1',
      actorClerkUserId: 'u',
    });
    const updateOp = ops.find((o) => o.op === 'update');
    expect(updateOp?.patch?.link_status).toBe('revoked');
    expect(updateOp?.patch?.link_revoked_at).toBeTruthy();
  });

  it('throws OrgScopeError when member belongs to another org', async () => {
    setMemberScript({
      id: 'm-1',
      organization_id: 'other-org',
      link_status: 'verified',
    });
    await expect(
      freezeMember({ orgId: 'org-1', memberId: 'm-1', actorClerkUserId: 'u' }),
    ).rejects.toBeInstanceOf(OrgScopeError);
  });

  it('throws NotFoundError when member missing', async () => {
    setMemberScript(null);
    await expect(
      revokeMember({ orgId: 'org-1', memberId: 'm-x', actorClerkUserId: 'u' }),
    ).rejects.toBeInstanceOf(NotFoundError);
  });
});
