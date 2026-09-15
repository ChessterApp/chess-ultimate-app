/**
 * Lesson-derived gamification — for NON-LINKED Chesster users (§Option B).
 *
 * Users not connected to a Chess-Empire tournament account have no
 * tournament-driven economy, so their XP / rank / streak are derived from their
 * own lesson-completion history instead of accruing to zero. Pure and
 * side-effect-free so it can be unit tested without a database.
 *
 * Rank math reuses the EXISTING `rankForXp` / `rankProgress` from `economy.ts`
 * unchanged — only the XP source differs.
 */
import {
  type RankRow,
  type RankProgress,
  rankForXp,
  rankProgress,
} from './economy';

/** Locked economy decision: every completed lesson is worth this much XP. */
export const XP_PER_LESSON = 10;

/**
 * Default rank ladder for non-linked users. Mirrors the chess-empire seed
 * ladder (migration 033) so lesson XP maps to the same visual ranks a linked
 * player would see. Non-CE tenants have no per-org `gamification_ranks` row, so
 * this constant is the client-side source of truth for the non-linked path.
 */
export const DEFAULT_RANKS: RankRow[] = [
  { code: 'pawn', name_ru: 'Пешка', name_kk: 'Сарбаз', name_en: 'Pawn', min_xp: 0, sort_order: 1 },
  { code: 'knight', name_ru: 'Конь', name_kk: 'Ат', name_en: 'Knight', min_xp: 10, sort_order: 2 },
  { code: 'bishop', name_ru: 'Слон', name_kk: 'Піл', name_en: 'Bishop', min_xp: 30, sort_order: 3 },
  { code: 'rook', name_ru: 'Ладья', name_kk: 'Тура', name_en: 'Rook', min_xp: 70, sort_order: 4 },
  { code: 'queen', name_ru: 'Ферзь', name_kk: 'Уәзір', name_en: 'Queen', min_xp: 150, sort_order: 5 },
  { code: 'king', name_ru: 'Король', name_kk: 'Патша', name_en: 'King', min_xp: 300, sort_order: 6 },
];

/** XP earned from N completed lessons. Negative / non-finite inputs → 0. */
export function deriveXpFromCompletions(totalCompletions: number): number {
  if (!Number.isFinite(totalCompletions) || totalCompletions <= 0) return 0;
  return Math.floor(totalCompletions) * XP_PER_LESSON;
}

export interface DerivedProfile {
  xp: number;
  rank: RankRow | null;
  rankProgress: RankProgress;
}

/**
 * Full non-linked profile: completions → XP → rank + progress. Feeds the
 * derived XP into the existing rank ladder helpers (imported, not duplicated).
 */
export function deriveProfile(
  totalCompletions: number,
  ranks: RankRow[] = DEFAULT_RANKS,
): DerivedProfile {
  const xp = deriveXpFromCompletions(totalCompletions);
  return {
    xp,
    rank: rankForXp(ranks, xp),
    rankProgress: rankProgress(ranks, xp),
  };
}

/** UTC calendar day (YYYY-MM-DD) of a date or datetime string. */
function toDayUTC(dateStr: string): string {
  return dateStr.slice(0, 10);
}

/** Add `days` to a YYYY-MM-DD string in UTC, returning YYYY-MM-DD. */
function addDaysUTC(day: string, days: number): string {
  const d = new Date(day + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/**
 * Consecutive calendar days (ending today, or yesterday if nothing today) that
 * have ≥1 lesson completion. Timezone basis is UTC, matching the ISO-week math
 * in `economy.ts`. Dates are normalized to day granularity and deduped, so
 * multiple completions on the same day count once. Empty input → 0.
 */
export function computeDailyStreak(completionDates: string[], today: Date): number {
  if (!completionDates || completionDates.length === 0) return 0;

  const days = new Set(completionDates.map(toDayUTC));
  const todayStr = today.toISOString().slice(0, 10);

  // Anchor the run at today; if there's no completion today, a streak can still
  // be "current" if it ran up to yesterday.
  let cursor = todayStr;
  if (!days.has(cursor)) {
    cursor = addDaysUTC(todayStr, -1);
    if (!days.has(cursor)) return 0;
  }

  let streak = 0;
  while (days.has(cursor)) {
    streak += 1;
    cursor = addDaysUTC(cursor, -1);
  }
  return streak;
}
