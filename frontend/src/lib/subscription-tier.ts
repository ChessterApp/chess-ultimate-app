/**
 * Shared subscription-tier resolution for the coach proxies.
 *
 * Every coach proxy (`chat`, `tool`, `live-token`, `voice-usage`) resolves the
 * caller's tier server-side through THIS one helper and forwards it to Hermes as
 * the `x-subscription-tier` header, so tier logic lives in exactly one place.
 *
 * For now it mirrors the historical stub (all users treated the same) but reads
 * the tier from env `COACH_DEFAULT_TIER` (default `'free'`) so ops can flip
 * behavior without a code change. The structure — a single async function with a
 * lazy lookup — is where a real Supabase/Whop subscription lookup slots in later
 * (see the TODO), without touching any of the callers.
 *
 * IMPORTANT: never initialize a Supabase (or any other) client at module scope.
 * Standalone mode evaluates module bodies eagerly and a module-level client init
 * crashes the route (this is why `api/subscription/status` was stubbed). Any
 * client must be lazily constructed inside the function.
 */

export type SubscriptionTier = 'free' | 'premium' | 'pro';

const VALID_TIERS: readonly SubscriptionTier[] = ['free', 'premium', 'pro'];

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
 * @param userId Clerk user id (currently unused; the real lookup keys on it).
 */
export async function resolveUserTier(
  userId: string,
): Promise<SubscriptionTier> {
  try {
    // TODO(billing): replace with a real per-user subscription lookup once
    // billing is live — lazily construct the Supabase/Whop client HERE (never
    // at module scope) and map the user's active plan to a tier, e.g.:
    //   const supabase = createClient(url, key);
    //   const plan = await supabase.from('subscriptions')...eq('user_id', userId)
    //   return mapPlanToTier(plan);
    // Until then every user gets the env-configured default tier.
    void userId;
    return defaultTier();
  } catch {
    return 'free';
  }
}
