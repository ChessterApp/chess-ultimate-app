import { NextRequest, NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { verifyWhopSignature } from './verify';

// PRD §6.1 — Whop webhook handler with HMAC SHA-256 signature verification.
//
// We read the raw text body before parsing JSON so the signature check works
// on the exact bytes Whop signed. JSON.parse only after verification passes.

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const sigHeader =
    req.headers.get('x-whop-signature') ||
    req.headers.get('whop-signature');

  const verifyRes = verifyWhopSignature(
    rawBody,
    sigHeader,
    process.env.WHOP_WEBHOOK_SECRET,
  );

  if (!verifyRes.ok) {
    if (verifyRes.reason === 'no_secret') {
      // Fail closed — refuse to process anything until env is wired.
      console.error('[Whop Webhook] WHOP_WEBHOOK_SECRET not set — rejecting');
      return NextResponse.json(
        { ok: false, error: 'webhook_not_configured' },
        { status: 500 },
      );
    }
    console.warn('[Whop Webhook] signature rejected:', verifyRes.reason);
    return NextResponse.json(
      { ok: false, error: 'invalid_signature' },
      { status: 401 },
    );
  }

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ ok: false, error: 'bad_json' }, { status: 400 });
  }

  try {
    const event =
      (body.action as string) || (body.event as string) || 'unknown';
    const membership = (body.data as Record<string, unknown>) || {};
    const metadata =
      (membership.metadata as Record<string, unknown> | undefined) || {};

    console.log(
      '[Whop Webhook]',
      event,
      'kind=',
      metadata.kind,
      JSON.stringify(body).slice(0, 300),
    );

    const kind = (metadata.kind as string) || 'individual';

    if (kind === 'org_subscription') {
      return await handleOrgSubscription(membership, metadata, event, body);
    }

    // Default: individual subscription (existing behavior)
    return await handleIndividualSubscription(membership, event, body);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'unknown';
    console.error('[Whop Webhook] Error:', msg);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}

// ─── Individual subscription path (existing flow) ──────────────────────────

async function handleIndividualSubscription(
  membership: Record<string, unknown>,
  event: string,
  body: Record<string, unknown>,
) {
  const membershipId = membership.id as string | undefined;
  const metadata = (membership.metadata as Record<string, unknown>) || {};
  const userId =
    (metadata.clerk_user_id as string | undefined) ||
    ((membership.discord as Record<string, unknown> | undefined)?.id as
      | string
      | undefined);
  const planId = membership.plan_id as string | undefined;
  const status = membership.status as string | undefined;
  const whopUserId = membership.user_id as string | undefined;

  if (!membershipId) {
    return NextResponse.json({ ok: true, message: 'No membership ID, skipped' });
  }

  const statusMap: Record<string, string> = {
    active: 'active',
    trialing: 'trialing',
    past_due: 'past_due',
    completed: 'active',
    expired: 'expired',
    cancelled: 'canceled',
  };
  const mappedStatus = statusMap[status || ''] || status || 'inactive';

  const planTypeMap: Record<string, string> = {
    plan_2PeIExuNwZt4h: 'weekly',
    plan_wLEg6HdpROrne: 'monthly',
    plan_U4dKEGLY0rEzs: 'yearly',
  };
  const planType = planTypeMap[planId || ''] || 'unknown';

  const { error: upsertError } = await supabaseAdmin
    .from('subscriptions')
    .upsert(
      {
        whop_membership_id: membershipId,
        clerk_user_id: userId || 'unknown',
        whop_user_id: whopUserId,
        plan_id: planId,
        plan_type: planType,
        status: mappedStatus,
        updated_at: new Date().toISOString(),
      },
      { onConflict: 'whop_membership_id' },
    );

  if (upsertError) {
    console.error('[Whop Webhook] Upsert error:', upsertError);
  }

  const { data: sub } = await supabaseAdmin
    .from('subscriptions')
    .select('id')
    .eq('whop_membership_id', membershipId)
    .single();

  if (sub) {
    await supabaseAdmin.from('subscription_events').insert({
      subscription_id: sub.id,
      event_type: event,
      event_data: body,
    });
  }

  return NextResponse.json({ ok: true, kind: 'individual' });
}

// ─── Org subscription path (new — PRD §6.1) ─────────────────────────────────

async function handleOrgSubscription(
  membership: Record<string, unknown>,
  metadata: Record<string, unknown>,
  event: string,
  _body: Record<string, unknown>,
) {
  const membershipId = membership.id as string | undefined;
  const orgId = metadata.org_id as string | undefined;
  const tier = (metadata.tier as string | undefined) || 'starter';
  const billingCycle =
    (metadata.billing_cycle as string | undefined) || 'monthly';
  const status = membership.status as string | undefined;
  const whopUserId = membership.user_id as string | undefined;
  const planId = membership.plan_id as string | undefined;

  if (!orgId || !membershipId) {
    console.warn('[Whop Webhook] org_subscription missing org_id/membership');
    return NextResponse.json(
      { ok: true, message: 'missing org_id or membership_id, skipped' },
    );
  }

  const orgStatus =
    status === 'active' ||
    status === 'completed' ||
    status === 'trialing'
      ? 'active'
      : 'suspended';

  // Upsert org billing row
  const { error: billErr } = await supabaseAdmin
    .from('organization_billing')
    .upsert(
      {
        organization_id: orgId,
        plan: tier,
        billing_cycle: billingCycle,
        whop_membership_id: membershipId,
        whop_user_id: whopUserId,
        whop_plan_id: planId,
      },
      { onConflict: 'organization_id' },
    );

  if (billErr) {
    console.error('[Whop Webhook] org billing upsert error:', billErr);
  }

  // Activate the org
  const { error: orgErr } = await supabaseAdmin
    .from('organizations')
    .update({ status: orgStatus })
    .eq('id', orgId);

  if (orgErr) {
    console.error('[Whop Webhook] org status update error:', orgErr);
  }

  return NextResponse.json({ ok: true, kind: 'org_subscription', event });
}
