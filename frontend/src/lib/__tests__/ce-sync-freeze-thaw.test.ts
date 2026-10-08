/**
 * Tests for the event-driven CE freeze/thaw helper in chess-empire-admin.ts.
 *
 * Drives `syncFreezeThawByStudent` end-to-end with an injected fake Supabase
 * client (via __setAdminClientFactoryForTests) and a mock Clerk adapter — no
 * network, no production Clerk/Supabase. Mirrors the reconciliation matrix of
 * scripts/sync-chess-empire-members.mjs for the freeze/thaw directions.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  __setAdminClientFactoryForTests,
  hasActivePersonalSubscription,
  syncFreezeThawByStudent,
  NotFoundError,
  type CeSyncClerkAdapter,
  type CeStudentStatusReader,
} from '../chess-empire-admin';

interface FakeMember {
  id: string;
  organization_id: string;
  user_id: string;
  link_status: string;
  organizations: { clerk_org_id: string | null } | null;
}

interface FakeSub {
  status: string;
  current_period_end: string | null;
}

/**
 * Single shared fake client so updates recorded by freezeMember/unfreezeMember
 * (which each call adminClient()) are visible to the test. `maybeSingle`
 * returns the member row (or null); the update chain merges its patch into the
 * returned row and records it in `updates`.
 */
function makeClient({
  member,
  subs = [],
}: {
  member: FakeMember | null;
  subs?: FakeSub[];
}) {
  const updates: Array<{ patch: Record<string, unknown> }> = [];
  const client = {
    updates,
    from(table: string) {
      if (table === 'subscriptions') {
        const chain = {
          select: () => chain,
          eq: () => chain,
          order: () => chain,
          limit: () => Promise.resolve({ data: subs, error: null }),
        };
        return chain;
      }
      if (table === 'organization_members') {
        let patch: Record<string, unknown> | null = null;
        const chain = {
          select: () => chain,
          update: (p: Record<string, unknown>) => {
            patch = p;
            return chain;
          },
          eq: () => chain,
          maybeSingle: () => Promise.resolve({ data: member, error: null }),
          single: () => {
            updates.push({ patch: patch ?? {} });
            return Promise.resolve({
              data: { ...(member ?? {}), ...(patch ?? {}) },
              error: null,
            });
          },
        };
        return chain;
      }
      throw new Error(`unexpected table ${table}`);
    },
  };
  return client;
}

function mockClerk(): CeSyncClerkAdapter & {
  create: ReturnType<typeof vi.fn>;
  del: ReturnType<typeof vi.fn>;
} {
  const create = vi.fn(async () => {});
  const del = vi.fn(async () => {});
  return {
    create,
    del,
    createMembership: create,
    deleteMembership: del,
  };
}

/** CE status reader stub — returns the authoritative status the test wants. */
function reader(status: string | null): CeStudentStatusReader & {
  getStatus: ReturnType<typeof vi.fn>;
} {
  const getStatus = vi.fn(async () => status);
  return { getStatus };
}

const baseMember: FakeMember = {
  id: 'mem-1',
  organization_id: 'org-1',
  user_id: 'user_1',
  link_status: 'frozen',
  organizations: { clerk_org_id: 'clerk-org-1' },
};

function inject(opts: { member: FakeMember | null; subs?: FakeSub[] }) {
  const client = makeClient(opts);
  __setAdminClientFactoryForTests(() => client as never);
  return client;
}

afterEach(() => {
  __setAdminClientFactoryForTests(null);
  vi.restoreAllMocks();
});

