/**
 * Tests for DELETE /api/chess-empire/link/members/[studentId].
 *
 * Covers: unauthenticated (401), missing id (400), foreign/absent row (404,
 * never revealing other users' links), `self` blocked (403), successful
 * child/other unlink (200 + row deleted), and idempotent double-delete
 * (second call 404, no delete issued).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

const store: {
  lookup: { data: unknown; error: unknown };
  deleteError: unknown;
  deleteCalled: boolean;
} = { lookup: { data: null, error: null }, deleteError: null, deleteCalled: false };

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: () => {
      const chain = {
        select: () => chain,
        delete: () => {
          store.deleteCalled = true;
          return chain;
        },
        eq: () => chain,
        in: () => chain,
        maybeSingle: () => Promise.resolve(store.lookup),
        then: (
          onFulfilled: (v: { error: unknown }) => unknown,
          onRejected?: (e: unknown) => unknown,
        ) => Promise.resolve({ error: store.deleteError }).then(onFulfilled, onRejected),
      };
      return chain;
    },
  },
}));

import { DELETE } from '../[studentId]/route';

function call(studentId: string) {
  return DELETE(new Request('http://t') as never, {
    params: Promise.resolve({ studentId }),
  });
}

beforeEach(() => {
  authStore.userId = 'user-1';
  store.lookup = { data: null, error: null };
  store.deleteError = null;
  store.deleteCalled = false;
});

describe('DELETE /api/chess-empire/link/members/[studentId]', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await call('stu-1');
    expect(res.status).toBe(401);
    expect(store.deleteCalled).toBe(false);
  });

  it('400 when the student id is blank', async () => {
    const res = await call('   ');
    expect(res.status).toBe(400);
    expect(store.deleteCalled).toBe(false);
  });

  it('404 for a foreign or absent row (never reveals other users links)', async () => {
    store.lookup = { data: null, error: null };
    const res = await call('stu-foreign');
    expect(res.status).toBe(404);
    expect(store.deleteCalled).toBe(false);
  });

  it('403 when the target row is the self link', async () => {
    store.lookup = { data: { id: 'm-1', relationship: 'self' }, error: null };
    const res = await call('stu-self');
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ error: 'cannot_remove_self' });
    expect(store.deleteCalled).toBe(false);
  });

  it('403 when relationship is null (pre-migration rows read as self)', async () => {
    store.lookup = { data: { id: 'm-1', relationship: null }, error: null };
    const res = await call('stu-legacy');
    expect(res.status).toBe(403);
    expect(store.deleteCalled).toBe(false);
  });

  it('removes a child link', async () => {
    store.lookup = { data: { id: 'm-2', relationship: 'child' }, error: null };
    const res = await call('stu-kid');
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    expect(store.deleteCalled).toBe(true);
  });

  it('removes an other link', async () => {
    store.lookup = { data: { id: 'm-3', relationship: 'other' }, error: null };
    const res = await call('stu-other');
    expect(res.status).toBe(200);
    expect(store.deleteCalled).toBe(true);
  });

  it('is idempotent — a second delete of an already-removed row 404s with no side effects', async () => {
    store.lookup = { data: { id: 'm-2', relationship: 'child' }, error: null };
    const first = await call('stu-kid');
    expect(first.status).toBe(200);

    // The row is gone now; the lookup returns nothing.
    store.lookup = { data: null, error: null };
    store.deleteCalled = false;
    const second = await call('stu-kid');
    expect(second.status).toBe(404);
    expect(store.deleteCalled).toBe(false);
  });

  it('500 when the lookup errors', async () => {
    store.lookup = { data: null, error: { message: 'boom' } };
    const res = await call('stu-kid');
    expect(res.status).toBe(500);
  });
});
