/**
 * Companion — pure, framework-free weekly practice-days goal rules (Phase 5).
 *
 * The spec's weekly goal (line 365): a user-adjustable TARGET number of
 * "meaningful practice days" per week (DEFAULT 3). Progress = the count of
 * DISTINCT meaningful practice days in the CURRENT week; it resets at the week
 * boundary by construction (we only count days inside the current week), while
 * earned history remains in competency_evidence. A "meaningful" day has at least
 * one completed learning/assessment/review/placement/game activity — a login or
 * reward claim alone does NOT count (spec line 1200, "meaningful session").
 *
 * HARD INVARIANT (R2): the weekly goal NEVER gates or unlocks anything, and a
 * missed week applies NO penalty. These helpers only COUNT — they expose no
 * "blocked"/"locked"/"penalty" output and are never read by any educational
 * path. See companion/__tests__/r2-invariant.test.ts.
 *
 * Everything here is deterministic and side-effect-free (no DB / Next imports)
 * and the clock is INJECTED (`now: Date`) so unit tests advance time
 * deterministically — mirroring review-rules.ts. The service-role IO that feeds
 * these lives in ./goal-service.ts.
 */

const DAY_MS = 86_400_000;

/** Spec line 365 DEFAULT target + sane bounds. Seed/fallback only — runtime
 * reads companion_reward_policy.config.weekly_goal. */
export const DEFAULT_WEEKLY_GOAL_TARGET = 3;
export const MIN_WEEKLY_GOAL_TARGET = 1;
export const MAX_WEEKLY_GOAL_TARGET = 7;

/**
 * Activity kinds that make a day "meaningful". Mirrors competency_evidence.kind
 * plus 'game' (completed game). 'login' / 'reward' are deliberately NOT here —
 * attendance alone never counts (spec line 1200).
 */
export const MEANINGFUL_ACTIVITY_KINDS: readonly string[] = [
  'learning',
  'assessment',
  'review',
  'placement',
  'game',
] as const;

export function isMeaningfulKind(kind: unknown): boolean {
  return typeof kind === 'string' && MEANINGFUL_ACTIVITY_KINDS.includes(kind);
}

/** One activity record the counter understands (the service maps evidence rows
 * onto this shape). `correct` is ignored — any completed activity is meaningful. */
export interface ActivityRecord {
  kind: string;
  at: string | Date;
}

/** Clamp a stored/requested target to an integer within [MIN, MAX]. A missing or
 * malformed value falls back (default from policy, never hardcoded in a path). */
export function clampTarget(raw: unknown, fallback: number = DEFAULT_WEEKLY_GOAL_TARGET): number {
  const n = Math.floor(Number(raw));
  if (!Number.isFinite(n)) return fallback;
  return Math.max(MIN_WEEKLY_GOAL_TARGET, Math.min(MAX_WEEKLY_GOAL_TARGET, n));
}

/** Whether a target is in-bounds (the PATCH route validates with this). */
export function isValidTarget(raw: unknown): boolean {
  const n = Number(raw);
  return Number.isInteger(n) && n >= MIN_WEEKLY_GOAL_TARGET && n <= MAX_WEEKLY_GOAL_TARGET;
}

/** UTC midnight of the Monday that starts the week containing `now` (ISO week). */
export function weekStart(now: Date): Date {
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const dow = d.getUTCDay(); // 0 = Sunday … 6 = Saturday
  const sinceMonday = (dow + 6) % 7; // Monday → 0
  d.setUTCDate(d.getUTCDate() - sinceMonday);
  return d;
}

export interface WeekBounds {
  /** Inclusive start (Monday 00:00 UTC). */
  start: Date;
  /** Exclusive end (next Monday 00:00 UTC). */
  end: Date;
}

export function weekBounds(now: Date): WeekBounds {
  const start = weekStart(now);
  return { start, end: new Date(start.getTime() + 7 * DAY_MS) };
}

/** UTC calendar-day key (YYYY-MM-DD) — the dedupe unit for distinct days. */
export function utcDayKey(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/**
 * Count DISTINCT meaningful practice days in the week containing `now`. Non-
 * meaningful kinds (login/reward) and activity outside the current week are
 * ignored, so progress resets at the week boundary automatically.
 */
export function countMeaningfulDays(activities: ActivityRecord[], now: Date): number {
  const { start, end } = weekBounds(now);
  const days = new Set<string>();
  for (const a of activities) {
    if (!isMeaningfulKind(a.kind)) continue;
    const t = a.at instanceof Date ? a.at.getTime() : Date.parse(String(a.at));
    if (!Number.isFinite(t)) continue;
    if (t < start.getTime() || t >= end.getTime()) continue;
    days.add(utcDayKey(new Date(t)));
  }
  return days.size;
}

export interface GoalProgress {
  /** The clamped target for this owner. */
  target: number;
  /** Distinct meaningful practice days in the current week (resets weekly). */
  progress: number;
  /** progress >= target. INFORMATIONAL ONLY — never gates anything (R2). */
  met: boolean;
  /** Current week bounds (ISO strings) for the UI. */
  week_start: string;
  week_end: string;
}

/**
 * Compute the full weekly-goal view. `met` is purely informational for the UI —
 * no caller may use it to block or unlock an educational path (R2). There is no
 * penalty field: a zero-progress week simply reports progress 0.
 */
export function computeGoalProgress(params: {
  target: unknown;
  activities: ActivityRecord[];
  now: Date;
  fallbackTarget?: number;
}): GoalProgress {
  const target = clampTarget(params.target, params.fallbackTarget ?? DEFAULT_WEEKLY_GOAL_TARGET);
  const progress = countMeaningfulDays(params.activities, params.now);
  const { start, end } = weekBounds(params.now);
  return {
    target,
    progress,
    met: progress >= target,
    week_start: start.toISOString(),
    week_end: end.toISOString(),
  };
}
