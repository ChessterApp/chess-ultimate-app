'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { fetchAndAnalyzeGames, type OnboardingGameData, type PlayerStats, type OpeningStat } from '@/lib/onboarding/gameFetcher';

const STORAGE_KEY = 'chesster_analysis';

// ─── Animated Number ─────────────────────────────────────────────────────────

function AnimatedNumber({ target, suffix = '', duration = 1200 }: { target: number; suffix?: string; duration?: number }) {
  const [value, setValue] = useState(0);
  const ref = useRef<number>(0);

  useEffect(() => {
    const start = performance.now();
    const from = 0;
    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setValue(Math.round(from + (target - from) * eased));
      if (progress < 1) ref.current = requestAnimationFrame(tick);
    }
    ref.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(ref.current);
  }, [target, duration]);

  return <>{value}{suffix}</>;
}

// ─── Donut Chart ─────────────────────────────────────────────────────────────

function DonutChart({ wins, losses, draws }: { wins: number; losses: number; draws: number }) {
  const total = wins + losses + draws;
  if (total === 0) return null;
  const wp = (wins / total) * 100;
  const lp = (losses / total) * 100;
  const dp = (draws / total) * 100;

  return (
    <div className="relative w-48 h-48 mx-auto">
      <div
        className="w-full h-full rounded-full"
        style={{
          background: `conic-gradient(#22c55e 0% ${wp}%, #ef4444 ${wp}% ${wp + lp}%, #6b7280 ${wp + lp}% 100%)`,
        }}
      />
      <div className="absolute inset-4 rounded-full bg-gray-50 dark:bg-gray-900 flex items-center justify-center flex-col">
        <span className="text-2xl font-bold text-gray-900 dark:text-white"><AnimatedNumber target={Math.round(wp)} suffix="%" /></span>
        <span className="text-xs text-gray-500 dark:text-white/50">Win Rate</span>
      </div>
    </div>
  );
}

// ─── Rating Chart (SVG) ─────────────────────────────────────────────────────

function RatingChart({ data }: { data: { date: number; rating: number }[] }) {
  if (data.length < 2) return <p className="text-gray-400 dark:text-white/40 text-center text-sm">Not enough data for chart</p>;

  const W = 600, H = 200, PAD = 40;
  const ratings = data.map(d => d.rating);
  const minR = Math.min(...ratings) - 20;
  const maxR = Math.max(...ratings) + 20;
  const rangeR = maxR - minR || 1;

  const points = data.map((d, i) => ({
    x: PAD + (i / (data.length - 1)) * (W - PAD * 2),
    y: PAD + (1 - (d.rating - minR) / rangeR) * (H - PAD * 2),
  }));

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  const fillD = `${pathD} L${points[points.length - 1].x},${H - PAD} L${points[0].x},${H - PAD} Z`;

  // Grid lines
  const gridLines = 4;
  const gridY = Array.from({ length: gridLines + 1 }, (_, i) => {
    const y = PAD + (i / gridLines) * (H - PAD * 2);
    const val = Math.round(maxR - (i / gridLines) * rangeR);
    return { y, val };
  });

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="xMidYMid meet">
      {/* Grid */}
      {gridY.map((g, i) => (
        <g key={i}>
          <line x1={PAD} y1={g.y} x2={W - PAD} y2={g.y} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
          <text x={PAD - 5} y={g.y + 4} textAnchor="end" fill="rgba(255,255,255,0.3)" fontSize="10">{g.val}</text>
        </g>
      ))}
      {/* Fill */}
      <path d={fillD} fill="url(#ratingGrad)" opacity="0.3" />
      {/* Line */}
      <path d={pathD} fill="none" stroke="#7c3aed" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Dots at start and end */}
      <circle cx={points[0].x} cy={points[0].y} r="4" fill="#7c3aed" />
      <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="4" fill="#7c3aed" stroke="white" strokeWidth="2" />
      <defs>
        <linearGradient id="ratingGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#7c3aed" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// ─── Opening Bar ─────────────────────────────────────────────────────────────

