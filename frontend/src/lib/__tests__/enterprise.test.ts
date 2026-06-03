import { describe, it, expect } from 'vitest';
import {
  nextTier,
  recommendTier,
  tierOrder,
  type TierMap,
} from '../tiers';

// PRD §11.3 #1 — Enterprise tier is now self-serve.
// These tests guard the tier-quota + recommendation behavior that drives
// the wizard's enterprise UX.

const TIERS: TierMap = {
  starter:    { id: 'starter',    display_name: 'Starter',    seat_cap: 25,  price_usd_monthly: 49,  price_usd_annual: 499,  features: [], best_for: '' },
  growth:     { id: 'growth',     display_name: 'Growth',     seat_cap: 100, price_usd_monthly: 129, price_usd_annual: 1316, features: [], best_for: '' },
  pro:        { id: 'pro',        display_name: 'Pro',        seat_cap: 300, price_usd_monthly: 299, price_usd_annual: 3050, features: [], best_for: '' },
  enterprise: { id: 'enterprise', display_name: 'Enterprise', seat_cap: null, price_usd_monthly: null, price_usd_annual: null, features: [], best_for: '' },
};

describe('Enterprise tier — recommendation', () => {
  it('recommends enterprise above 300 students', () => {
    expect(recommendTier(301, TIERS)).toBe('enterprise');
    expect(recommendTier(500, TIERS)).toBe('enterprise');
    expect(recommendTier(1000, TIERS)).toBe('enterprise');
    expect(recommendTier(50_000, TIERS)).toBe('enterprise');
  });

  it('recommends pro at exactly 300', () => {
    expect(recommendTier(300, TIERS)).toBe('pro');
  });

  it('does not recommend enterprise for normal student counts', () => {
    expect(recommendTier(50, TIERS)).not.toBe('enterprise');
    expect(recommendTier(150, TIERS)).not.toBe('enterprise');
    expect(recommendTier(280, TIERS)).not.toBe('enterprise');
  });
});

describe('Enterprise tier — ladder position', () => {
  it('appears last in tier order', () => {
    const order = tierOrder();
    expect(order[order.length - 1]).toBe('enterprise');
  });

  it('has null seat_cap (unlimited)', () => {
    expect(TIERS.enterprise.seat_cap).toBeNull();
  });

  it('has null price (custom)', () => {
    expect(TIERS.enterprise.price_usd_monthly).toBeNull();
    expect(TIERS.enterprise.price_usd_annual).toBeNull();
  });

  it('is the top of the ladder — nextTier returns null', () => {
    expect(nextTier('enterprise')).toBeNull();
  });
});
