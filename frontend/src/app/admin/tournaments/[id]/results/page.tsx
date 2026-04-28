'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

interface Standing {
  user_id: string;
  rank: number;
  score: number;
  buchholz: number;
  sonneborn_berger: number;
  wins: number;
  draws: number;
  losses: number;
}

interface Tournament {
  id: string;
  name: string;
  status: string;
}

export default function AdminTournamentResultsPage() {
  const params = useParams();
  const tournamentId = params?.id as string;

  const [tournament, setTournament] = useState<Tournament | null>(null);
  const [standings, setStandings] = useState<Standing[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    fetchData();
  }, [tournamentId]);

  async function fetchData() {
    setLoading(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const [tournamentRes, standingsRes] = await Promise.all([
        fetch(`${backendUrl}/api/tournaments/${tournamentId}`),
        fetch(`${backendUrl}/api/tournaments/${tournamentId}/results`),
      ]);

      if (tournamentRes.ok) {
        setTournament(await tournamentRes.json());
      }
      if (standingsRes.ok) {
        const data = await standingsRes.json();
        setStandings(data.standings || []);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleUploadCSV(e: React.FormEvent) {
    e.preventDefault();
    if (!csvText.trim()) return;
    setUploading(true);
    setError('');
    setSuccess('');

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const res = await fetch(`${backendUrl}/api/tournaments/${tournamentId}/results`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: csvText, format: 'csv' }),
      });

      if (res.ok) {
        const data = await res.json();
        setSuccess(`Uploaded ${data.count} results`);
        setCsvText('');
        fetchData();
      } else {
        const data = await res.json();
        setError(data.error || 'Upload failed');
      }
    } catch {
      setError('Network error');
    } finally {
      setUploading(false);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    setSuccess('');

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${backendUrl}/api/tournaments/${tournamentId}/results`, {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        setSuccess(`Uploaded ${data.count} results from file`);
        fetchData();
      } else {
        const data = await res.json();
        setError(data.error || 'Upload failed');
      }
    } catch {
      setError('Network error');
    } finally {
      setUploading(false);
    }
  }

  async function handleFinalize() {
    if (!confirm('Finalize this tournament? This will lock results and trigger rating calculation.')) return;
    setFinalizing(true);
    setError('');
    setSuccess('');

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const res = await fetch(`${backendUrl}/api/tournaments/${tournamentId}/finalize`, {
        method: 'POST',
      });

      if (res.ok) {
        setSuccess('Tournament finalized and ratings updated');
        fetchData();
      } else {
        const data = await res.json();
        setError(data.error || 'Finalization failed');
      }
    } catch {
      setError('Network error');
    } finally {
      setFinalizing(false);
    }
  }

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Results</h1>
        <p className="text-gray-500 dark:text-gray-400">Loading...</p>
      </div>
    );
  }

  const isCompleted = tournament?.status === 'completed';

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Results {tournament ? `— ${tournament.name}` : ''}
        </h1>
        {!isCompleted && (
          <button
            onClick={handleFinalize}
            disabled={finalizing || standings.length === 0}
            className="px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 transition-colors bg-green-600 hover:bg-green-700"
          >
            {finalizing ? 'Finalizing...' : 'Finalize Tournament'}
          </button>
        )}
      </div>

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

      {/* Standings Table */}
      {standings.length > 0 && (
        <section className="mb-6 overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">#</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Player</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Score</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400">W</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400">D</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400">L</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Buch.</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 dark:text-gray-400">SB</th>
              </tr>
            </thead>
            <tbody>
              {standings.map(s => (
                <tr key={s.user_id} className="border-b border-gray-100 dark:border-gray-700 last:border-0">
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{s.rank}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-gray-100">{s.user_id}</td>
                  <td className="px-4 py-3 text-center font-semibold text-gray-900 dark:text-gray-100">{s.score}</td>
                  <td className="px-4 py-3 text-center text-gray-500 dark:text-gray-400">{s.wins}</td>
                  <td className="px-4 py-3 text-center text-gray-500 dark:text-gray-400">{s.draws}</td>
                  <td className="px-4 py-3 text-center text-gray-500 dark:text-gray-400">{s.losses}</td>
                  <td className="px-4 py-3 text-center text-gray-500 dark:text-gray-400">{s.buchholz.toFixed(1)}</td>
                  <td className="px-4 py-3 text-center text-gray-500 dark:text-gray-400">{s.sonneborn_berger.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Upload Results */}
      {!isCompleted && (
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Upload Results</h2>

          {/* File Upload */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Upload CSV File</label>
            <input
              type="file"
              accept=".csv"
              onChange={handleFileUpload}
              disabled={uploading}
              className="text-sm text-gray-500 dark:text-gray-400"
            />
          </div>

          <div className="relative mb-4">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200 dark:border-gray-700" /></div>
            <div className="relative flex justify-center"><span className="px-2 bg-white dark:bg-gray-800 text-xs text-gray-500">or paste CSV</span></div>
          </div>

          {/* CSV Text Input */}
          <form onSubmit={handleUploadCSV}>
            <div className="mb-2">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                Columns: round, board, white_player_id, black_player_id, result
              </p>
              <textarea
                value={csvText}
                onChange={e => setCsvText(e.target.value)}
                rows={5}
                placeholder="round,board,white_player_id,black_player_id,result&#10;1,1,player_a,player_b,1-0&#10;1,2,player_c,player_d,1/2-1/2"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm font-mono"
              />
            </div>
            <button
              type="submit"
              disabled={uploading || !csvText.trim()}
              className="px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 transition-colors"
              style={{ backgroundColor: 'var(--brand-primary)' }}
            >
              {uploading ? 'Uploading...' : 'Upload CSV'}
            </button>
          </form>
        </section>
      )}
    </div>
  );
}
