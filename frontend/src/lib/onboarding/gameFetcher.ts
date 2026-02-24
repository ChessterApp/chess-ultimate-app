import { getOpeningName } from '@/lib/openings/ecoNames';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface OnboardingGameData {
  platform: 'lichess' | 'chessdotcom';
  username: string;
  games: ParsedGame[];
  stats: PlayerStats;
  status: 'idle' | 'fetching' | 'analyzing' | 'ready' | 'error';
  error?: string;
}

export interface ParsedGame {
  id: string;
  result: 'win' | 'loss' | 'draw';
  userColor: 'white' | 'black';
  eco: string;
  openingName: string;
  userRating: number;
  opponentRating: number;
  timeControl: string;
  date: number;
}

export interface PlayerStats {
  totalGames: number;
  wins: number;
  losses: number;
  draws: number;
  winRate: number;
  avgRating: number;
  ratingTrend: 'improving' | 'stable' | 'declining';
  bestOpeningsWhite: OpeningStat[];
  worstOpeningsWhite: OpeningStat[];
  bestOpeningsBlack: OpeningStat[];
  worstOpeningsBlack: OpeningStat[];
  timeControlPreference: string;
  recentForm: ('win' | 'loss' | 'draw')[];
  ratingHistory: { date: number; rating: number }[];
}

export interface OpeningStat {
  name: string;
  eco: string;
  gamesPlayed: number;
  wins: number;
  losses: number;
  draws: number;
  winRate: number;
  avgOpponentRating: number;
}

// ─── Lichess Fetching ────────────────────────────────────────────────────────

interface LichessGame {
  id: string;
  status: string;
  winner?: 'white' | 'black';
  players: {
    white: { user?: { name: string }; rating?: number };
    black: { user?: { name: string }; rating?: number };
  };
  opening?: { eco?: string; name?: string };
  speed: string;
  lastMoveAt: number;
}

async function fetchLichessGames(username: string): Promise<ParsedGame[]> {
  const url = `https://lichess.org/api/games/user/${username}?max=200&pgnInJson=true&opening=true&sort=dateDesc`;
  const res = await fetch(url, {
    headers: { Accept: 'application/x-ndjson' },
  });

  if (!res.ok) {
    if (res.status === 404) throw new Error('User not found on Lichess');
    throw new Error(`Lichess API error: ${res.status}`);
  }

  const text = await res.text();
  const lines = text.trim().split('\n').filter(Boolean);
  const userLower = username.toLowerCase();

  return lines.map((line) => {
    const g: LichessGame = JSON.parse(line);
    const isWhite = g.players.white.user?.name?.toLowerCase() === userLower;
    const userColor: 'white' | 'black' = isWhite ? 'white' : 'black';

    let result: 'win' | 'loss' | 'draw';
    if (!g.winner) {
      result = 'draw';
    } else if (g.winner === userColor) {
      result = 'win';
    } else {
      result = 'loss';
    }

    const eco = g.opening?.eco || '';
    return {
      id: g.id,
      result,
      userColor,
      eco,
      openingName: g.opening?.name || getOpeningName(eco) || 'Unknown',
      userRating: (isWhite ? g.players.white.rating : g.players.black.rating) || 0,
      opponentRating: (isWhite ? g.players.black.rating : g.players.white.rating) || 0,
      timeControl: g.speed || 'unknown',
      date: g.lastMoveAt || 0,
    };
  });
}

// ─── Chess.com Fetching ──────────────────────────────────────────────────────

function extractPgnHeader(pgn: string, header: string): string {
  const re = new RegExp(`\\[${header}\\s+"([^"]*)"\\]`);
  const m = pgn.match(re);
  return m?.[1] || '';
}

interface ChessDotComGame {
  url: string;
  pgn: string;
  time_control: string;
  end_time: number;
  time_class: string;
  white: { username: string; rating: number; result: string };
  black: { username: string; rating: number; result: string };
  eco?: string;
}

const CHESSCOM_LOSS_RESULTS = new Set([
  'checkmated', 'timeout', 'resigned', 'abandoned', 'lose', 'threecheck',
  'kingofthehill', 'bughousepartnerlose',
]);

