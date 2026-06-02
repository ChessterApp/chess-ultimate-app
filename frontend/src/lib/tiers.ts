/**
 * Tier types + client-side fetcher.
 *
 * Single source of truth lives in `backend/services/tier_quota.py` and is
 * served via `/api/tiers`. Never hardcode tier values in the frontend.
 */

export type TierId = 'starter' | 'growth' | 'pro' | 'enterprise';

export interface Tier {
  id: TierId;
  display_name: string;
  seat_cap: number | null; // null = unlimited
  price_usd_monthly: number | null; // null = custom (enterprise)
  price_usd_annual: number | null;
  features: string[];
  best_for: string;
}

export type TierMap = Record<TierId, Tier>;

export async function fetchTiers(fetchImpl: typeof fetch = fetch): Promise<TierMap> {
  const res = await fetchImpl('/api/tiers', { cache: 'force-cache' });
  if (!res.ok) {
    throw new Error(`Failed to load tiers: ${res.status}`);
  }
  const body = await res.json();
  return body.tiers as TierMap;
}

export function tierOrder(): TierId[] {
  return ['starter', 'growth', 'pro', 'enterprise'];
}

export function nextTier(current: TierId): TierId | null {
  const order = tierOrder();
  const i = order.indexOf(current);
  return i >= 0 && i < order.length - 1 ? order[i + 1] : null;
}

export function recommendTier(studentCount: number, tiers: TierMap): TierId {
  // Walk Starter→Growth→Pro→Enterprise; return the first that fits.
  for (const id of tierOrder()) {
    const t = tiers[id];
    if (!t) continue;
    if (t.seat_cap === null || studentCount <= t.seat_cap) return id;
  }
  return 'enterprise';
}
