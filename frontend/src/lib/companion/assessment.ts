/**
 * Companion — pure assessment rules (Phase 2).
 *
 * Deterministic, side-effect-free helpers for the assessment pipeline: task
 * selection, server-side answer judging (chess.js legality for move tasks, exact
 * placement match for board-assembly tasks), the public (solution-free) task
 * payload, the submission idempotency key, and the versioned reward policy.
 *
 * No DB / Next imports, so this unit-tests without a database — mirroring
 * economy.ts / state.ts. The service-role IO that feeds these lives in
 * ./assessment-service.ts.
 *
 * HARD RULE (plan A7): a task's `solution` and raw `hints` never leave the
 * server inside an assignment payload — see toPublicTask().
 */
import { applyMove } from '@/lib/live-game/validate';

// ---------------------------------------------------------------------------
// Task shape (the server-only task_definition row, subset used by the rules)
// ---------------------------------------------------------------------------

/** A validator kind. `move` replays via chess.js; `setup` compares placement. */
export type ValidatorKind = 'move' | 'setup';

export interface TaskDefinition {
  id: string;
  competency_code: string;
  family: string;
  fen: string;
  prompt_en: string;
  prompt_ru: string;
  prompt_kk: string;
  /** Answer key — NEVER sent to the client. */
  solution: TaskSolution;
  validator: ValidatorKind | string;
  /** Ordered hints (localized objects). Revealed one at a time via /hints. */
  hints: TaskHint[];
}

export interface TaskHint {
  en: string;
  ru: string;
  kk: string;
}

/** Move tasks accept a set of UCI moves; setup tasks match a placement field. */
export interface TaskSolution {
  moves?: string[];
  placement?: string;
}

/** The submission a client may send (shape depends on the validator). */
export interface Submission {
  uci?: string;
  placement?: string;
  fen?: string;
}

// ---------------------------------------------------------------------------
// Public (solution-free) assignment payload
// ---------------------------------------------------------------------------

export interface PublicTaskPayload {
  assignment_id: string;
  competency: string;
  family: string;
  fen: string;
  prompt: { en: string; ru: string; kk: string };
  validator: string;
  /** How many hints exist — the content is fetched one at a time via /hints. */
  hints_total: number;
}

/**
 * Assemble the payload the assignment route returns. Contains the FEN + prompt
 * only — NEVER the solution or hint content (plan A7 hard rule). Only the hint
 * COUNT is exposed so the UI can render a "hint" affordance.
 */
export function toPublicTask(
  assignmentId: string,
  competency: string,
  task: TaskDefinition,
): PublicTaskPayload {
  return {
    assignment_id: assignmentId,
    competency,
    family: task.family,
    fen: task.fen,
    prompt: { en: task.prompt_en, ru: task.prompt_ru, kk: task.prompt_kk },
    validator: task.validator,
    hints_total: Array.isArray(task.hints) ? task.hints.length : 0,
  };
}

// ---------------------------------------------------------------------------
// Task selection
// ---------------------------------------------------------------------------

/**
 * Pick one assessment task for a competency. Prefers a task NOT in `recentTaskIds`
 * (fresh retries, spec §4.2) and rotates deterministically by `rotate` (e.g. the
 * owner's prior attempt count) so repeat calls cycle through the pool rather than
 * always returning the first instance. Returns null when the pool is empty.
 */
export function pickAssessmentTask(
  tasks: TaskDefinition[],
  recentTaskIds: string[] = [],
  rotate = 0,
): TaskDefinition | null {
  if (!tasks.length) return null;
  const recent = new Set(recentTaskIds);
  const fresh = tasks.filter((t) => !recent.has(t.id));
  const pool = fresh.length ? fresh : tasks; // all seen ⇒ fall back to full pool
  const idx = ((rotate % pool.length) + pool.length) % pool.length;
  return pool[idx];
}

// ---------------------------------------------------------------------------
// Judging (server-authoritative; the client's position is never trusted)
// ---------------------------------------------------------------------------

export interface Judgement {
  correct: boolean;
  /** Why it was rejected (never leaks the answer): illegal_move | wrong | malformed. */
  reason?: string;
}

/** Piece-placement field of a FEN, trimmed (case-sensitive: upper = white). */
function placementField(s: string): string {
  return (s ?? '').trim().split(/\s+/)[0] ?? '';
}

