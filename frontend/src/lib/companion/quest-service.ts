/**
 * Companion — minimal quest strip server IO (Phase 5, service-role, spec §7.2).
 *
 * The pilot ships exactly ONE quest wrapping the shipped Watchtower chapter
 * (objective = complete W01–W06). Two surfaces over `supabaseAdmin`:
 *  • loadQuests — the quest strip: each active published quest's PUBLIC payload
 *    (copy keys ×3 locales + state + objective progress, NEVER any task solution)
 *    with server-computed state. Reconciles completion on read (idempotent).
 *  • startQuest — available → active (records started_at), then reconciles.
 *
 * Objective completion is computed SERVER-SIDE by reusing the Phase 4 chapter
 * computation (loadWatchtower → distinct correct learning nodes) — a client flag
 * is never trusted. The first-completion reward commits through
 * companion_complete_quest (ONE idempotent RPC) reusing the chapter_first AMOUNT
 * with a distinct companion:quest:<owner>:<quest_version> key, so repeat play
 * regrants nothing.
 *
 * Owner-keyed by Clerk owner_user_id (A3); the RPC bridges owner → (org, student)
 * at the ledger boundary only. Quests are never coin-gated and NEVER gate any
 * educational path (R1/R2).
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { companionIdempotencyKey } from '@/lib/gamification/companion-rules';
import { rewardForChapter } from './assessment';
import { loadRewardPolicy } from './assessment-service';
import { loadWatchtower } from './watchtower-service';
import {
  type QuestState,
  WATCHTOWER_QUEST_ID,
  computeQuestState,
  shouldCommitCompletion,
} from './quest-rules';

const QUEST_COLS =
  'id,version,title_en,title_ru,title_kk,desc_en,desc_ru,desc_kk,region,prerequisites,reward_policy_key,replay_policy,sort_order';

interface QuestDefRow {
  id: string;
  version: number;
  title_en: string;
  title_ru: string;
  title_kk: string;
  desc_en: string;
  desc_ru: string;
  desc_kk: string;
  region: string | null;
  prerequisites: unknown;
  reward_policy_key: string;
  replay_policy: string;
  sort_order: number;
}

interface QuestProgressRow {
  quest_id: string;
  quest_version: number;
  state: QuestState;
  started_at: string | null;
  completed_at: string | null;
}

export interface QuestView {
  id: string;
  version: number;
  title: { en: string; ru: string; kk: string };
  description: { en: string; ru: string; kk: string };
  region: string | null;
  state: QuestState;
  objectives: { done: number; total: number; complete: boolean };
  reward_granted: boolean;
  xp: number;
  coins: number;
}

/** The authoritative objective count for a quest (pilot: Watchtower nodes). */
async function objectiveProgress(
  questId: string,
  ownerUserId: string,
): Promise<{ done: number; total: number }> {
  if (questId === WATCHTOWER_QUEST_ID) {
    const wt = await loadWatchtower(ownerUserId);
    return { done: wt.completed_count, total: wt.total };
  }
  return { done: 0, total: 0 };
}

/** Commit a quest completion through the idempotent RPC (reuses chapter_first). */
async function commitCompletion(
  def: QuestDefRow,
  ownerUserId: string,
  orgId: string,
  studentId: string,
  total: number,
): Promise<{ state: QuestState; reward_granted: boolean; xp: number; coins: number }> {
  // Reuse an existing reward amount (chapter_first) — no new amounts in code.
  const reward = rewardForChapter(await loadRewardPolicy());
  const rewardKey = companionIdempotencyKey('quest', ownerUserId, `${def.id}:v${def.version}`);

  const { data, error } = await supabaseAdmin.rpc('companion_complete_quest', {
    p_owner: ownerUserId,
    p_org: orgId,
    p_student: studentId,
    p_quest_id: def.id,
    p_quest_version: def.version,
    p_total_nodes: total,
    p_reward_xp: reward.xp,
    p_reward_coins: reward.coins,
    p_reward_key: rewardKey,
  });
  if (error) throw new Error(error.message);

  const r = (data ?? {}) as Record<string, unknown>;
  return {
    state: (r.state as QuestState) ?? 'completed',
    reward_granted: !!r.reward_granted,
    xp: Number(r.xp ?? 0),
    coins: Number(r.coins ?? 0),
  };
}

