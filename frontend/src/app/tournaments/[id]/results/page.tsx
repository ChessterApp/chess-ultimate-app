import Link from 'next/link';

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

interface Game {
  id: string;
  round: number;
  board: number;
  white_player_id: string;
  black_player_id: string;
  result: string;
}

interface Tournament {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
}

async function fetchTournament(id: string): Promise<Tournament | null> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/tournaments/${id}`, {
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function fetchStandings(id: string): Promise<Standing[]> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/tournaments/${id}/results`, {
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.standings || [];
  } catch {
    return [];
  }
}

async function fetchGames(id: string): Promise<Game[]> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/tournaments/${id}/games`, {
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.games || [];
  } catch {
    return [];
  }
}

export default async function TournamentResultsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [tournament, standings, games] = await Promise.all([
    fetchTournament(id),
    fetchStandings(id),
    fetchGames(id),
  ]);

  if (!tournament) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Tournament Not Found</h1>
      </div>
    );
  }

  const roundNumbers = [...new Set(games.map(g => g.round))].sort((a, b) => a - b);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href={`/tournaments/${id}`} className="text-sm text-blue-600 dark:text-blue-400 hover:underline mb-4 inline-block">
        &larr; Back to Tournament
      </Link>

      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">{tournament.name}</h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
        {new Date(tournament.start_date).toLocaleDateString()} — {new Date(tournament.end_date).toLocaleDateString()}
      </p>

      {/* Standings */}
      {standings.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">Final Standings</h2>
          <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
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
                {standings.map((s, i) => (
                  <tr key={s.user_id} className={`border-b border-gray-100 dark:border-gray-700 last:border-0 ${i < 3 ? 'bg-yellow-50/50 dark:bg-yellow-900/10' : ''}`}>
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
          </div>
        </section>
      )}

      {/* Round Results */}
      {roundNumbers.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">Round Results</h2>
          <div className="space-y-4">
            {roundNumbers.map(r => {
              const roundGames = games.filter(g => g.round === r).sort((a, b) => a.board - b.board);
              return (
                <div key={r} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Round {r}</h3>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700">
                        <th className="text-left px-2 py-1 font-medium text-gray-500 dark:text-gray-400">Bd</th>
                        <th className="text-right px-2 py-1 font-medium text-gray-500 dark:text-gray-400">White</th>
                        <th className="text-center px-2 py-1 font-medium text-gray-500 dark:text-gray-400">Result</th>
                        <th className="text-left px-2 py-1 font-medium text-gray-500 dark:text-gray-400">Black</th>
                      </tr>
                    </thead>
                    <tbody>
                      {roundGames.map(g => (
                        <tr key={g.id} className="border-b border-gray-100 dark:border-gray-700 last:border-0">
                          <td className="px-2 py-1 text-gray-500">{g.board}</td>
                          <td className="px-2 py-1 text-right text-gray-900 dark:text-gray-100">{g.white_player_id}</td>
                          <td className="px-2 py-1 text-center font-mono text-gray-700 dark:text-gray-300">{g.result}</td>
                          <td className="px-2 py-1 text-gray-900 dark:text-gray-100">{g.black_player_id}</td>
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

      {standings.length === 0 && games.length === 0 && (
        <p className="text-gray-500 dark:text-gray-400 text-center py-8">
          No results available yet.
        </p>
      )}
    </div>
  );
}