/**
 * Judge a submission against a task's solution. Pure + deterministic:
 *  - `move`:  the UCI must be LEGAL from the task FEN (chess.js) AND in the
 *             accepted-move set. Legality first means an illegal move can never
 *             be scored correct even if it were (mistakenly) listed.
 *  - `setup`: the submitted piece-placement must exactly match the solution.
 */
export function judgeSubmission(task: TaskDefinition, submission: Submission): Judgement {
  if (task.validator === 'setup') {
    const want = placementField(task.solution?.placement ?? '');
    const got = placementField(submission?.placement ?? submission?.fen ?? '');
    if (!want) return { correct: false, reason: 'malformed' };
    if (!got) return { correct: false, reason: 'malformed' };
    return { correct: got === want, reason: got === want ? undefined : 'wrong' };
  }

  // Default: move validator.
  const uci = typeof submission?.uci === 'string' ? submission.uci.trim().toLowerCase() : '';
  if (!uci) return { correct: false, reason: 'malformed' };
  const accepted = (task.solution?.moves ?? []).map((m) => m.toLowerCase());
  const applied = applyMove(task.fen, uci);
  if (!applied.ok) return { correct: false, reason: 'illegal_move' };
  return accepted.includes(uci)
    ? { correct: true }
    : { correct: false, reason: 'wrong' };
}

// ---------------------------------------------------------------------------
// Submission idempotency key — a double-click sends the same body ⇒ same key,
// so the DB UNIQUE(submission_key) dedups it to a single attempt/evidence row.
// ---------------------------------------------------------------------------

/** Stable JSON (sorted keys) so equal submissions serialise identically. */
export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(',')}}`;
}

/**
 * Deterministic submission key for one answer on one assignment. Same owner +
 * assignment + answer ⇒ identical key (double-submit dedup). A genuinely
 * different answer on the same assignment produces a new key (a new attempt).
 */
export function deriveSubmissionKey(
  ownerUserId: string,
  assignmentId: string,
  submission: Submission,
): string {
  return `companion:attempt:${ownerUserId}:${assignmentId}:${stableStringify(submission)}`;
}

// ---------------------------------------------------------------------------
// Reward policy (spec §6.2) — values come from DATA (companion_reward_policy /
// the DB), NEVER hardcoded in code paths. The constant below only documents the
// shape and seeds a fallback when the row is missing (mirrors economy DEFAULT_CONFIG).
// ---------------------------------------------------------------------------

export interface RewardEntry {
  xp: number;
  coins: number;
}

export interface RewardPolicy {
  lesson_node_first: RewardEntry;
  competency_pass_first: RewardEntry;
  due_review: RewardEntry;
  post_game_review: RewardEntry;
  chapter_first: RewardEntry;
}

/** Seed/fallback only (spec §6.2). Runtime reads companion_reward_policy. */
export const DEFAULT_REWARD_POLICY: RewardPolicy = {
  lesson_node_first: { xp: 20, coins: 5 },
  competency_pass_first: { xp: 30, coins: 10 },
  due_review: { xp: 15, coins: 5 },
  post_game_review: { xp: 15, coins: 5 },
  chapter_first: { xp: 50, coins: 20 },
};

function entry(raw: unknown, fallback: RewardEntry): RewardEntry {
  const e = (raw ?? {}) as Partial<RewardEntry>;
  return {
    xp: Number.isFinite(e.xp) ? (e.xp as number) : fallback.xp,
    coins: Number.isFinite(e.coins) ? (e.coins as number) : fallback.coins,
  };
}

/** Merge a (possibly partial) stored policy config over the defaults. */
export function normalizeRewardPolicy(raw: unknown): RewardPolicy {
  const c = (raw ?? {}) as Partial<RewardPolicy>;
  return {
    lesson_node_first: entry(c.lesson_node_first, DEFAULT_REWARD_POLICY.lesson_node_first),
    competency_pass_first: entry(c.competency_pass_first, DEFAULT_REWARD_POLICY.competency_pass_first),
    due_review: entry(c.due_review, DEFAULT_REWARD_POLICY.due_review),
    post_game_review: entry(c.post_game_review, DEFAULT_REWARD_POLICY.post_game_review),
    chapter_first: entry(c.chapter_first, DEFAULT_REWARD_POLICY.chapter_first),
  };
}

/** The reward for a first independent competency pass (the only Phase 2 grant). */
export function rewardForCompetencyPass(policy: RewardPolicy): RewardEntry {
  return policy.competency_pass_first;
}
