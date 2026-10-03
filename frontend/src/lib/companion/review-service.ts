/**
 * Companion — pull-based SM-2 review server IO (Phase 4, service-role).
 *
 * Two surfaces over `supabaseAdmin`:
 *  • loadDueReviews — the read-time "due" queue (plan A4, ported from
 *    backend/api/openings.py:1764 `get_due_nodes`): competencies the owner has a
 *    mastery_state row for whose next_review_at <= now OR is null. Returns review
 *    items WITHOUT any solution fields.
 *  • recordReview — judge a review submission (chess.js, server-authoritative),
 *    advance the FIXED ladder (1/3/7/14 — values from DATA, clock injectable),
 *    and persist + grant the due_review reward via ONE idempotent RPC.
 *
 * Owner-keyed by Clerk owner_user_id (plan A3); the RPC bridges owner →
 * (org, student) at the ledger boundary only. Reviewing is never coin-gated (R1).
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { companionIdempotencyKey } from '@/lib/gamification/companion-rules';
import {
  type Submission,
  type TaskDefinition,
  deriveSubmissionKey,
  judgeSubmission,
  normalizeRewardPolicy,
  rewardForDueReview,
} from './assessment';
import {
  dueMarker,
  isDue,
  normalizeLadder,
  rungForInterval,
  scheduleReview,
} from './review-rules';

/** The reward-policy version this phase writes onto every evidence row. */
export const POLICY_VERSION = 'hatch-v1';

const TASK_COLS =
  'id,competency_code,family,fen,prompt_en,prompt_ru,prompt_kk,solution,validator,hints';

// ---------------------------------------------------------------------------
// Reward policy + ladder (data, not code).
// ---------------------------------------------------------------------------
async function loadPolicyConfig(): Promise<Record<string, unknown>> {
  const { data } = await supabaseAdmin
    .from('companion_reward_policy')
    .select('config')
    .eq('version', POLICY_VERSION)
    .maybeSingle();
  const config = (data as { config?: unknown } | null)?.config;
  return config && typeof config === 'object' ? (config as Record<string, unknown>) : {};
}

// ---------------------------------------------------------------------------
// loadDueReviews — the pull-based due queue (NO solution fields)
// ---------------------------------------------------------------------------

export interface DueReviewItem {
  competency: string;
  title_en: string;
  title_ru: string;
  title_kk: string;
  /** 1-based ladder rung (0 = never reviewed yet). */
  rung: number;
  interval_days: number;
  next_review_at: string | null;
}

export async function loadDueReviews(
  ownerUserId: string,
  now: Date = new Date(),
): Promise<DueReviewItem[]> {
  const [masteryRes, ladderConfig] = await Promise.all([
    supabaseAdmin
      .from('mastery_state')
      .select('competency_code,interval_days,next_review_at')
      .eq('owner_user_id', ownerUserId),
    loadPolicyConfig(),
  ]);

  const mastery =
    (masteryRes.data as
      | { competency_code: string; interval_days: number; next_review_at: string | null }[]
      | null) ?? [];
  const due = mastery.filter((m) => isDue(m.next_review_at, now));
  if (!due.length) return [];

  const ladder = normalizeLadder((ladderConfig as { review_ladder?: unknown }).review_ladder);

  // Titles + active-competency filter from the public catalog.
  const { data: defRows } = await supabaseAdmin
    .from('competency_definition')
    .select('code,title_en,title_ru,title_kk,sort_order')
    .eq('active', true)
    .in(
      'code',
      due.map((d) => d.competency_code),
    );
  const defs = new Map(
    ((defRows as
      | { code: string; title_en: string; title_ru: string; title_kk: string; sort_order: number }[]
      | null) ?? []
    ).map((d) => [d.code, d]),
  );

  return due
    .filter((m) => defs.has(m.competency_code))
    .map((m) => {
      const def = defs.get(m.competency_code)!;
      return {
        competency: m.competency_code,
        title_en: def.title_en,
        title_ru: def.title_ru,
        title_kk: def.title_kk,
        rung: rungForInterval(m.interval_days ?? 0, ladder),
        interval_days: m.interval_days ?? 0,
        next_review_at: m.next_review_at,
      };
    })
    .sort((a, b) => a.competency.localeCompare(b.competency));
}

// ---------------------------------------------------------------------------
// recordReview — judge, advance the ladder, persist+reward via one RPC
// ---------------------------------------------------------------------------

