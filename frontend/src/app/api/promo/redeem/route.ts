import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';

// PROMO_CODE_PRD §2 — Promo-code redeem endpoint.
//
// v1 scope: 100%-off codes only. Skips Whop checkout entirely and activates
// the org directly, mirroring the org-activation side-effects from the Whop
// webhook (../whop/webhook/route.ts → handleOrgSubscription).

type Tier = 'starter' | 'growth' | 'pro' | 'enterprise';
type Cycle = 'monthly' | 'annual';

const VALID_TIERS = new Set<Tier>(['starter', 'growth', 'pro', 'enterprise']);
const VALID_CYCLES = new Set<Cycle>(['monthly', 'annual']);

interface PromoRow {
  code: string;
  discount_pct: number;
  max_uses: number | null;
  uses: number;
  active: boolean;
  expires_at: string | null;
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  let body: { code?: string; orgId?: string; tier?: string; cycle?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }

  const code = typeof body.code === 'string' ? body.code.trim() : '';
  const orgId = typeof body.orgId === 'string' ? body.orgId.trim() : '';
  const tier = body.tier as Tier | undefined;
  const cycle = body.cycle as Cycle | undefined;

  if (!code) {
    return NextResponse.json({ error: 'missing_code' }, { status: 400 });
  }
  if (!orgId) {
    return NextResponse.json({ error: 'missing_orgId' }, { status: 400 });
  }
  if (!tier || !VALID_TIERS.has(tier)) {
    return NextResponse.json({ error: 'invalid_tier' }, { status: 400 });
  }
  if (!cycle || !VALID_CYCLES.has(cycle)) {
    return NextResponse.json({ error: 'invalid_cycle' }, { status: 400 });
  }

  // Org-owner check: caller must be the owner of `orgId`.
  const { data: membership, error: memberErr } = await supabaseAdmin
    .from('organization_members')
    .select('role')
    .eq('organization_id', orgId)
    .eq('user_id', userId)
    .maybeSingle();
  if (memberErr) {
    console.error('[promo/redeem] membership lookup failed', memberErr);
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  if (!membership || membership.role !== 'owner') {
    return NextResponse.json({ error: 'forbidden' }, { status: 403 });
  }

  // Load promo code (case-insensitive lookup against the PK).
  const { data: promo, error: promoErr } = await supabaseAdmin
    .from('promo_codes')
    .select('code, discount_pct, max_uses, uses, active, expires_at')
    .eq('code', code)
    .maybeSingle();
  if (promoErr) {
    console.error('[promo/redeem] promo lookup failed', promoErr);
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  if (!promo) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  const promoRow = promo as PromoRow;

  if (!promoRow.active) {
    return NextResponse.json({ error: 'inactive' }, { status: 410 });
  }
  if (promoRow.expires_at && new Date(promoRow.expires_at) <= new Date()) {
    return NextResponse.json({ error: 'expired' }, { status: 410 });
  }
  if (promoRow.max_uses != null && promoRow.uses >= promoRow.max_uses) {
    return NextResponse.json({ error: 'code_exhausted' }, { status: 409 });
  }
  if (promoRow.discount_pct < 100) {
    return NextResponse.json(
      { error: 'partial_discount_unsupported' },
      { status: 400 },
    );
  }

  // 100%-off codes always upgrade the partner to the top tier (annual
  // enterprise). Best for the partner, simplest to support — silent override
  // on the server, response shape to the client is unchanged.
  let effectiveTier: Tier = tier;
  let effectiveCycle: Cycle = cycle;
  const isFullDiscount =
    promoRow.discount_pct === 100 || promoRow.code.toUpperCase() === 'FREE';
  if (isFullDiscount && (effectiveTier !== 'enterprise' || effectiveCycle !== 'annual')) {
    console.info(
      `[promo/redeem] full-discount override: code=${promoRow.code} ` +
        `requested=${tier}/${cycle} → enterprise/annual`,
    );
    effectiveTier = 'enterprise';
    effectiveCycle = 'annual';
  }

  // Atomic redeem via optimistic concurrency: only succeed when the row's
  // `uses` still matches what we just read. If a concurrent redeem already
  // bumped it, this update affects 0 rows and we retry-or-409.
  const { data: redeemed, error: updErr } = await supabaseAdmin
    .from('promo_codes')
    .update({ uses: promoRow.uses + 1 })
    .eq('code', promoRow.code)
    .eq('uses', promoRow.uses)
    .eq('active', true)
    .select('code, uses')
    .maybeSingle();
  if (updErr) {
    console.error('[promo/redeem] redeem update failed', updErr);
    return NextResponse.json({ error: 'redeem_failed' }, { status: 500 });
  }
  if (!redeemed) {
    return NextResponse.json({ error: 'code_exhausted' }, { status: 409 });
  }

  // Mirror Whop webhook's handleOrgSubscription: upsert organization_billing
  // (pinned on organization_id) and flip the org to active.
  const { error: billErr } = await supabaseAdmin
    .from('organization_billing')
    .upsert(
      {
        organization_id: orgId,
        plan: effectiveTier,
        billing_cycle: effectiveCycle,
        redeemed_promo_code: promoRow.code,
        redeemed_promo_at: new Date().toISOString(),
      },
      { onConflict: 'organization_id' },
    );
  if (billErr) {
    console.error('[promo/redeem] org_billing upsert failed', billErr);
    return NextResponse.json({ error: 'billing_failed' }, { status: 500 });
  }

  const { error: orgErr } = await supabaseAdmin
    .from('organizations')
    .update({ status: 'active' })
    .eq('id', orgId);
  if (orgErr) {
    console.error('[promo/redeem] org status update failed', orgErr);
    return NextResponse.json({ error: 'activation_failed' }, { status: 500 });
  }

  return NextResponse.json({ ok: true, redirect: '/for-schools/start/brand' });
}
