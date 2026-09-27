/**
 * Unit tests for the requireAccess server guard: restricted members are
 * redirected to /dashboard?locked=<feature> for gated routes, allowed routes
 * pass through, and full-access members are never redirected.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const redirectMock = vi.fn();
vi.mock('next/navigation', () => ({
  redirect: (url: string) => redirectMock(url),
}));

const resolveAccessPolicyMock = vi.fn();
vi.mock('@/lib/access-membership', () => ({
  resolveAccessPolicy: () => resolveAccessPolicyMock(),
}));

import { requireAccess } from '../require-access';
import { getAccessPolicy } from '../access-policy';

beforeEach(() => {
  redirectMock.mockClear();
  resolveAccessPolicyMock.mockReset();
});

describe('requireAccess', () => {
  it('redirects a frozen member off a locked route with the feature key', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('frozen'));
    await requireAccess('/play');
    expect(redirectMock).toHaveBeenCalledWith('/dashboard?locked=play');
  });

  it('redirects an expired member off a locked route', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('expired'));
    await requireAccess('/database');
    expect(redirectMock).toHaveBeenCalledWith('/dashboard?locked=database');
  });

  it('does not redirect a restricted member on an allowed route', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('frozen'));
    await requireAccess('/learn');
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it('does not redirect a full-access member on a gated route', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('verified'));
    await requireAccess('/play');
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it('treats a null (non-member) state as full access', async () => {
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy(null));
    await requireAccess('/coach');
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it('grants full access to a restricted member with a personal subscription', async () => {
    // The override resolves to a full-access policy → no redirect on a gated route.
    resolveAccessPolicyMock.mockResolvedValue(getAccessPolicy('frozen', true));
    await requireAccess('/play');
    expect(redirectMock).not.toHaveBeenCalled();
  });
});
