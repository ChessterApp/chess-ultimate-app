/**
 * Shared resolver for the player-facing cosmetics routes: Clerk auth → org →
 * verified CE student. Coin spending and inventory require a verified linked
 * account (D-8, §7.1) — unlinked callers are refused with a typed result the
 * route turns into 401/400/403.
 */
import 'server-only';
import { auth } from '@clerk/nextjs/server';
import { loadOrgFromHeaders } from '@/lib/org-from-headers';
import { getMembershipState } from '@/lib/chess-empire-member';

export type ResolvedStudent =
  | { ok: true; orgId: string; studentId: string; ownerUserId: string }
  | { ok: false; status: 401 | 400 | 403; error: string };

export async function resolveStudent(): Promise<ResolvedStudent> {
  const { userId } = await auth();
  if (!userId) return { ok: false, status: 401, error: 'Unauthorized' };

  const org = await loadOrgFromHeaders();
  if (!org) return { ok: false, status: 400, error: 'Organization not resolved' };

  const membership = await getMembershipState({ orgId: org.id, clerkUserId: userId });
  if (membership.state !== 'verified' || !membership.studentId) {
    return { ok: false, status: 403, error: 'not_linked' };
  }
  // `ownerUserId` is the caller's Clerk id — the subject key for the owner-keyed
  // companion tables (plan A3). Other gamification routes ignore it and use the
  // (orgId, studentId) ledger keying.
  return { ok: true, orgId: org.id, studentId: membership.studentId, ownerUserId: userId };
}
