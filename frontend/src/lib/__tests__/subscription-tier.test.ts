import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest';

const getPersonalSubscription = vi.fn();
vi.mock('@/lib/personal-subscription', () => ({
  getPersonalSubscription: (...args: unknown[]) => getPersonalSubscription(...args),
}));

import { resolveUserTier } from '../subscription-tier';

const NO_SUB = { active: false, plan: null, status: 'none', currentPeriodEnd: null };

describe('resolveUserTier', () => {
  const original = process.env.COACH_DEFAULT_TIER;

  beforeEach(() => {
    getPersonalSubscription.mockReset();
    getPersonalSubscription.mockResolvedValue(NO_SUB);
  });

  afterEach(() => {
    if (original === undefined) delete process.env.COACH_DEFAULT_TIER;
    else process.env.COACH_DEFAULT_TIER = original;
  });

  it('defaults to free when COACH_DEFAULT_TIER is unset', async () => {
    delete process.env.COACH_DEFAULT_TIER;
    expect(await resolveUserTier('user_1')).toBe('free');
  });

  it('honors a valid COACH_DEFAULT_TIER override', async () => {
    process.env.COACH_DEFAULT_TIER = 'premium';
    expect(await resolveUserTier('user_1')).toBe('premium');
    process.env.COACH_DEFAULT_TIER = 'PRO';
    expect(await resolveUserTier('user_1')).toBe('pro');
  });

  it('falls back to free for an invalid tier value', async () => {
    process.env.COACH_DEFAULT_TIER = 'enterprise';
    expect(await resolveUserTier('user_1')).toBe('free');
  });

  it('returns a valid tier for any user id', async () => {
    delete process.env.COACH_DEFAULT_TIER;
    const tier = await resolveUserTier('anyone');
    expect(['free', 'premium', 'pro']).toContain(tier);
  });

  it('gives an active vip subscription the pro tier', async () => {
    delete process.env.COACH_DEFAULT_TIER;
    getPersonalSubscription.mockResolvedValue({
      active: true, plan: 'vip', status: 'active', currentPeriodEnd: null,
    });
    expect(await resolveUserTier('user_vip')).toBe('pro');
    expect(getPersonalSubscription).toHaveBeenCalledWith('user_vip');
  });

  it('keeps non-vip active plans on the default tier', async () => {
    delete process.env.COACH_DEFAULT_TIER;
    for (const plan of ['manual', 'yearly', 'monthly', null]) {
      getPersonalSubscription.mockResolvedValue({
        active: true, plan, status: 'active', currentPeriodEnd: null,
      });
      expect(await resolveUserTier('user_paid')).toBe('free');
    }
  });

  it('ignores an inactive vip row', async () => {
    delete process.env.COACH_DEFAULT_TIER;
    getPersonalSubscription.mockResolvedValue({
      active: false, plan: null, status: 'canceled', currentPeriodEnd: null,
    });
    expect(await resolveUserTier('user_lapsed')).toBe('free');
  });

  it('falls back to free when the lookup throws', async () => {
    delete process.env.COACH_DEFAULT_TIER;
    getPersonalSubscription.mockRejectedValue(new Error('db down'));
    expect(await resolveUserTier('user_1')).toBe('free');
  });
});
