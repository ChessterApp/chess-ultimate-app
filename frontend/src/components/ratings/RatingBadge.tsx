'use client';

import { getLeague } from '@/lib/league';

interface RatingBadgeProps {
  rating: number;
  league?: string;
  provisional?: boolean;
  className?: string;
}

const LEAGUE_COLORS: Record<string, { bg: string; text: string }> = {
  C: { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-700 dark:text-gray-300' },
  B: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-300' },
  A: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-300' },
  Master: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-300' },
};

const LEAGUE_ICONS: Record<string, string> = {
  C: '\u2659',    // White pawn
  B: '\u2658',    // White knight
  A: '\u2657',    // White bishop
  Master: '\u2655', // White queen
};

export default function RatingBadge({ rating, league, provisional, className = '' }: RatingBadgeProps) {
  const resolvedLeague = league || getLeague(rating);
  const colors = LEAGUE_COLORS[resolvedLeague] || LEAGUE_COLORS.C;
  const icon = LEAGUE_ICONS[resolvedLeague] || '';

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text} ${className}`}>
      <span>{icon}</span>
      <span>{rating}{provisional ? '?' : ''}</span>
    </span>
  );
}
