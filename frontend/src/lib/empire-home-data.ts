/**
 * Data loader for the Chess Empire personalized homepage.
 *
 * The exact decision tree that `renderEmpireHomepage` used to run inline,
 * returned as a discriminated union so two consumers share one source of
 * truth:
 *  - `renderEmpireHomepage` (the `/` and `/dashboard` server render) maps each
 *    kind to the same nodes as before.
 *  - `GET /api/chess-empire/home` (the mobile app) serializes a trimmed copy.
 *
 * Auth and the pending-cookie auto-claim stay with the callers; this loader
 * starts at the membership lookup. A required fetch failing (membership,
 * missing studentId, student profile) THROWS the original error — callers map
 * it to their `lookup_error` outcome. Every other fetch degrades individually,
 * exactly as before.
 */
import 'server-only';
import { getMembershipState } from '@/lib/chess-empire-member';
import { resolveStudentDisplayName } from '@/lib/student-name';
import {
  getStudentProfile,
  getStudentRank,
  getStudentRatings,
  getStudentAchievements,
  getCoachProfile,
  listBranches,
  listActiveStudentsByCoach,
  type CEAchievement,
  type CEActiveStudent,
  type CECoachProfile,
  type CERatingPoint,
  type CEStudentProfile,
  type CEStudentRank,
} from '@/lib/chess-empire-client';
import { loadGamificationProfile } from '@/lib/gamification/store';
import { buildCurrentStandings } from '@/lib/gamification/standings-store';
import {
  type LegionStanding,
  type StudentProximity,
  studentProximity,
} from '@/lib/gamification/standings';
import type { GamificationProfile } from '@/lib/gamification/profile';
import { computeCoachStats, type CoachHomeStats } from '@/lib/empire-coach-stats';

export interface EmpireCoachHomeData {
  displayName: string | null;
  photoUrl: string | null;
  bio: string | null;
  branchName: string | null;
  stats: CoachHomeStats;
  roster: CEActiveStudent[];
}

export interface EmpireStudentHomeData {
  kind: 'student';
  studentDisplayName: string | null;
  profile: CEStudentProfile;
  ratings: CERatingPoint[];
  rank: CEStudentRank;
  bestSurvivalScore: number | null;
  bestDefeatedBot: CEStudentProfile['best_defeated_bot'] | null;
  gamification: GamificationProfile | null;
  achievements: CEAchievement[];
  legionStanding: Omit<LegionStanding, 'members'> | null;
  topNProximity: StudentProximity | null;
  topN: number;
}

export type EmpireHomeData =
  | { kind: 'no_link' }
  | { kind: 'frozen' }
  | { kind: 'expired' }
  | { kind: 'online' }
  /** `coach: null` — the coach profile fetch failed (name-less greeting). */
  | { kind: 'coach'; coach: EmpireCoachHomeData | null }
  | { kind: 'pending_confirm'; studentDisplayName: string | null }
  | EmpireStudentHomeData;