async function fetchChessDotComGames(username: string): Promise<ParsedGame[]> {
  // Fetch archive list
  const archiveRes = await fetch(
    `https://api.chess.com/pub/player/${username}/games/archives`
  );
  if (!archiveRes.ok) {
    if (archiveRes.status === 404) throw new Error('User not found on Chess.com');
    throw new Error(`Chess.com API error: ${archiveRes.status}`);
  }
  const { archives } = (await archiveRes.json()) as { archives: string[] };

  if (!archives || archives.length === 0) {
    throw new Error('No games found for this Chess.com user');
  }

  const games: ParsedGame[] = [];
  const userLower = username.toLowerCase();

  // Fetch most recent archives until we have 200 games
  for (let i = archives.length - 1; i >= 0 && games.length < 200; i--) {
    const res = await fetch(archives[i]);
    if (!res.ok) continue;
    const data = (await res.json()) as { games: ChessDotComGame[] };
    if (!data.games) continue;

    // Process games in reverse (most recent first)
    for (let j = data.games.length - 1; j >= 0 && games.length < 200; j--) {
      const g = data.games[j];
      const isWhite = g.white.username.toLowerCase() === userLower;
      const userColor: 'white' | 'black' = isWhite ? 'white' : 'black';
      const userResult = isWhite ? g.white.result : g.black.result;

      let result: 'win' | 'loss' | 'draw';
      if (userResult === 'win') {
        result = 'win';
      } else if (CHESSCOM_LOSS_RESULTS.has(userResult)) {
        result = 'loss';
      } else {
        result = 'draw';
      }

      // ECO code: prefer PGN header (always "A00"-"E99"), fallback to URL
      const pgnEco = extractPgnHeader(g.pgn || '', 'ECO');
      const urlPath = g.eco?.replace('https://www.chess.com/openings/', '') || '';
      const ecoCode = pgnEco.match(/^[A-E]\d{2}/)?.[0] || urlPath.match(/^[A-E]\d{2}/)?.[0] || '';
      // Opening name: prefer ECO lookup, then URL path cleaned up
      const urlName = urlPath ? urlPath.split('/')[0]?.replace(/-/g, ' ') : '';

      games.push({
        id: g.url?.split('/').pop() || String(g.end_time),
        result,
        userColor,
        eco: ecoCode,
        openingName: getOpeningName(ecoCode) || urlName || 'Unknown',
        userRating: isWhite ? g.white.rating : g.black.rating,
        opponentRating: isWhite ? g.black.rating : g.white.rating,
        timeControl: g.time_class || 'unknown',
        date: g.end_time * 1000,
      });
    }
  }

  return games;
}

// ─── Stats Calculation ───────────────────────────────────────────────────────

function calculateOpeningStats(
  games: ParsedGame[],
  color: 'white' | 'black'
): { best: OpeningStat[]; worst: OpeningStat[] } {
  const colorGames = games.filter((g) => g.userColor === color);
  const grouped = new Map<string, ParsedGame[]>();

  for (const g of colorGames) {
    if (!g.eco) continue;
    const key = g.eco;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(g);
  }

  const stats: OpeningStat[] = [];
  for (const [eco, gs] of grouped) {
    if (gs.length < 3) continue;
    const wins = gs.filter((g) => g.result === 'win').length;
    const losses = gs.filter((g) => g.result === 'loss').length;
    const draws = gs.length - wins - losses;
    stats.push({
      name: getOpeningName(eco) || gs[0].openingName || eco,
      eco,
      gamesPlayed: gs.length,
      wins,
      losses,
      draws,
      winRate: Math.round((wins / gs.length) * 100),
      avgOpponentRating: Math.round(
        gs.reduce((s, g) => s + g.opponentRating, 0) / gs.length
      ),
    });
  }

  const sorted = [...stats].sort((a, b) => b.winRate - a.winRate || b.gamesPlayed - a.gamesPlayed);
  return {
    best: sorted.slice(0, 3),
    worst: sorted.slice(-3).reverse(),
  };
}

