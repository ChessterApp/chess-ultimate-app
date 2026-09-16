/**
 * GET /api/gamification/profile
 *
 * Clerk-authenticated. Resolves the caller's linked CE student via the existing
 * verified-link machinery and returns their gamification profile (xp, rank +
 * progress, coins, streak, tournament stats since launch). Unlinked students get
 * an empty/hidden payload (D-8) — nothing accrues visibly until they link.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { loadOrgFromHeaders } from '@/lib/org-from-headers';
import { getMembershipState } from '@/lib/chess-empire-member';
import { loadGamificationProfile } from '@/lib/gamification/store';
import { UNLINKED_PROFILE } from '@/lib/gamification/profile';

export const dynamic = 'force-dynamic';

export async function GET() {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const org = await loadOrgFromHeaders();
  if (!org) {
    // No org on the host (e.g. plain chesster.io): there is nothing to link to,
    // so surface the same hidden-profile payload as an unlinked membership (D-8)
    // rather than a 400 that spams the dashboard console on every load.
    return NextResponse.json(UNLINKED_PROFILE);
  }

  const membership = await getMembershipState({ orgId: org.id, clerkUserId: userId });
  if (membership.state !== 'verified' || !membership.studentId) {
    // D-8: unlinked students are hidden everywhere.
    return NextResponse.json(UNLINKED_PROFILE);
  }

  const profile = await loadGamificationProfile(org.id, membership.studentId);
  return NextResponse.json(profile);
}
