import { describe, it, expect, afterEach } from 'vitest';

import { resolveUserTier } from '../subscription-tier';

describe('resolveUserTier', () => {
  const original = process.env.COACH_DEFAULT_TIER;

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
});
