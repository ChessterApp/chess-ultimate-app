/**
 * Personal (individual) Whop subscription lookup.
 *
 * The single source of truth for "does this Clerk user have their own active
 * paid plan" — independent of any Chess Empire school link. Reads the
 * `subscriptions` table that the Whop webhook upserts (see
 * `src/app/api/whop/webhook/route.ts`, keyed `whop_membership_id`, linked to a
 * user via `clerk_user_id`).
 *
 * Used by:
 *  - `GET /api/subscription/status` (the client-facing premium check), and
 *  - the access layer's restriction override (`access-membership.ts`): a frozen
 *    or expired school membership is overridden to full access when the user
 *    pays for their own plan.
 *
 * The Supabase admin client is initialized lazily inside each call (via the
 * `supabaseAdmin` proxy) so importing this module is side-effect free — the old
 * status route was stubbed precisely because a module-level Supabase init
 * crashed in standalone mode.
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';

export interface PersonalSubscription {
  active: boolean;
  plan: string | null;
  status: string;
  currentPeriodEnd: string | null;
}

/** Statuses that count as a live, paying (or trialing) subscription. */
const ACTIVE_STATUSES = new Set(['active', 'trialing']);

const INACTIVE: PersonalSubscription = {
  active: false,
  plan: null,
  status: 'none',
  currentPeriodEnd: null,
};

/**
 * Resolve the caller's personal subscription. Returns `{active:false, ...
 * status:'none'}` when there is no row, the row is inactive, or its billing
 * period has elapsed. Any lookup error resolves to inactive (fail-closed for
 * the premium check; the access-layer override treats "no active sub" as "no
 * override", so the underlying school link still governs access).
 */
export async function getPersonalSubscription(
  clerkUserId: string | null | undefined,
): Promise<PersonalSubscription> {
  if (!clerkUserId) return INACTIVE;

  try {
    const { data, error } = await supabaseAdmin
      .from('subscriptions')
      .select('plan_type, status, current_period_end')
      .eq('clerk_user_id', clerkUserId)
      .order('updated_at', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error || !data) return INACTIVE;

    const status = (data.status as string | null) || 'none';
    const currentPeriodEnd = (data.current_period_end as string | null) ?? null;

    const notExpired = currentPeriodEnd
      ? new Date(currentPeriodEnd).getTime() > Date.now()
      : true;
    const active = ACTIVE_STATUSES.has(status) && notExpired;

    if (!active) {
      return { active: false, plan: null, status, currentPeriodEnd };
    }
    return {
      active: true,
      plan: (data.plan_type as string | null) ?? null,
      status,
      currentPeriodEnd,
    };
  } catch (err) {
    console.error('[personal-subscription] lookup failed', err);
    return INACTIVE;
  }
}
