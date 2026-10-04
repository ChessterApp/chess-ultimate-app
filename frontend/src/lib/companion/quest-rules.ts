/**
 * Companion — pure, framework-free quest state-machine rules (Phase 5, spec §7.2).
 *
 * The minimal pilot quest wraps the shipped Watchtower chapter: its single
 * objective is "complete all six Watchtower learning nodes". Objective
 * completion is computed SERVER-SIDE from Watchtower evidence (never a client
 * flag) — these helpers only turn that server-computed count into the quest
 * state machine and decide when the first-completion reward may be granted.
 *
 * Quest states (spec §7.2): locked → available → active → objectives_complete →
 * completed. Rewards commit with completion; repeat play cannot regrant the
 * first-completion reward (idempotency enforced at the ledger via a
 * companion:quest:<owner>:<quest_version> key — see companion_complete_quest).
 *
 * HARD INVARIANT (R2): quest state NEVER gates or unlocks an educational path.
 * Watchtower nodes and reviews remain fully playable regardless of quest state;
 * the quest merely observes and rewards. No helper here returns an educational
 * gate. See companion/__tests__/r2-invariant.test.ts.
 *
 * Deterministic + side-effect-free (no DB / Next imports); unit-tested like
 * review-rules.ts. The service-role IO lives in ./quest-service.ts.
 */

/** The one seeded pilot quest id (migration 048). */
export const WATCHTOWER_QUEST_ID = 'watchtower';

export type QuestState =
  | 'locked'
  | 'available'
  | 'active'
  | 'objectives_complete'
  | 'completed';

/** Canonical ordering (spec §7.2) — used only for display/progress, never gating. */
export const QUEST_STATE_ORDER: readonly QuestState[] = [
  'locked',
  'available',
  'active',
  'objectives_complete',
  'completed',
] as const;

/** Objectives are complete when every required node has a correct attempt. */
export function objectivesComplete(done: number, total: number): boolean {
  return total > 0 && done >= total;
}

export interface QuestStateInput {
  /** All prerequisite quests satisfied (the pilot quest has none ⇒ true). */
  prerequisitesMet: boolean;
  /** The owner has started the quest (quest_progress exists with started_at). */
  started: boolean;
  /** Distinct objective items completed, from server-computed evidence. */
  done: number;
  /** Total objective items required. */
  total: number;
  /** The quest has already been committed as completed (idempotent terminal). */
  alreadyCompleted: boolean;
}

/**
 * Derive the current quest state from server-authoritative inputs. `completed`
 * is terminal (idempotent); otherwise an unstarted-but-unlocked quest is
 * `available`, a started quest is `objectives_complete` once its objectives are
 * met and `active` until then, and a quest with unmet prerequisites is `locked`.
 */
export function computeQuestState(i: QuestStateInput): QuestState {
  if (i.alreadyCompleted) return 'completed';
  if (!i.prerequisitesMet) return 'locked';
  if (!i.started) return 'available';
  return objectivesComplete(i.done, i.total) ? 'objectives_complete' : 'active';
}

/**
 * Whether the first-completion reward should be committed now: the quest is
 * started, its objectives are met, and it has not already been completed. The
 * ledger idempotency key is the ultimate guard, but this avoids a redundant RPC
 * call on every read once a quest is done.
 */
export function shouldCommitCompletion(i: QuestStateInput): boolean {
  return i.started && !i.alreadyCompleted && objectivesComplete(i.done, i.total);
}
