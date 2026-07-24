/**
 * Tests for GET /api/chess-empire/link/status.
 *
 * Covers: unauthenticated (401), each link state passthrough, and lookup
 * error (500). The membership lookup is mocked.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

const memberStore: {
  result: { state: string; role: string } | null;
  throws: boolean;
} = { result: { state: 'no_link', role: 'student' }, throws: false };
vi.mock('@/lib/chess-empire-member', () => ({
  getMembershipStateForUser: vi.fn(async () => {
    if (memberStore.throws) throw new Error('boom');
    return memberStore.result;
  }),
}));

// Auto-claim is a no-op here (no pending cookie); its own path is tested in
// pending-registration.test.ts.
vi.mock('@/lib/pending-registration', () => ({
  autoClaimPendingCookie: vi.fn(async () => false),
}));

import { GET } from '../status/route';

beforeEach(() => {
  authStore.userId = 'user-1';
  memberStore.result = { state: 'no_link', role: 'student' };
  memberStore.throws = false;
});

describe('GET /api/chess-empire/link/status', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it('returns no_link for an unlinked user', async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ state: 'no_link', role: 'student' });
  });

  it('returns verified once the row is written', async () => {
    memberStore.result = { state: 'verified', role: 'student' };
    const res = await GET();
    expect(await res.json()).toEqual({ state: 'verified', role: 'student' });
  });

  it('returns pending_confirm state', async () => {
    memberStore.result = { state: 'pending_confirm', role: 'student' };
    const res = await GET();
    expect(await res.json()).toEqual({ state: 'pending_confirm', role: 'student' });
  });

  it('500 when the lookup throws', async () => {
    memberStore.throws = true;
    const res = await GET();
    expect(res.status).toBe(500);
  });
});
