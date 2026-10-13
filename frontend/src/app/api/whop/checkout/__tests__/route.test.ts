import { describe, it, expect, vi, beforeAll } from 'vitest';
import { NextRequest } from 'next/server';

vi.mock('@clerk/nextjs/server', () => ({ auth: async () => ({ userId: 'user_1' }) }));

let POST: typeof import('../route').POST;

beforeAll(async () => {
  vi.stubEnv('NEXT_PUBLIC_WHOP_MONTHLY_PLAN', 'plan_monthly');
  ({ POST } = await import('../route'));
});

describe('POST /api/whop/checkout', () => {
  it('returns from Whop to /upgrade/success (not onboarding?step=complete)', async () => {
    const req = new NextRequest('https://chesster.io/api/whop/checkout', {
      method: 'POST',
      body: JSON.stringify({ planId: 'plan_monthly' }),
    });
    const { checkoutUrl } = await (await POST(req)).json();
    const url = new URL(checkoutUrl);
    expect(url.searchParams.get('d')).toBe('https://chesster.io/upgrade/success');
    expect(url.searchParams.get('metadata[clerk_user_id]')).toBe('user_1');
  });
});
