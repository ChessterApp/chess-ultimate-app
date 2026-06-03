import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// PRD §6.1 — Org-level Whop checkout.
// Mirrors the individual checkout at ../checkout/route.ts but stamps
// metadata.kind='org_subscription' so the webhook can branch into the
// organization_billing path.

type TierId = 'starter' | 'growth' | 'pro' | 'enterprise';
type BillingCycle = 'monthly' | 'annual';

// Map (tier, cycle) -> the Whop plan id env var.
// Enterprise (PRD §11.3 #1): self-serve checkout uses a dedicated
// NEXT_PUBLIC_WHOP_ORG_ENTERPRISE_{MONTHLY,ANNUAL} plan. Sales-assist
// Calendly stays as an alternate CTA in the UI.
function planIdFor(tier: TierId, cycle: BillingCycle): string | undefined {
  const key = `NEXT_PUBLIC_WHOP_ORG_${tier.toUpperCase()}_${cycle.toUpperCase()}`;
  return process.env[key];
}

const VALID_TIERS = new Set<TierId>(['starter', 'growth', 'pro', 'enterprise']);
const VALID_CYCLES = new Set<BillingCycle>(['monthly', 'annual']);

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: {
    tier?: string;
    billing_cycle?: string;
    org_id?: string;
    sso_enabled?: boolean;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const { tier, billing_cycle, org_id, sso_enabled } = body;
  if (!tier || !VALID_TIERS.has(tier as TierId)) {
    return NextResponse.json({ error: 'Invalid tier' }, { status: 400 });
  }
  if (!billing_cycle || !VALID_CYCLES.has(billing_cycle as BillingCycle)) {
    return NextResponse.json({ error: 'Invalid billing_cycle' }, { status: 400 });
  }
  if (!org_id || typeof org_id !== 'string') {
    return NextResponse.json({ error: 'Missing org_id' }, { status: 400 });
  }

  const planId = planIdFor(tier as TierId, billing_cycle as BillingCycle);
  if (!planId) {
    return NextResponse.json(
      { error: 'plan_not_configured', tier, billing_cycle },
      { status: 500 },
    );
  }

  const redirectUrl = encodeURIComponent(
    'https://chesster.io/for-schools/start/brand?status=paid',
  );

  let checkoutUrl = `https://whop.com/checkout/${planId}?d=${redirectUrl}`;
  checkoutUrl += `&metadata[kind]=${encodeURIComponent('org_subscription')}`;
  checkoutUrl += `&metadata[org_id]=${encodeURIComponent(org_id)}`;
  checkoutUrl += `&metadata[tier]=${encodeURIComponent(tier)}`;
  checkoutUrl += `&metadata[billing_cycle]=${encodeURIComponent(billing_cycle)}`;
  checkoutUrl += `&metadata[clerk_user_id]=${encodeURIComponent(userId)}`;

  // Enterprise self-serve: stamp the SSO toggle into metadata so the webhook
  // can flip the SSO-stub flag on the org. UI sends `sso_enabled` from the
  // enterprise tier card. Other tiers ignore the field.
  if (tier === 'enterprise' && sso_enabled === true) {
    checkoutUrl += `&metadata[sso_enabled]=true`;
  }

  return NextResponse.json({ checkoutUrl, planId });
}
