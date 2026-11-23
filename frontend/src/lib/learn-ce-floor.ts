/**
 * Learn path gating — Chess Empire student level floor (Phase 2).
 *
 * Resolves the CE `current_level` for a verified Chess Empire roster student so
 * the `/learn` path can auto-unlock their current level and every level below
 * it (see `computeLockStates` in `@/lib/learn-gating`). Regular chesster.io
 * users, online members, and coaches never get a floor — they keep the plain
 * progressive unlock.
 *
 * Every step is best-effort: any failure or non-applicable case resolves to
 * `undefined`, which makes the learn path fall back to progressive unlock. This
 * never throws — a broken CE lookup must not crash the learn page.
 */
import 'server-only';
import { headers } from 'next/headers';
import { auth } from '@clerk/nextjs/server';
import { getMembershipState, type MembershipStateResult } from '@/lib/chess-empire-member';
import { getStudentProfile } from '@/lib/chess-empire-client';

/**
 * The CE level floor of one membership: a verified/pending roster student's `current_level` (>= 1), else undefined.
 * /learn's floor (below) and the coach's (src/lib/coach/learn-floor.ts) both go through it.
 */
export async function floorFromMembership(membership: MembershipStateResult): Promise<number | undefined> {
  // Only a verified/pending CE roster student gets a floor — online members and coaches never do.
  const isRosterStudent =
    membership.source === 'chess_empire' &&
    membership.role === 'student' &&
    (membership.state === 'verified' || membership.state === 'pending_confirm') &&
    !!membership.studentId;
  if (!isRosterStudent || !membership.studentId) return undefined;

  // The CE profile (best-effort).
  let profile;
  try {
    profile = await getStudentProfile(membership.studentId);
  } catch {
    return undefined;
  }

  // Only a finite level >= 1 is a valid floor.
  const level = profile.current_level;
  if (typeof level === 'number' && Number.isFinite(level) && level >= 1) {
    return level;
  }
  return undefined;
}

export async function resolveCeLevelFloor(): Promise<number | undefined> {
  // 1. Tenant gate — only the chess-empire host carries a level floor.
  const headersList = await headers();
  const orgId = headersList.get('x-org-id');
  const orgSlug = headersList.get('x-org-slug');
  if (!orgId || orgSlug !== 'chess-empire') return undefined;

  // 2. Signed-in Clerk user.
  const { userId } = await auth();
  if (!userId) return undefined;

  // 3. Membership lookup (never throws out).
  let membership;
  try {
    membership = await getMembershipState({ orgId, clerkUserId: userId });
  } catch {
    return undefined;
  }

  // 4–6. A roster student's CE level.
  return floorFromMembership(membership);
}
