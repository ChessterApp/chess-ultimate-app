import { NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { getPersonalSubscription } from '@/lib/personal-subscription';

/**
 * GET /api/subscription/status — the client-facing premium check.
 *
 * Reports the caller's personal (individual) Whop subscription, resolved from
 * the `subscriptions` table via `getPersonalSubscription`. The Supabase client
 * is initialized lazily inside the helper, so this route no longer risks the
 * module-level init crash that forced the previous "everyone is premium" stub.
 *
 *  - Not authenticated → { active:false, plan:null, reason:'not_authenticated' }
 *  - Active row        → { active:true, plan, status, currentPeriodEnd }
 *  - No row / inactive → { active:false, plan:null, status:'none' }
 */
export async function GET() {
  try {
    const { userId } = await auth();
    if (!userId) {
      return NextResponse.json({
        active: false,
        plan: null,
        reason: 'not_authenticated',
      });
    }

    const sub = await getPersonalSubscription(userId);
    if (sub.active) {
      return NextResponse.json({
        active: true,
        plan: sub.plan,
        status: sub.status,
        currentPeriodEnd: sub.currentPeriodEnd,
      });
    }
    return NextResponse.json({ active: false, plan: null, status: 'none' });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'unknown';
    console.error('[Subscription Status] Error:', message);
    return NextResponse.json({ active: false, plan: null, error: message });
  }
}
