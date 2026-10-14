/**
 * Shared "is this subscriptions row a live plan" rule.
 *
 * Used by the server lookup (`personal-subscription.ts`) and the local-first
 * PowerSync path in `useSubscription`, so both answer the same way. The
 * `subscriptions` table has no `active` column — activeness is derived from
 * `status` and `current_period_end`.
 */

/** Statuses that count as a live, paying (or trialing) subscription. */
export const ACTIVE_STATUSES: ReadonlySet<string> = new Set(['active', 'trialing']);

export function isSubscriptionActive(
  status: string | null | undefined,
  currentPeriodEnd: string | null | undefined,
  now: number = Date.now(),
): boolean {
  if (!status || !ACTIVE_STATUSES.has(status)) return false;
  if (!currentPeriodEnd) return true;
  const end = new Date(currentPeriodEnd).getTime();
  // An unparseable end date fails closed, same as an elapsed one.
  return Number.isFinite(end) && end > now;
}
