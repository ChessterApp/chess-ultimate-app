import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import crypto from 'crypto';

import { computeOrgStatus, extractProratedAmount } from '../route';

// PRD §11.2 #8 — annual prorate / org-subscription webhook tests.

describe('computeOrgStatus', () => {
  it('returns suspended for subscription.canceled', () => {
    expect(computeOrgStatus('subscription.canceled', 'active')).toBe('suspended');
    expect(computeOrgStatus('subscription.cancelled', 'active')).toBe('suspended');
  });

  it('returns active for active/trialing/completed', () => {
    expect(computeOrgStatus('subscription.updated', 'active')).toBe('active');
    expect(computeOrgStatus('subscription.updated', 'trialing')).toBe('active');
    expect(computeOrgStatus('membership.went_valid', 'completed')).toBe('active');
  });

  it('returns suspended for unknown statuses', () => {
    expect(computeOrgStatus('subscription.updated', 'paused')).toBe('suspended');
    expect(computeOrgStatus('subscription.updated', undefined)).toBe('suspended');
  });
});

describe('extractProratedAmount', () => {
  it('reads prorated_next_charge_cents first', () => {
    const body = { data: { prorated_next_charge_cents: 1234 } };
    expect(extractProratedAmount(body)).toBe(1234);
  });

  it('falls back to next_billing_amount_cents', () => {
    const body = { data: { next_billing_amount_cents: 4321 } };
    expect(extractProratedAmount(body)).toBe(4321);
  });

  it('falls back to prorated_amount_cents', () => {
    const body = { data: { prorated_amount_cents: 999 } };
    expect(extractProratedAmount(body)).toBe(999);
  });

  it('returns null when no amount present', () => {
    expect(extractProratedAmount({ data: {} })).toBeNull();
    expect(extractProratedAmount({})).toBeNull();
  });

  it('coerces numeric strings', () => {
    expect(extractProratedAmount({ data: { next_billing_amount_cents: '4500' } })).toBe(4500);
  });

  it('ignores non-numeric junk', () => {
    expect(extractProratedAmount({ data: { next_billing_amount_cents: 'oops' } })).toBeNull();
  });
});

// ─── End-to-end webhook tests for subscription.updated + canceled ────────

const supabaseCalls: Record<string, unknown[]> = { upsert: [], update: [] };

vi.mock('@/lib/supabase-admin', () => {
  const builder = {
    upsert: (row: unknown) => {
      supabaseCalls.upsert.push(row);
      return Promise.resolve({ error: null });
    },
    update: (patch: unknown) => {
      supabaseCalls.update.push(patch);
      return {
        eq: () => Promise.resolve({ error: null }),
      };
    },
  };
  return {
    supabaseAdmin: {
      from: () => builder,
    },
  };
});

function signedRequest(body: Record<string, unknown>): Request {
  const raw = JSON.stringify(body);
  const sig = crypto.createHmac('sha256', 'test-secret').update(raw).digest('hex');
  return new Request('http://localhost/api/whop/webhook', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Whop-Signature': sig,
    },
    body: raw,
  });
}

describe('Whop webhook — subscription.updated + canceled', () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    supabaseCalls.upsert.length = 0;
    supabaseCalls.update.length = 0;
    process.env.WHOP_WEBHOOK_SECRET = 'test-secret';
  });

  afterEach(() => {
    vi.restoreAllMocks();
    process.env = { ...originalEnv };
  });

  it('records prorate amount on subscription.updated', async () => {
    const { POST } = await import('../route');
    const body = {
      action: 'subscription.updated',
      data: {
        id: 'mem_123',
        status: 'active',
        plan_id: 'plan_pro_annual',
        metadata: {
          kind: 'org_subscription',
          org_id: 'org_abc',
          tier: 'pro',
          billing_cycle: 'annual',
        },
        prorated_next_charge_cents: 24500,
      },
    };
    const res = await POST(signedRequest(body) as never);
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.updated).toBe(true);
    expect(data.prorated_next_charge_cents).toBe(24500);
    const upserted = supabaseCalls.upsert[0] as Record<string, unknown>;
    expect(upserted.plan).toBe('pro');
    expect(upserted.billing_cycle).toBe('annual');
    expect(upserted.next_charge_amount_cents).toBe(24500);
  });

  it('suspends the org on subscription.canceled', async () => {
    const { POST } = await import('../route');
    const body = {
      action: 'subscription.canceled',
      data: {
        id: 'mem_456',
        status: 'cancelled',
        plan_id: 'plan_growth_monthly',
        metadata: {
          kind: 'org_subscription',
          org_id: 'org_def',
          tier: 'growth',
          billing_cycle: 'monthly',
        },
      },
    };
    const res = await POST(signedRequest(body) as never);
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.canceled).toBe(true);
    const upserted = supabaseCalls.upsert[0] as Record<string, unknown>;
    expect(upserted).toHaveProperty('canceled_at');
    const orgUpdate = supabaseCalls.update[0] as Record<string, unknown>;
    expect(orgUpdate.status).toBe('suspended');
  });
});
