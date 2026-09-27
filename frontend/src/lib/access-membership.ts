/**
 * Shared server-side resolver for the signed-in user's membership state, used
 * by the access layer (root-layout `MembershipProvider` + the `requireAccess`
 * route guard). Wraps `getMembershipStateForUser` — the same by-user lookup the
 * `/api/chess-empire/link/status` route uses — and is deliberately tolerant:
 * unauthenticated / non-member users and any lookup error resolve to `null`
 * (full access), so the access layer never blocks the app on a transient
 * failure.
 */
import 'server-only';
import { auth } from '@clerk/nextjs/server';
import {
  getMembershipStateForUser,
  type MembershipState,
} from '@/lib/chess-empire-member';
import { getAccessPolicy, type AccessPolicy } from '@/lib/access-policy';
import { getPersonalSubscription } from '@/lib/personal-subscription';

export async function resolveMembershipState(): Promise<MembershipState | null> {
  try {
    const { userId } = await auth();
    if (!userId) return null;
    const membership = await getMembershipStateForUser(userId);
    return membership.state;
  } catch (err) {
    console.error('[access] membership resolve failed', err);
    return null;
  }
}

export interface MembershipContext {
  state: MembershipState | null;
  /** True when the user has an active personal Whop subscription. */
  personalSubActive: boolean;
}

/**
 * Resolve the signed-in user's membership state AND whether they hold an active
 * personal subscription — the two inputs the access policy needs. The personal
 * subscription is only looked up when the state is actually restricted
 * (`frozen`/`expired`): for everyone else the override is irrelevant, so we skip
 * the extra Supabase round-trip. Best-effort throughout — any failure resolves
 * to full access.
 */
export async function resolveMembershipContext(): Promise<MembershipContext> {
  try {
    const { userId } = await auth();
    if (!userId) return { state: null, personalSubActive: false };
    const membership = await getMembershipStateForUser(userId);
    const state = membership.state;
    if (state !== 'frozen' && state !== 'expired') {
      return { state, personalSubActive: false };
    }
    const sub = await getPersonalSubscription(userId);
    return { state, personalSubActive: sub.active };
  } catch (err) {
    console.error('[access] membership context resolve failed', err);
    return { state: null, personalSubActive: false };
  }
}

/**
 * Resolve the caller's effective access policy, applying the personal-
 * subscription override. This is the server-side entry point shared by the
 * route guard, the Learn ceiling resolver and the API guard.
 */
export async function resolveAccessPolicy(): Promise<AccessPolicy> {
  const { state, personalSubActive } = await resolveMembershipContext();
  return getAccessPolicy(state, personalSubActive);
}
