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

const resolveMembershipStateMock = vi.fn();
vi.mock('@/lib/access-membership', () => ({
  resolveMembershipState: () => resolveMembershipStateMock(),
}));

import { requireAccess } from '../require-access';

beforeEach(() => {
  redirectMock.mockClear();
  resolveMembershipStateMock.mockReset();
});

describe('requireAccess', () => {
  it('redirects a frozen member off a locked route with the feature key', async () => {
    resolveMembershipStateMock.mockResolvedValue('frozen');
    await requireAccess('/play');
    expect(redirectMock).toHaveBeenCalledWith('/dashboard?locked=play');
  });

  it('redirects an expired member off a locked route', async () => {
    resolveMembershipStateMock.mockResolvedValue('expired');
    await requireAccess('/database');
    expect(redirectMock).toHaveBeenCalledWith('/dashboard?locked=database');
  });

  it('does not redirect a restricted member on an allowed route', async () => {
    resolveMembershipStateMock.mockResolvedValue('frozen');
    await requireAccess('/learn');
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it('does not redirect a full-access member on a gated route', async () => {
    resolveMembershipStateMock.mockResolvedValue('verified');
    await requireAccess('/play');
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it('treats a null (non-member) state as full access', async () => {
    resolveMembershipStateMock.mockResolvedValue(null);
    await requireAccess('/coach');
    expect(redirectMock).not.toHaveBeenCalled();
  });
});
