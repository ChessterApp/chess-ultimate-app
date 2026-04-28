'use client';

import { useEffect, useState } from 'react';
import Leaderboard from '@/components/ratings/Leaderboard';

interface LeaderboardEntry {
  user_id: string;
  rating: number;
  league: string;
  games_played: number;
  is_provisional: boolean;
  peak_rating?: number;
  player_name?: string;
}

export default function LeaderboardPage() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [league, setLeague] = useState('');
  const [includeProvisional, setIncludeProvisional] = useState(false);

  useEffect(() => {
    fetchLeaderboard();
  }, [league, includeProvisional]);

  async function fetchLeaderboard() {
    setLoading(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const params = new URLSearchParams();
      if (league) params.set('league', league);
      if (includeProvisional) params.set('include_provisional', 'true');
      params.set('limit', '50');

      const res = await fetch(`${backendUrl}/api/ratings/leaderboard?${params}`);
      if (res.ok) {
        const data = await res.json();
        setEntries(data.leaderboard || []);
      }
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Leaderboard</h1>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-6">
        <select
          value={league}
          onChange={e => setLeague(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm"
        >
          <option value="">All Leagues</option>
          <option value="C">League C (&lt;1400)</option>
          <option value="B">League B (1400-1799)</option>
          <option value="A">League A (1800-2199)</option>
          <option value="Master">Master (2200+)</option>
        </select>

        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            checked={includeProvisional}
            onChange={e => setIncludeProvisional(e.target.checked)}
            className="rounded border-gray-300 dark:border-gray-600"
          />
          Include provisional
        </label>
      </div>

      <Leaderboard entries={entries} loading={loading} />
    </div>
  );
}
