/**
 * Tests for POST /api/account/delete — self-service account deletion.
 *
 * Guarantees:
 *   - 401 when the caller is not signed in.
 *   - deletes the CALLER's own Clerk user via clerkClient (never a body id).
 *   - a userId supplied in the request body is ignored — only auth() decides.
 *   - a user who still OWNS an organization is blocked (409), not deleted.
 *   - { ok: true } on success.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

// ---- mock state -------------------------------------------------------------
const state: {
  userId: string | null;
  ownedOrgs: Array<{ organization_id: string }>;
  ownedOrgsError: { message: string } | null;
  deleteUserCalls: string[];
  deleteUserThrows: boolean;
  memberFilters: Array<[string, unknown]>;
} = {
  userId: null,
  ownedOrgs: [],
  ownedOrgsError: null,
  deleteUserCalls: [],
  deleteUserThrows: false,
  memberFilters: [],
};

function resetState(overrides: Partial<typeof state> = {}) {
  state.userId = overrides.userId ?? null;
  state.ownedOrgs = overrides.ownedOrgs ?? [];
  state.ownedOrgsError = overrides.ownedOrgsError ?? null;
  state.deleteUserCalls = [];
  state.deleteUserThrows = overrides.deleteUserThrows ?? false;
  state.memberFilters = [];
}

vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: state.userId }),
  clerkClient: async () => ({
    users: {
      deleteUser: async (id: string) => {
        if (state.deleteUserThrows) throw new Error('clerk down');
        state.deleteUserCalls.push(id);
        return { id };
      },
    },
  }),
}));

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from(_table: string) {
      const chain = {
        select() {
          return chain;
        },
        eq(col: string, val: unknown) {
          state.memberFilters.push([col, val]);
          return chain;
        },
        then(onFulfilled: (v: unknown) => unknown, onRejected?: (e: unknown) => unknown) {
          return Promise.resolve({
            data: state.ownedOrgs,
            error: state.ownedOrgsError,
          }).then(onFulfilled, onRejected);
        },
      };
      return chain;
    },
  },
}));

import { POST } from '../route';

function makeRequest(body?: unknown): Request {
  return new Request('http://localhost/api/account/delete', {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
}

beforeEach(() => {
  resetState();
});

describe('POST /api/account/delete', () => {
  it('returns 401 when not signed in', async () => {
    resetState({ userId: null });

    const res = await POST();
    expect(res.status).toBe(401);
    expect(state.deleteUserCalls).toHaveLength(0);
  });

  it("deletes the caller's own Clerk user and returns { ok: true }", async () => {
    resetState({ userId: 'user_self_1' });

    const res = await POST();
    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toEqual({ ok: true });

    expect(state.deleteUserCalls).toEqual(['user_self_1']);
    // Org-ownership guard filtered on the caller's id + owner role.
    expect(state.memberFilters).toContainEqual(['user_id', 'user_self_1']);
    expect(state.memberFilters).toContainEqual(['role', 'owner']);
  });

  it('ignores a userId supplied in the request body — only deletes auth() id', async () => {
    resetState({ userId: 'user_self_2' });

    // The handler takes no Request param at all — there is structurally no path
    // for a body-supplied id to reach deleteUser. A crafted request is built to
    // document intent, but only the auth() id can ever be deleted.
    void makeRequest({ userId: 'user_victim' });
    await POST();

    expect(state.deleteUserCalls).toEqual(['user_self_2']);
    expect(state.deleteUserCalls).not.toContain('user_victim');
  });

  it('blocks (409) a user who still owns an organization', async () => {
    resetState({
      userId: 'user_owner_1',
      ownedOrgs: [{ organization_id: 'org-1' }],
    });

    const res = await POST();
    expect(res.status).toBe(409);
    const body = await res.json();
    expect(body.code).toBe('owns_organization');
    // The account must NOT be deleted while an org is owned.
    expect(state.deleteUserCalls).toHaveLength(0);
  });

  it('returns 500 (and does not delete) when the ownership check errors', async () => {
    resetState({
      userId: 'user_3',
      ownedOrgsError: { message: 'db down' },
    });

    const res = await POST();
    expect(res.status).toBe(500);
    expect(state.deleteUserCalls).toHaveLength(0);
  });

  it('returns 500 when Clerk deleteUser fails', async () => {
    resetState({ userId: 'user_4', deleteUserThrows: true });

    const res = await POST();
    expect(res.status).toBe(500);
  });
});
