/**
 * Companion — weekly practice-days goal server IO (Phase 5, service-role).
 *
 * Two surfaces over `supabaseAdmin`:
 *  • loadGoal — the per-owner TARGET (override or policy default) + the CURRENT-
 *    week progress, computed at read time from competency_evidence (owner-keyed).
 *    Returns NO solution/PII — just the day count and target.
 *  • setGoalTarget — persist a user-adjusted target (bounds validated), then
 *    return the refreshed view.
 *
 * Progress is never stored; it is derived each read over the current week, so it
 * resets at the week boundary while earned history remains in competency_evidence
 * (spec line 365). The target default/bounds live in DATA
 * (companion_reward_policy.config.weekly_goal), never hardcoded in a code path.
 *
 * HARD INVARIANT (R2): the weekly goal NEVER gates or unlocks anything and a
 * missed week has no penalty. This module only reads evidence and writes a
 * target; it never touches the ledger, mastery, or any educational path.
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';
import {
  type ActivityRecord,
  type GoalProgress,
  DEFAULT_WEEKLY_GOAL_TARGET,
  clampTarget,
  computeGoalProgress,
  isValidTarget,
  weekStart,
} from './goal-rules';

const POLICY_VERSION = 'hatch-v1';

/** Read the weekly-goal default from the reward policy config (DATA, not code). */
async function loadDefaultTarget(): Promise<number> {
  const { data } = await supabaseAdmin
    .from('companion_reward_policy')
    .select('config')
    .eq('version', POLICY_VERSION)
    .maybeSingle();
  const config = (data as { config?: Record<string, unknown> } | null)?.config ?? {};
  const wg = (config as { weekly_goal?: { default_target?: unknown } }).weekly_goal;
  return clampTarget(wg?.default_target, DEFAULT_WEEKLY_GOAL_TARGET);
}

/**
 * Load the owner's weekly goal: their target (override → policy default) and the
 * current-week meaningful-day progress. Clock injectable so tests move time.
 */
export async function loadGoal(ownerUserId: string, now: Date = new Date()): Promise<GoalProgress> {
  const start = weekStart(now);
  const [goalRes, evidenceRes, defaultTarget] = await Promise.all([
    supabaseAdmin
      .from('companion_weekly_goal')
      .select('target')
      .eq('owner_user_id', ownerUserId)
      .maybeSingle(),
    // Only the current week is needed to compute progress; earned history before
    // weekStart is intentionally not fetched (it is retained, just not counted).
    supabaseAdmin
      .from('competency_evidence')
      .select('kind,created_at')
      .eq('owner_user_id', ownerUserId)
      .gte('created_at', start.toISOString()),
    loadDefaultTarget(),
  ]);

  const stored = (goalRes.data as { target?: number } | null)?.target;
  const activities: ActivityRecord[] = (
    (evidenceRes.data as { kind: string; created_at: string }[] | null) ?? []
  ).map((e) => ({ kind: e.kind, at: e.created_at }));

  return computeGoalProgress({
    target: stored ?? defaultTarget,
    activities,
    now,
    fallbackTarget: defaultTarget,
  });
}

export type SetGoalResult =
  | { status: 'ok'; goal: GoalProgress }
  | { status: 'invalid_target' };

/**
 * Persist a user-adjusted target (validated to the sane 1..7 bounds) and return
 * the refreshed view. Upsert keyed on owner_user_id (one goal row per owner).
 */
export async function setGoalTarget(
  ownerUserId: string,
  target: unknown,
  now: Date = new Date(),
): Promise<SetGoalResult> {
  if (!isValidTarget(target)) return { status: 'invalid_target' };

  const { error } = await supabaseAdmin
    .from('companion_weekly_goal')
    .upsert(
      { owner_user_id: ownerUserId, target: target as number },
      { onConflict: 'owner_user_id' },
    );
  if (error) throw new Error(error.message);

  return { status: 'ok', goal: await loadGoal(ownerUserId, now) };
}