function OpeningBar({ opening }: { opening: OpeningStat }) {
  const color = opening.winRate > 60 ? 'bg-green-500' : opening.winRate >= 40 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="text-gray-700 dark:text-white/80 truncate mr-2">{opening.name}</span>
        <span className="text-gray-500 dark:text-white/50 shrink-0">{opening.winRate}% · {opening.gamesPlayed}g</span>
      </div>
      <div className="h-2 bg-gray-200 dark:bg-white/10 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-700`} style={{ width: `${opening.winRate}%` }} />
      </div>
    </div>
  );
}

// ─── Recommendations ─────────────────────────────────────────────────────────

function generateRecommendations(stats: PlayerStats): string[] {
  const recs: string[] = [];

  // Worst opening
  const allWorst = [...(stats.worstOpeningsWhite || []), ...(stats.worstOpeningsBlack || [])];
  const worst = allWorst.sort((a, b) => a.winRate - b.winRate)[0];
  if (worst && worst.winRate < 40) {
    recs.push(`Your ${worst.name} needs work (${worst.winRate}% win rate) — study alternative lines or switch to a more solid setup.`);
  }

  // Rating trend
  if (stats.ratingTrend === 'declining') {
    recs.push('Your rating has dipped recently. Focus on your strongest openings to stabilize before experimenting.');
  }

  // Time control diversity
  const tc = stats.timeControlPreference;
  if (tc) {
    const alt = tc === 'blitz' ? 'rapid' : tc === 'rapid' ? 'classical' : 'blitz';
    recs.push(`You mostly play ${tc}. Try ${alt} to develop different decision-making skills.`);
  }

  // Focus area
  const focusMap: Record<string, string> = { declining: 'endgame', stable: 'tactical', improving: 'positional' };
  const focus = focusMap[stats.ratingTrend] || 'tactical';
  recs.push(`Practice ${focus} puzzles daily to sharpen your vision and pattern recognition.`);

  return recs;
}

// ─── Loading Skeleton ────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="grid grid-cols-3 gap-3">
        {[1, 2, 3].map(i => <div key={i} className="h-24 bg-gray-200 dark:bg-white/5 rounded-2xl" />)}
      </div>
      <div className="h-48 bg-gray-200 dark:bg-white/5 rounded-2xl" />
      <div className="h-48 bg-gray-200 dark:bg-white/5 rounded-2xl" />
      <div className="h-32 bg-gray-200 dark:bg-white/5 rounded-2xl" />
    </div>
  );
}

// ─── Connect Prompt ──────────────────────────────────────────────────────────

