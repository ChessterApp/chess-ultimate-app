/**
 * Fallback rating → league mapping, mirroring the Chess Empire database's
 * `calc_league_from_rating` RPC (>=900 → A, >=500 → B, else C).
 *
 * Only use this when the API did not supply a league: CE leagues are
 * promotion-event driven (see `student_league_events`), so the stored league
 * in `student_current_ratings` is the source of truth and can legitimately
 * disagree with this formula.
 */
export function getLeague(rating: number): string {
  if (rating >= 900) return 'A';
  if (rating >= 500) return 'B';
  return 'C';
}