function calculateStats(games: ParsedGame[]): PlayerStats {
  const wins = games.filter((g) => g.result === 'win').length;
  const losses = games.filter((g) => g.result === 'loss').length;
  const draws = games.length - wins - losses;

  const avgRating = games.length
    ? Math.round(games.reduce((s, g) => s + g.userRating, 0) / games.length)
    : 0;

  // Rating trend: compare first 50 vs last 50 (games are sorted recent-first)
  let ratingTrend: 'improving' | 'stable' | 'declining' = 'stable';
  if (games.length >= 20) {
    const recentSlice = games.slice(0, Math.min(50, Math.floor(games.length / 2)));
    const olderSlice = games.slice(-Math.min(50, Math.floor(games.length / 2)));
    const recentAvg = recentSlice.reduce((s, g) => s + g.userRating, 0) / recentSlice.length;
    const olderAvg = olderSlice.reduce((s, g) => s + g.userRating, 0) / olderSlice.length;
    const diff = recentAvg - olderAvg;
    if (diff > 30) ratingTrend = 'improving';
    else if (diff < -30) ratingTrend = 'declining';
  }

  // Time control preference
  const tcCounts = new Map<string, number>();
  for (const g of games) {
    tcCounts.set(g.timeControl, (tcCounts.get(g.timeControl) || 0) + 1);
  }
  const timeControlPreference = [...tcCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || 'unknown';

  const whiteStats = calculateOpeningStats(games, 'white');
  const blackStats = calculateOpeningStats(games, 'black');

  return {
    totalGames: games.length,
    wins,
    losses,
    draws,
    winRate: games.length ? Math.round((wins / games.length) * 100) : 0,
    avgRating,
    ratingTrend,
    bestOpeningsWhite: whiteStats.best,
    worstOpeningsWhite: whiteStats.worst,
    bestOpeningsBlack: blackStats.best,
    worstOpeningsBlack: blackStats.worst,
    timeControlPreference,
    recentForm: games.slice(0, 10).map((g) => g.result),
    ratingHistory: games
      .map((g) => ({ date: g.date, rating: g.userRating }))
      .filter((r) => r.rating > 0)
      .reverse(), // chronological order for charts
  };
}

// ─── Most Played Openings ────────────────────────────────────────────────────

export interface MostPlayedOpening {
  name: string;
  eco: string;
  gamesPlayed: number;
  playPercentage: number;
  winRate: number;
  wins: number;
  losses: number;
  draws: number;
}

export function getMostPlayedOpenings(
  games: ParsedGame[],
  color: 'white' | 'black'
): MostPlayedOpening[] {
  const colorGames = games.filter((g) => g.userColor === color);
  if (colorGames.length === 0) return [];

  const grouped = new Map<string, ParsedGame[]>();
  for (const g of colorGames) {
    if (!g.eco) continue;
    const key = g.eco;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(g);
  }

  const stats: MostPlayedOpening[] = [];
  for (const [eco, gs] of grouped) {
    if (gs.length < 2) continue;
    const wins = gs.filter((g) => g.result === 'win').length;
    const losses = gs.filter((g) => g.result === 'loss').length;
    const draws = gs.length - wins - losses;
    stats.push({
      name: getOpeningName(eco) || gs[0].openingName || eco,
      eco,
      gamesPlayed: gs.length,
      playPercentage: Math.round((gs.length / colorGames.length) * 100),
      winRate: Math.round((wins / gs.length) * 100),
      wins,
      losses,
      draws,
    });
  }

  return stats.sort((a, b) => b.gamesPlayed - a.gamesPlayed).slice(0, 3);
}

// ─── Main Export ─────────────────────────────────────────────────────────────

export async function fetchAndAnalyzeGames(
  platform: 'lichess' | 'chessdotcom',
  username: string
): Promise<OnboardingGameData> {
  const result: OnboardingGameData = {
    platform,
    username,
    games: [],
    stats: {} as PlayerStats,
    status: 'fetching',
  };

  try {
    const games =
      platform === 'lichess'
        ? await fetchLichessGames(username)
        : await fetchChessDotComGames(username);

    if (games.length === 0) {
      return { ...result, status: 'error', error: 'No games found for this user' };
    }

    result.games = games;
    result.status = 'analyzing';
    result.stats = calculateStats(games);
    result.status = 'ready';
    return result;
  } catch (err) {
    return {
      ...result,
      status: 'error',
      error: err instanceof Error ? err.message : 'Failed to fetch games',
    };
  }
}
