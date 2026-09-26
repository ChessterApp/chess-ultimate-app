/**
 * Server-side route guard for gated features. Call at the top of a gated
 * route's server layout: it resolves the signed-in user's membership and, if
 * they're restricted (frozen/expired) and the route isn't in their allowlist,
 * redirects to `/dashboard?locked=<featureKey>` — where the dashboard opens the
 * contextual upsell modal. Full-access users pass straight through.
 */
import 'server-only';
import { redirect } from 'next/navigation';
import {
  getAccessPolicy,
  isRouteAllowed,
  featureKeyForPath,
} from '@/lib/access-policy';
import { resolveMembershipState } from '@/lib/access-membership';

export async function requireAccess(pathname: string): Promise<void> {
  const state = await resolveMembershipState();
  const policy = getAccessPolicy(state);
  if (isRouteAllowed(policy, pathname)) return;
  const feature = featureKeyForPath(pathname);
  redirect(feature ? `/dashboard?locked=${feature}` : '/dashboard');
}
