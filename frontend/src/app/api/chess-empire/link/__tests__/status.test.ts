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
// pending-registration.test.ts. `hasLivePendingCookie` drives `recoverable`.
const recoverableStore = { current: false };
vi.mock('@/lib/pending-registration', () => ({
  autoClaimPendingCookie: vi.fn(async () => false),
  hasLivePendingCookie: vi.fn(async () => recoverableStore.current),
}));

// Personal-subscription lookup (only consulted for frozen/expired states).
const subStore = { active: false };
vi.mock('@/lib/personal-subscription', () => ({
  getPersonalSubscription: vi.fn(async () => ({
    active: subStore.active,
    plan: null,
    status: subStore.active ? 'active' : 'none',
    currentPeriodEnd: null,
  })),
}));

import { GET } from '../status/route';

beforeEach(() => {
  authStore.userId = 'user-1';
  memberStore.result = { state: 'no_link', role: 'student' };
  memberStore.throws = false;
  recoverableStore.current = false;
  subStore.active = false;
});

describe('GET /api/chess-empire/link/status', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it('returns no_link with recoverable:false when no live pending cookie exists', async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      state: 'no_link',
      role: 'student',
      recoverable: false,
      personalSubscriptionActive: false,
    });
  });

  it('reports recoverable:true when a live pending cookie can still complete the link', async () => {
    recoverableStore.current = true;
    const res = await GET();
    expect(await res.json()).toEqual({
      state: 'no_link',
      role: 'student',
      recoverable: true,
      personalSubscriptionActive: false,
    });
  });

  it('returns verified once the row is written', async () => {
    memberStore.result = { state: 'verified', role: 'student' };
    const res = await GET();
    expect(await res.json()).toEqual({
      state: 'verified',
      role: 'student',
      recoverable: false,
      personalSubscriptionActive: false,
    });
  });

  it('returns pending_confirm state', async () => {
    memberStore.result = { state: 'pending_confirm', role: 'student' };
    const res = await GET();
    expect(await res.json()).toEqual({
      state: 'pending_confirm',
      role: 'student',
      recoverable: false,
      personalSubscriptionActive: false,
    });
  });

  it('returns frozen state as recoverable:false', async () => {
    memberStore.result = { state: 'frozen', role: 'student' };
    const res = await GET();
    expect(await res.json()).toEqual({
      state: 'frozen',
      role: 'student',
      recoverable: false,
      personalSubscriptionActive: false,
    });
  });

  it('forces recoverable:false for frozen even when a live pending cookie exists', async () => {
    // A frozen membership can never be reactivated by re-claiming the invite,
    // so a live cookie must NOT be reported as recoverable.
    memberStore.result = { state: 'frozen', role: 'student' };
    recoverableStore.current = true;
    const res = await GET();
    expect(await res.json()).toEqual({
      state: 'frozen',
      role: 'student',
      recoverable: false,
      personalSubscriptionActive: false,
    });
  });

  it('reports personalSubscriptionActive:true for a frozen member who self-pays', async () => {
    memberStore.result = { state: 'frozen', role: 'student' };
    subStore.active = true;
    const res = await GET();
    expect(await res.json()).toEqual({
      state: 'frozen',
      role: 'student',
      recoverable: false,
      personalSubscriptionActive: true,
    });
  });

  it('500 when the lookup throws', async () => {
    memberStore.throws = true;
    const res = await GET();
    expect(res.status).toBe(500);
  });
});
