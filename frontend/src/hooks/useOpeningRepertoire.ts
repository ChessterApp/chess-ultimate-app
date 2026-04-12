/**
 * useOpeningRepertoire — Hook for managing opening repertoire data
 * Communicates with /api/openings backend endpoints
 */

import { useState, useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';
import { apiFetch as globalApiFetch } from '@/lib/api';

const API_BASE = '/api/openings';

// ─── Types ───────────────────────────────

export interface Repertoire {
  id: string;
  name: string;
  color: 'w' | 'b';
  description: string | null;
  is_primary: boolean;
  starting_fen: string | null;
  starting_move_line: string | null;
  created_at: string;
  updated_at: string;
  node_count?: number;
}

export interface OpeningNode {
  id: string;
  repertoire_id: string;
  parent_id: string | null;
  fen: string;
  move_san: string | null;
  move_uci: string | null;
  move_number: number;
  is_white_move: boolean | null;
  opening_name: string | null;
  eco_code: string | null;
  notes: string | null;
  priority: number;
  is_critical: boolean;
  times_trained: number;
  times_correct: number;
  last_trained_at: string | null;
  next_review_at: string | null;
  ease_factor: number;
  interval_days: number;
  created_at: string;
  updated_at: string;
  children?: OpeningNode[];
  arrows?: ArrowAnnotation[];
}

export interface ArrowAnnotation {
  id: string;
  node_id: string;
  from_square: string;
  to_square: string;
  color: string;
  opacity: number;
}

export interface GameLink {
  id: string;
  node_id: string;
  game_source: 'internal' | 'lichess' | 'chesscom' | 'pgn' | 'user';
  game_id: string | null;
  game_pgn: string | null;
  white_player: string | null;
  black_player: string | null;
  white_elo: number | null;
  black_elo: number | null;
  result: string | null;
  date_played: string | null;
  event_name: string | null;
  created_at: string;
}

export interface ImportPgnResult {
  imported: number;
  skipped: number;
  errors: string[];
  nodes?: Partial<OpeningNode>[];
}

export interface TrainingStats {
  total_nodes: number;
  trained_nodes: number;
  due_nodes: number;
  total_reviews: number;
  accuracy: number;
}

export interface GameSearchResult {
  id: string | number;
  source: string;
  white: string;
  black: string;
  white_name?: string;
  black_name?: string;
  white_elo: number | null;
  black_elo: number | null;
  result: string;
  date: string;
  year?: number | string;
  eco: string | null;
  opening: string | null;
  event: string | null;
  pgn?: string;
  pgn_offset?: number;
  pgn_length?: number;
  url?: string;
}

export interface MoveCandidate {
  uci: string;
  san: string;
  count: number;
  percentage: number;
  white_wins: number;
  draws: number;
  black_wins: number;
  avg_elo: number | null;
  avg_year: number | null;
  score: string;
  winrate: string;
}

export interface CandidatesResponse {
  status: string;
  total_games: number;
  moves: MoveCandidate[];
}

export interface TopPlayer {
  name: string;
  elo: number;
  title: string;
  games: number;
}

// ─── Hook ────────────────────────────────

export function useOpeningRepertoire() {
  const { getToken } = useAuth();
  const [repertoires, setRepertoires] = useState<Repertoire[]>([]);
  const [currentTree, setCurrentTree] = useState<OpeningNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [treeLoading, setTreeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchWithAuth = useCallback(async <T>(path: string, options?: RequestInit & { timeout?: number }): Promise<T> => {
    const token = await getToken();
    if (!token) {
      throw new Error('Not authenticated');
    }
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    };
    return globalApiFetch<T>(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers, ...options?.headers },
    });
  }, [getToken]);

  // ── Repertoire CRUD ──────────

  const fetchRepertoires = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWithAuth<{ repertoires: Repertoire[] }>('/repertoires');
      setRepertoires(data.repertoires);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const createRepertoire = useCallback(async (
    name: string,
    color: 'w' | 'b',
    opts?: { description?: string; startingFen?: string; startingMoveLine?: string }
  ): Promise<Repertoire> => {
    const data = await fetchWithAuth<{ repertoire: Repertoire }>('/repertoires', {
      method: 'POST',
      body: JSON.stringify({ name, color, ...opts }),
    });
    await fetchRepertoires();
    return data.repertoire;
  }, [fetchRepertoires]);

  const updateRepertoire = useCallback(async (id: string, updates: Partial<Repertoire>) => {
    await fetchWithAuth(`/repertoires/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
    await fetchRepertoires();
  }, [fetchRepertoires]);

  const deleteRepertoire = useCallback(async (id: string) => {
    await fetchWithAuth(`/repertoires/${id}`, { method: 'DELETE' });
    await fetchRepertoires();
  }, [fetchRepertoires]);

  // ── Tree ──────────────────────

  const fetchTree = useCallback(async (repertoireId: string, silent = false) => {
    if (!silent) setTreeLoading(true);
    try {
      const data = await fetchWithAuth<{ repertoire: Repertoire; tree: OpeningNode }>(`/repertoires/${repertoireId}`);
      setCurrentTree(data.tree);
    } catch (e: any) {
      if (!silent) setError(e.message);
    } finally {
      if (!silent) setTreeLoading(false);
    }
  }, []);

  const addNode = useCallback(async (
    parentId: string,
    moveSan: string,
    moveUci: string,
    newFen: string
  ): Promise<OpeningNode> => {
    const data = await fetchWithAuth<OpeningNode>('/nodes', {
      method: 'POST',
      body: JSON.stringify({ parentId, moveSan, moveUci, newFen }),
    });
    return data;
  }, []);

  const updateNode = useCallback(async (
    nodeId: string,
    data: { notes?: string; priority?: number; isCritical?: boolean }
  ) => {
    await fetchWithAuth(`/nodes/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }, []);

  const deleteNode = useCallback(async (nodeId: string) => {
    await fetchWithAuth(`/nodes/${nodeId}`, { method: 'DELETE' });
  }, []);

  // ── Starting position ────────

  const setStartingPosition = useCallback(async (
    repertoireId: string,
    fen: string,
    moveLine?: string
  ) => {
    await fetchWithAuth(`/repertoires/${repertoireId}/starting-position`, {
      method: 'PUT',
      body: JSON.stringify({ fen, moveLine }),
    });
  }, []);

  // ── PGN import/export ────────

  const importPgn = useCallback(async (
    repertoireId: string,
    pgn: string,
    maxPly?: number
  ): Promise<ImportPgnResult> => {
    return fetchWithAuth(`/repertoires/${repertoireId}/import`, {
      method: 'POST',
      body: JSON.stringify({ pgn, maxPly: maxPly || 30 }),
    });
  }, []);

  const exportPgn = useCallback(async (
    repertoireId: string,
    includeNotes?: boolean
  ): Promise<string> => {
    const notes = includeNotes !== false ? 'true' : 'false';
    return fetchWithAuth<string>(`/repertoires/${repertoireId}/pgn?include_notes=${notes}`);
  }, []);

  // ── Arrows ───────────────────

  const addArrow = useCallback(async (
    nodeId: string,
    fromSquare: string,
    toSquare: string,
    color?: string
  ): Promise<ArrowAnnotation> => {
    return fetchWithAuth(`/nodes/${nodeId}/arrows`, {
      method: 'POST',
      body: JSON.stringify({ fromSquare, toSquare, color: color || 'green' }),
    });
  }, []);

  const deleteArrow = useCallback(async (nodeId: string, arrowId: string) => {
    await fetchWithAuth(`/nodes/${nodeId}/arrows/${arrowId}`, { method: 'DELETE' });
  }, []);

  // ── Game search & linking ────

  const fetchGamesByPosition = useCallback(async (
    fen: string,
    limit: number = 5,
    playerColor: string = '',
    playerName: string = '',
    sortBy: string = 'rating',
    opponentName: string = '',
    result: string = '',
    whiteEloMin: number = 0,
    whiteEloMax: number = 3500,
    blackEloMin: number = 0,
    blackEloMax: number = 3500,
    dateFrom: string = '',
    dateTo: string = '',
    ecoCode: string = '',
    eventName: string = ''
  ): Promise<{ games: GameSearchResult[]; total: number; indexed: boolean; count_exact?: boolean }> => {
    const params = new URLSearchParams({ fen, limit: String(limit) });
    if (playerColor) params.set('player_color', playerColor);
    if (playerName) params.set('player_name', playerName);
    if (opponentName) params.set('opponent_name', opponentName);
    if (sortBy && sortBy !== 'rating') params.set('sort_by', sortBy);
    if (result) params.set('result', result);
    // Only send ELO params when they differ from defaults
    if (whiteEloMin !== 0) params.set('white_elo_min', String(whiteEloMin));
    if (whiteEloMax !== 3500) params.set('white_elo_max', String(whiteEloMax));
    if (blackEloMin !== 0) params.set('black_elo_min', String(blackEloMin));
    if (blackEloMax !== 3500) params.set('black_elo_max', String(blackEloMax));
    // New filters
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    if (ecoCode) params.set('eco_code', ecoCode);
    if (eventName) params.set('event_name', eventName);
    const data = await fetchWithAuth<{ games: GameSearchResult[]; total: number; indexed: boolean; count_exact?: boolean }>(`/games/by-position?${params}`, { timeout: 120000 });
    return data;
  }, []);

  const fetchPositionCount = useCallback(async (fen: string): Promise<number> => {
    const params = new URLSearchParams({ fen });
    const data = await fetchWithAuth<{ count: number }>(`/games/position-count?${params}`);
    return data.count;
  }, []);

  const fetchGamePgn = useCallback(async (gameId: number): Promise<string> => {
    const data = await fetchWithAuth<{ pgn: string }>(`/games/${gameId}/pgn`);
    return data.pgn;
  }, []);

  const fetchLichessPgn = useCallback(async (gameId: string): Promise<string> => {
    const data = await fetchWithAuth<{ pgn: string }>(`/games/lichess/${gameId}/pgn`);
    return data.pgn;
  }, []);

  const searchGames = useCallback(async (
    source: string,
    fen: string,
    opts?: { username?: string; maxGames?: number }
  ): Promise<GameSearchResult[]> => {
    const params = new URLSearchParams({ source, fen });
    if (opts?.username) params.set('username', opts.username);
    if (opts?.maxGames) params.set('max_games', String(opts.maxGames));
    const data = await fetchWithAuth<{ games: GameSearchResult[] }>(`/games/search?${params}`);
    return data.games;
  }, []);

  const searchGamesStream = useCallback((
    source: string,
    fen: string,
    opts: {
      eco?: string;
      minRating?: number;
      username?: string;
      maxGames?: number;
      archiveMonths?: number;
      playerColor?: string;
      resultFilter?: string;
    } | undefined,
    onGame: (game: GameSearchResult) => void,
    onProgress: (progress: { checked: number; found: number }) => void
  ): (() => void) => {
    const params = new URLSearchParams({ source, fen });
    if (opts?.eco) params.set('eco', opts.eco);
    if (opts?.minRating) params.set('min_rating', String(opts.minRating));
    if (opts?.username) params.set('username', opts.username);
    if (opts?.maxGames) params.set('max_games', String(opts.maxGames));
    if (opts?.archiveMonths) params.set('archive_months', String(opts.archiveMonths));
    if (opts?.playerColor) params.set('player_color', opts.playerColor);
    if (opts?.resultFilter) params.set('result_filter', opts.resultFilter);

    const controller = new AbortController();

    getToken().then(async (clerkToken) => {
      const token = clerkToken || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJsb2NhbF91c2VyIn0.FakeTokenForLocalDev';
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      };
      return fetch(`${API_BASE}/games/search/stream?${params}`, {
        headers,
        signal: controller.signal,
      });
    }).then(async (res) => {
      if (!res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'game') {
                onGame(event.game);
              }
              if (event.type === 'progress' || event.type === 'game') {
                onProgress({ checked: event.checked || 0, found: event.found || 0 });
              }
            } catch { /* ignore parse errors */ }
          }
        }
      }
    }).catch((err) => {
      if (err?.name !== 'AbortError') {
        console.error('Game search stream failed:', err);
        onProgress({ checked: 0, found: 0 });
      }
    });

    return () => controller.abort();
  }, [getToken]);

  const linkGame = useCallback(async (nodeId: string, data: Partial<GameLink>) => {
    await fetchWithAuth(`/nodes/${nodeId}/games`, {
      method: 'POST',
      body: JSON.stringify({
        gameSource: data.game_source,
        gameId: data.game_id,
        gamePgn: data.game_pgn,
        whitePlayer: data.white_player,
        blackPlayer: data.black_player,
        whiteElo: data.white_elo,
        blackElo: data.black_elo,
        result: data.result,
        datePlayed: data.date_played,
        eventName: data.event_name,
      }),
    });
  }, []);

  const getNodeGames = useCallback(async (nodeId: string): Promise<GameLink[]> => {
    const data = await fetchWithAuth<{ games: GameLink[] }>(`/nodes/${nodeId}/games`);
    return data.games;
  }, []);

  const deleteGameLink = useCallback(async (gameLinkId: string) => {
    await fetchWithAuth(`/games/${gameLinkId}`, { method: 'DELETE' });
  }, []);

  // ── Training ─────────────────

  const getDueNodes = useCallback(async (
    repertoireId?: string,
    limit?: number
  ): Promise<OpeningNode[]> => {
    const params = new URLSearchParams();
    if (repertoireId) params.set('repertoire_id', repertoireId);
    if (limit) params.set('limit', String(limit));
    const data = await fetchWithAuth<{ nodes: OpeningNode[] }>(`/training/due?${params}`);
    return data.nodes;
  }, []);

  const recordTrainingResult = useCallback(async (
    nodeId: string,
    correct: boolean,
    timeMs?: number
  ) => {
    await fetchWithAuth('/training/result', {
      method: 'POST',
      body: JSON.stringify({ nodeId, correct, timeMs }),
    });
  }, []);

  const getTrainingStats = useCallback(async (
    repertoireId?: string
  ): Promise<TrainingStats> => {
    const params = new URLSearchParams();
    if (repertoireId) params.set('repertoire_id', repertoireId);
    return fetchWithAuth(`/training/stats?${params}`);
  }, []);

  // ─── Move Tree: Candidate moves ───
  const fetchCandidateMoves = useCallback(async (fen: string): Promise<CandidatesResponse> => {
    const params = new URLSearchParams({ fen, limit: '20' });
    const data = await fetchWithAuth<any>(`/positions/candidates?${params}`, { timeout: 60000 });
    return {
      status: data.status || 'ok',
      total_games: data.total_games || 0,
      moves: Array.isArray(data.moves) ? data.moves : [],
    };
  }, []);

  // ─── Move Tree: Top players at position ───
  const fetchTopPlayers = useCallback(async (fen: string): Promise<TopPlayer[]> => {
    const params = new URLSearchParams({ fen, limit: '10' });
    const data = await fetchWithAuth<any>(`/positions/top-players?${params}`, { timeout: 60000 });
    return Array.isArray(data.players) ? data.players : [];
  }, []);

  return {
    // Repertoire CRUD
    repertoires,
    loading,
    error,
    fetchRepertoires,
    createRepertoire,
    updateRepertoire,
    deleteRepertoire,
    // Tree
    currentTree,
    setCurrentTree,
    treeLoading,
    fetchTree,
    addNode,
    updateNode,
    deleteNode,
    // Starting position
    setStartingPosition,
    // PGN
    importPgn,
    exportPgn,
    // Arrows
    addArrow,
    deleteArrow,
    // Game search
    fetchGamesByPosition,
    fetchPositionCount,
    fetchGamePgn,
    fetchLichessPgn,
    searchGames,
    searchGamesStream,
    linkGame,
    getNodeGames,
    deleteGameLink,
    // Training
    getDueNodes,
    recordTrainingResult,
    getTrainingStats,
    // Move tree
    fetchCandidateMoves,
    fetchTopPlayers,
  };
}
