/**
 * Unit tests for getPersonalSubscription: active/trialing (not expired) → active;
 * canceled / past-period / no-row / error → inactive.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const maybeSingleResult = { data: null as unknown, error: null as unknown };

// Minimal chainable stub of the supabaseAdmin query builder.
const builder = {
  select: vi.fn(() => builder),
  eq: vi.fn(() => builder),
  order: vi.fn(() => builder),
  limit: vi.fn(() => builder),
  maybeSingle: vi.fn(async () => maybeSingleResult),
};
vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: { from: vi.fn(() => builder) },
}));

import { getPersonalSubscription } from '../personal-subscription';

const FUTURE = new Date(Date.now() + 86400_000).toISOString();
const PAST = new Date(Date.now() - 86400_000).toISOString();

beforeEach(() => {
  maybeSingleResult.data = null;
  maybeSingleResult.error = null;
});

describe('getPersonalSubscription', () => {
  it('inactive when no user id', async () => {
    expect(await getPersonalSubscription(null)).toMatchObject({ active: false, status: 'none' });
  });

  it('active for an active row with a future period end', async () => {
    maybeSingleResult.data = { plan_type: 'monthly', status: 'active', current_period_end: FUTURE };
    const sub = await getPersonalSubscription('u1');
    expect(sub).toEqual({
      active: true,
      plan: 'monthly',
      status: 'active',
      currentPeriodEnd: FUTURE,
    });
  });

  it('active for a trialing row with no period end', async () => {
    maybeSingleResult.data = { plan_type: 'weekly', status: 'trialing', current_period_end: null };
    expect((await getPersonalSubscription('u1')).active).toBe(true);
  });

  it('inactive for an active row past its period end', async () => {
    maybeSingleResult.data = { plan_type: 'monthly', status: 'active', current_period_end: PAST };
    expect((await getPersonalSubscription('u1')).active).toBe(false);
  });

  it('inactive for a canceled row', async () => {
    maybeSingleResult.data = { plan_type: 'monthly', status: 'canceled', current_period_end: FUTURE };
    expect((await getPersonalSubscription('u1')).active).toBe(false);
  });

  it('inactive when no row exists', async () => {
    maybeSingleResult.data = null;
    expect(await getPersonalSubscription('u1')).toMatchObject({ active: false, status: 'none' });
  });

  it('inactive (fail-closed) on a query error', async () => {
    maybeSingleResult.error = { message: 'boom' };
    expect((await getPersonalSubscription('u1')).active).toBe(false);
  });
});
