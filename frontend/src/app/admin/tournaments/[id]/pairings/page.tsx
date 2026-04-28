'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

interface Participant {
  id: string;
  user_id: string;
  player_name: string;
  rating_at_registration: number | null;
}

interface Game {
  id: string;
  round: number;
  board: number;
  white_player_id: string;
  black_player_id: string;
  result: string;
}

interface PairingInput {
  white_player_id: string;
  black_player_id: string;
}

export default function AdminTournamentPairingsPage() {
  const params = useParams();
  const tournamentId = params?.id as string;

  const [participants, setParticipants] = useState<Participant[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [round, setRound] = useState(1);
  const [pairings, setPairings] = useState<PairingInput[]>([{ white_player_id: '', black_player_id: '' }]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    fetchData();
  }, [tournamentId]);

  async function fetchData() {
    setLoading(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const [participantsRes, gamesRes] = await Promise.all([
        fetch(`${backendUrl}/api/tournaments/${tournamentId}/participants`),
        fetch(`${backendUrl}/api/tournaments/${tournamentId}/games`),
      ]);

      if (participantsRes.ok) {
        const data = await participantsRes.json();
        setParticipants(data.participants || []);
      }
      if (gamesRes.ok) {
        const data = await gamesRes.json();
        setGames(data.games || []);
        // Auto-set round to next round
        if (data.games?.length) {
          const maxRound = Math.max(...data.games.map((g: Game) => g.round));
          setRound(maxRound + 1);
        }
      }
    } finally {
      setLoading(false);
    }
  }

  function addPairing() {
    setPairings([...pairings, { white_player_id: '', black_player_id: '' }]);
  }

  function removePairing(index: number) {
    setPairings(pairings.filter((_, i) => i !== index));
  }

  function updatePairing(index: number, field: keyof PairingInput, value: string) {
    const updated = [...pairings];
    updated[index] = { ...updated[index], [field]: value };
    setPairings(updated);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    const validPairings = pairings.filter(p => p.white_player_id && p.black_player_id);
    if (validPairings.length === 0) {
      setError('Add at least one valid pairing');
      setSaving(false);
      return;
    }

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const res = await fetch(`${backendUrl}/api/tournaments/${tournamentId}/pairings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ round, pairings: validPairings }),
      });

      if (res.ok) {
        const data = await res.json();
        setSuccess(`Created ${data.count} pairings for round ${round}`);
        setPairings([{ white_player_id: '', black_player_id: '' }]);
        fetchData();
      } else {
        const data = await res.json();
        setError(data.error || 'Failed to create pairings');
      }
    } catch {
      setError('Network error');
    } finally {
      setSaving(false);
    }
  }

  function getPlayerName(userId: string): string {
    const p = participants.find(p => p.user_id === userId);
    return p?.player_name || userId;
  }

  const roundNumbers = [...new Set(games.map(g => g.round))].sort((a, b) => a - b);

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Pairings</h1>
        <p className="text-gray-500 dark:text-gray-400">Loading...</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Pairings</h1>

      {/* Existing Pairings */}
      {roundNumbers.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Existing Rounds</h2>
          <div className="space-y-4">
            {roundNumbers.map(r => {
              const roundGames = games.filter(g => g.round === r);
              return (
                <div key={r} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Round {r}</h3>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700">
                        <th className="text-left px-2 py-1 font-medium text-gray-500 dark:text-gray-400">Bd</th>
                        <th className="text-left px-2 py-1 font-medium text-gray-500 dark:text-gray-400">White</th>
                        <th className="text-center px-2 py-1 font-medium text-gray-500 dark:text-gray-400">Result</th>
                        <th className="text-left px-2 py-1 font-medium text-gray-500 dark:text-gray-400">Black</th>
                      </tr>
                    </thead>
                    <tbody>
                      {roundGames.map(g => (
                        <tr key={g.id} className="border-b border-gray-100 dark:border-gray-700 last:border-0">
                          <td className="px-2 py-1 text-gray-500">{g.board}</td>
                          <td className="px-2 py-1 text-gray-900 dark:text-gray-100">{getPlayerName(g.white_player_id)}</td>
                          <td className="px-2 py-1 text-center font-mono text-gray-700 dark:text-gray-300">{g.result}</td>
                          <td className="px-2 py-1 text-gray-900 dark:text-gray-100">{getPlayerName(g.black_player_id)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* New Pairings Form */}
      <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Add Pairings</h2>

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 p-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 rounded-lg border border-green-200 bg-green-50 dark:bg-green-900/20 dark:border-green-800 p-3 text-sm text-green-700 dark:text-green-300">
            {success}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Round</label>
            <input
              type="number"
              min={1}
              value={round}
              onChange={e => setRound(parseInt(e.target.value) || 1)}
              className="w-24 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
            />
          </div>

          <div className="space-y-2">
            {pairings.map((pairing, index) => (
              <div key={index} className="flex items-center gap-2">
                <span className="text-xs text-gray-500 w-6">{index + 1}.</span>
                <select
                  value={pairing.white_player_id}
                  onChange={e => updatePairing(index, 'white_player_id', e.target.value)}
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                >
                  <option value="">White...</option>
                  {participants.map(p => (
                    <option key={p.user_id} value={p.user_id}>
                      {p.player_name} {p.rating_at_registration ? `(${p.rating_at_registration})` : ''}
                    </option>
                  ))}
                </select>
                <span className="text-xs text-gray-400">vs</span>
                <select
                  value={pairing.black_player_id}
                  onChange={e => updatePairing(index, 'black_player_id', e.target.value)}
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                >
                  <option value="">Black...</option>
                  {participants.map(p => (
                    <option key={p.user_id} value={p.user_id}>
                      {p.player_name} {p.rating_at_registration ? `(${p.rating_at_registration})` : ''}
                    </option>
                  ))}
                </select>
                {pairings.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removePairing(index)}
                    className="text-red-500 hover:text-red-700 text-xs"
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={addPairing}
            className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
          >
            + Add pairing
          </button>

          <div className="pt-2">
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 transition-colors"
              style={{ backgroundColor: 'var(--brand-primary)' }}
            >
              {saving ? 'Saving...' : 'Save Pairings'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
