/**
 * Tests for /api/premium-welcome.
 *
 * Covers: GET returns the seen flag (true/false/absent), POST sets the flag by
 * merging into existing publicMetadata, and 401 for both verbs when
 * unauthenticated. Clerk `auth` and `clerkClient` are mocked like the other
 * route tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'user-1' };
const userStore: { publicMetadata: Record<string, unknown> } = {
  publicMetadata: {},
};
const updateSpy = vi.fn(async () => ({}));

vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
  clerkClient: async () => ({
    users: {
      getUser: async () => ({ publicMetadata: userStore.publicMetadata }),
      updateUserMetadata: updateSpy,
    },
  }),
}));

import { GET, POST } from '../route';

beforeEach(() => {
  authStore.userId = 'user-1';
  userStore.publicMetadata = {};
  updateSpy.mockClear();
});

describe('GET /api/premium-welcome', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it('returns seen:false when the flag is absent', async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ seen: false });
  });

  it('returns seen:true when the flag is set', async () => {
    userStore.publicMetadata = { premiumWelcomeSeen: true };
    const res = await GET();
    expect(await res.json()).toEqual({ seen: true });
  });

  it('treats a non-true flag value as not seen', async () => {
    userStore.publicMetadata = { premiumWelcomeSeen: 'yes' };
    const res = await GET();
    expect(await res.json()).toEqual({ seen: false });
  });
});

describe('POST /api/premium-welcome', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await POST();
    expect(res.status).toBe(401);
    expect(updateSpy).not.toHaveBeenCalled();
  });

  it('sets premiumWelcomeSeen and returns ok', async () => {
    const res = await POST();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    expect(updateSpy).toHaveBeenCalledWith('user-1', {
      publicMetadata: { premiumWelcomeSeen: true },
    });
  });

  it('only sends the premiumWelcomeSeen key so Clerk preserves other metadata', async () => {
    await POST();
    const payload = updateSpy.mock.calls[0][1] as {
      publicMetadata: Record<string, unknown>;
    };
    expect(Object.keys(payload.publicMetadata)).toEqual(['premiumWelcomeSeen']);
  });
});
