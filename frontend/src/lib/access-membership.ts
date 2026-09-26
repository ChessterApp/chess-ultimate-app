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