function ConnectPrompt({ onConnect }: { onConnect: (platform: 'chessdotcom' | 'lichess', username: string) => void }) {
  const [platform, setPlatform] = useState<'chessdotcom' | 'lichess'>('chessdotcom');
  const [username, setUsername] = useState('');

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center text-gray-900 dark:text-white">
      <div className="text-6xl">📊</div>
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Connect Your Chess Account</h2>
      <p className="text-gray-500 dark:text-white/60 max-w-sm">Link your Chess.com or Lichess account to see detailed analysis of your games.</p>

      <div className="flex gap-2">
        {(['chessdotcom', 'lichess'] as const).map(p => (
          <button
            key={p}
            onClick={() => setPlatform(p)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${platform === p ? 'bg-purple-600 text-white' : 'bg-gray-100 dark:bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent text-gray-600 dark:text-white/60 hover:bg-gray-200 dark:hover:bg-white/10'}`}
          >
            {p === 'chessdotcom' ? '♔ Chess.com' : '♞ Lichess'}
          </button>
        ))}
      </div>

      <input
        type="text"
        value={username}
        onChange={e => setUsername(e.target.value)}
        placeholder="Enter username..."
        className="bg-gray-100 dark:bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent border border-gray-300 dark:border-white/10 rounded-xl px-4 py-3 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-white/30 text-center w-64 outline-none focus:border-purple-500 transition-colors"
      />

      <button
        onClick={() => username.trim() && onConnect(platform, username.trim())}
        disabled={!username.trim()}
        className="bg-purple-600 hover:bg-purple-500 text-white font-bold px-8 py-3 rounded-full transition-all disabled:opacity-40 hover:scale-105 active:scale-95"
      >
        Analyze My Games
      </button>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function AnalysisPage() {
  const [data, setData] = useState<OnboardingGameData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showConnect, setShowConnect] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as OnboardingGameData;
        if (parsed?.stats?.totalGames) {
          setData(parsed);
          setLoading(false);
          return;
        }
      }
    } catch {}
    setLoading(false);
    setShowConnect(true);
  }, []);

  const handleFetch = useCallback(async (platform: 'chessdotcom' | 'lichess', username: string) => {
    setLoading(true);
    setError(null);
    setShowConnect(false);
    try {
      const result = await fetchAndAnalyzeGames(platform, username);
      if (result.status === 'error') {
        setError(result.error || 'Failed to fetch games');
        setShowConnect(true);
      } else {
        setData(result);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(result));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setShowConnect(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const stats = data?.stats;

  const trendIcon = stats?.ratingTrend === 'improving' ? '↑' : stats?.ratingTrend === 'declining' ? '↓' : '→';
  const trendColor = stats?.ratingTrend === 'improving' ? 'text-green-600 dark:text-green-400' : stats?.ratingTrend === 'declining' ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-white/50';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0f0f0f] text-gray-900 dark:text-white">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold">Your Chess Analysis</h1>
            {data && <p className="text-gray-500 dark:text-white/50 text-sm mt-1">{data.username} · {data.platform === 'chessdotcom' ? 'Chess.com' : 'Lichess'}</p>}
          </div>
          <div className="flex gap-2">
            {data && (
              <button
                onClick={() => handleFetch(data.platform, data.username)}
                disabled={loading}
                className="bg-gray-100 dark:bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent hover:bg-gray-200 dark:hover:bg-white/10 text-gray-600 dark:text-white/70 hover:text-gray-900 dark:hover:text-white px-4 py-2 rounded-xl text-sm transition-all disabled:opacity-40"
              >
                🔄 Refresh
              </button>
            )}
            <button
              onClick={() => { setShowConnect(true); setData(null); }}
              className="bg-gray-100 dark:bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent hover:bg-gray-200 dark:hover:bg-white/10 text-gray-600 dark:text-white/70 hover:text-gray-900 dark:hover:text-white px-4 py-2 rounded-xl text-sm transition-all"
            >
              Switch Account
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-4 mb-6 text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Connect Prompt */}
        {showConnect && !loading && <ConnectPrompt onConnect={handleFetch} />}

        {/* Loading */}
        {loading && <Skeleton />}

        {/* Analysis Content */}
        {stats && !loading && (
          <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent backdrop-blur rounded-2xl p-4 text-center">
                <div className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white"><AnimatedNumber target={stats.totalGames} /></div>
                <div className="text-gray-500 dark:text-white/50 text-sm mt-1">Games</div>
              </div>
              <div className="bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent backdrop-blur rounded-2xl p-4 text-center">
                <div className="text-3xl md:text-4xl font-bold text-green-600 dark:text-green-400"><AnimatedNumber target={stats.winRate} suffix="%" /></div>
                <div className="text-gray-500 dark:text-white/50 text-sm mt-1">Win Rate</div>
              </div>
              <div className="bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent backdrop-blur rounded-2xl p-4 text-center">
                <div className="text-3xl md:text-4xl font-bold text-purple-600 dark:text-purple-400"><AnimatedNumber target={stats.avgRating} /></div>
                <div className="text-gray-500 dark:text-white/50 text-sm mt-1">Avg Rating</div>
              </div>
            </div>

            {/* Donut + Recent Form */}
            <div className="grid md:grid-cols-2 gap-6">
              <div className="bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent backdrop-blur rounded-2xl p-6">
                <h3 className="text-lg font-semibold mb-4">Results</h3>
                <DonutChart wins={stats.wins} losses={stats.losses} draws={stats.draws} />
                <div className="flex justify-center gap-6 mt-4 text-sm">
                  <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-green-500" /> {stats.wins}W</span>
                  <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-red-500" /> {stats.losses}L</span>
                  <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-gray-500" /> {stats.draws}D</span>
                </div>
              </div>

              <div className="bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent backdrop-blur rounded-2xl p-6">
                <h3 className="text-lg font-semibold mb-4">Recent Form</h3>
                <div className="flex gap-2 justify-center flex-wrap mb-6">
                  {stats.recentForm.map((r, i) => (
                    <div
                      key={i}
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                        r === 'win' ? 'bg-green-500' : r === 'loss' ? 'bg-red-500' : 'bg-gray-600'
                      } ${i === 0 ? 'ring-2 ring-white/30 animate-pulse' : ''}`}
                    >
                      {r === 'win' ? 'W' : r === 'loss' ? 'L' : 'D'}
                    </div>
                  ))}
                </div>
                <div className="text-center">
                  <span className={`text-2xl ${trendColor}`}>{trendIcon}</span>
                  <p className="text-gray-500 dark:text-white/50 text-sm mt-1 capitalize">{stats.ratingTrend}</p>
                </div>
              </div>
            </div>

            {/* Rating History */}
            {stats.ratingHistory.length > 1 && (
              <div className="bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent backdrop-blur rounded-2xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold">Rating History</h3>
                  <span className={`text-sm font-medium ${trendColor}`}>{trendIcon} {stats.ratingTrend}</span>
                </div>
                <RatingChart data={stats.ratingHistory} />
              </div>
            )}

            {/* Openings */}
            <div className="grid md:grid-cols-2 gap-6">
              <div className="bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent backdrop-blur rounded-2xl p-6">
                <h3 className="text-lg font-semibold mb-4">♔ As White</h3>
                {[...stats.bestOpeningsWhite, ...stats.worstOpeningsWhite]
                  .sort((a, b) => b.gamesPlayed - a.gamesPlayed)
                  .slice(0, 5)
                  .map((o, i) => <OpeningBar key={i} opening={o} />)}
                {stats.bestOpeningsWhite.length === 0 && <p className="text-gray-400 dark:text-white/30 text-sm">Not enough data</p>}
              </div>
              <div className="bg-white dark:bg-white/5 border border-gray-200 dark:border-transparent backdrop-blur rounded-2xl p-6">
                <h3 className="text-lg font-semibold mb-4">♚ As Black</h3>
                {[...stats.bestOpeningsBlack, ...stats.worstOpeningsBlack]
                  .sort((a, b) => b.gamesPlayed - a.gamesPlayed)
                  .slice(0, 5)
                  .map((o, i) => <OpeningBar key={i} opening={o} />)}
                {stats.bestOpeningsBlack.length === 0 && <p className="text-gray-400 dark:text-white/30 text-sm">Not enough data</p>}
              </div>
            </div>

            {/* AI Recommendations */}
            <div className="bg-purple-50 dark:bg-gray-800/50 backdrop-blur rounded-2xl p-6 border-l-4 border-purple-500">
              <h3 className="text-lg font-semibold mb-4">🤖 AI Recommendations</h3>
              <ul className="space-y-3">
                {generateRecommendations(stats).map((rec, i) => (
                  <li key={i} className="flex gap-3 text-gray-700 dark:text-white/80 text-sm">
                    <span className="text-purple-400 shrink-0">→</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* CTA */}
            <div className="text-center pt-4 pb-8">
              <Link
                href="/learn"
                className="inline-block bg-purple-600 hover:bg-purple-500 text-white font-bold text-lg px-10 py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-all"
              >
                Start Improving →
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
