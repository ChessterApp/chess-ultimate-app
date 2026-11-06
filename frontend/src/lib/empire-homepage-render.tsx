/**
 * Shared render pipeline for the Chess Empire personalized homepage.
 *
 * Used by:
 *  - the apex `/` route when the request lands on
 *    `chess-empire.chesster.io` (tenant landing).
 *  - the `/dashboard` route when the request lands on the same subdomain
 *    (post sign-in destination).
 *
 * The pipeline: read the signed-in Clerk user, auto-claim a pending cookie,
 * then `loadEmpireHomeData` (lib/empire-home-data.ts — shared with the
 * `GET /api/chess-empire/home` JSON route) resolves the membership and fetches
 * the CE data; this file only maps each loaded kind to its node.
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
import { resolveLearnCeiling } from '@/lib/learn-ceiling-server';
import { autoClaimPendingCookie } from '@/lib/pending-registration';
import { loadEmpireHomeData } from '@/lib/empire-home-data';

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

/**
 * Level-complete framing for the restricted Home hub. When the member's current
 * level (their Learn ceiling) is already 100% complete, surface "Level N
 * complete — continue with Level N+1". Best-effort: any gap resolves to `{}`,
 * leaving the hub's default "Learn stays open" copy.
 */
async function resolveRestrictedHubProps(): Promise<{
  currentLevel?: number;
  currentLevelComplete?: boolean;
  nextLevelTitle?: string | null;
}> {
  const { ceiling, courses } = await resolveLearnCeiling();
  if (ceiling === undefined) return {};
  const current = courses.find((c) => c.position === ceiling);
  if (!current || current.progress !== 100) return {};
  const next = courses.find((c) => c.position === ceiling + 1) ?? null;
  return {
    currentLevel: ceiling,
    currentLevelComplete: true,
    nextLevelTitle: next?.title ?? null,
  };
}

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

  let data;
  try {
    data = await loadEmpireHomeData(orgId, userId);
  } catch (err) {
    // The loader already logged the failing step with a stable prefix.
    return { status: 'lookup_error', error: err };
  }

  switch (data.kind) {
    case 'no_link':
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

    case 'frozen': {
      // The school paused this membership. Show the restricted "paused" hub and
      // never wrap the dashboard in the invite poller — re-claiming the invite
      // cannot reactivate a frozen membership, so it must not enter the claim flow.
      const hub = await resolveRestrictedHubProps();
      return { status: 'frozen', node: <EmpireRestrictedHub reason="frozen" {...hub} /> };
    }

    case 'expired': {
      // Time-boxed access ran out (online invite past its window). Show the
      // restricted "trial ended" hub instead of the app — no profile fetch needed.
      const hub = await resolveRestrictedHubProps();
      return { status: 'ok', node: <EmpireRestrictedHub reason="expired" {...hub} /> };
    }

    case 'online':
      // Online-track members have no Chess Empire roster profile to personalize
      // against, so serve them the standard Chesster app rather than the CE
      // player-card homepage (which would 404 on the synthetic student id).
      return { status: 'ok', node: <ChessterDashboard showTournamentCta /> };

    case 'coach': {
      // Profile fetch failed — degrade to the bare name-less coach greeting.
      if (!data.coach) {
        return { status: 'ok', node: <EmpireCoachHome coachDisplayName={null} /> };
      }
      const coach = data.coach;
      return {
        status: 'ok',
        node: (
          <EmpireCoachHome
            coachDisplayName={coach.displayName}
            photoUrl={coach.photoUrl}
            bio={coach.bio}
            branchName={coach.branchName}
            stats={coach.stats}
            roster={coach.roster}
          />
        ),
      };
    }

    case 'pending_confirm':
      return {
        status: 'ok',
        node: (
          <EmpireHomePage
            state="pending_confirm"
            studentDisplayName={data.studentDisplayName}
          />
        ),
      };

    case 'student':
      return {
        status: 'ok',
        node: (
          <EmpireHomePage
            state="verified"
            studentDisplayName={data.studentDisplayName}
            profile={data.profile}
            ratings={data.ratings}
            rank={data.rank}
            bestSurvivalScore={data.bestSurvivalScore}
            bestDefeatedBot={data.bestDefeatedBot}
            gamification={data.gamification}
            achievements={data.achievements}
            legionStanding={data.legionStanding}
            topNProximity={data.topNProximity}
            topN={data.topN}
          />
        ),
      };
  }
}
