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
  listBranches,
  listActiveStudentsByCoach,
} from '@/lib/chess-empire-client';
import type { CECoachProfile } from '@/lib/chess-empire-client';
import { computeCoachStats } from '@/lib/empire-coach-stats';

/**
 * Discriminated result of the render pipeline. Splitting the old bare `null`
 * lets the caller (`/dashboard`) tell WHY personalization was skipped and stop
 * masking real failures behind the generic Chesster dashboard on tenant hosts:
 *  - `ok`          → render `node` (verified student / coach / pending_confirm).
 *  - `no_link`     → render `node` (the poller + "profile getting ready" screen).
 *  - `auth_null`   → no server-side session (stale token / signed-out).
 *  - `lookup_error`→ a required fetch threw; `error` is logged with a stable prefix.
 */
export type EmpireHomeResult =
  | { status: 'ok'; node: React.ReactElement }
  | { status: 'no_link'; node: React.ReactElement }
  | { status: 'auth_null' }
  | { status: 'lookup_error'; error: unknown };

export async function renderEmpireHomepage(
  orgId: string,
): Promise<EmpireHomeResult> {
  let userId: string | null = null;
  try {
    const session = await auth();
    userId = session.userId ?? null;
  } catch (err) {
    console.error('[empire-home] auth() threw', err);
    return { status: 'auth_null' };
  }
  if (!userId) return { status: 'auth_null' };

  let membership;
  try {
    membership = await getMembershipState({ orgId, clerkUserId: userId });
  } catch (err) {
    console.error('[empire-home] member lookup failed', err);
    return { status: 'lookup_error', error: err };
  }

  if (membership.state === 'no_link') {
    // Client wrapper polls for the async webhook / claim write and refreshes
    // into the personalized page; the static screen is its post-timeout child.
    return {
      status: 'no_link',
      node: (
        <EmpireNoLinkClient>
          <EmpireHomePage state="no_link" studentDisplayName={null} />
        </EmpireNoLinkClient>
      ),
    };
  }

  const studentId = membership.studentId;
  if (!studentId) {
    // A verified/pending_confirm row with no external_student_id is a data
    // inconsistency — surface it as a lookup error rather than a blank fallback.
    const error = new Error(
      `membership state ${membership.state} has no studentId`,
    );
    console.error('[empire-home] missing studentId', error);
    return { status: 'lookup_error', error };
  }

  // Coaches share the invite flow but live in the CE `coaches` table — the
  // student profile API 404s for them. Render the coach variant instead of
  // silently falling back to the generic dashboard.
  if (membership.role === 'coach') {
    let coach: CECoachProfile | null = null;
    try {
      coach = await getCoachProfile(studentId);
    } catch (err) {
      console.error('[empire-home] coach profile fetch failed', err);
    }

    // Profile fetch failed — degrade to the bare name-less coach greeting.
    if (!coach) {
      return { status: 'ok', node: <EmpireCoachHome coachDisplayName={null} /> };
    }

    const coachDisplayName =
      `${coach.first_name ?? ''} ${coach.last_name ?? ''}`.trim() || null;

    // Branch name + own roster are best-effort: either failing leaves the
    // coach home with an empty state rather than breaking the page.
    const [branches, roster] = await Promise.all([
      listBranches().catch((err) => {
        console.error('[empire-home] coach branches fetch failed', err);
        return [];
      }),
      listActiveStudentsByCoach(coach.id).catch((err) => {
        console.error('[empire-home] coach roster fetch failed', err);
        return [];
      }),
    ]);

    const branchName =
      branches.find((b) => b.id === coach!.branch_id)?.name ?? null;
    const stats = computeCoachStats(roster);

    return {
      status: 'ok',
      node: (
        <EmpireCoachHome
          coachDisplayName={coachDisplayName}
          photoUrl={coach.photo_url ?? null}
          bio={coach.bio ?? null}
          branchName={branchName}
          stats={stats}
          roster={roster}
        />
      ),
    };
  }

  let profile;
  try {
    profile = await getStudentProfile(studentId);
  } catch (err) {
    console.error('[empire-home] profile fetch failed', err);
    return { status: 'lookup_error', error: err };
  }

  const studentDisplayName = resolveStudentDisplayName(profile);

  if (membership.state === 'pending_confirm') {
    return {
      status: 'ok',
      node: (
        <EmpireHomePage
          state="pending_confirm"
          studentDisplayName={studentDisplayName}
        />
      ),
    };
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

  return {
    status: 'ok',
    node: (
      <EmpireHomePage
        state="verified"
        studentDisplayName={studentDisplayName}
        profile={profile}
        ratings={ratings}
        rank={rank}
        bestSurvivalScore={profile.best_survival_score ?? null}
        bestDefeatedBot={profile.best_defeated_bot ?? null}
      />
    ),
  };
}
