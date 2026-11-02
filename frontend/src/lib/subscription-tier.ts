/**
 * Shared subscription-tier resolution for the coach proxies.
 *
 * Every coach proxy (`chat`, `tool`, `live-token`, `voice-usage`, `analysis`,
 * `analysis/stream`) resolves the
 * caller's tier server-side through THIS one helper and forwards it to Hermes as
 * the `x-subscription-tier` header, so tier logic lives in exactly one place.
 *
 * Users with an active `vip` personal subscription (`subscriptions.plan_type`,
 * granted manually by ops) get the `pro` tier — Hermes pairs it with
 * `VOICE_MINUTES_PRO=unlimited` for unrestricted coaching. Everyone else gets the
 * env `COACH_DEFAULT_TIER` (default `'free'`) so ops can flip behavior without a
 * code change. Mapping paid Whop plans to tiers slots in here later (see the
 * TODO), without touching any of the callers.
 *
 * IMPORTANT: never initialize a Supabase (or any other) client at module scope.
 * Standalone mode evaluates module bodies eagerly and a module-level client init
 * crashes the route (this is why `api/subscription/status` was stubbed). Any
 * client must be lazily constructed inside the function.
 */

import { getPersonalSubscription } from '@/lib/personal-subscription';

export type SubscriptionTier = 'free' | 'premium' | 'pro';

const VALID_TIERS: readonly SubscriptionTier[] = ['free', 'premium', 'pro'];

/** Manually granted plan that unlocks the top coach tier. */
const VIP_PLAN = 'vip';

/** Read + validate the ops-configurable default tier from env. */
function defaultTier(): SubscriptionTier {
  const raw = (process.env.COACH_DEFAULT_TIER || 'free').trim().toLowerCase();
  return (VALID_TIERS as readonly string[]).includes(raw)
    ? (raw as SubscriptionTier)
    : 'free';
}

/**
 * Resolve a Clerk user's subscription tier. Always returns a valid tier and
 * never throws — on any failure it falls back to the configured default so a
 * lookup outage never blocks the coach.
 *
 * @param userId Clerk user id.
 */
export async function resolveUserTier(
  userId: string,
): Promise<SubscriptionTier> {
  try {
    // getPersonalSubscription constructs its Supabase client lazily and never
    // throws (errors resolve to inactive → default tier).
    const sub = await getPersonalSubscription(userId);
    if (sub.active && sub.plan?.toLowerCase() === VIP_PLAN) return 'pro';
    // TODO(billing): map paid Whop plans to tiers once billing tiers are defined.
    return defaultTier();
  } catch {
    return 'free';
  }
}
