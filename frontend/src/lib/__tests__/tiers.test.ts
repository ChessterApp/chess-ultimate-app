import { describe, it, expect } from 'vitest';
import {
  nextTier,
  recommendTier,
  tierOrder,
  type Tier,
  type TierMap,
} from '../tiers';

const TIERS: TierMap = {
  starter: { id: 'starter', display_name: 'Starter', seat_cap: 25, price_usd_monthly: 49, price_usd_annual: 499, features: [], best_for: '' },
  growth:  { id: 'growth',  display_name: 'Growth',  seat_cap: 100, price_usd_monthly: 129, price_usd_annual: 1316, features: [], best_for: '' },
  pro:     { id: 'pro',     display_name: 'Pro',     seat_cap: 300, price_usd_monthly: 299, price_usd_annual: 3050, features: [], best_for: '' },
  enterprise: { id: 'enterprise', display_name: 'Enterprise', seat_cap: null, price_usd_monthly: null, price_usd_annual: null, features: [], best_for: '' },
};

describe('tierOrder', () => {
  it('returns the canonical order', () => {
    expect(tierOrder()).toEqual(['starter', 'growth', 'pro', 'enterprise']);
  });
});

describe('nextTier', () => {
  it('returns the next ladder rung', () => {
    expect(nextTier('starter')).toBe('growth');
    expect(nextTier('growth')).toBe('pro');
    expect(nextTier('pro')).toBe('enterprise');
  });
  it('returns null at top of ladder', () => {
    expect(nextTier('enterprise')).toBeNull();
  });
});

describe('recommendTier', () => {
  it('recommends starter for tiny schools', () => {
    expect(recommendTier(10, TIERS)).toBe('starter');
  });
  it('recommends growth at 26-100', () => {
    expect(recommendTier(80, TIERS)).toBe('growth');
  });
  it('recommends pro at 101-300', () => {
    expect(recommendTier(250, TIERS)).toBe('pro');
  });
  it('recommends enterprise above pro cap', () => {
    expect(recommendTier(1000, TIERS)).toBe('enterprise');
  });
});
