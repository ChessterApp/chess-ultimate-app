/**
 * Coach home — roster stats.
 *
 * Pure aggregation over a coach's active roster (from
 * `listActiveStudentsByCoach`). Kept separate from the render pipeline and the
 * `server-only` client so it can be unit-tested directly.
 */
import type { CEActiveStudent } from './chess-empire-client';

export interface CoachLeagueCount {
  league: string;
  count: number;
}

export interface CoachHomeStats {
  /** Total active students assigned to the coach. */
  total: number;
  /** Count with a real razryad (set, non-empty, not "none"). */
  withRazryad: number;
  /** Per-league counts, most populous first (ties broken alphabetically). */
  leagueBreakdown: CoachLeagueCount[];
}

/**
 * "Has razryad" per the CE convention: `razryad` is a string that is unset for
 * unranked students and the literal "none" otherwise. Case/whitespace tolerant.
 */
export function hasRazryad(razryad: string | null | undefined): boolean {
  const v = (razryad ?? '').trim().toLowerCase();
  return v !== '' && v !== 'none';
}

export function computeCoachStats(roster: CEActiveStudent[]): CoachHomeStats {
  let withRazryad = 0;
  const counts = new Map<string, number>();
  for (const s of roster) {
    if (hasRazryad(s.current_razryad)) withRazryad += 1;
    const league = (s.current_league ?? '').trim();
    if (league) counts.set(league, (counts.get(league) ?? 0) + 1);
  }
  const leagueBreakdown = [...counts.entries()]
    .map(([league, count]) => ({ league, count }))
    .sort((a, b) => b.count - a.count || a.league.localeCompare(b.league));
  return { total: roster.length, withRazryad, leagueBreakdown };
}
