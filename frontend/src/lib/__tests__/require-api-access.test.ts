/**
 * Unit tests for the shared API guard `requireApiAccess`: restricted members get
 * a 403 MEMBERSHIP_RESTRICTED envelope; everyone else passes (null).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getAccessPolicy } from '../access-policy';

const resolveAccessPolicyMock = vi.fn();
vi.mock('@/lib/access-membership', () => ({
  resolveAccessPolicy: () => resolveAccessPolicyMock(),
}));

import { requireApiAccess } from '../require-api-access';

beforeEach(() => {
  resolveAccessPolicyMock.mockReset();
});

describe('requireApiAccess', () => {
  it('returns null for a full-access member', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('verified'));
    expect(await requireApiAccess()).toBeNull();
  });

  it('returns a 403 envelope for a frozen member', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('frozen'));
    const res = await requireApiAccess();
    expect(res).not.toBeNull();
    expect(res!.status).toBe(403);
    expect(await res!.json()).toEqual({
      error: 'MEMBERSHIP_RESTRICTED',
      reason: 'frozen',
      upgradePath: '/upgrade/continue',
    });
  });

  it('returns a 403 with the expired upgrade path for an expired member', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('expired'));
    const res = await requireApiAccess();
    expect(res!.status).toBe(403);
    expect((await res!.json()).upgradePath).toBe('/upgrade/expired');
  });

  it('returns null when the personal-subscription override lifts the restriction', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('frozen', true));
    expect(await requireApiAccess()).toBeNull();
  });
});
