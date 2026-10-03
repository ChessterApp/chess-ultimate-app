/**
 * Companion — Watchtower chapter server IO (Phase 4, service-role).
 *
 * The six Watchtower learning nodes (spec §7.3 W01–W06) and the chapter-
 * completion reward. Two surfaces over `supabaseAdmin`:
 *  • loadWatchtower — the chapter view: each node's PUBLIC payload (FEN + prompt
 *    + validator + hint count, NEVER the solution — plan A7) plus which nodes
 *    this owner has already completed, computed server-side from correct
 *    attempts (never a client flag).
 *  • recordLearningNode — judge a node submission (chess.js, server-authoritative)
 *    and persist + (on full completion) grant the chapter reward via ONE
 *    idempotent RPC.
 *
 * Owner-keyed by Clerk owner_user_id (plan A3). Learning is never coin-gated (R1).
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { companionIdempotencyKey } from '@/lib/gamification/companion-rules';
import {
  type PublicTaskPayload,
  type Submission,
  type TaskDefinition,
  judgeSubmission,
  rewardForChapter,
  stableStringify,
  toPublicTask,
} from './assessment';
import { POLICY_VERSION, loadRewardPolicy } from './assessment-service';
import { WATCHTOWER_NODE_FAMILIES, WATCHTOWER_TOTAL_NODES, isWatchtowerNode } from './review-rules';

const TASK_COLS =
  'id,competency_code,family,fen,prompt_en,prompt_ru,prompt_kk,solution,validator,hints';

// ---------------------------------------------------------------------------
// loadWatchtower — the chapter view (public node payloads + completion)
// ---------------------------------------------------------------------------

export interface WatchtowerNode extends PublicTaskPayload {
  node: string;
  completed: boolean;
}

export interface WatchtowerView {
  nodes: WatchtowerNode[];
  completed_count: number;
  total: number;
  chapter_complete: boolean;
}

export async function loadWatchtower(ownerUserId: string): Promise<WatchtowerView> {
  const { data: taskRows } = await supabaseAdmin
    .from('task_definition')
    .select(TASK_COLS)
    .eq('mode', 'learning')
    .eq('active', true)
    .in('family', [...WATCHTOWER_NODE_FAMILIES]);
  const tasks = (taskRows as TaskDefinition[] | null) ?? [];

  // Which node tasks has the owner already answered correctly?
  const taskIds = tasks.map((t) => t.id);
  let completedTaskIds = new Set<string>();
  if (taskIds.length) {
    const { data: attemptRows } = await supabaseAdmin
      .from('task_attempt')
      .select('task_id')
      .eq('owner_user_id', ownerUserId)
      .eq('correct', true)
      .in('task_id', taskIds);
    completedTaskIds = new Set(
      ((attemptRows as { task_id: string }[] | null) ?? []).map((r) => r.task_id),
    );
  }

  const byFamily = new Map(tasks.map((t) => [t.family, t]));
  const nodes: WatchtowerNode[] = WATCHTOWER_NODE_FAMILIES.filter((f) => byFamily.has(f)).map((f) => {
    const task = byFamily.get(f)!;
    // The assignment_id is issued at submit time; the view carries none yet.
    const payload = toPublicTask('', task.competency_code, task);
    return { ...payload, node: f, completed: completedTaskIds.has(task.id) };
  });

  const completedCount = nodes.filter((n) => n.completed).length;
  return {
    nodes,
    completed_count: completedCount,
    total: WATCHTOWER_TOTAL_NODES,
    chapter_complete: completedCount >= WATCHTOWER_TOTAL_NODES,
  };
}

// ---------------------------------------------------------------------------
// recordLearningNode — judge, then persist+reward via one idempotent RPC
// ---------------------------------------------------------------------------

export type RecordLearningNodeResult =
  | {
      status: 'ok' | 'replayed';
      correct: boolean;
      completed_count: number;
      total: number;
      chapter_complete: boolean;
      reward_granted: boolean;
      xp: number;
      coins: number;
    }
  | { status: 'not_found' };

export async function recordLearningNode(params: {
  ownerUserId: string;
  orgId: string;
  studentId: string;
  node: string;
  submission: Submission;
}): Promise<RecordLearningNodeResult> {
  const { ownerUserId, orgId, studentId, node, submission } = params;
  if (!isWatchtowerNode(node)) return { status: 'not_found' };

  const { data: tRow } = await supabaseAdmin
    .from('task_definition')
    .select(TASK_COLS)
    .eq('family', node)
    .eq('mode', 'learning')
    .eq('active', true)
    .maybeSingle();
  const task = tRow as TaskDefinition | null;
  if (!task) return { status: 'not_found' };

  const { correct } = judgeSubmission(task, submission);

  // Issue the learning assignment this attempt is recorded against.
  const { data: inserted, error: insErr } = await supabaseAdmin
    .from('task_assignment')
    .insert({
      owner_user_id: ownerUserId,
      task_id: task.id,
      competency_code: task.competency_code,
      mode: 'learning',
      status: 'issued',
    })
    .select('id')
    .single();
  if (insErr || !inserted) throw insErr ?? new Error('recordLearningNode: insert returned no row');

  // Assignment-independent so a double-submit of the same answer dedups.
  const submissionKey = `companion:learning:${ownerUserId}:${node}:${stableStringify(submission)}`;
  const reward = rewardForChapter(await loadRewardPolicy());
  const rewardKey = companionIdempotencyKey('chapter', ownerUserId, 'watchtower');

  const { data, error } = await supabaseAdmin.rpc('companion_complete_learning_node', {
    p_owner: ownerUserId,
    p_org: orgId,
    p_student: studentId,
    p_assignment: (inserted as { id: string }).id,
    p_task: task.id,
    p_competency: task.competency_code,
    p_submission: submission,
    p_correct: correct,
    p_submission_key: submissionKey,
    p_policy_version: POLICY_VERSION,
    p_total_nodes: WATCHTOWER_TOTAL_NODES,
    p_reward_xp: reward.xp,
    p_reward_coins: reward.coins,
    p_reward_key: rewardKey,
  });
  if (error) throw new Error(error.message);

  const res = (data ?? {}) as Record<string, unknown>;
  return {
    status: (res.status as 'ok' | 'replayed') ?? 'ok',
    correct: !!res.correct,
    completed_count: Number(res.completed_count ?? 0),
    total: Number(res.total ?? WATCHTOWER_TOTAL_NODES),
    chapter_complete: !!res.chapter_complete,
    reward_granted: !!res.reward_granted,
    xp: Number(res.xp ?? 0),
    coins: Number(res.coins ?? 0),
  };
}
