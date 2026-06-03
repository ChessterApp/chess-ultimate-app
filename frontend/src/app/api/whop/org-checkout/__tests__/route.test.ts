import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';

describe('POST /api/whop/org-checkout', () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_WHOP_ORG_GROWTH_MONTHLY = 'plan_growth_monthly_test';
    process.env.NEXT_PUBLIC_WHOP_ORG_STARTER_ANNUAL = 'plan_starter_annual_test';
  });

  afterEach(() => {
    vi.restoreAllMocks();
    process.env = { ...originalEnv };
  });

  function req(body: unknown) {
    return new Request('http://localhost/api/whop/org-checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  it('rejects unauthenticated requests', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: null });
    const { POST } = await import('../route');
    const r = await POST(req({ tier: 'growth', billing_cycle: 'monthly', org_id: 'org_1' }) as never);
    expect(r.status).toBe(401);
  });

  it('rejects invalid tier', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_1' });
    const { POST } = await import('../route');
    const r = await POST(req({ tier: 'bogus', billing_cycle: 'monthly', org_id: 'org_1' }) as never);
    expect(r.status).toBe(400);
  });

  it('rejects invalid billing cycle', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_1' });
    const { POST } = await import('../route');
    const r = await POST(req({ tier: 'growth', billing_cycle: 'biennial', org_id: 'org_1' }) as never);
    expect(r.status).toBe(400);
  });

  it('rejects missing org_id', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_1' });
    const { POST } = await import('../route');
    const r = await POST(req({ tier: 'growth', billing_cycle: 'monthly' }) as never);
    expect(r.status).toBe(400);
  });

  it('returns 500 when env plan id missing', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_1' });
    delete process.env.NEXT_PUBLIC_WHOP_ORG_PRO_MONTHLY;
    const { POST } = await import('../route');
    const r = await POST(req({ tier: 'pro', billing_cycle: 'monthly', org_id: 'org_1' }) as never);
    expect(r.status).toBe(500);
    const body = await r.json();
    expect(body.error).toBe('plan_not_configured');
  });

  it('returns a checkout URL with org metadata stamped on success', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_xyz' });
    const { POST } = await import('../route');
    const r = await POST(req({ tier: 'growth', billing_cycle: 'monthly', org_id: 'org_abc' }) as never);
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.checkoutUrl).toContain('whop.com/checkout/plan_growth_monthly_test');
    expect(body.checkoutUrl).toContain('metadata[kind]=org_subscription');
    expect(body.checkoutUrl).toContain('metadata[org_id]=org_abc');
    expect(body.checkoutUrl).toContain('metadata[tier]=growth');
    expect(body.checkoutUrl).toContain('metadata[billing_cycle]=monthly');
    expect(body.checkoutUrl).toContain('metadata[clerk_user_id]=user_xyz');
  });

  it('accepts enterprise tier (PRD §11.3 #1)', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_xyz' });
    process.env.NEXT_PUBLIC_WHOP_ORG_ENTERPRISE_MONTHLY = 'plan_ent_monthly_test';
    const { POST } = await import('../route');
    const r = await POST(req({ tier: 'enterprise', billing_cycle: 'monthly', org_id: 'org_ent' }) as never);
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.checkoutUrl).toContain('whop.com/checkout/plan_ent_monthly_test');
    expect(body.checkoutUrl).toContain('metadata[tier]=enterprise');
  });

  it('stamps sso_enabled when true on enterprise checkout', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_xyz' });
    process.env.NEXT_PUBLIC_WHOP_ORG_ENTERPRISE_ANNUAL = 'plan_ent_annual_test';
    const { POST } = await import('../route');
    const r = await POST(req({
      tier: 'enterprise', billing_cycle: 'annual', org_id: 'org_ent', sso_enabled: true,
    }) as never);
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.checkoutUrl).toContain('metadata[sso_enabled]=true');
  });

  it('does not stamp sso_enabled for non-enterprise tier', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_xyz' });
    const { POST } = await import('../route');
    const r = await POST(req({
      tier: 'growth', billing_cycle: 'monthly', org_id: 'org_abc', sso_enabled: true,
    }) as never);
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.checkoutUrl).not.toContain('metadata[sso_enabled]');
  });

  it('omits sso_enabled when false on enterprise', async () => {
    (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({ userId: 'user_xyz' });
    process.env.NEXT_PUBLIC_WHOP_ORG_ENTERPRISE_MONTHLY = 'plan_ent_monthly_test';
    const { POST } = await import('../route');
    const r = await POST(req({
      tier: 'enterprise', billing_cycle: 'monthly', org_id: 'org_ent', sso_enabled: false,
    }) as never);
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(body.checkoutUrl).not.toContain('metadata[sso_enabled]');
  });
});