/** Build the public quest view, reconciling completion on read (idempotent). */
async function buildView(
  def: QuestDefRow,
  progress: QuestProgressRow | null,
  ownerUserId: string,
  orgId: string,
  studentId: string,
): Promise<QuestView> {
  const { done, total } = await objectiveProgress(def.id, ownerUserId);
  const prereqs = Array.isArray(def.prerequisites) ? def.prerequisites : [];
  const prerequisitesMet = prereqs.length === 0; // pilot quest has none
  const started = !!progress?.started_at;
  let alreadyCompleted = progress?.state === 'completed';

  let state = computeQuestState({ prerequisitesMet, started, done, total, alreadyCompleted });
  let reward = { reward_granted: false, xp: 0, coins: 0 };

  if (shouldCommitCompletion({ prerequisitesMet, started, done, total, alreadyCompleted })) {
    const r = await commitCompletion(def, ownerUserId, orgId, studentId, total);
    state = r.state;
    alreadyCompleted = state === 'completed';
    reward = { reward_granted: r.reward_granted, xp: r.xp, coins: r.coins };
  }

  return {
    id: def.id,
    version: def.version,
    title: { en: def.title_en, ru: def.title_ru, kk: def.title_kk },
    description: { en: def.desc_en, ru: def.desc_ru, kk: def.desc_kk },
    region: def.region,
    state,
    objectives: { done, total, complete: total > 0 && done >= total },
    ...reward,
  };
}

async function loadProgressMap(ownerUserId: string): Promise<Map<string, QuestProgressRow>> {
  const { data } = await supabaseAdmin
    .from('quest_progress')
    .select('quest_id,quest_version,state,started_at,completed_at')
    .eq('owner_user_id', ownerUserId);
  return new Map(
    ((data as QuestProgressRow[] | null) ?? []).map((p) => [`${p.quest_id}:${p.quest_version}`, p]),
  );
}

/** The quest strip: every active published quest with the owner's state. */
export async function loadQuests(
  ownerUserId: string,
  orgId: string,
  studentId: string,
): Promise<QuestView[]> {
  const { data: defRows } = await supabaseAdmin
    .from('quest_definition')
    .select(QUEST_COLS)
    .eq('active', true)
    .eq('publish_state', 'published')
    .order('sort_order', { ascending: true });
  const defs = (defRows as QuestDefRow[] | null) ?? [];
  if (!defs.length) return [];

  const progress = await loadProgressMap(ownerUserId);
  const views: QuestView[] = [];
  for (const def of defs) {
    const p = progress.get(`${def.id}:${def.version}`) ?? null;
    views.push(await buildView(def, p, ownerUserId, orgId, studentId));
  }
  return views;
}

export type StartQuestResult = { status: 'ok'; quest: QuestView } | { status: 'not_found' };

/** Start a quest: available → active (records started_at), then reconcile. */
export async function startQuest(params: {
  ownerUserId: string;
  orgId: string;
  studentId: string;
  questId: string;
}): Promise<StartQuestResult> {
  const { ownerUserId, orgId, studentId, questId } = params;

  const { data: defRow } = await supabaseAdmin
    .from('quest_definition')
    .select(QUEST_COLS)
    .eq('id', questId)
    .eq('active', true)
    .eq('publish_state', 'published')
    .order('version', { ascending: false })
    .limit(1)
    .maybeSingle();
  const def = defRow as QuestDefRow | null;
  if (!def) return { status: 'not_found' };

  const { data: existingRow } = await supabaseAdmin
    .from('quest_progress')
    .select('quest_id,quest_version,state,started_at,completed_at')
    .eq('owner_user_id', ownerUserId)
    .eq('quest_id', def.id)
    .eq('quest_version', def.version)
    .maybeSingle();
  const existing = existingRow as QuestProgressRow | null;

  if (!existing) {
    // First start: create an active row with started_at.
    await supabaseAdmin.from('quest_progress').insert({
      owner_user_id: ownerUserId,
      quest_id: def.id,
      quest_version: def.version,
      state: 'active',
      started_at: new Date().toISOString(),
    });
  } else if (existing.state !== 'completed') {
    // Re-start an in-progress quest: mark active, backfill started_at.
    await supabaseAdmin
      .from('quest_progress')
      .update({ state: 'active', started_at: existing.started_at ?? new Date().toISOString() })
      .eq('owner_user_id', ownerUserId)
      .eq('quest_id', def.id)
      .eq('quest_version', def.version);
  }

  const progress = await loadProgressMap(ownerUserId);
  const quest = await buildView(
    def,
    progress.get(`${def.id}:${def.version}`) ?? null,
    ownerUserId,
    orgId,
    studentId,
  );
  return { status: 'ok', quest };
}
