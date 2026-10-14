import { isSubscriptionActive } from '@/lib/subscription-status';

const NOW = Date.parse('2026-10-14T12:00:00Z');

describe('isSubscriptionActive', () => {
  it('accepts active and trialing with no end date', () => {
    expect(isSubscriptionActive('active', null, NOW)).toBe(true);
    expect(isSubscriptionActive('trialing', undefined, NOW)).toBe(true);
  });

  it('accepts a live status whose period ends in the future', () => {
    expect(isSubscriptionActive('active', '2027-09-28T00:00:00Z', NOW)).toBe(true);
  });

  it('rejects an elapsed period', () => {
    expect(isSubscriptionActive('active', '2026-10-13T00:00:00Z', NOW)).toBe(false);
  });

  it('rejects non-live statuses and a missing status', () => {
    for (const s of ['canceled', 'past_due', 'expired', 'none', '', null, undefined]) {
      expect(isSubscriptionActive(s, null, NOW)).toBe(false);
    }
  });

  it('fails closed on an unparseable end date', () => {
    expect(isSubscriptionActive('active', 'not-a-date', NOW)).toBe(false);
  });
});