interface AssignmentRow {
  id: string;
  owner_user_id: string;
  task_id: string;
  competency_code: string;
  mode: string;
  assistance_used: boolean;
}

export type RecordReviewResult =
  | {
      status: 'ok' | 'replayed';
      correct: boolean;
      assistance_used: boolean;
      interval_days: number;
      next_review_at: string | null;
      times_correct: number;
      reward_granted: boolean;
      xp: number;
      coins: number;
    }
  | { status: 'not_found' }
  | { status: 'invalid_mode' };

export async function recordReview(params: {
  ownerUserId: string;
  orgId: string;
  studentId: string;
  assignmentId: string;
  submission: Submission;
  assistanceUsed?: boolean;
  now?: Date;
}): Promise<RecordReviewResult> {
  const { ownerUserId, orgId, studentId, assignmentId, submission } = params;
  const now = params.now ?? new Date();

  const { data: aRow } = await supabaseAdmin
    .from('task_assignment')
    .select('id,owner_user_id,task_id,competency_code,mode,assistance_used')
    .eq('id', assignmentId)
    .eq('owner_user_id', ownerUserId)
    .maybeSingle();
  const assignment = aRow as AssignmentRow | null;
  if (!assignment) return { status: 'not_found' };
  if (assignment.mode !== 'review') return { status: 'invalid_mode' };

  const { data: tRow } = await supabaseAdmin
    .from('task_definition')
    .select(TASK_COLS)
    .eq('id', assignment.task_id)
    .maybeSingle();
  const task = tRow as TaskDefinition | null;
  if (!task) return { status: 'not_found' };

  const { correct } = judgeSubmission(task, submission);

  // Assistance is server-authoritative (a hint on this assignment OR a client
  // assertion). An assisted review never earns the reward and resets the rung.
  const assistanceUsed = assignment.assistance_used === true || params.assistanceUsed === true;

  // Current rung → next rung (clock injected so tests can advance time).
  const config = await loadPolicyConfig();
  const ladder = normalizeLadder((config as { review_ladder?: unknown }).review_ladder);
  const { data: msRow } = await supabaseAdmin
    .from('mastery_state')
    .select('interval_days,next_review_at')
    .eq('owner_user_id', ownerUserId)
    .eq('competency_code', assignment.competency_code)
    .maybeSingle();
  const current = (msRow as { interval_days: number; next_review_at: string | null } | null) ?? {
    interval_days: 0,
    next_review_at: null,
  };
  const passed = correct && !assistanceUsed;
  const schedule = scheduleReview({
    intervalDays: current.interval_days ?? 0,
    correct: passed,
    now,
    ladder,
  });

  const reward = rewardForDueReview(normalizeRewardPolicy(config));
  const submissionKey = deriveSubmissionKey(ownerUserId, assignmentId, submission);
  const rewardKey = companionIdempotencyKey(
    'review',
    ownerUserId,
    `${assignment.competency_code}:${dueMarker(current.next_review_at)}`,
  );

  const { data, error } = await supabaseAdmin.rpc('companion_record_review', {
    p_owner: ownerUserId,
    p_org: orgId,
    p_student: studentId,
    p_assignment: assignmentId,
    p_task: assignment.task_id,
    p_competency: assignment.competency_code,
    p_submission: submission,
    p_correct: correct,
    p_assistance_used: assistanceUsed,
    p_submission_key: submissionKey,
    p_policy_version: POLICY_VERSION,
    p_interval_days: schedule.intervalDays,
    p_next_review_at: schedule.nextReviewAt,
    p_reward_xp: reward.xp,
    p_reward_coins: reward.coins,
    p_reward_key: rewardKey,
  });
  if (error) throw new Error(error.message);

  const res = (data ?? {}) as Record<string, unknown>;
  return {
    status: (res.status as 'ok' | 'replayed') ?? 'ok',
    correct: !!res.correct,
    assistance_used: !!res.assistance_used,
    interval_days: Number(res.interval_days ?? schedule.intervalDays),
    next_review_at: (res.next_review_at as string | null) ?? schedule.nextReviewAt,
    times_correct: Number(res.times_correct ?? 0),
    reward_granted: !!res.reward_granted,
    xp: Number(res.xp ?? 0),
    coins: Number(res.coins ?? 0),
  };
}
