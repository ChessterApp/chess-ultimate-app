import { NextRequest, NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/supabase-admin';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const event = body.action || body.event || 'unknown';
    
    console.log('[Whop Webhook]', event, JSON.stringify(body).slice(0, 500));

    // Extract membership data
    const membership = body.data || {};
    const membershipId = membership.id;
    const userId = membership.metadata?.clerk_user_id || membership.discord?.id;
    const planId = membership.plan_id;
    const status = membership.status;
    const whopUserId = membership.user_id;

    if (!membershipId) {
      return NextResponse.json({ ok: true, message: 'No membership ID, skipped' });
    }

    // Map Whop status to our status
    const statusMap: Record<string, string> = {
      'active': 'active',
      'trialing': 'trialing',
      'past_due': 'past_due',
      'completed': 'active',
      'expired': 'expired',
      'cancelled': 'canceled',
    };
    const mappedStatus = statusMap[status] || status || 'inactive';

    // Determine plan type
    const planTypeMap: Record<string, string> = {
      'plan_2PeIExuNwZt4h': 'weekly',
      'plan_wLEg6HdpROrne': 'monthly',
      'plan_U4dKEGLY0rEzs': 'yearly',
    };
    const planType = planTypeMap[planId] || 'unknown';

    // Upsert subscription
    const { error: upsertError } = await supabaseAdmin
      .from('subscriptions')
      .upsert({
        whop_membership_id: membershipId,
        clerk_user_id: userId || 'unknown',
        whop_user_id: whopUserId,
        plan_id: planId,
        plan_type: planType,
        status: mappedStatus,
        updated_at: new Date().toISOString(),
      }, {
        onConflict: 'whop_membership_id',
      });

    if (upsertError) {
      console.error('[Whop Webhook] Upsert error:', upsertError);
    }

    // Log event
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

    return NextResponse.json({ ok: true });
  } catch (err: any) {
    console.error('[Whop Webhook] Error:', err.message);
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}
