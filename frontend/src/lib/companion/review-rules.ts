/**
 * Companion — pure, framework-free SM-2 review scheduler (Phase 4).
 *
 * The spec's FIXED review ladder (§6.3): first review after 1 day, then 3, 7,
 * and 14 days after each successful completion; a failed or assisted review
 * resets to the first rung (repair practice, new review after 1 day). The ladder
 * values come from DATA (companion_reward_policy.config.review_ladder) and are
 * passed in — never hardcoded in a code path (the constant below only documents
 * the shape + seeds a fallback, mirroring economy DEFAULT_CONFIG).
 *
 * Everything here is deterministic and side-effect-free (no DB / Next imports)
 * and the clock is INJECTED (`now: Date`) so unit tests can advance time
 * deterministically — mirroring state.ts / assessment.ts. The service-role IO
 * that feeds these lives in ./review-service.ts.
 */

const DAY_MS = 86_400_000;

/** Spec §6.3 DEFAULT ladder. Seed/fallback only — runtime reads the policy. */
export const DEFAULT_REVIEW_LADDER: readonly number[] = [1, 3, 7, 14] as const;

/** Coerce a stored ladder into a strictly-ascending, positive-integer rung list. */
export function normalizeLadder(raw: unknown): number[] {
  if (!Array.isArray(raw)) return [...DEFAULT_REVIEW_LADDER];
  const out: number[] = [];
  for (const v of raw) {
    const n = Math.floor(Number(v));
    if (Number.isFinite(n) && n > 0 && (out.length === 0 || n > out[out.length - 1])) {
      out.push(n);
    }
  }
  return out.length ? out : [...DEFAULT_REVIEW_LADDER];
}

/**
 * The interval (days) a review schedules next.
 *  - correct: advance to the next rung STRICTLY above `current` (0 ⇒ first rung;
 *    at/past the last rung ⇒ stay on the last rung — spec caps at 14d).
 *  - miss (or assisted): reset to the FIRST rung (spec: new review after 1 day).
 */
export function nextIntervalDays(
  current: number,
  correct: boolean,
  ladder: number[] = [...DEFAULT_REVIEW_LADDER],
): number {
  const rungs = ladder.length ? ladder : [...DEFAULT_REVIEW_LADDER];
  if (!correct) return rungs[0];
  const cur = Number.isFinite(current) ? current : 0;
  for (const d of rungs) if (d > cur) return d;
  return rungs[rungs.length - 1];
}

/** 1-based rung for an interval (0/unknown ⇒ rung 0 = not yet reviewed). */
export function rungForInterval(
  intervalDays: number,
  ladder: number[] = [...DEFAULT_REVIEW_LADDER],
): number {
  const rungs = ladder.length ? ladder : [...DEFAULT_REVIEW_LADDER];
  const idx = rungs.indexOf(Math.floor(Number(intervalDays)));
  return idx < 0 ? 0 : idx + 1;
}

export interface ReviewSchedule {
  /** The new mastery_state.interval_days (the rung just scheduled). */
  intervalDays: number;
  /** The new mastery_state.next_review_at (ISO 8601). */
  nextReviewAt: string;
}

/**
 * Compute the next schedule for a review result. The clock is injected so tests
 * can move time deterministically; production passes `new Date()`.
 */
export function scheduleReview(params: {
  intervalDays: number;
  correct: boolean;
  now: Date;
  ladder?: number[];
}): ReviewSchedule {
  const next = nextIntervalDays(params.intervalDays, params.correct, params.ladder);
  const at = new Date(params.now.getTime() + next * DAY_MS);
  return { intervalDays: next, nextReviewAt: at.toISOString() };
}

/**
 * Pull-model "due" predicate (ported from backend/api/openings.py:1764 —
 * `next_review_at <= now OR next_review_at is null`). A never-reviewed concept
 * (null) is due immediately; no cron needed (plan A4).
 */
export function isDue(nextReviewAt: string | null | undefined, now: Date): boolean {
  if (!nextReviewAt) return true;
  const t = Date.parse(nextReviewAt);
  if (!Number.isFinite(t)) return true;
  return t <= now.getTime();
}

/**
 * The stable idempotency "marker" for a due OCCURRENCE: the next_review_at that
 * became due (date-only, UTC), or 'initial' for the first-ever review. Two
 * submissions for the same occurrence share a marker ⇒ one reward; advancing to
 * a new rung produces a new occurrence (new date) ⇒ a new reward is possible.
 */
export function dueMarker(nextReviewAt: string | null | undefined): string {
  if (!nextReviewAt) return 'initial';
  const t = Date.parse(nextReviewAt);
  if (!Number.isFinite(t)) return 'initial';
  return new Date(t).toISOString().slice(0, 10);
}

/** The Watchtower chapter's six learning-node families (spec §7.3 W01–W06). */
export const WATCHTOWER_NODE_FAMILIES: readonly string[] = [
  'W01',
  'W02',
  'W03',
  'W04',
  'W05',
  'W06',
] as const;

/** Total Watchtower learning nodes — the chapter-completion target. */
export const WATCHTOWER_TOTAL_NODES = WATCHTOWER_NODE_FAMILIES.length;

export function isWatchtowerNode(family: unknown): family is string {
  return typeof family === 'string' && WATCHTOWER_NODE_FAMILIES.includes(family);
}
