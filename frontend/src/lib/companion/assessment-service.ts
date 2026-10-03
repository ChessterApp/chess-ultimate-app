/**
 * Companion — assessment pipeline server IO (Phase 2, service-role).
 *
 * Server-authoritative glue over `supabaseAdmin` for the three assessment
 * routes: issue an assignment (FEN + prompt, NO solution), record an attempt
 * (judge → ONE idempotent RPC that writes evidence + mastery + reward), and log
 * a hint (flip assistance BEFORE revealing content). Owner-keyed by Clerk
 * `owner_user_id` (plan A3); the RPC bridges owner → (org, student) at the
 * ledger boundary only. Nothing here is coin-gated — reading/attempting a lesson
 * is always free (R1).
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { companionIdempotencyKey } from '@/lib/gamification/companion-rules';
import { MASTERY_TARGET_CORRECT } from './state';
import {
  type PublicTaskPayload,
  type Submission,
  type TaskDefinition,
  deriveSubmissionKey,
  judgeSubmission,
  normalizeRewardPolicy,
  pickAssessmentTask,
  rewardForCompetencyPass,
  toPublicTask,
} from './assessment';

/** The reward-policy version this phase writes onto every evidence row. */
export const POLICY_VERSION = 'hatch-v1';

const TASK_COLS =
  'id,competency_code,family,fen,prompt_en,prompt_ru,prompt_kk,solution,validator,hints';

// ---------------------------------------------------------------------------
// Reward policy (data, not code) — read the versioned row, fall back to the
// documented default only if the seed row is missing (mirrors economy config).
// ---------------------------------------------------------------------------
async function loadRewardPolicy() {
  const { data } = await supabaseAdmin
    .from('companion_reward_policy')
    .select('config')
    .eq('version', POLICY_VERSION)
    .maybeSingle();
  return normalizeRewardPolicy((data as { config?: unknown } | null)?.config);
}

// ---------------------------------------------------------------------------
// createAssignment — issue a fresh assessment instance for a competency
// ---------------------------------------------------------------------------

export type CreateAssignmentResult =
  | { status: 'ok'; task: PublicTaskPayload }
  | { status: 'no_tasks' };

export async function createAssignment(
  ownerUserId: string,
  competency: string,
): Promise<CreateAssignmentResult> {
  const { data: taskRows } = await supabaseAdmin
    .from('task_definition')
    .select(TASK_COLS)
    .eq('competency_code', competency)
    .eq('mode', 'assessment')
    .eq('active', true);

  const tasks = (taskRows as TaskDefinition[] | null) ?? [];
  if (!tasks.length) return { status: 'no_tasks' };

  // Rotate by how many assignments the owner already has for this competency,
  // and avoid the most recent few task instances (fresh retries, §4.2).
  const { data: priorRows } = await supabaseAdmin
    .from('task_assignment')
    .select('task_id,issued_at')
    .eq('owner_user_id', ownerUserId)
    .eq('competency_code', competency)
    .order('issued_at', { ascending: false })
    .limit(10);
  const prior = (priorRows as { task_id: string }[] | null) ?? [];
  const recentTaskIds = prior.slice(0, 3).map((r) => r.task_id);

  const task = pickAssessmentTask(tasks, recentTaskIds, prior.length);
  if (!task) return { status: 'no_tasks' };

  const { data: inserted, error } = await supabaseAdmin
    .from('task_assignment')
    .insert({
      owner_user_id: ownerUserId,
      task_id: task.id,
      competency_code: competency,
      mode: 'assessment',
      status: 'issued',
    })
    .select('id')
    .single();
  if (error || !inserted) throw error ?? new Error('createAssignment: insert returned no row');

  return { status: 'ok', task: toPublicTask((inserted as { id: string }).id, competency, task) };
}

// ---------------------------------------------------------------------------
// recordAttempt — judge, then persist+reward via one idempotent RPC
// ---------------------------------------------------------------------------

interface AssignmentRow {
  id: string;
  owner_user_id: string;
  task_id: string;
  competency_code: string;
  mode: string;
  assistance_used: boolean;
}

export type RecordAttemptResult =
  | {
      status: 'ok' | 'replayed';
      correct: boolean;
      assistance_used: boolean;
      demonstrated: boolean;
      times_correct: number;
      reward_granted: boolean;
      xp: number;
      coins: number;
    }
  | { status: 'not_found' }
  | { status: 'invalid_mode' };

