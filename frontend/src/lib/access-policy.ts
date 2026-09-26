/**
 * Access policy for Chess Empire members in a restricted state.
 *
 * A `frozen` (school paused) or `expired` (online trial ended) membership keeps
 * the user in the app but limited to Home + Learn + their account pages. Every
 * other feature is visibly locked and routed to an audience-specific upgrade
 * page. This module is the single source of truth for that policy — a pure,
 * React-free module so both client (nav locks, modal) and server (route guard)
 * layers share the exact same rules.
 *
 * Route/feature data is derived from the nav arrays in
 * `src/components/ui/DesktopSidebar.tsx` and
 * `src/components/ui/BottomNavigation.tsx`.
 */
import type { MembershipState } from '@/lib/chess-empire-member';

export type AccessMode = 'full' | 'restricted';
export type RestrictionReason = 'frozen' | 'expired' | null;

export interface AccessPolicy {
  mode: AccessMode;
  reason: RestrictionReason;
  /** Where the primary upgrade CTA points for this restriction. */
  upgradePath: string;
  /** Route prefixes a restricted user may still open (prefix match). */
  allowedRoutes: string[];
}

/**
 * Routes a restricted member keeps: Home (dashboard), Learn, and their own
 * account surfaces, plus the upgrade funnel itself. Prefix-matched, so
 * `/learn/anything` and `/upgrade/expired` are allowed.
 */
export const ALLOWED_RESTRICTED_ROUTES = [
  '/dashboard',
  '/learn',
  '/settings',
  '/profile',
  '/upgrade',
] as const;

/**
 * Locked feature routes → feature key. The key names the feature in the lock
 * modal (i18n `access.feature.<key>`) and is echoed in the
 * `/dashboard?locked=<key>` redirect. Derived from the nav arrays: everything a
 * member sees that is NOT in `ALLOWED_RESTRICTED_ROUTES`.
 */
export const LOCKED_FEATURES: Record<string, string> = {
  '/play': 'play',
  '/coach': 'coach',
  '/database': 'database',
  '/puzzle': 'puzzles',
  '/games': 'games',
  '/editor': 'editor',
};

/** Full, unrestricted access — the default for everyone who isn't gated. */
const FULL_ACCESS: AccessPolicy = {
  mode: 'full',
  reason: null,
  upgradePath: '',
  allowedRoutes: [],
};

/**
 * Resolve the access policy for a membership state. Only `frozen`/`expired`
 * restrict; every other state (including null/undefined, `no_link`,
 * `verified`, `pending_confirm`) gets full access.
 */
export function getAccessPolicy(
  state: MembershipState | null | undefined,
): AccessPolicy {
  if (state === 'frozen') {
    return {
      mode: 'restricted',
      reason: 'frozen',
      upgradePath: '/upgrade/continue',
      allowedRoutes: [...ALLOWED_RESTRICTED_ROUTES],
    };
  }
  if (state === 'expired') {
    return {
      mode: 'restricted',
      reason: 'expired',
      upgradePath: '/upgrade/expired',
      allowedRoutes: [...ALLOWED_RESTRICTED_ROUTES],
    };
  }
  return FULL_ACCESS;
}

/** True when `pathname` sits under `prefix` (exact match or `<prefix>/...`). */
function matchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/**
 * Whether a restricted user may open `pathname`. Always true under full access.
 * The root `/` renders the dashboard/home, so it counts as allowed.
 */
export function isRouteAllowed(policy: AccessPolicy, pathname: string): boolean {
  if (policy.mode === 'full') return true;
  if (pathname === '/') return true;
  return policy.allowedRoutes.some((route) => matchesPrefix(pathname, route));
}

/**
 * Feature key for a locked route (e.g. `/play` → `play`, `/games/wheel` →
 * `games`), or null if the path maps to no locked feature.
 */
export function featureKeyForPath(pathname: string): string | null {
  for (const [prefix, key] of Object.entries(LOCKED_FEATURES)) {
    if (matchesPrefix(pathname, prefix)) return key;
  }
  return null;
}
