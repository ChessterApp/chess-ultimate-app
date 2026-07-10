/**
 * Shared render pipeline for the Chess Empire personalized homepage.
 *
 * Used by:
 *  - the apex `/` route when the request lands on
 *    `chess-empire.chesster.io` (tenant landing).
 *  - the `/dashboard` route when the request lands on the same subdomain
 *    (post sign-in destination).
 *
 * The pipeline: read the signed-in Clerk user, resolve their
 * `organization_members` state, fetch the CE profile when we have a linked
 * student, and hand off to `<EmpireHomePage>` with the appropriate state.
 * Every fetch is best-effort — the profile is required (falls back to
 * `null` if it fails so the caller can render a graceful default), the
 * rest degrade individually to an empty result rather than blowing up
 * the page.
 */
import 'server-only';
import { auth } from '@clerk/nextjs/server';
import EmpireHomePage from '@/components/empire/EmpireHomePage';
import EmpireCoachHome from '@/components/empire/EmpireCoachHome';
import EmpireNoLinkClient from '@/components/empire/EmpireNoLinkClient';
import { getMembershipState } from '@/lib/chess-empire-member';
import { resolveStudentDisplayName } from '@/lib/student-name';
import {
  getStudentProfile,
  getStudentRank,
  getStudentRatings,
  getCoachProfile,
} from '@/lib/chess-empire-client';

export async function renderEmpireHomepage(
  orgId: string,
): Promise<React.ReactElement | null> {
  let userId: string | null = null;
  try {
    const session = await auth();
    userId = session.userId ?? null;
  } catch {
    return null;
  }
  if (!userId) return null;

  let membership;
  try {
    membership = await getMembershipState({ orgId, clerkUserId: userId });
  } catch (err) {
    console.error('[empire-home] member lookup failed', err);
    return null;
  }

  if (membership.state === 'no_link') {
    // Client wrapper polls for the async webhook / claim write and refreshes
    // into the personalized page; the static screen is its post-timeout child.
    return (
      <EmpireNoLinkClient>
        <EmpireHomePage state="no_link" studentDisplayName={null} />
      </EmpireNoLinkClient>
    );
  }

  const studentId = membership.studentId;
  if (!studentId) return null;

  // Coaches share the invite flow but live in the CE `coaches` table — the
  // student profile API 404s for them. Render the coach variant instead of
  // silently falling back to the generic dashboard.
  if (membership.role === 'coach') {
    let coachDisplayName: string | null = null;
    try {
      const coach = await getCoachProfile(studentId);
      coachDisplayName =
        `${coach.first_name ?? ''} ${coach.last_name ?? ''}`.trim() || null;
    } catch (err) {
      console.error('[empire-home] coach profile fetch failed', err);
    }
    return <EmpireCoachHome coachDisplayName={coachDisplayName} />;
  }

  let profile;
  try {
    profile = await getStudentProfile(studentId);
  } catch (err) {
    console.error('[empire-home] profile fetch failed', err);
    return null;
  }

  const studentDisplayName = resolveStudentDisplayName(profile);

  if (membership.state === 'pending_confirm') {
    return (
      <EmpireHomePage
        state="pending_confirm"
        studentDisplayName={studentDisplayName}
      />
    );
  }

  const [ratings, rank] = await Promise.all([
    getStudentRatings(studentId, 30).catch((err) => {
      console.error('[empire-home] ratings fetch failed', err);
      return [];
    }),
    getStudentRank(studentId).catch((err) => {
      console.error('[empire-home] rank fetch failed', err);
      return {
        branch_rank: null,
        school_rank: null,
        branch_size: null,
        school_size: null,
      };
    }),
  ]);

  if (!studentDisplayName) {
    console.warn(
      `[empire-home] resolved student ${studentId} has no first_name/full_name — greeting will be name-less`,
    );
  }

  return (
    <EmpireHomePage
      state="verified"
      studentDisplayName={studentDisplayName}
      profile={profile}
      ratings={ratings}
      rank={rank}
      bestSurvivalScore={profile.best_survival_score ?? null}
      bestDefeatedBot={profile.best_defeated_bot ?? null}
    />
  );
}
