/**
 * League tier thresholds, shared so the RatingBadge and the Chess Empire
 * hero banner agree on the same rating → league mapping.
 */
export function getLeague(rating: number): string {
  if (rating >= 2200) return 'Master';
  if (rating >= 1800) return 'A';
  if (rating >= 1400) return 'B';
  return 'C';
}
