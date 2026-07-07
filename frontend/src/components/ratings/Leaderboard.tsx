'use client';

import RatingBadge from './RatingBadge';
import LeagueBadge from './LeagueBadge';

interface LeaderboardEntry {
  user_id: string;
  rating: number;
  league: string;
  games_played: number;
  is_provisional: boolean;
  peak_rating?: number;
  player_name?: string;
}

interface LeaderboardProps {
  entries: LeaderboardEntry[];
  loading?: boolean;
  className?: string;
}

export default function Leaderboard({ entries, loading, className = '' }: LeaderboardProps) {
  if (loading) {
    return (
      <div className={`rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 ${className}`}>
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Leaderboard</h2>
        </div>
        <div className="px-4 py-8 text-center text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className={`rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 ${className}`}>
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Leaderboard</h2>
      </div>

      {entries.length === 0 ? (
        <div className="px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
          No rated players yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">#</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Player</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">League</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Rating</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400 hidden sm:table-cell">Games</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400 hidden sm:table-cell">Peak</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, i) => (
                <tr key={entry.user_id} className={`border-b border-gray-100 dark:border-gray-700 last:border-0 ${i < 3 ? 'bg-yellow-50/50 dark:bg-yellow-900/10' : ''}`}>
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{i + 1}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-gray-100">
                    {entry.player_name || entry.user_id}
                  </td>
                  <td className="px-4 py-3">
                    <LeagueBadge league={entry.league} />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <RatingBadge rating={entry.rating} league={entry.league} provisional={entry.is_provisional} />
                  </td>
                  <td className="px-4 py-3 text-center text-gray-500 dark:text-gray-400 hidden sm:table-cell">{entry.games_played}</td>
                  <td className="px-4 py-3 text-center text-gray-500 dark:text-gray-400 hidden sm:table-cell">{entry.peak_rating ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
