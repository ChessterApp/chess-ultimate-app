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
import EmpireRestrictedHub from '@/components/empire/EmpireRestrictedHub';
import ChessterDashboard from '@/app/dashboard/ChessterDashboard';
import { getMembershipState } from '@/lib/chess-empire-member';
import { autoClaimPendingCookie } from '@/lib/pending-registration';
import { resolveStudentDisplayName } from '@/lib/student-name';
import {
  getStudentProfile,
  getStudentRank,
  getStudentRatings,
  getStudentAchievements,
  getCoachProfile,
  listBranches,
  listActiveStudentsByCoach,
} from '@/lib/chess-empire-client';
import { loadGamificationProfile } from '@/lib/gamification/store';
import { buildCurrentStandings } from '@/lib/gamification/standings-store';
import { type LegionStanding, type StudentProximity, studentProximity } from '@/lib/gamification/standings';
import type { CECoachProfile } from '@/lib/chess-empire-client';
import { computeCoachStats } from '@/lib/empire-coach-stats';

/**
 * Discriminated result of the render pipeline. Splitting the old bare `null`
 * lets the caller (`/dashboard`) tell WHY personalization was skipped and stop
 * masking real failures behind the generic Chesster dashboard on tenant hosts:
 *  - `ok`          → render `node` (verified student / coach / pending_confirm).
 *  - `no_link`     → render `node` (the standard Chesster dashboard wrapped in
 *                    the background poller that auto-upgrades once a link lands).
 *  - `frozen`      → render `node` (the "membership paused" notice). NOT wrapped
 *                    in the poller — re-claiming the invite cannot reactivate a
 *                    frozen membership, so it never enters the claim flow.
 *  - `auth_null`   → no server-side session (stale token / signed-out).
 *  - `lookup_error`→ a required fetch threw; `error` is logged with a stable prefix.
 */
export type EmpireHomeResult =
  | { status: 'ok'; node: React.ReactElement }
  | { status: 'no_link'; node: React.ReactElement }
  | { status: 'frozen'; node: React.ReactElement }
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

  // Server-side auto-claim: if a same-browser sign-up left a `ce_pending_jti`
  // cookie, complete the pending link BEFORE reading membership so a signed-in
  // student never even reaches the waiting screen. Best-effort — the cached
  // membership read below reflects the freshly-written row.
  try {
    await autoClaimPendingCookie(userId);
  } catch (err) {
    console.error('[empire-home] pending auto-claim threw', err);
  }

  let membership;
  try {
    membership = await getMembershipState({ orgId, clerkUserId: userId });
  } catch (err) {
    console.error('[empire-home] member lookup failed', err);
    return { status: 'lookup_error', error: err };
  }

  if (membership.state === 'no_link') {
    // No membership row yet (branch webhook/claim still in flight, or a plain
    // no-invite signup). Serve the standard Chesster dashboard — a fully usable
    // app, not a waiting screen. The client wrapper keeps polling in the
    // background and `router.refresh()`es into the personalized CE homepage the
    // moment a branch link lands; a late webhook still auto-upgrades the user.
    return {
      status: 'no_link',
      node: (
        <EmpireNoLinkClient>
          <ChessterDashboard showTournamentCta />
        </EmpireNoLinkClient>
      ),
    };
  }

  // The school paused this membership. Show the restricted "paused" hub and
  // never wrap the dashboard in the invite poller — re-claiming the invite
  // cannot reactivate a frozen membership, so it must not enter the claim flow.
  if (membership.state === 'frozen') {
    return { status: 'frozen', node: <EmpireRestrictedHub reason="frozen" /> };
  }

  // Time-boxed access ran out (online invite past its window). Show the
  // restricted "trial ended" hub instead of the app — no profile fetch needed.
  if (membership.state === 'expired') {
    return { status: 'ok', node: <EmpireRestrictedHub reason="expired" /> };
  }

  // Online-track members have no Chess Empire roster profile to personalize
  // against, so serve them the standard Chesster app rather than the CE
  // player-card homepage (which would 404 on the synthetic student id).
  if (membership.source === 'online') {
    return { status: 'ok', node: <ChessterDashboard showTournamentCta /> };
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

  const [ratings, rank, gamification, achievements, standingsBundle] = await Promise.all([
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
    loadGamificationProfile(orgId, studentId).catch((err) => {
      console.error('[empire-home] gamification fetch failed', err);
      return null;
    }),
    getStudentAchievements(studentId).catch((err) => {
      console.error('[empire-home] achievements fetch failed', err);
      return [];
    }),
    buildCurrentStandings(orgId).catch((err) => {
      console.error('[empire-home] standings fetch failed', err);
      return null;
    }),
  ]);

  // Caller's own legion standing (§9.2) — members stripped, plus their Top-N
  // proximity. Best-effort: a missing season / unmapped branch leaves it null.
  let legionStanding: Omit<LegionStanding, 'members'> | null = null;
  let topNProximity: StudentProximity | null = null;
  let topN = 5;
  if (standingsBundle) {
    topN = standingsBundle.standings.top_n;
    const prox = studentProximity(standingsBundle.standings, studentId);
    topNProximity = prox;
    if (prox.legion_id) {
      const ls = standingsBundle.standings.legions.find((l) => l.legion.id === prox.legion_id);
      if (ls) {
        const { members, ...rest } = ls;
        void members;
        legionStanding = rest;
      }
    }
  }

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
        gamification={gamification}
        achievements={achievements}
        legionStanding={legionStanding}
        topNProximity={topNProximity}
        topN={topN}
      />
    ),
  };
}