describe('syncFreezeThawByStudent', () => {
  it('thaws a frozen member + adds Clerk org membership', async () => {
    const client = inject({ member: { ...baseMember, link_status: 'frozen' } });
    const clerk = mockClerk();

    const result = await syncFreezeThawByStudent({
      externalStudentId: 'stu-1',
      ceStatus: 'active',
      clerk,
      ceReader: reader('active'),
    });

    expect(result.action).toBe('thaw');
    expect(result.linkStatus).toBe('verified');
    expect(client.updates[0].patch.link_status).toBe('verified');
    expect(clerk.create).toHaveBeenCalledWith('clerk-org-1', 'user_1');
    expect(clerk.del).not.toHaveBeenCalled();
  });

  it('freezes a verified member + removes Clerk org membership', async () => {
    const client = inject({ member: { ...baseMember, link_status: 'verified' }, subs: [] });
    const clerk = mockClerk();

    const result = await syncFreezeThawByStudent({
      externalStudentId: 'stu-1',
      ceStatus: 'frozen',
      clerk,
      ceReader: reader('frozen'),
    });

    expect(result.action).toBe('freeze');
    expect(result.linkStatus).toBe('frozen');
    expect(client.updates[0].patch.link_status).toBe('frozen');
    expect(clerk.del).toHaveBeenCalledWith('clerk-org-1', 'user_1');
    expect(clerk.create).not.toHaveBeenCalled();
  });

  it('freeze with an active personal sub keeps the Clerk org membership', async () => {
    const client = inject({
      member: { ...baseMember, link_status: 'verified' },
      subs: [{ status: 'active', current_period_end: null }],
    });
    const clerk = mockClerk();

    const result = await syncFreezeThawByStudent({
      externalStudentId: 'stu-1',
      ceStatus: 'frozen',
      clerk,
      ceReader: reader('frozen'),
    });

    expect(result.action).toBe('freeze');
    expect(client.updates[0].patch.link_status).toBe('frozen');
    expect(clerk.del).not.toHaveBeenCalled();
  });

  it('is a no-op when CE status already matches link_status', async () => {
    const client = inject({ member: { ...baseMember, link_status: 'verified' } });
    const clerk = mockClerk();

    const result = await syncFreezeThawByStudent({
      externalStudentId: 'stu-1',
      ceStatus: 'active',
      clerk,
      ceReader: reader('active'),
    });

    expect(result.action).toBe('none');
    expect(result.linkStatus).toBe('verified');
    expect(client.updates).toHaveLength(0);
    expect(clerk.create).not.toHaveBeenCalled();
    expect(clerk.del).not.toHaveBeenCalled();
  });

  it('does not touch Clerk when the org has no clerk_org_id', async () => {
    inject({ member: { ...baseMember, link_status: 'frozen', organizations: { clerk_org_id: null } } });
    const clerk = mockClerk();

    const result = await syncFreezeThawByStudent({
      externalStudentId: 'stu-1',
      ceStatus: 'active',
      clerk,
      ceReader: reader('active'),
    });

    expect(result.action).toBe('thaw');
    expect(clerk.create).not.toHaveBeenCalled();
  });

  it('throws NotFoundError when the student is not linked in Chesster', async () => {
    inject({ member: null });
    const clerk = mockClerk();

    await expect(
      syncFreezeThawByStudent({
        externalStudentId: 'nope',
        ceStatus: 'frozen',
        clerk,
        ceReader: reader('frozen'),
      }),
    ).rejects.toBeInstanceOf(NotFoundError);
    expect(clerk.create).not.toHaveBeenCalled();
    expect(clerk.del).not.toHaveBeenCalled();
  });

  it('acts on the CE DB status, not the posted hint (DB says frozen → freeze)', async () => {
    // Attacker posts `active` to thaw, but CE DB says the student is frozen.
    const client = inject({ member: { ...baseMember, link_status: 'verified' } });
    const clerk = mockClerk();
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    const result = await syncFreezeThawByStudent({
      externalStudentId: 'stu-1',
      ceStatus: 'active',
      clerk,
      ceReader: reader('frozen'),
    });

    expect(result.action).toBe('freeze');
    expect(client.updates[0].patch.link_status).toBe('frozen');
    expect(clerk.del).toHaveBeenCalledWith('clerk-org-1', 'user_1');
    expect(clerk.create).not.toHaveBeenCalled();
  });

  it('acts on the CE DB status, not the posted hint (DB says active → thaw)', async () => {
    // Attacker posts `frozen` to freeze, but CE DB says the student is active.
    const client = inject({ member: { ...baseMember, link_status: 'frozen' } });
    const clerk = mockClerk();
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    const result = await syncFreezeThawByStudent({
      externalStudentId: 'stu-1',
      ceStatus: 'frozen',
      clerk,
      ceReader: reader('active'),
    });

    expect(result.action).toBe('thaw');
    expect(client.updates[0].patch.link_status).toBe('verified');
    expect(clerk.create).toHaveBeenCalledWith('clerk-org-1', 'user_1');
    expect(clerk.del).not.toHaveBeenCalled();
  });

  it('throws NotFoundError (and touches nothing) when the student is missing in CE DB', async () => {
    const client = inject({ member: { ...baseMember, link_status: 'frozen' } });
    const clerk = mockClerk();
    const ceReader = reader(null);

    await expect(
      syncFreezeThawByStudent({
        externalStudentId: 'stu-1',
        ceStatus: 'active',
        clerk,
        ceReader,
      }),
    ).rejects.toBeInstanceOf(NotFoundError);
    // CE missing is checked before any Chesster read/mutation or Clerk call.
    expect(client.updates).toHaveLength(0);
    expect(clerk.create).not.toHaveBeenCalled();
    expect(clerk.del).not.toHaveBeenCalled();
  });
});

describe('hasActivePersonalSubscription', () => {
  it('active row with no expiry → true', async () => {
    inject({ member: null, subs: [{ status: 'active', current_period_end: null }] });
    expect(await hasActivePersonalSubscription('u1')).toBe(true);
  });

  it('canceled row → false', async () => {
    inject({ member: null, subs: [{ status: 'canceled', current_period_end: null }] });
    expect(await hasActivePersonalSubscription('u1')).toBe(false);
  });

  it('active but past period end → false', async () => {
    inject({
      member: null,
      subs: [{ status: 'active', current_period_end: '2000-01-01T00:00:00Z' }],
    });
    expect(await hasActivePersonalSubscription('u1')).toBe(false);
  });

  it('no row → false', async () => {
    inject({ member: null, subs: [] });
    expect(await hasActivePersonalSubscription('nobody')).toBe(false);
  });
});