export async function recordAttempt(params: {
  ownerUserId: string;
  orgId: string;
  studentId: string;
  assignmentId: string;
  submission: Submission;
  assistanceUsed?: boolean;
}): Promise<RecordAttemptResult> {
  const { ownerUserId, orgId, studentId, assignmentId, submission } = params;

  const { data: aRow } = await supabaseAdmin
    .from('task_assignment')
    .select('id,owner_user_id,task_id,competency_code,mode,assistance_used')
    .eq('id', assignmentId)
    .eq('owner_user_id', ownerUserId)
    .maybeSingle();
  const assignment = aRow as AssignmentRow | null;
  if (!assignment) return { status: 'not_found' };
  if (assignment.mode !== 'assessment') return { status: 'invalid_mode' };

  const { data: tRow } = await supabaseAdmin
    .from('task_definition')
    .select(TASK_COLS)
    .eq('id', assignment.task_id)
    .maybeSingle();
  const task = tRow as TaskDefinition | null;
  if (!task) return { status: 'not_found' };

  const { correct } = judgeSubmission(task, submission);

  // Assistance is server-authoritative: a hint on this assignment (persisted) or
  // a client-asserted true both count; the RPC also folds in "not first response"
  // so a client can never downgrade assistance to false (spec §4.3, §12.3).
  const assistanceUsed = assignment.assistance_used === true || params.assistanceUsed === true;

  const submissionKey = deriveSubmissionKey(ownerUserId, assignmentId, submission);
  const reward = rewardForCompetencyPass(await loadRewardPolicy());
  const rewardKey = companionIdempotencyKey('competency_pass', ownerUserId, assignment.competency_code);

  const { data, error } = await supabaseAdmin.rpc('companion_record_attempt', {
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
    p_mastery_target: MASTERY_TARGET_CORRECT,
    p_reward_xp: reward.xp,
    p_reward_coins: reward.coins,
    p_reward_key: rewardKey,
  });
  if (error) throw new Error(error.message);

  const r = (data ?? {}) as Record<string, unknown>;
  return {
    status: (r.status as 'ok' | 'replayed') ?? 'ok',
    correct: !!r.correct,
    assistance_used: !!r.assistance_used,
    demonstrated: !!r.demonstrated,
    times_correct: Number(r.times_correct ?? 0),
    reward_granted: !!r.reward_granted,
    xp: Number(r.xp ?? 0),
    coins: Number(r.coins ?? 0),
  };
}

// ---------------------------------------------------------------------------
// logHint — mark assistance BEFORE revealing a hint, then return its content
// ---------------------------------------------------------------------------

export type LogHintResult =
  | {
      status: 'ok';
      assistance_used: true;
      hint_index: number;
      hints_total: number;
      hint: { en: string; ru: string; kk: string } | null;
    }
  | { status: 'not_found' };

export async function logHint(
  ownerUserId: string,
  assignmentId: string,
  hintIndex: number,
): Promise<LogHintResult> {
  const { data: aRow } = await supabaseAdmin
    .from('task_assignment')
    .select('id,task_id')
    .eq('id', assignmentId)
    .eq('owner_user_id', ownerUserId)
    .maybeSingle();
  const assignment = aRow as { id: string; task_id: string } | null;
  if (!assignment) return { status: 'not_found' };

  // Record assistance FIRST — a crash after this must leave assistance set, never
  // leak a hint that was not accounted for (spec §12.3: persist before returning).
  const { error: updErr } = await supabaseAdmin
    .from('task_assignment')
    .update({ assistance_used: true })
    .eq('id', assignmentId)
    .eq('owner_user_id', ownerUserId);
  if (updErr) throw new Error(updErr.message);

  const { data: tRow } = await supabaseAdmin
    .from('task_definition')
    .select('hints')
    .eq('id', assignment.task_id)
    .maybeSingle();
  const hints = ((tRow as { hints?: unknown } | null)?.hints as TaskDefinition['hints']) ?? [];

  const total = hints.length;
  const idx = Number.isFinite(hintIndex) ? Math.max(0, Math.min(Math.floor(hintIndex), total - 1)) : 0;
  return {
    status: 'ok',
    assistance_used: true,
    hint_index: idx,
    hints_total: total,
    hint: total > 0 ? hints[idx] : null,
  };
}