export async function loadEmpireHomeData(
  orgId: string,
  userId: string,
): Promise<EmpireHomeData> {
  let membership;
  try {
    membership = await getMembershipState({ orgId, clerkUserId: userId });
  } catch (err) {
    console.error('[empire-home] member lookup failed', err);
    throw err;
  }

  // No membership row yet (branch webhook/claim still in flight, or a plain
  // no-invite signup).
  if (membership.state === 'no_link') return { kind: 'no_link' };

  // The school paused this membership — never enters the claim flow.
  if (membership.state === 'frozen') return { kind: 'frozen' };

  // Time-boxed access ran out (online invite past its window).
  if (membership.state === 'expired') return { kind: 'expired' };

  // Online-track members have no Chess Empire roster profile to personalize
  // against (the synthetic student id would 404 on the profile API).
  if (membership.source === 'online') return { kind: 'online' };

  const studentId = membership.studentId;
  if (!studentId) {
    // A verified/pending_confirm row with no external_student_id is a data
    // inconsistency — surface it as a lookup error rather than a blank fallback.
    const error = new Error(
      `membership state ${membership.state} has no studentId`,
    );
    console.error('[empire-home] missing studentId', error);
    throw error;
  }

  // Coaches share the invite flow but live in the CE `coaches` table — the
  // student profile API 404s for them. Checked BEFORE pending_confirm, so a
  // pending coach also gets the coach home.
  if (membership.role === 'coach') {
    let coach: CECoachProfile | null = null;
    try {
      coach = await getCoachProfile(studentId);
    } catch (err) {
      console.error('[empire-home] coach profile fetch failed', err);
    }

    // Profile fetch failed — degrade to the bare name-less coach greeting.
    if (!coach) return { kind: 'coach', coach: null };

    const displayName =
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

    return {
      kind: 'coach',
      coach: {
        displayName,
        photoUrl: coach.photo_url ?? null,
        bio: coach.bio ?? null,
        branchName,
        stats: computeCoachStats(roster),
        roster,
      },
    };
  }

  let profile: CEStudentProfile;
  try {
    profile = await getStudentProfile(studentId);
  } catch (err) {
    console.error('[empire-home] profile fetch failed', err);
    throw err;
  }

  const studentDisplayName = resolveStudentDisplayName(profile);

  if (membership.state === 'pending_confirm') {
    return { kind: 'pending_confirm', studentDisplayName };
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
    kind: 'student',
    studentDisplayName,
    profile,
    ratings,
    rank,
    bestSurvivalScore: profile.best_survival_score ?? null,
    bestDefeatedBot: profile.best_defeated_bot ?? null,
    gamification,
    achievements,
    legionStanding,
    topNProximity,
    topN,
  };
}

/**
 * Trim a loaded home to the JSON the mobile app receives. Drops the fields
 * the page never shows and that must not leave the server: the student's
 * date_of_birth / status / branch_id / coach_id, and every roster row's
 * date_of_birth / status / branch_id / coach_id. Coach e-mail is never loaded
 * into the data shape at all.
 */
export function toEmpireHomeJson(data: EmpireHomeData): Record<string, unknown> {
  if (data.kind === 'coach') {
    if (!data.coach) return { kind: 'coach', coach: null };
    const c = data.coach;
    return {
      kind: 'coach',
      coach: {
        displayName: c.displayName,
        photoUrl: c.photoUrl,
        bio: c.bio,
        branchName: c.branchName,
        stats: c.stats,
        roster: c.roster.map((s) => ({
          id: s.id,
          first_name: s.first_name,
          last_name: s.last_name,
          current_razryad: s.current_razryad ?? null,
          current_league: s.current_league ?? null,
        })),
      },
    };
  }
  if (data.kind === 'student') {
    const p = data.profile;
    return {
      kind: 'student',
      studentDisplayName: data.studentDisplayName,
      profile: {
        first_name: p.first_name,
        last_name: p.last_name,
        photo_url: p.photo_url ?? null,
        branch_name: p.branch_name ?? null,
        coach_name: p.coach_name ?? null,
        current_level: p.current_level ?? null,
        current_lesson: p.current_lesson ?? null,
        total_lessons: p.total_lessons ?? null,
        current_rating: p.current_rating ?? null,
        razryad: p.razryad ?? null,
        current_league: p.current_league ?? null,
        league_tier: p.league_tier ?? null,
        joined_at: p.joined_at ?? null,
      },
      ratings: data.ratings,
      rank: data.rank,
      bestSurvivalScore: data.bestSurvivalScore,
      bestDefeatedBot: data.bestDefeatedBot,
      gamification: data.gamification,
      achievements: data.achievements,
      legionStanding: data.legionStanding,
      topNProximity: data.topNProximity,
      topN: data.topN,
    };
  }
  return { ...data };
}
